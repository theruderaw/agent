"""
app/runtime/runtime.py

Agent runtime loop.

Flow:
  load_context -> [resume from user input] -> loop:
    build messages -> call LLM -> parse AgentAction -> execute -> transition -> repeat
  until STOP or FAILED.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.agent.models import (
    AskUser,
    FinalAnswer,
    Refuse,
    SkillRequest,
    ToolCall,
)
from app.core import settings
from app.db.models import EventType
from app.db.repository import EventRepository, RunRepository, ToolExecutionRepository
from app.llm.base import LLM
from app.llm.models import Message
from app.runtime.context import ContextMessage, RunContext, load_context
from app.runtime.util import ModelParseError, build_messages, call_llm
from app.skills.loader import SkillLoader
from app.state.state import State, next_state
from app.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Action handlers
# --------------------------------------------------------------------------

async def _handle_tool_call(
    ctx: RunContext,
    action: ToolCall,
    registry: ToolRegistry,
    tool_executions: ToolExecutionRepository,
    runs: RunRepository,
    session: AsyncSession,
) -> None:
    execution = await tool_executions.create_execution(
        run_id=ctx.run_id,
        tool_name=action.tool,
        arguments=action.arguments,
    )
    await session.commit()

    await runs.update_state(ctx.run_id, action=action)
    await session.commit()

    result = registry.dispatch(action.tool, action.arguments)

    payload = {"result": {"data": result.data}} if result.ok else {"error": result.error}

    await tool_executions.complete_execution(
        tool_execution_id=execution.id,
        run_id=ctx.run_id,
        success=result.ok,
        result={"data": result.data} if result.ok else None,
        error=result.error,
    )
    await session.commit()

    ctx.messages.append(ContextMessage(role="tool", content=json.dumps(payload)))


async def _handle_skill_request(
    ctx: RunContext,
    action: SkillRequest,
    events: EventRepository,
    runs: RunRepository,
    skill_loader: SkillLoader,
    session: AsyncSession,
) -> None:
    await runs.update_state(ctx.run_id, action=action)
    await session.commit()

    try:
        skill_loader.load(action.skill)
    except Exception as e:
        logger.warning("Skill '%s' not found: %s", action.skill, e)
        run = await runs.get(ctx.run_id)
        run.state = State.MODEL_CALL
        await session.flush()
        await session.commit()
        return

    ctx.loaded_skills.add(action.skill)

    await events.append(
        run_id=ctx.run_id,
        event_type=EventType.SKILL_RECEIVED,
        payload={"skill": action.skill},
    )

    run = await runs.get(ctx.run_id)
    run.state = State.MODEL_CALL
    await session.flush()
    await session.commit()

    ctx.state = State.MODEL_CALL


async def _handle_final(
    ctx: RunContext,
    action: FinalAnswer,
    events: EventRepository,
    runs: RunRepository,
    session: AsyncSession,
) -> None:
    await events.append(
        run_id=ctx.run_id,
        event_type=EventType.FINAL,
        payload={"content": action.content},
    )

    await runs.set_final_response(ctx.run_id, action.content)
    await session.commit()


async def _handle_refuse(
    ctx: RunContext,
    action: Refuse,
    events: EventRepository,
    runs: RunRepository,
    session: AsyncSession,
) -> None:
    await events.append(
        run_id=ctx.run_id,
        event_type=EventType.REFUSED,
        payload={"reason": action.reason},
    )

    await runs.set_refused_response(ctx.run_id, action.reason)
    await session.commit()


async def _handle_ask_user(
    ctx: RunContext,
    action: AskUser,
    events: EventRepository,
    runs: RunRepository,
    session: AsyncSession,
) -> None:
    await events.append(
        run_id=ctx.run_id,
        event_type=EventType.ASK_USER,
        payload={"question": action.question},
    )

    await runs.update_state(ctx.run_id, action=action)
    await session.commit()
    ctx.state = State.WAITING_FOR_USER


# --------------------------------------------------------------------------
# Main runtime loop
# --------------------------------------------------------------------------

async def execute_run(
    run_id: UUID,
    session: AsyncSession,
    llm: LLM,
    registry: ToolRegistry,
    skill_loader: SkillLoader,
    user_input: str | None = None,
) -> None:
    runs = RunRepository(session)
    events = EventRepository(session)
    tool_executions = ToolExecutionRepository(session)

    ctx = await load_context(run_id, session)

    # Resume from user input
    if ctx.state == State.WAITING_FOR_USER and user_input is not None:
        await events.append(
            run_id=ctx.run_id,
            event_type=EventType.USER_INPUT,
            payload={"input": user_input},
        )
        run = await runs.get(ctx.run_id)
        run.state = next_state(State.WAITING_FOR_USER)
        await session.flush()
        ctx.state = State.MODEL_CALL
        ctx.messages.append(ContextMessage(role="user", content=user_input))
        await session.commit()

    # Handle fresh run: go straight to waiting for user input
    if ctx.state == State.START:
        run = await runs.get(ctx.run_id)
        run.state = State.WAITING_FOR_USER
        await session.flush()
        ctx.state = State.WAITING_FOR_USER
        await session.commit()
        return

    # Main loop
    for iteration in range(settings.max_iterations):
        if ctx.state in (State.STOP, State.FAILED):
            break

        if ctx.state != State.MODEL_CALL:
            await runs.set_run_failed(ctx.run_id, f"Unexpected state: {ctx.state}")
            await session.commit()
            return

        messages = build_messages(ctx, registry, skill_loader)
        try:
            response, action = await call_llm(llm, messages, events, ctx.run_id)
        except ModelParseError as e:
            await events.append(
                run_id=ctx.run_id,
                event_type=EventType.MODEL_OUTPUT,
                payload={"content": e.content, "action": None, "error": e.reason},
            )
            ctx.messages.append(ContextMessage(
                role="user",
                content=f"Error: {e.reason}. Raw output:\n{e.content}",
            ))
            await _handle_ask_user(
                ctx,
                AskUser(question=f"Model produced invalid output:\n{e.content}"),
                events,
                runs,
                session,
            )
            return

        ctx.messages.append(ContextMessage(role="assistant", content=response.content))

        if isinstance(action, ToolCall):
            await _handle_tool_call(ctx, action, registry, tool_executions, runs, session)
            ctx.state = State.MODEL_CALL

        elif isinstance(action, SkillRequest):
            await _handle_skill_request(
                ctx, action, events, runs, skill_loader, session,
            )

        elif isinstance(action, AskUser):
            await _handle_ask_user(ctx, action, events, runs, session)
            return

        elif isinstance(action, FinalAnswer):
            await _handle_final(ctx, action, events, runs, session)
            ctx.state = next_state(ctx.state, action=action)
            break

        elif isinstance(action, Refuse):
            await _handle_refuse(ctx, action, events, runs, session)
            ctx.state = next_state(ctx.state, action=action)
            break

        else:
            logger.error("Unknown action type: %s", type(action))
            await runs.set_run_failed(ctx.run_id, f"Unknown action: {type(action)}")
            await session.commit()
            return

    else:
        logger.error(
            "Runtime loop exhausted max_iterations=%d for run_id=%s",
            settings.max_iterations,
            run_id,
        )
        await runs.set_run_failed(
            ctx.run_id,
            f"Exceeded maximum iterations ({settings.max_iterations})",
        )
        await session.commit()
