"""
Recovery tests — reconstruct RunContext from persisted events after each
major checkpoint and verify the next model call would receive correct state.

These tests use the real load_context with mocked repositories (no DB).
"""
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agent.models import FinalAnswer, ToolCall
from app.db.models import Event, EventType
from app.runtime.context import ContextMessage, RunContext, ToolResult, load_context
from app.state.state import State


class FakeRun:
    def __init__(self, id, state, final_response=None):
        self.id = id
        self.state = state
        self.final_response = final_response


async def _load(run_id, state, events, final_response=None):
    fake_run = FakeRun(id=run_id, state=state, final_response=final_response)
    with (
        patch("app.runtime.context.RunRepository") as MockRunRepo,
        patch("app.runtime.context.EventRepository") as MockEventRepo,
    ):
        MockRunRepo.return_value.get = AsyncMock(return_value=fake_run)
        MockEventRepo.return_value.get = AsyncMock(return_value=events)
        return await load_context(run_id, session=AsyncMock())


class TestRecoveryWaitingForUser:
    @pytest.mark.asyncio
    async def test_recovery_after_ask_user(self):
        run_id = uuid4()
        events = [
            Event(run_id=run_id, event_type=EventType.MODEL_INPUT, sequence=1,
                  payload={"content": "prompt"}),
            Event(run_id=run_id, event_type=EventType.MODEL_OUTPUT, sequence=2,
                  payload={"content": "question", "action": {"action": "ask_user", "question": "which one?"}}),
            Event(run_id=run_id, event_type=EventType.ASK_USER, sequence=3,
                  payload={"question": "which one?"}),
        ]
        ctx = await _load(run_id, State.WAITING_FOR_USER, events)

        assert ctx.state == State.WAITING_FOR_USER
        assert isinstance(ctx.current_action, type(None)) is False
        # The assistant message should be in context
        assert any(m.role == "assistant" for m in ctx.messages)

    @pytest.mark.asyncio
    async def test_recovery_after_user_input(self):
        run_id = uuid4()
        events = [
            Event(run_id=run_id, event_type=EventType.MODEL_INPUT, sequence=1,
                  payload={"content": "prompt"}),
            Event(run_id=run_id, event_type=EventType.MODEL_OUTPUT, sequence=2,
                  payload={"content": "q", "action": {"action": "ask_user", "question": "yes?"}}),
            Event(run_id=run_id, event_type=EventType.ASK_USER, sequence=3,
                  payload={"question": "yes?"}),
            Event(run_id=run_id, event_type=EventType.USER_INPUT, sequence=4,
                  payload={"input": "yes"}),
        ]
        ctx = await _load(run_id, State.MODEL_CALL, events)

        assert ctx.state == State.MODEL_CALL
        # User input should be in messages
        user_msgs = [m for m in ctx.messages if m.role == "user"]
        assert any("yes" in m.content for m in user_msgs)


class TestRecoveryCompletedToolCall:
    @pytest.mark.asyncio
    async def test_recovery_after_tool_result(self):
        run_id = uuid4()
        events = [
            Event(run_id=run_id, event_type=EventType.MODEL_INPUT, sequence=1,
                  payload={"content": "prompt"}),
            Event(run_id=run_id, event_type=EventType.MODEL_OUTPUT, sequence=2,
                  payload={
                      "content": '{"action": "tool_call", "tool": "calc", "arguments": {"expr": "1+1"}}',
                      "action": {"action": "tool_call", "tool": "calc", "arguments": {"expr": "1+1"}},
                  }),
            Event(run_id=run_id, event_type=EventType.TOOL_CALL, sequence=3,
                  payload={"tool": "calc", "arguments": {"expr": "1+1"}}),
            Event(run_id=run_id, event_type=EventType.TOOL_RESULT, sequence=4,
                  payload={"result": {"value": 2}}),
        ]
        ctx = await _load(run_id, State.MODEL_CALL, events)

        assert ctx.state == State.MODEL_CALL
        assert ctx.tool_result == ToolResult(success=True, result={"value": 2})
        # Tool result should be in messages
        tool_msgs = [m for m in ctx.messages if m.role == "tool"]
        assert len(tool_msgs) == 1
        assert isinstance(ctx.current_action, ToolCall)
        assert ctx.current_action.tool == "calc"


class TestRecoveryCompletedSkillLoad:
    @pytest.mark.asyncio
    async def test_recovery_after_skill_received(self):
        run_id = uuid4()
        events = [
            Event(run_id=run_id, event_type=EventType.MODEL_INPUT, sequence=1,
                  payload={"content": "prompt"}),
            Event(run_id=run_id, event_type=EventType.MODEL_OUTPUT, sequence=2,
                  payload={
                      "content": '{"action": "skill_request", "skill": "git_helper"}',
                      "action": {"action": "skill_request", "skill": "git_helper"},
                  }),
            Event(run_id=run_id, event_type=EventType.SKILL_RECEIVED, sequence=3,
                  payload={"skill": "git_helper"}),
        ]
        ctx = await _load(run_id, State.MODEL_CALL, events)

        assert ctx.state == State.MODEL_CALL
        assert "git_helper" in ctx.loaded_skills


class TestRecoveryTerminalFinal:
    @pytest.mark.asyncio
    async def test_recovery_after_final(self):
        run_id = uuid4()
        events = [
            Event(run_id=run_id, event_type=EventType.MODEL_INPUT, sequence=1,
                  payload={"content": "prompt"}),
            Event(run_id=run_id, event_type=EventType.MODEL_OUTPUT, sequence=2,
                  payload={
                      "content": '{"action": "final", "content": "the answer"}',
                      "action": {"action": "final", "content": "the answer"},
                  }),
            Event(run_id=run_id, event_type=EventType.FINAL, sequence=3,
                  payload={"content": "the answer"}),
        ]
        ctx = await _load(run_id, State.FINAL, events, final_response="the answer")

        assert ctx.state == State.FINAL
        assert ctx.final_response == "the answer"
        assert isinstance(ctx.current_action, FinalAnswer)
        assert ctx.current_action.content == "the answer"


class TestRecoveryTerminalRefusal:
    @pytest.mark.asyncio
    async def test_recovery_after_refusal(self):
        run_id = uuid4()
        events = [
            Event(run_id=run_id, event_type=EventType.MODEL_INPUT, sequence=1,
                  payload={"content": "prompt"}),
            Event(run_id=run_id, event_type=EventType.MODEL_OUTPUT, sequence=2,
                  payload={
                      "content": '{"action": "refuse", "reason": "cannot"}',
                      "action": {"action": "refuse", "reason": "cannot"},
                  }),
            Event(run_id=run_id, event_type=EventType.REFUSED, sequence=3,
                  payload={"reason": "cannot"}),
        ]
        ctx = await _load(run_id, State.REFUSED, events)

        assert ctx.state == State.REFUSED


class TestRecoveryParseError:
    @pytest.mark.asyncio
    async def test_recovery_after_parse_error(self):
        run_id = uuid4()
        events = [
            Event(run_id=run_id, event_type=EventType.MODEL_INPUT, sequence=1,
                  payload={"content": "prompt"}),
            Event(run_id=run_id, event_type=EventType.MODEL_OUTPUT, sequence=2,
                  payload={"content": "not json", "action": None, "error": "Invalid JSON"}),
        ]
        ctx = await _load(run_id, State.WAITING_FOR_USER, events)

        assert ctx.state == State.WAITING_FOR_USER
        assert ctx.current_action is None
        # The raw model output should be in messages as assistant
        assistant_msgs = [m for m in ctx.messages if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0].content == "not json"
