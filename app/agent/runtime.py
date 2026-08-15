from uuid import UUID
from pydantic import ValidationError

from app.agent.llms.qwen import call_qwen
from app.agent.models import action_adapter
from app.agent.registry import get_tool
from app.db.database import (
    add_run_iter,
    append_event,
    create_run,
    get_run,
    get_last_events,
    set_run,
)
from app.agent.state import State


MAX_ITERATIONS = 15


def _events_to_context(events) -> str:
    lines = []

    for e in events:
        # MODEL_INPUT is generated context, so don't feed it back into Qwen.
        if e.event_type == "MODEL_INPUT":
            continue

        lines.append(f"[{e.event_type}] {e.payload}")

    return "\n".join(lines)


def _build_context(run_id: UUID, original_task: str) -> str:
    events = get_last_events(run_id, limit=7)
    context = _events_to_context(events)

    return f"""
Original task:
{original_task}

Recent activity:
{context}

Continue solving the original task.
""".strip()


def _loop(run_id, prompt: str, original_task: str):

    for _ in range(MAX_ITERATIONS):

        add_run_iter(run_id)

        append_event(
            run_id=run_id,
            event_type="MODEL_INPUT",
            payload=prompt
        )

        raw_response = call_qwen(prompt)

        set_run(run_id=run_id, status=State.MODEL_CALL)

        append_event(
            run_id=run_id,
            event_type="MODEL_OUTPUT",
            payload=raw_response
        )

        print(raw_response)

        try:
            action = action_adapter.validate_json(raw_response)

        except ValidationError as e:

            append_event(
                run_id=run_id,
                event_type="MODEL_OUTPUT_INVALID",
                payload=str(e)
            )

            prompt = f"""
Original task:
{original_task}

Your last response was not valid JSON for the expected schema.

Error:
{e}

Your response was:
{raw_response}

Respond again with ONLY valid JSON matching the required action schema.
"""

            continue

        # ---------------------------------------------------------
        # TOOL CALL
        # ---------------------------------------------------------

        if action.action == "tool_call":

            append_event(
                run_id=run_id,
                event_type="TOOL_INPUT",
                payload=raw_response
            )

            set_run(run_id, State.TOOL_CALL)

            tool = get_tool(action.tool)

            if tool is None:

                append_event(
                    run_id=run_id,
                    event_type="TOOL_FAILED",
                    payload=f"Unknown tool: {action.tool}"
                )

                prompt = _build_context(
                    run_id,
                    original_task
                )

                continue

            try:
                result = tool(**action.arguments)

            except Exception as e:

                append_event(
                    run_id=run_id,
                    event_type="TOOL_FAILED",
                    payload=str(e)
                )

                prompt = _build_context(
                    run_id,
                    original_task
                )

                continue

            set_run(run_id, State.TOOL_RESULT)

            append_event(
                run_id=run_id,
                event_type="TOOL_OUTPUT",
                payload=result
            )

            prompt = _build_context(
                run_id,
                original_task
            )

            continue

        # ---------------------------------------------------------
        # FINAL
        # ---------------------------------------------------------

        elif action.action == "final":

            append_event(
                run_id=run_id,
                event_type="FINAL",
                payload=raw_response
            )

            set_run(run_id, State.FINAL)

            append_event(
                run_id=run_id,
                event_type="COMPLETED",
                payload=raw_response
            )

            set_run(run_id, State.STOP)

            return (run_id, action.answer)

        # ---------------------------------------------------------
        # ASK USER
        # ---------------------------------------------------------

        elif action.action == "ask_user":

            append_event(
                run_id=run_id,
                event_type="ASK_USER",
                payload=action.question
            )

            set_run(run_id, State.WAITING_FOR_USER)

            return (run_id, action)

        # ---------------------------------------------------------
        # REFUSE
        # ---------------------------------------------------------

        elif action.action == "refuse":

            append_event(
                run_id=run_id,
                event_type="REFUSED",
                payload=action.reason
            )

            set_run(run_id, State.REFUSED)

            append_event(
                run_id=run_id,
                event_type="COMPLETED",
                payload=raw_response
            )

            set_run(run_id, State.STOP)

            return (run_id, action)

    # -------------------------------------------------------------
    # MAX ITERATIONS
    # -------------------------------------------------------------

    append_event(
        run_id=run_id,
        event_type="FAILED",
        payload="Exceeded reasoning depth"
    )

    set_run(run_id, State.FAILED)

    raise ValueError("Exceeded reasoning depth")


def run_agent(prompt: str):

    run_id = create_run()

    append_event(
        run_id=run_id,
        event_type="RUN_STARTED",
        payload=""
    )

    return _loop(
        run_id,
        prompt,
        prompt
    )


def resume_agent(run_id: UUID, user_message: str):

    run = get_run(run_id)

    if run is None:
        raise ValueError(f"Unknown run: {run_id}")

    if run.status != State.WAITING_FOR_USER:
        raise ValueError(
            f"Run {run_id} is not waiting for user input "
            f"(status={run.status})"
        )

    append_event(
        run_id=run_id,
        event_type="USER_RESPONSE",
        payload=user_message
    )

    # Recover original task from the earliest MODEL_INPUT.
    # This is temporary until task is stored directly on agent_runs.
    events = get_last_events(run_id, limit=100)

    original_task = None

    for event in events:
        if event.event_type == "MODEL_INPUT":
            original_task = event.payload
            break

    if original_task is None:
        raise ValueError("Could not recover original task")

    # Find the pending question.
    question = None

    for event in reversed(events):
        if event.event_type == "ASK_USER":
            question = event.payload
            break

    if question is None:
        raise ValueError("Could not find pending user question")

    resumed_prompt = f"""
Original task:
{original_task}

The user was asked:
{question}

Their answer:
{user_message}

Continue solving the original task.
"""

    set_run(run_id, State.MODEL_CALL)

    return _loop(
        run_id,
        resumed_prompt,
        original_task
    )