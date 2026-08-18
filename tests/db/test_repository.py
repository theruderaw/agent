"""
Unit tests for app/db/repository.py

These tests mock AsyncSession directly (no real Postgres) so they run fast
and in isolation, per spec §41 ("Unit tests ... repository"). They check:
  - correct fields are set on constructed rows
  - flush() is called, commit() is NEVER called (repo methods must not
    own the transaction boundary — see conversation history / §16)
  - state transitions delegate to next_state() with the right kwargs
  - event sequence numbering
  - not-found paths raise

Integration tests against a real Postgres instance (§44) are a separate
file — these are pure unit tests with a fake/mock session.
"""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.agent.models import FinalAnswer, ToolCall
from app.db.models import Event, EventType, Run, ToolExecution
from app.db.repository import (
    EventRepository,
    RunRepository,
    ToolExecutionRepository,
)
from app.state.state import State


def make_session() -> AsyncMock:
    """
    A minimal AsyncSession stand-in.

    session.add / session.flush / session.refresh / session.get are async
    or sync depending on the real SQLAlchemy API (add is sync, the rest
    are async) — mirror that here so call-signature mistakes get caught.
    """
    session = MagicMock()
    session.add = MagicMock()  # sync in real SQLAlchemy
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()
    session.exec = AsyncMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# RunRepository
# ---------------------------------------------------------------------------


class TestRunRepositoryCreate:
    @pytest.mark.asyncio
    async def test_create_sets_start_state(self):
        session = make_session()
        repo = RunRepository(session)

        added_run: Run | None = None

        def capture_add(obj):
            nonlocal added_run
            added_run = obj

        session.add.side_effect = capture_add

        run_id = await repo.create()

        assert added_run is not None
        assert added_run.state == State.START
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(added_run)
        session.commit.assert_not_called()
        assert run_id == added_run.id

    @pytest.mark.asyncio
    async def test_create_never_commits(self):
        session = make_session()
        repo = RunRepository(session)
        await repo.create()
        session.commit.assert_not_called()


class TestRunRepositoryGet:
    @pytest.mark.asyncio
    async def test_get_returns_run(self):
        session = make_session()
        run = Run(id=uuid4(), state=State.MODEL_CALL)
        session.get.return_value = run

        repo = RunRepository(session)
        result = await repo.get(run.id)

        assert result is run
        session.get.assert_awaited_once_with(Run, run.id)

    @pytest.mark.asyncio
    async def test_get_raises_when_missing(self):
        session = make_session()
        session.get.return_value = None

        repo = RunRepository(session)
        with pytest.raises(ValueError):
            await repo.get(uuid4())


class TestRunRepositoryUpdateState:
    @pytest.mark.asyncio
    async def test_update_state_with_action_transitions_from_model_call(self):
        session = make_session()
        run = Run(id=uuid4(), state=State.MODEL_CALL)
        session.get.return_value = run

        repo = RunRepository(session)
        action = ToolCall(tool="search", arguments={"q": "hi"})
        result = await repo.update_state(run.id, action=action)

        assert result.state == State.TOOL_CALL
        session.flush.assert_awaited_once()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_state_tool_call_transitions_to_model_call(self):
        session = make_session()
        run = Run(id=uuid4(), state=State.TOOL_CALL)
        session.get.return_value = run

        repo = RunRepository(session)
        result = await repo.update_state(run.id)

        assert result.state == State.MODEL_CALL

    @pytest.mark.asyncio
    async def test_update_state_model_call_without_action_raises(self):
        session = make_session()
        run = Run(id=uuid4(), state=State.MODEL_CALL)
        session.get.return_value = run

        repo = RunRepository(session)
        with pytest.raises(ValueError):
            await repo.update_state(run.id)


class TestRunRepositorySetFinalResponse:
    @pytest.mark.asyncio
    async def test_sets_response_and_final_state(self):
        session = make_session()
        run = Run(id=uuid4(), state=State.MODEL_CALL)
        session.get.return_value = run

        repo = RunRepository(session)
        result = await repo.set_final_response(run.id, "the answer")

        assert result.final_response == "the answer"
        assert result.state == State.FINAL
        session.flush.assert_awaited_once()
        session.commit.assert_not_called()


class TestRunRepositorySetRunFailed:
    @pytest.mark.asyncio
    async def test_sets_error_and_failed_state(self):
        session = make_session()
        run = Run(id=uuid4(), state=State.TOOL_CALL)
        session.get.return_value = run

        repo = RunRepository(session)
        result = await repo.set_run_failed(run.id, "boom")

        assert result.error == "boom"
        assert result.state == State.FAILED
        session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# EventRepository
# ---------------------------------------------------------------------------


def make_exec_result(scalar_value):
    """Fakes the object returned by `await session.exec(...)`,
    supporting both `.one()` (used for MAX(sequence)) and `.all()`
    (used for the ordered event list)."""
    result = MagicMock()
    result.one.return_value = scalar_value
    result.all.return_value = scalar_value
    return result


class TestEventRepositoryAppend:
    @pytest.mark.asyncio
    async def test_first_event_gets_sequence_one(self):
        session = make_session()
        session.exec.return_value = make_exec_result(None)

        repo = EventRepository(session)
        run_id = uuid4()
        event = await repo.append(run_id, EventType.TOOL_CALL, {"q": "hi"})

        assert event.sequence == 1
        assert event.event_type == EventType.TOOL_CALL
        assert event.run_id == run_id
        session.flush.assert_awaited_once()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_sequence_increments_from_existing_max(self):
        session = make_session()
        session.exec.return_value = make_exec_result(4)

        repo = EventRepository(session)
        event = await repo.append(uuid4(), EventType.MODEL_INPUT, {})

        assert event.sequence == 5

    @pytest.mark.asyncio
    async def test_event_type_must_be_enum_value_not_arbitrary_string(self):
        with pytest.raises(ValueError):
            Event(
                run_id=uuid4(),
                event_type="TOOL_CALL",
                sequence=1,
                payload={},
            )


class TestEventRepositoryGet:
    @pytest.mark.asyncio
    async def test_returns_events_in_sequence_order(self):
        session = make_session()
        run_id = uuid4()
        events = [
            Event(run_id=run_id, event_type=EventType.MODEL_INPUT, sequence=1, payload={}),
            Event(run_id=run_id, event_type=EventType.MODEL_OUTPUT, sequence=2, payload={}),
        ]
        session.exec.return_value = make_exec_result(events)

        repo = EventRepository(session)
        result = await repo.get(run_id)

        assert result == events

    @pytest.mark.asyncio
    async def test_empty_history_returns_empty_list_not_error(self):
        session = make_session()
        session.exec.return_value = make_exec_result([])

        repo = EventRepository(session)
        result = await repo.get(uuid4())

        assert result == []


# ---------------------------------------------------------------------------
# ToolExecutionRepository
# ---------------------------------------------------------------------------


class TestToolExecutionRepositoryCreateExecution:
    @pytest.mark.asyncio
    async def test_creates_row_and_appends_tool_call_event(self):
        session = make_session()
        session.exec.return_value = make_exec_result(None)

        added: list = []
        session.add.side_effect = lambda obj: added.append(obj)

        repo = ToolExecutionRepository(session)
        run_id = uuid4()
        tool = await repo.create_execution(run_id, "search", {"q": "hi"})

        assert tool.run_id == run_id
        assert tool.tool_name == "search"
        assert tool.arguments == {"q": "hi"}

        assert any(isinstance(o, ToolExecution) for o in added)
        assert any(isinstance(o, Event) for o in added)

        appended_event = next(o for o in added if isinstance(o, Event))
        assert appended_event.event_type == EventType.TOOL_CALL
        assert appended_event.payload == {"q": "hi"}

        session.commit.assert_not_called()


class TestToolExecutionRepositoryCompleteExecution:
    @pytest.mark.asyncio
    async def test_success_path_updates_tool_appends_event_and_transitions_run(self):
        session = make_session()
        tool_id = uuid4()
        run_id = uuid4()

        existing_tool = ToolExecution(
            id=tool_id, run_id=run_id, tool_name="search", arguments={}
        )
        run = Run(id=run_id, state=State.TOOL_CALL)

        session.get.side_effect = [existing_tool, run]
        session.exec.return_value = make_exec_result(None)

        repo = ToolExecutionRepository(session)
        result = await repo.complete_execution(
            tool_execution_id=tool_id,
            run_id=run_id,
            success=True,
            result={"answer": 42},
            error=None,
        )

        assert result.success is True
        assert result.result == {"answer": 42}
        assert result.completed_at is not None
        assert run.state == State.MODEL_CALL
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure_path_sets_error_and_transitions_to_model_call(self):
        session = make_session()
        tool_id = uuid4()
        run_id = uuid4()

        existing_tool = ToolExecution(
            id=tool_id, run_id=run_id, tool_name="search", arguments={}
        )
        run = Run(id=run_id, state=State.TOOL_CALL)

        session.get.side_effect = [existing_tool, run]
        session.exec.return_value = make_exec_result(None)

        repo = ToolExecutionRepository(session)
        result = await repo.complete_execution(
            tool_execution_id=tool_id,
            run_id=run_id,
            success=False,
            result=None,
            error="timeout",
        )

        assert result.success is False
        assert result.error == "timeout"
        assert run.state == State.MODEL_CALL

    @pytest.mark.asyncio
    async def test_missing_tool_execution_raises(self):
        session = make_session()
        session.get.return_value = None

        repo = ToolExecutionRepository(session)
        with pytest.raises(ValueError):
            await repo.complete_execution(
                tool_execution_id=uuid4(),
                run_id=uuid4(),
                success=True,
                result=None,
                error=None,
            )
