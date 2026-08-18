"""Additional tests for app/runtime/runtime.py — edge cases not in test_runtime.py."""

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agent.models import AskUser, FinalAnswer, Refuse, SkillRequest, ToolCall
from app.db.models import EventType
from app.runtime.context import ContextMessage, RunContext
from app.state.state import State


# ─────────────────────────────────────────────
# Helpers (same as test_runtime.py)
# ─────────────────────────────────────────────


@dataclass
class FakeRun:
    id: uuid4
    state: State = State.START
    final_response: str | None = None
    error: str | None = None


@dataclass
class FakeToolResult:
    ok: bool = True
    data: dict = field(default_factory=lambda: {"answer": 42})
    error: str | None = None


class FakeLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self._call_count = 0

    async def generate(self, messages):
        idx = self._call_count
        self._call_count += 1
        return SimpleNamespace(content=self._responses[idx])


class FakeRegistry:
    def schemas(self):
        return [{"name": "calc:add", "description": "add", "input_schema": {}}]

    def dispatch(self, tool, arguments):
        return FakeToolResult(ok=True, data={"result": 42})


class FailingRegistry(FakeRegistry):
    def dispatch(self, tool, arguments):
        return FakeToolResult(ok=False, error="tool crashed")


class FakeSkillLoader:
    def load(self, name):
        @dataclass
        class Skill:
            content: str
        return Skill(content=f"skill content for {name}")

    def list_available(self):
        return []


class FailingSkillLoader:
    def load(self, name):
        raise FileNotFoundError(f"Skill {name} not found on disk")

    def list_available(self):
        return []


def make_session():
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.get = AsyncMock()
    session.exec = AsyncMock()
    return session


def make_ctx(run_id, state=State.MODEL_CALL):
    return RunContext(run_id=run_id, state=state)


def llm_response(action_dict):
    return json.dumps(action_dict)


# ─────────────────────────────────────────────
# Skill-not-found path
# ─────────────────────────────────────────────


class TestSkillNotFound:
    @pytest.mark.asyncio
    async def test_skill_not_found_returns_to_model_call(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)
        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        skill_action = {"action": "skill_request", "skill": "nonexistent"}
        final_action = {"action": "final", "content": "done"}

        llm = FakeLLM([
            llm_response(skill_action),
            llm_response(final_action),
        ])

        with (
            patch("app.runtime.runtime.RunRepository") as MockRunRepo,
            patch("app.runtime.runtime.EventRepository") as MockEventRepo,
            patch("app.runtime.runtime.ToolExecutionRepository"),
            patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
        ):
            mock_load.return_value = ctx
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockRunRepo.return_value.set_final_response = AsyncMock(return_value=run)
            MockRunRepo.return_value.update_state = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()

            await execute_run(
                run_id, session, llm, FakeRegistry(), FailingSkillLoader()
            )

        assert "nonexistent" not in ctx.loaded_skills
        assert ctx.state == State.FINAL


# ─────────────────────────────────────────────
# Tool failure path
# ─────────────────────────────────────────────


class TestToolFailure:
    @pytest.mark.asyncio
    async def test_tool_failure_continues_loop(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)
        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        tool_action = {"action": "tool_call", "tool": "calc:add", "arguments": {"a": 1}}
        final_action = {"action": "final", "content": "done"}

        llm = FakeLLM([
            llm_response(tool_action),
            llm_response(final_action),
        ])

        fake_execution = MagicMock()
        fake_execution.id = uuid4()

        with (
            patch("app.runtime.runtime.RunRepository") as MockRunRepo,
            patch("app.runtime.runtime.EventRepository") as MockEventRepo,
            patch("app.runtime.runtime.ToolExecutionRepository") as MockToolExec,
            patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
        ):
            mock_load.return_value = ctx
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockRunRepo.return_value.set_final_response = AsyncMock(return_value=run)
            MockRunRepo.return_value.update_state = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()
            MockToolExec.return_value.create_execution = AsyncMock(return_value=fake_execution)
            MockToolExec.return_value.complete_execution = AsyncMock(return_value=fake_execution)

            await execute_run(
                run_id, session, llm, FailingRegistry(), FakeSkillLoader()
            )

        tool_msgs = [m for m in ctx.messages if m.role == "tool"]
        assert len(tool_msgs) == 1
        assert ctx.state == State.FINAL


# ─────────────────────────────────────────────
# AskUser returns immediately
# ─────────────────────────────────────────────


class TestAskUserReturnsImmediately:
    @pytest.mark.asyncio
    async def test_ask_user_breaks_loop(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)
        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        ask_action = {"action": "ask_user", "question": "which?"}
        llm = FakeLLM([llm_response(ask_action)])

        with (
            patch("app.runtime.runtime.RunRepository") as MockRunRepo,
            patch("app.runtime.runtime.EventRepository") as MockEventRepo,
            patch("app.runtime.runtime.ToolExecutionRepository"),
            patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
        ):
            mock_load.return_value = ctx
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockRunRepo.return_value.update_state = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()

            await execute_run(run_id, session, llm, FakeRegistry(), FakeSkillLoader())

        assert ctx.state == State.WAITING_FOR_USER


# ─────────────────────────────────────────────
# STOP state breaks loop
# ─────────────────────────────────────────────


class TestStopBreaksLoop:
    @pytest.mark.asyncio
    async def test_stop_state_exits_loop(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.STOP)
        ctx = make_ctx(run_id, State.STOP)
        session = make_session()
        session.commit = AsyncMock()

        llm = FakeLLM([])

        with (
            patch("app.runtime.runtime.RunRepository") as MockRunRepo,
            patch("app.runtime.runtime.EventRepository"),
            patch("app.runtime.runtime.ToolExecutionRepository"),
            patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
        ):
            mock_load.return_value = ctx
            MockRunRepo.return_value.get = AsyncMock(return_value=run)

            await execute_run(run_id, session, llm, FakeRegistry(), FakeSkillLoader())

        # LLM should never have been called
        assert llm._call_count == 0


# ─────────────────────────────────────────────
# No user_input on WAITING_FOR_USER
# ─────────────────────────────────────────────


class TestWaitingForUserWithoutInput:
    @pytest.mark.asyncio
    async def test_waiting_for_user_no_input_fails_as_unexpected_state(self):
        """When the runtime receives WAITING_FOR_USER with no user_input,
        it enters the main loop, sees the state is not MODEL_CALL,
        and calls set_run_failed — this is correct behavior."""
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.WAITING_FOR_USER)
        ctx = make_ctx(run_id, State.WAITING_FOR_USER)
        session = make_session()
        session.commit = AsyncMock()

        llm = FakeLLM([])

        with (
            patch("app.runtime.runtime.RunRepository") as MockRunRepo,
            patch("app.runtime.runtime.EventRepository"),
            patch("app.runtime.runtime.ToolExecutionRepository"),
            patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
        ):
            mock_load.return_value = ctx
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockRunRepo.return_value.set_run_failed = AsyncMock(return_value=run)

            await execute_run(run_id, session, llm, FakeRegistry(), FakeSkillLoader())

        MockRunRepo.return_value.set_run_failed.assert_awaited_once()
        assert llm._call_count == 0
