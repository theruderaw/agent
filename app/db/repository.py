from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agent.models import AgentAction
from app.db.models import Event, EventType, Run, ToolExecution, utc_now
from app.state.state import State, next_state


class RunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self) -> UUID:
        run = Run(
            state=State.START,
        )

        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run.id

    async def get(self, run_id: UUID) -> Run:
        run = await self.session.get(Run, run_id)
        if not run:
            raise ValueError("Run not found")
        return run

    async def update_state(
        self,
        run_id: UUID,
        action: AgentAction | None = None,
    ) -> Run:
        run = await self.get(run_id)
        run.state = next_state(run.state, action=action)
        await self.session.flush()
        return run

    async def set_final_response(self, run_id: UUID, response: str) -> Run:
        run = await self.get(run_id)
        run.final_response = response
        run.state = State.FINAL
        await self.session.flush()
        return run

    async def set_refused_response(self, run_id: UUID, reason: str) -> Run:
        run = await self.get(run_id)
        run.final_response = reason
        run.state = State.REFUSED
        await self.session.flush()
        return run

    async def set_run_failed(self, run_id: UUID, error: str) -> Run:
        run = await self.get(run_id)
        run.error = error
        run.state = State.FAILED
        await self.session.flush()
        return run


class EventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def append(
        self,
        run_id: UUID,
        event_type: EventType,
        payload: dict[str, Any],
    ) -> Event:
        # NOTE: single-worker-safe only until §48 concurrent-run locking
        # exists. MAX(sequence)+1 is a read-then-write and is NOT race-safe
        # under concurrent workers touching the same run. Revisit once
        # workers multiply — either add proper locking here, or switch
        # Event.sequence to a DB-assigned Identity column (see models.py TODO).
        if not isinstance(event_type, EventType):
            raise ValueError(
                f"event_type must be an EventType, got {event_type!r}"
            )
        result = await self.session.exec(
            select(func.max(Event.sequence)).where(Event.run_id == run_id)
        )
        current_max = result.one()
        next_sequence = (current_max or 0) + 1

        event = Event(
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            sequence=next_sequence,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get(self, run_id: UUID) -> list[Event]:
        result = await self.session.exec(
            select(Event)
            .where(Event.run_id == run_id)
            .order_by(Event.sequence)
        )
        return list(result.all())


class ToolExecutionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_execution(
        self,
        run_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolExecution:
        tool = ToolExecution(
            run_id=run_id,
            tool_name=tool_name,
            arguments=arguments,
        )
        self.session.add(tool)
        await self.session.flush()
        await self.session.refresh(tool)

        events = EventRepository(self.session)
        await events.append(
            run_id=run_id,
            event_type=EventType.TOOL_CALL,
            payload=arguments,
        )

        return tool

    async def complete_execution(
        self,
        tool_execution_id: UUID,
        run_id: UUID,
        success: bool,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> ToolExecution:
        tool = await self.session.get(ToolExecution, tool_execution_id)
        if not tool:
            raise ValueError("ToolExecution not found")

        tool.result = result
        tool.success = success
        tool.error = error
        tool.completed_at = utc_now()
        await self.session.flush()

        events = EventRepository(self.session)
        await events.append(
            run_id=run_id,
            event_type=EventType.TOOL_RESULT if success else EventType.TOOL_FAILED,
            payload={"result": result} if success else {"error": error},
        )

        runs = RunRepository(self.session)
        await runs.update_state(run_id)

        return tool