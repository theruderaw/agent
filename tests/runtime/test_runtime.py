"""
Unit tests for app/runtime/runtime.py — the main execute_run loop.

All database interaction is mocked. These tests verify:
  - state transitions are persisted and committed at correct checkpoints
  - tool/skill/final/refuse/parse-failure paths work end-to-end
  - unexpected states produce FAILED
  - max iteration exhaustion produces FAILED
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agent.models import AskUser, FinalAnswer, Refuse, SkillRequest, ToolCall
from app.db.models import EventType
from app.runtime.context import ContextMessage, RunContext, load_context
from app.state.state import State, next_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        return [{"name": "calc:add", "description": "add two numbers", "input_schema": {}}]

    async def dispatch(self, tool, arguments):
        return FakeToolResult(ok=True, data={"result": 42})


class FakeSkillLoader:
    def load(self, name):
        @dataclass
        class Skill:
            content: str
        return Skill(content=f"skill content for {name}")

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


def make_update_state_mock(run):
    async def _update(run_id, action=None):
        run.state = next_state(run.state, action=action)
        return run
    return AsyncMock(side_effect=_update)


def llm_response(action_dict):
    return json.dumps(action_dict)


def _mock_repos(run, events_list=None):
    """Return patched RunRepository, EventRepository, ToolExecutionRepository
    plus a MagicMock session, all wired together."""
    session = make_session()
    committed_states = []
    original_commit = session.commit

    async def track_commit():
        committed_states.append(run.state)
        await original_commit()

    session.commit.side_effect = track_commit
    session.get.return_value = run

    return session, committed_states


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


class TestFreshRunTransitionsToWaitingForUser:
    @pytest.mark.asyncio
    async def test_start_transitions_to_waiting_for_user_and_returns(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.START)

        ctx = make_ctx(run_id, State.START)
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

        assert ctx.state == State.WAITING_FOR_USER
        assert run.state == State.WAITING_FOR_USER


class TestToolRoundTrip:
    @pytest.mark.asyncio
    async def test_model_call_to_tool_call_to_model_call(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)

        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        tool_call_action = {"action": "tool_call", "tool": "calc.add", "arguments": {"a": 1, "b": 2}}
        final_action = {"action": "final", "content": "42"}

        llm = FakeLLM([
            llm_response(tool_call_action),
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

            await execute_run(run_id, session, llm, FakeRegistry(), FakeSkillLoader())

        tool_msgs = [m for m in ctx.messages if m.role == "tool"]
        assert len(tool_msgs) == 1
        assert ctx.state == State.FINAL


class TestSkillRoundTrip:
    @pytest.mark.asyncio
    async def test_model_call_to_skill_requested_to_model_call(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)

        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        skill_action = {"action": "skill_request", "skill": "git_helper"}
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
            MockRunRepo.return_value.update_state = make_update_state_mock(run)
            MockEventRepo.return_value.append = AsyncMock()

            await execute_run(run_id, session, llm, FakeRegistry(), FakeSkillLoader())

        assert "git_helper" in ctx.loaded_skills
        assert ctx.state == State.FINAL


class TestWaitingForUserResume:
    @pytest.mark.asyncio
    async def test_resume_from_user_input(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.WAITING_FOR_USER)

        ctx = make_ctx(run_id, State.WAITING_FOR_USER)
        session = make_session()
        session.commit = AsyncMock()

        final_action = {"action": "final", "content": "thanks"}
        llm = FakeLLM([llm_response(final_action)])

        with (
            patch("app.runtime.runtime.RunRepository") as MockRunRepo,
            patch("app.runtime.runtime.EventRepository") as MockEventRepo,
            patch("app.runtime.runtime.ToolExecutionRepository"),
            patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
        ):
            mock_load.return_value = ctx
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockRunRepo.return_value.set_final_response = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()

            await execute_run(
                run_id, session, llm, FakeRegistry(), FakeSkillLoader(),
                user_input="yes please",
            )

        user_msgs = [m for m in ctx.messages if m.role == "user"]
        assert any("yes please" in m.content for m in user_msgs)
        assert ctx.state == State.FINAL


class TestFinalAnswerPersistsFinal:
    @pytest.mark.asyncio
    async def test_final_answer_persists_final_state_and_response(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)

        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        final_action = {"action": "final", "content": "the answer is 42"}
        llm = FakeLLM([llm_response(final_action)])

        with (
            patch("app.runtime.runtime.RunRepository") as MockRunRepo,
            patch("app.runtime.runtime.EventRepository") as MockEventRepo,
            patch("app.runtime.runtime.ToolExecutionRepository"),
            patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
        ):
            mock_load.return_value = ctx
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockRunRepo.return_value.set_final_response = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()

            await execute_run(run_id, session, llm, FakeRegistry(), FakeSkillLoader())

        MockRunRepo.return_value.set_final_response.assert_awaited_once_with(
            run_id, "the answer is 42", action=FinalAnswer(content="the answer is 42"),
        )
        assert ctx.state == State.FINAL


class TestRefusalPersistsRefused:
    @pytest.mark.asyncio
    async def test_refusal_persists_refused_state(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)

        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        refuse_action = {"action": "refuse", "reason": "cannot do that"}
        llm = FakeLLM([llm_response(refuse_action)])

        with (
            patch("app.runtime.runtime.RunRepository") as MockRunRepo,
            patch("app.runtime.runtime.EventRepository") as MockEventRepo,
            patch("app.runtime.runtime.ToolExecutionRepository"),
            patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
        ):
            mock_load.return_value = ctx
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockRunRepo.return_value.set_refused_response = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()

            await execute_run(run_id, session, llm, FakeRegistry(), FakeSkillLoader())

        MockRunRepo.return_value.set_refused_response.assert_awaited_once_with(
            run_id, "cannot do that", action=Refuse(reason="cannot do that"),
        )
        assert ctx.state == State.REFUSED


class TestParseFailure:
    @pytest.mark.asyncio
    async def test_parse_failure_follows_recovery_path(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)

        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        invalid = "not valid json at all"
        valid = json.dumps({"action": "final", "content": "ok"})
        llm = FakeLLM([invalid, invalid, invalid, valid])

        with (
            patch("app.runtime.runtime.RunRepository") as MockRunRepo,
            patch("app.runtime.runtime.EventRepository") as MockEventRepo,
            patch("app.runtime.runtime.ToolExecutionRepository"),
            patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
            patch("app.runtime.runtime.settings") as mock_settings,
        ):
            mock_settings.max_iterations = 50
            mock_settings.max_parse_retries = 3
            mock_load.return_value = ctx
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockRunRepo.return_value.update_state = AsyncMock(return_value=run)
            MockRunRepo.return_value.set_final_response = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()

            await execute_run(run_id, session, llm, FakeRegistry(), FakeSkillLoader())

        model_output_errors = [
            c for c in MockEventRepo.return_value.append.call_args_list
            if c.kwargs.get("event_type") == EventType.MODEL_OUTPUT
            and c.kwargs["payload"].get("action") is None
        ]
        assert len(model_output_errors) == 3
        assert ctx.state == State.FINAL

    @pytest.mark.asyncio
    async def test_parse_failure_exhausts_retries_to_waiting(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)

        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        llm = FakeLLM(["bad1", "bad2", "bad3", "bad4"])

        with (
            patch("app.runtime.runtime.RunRepository") as MockRunRepo,
            patch("app.runtime.runtime.EventRepository") as MockEventRepo,
            patch("app.runtime.runtime.ToolExecutionRepository"),
            patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
            patch("app.runtime.runtime.settings") as mock_settings,
        ):
            mock_settings.max_iterations = 50
            mock_settings.max_parse_retries = 3
            mock_load.return_value = ctx
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockRunRepo.return_value.update_state = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()

            await execute_run(run_id, session, llm, FakeRegistry(), FakeSkillLoader())

        model_output_calls = [
            c for c in MockEventRepo.return_value.append.call_args_list
            if c.kwargs.get("event_type") == EventType.MODEL_OUTPUT
        ]
        assert len(model_output_calls) == 4
        assert ctx.state == State.WAITING_FOR_USER


class TestUnexpectedStateProducesFailed:
    @pytest.mark.asyncio
    async def test_unexpected_state_sets_failed(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.SKILL_REQUESTED)

        ctx = make_ctx(run_id, State.SKILL_REQUESTED)
        session = make_session()
        session.commit = AsyncMock()

        llm = FakeLLM([])

        with (
            patch("app.runtime.runtime.RunRepository") as MockRunRepo,
            patch("app.runtime.runtime.EventRepository") as MockEventRepo,
            patch("app.runtime.runtime.ToolExecutionRepository"),
            patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
        ):
            mock_load.return_value = ctx
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockRunRepo.return_value.set_run_failed = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()

            await execute_run(run_id, session, llm, FakeRegistry(), FakeSkillLoader())

        MockRunRepo.return_value.set_run_failed.assert_awaited_once()
        session.commit.assert_awaited()


class TestMaxIterationExhaustion:
    @pytest.mark.asyncio
    async def test_max_iterations_exceeded_sets_failed(self):
        from app.runtime.runtime import execute_run
        from app.core import settings

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)

        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        tool_action = {"action": "tool_call", "tool": "calc.add", "arguments": {"a": 1}}

        original_max = settings.max_iterations
        settings.max_iterations = 1

        llm = FakeLLM([llm_response(tool_action)])

        fake_execution = MagicMock()
        fake_execution.id = uuid4()

        try:
            with (
                patch("app.runtime.runtime.RunRepository") as MockRunRepo,
                patch("app.runtime.runtime.EventRepository") as MockEventRepo,
                patch("app.runtime.runtime.ToolExecutionRepository") as MockToolExec,
                patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
            ):
                mock_load.return_value = ctx
                MockRunRepo.return_value.get = AsyncMock(return_value=run)
                MockRunRepo.return_value.set_run_failed = AsyncMock(return_value=run)
                MockRunRepo.return_value.update_state = AsyncMock(return_value=run)
                MockEventRepo.return_value.append = AsyncMock()
                MockToolExec.return_value.create_execution = AsyncMock(return_value=fake_execution)
                MockToolExec.return_value.complete_execution = AsyncMock(return_value=fake_execution)

                await execute_run(run_id, session, llm, FakeRegistry(), FakeSkillLoader())
        finally:
            settings.max_iterations = original_max

        MockRunRepo.return_value.set_run_failed.assert_awaited()


class TestCheckpointsCommitSession:
    @pytest.mark.asyncio
    async def test_multiple_commits_throughout_run(self):
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)

        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        commit_count = 0

        async def count_commit():
            nonlocal commit_count
            commit_count += 1

        session.commit.side_effect = count_commit

        final_action = {"action": "final", "content": "done"}
        llm = FakeLLM([llm_response(final_action)])

        with (
            patch("app.runtime.runtime.RunRepository") as MockRunRepo,
            patch("app.runtime.runtime.EventRepository") as MockEventRepo,
            patch("app.runtime.runtime.ToolExecutionRepository"),
            patch("app.runtime.runtime.load_context", new_callable=AsyncMock) as mock_load,
        ):
            mock_load.return_value = ctx
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockRunRepo.return_value.set_final_response = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()

            await execute_run(run_id, session, llm, FakeRegistry(), FakeSkillLoader())

        assert commit_count >= 1
