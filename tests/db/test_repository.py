"""Tests for app/db/repository.py — all branches."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agent.models import FinalAnswer, Refuse, SkillRequest, ToolCall
from app.db.models import Event, EventType, Run, ToolExecution, utc_now
from app.db.repository import EventRepository, RunRepository, ToolExecutionRepository
from app.state.state import State, next_state


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def make_session():
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.get = AsyncMock()
    session.exec = AsyncMock()
    return session


# ─────────────────────────────────────────────
# RunRepository
# ─────────────────────────────────────────────


class TestRunRepositoryCreate:
    @pytest.mark.asyncio
    async def test_create_sets_start_state(self):
        session = make_session()
        repo = RunRepository(session)

        created_run = Run(id=uuid4(), state=State.START)
        session.refresh.side_effect = lambda r: setattr(r, "id", created_run.id)

        run_id = await repo.create()
        assert run_id is not None
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_flushes_before_returning(self):
        session = make_session()
        repo = RunRepository(session)
        flush_called = []

        async def track_flush():
            flush_called.append(True)

        session.flush.side_effect = track_flush
        session.refresh.side_effect = lambda r: setattr(r, "id", uuid4())

        await repo.create()
        assert len(flush_called) == 1


class TestRunRepositoryGet:
    @pytest.mark.asyncio
    async def test_get_existing_run(self):
        session = make_session()
        repo = RunRepository(session)
        run_id = uuid4()
        expected = Run(id=run_id, state=State.MODEL_CALL)
        session.get.return_value = expected

        result = await repo.get(run_id)
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_nonexistent_raises(self):
        session = make_session()
        repo = RunRepository(session)
        session.get.return_value = None

        with pytest.raises(ValueError, match="Run not found"):
            await repo.get(uuid4())


class TestRunRepositoryUpdateState:
    @pytest.mark.asyncio
    async def test_update_state_transitions(self):
        session = make_session()
        repo = RunRepository(session)
        run_id = uuid4()
        run = Run(id=run_id, state=State.MODEL_CALL)
        session.get.return_value = run

        result = await repo.update_state(run_id, action=FinalAnswer(content="done"))
        assert result.state == State.FINAL
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_state_tool_call(self):
        session = make_session()
        repo = RunRepository(session)
        run_id = uuid4()
        run = Run(id=run_id, state=State.MODEL_CALL)
        session.get.return_value = run

        result = await repo.update_state(
            run_id,
            action=ToolCall(tool="x:y", arguments={}),
        )
        assert result.state == next_state(State.MODEL_CALL, action=ToolCall(tool="x:y", arguments={}))

    @pytest.mark.asyncio
    async def test_update_state_skill_request(self):
        session = make_session()
        repo = RunRepository(session)
        run_id = uuid4()
        run = Run(id=run_id, state=State.MODEL_CALL)
        session.get.return_value = run

        result = await repo.update_state(
            run_id,
            action=SkillRequest(skill="git"),
        )
        assert result.state == State.SKILL_REQUESTED


class TestRunRepositorySetFinalResponse:
    @pytest.mark.asyncio
    async def test_sets_response_and_final_state(self):
        session = make_session()
        repo = RunRepository(session)
        run_id = uuid4()
        run = Run(id=run_id, state=State.MODEL_CALL)
        session.get.return_value = run

        result = await repo.set_final_response(run_id, "the answer")
        assert result.final_response == "the answer"
        assert result.state == State.FINAL
        session.flush.assert_awaited_once()


class TestRunRepositorySetRefusedResponse:
    @pytest.mark.asyncio
    async def test_sets_reason_and_refused_state(self):
        session = make_session()
        repo = RunRepository(session)
        run_id = uuid4()
        run = Run(id=run_id, state=State.MODEL_CALL)
        session.get.return_value = run

        result = await repo.set_refused_response(run_id, "cannot")
        assert result.final_response == "cannot"
        assert result.state == State.REFUSED
        session.flush.assert_awaited_once()


class TestRunRepositorySetRunFailed:
    @pytest.mark.asyncio
    async def test_sets_error_and_failed_state(self):
        session = make_session()
        repo = RunRepository(session)
        run_id = uuid4()
        run = Run(id=run_id, state=State.MODEL_CALL)
        session.get.return_value = run

        result = await repo.set_run_failed(run_id, "something broke")
        assert result.error == "something broke"
        assert result.state == State.FAILED
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_run_failed_from_start(self):
        session = make_session()
        repo = RunRepository(session)
        run_id = uuid4()
        run = Run(id=run_id, state=State.START)
        session.get.return_value = run

        result = await repo.set_run_failed(run_id, "init failed")
        assert result.state == State.FAILED
        assert result.error == "init failed"


# ─────────────────────────────────────────────
# EventRepository
# ─────────────────────────────────────────────


class TestEventRepositoryAppend:
    @pytest.mark.asyncio
    async def test_first_event_sequence_is_1(self):
        session = make_session()
        repo = EventRepository(session)
        run_id = uuid4()

        result_mock = MagicMock()
        result_mock.one.return_value = None  # no existing events
        session.exec.return_value = result_mock

        event = await repo.append(run_id, EventType.USER_INPUT, {"input": "hi"})
        assert event.sequence == 1
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_subsequent_event_increments_sequence(self):
        session = make_session()
        repo = EventRepository(session)
        run_id = uuid4()

        result_mock = MagicMock()
        result_mock.one.return_value = 5  # max sequence is 5
        session.exec.return_value = result_mock

        event = await repo.append(run_id, EventType.MODEL_INPUT, {"content": "x"})
        assert event.sequence == 6

    @pytest.mark.asyncio
    async def test_append_rejects_non_event_type(self):
        session = make_session()
        repo = EventRepository(session)

        with pytest.raises(ValueError, match="event_type must be an EventType"):
            await repo.append(uuid4(), "not_an_event_type", {})

    @pytest.mark.asyncio
    async def test_append_sets_correct_fields(self):
        session = make_session()
        repo = EventRepository(session)
        run_id = uuid4()

        result_mock = MagicMock()
        result_mock.one.return_value = 0
        session.exec.return_value = result_mock

        payload = {"input": "hello"}
        event = await repo.append(run_id, EventType.USER_INPUT, payload)
        assert event.run_id == run_id
        assert event.event_type == EventType.USER_INPUT
        assert event.payload == payload


class TestEventRepositoryGet:
    @pytest.mark.asyncio
    async def test_get_returns_ordered_events(self):
        session = make_session()
        repo = EventRepository(session)
        run_id = uuid4()

        events = [
            Event(sequence=1, event_type=EventType.USER_INPUT, payload={}),
            Event(sequence=2, event_type=EventType.MODEL_OUTPUT, payload={}),
        ]
        result_mock = MagicMock()
        result_mock.all.return_value = events
        session.exec.return_value = result_mock

        result = await repo.get(run_id)
        assert len(result) == 2
        assert result[0].sequence == 1

    @pytest.mark.asyncio
    async def test_get_empty_run(self):
        session = make_session()
        repo = EventRepository(session)

        result_mock = MagicMock()
        result_mock.all.return_value = []
        session.exec.return_value = result_mock

        result = await repo.get(uuid4())
        assert result == []


# ─────────────────────────────────────────────
# ToolExecutionRepository
# ─────────────────────────────────────────────


class TestToolExecutionRepositoryCreate:
    @pytest.mark.asyncio
    async def test_create_execution_adds_tool_call_event(self):
        session = make_session()
        repo = ToolExecutionRepository(session)
        run_id = uuid4()

        tool_exec = ToolExecution(id=uuid4(), run_id=run_id, tool_name="x:y", arguments={})
        session.refresh.side_effect = lambda r: setattr(r, "id", tool_exec.id)

        result_mock = MagicMock()
        result_mock.one.return_value = 0
        session.exec.return_value = result_mock

        result = await repo.create_execution(run_id, "x:y", {"a": 1})
        assert result.tool_name == "x:y"
        assert result.arguments == {"a": 1}
        session.add.assert_called()
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_execution_stores_arguments(self):
        session = make_session()
        repo = ToolExecutionRepository(session)
        run_id = uuid4()

        session.refresh.side_effect = lambda r: setattr(r, "id", uuid4())

        result_mock = MagicMock()
        result_mock.one.return_value = 0
        session.exec.return_value = result_mock

        args = {"path": "/etc/passwd", "encoding": "utf-8"}
        result = await repo.create_execution(run_id, "fs:read", args)
        assert result.arguments == args


class TestToolExecutionRepositoryComplete:
    @pytest.mark.asyncio
    async def test_complete_execution_success(self):
        session = make_session()
        repo = ToolExecutionRepository(session)
        tool_id = uuid4()
        run_id = uuid4()

        tool_exec = ToolExecution(id=tool_id, run_id=run_id, tool_name="x:y", arguments={})

        def get_side_effect(model, id):
            return tool_exec

        session.get.side_effect = get_side_effect

        result_mock = MagicMock()
        result_mock.one.return_value = 1
        session.exec.return_value = result_mock

        with patch("app.db.repository.RunRepository") as MockRunRepo:
            MockRunRepo.return_value.update_state = AsyncMock()

            result = await repo.complete_execution(
                tool_id, run_id, success=True, result={"data": 42}, error=None
            )
            assert result.success is True
            assert result.result == {"data": 42}
            assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_complete_execution_failure(self):
        session = make_session()
        repo = ToolExecutionRepository(session)
        tool_id = uuid4()
        run_id = uuid4()

        tool_exec = ToolExecution(id=tool_id, run_id=run_id, tool_name="x:y", arguments={})

        def get_side_effect(model, id):
            return tool_exec

        session.get.side_effect = get_side_effect

        result_mock = MagicMock()
        result_mock.one.return_value = 1
        session.exec.return_value = result_mock

        with patch("app.db.repository.RunRepository") as MockRunRepo:
            MockRunRepo.return_value.update_state = AsyncMock()

            result = await repo.complete_execution(
                tool_id, run_id, success=False, result=None, error="boom"
            )
            assert result.success is False
            assert result.error == "boom"

    @pytest.mark.asyncio
    async def test_complete_execution_nonexistent_raises(self):
        session = make_session()
        repo = ToolExecutionRepository(session)
        session.get.return_value = None

        with pytest.raises(ValueError, match="ToolExecution not found"):
            await repo.complete_execution(uuid4(), uuid4(), True, None, None)
