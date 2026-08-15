from enum import StrEnum

from app.agent.models import AgentAction


class State(StrEnum):
    START = "start"
    MODEL_CALL = "model_call"
    MODEL_OUTPUT = "model_output"

    SKILL_REQUESTED = "skill_requested"
    SKILL_RECEIVED = "skill_received"

    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_FAILED = "tool_failed"

    WAITING_FOR_USER = "waiting_for_user"

    FINAL = "final"
    REFUSED = "refused"

    STOP = "stop"
    FAILED = "failed"
    
def next_state(
    state: State,
    tool_completed: bool | None = None,
    action: AgentAction | None = None,
) -> State:
    if state == State.START:
        return State.MODEL_CALL

    if state == State.MODEL_CALL:
        return State.MODEL_OUTPUT

    if state == State.MODEL_OUTPUT:
        if action is None:
            raise ValueError("AgentAction required in MODEL_OUTPUT")

        if action.action == "ask_user":
            return State.WAITING_FOR_USER

        if action.action == "skill_request":
            return State.SKILL_REQUESTED

        if action.action == "tool_call":
            return State.TOOL_CALL

        if action.action == "refuse":
            return State.REFUSED

        if action.action == "final":
            return State.FINAL

    if state == State.SKILL_REQUESTED:
        return State.SKILL_RECEIVED

    if state == State.SKILL_RECEIVED:
        return State.MODEL_CALL

    if state == State.TOOL_CALL:
        if tool_completed is None:
            raise ValueError("tool_completed required in TOOL_CALL")
        return State.TOOL_RESULT if tool_completed else State.TOOL_FAILED

    if state == State.TOOL_RESULT:
        return State.MODEL_CALL

    if state == State.TOOL_FAILED:
        return State.MODEL_CALL

    if state == State.WAITING_FOR_USER:
        return State.MODEL_CALL

    if state in (State.FINAL, State.REFUSED):
        return State.STOP

    raise ValueError(f"Invalid state transition from {state}")