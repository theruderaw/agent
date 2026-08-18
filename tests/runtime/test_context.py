"""
Unit tests for app/runtime/context.py

Split into two groups:
  - RunContext itself: defaults, independent mutability across instances
  - load_context / _apply_event: event replay reconstructs the right
    fields from a fake event history, without touching a real DB
    (RunRepository/EventRepository are mocked)
"""
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agent.models import FinalAnswer, ToolCall
from app.db.models import Event, EventType
from app.runtime.context import ContextMessage, RunContext, ToolResult, _apply_event, load_context
from app.state.state import State


# ---------------------------------------------------------------------------
# RunContext model itself
# ---------------------------------------------------------------------------


class TestRunContextDefaults:
    def test_minimal_construction(self):
        run_id = uuid4()
        ctx = RunContext(run_id=run_id, state=State.START)

        assert ctx.run_id == run_id
        assert ctx.state == State.START
        assert ctx.current_action is None
        assert ctx.messages == []
        assert ctx.loaded_skills == set()
        assert ctx.tool_result is None
        assert ctx.final_response is None

    def test_mutable_defaults_are_not_shared_across_instances(self):
        ctx1 = RunContext(run_id=uuid4(), state=State.START)
        ctx2 = RunContext(run_id=uuid4(), state=State.START)

        ctx1.messages.append(ContextMessage(role="user", content="hello"))
        ctx1.loaded_skills.add("some_skill")

        assert ctx2.messages == []
        assert ctx2.loaded_skills == set()

    def test_loaded_skills_deduplicates(self):
        ctx = RunContext(run_id=uuid4(), state=State.START)
        ctx.loaded_skills.add("math")
        ctx.loaded_skills.add("math")
        assert ctx.loaded_skills == {"math"}


class TestToolResult:
    def test_success_result_shape(self):
        tr = ToolResult(success=True, result={"answer": 1})
        assert tr.success is True
        assert tr.result == {"answer": 1}
        assert tr.error is None

    def test_failure_result_shape(self):
        tr = ToolResult(success=False, error="boom")
        assert tr.success is False
        assert tr.result is None
        assert tr.error == "boom"


# ---------------------------------------------------------------------------
# _apply_event — replay logic, one branch per EventType handled
# ---------------------------------------------------------------------------


class TestApplyEvent:
    def test_model_input_is_audit_only_does_not_add_to_messages(self):
        ctx = RunContext(run_id=uuid4(), state=State.MODEL_CALL)
        _apply_event(ctx, EventType.MODEL_INPUT, {"content": "hi there"})
        assert ctx.messages == []

    def test_model_output_appends_assistant_message_and_sets_current_action(self):
        ctx = RunContext(run_id=uuid4(), state=State.MODEL_CALL)
        payload = {"content": "done", "action": {"action": "final", "content": "done"}}
        _apply_event(ctx, EventType.MODEL_OUTPUT, payload)

        assert ctx.messages == [ContextMessage(role="assistant", content="done")]
        assert isinstance(ctx.current_action, FinalAnswer)
        assert ctx.current_action.content == "done"

    def test_model_output_with_action_none_sets_current_action_none(self):
        ctx = RunContext(run_id=uuid4(), state=State.MODEL_CALL)
        ctx.current_action = FinalAnswer(content="stale")
        _apply_event(ctx, EventType.MODEL_OUTPUT, {"content": "raw", "action": None, "error": "bad"})
        assert ctx.current_action is None

    def test_model_output_with_invalid_action_sets_current_action_none(self):
        ctx = RunContext(run_id=uuid4(), state=State.MODEL_CALL)
        ctx.current_action = FinalAnswer(content="stale")
        _apply_event(ctx, EventType.MODEL_OUTPUT, {"content": "raw", "action": {"action": "nonexistent"}})
        assert ctx.current_action is None

    def test_user_input_replay_restores_user_message(self):
        ctx = RunContext(run_id=uuid4(), state=State.WAITING_FOR_USER)
        _apply_event(ctx, EventType.USER_INPUT, {"input": "yes please"})
        assert ctx.messages == [ContextMessage(role="user", content="yes please")]

    def test_skill_received_adds_to_loaded_skills(self):
        ctx = RunContext(run_id=uuid4(), state=State.SKILL_REQUESTED)
        _apply_event(ctx, EventType.SKILL_RECEIVED, {"skill": "math_helper"})
        assert ctx.loaded_skills == {"math_helper"}

    def test_tool_call_clears_pending_result(self):
        ctx = RunContext(run_id=uuid4(), state=State.TOOL_CALL)
        ctx.tool_result = ToolResult(success=True, result={"stale": True})
        _apply_event(ctx, EventType.TOOL_CALL, {"tool": "search", "arguments": {}})
        assert ctx.tool_result is None

    def test_tool_result_sets_success_and_payload(self):
        ctx = RunContext(run_id=uuid4(), state=State.TOOL_CALL)
        _apply_event(ctx, EventType.TOOL_RESULT, {"result": {"answer": 42}})
        assert ctx.tool_result == ToolResult(success=True, result={"answer": 42})

    def test_tool_failed_sets_failure_and_error(self):
        ctx = RunContext(run_id=uuid4(), state=State.TOOL_CALL)
        _apply_event(ctx, EventType.TOOL_FAILED, {"error": "timeout"})
        assert ctx.tool_result == ToolResult(success=False, error="timeout")

    def test_tool_result_appends_to_messages(self):
        ctx = RunContext(run_id=uuid4(), state=State.TOOL_CALL)
        _apply_event(ctx, EventType.TOOL_RESULT, {"result": {"answer": 42}})
        assert len(ctx.messages) == 1
        assert ctx.messages[0].role == "tool"

    def test_tool_failed_appends_to_messages(self):
        ctx = RunContext(run_id=uuid4(), state=State.TOOL_CALL)
        _apply_event(ctx, EventType.TOOL_FAILED, {"error": "timeout"})
        assert len(ctx.messages) == 1
        assert ctx.messages[0].role == "tool"

    def test_model_output_tool_call_preserves_tool_and_arguments(self):
        ctx = RunContext(run_id=uuid4(), state=State.MODEL_CALL)
        payload = {
            "content": '{"action": "tool_call", "tool": "calc", "arguments": {"expr": "1+1"}}',
            "action": {"action": "tool_call", "tool": "calc", "arguments": {"expr": "1+1"}},
        }
        _apply_event(ctx, EventType.MODEL_OUTPUT, payload)
        assert isinstance(ctx.current_action, ToolCall)
        assert ctx.current_action.tool == "calc"
        assert ctx.current_action.arguments == {"expr": "1+1"}


# ---------------------------------------------------------------------------
# load_context — full replay through a mocked repository layer
# ---------------------------------------------------------------------------


class FakeRun:
    def __init__(self, id, state, final_response=None):
        self.id = id
        self.state = state
        self.final_response = final_response


class TestLoadContext:
    @pytest.mark.asyncio
    async def test_fresh_run_with_no_events_returns_default_context(self):
        run_id = uuid4()
        fake_run = FakeRun(id=run_id, state=State.START)

        with (
            patch("app.runtime.context.RunRepository") as MockRunRepo,
            patch("app.runtime.context.EventRepository") as MockEventRepo,
        ):
            MockRunRepo.return_value.get = AsyncMock(return_value=fake_run)
            MockEventRepo.return_value.get = AsyncMock(return_value=[])

            ctx = await load_context(run_id, session=AsyncMock())

        assert ctx.run_id == run_id
        assert ctx.state == State.START
        assert ctx.messages == []
        assert ctx.tool_result is None

    @pytest.mark.asyncio
    async def test_replays_full_event_history_in_order(self):
        run_id = uuid4()
        fake_run = FakeRun(id=run_id, state=State.TOOL_CALL)

        history = [
            Event(
                run_id=run_id,
                event_type=EventType.MODEL_INPUT,
                sequence=1,
                payload={"content": "what's 2+2?"},
            ),
            Event(
                run_id=run_id,
                event_type=EventType.MODEL_OUTPUT,
                sequence=2,
                payload={
                    "content": '{"action": "tool_call", "tool": "calc", "arguments": {"expr": "2+2"}}',
                    "action": {"action": "tool_call", "tool": "calc", "arguments": {"expr": "2+2"}},
                },
            ),
            Event(
                run_id=run_id,
                event_type=EventType.TOOL_CALL,
                sequence=3,
                payload={"tool": "calc", "arguments": {"expr": "2+2"}},
            ),
            Event(
                run_id=run_id,
                event_type=EventType.TOOL_RESULT,
                sequence=4,
                payload={"result": {"value": 4}},
            ),
        ]

        with (
            patch("app.runtime.context.RunRepository") as MockRunRepo,
            patch("app.runtime.context.EventRepository") as MockEventRepo,
        ):
            MockRunRepo.return_value.get = AsyncMock(return_value=fake_run)
            MockEventRepo.return_value.get = AsyncMock(return_value=history)

            ctx = await load_context(run_id, session=AsyncMock())

        assert ctx.state == State.TOOL_CALL
        # MODEL_INPUT is audit-only, not replayed as a message
        assert ctx.messages == [
            ContextMessage(
                role="assistant",
                content='{"action": "tool_call", "tool": "calc", "arguments": {"expr": "2+2"}}',
            ),
            ContextMessage(role="tool", content='{"result": {"value": 4}}'),
        ]
        assert isinstance(ctx.current_action, ToolCall)
        assert ctx.current_action.tool == "calc"
        assert ctx.tool_result == ToolResult(success=True, result={"value": 4})

    @pytest.mark.asyncio
    async def test_reload_after_failed_tool_reflects_failure_not_stale_success(self):
        run_id = uuid4()
        fake_run = FakeRun(id=run_id, state=State.TOOL_CALL)

        history = [
            Event(run_id=run_id, event_type=EventType.TOOL_CALL, sequence=1, payload={}),
            Event(
                run_id=run_id,
                event_type=EventType.TOOL_FAILED,
                sequence=2,
                payload={"error": "connection refused"},
            ),
        ]

        with (
            patch("app.runtime.context.RunRepository") as MockRunRepo,
            patch("app.runtime.context.EventRepository") as MockEventRepo,
        ):
            MockRunRepo.return_value.get = AsyncMock(return_value=fake_run)
            MockEventRepo.return_value.get = AsyncMock(return_value=history)

            ctx = await load_context(run_id, session=AsyncMock())

        assert ctx.tool_result == ToolResult(success=False, error="connection refused")

    @pytest.mark.asyncio
    async def test_model_output_parse_failure_does_not_crash_replay(self):
        run_id = uuid4()
        fake_run = FakeRun(id=run_id, state=State.WAITING_FOR_USER)

        history = [
            Event(
                run_id=run_id,
                event_type=EventType.MODEL_OUTPUT,
                sequence=1,
                payload={"content": "not json at all", "action": None, "error": "Invalid JSON"},
            ),
        ]

        with (
            patch("app.runtime.context.RunRepository") as MockRunRepo,
            patch("app.runtime.context.EventRepository") as MockEventRepo,
        ):
            MockRunRepo.return_value.get = AsyncMock(return_value=fake_run)
            MockEventRepo.return_value.get = AsyncMock(return_value=history)

            ctx = await load_context(run_id, session=AsyncMock())

        assert ctx.current_action is None
        assert ctx.messages == [ContextMessage(role="assistant", content="not json at all")]

    @pytest.mark.asyncio
    async def test_user_input_replay_restores_user_response(self):
        run_id = uuid4()
        fake_run = FakeRun(id=run_id, state=State.MODEL_CALL)

        history = [
            Event(
                run_id=run_id,
                event_type=EventType.USER_INPUT,
                sequence=1,
                payload={"input": "yes, proceed"},
            ),
        ]

        with (
            patch("app.runtime.context.RunRepository") as MockRunRepo,
            patch("app.runtime.context.EventRepository") as MockEventRepo,
        ):
            MockRunRepo.return_value.get = AsyncMock(return_value=fake_run)
            MockEventRepo.return_value.get = AsyncMock(return_value=history)

            ctx = await load_context(run_id, session=AsyncMock())

        assert ctx.messages == [ContextMessage(role="user", content="yes, proceed")]

    @pytest.mark.asyncio
    async def test_skill_received_reconstructs_loaded_skills(self):
        run_id = uuid4()
        fake_run = FakeRun(id=run_id, state=State.MODEL_CALL)

        history = [
            Event(
                run_id=run_id,
                event_type=EventType.SKILL_RECEIVED,
                sequence=1,
                payload={"skill": "git_helper"},
            ),
            Event(
                run_id=run_id,
                event_type=EventType.SKILL_RECEIVED,
                sequence=2,
                payload={"skill": "ruff_linter"},
            ),
        ]

        with (
            patch("app.runtime.context.RunRepository") as MockRunRepo,
            patch("app.runtime.context.EventRepository") as MockEventRepo,
        ):
            MockRunRepo.return_value.get = AsyncMock(return_value=fake_run)
            MockEventRepo.return_value.get = AsyncMock(return_value=history)

            ctx = await load_context(run_id, session=AsyncMock())

        assert ctx.loaded_skills == {"git_helper", "ruff_linter"}

    @pytest.mark.asyncio
    async def test_event_replay_preserves_message_ordering(self):
        run_id = uuid4()
        fake_run = FakeRun(id=run_id, state=State.MODEL_CALL)

        history = [
            Event(
                run_id=run_id,
                event_type=EventType.USER_INPUT,
                sequence=1,
                payload={"input": "question"},
            ),
            Event(
                run_id=run_id,
                event_type=EventType.MODEL_OUTPUT,
                sequence=2,
                payload={
                    "content": "assistant reply",
                    "action": {"action": "final", "content": "done"},
                },
            ),
        ]

        with (
            patch("app.runtime.context.RunRepository") as MockRunRepo,
            patch("app.runtime.context.EventRepository") as MockEventRepo,
        ):
            MockRunRepo.return_value.get = AsyncMock(return_value=fake_run)
            MockEventRepo.return_value.get = AsyncMock(return_value=history)

            ctx = await load_context(run_id, session=AsyncMock())

        assert ctx.messages[0].role == "user"
        assert ctx.messages[1].role == "assistant"
