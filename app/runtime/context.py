from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agent.models import AgentAction, agent_action_adapter
from app.db.models import EventType
from app.db.repository import EventRepository, RunRepository
from app.state.state import State


class ToolResult(BaseModel):
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None


class RunContext(BaseModel):
    run_id: UUID
    state: State
    current_action: AgentAction | None = None
    messages: list[str] = Field(default_factory=list)
    loaded_skills: set[str] = Field(default_factory=set)
    tool_result: ToolResult | None = None
    final_response: str | None = None


async def load_context(run_id: UUID, session: AsyncSession) -> RunContext:
    # TODO(recovery): replay assumes events store enough payload to
    # reconstruct messages/current_action faithfully. Not yet exercised
    # against real runtime-emitted events — see Checkpoint 7.
    runs = RunRepository(session)
    events = EventRepository(session)

    run = await runs.get(run_id)
    history = await events.get(run_id)  # already ordered by sequence

    context = RunContext(
        run_id=run.id,
        state=run.state,
        final_response=run.final_response,
    )

    for event in history:
        _apply_event(context, event.event_type, event.payload)

    return context


def _apply_event(context: RunContext, event_type: EventType, payload: dict[str, Any]) -> None:
    if event_type == EventType.MODEL_INPUT:
        context.messages.append(payload["content"])
    elif event_type == EventType.MODEL_OUTPUT:
        if "content" in payload:
            context.messages.append(payload["content"])

        context.current_action = agent_action_adapter.validate_python(payload)

        
    elif event_type == EventType.SKILL_RECEIVED:
        context.loaded_skills.add(payload["skill"])

    elif event_type == EventType.TOOL_CALL:
        context.tool_result = None  # tool in flight, no result yet

    elif event_type == EventType.TOOL_RESULT:
        context.tool_result = ToolResult(success=True, result=payload.get("result"))

    elif event_type == EventType.TOOL_FAILED:
        context.tool_result = ToolResult(success=False, error=payload.get("error"))