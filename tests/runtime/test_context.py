"""
Unit tests for app/runtime/context.py (§17-19).

Split into two groups:
  - RunContext itself: defaults, independent mutability across instances
    (guards the mutable-default-argument class of bug discussed earlier)
  - load_context / _apply_event: event replay reconstructs the right
    fields from a fake event history, without touching a real DB
    (RunRepository/EventRepository are mocked)
"""
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agent.models import FinalAnswer, ToolCall
from app.db.models import Event, EventType
from app.runtime.context import RunContext, ToolResult, _apply_event, load_context
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
        """Regression guard for the mutable-default-argument concern
        raised during review — Pydantic default_factory should give each
        instance its own list/set, not a shared one."""
        ctx1 = RunContext(run_id=uuid4(), state=State.START)
        ctx2 = RunContext(run_id=uuid4(), state=State.START)

        ctx1.messages.append("hello")
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
    def test_model_input_appends_message(self):
        ctx = RunContext(run_id=uuid4(), state=State.MODEL_CALL)
        _apply_event(ctx, EventType.MODEL_INPUT, {"content": "hi there"})
        assert ctx.messages == ["hi there"]

    def test_model_output_appends_message_and_sets_current_action(self):
        ctx = RunContext(run_id=uuid4(), state=State.MODEL_OUTPUT)
        payload = {"content": "", "action": "final", "content_field_unused": True}
        # FinalAnswer requires: action="final", content=str
        payload = {"content": "done", "action": "final"}
        _apply_event(ctx, EventType.MODEL_OUTPUT, payload)

        assert ctx.messages == ["done"]
        assert isinstance(ctx.current_action, FinalAnswer)
        assert ctx.current_action.content == "done"

    def test_skill_received_adds_to_loaded_skills(self):
        ctx = RunContext(run_id=uuid4(), state=State.SKILL_RECEIVED)
        _apply_event(ctx, EventType.SKILL_RECEIVED, {"skill": "math_helper"})
        assert ctx.loaded_skills == {"math_helper"}

    def test_tool_call_clears_pending_result(self):
        ctx = RunContext(run_id=uuid4(), state=State.TOOL_CALL)
        ctx.tool_result = ToolResult(success=True, result={"stale": True})
        _apply_event(ctx, EventType.TOOL_CALL, {"tool": "search", "arguments": {}})
        assert ctx.tool_result is None

    def test_tool_result_sets_success_and_payload(self):
        ctx = RunContext(run_id=uuid4(), state=State.TOOL_RESULT)
        _apply_event(ctx, EventType.TOOL_RESULT, {"result": {"answer": 42}})
        assert ctx.tool_result == ToolResult(success=True, result={"answer": 42})

    def test_tool_failed_sets_failure_and_error(self):
        ctx = RunContext(run_id=uuid4(), state=State.TOOL_FAILED)
        _apply_event(ctx, EventType.TOOL_FAILED, {"error": "timeout"})
        assert ctx.tool_result == ToolResult(success=False, error="timeout")

    def test_unhandled_event_type_is_a_silent_noop_currently(self):
        """Documents current (incomplete) behavior rather than asserting
        it's correct: ASK_USER / USER_INPUT / FINAL / REFUSED have no
        branch yet and are silently ignored. This test exists so that if
        someone adds a branch for one of these, they notice this test and
        update it deliberately, instead of the gap staying invisible.
        See conversation history: no exhaustiveness check yet."""
        ctx = RunContext(run_id=uuid4(), state=State.WAITING_FOR_USER)
        before = ctx.model_copy(deep=True)

        _apply_event(ctx, EventType.ASK_USER, {"question": "which one?"})

        assert ctx == before


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
        fake_run = FakeRun(id=run_id, state=State.TOOL_RESULT)

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
                payload={"action": "tool_call", "tool": "calc", "arguments": {"expr": "2+2"}},
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

        assert ctx.state == State.TOOL_RESULT
        assert ctx.messages == ["what's 2+2?"]
        assert isinstance(ctx.current_action, ToolCall)
        assert ctx.current_action.tool == "calc"
        assert ctx.tool_result == ToolResult(success=True, result={"value": 4})

    @pytest.mark.asyncio
    async def test_reload_after_failed_tool_reflects_failure_not_stale_success(self):
        """Guards against a subtle replay-ordering bug: if TOOL_CALL's
        'clear pending result' branch ran after TOOL_FAILED instead of
        before, a stale/incorrect tool_result could survive replay."""
        run_id = uuid4()
        fake_run = FakeRun(id=run_id, state=State.TOOL_FAILED)

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