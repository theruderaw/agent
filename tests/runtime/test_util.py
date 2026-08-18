"""Tests for app/runtime/util.py — prompt building, call_llm, build_messages."""

import json
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.agent.models import FinalAnswer, ToolCall
from app.db.models import EventType
from app.llm.models import Message
from app.runtime.context import ContextMessage, RunContext
from app.runtime.util import (
    ModelParseError,
    SYSTEM_PROMPT,
    build_messages,
    build_skills_section,
    build_tools_section,
    call_llm,
)
from app.state.state import State


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@dataclass
class FakeToolResult:
    ok: bool = True
    data: dict = None
    error: str | None = None


class FakeTool:
    def __init__(self, name="fs:read", desc="read a file"):
        self.name = name
        self.desc = desc

    def schema(self):
        return {
            "name": self.name,
            "description": self.desc,
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
        }


class FakeRegistry:
    def __init__(self, tools=None):
        self._tools = tools if tools is not None else [FakeTool()]

    def schemas(self):
        return [t.schema() for t in self._tools]

    def dispatch(self, name, args):
        return FakeToolResult(data={"content": "hello"})


class FakeSkill:
    def __init__(self, name, content):
        self.name = name
        self.path = None
        self.content = content


class FakeSkillLoader:
    def __init__(self, available=None, skills=None):
        self._available = available or []
        self._skills = skills or {}

    def list_available(self):
        return self._available

    def load(self, name):
        if name in self._skills:
            return FakeSkill(name=name, content=self._skills[name])
        raise FileNotFoundError(f"Skill {name} not found")


# ─────────────────────────────────────────────
# ModelParseError
# ─────────────────────────────────────────────


class TestModelParseError:
    def test_stores_content_and_reason(self):
        err = ModelParseError("raw text", "bad json")
        assert err.content == "raw text"
        assert err.reason == "bad json"
        assert str(err) == "bad json"

    def test_is_exception(self):
        assert issubclass(ModelParseError, Exception)


# ─────────────────────────────────────────────
# SYSTEM_PROMPT
# ─────────────────────────────────────────────


class TestSystemPrompt:
    def test_contains_action_schemas(self):
        assert "tool_call" in SYSTEM_PROMPT
        assert "skill_request" in SYSTEM_PROMPT
        assert "ask_user" in SYSTEM_PROMPT
        assert "final" in SYSTEM_PROMPT
        assert "refuse" in SYSTEM_PROMPT

    def test_contains_decision_flow(self):
        assert "Decision flow" in SYSTEM_PROMPT

    def test_contains_tool_call_rules(self):
        assert "NEVER put a tool name in the 'action' field" in SYSTEM_PROMPT


# ─────────────────────────────────────────────
# build_skills_section
# ─────────────────────────────────────────────


class TestBuildSkillsSection:
    def test_no_skills_available(self):
        loader = FakeSkillLoader(available=[])
        result = build_skills_section(loader, set())
        assert "No skills available on disk" in result

    def test_all_pending(self):
        loader = FakeSkillLoader(available=["git", "docker"])
        result = build_skills_section(loader, set())
        assert "Available skills" in result
        assert "git" in result
        assert "docker" in result
        assert "Loaded skills" not in result

    def test_some_loaded(self):
        loader = FakeSkillLoader(available=["git", "docker"])
        result = build_skills_section(loader, {"git"})
        assert "Loaded skills" in result
        assert "git" in result
        assert "docker" in result
        assert "Available skills" in result

    def test_all_loaded(self):
        loader = FakeSkillLoader(available=["git"])
        result = build_skills_section(loader, {"git"})
        assert "Loaded skills" in result
        assert "git" in result
        assert "Available skills" not in result

    def test_loaded_not_in_available_ignored(self):
        loader = FakeSkillLoader(available=["git"])
        result = build_skills_section(loader, {"git", "nonexistent"})
        assert "nonexistent" not in result


# ─────────────────────────────────────────────
# build_tools_section
# ─────────────────────────────────────────────


class TestBuildToolsSection:
    def test_includes_header(self):
        registry = FakeRegistry()
        result = build_tools_section(registry)
        assert result.startswith("Available tools:")

    def test_includes_tool_schema(self):
        registry = FakeRegistry()
        result = build_tools_section(registry)
        assert "fs:read" in result
        assert "read a file" in result

    def test_multiple_tools(self):
        tools = [FakeTool("a:b", "tool b"), FakeTool("c:d", "tool d")]
        registry = FakeRegistry(tools=tools)
        result = build_tools_section(registry)
        assert "a:b" in result
        assert "c:d" in result

    def test_empty_registry(self):
        registry = FakeRegistry(tools=[])
        result = build_tools_section(registry)
        assert result == "Available tools:"


# ─────────────────────────────────────────────
# build_messages
# ─────────────────────────────────────────────


class TestBuildMessages:
    def test_system_message_first(self):
        ctx = RunContext(run_id=uuid4(), state=State.MODEL_CALL)
        registry = FakeRegistry()
        loader = FakeSkillLoader()
        messages = build_messages(ctx, registry, loader)
        assert messages[0].role == "system"
        assert SYSTEM_PROMPT in messages[0].content

    def test_includes_tools_section(self):
        ctx = RunContext(run_id=uuid4(), state=State.MODEL_CALL)
        registry = FakeRegistry()
        loader = FakeSkillLoader()
        messages = build_messages(ctx, registry, loader)
        assert "Available tools:" in messages[0].content
        assert "fs:read" in messages[0].content

    def test_includes_skills_section(self):
        ctx = RunContext(run_id=uuid4(), state=State.MODEL_CALL)
        registry = FakeRegistry()
        loader = FakeSkillLoader(available=["git"])
        messages = build_messages(ctx, registry, loader)
        assert "git" in messages[0].content

    def test_includes_loaded_skill_content(self):
        ctx = RunContext(run_id=uuid4(), state=State.MODEL_CALL, loaded_skills={"git"})
        registry = FakeRegistry()
        loader = FakeSkillLoader(available=["git"], skills={"git": "# Git Skill\nUse git."})
        messages = build_messages(ctx, registry, loader)
        assert "[Skill: git]" in messages[0].content
        assert "Use git." in messages[0].content

    def test_user_messages_after_system(self):
        ctx = RunContext(
            run_id=uuid4(),
            state=State.MODEL_CALL,
            messages=[ContextMessage(role="user", content="hello")],
        )
        registry = FakeRegistry()
        loader = FakeSkillLoader()
        messages = build_messages(ctx, registry, loader)
        assert len(messages) == 2
        assert messages[1].role == "user"
        assert messages[1].content == "hello"

    def test_multiple_context_messages_preserved(self):
        ctx = RunContext(
            run_id=uuid4(),
            state=State.MODEL_CALL,
            messages=[
                ContextMessage(role="user", content="q1"),
                ContextMessage(role="assistant", content="a1"),
                ContextMessage(role="tool", content="t1"),
                ContextMessage(role="user", content="q2"),
            ],
        )
        registry = FakeRegistry()
        loader = FakeSkillLoader()
        messages = build_messages(ctx, registry, loader)
        assert len(messages) == 5
        assert messages[1].content == "q1"
        assert messages[2].content == "a1"
        assert messages[3].content == "t1"
        assert messages[4].content == "q2"

    def test_skill_load_failure_does_not_crash(self):
        ctx = RunContext(run_id=uuid4(), state=State.MODEL_CALL, loaded_skills={"nonexistent"})
        registry = FakeRegistry()
        loader = FakeSkillLoader(available=[], skills={})
        messages = build_messages(ctx, registry, loader)
        assert len(messages) == 1  # only system message


# ─────────────────────────────────────────────
# call_llm
# ─────────────────────────────────────────────


class TestCallLLM:
    @pytest.mark.asyncio
    async def test_success_returns_response_and_action(self):
        run_id = uuid4()
        events = MagicMock()
        events.append = AsyncMock()

        raw = json.dumps({"action": "final", "content": "done"}, separators=(",", ":"))

        class FakeLLM:
            async def generate(self, msgs):
                return SimpleNamespace(content=raw)

        messages = [Message(role="user", content="hello")]
        response, action = await call_llm(FakeLLM(), messages, events, run_id)

        assert response.content == raw
        assert isinstance(action, FinalAnswer)
        assert action.content == "done"

    @pytest.mark.asyncio
    async def test_emits_model_input_and_model_output_events(self):
        run_id = uuid4()
        events = MagicMock()
        events.append = AsyncMock()

        class FakeLLM:
            async def generate(self, msgs):
                return SimpleNamespace(
                    content=json.dumps({"action": "final", "content": "ok"})
                )

        await call_llm(FakeLLM(), [Message(role="user", content="hi")], events, run_id)

        calls = events.append.call_args_list
        assert len(calls) == 2
        assert calls[0].kwargs["event_type"] == EventType.MODEL_INPUT
        assert calls[1].kwargs["event_type"] == EventType.MODEL_OUTPUT
        assert calls[1].kwargs["payload"]["action"] == {"action": "final", "content": "ok"}

    @pytest.mark.asyncio
    async def test_invalid_json_raises_model_parse_error(self):
        run_id = uuid4()
        events = MagicMock()
        events.append = AsyncMock()

        class FakeLLM:
            async def generate(self, msgs):
                return SimpleNamespace(content="not json")

        with pytest.raises(ModelParseError, match="Invalid JSON"):
            await call_llm(FakeLLM(), [Message(role="user", content="x")], events, run_id)

    @pytest.mark.asyncio
    async def test_invalid_action_schema_raises_model_parse_error(self):
        run_id = uuid4()
        events = MagicMock()
        events.append = AsyncMock()

        class FakeLLM:
            async def generate(self, msgs):
                return SimpleNamespace(content=json.dumps({"action": "bogus"}))

        with pytest.raises(ModelParseError, match="Invalid action schema"):
            await call_llm(FakeLLM(), [Message(role="user", content="x")], events, run_id)

    @pytest.mark.asyncio
    async def test_model_parse_error_preserves_raw_content(self):
        run_id = uuid4()
        events = MagicMock()
        events.append = AsyncMock()

        class FakeLLM:
            async def generate(self, msgs):
                return SimpleNamespace(content="garbage output here")

        try:
            await call_llm(FakeLLM(), [Message(role="user", content="x")], events, run_id)
        except ModelParseError as e:
            assert e.content == "garbage output here"
            assert "Invalid JSON" in e.reason

    @pytest.mark.asyncio
    async def test_missing_action_field_raises_model_parse_error(self):
        run_id = uuid4()
        events = MagicMock()
        events.append = AsyncMock()

        class FakeLLM:
            async def generate(self, msgs):
                return SimpleNamespace(content=json.dumps({"content": "no action"}))

        with pytest.raises(ModelParseError):
            await call_llm(FakeLLM(), [Message(role="user", content="x")], events, run_id)

    @pytest.mark.asyncio
    async def test_model_input_payload_contains_prompt_text(self):
        run_id = uuid4()
        events = MagicMock()
        events.append = AsyncMock()

        class FakeLLM:
            async def generate(self, msgs):
                return SimpleNamespace(
                    content=json.dumps({"action": "final", "content": ""})
                )

        messages = [Message(role="system", content="sys"), Message(role="user", content="q")]
        await call_llm(FakeLLM(), messages, events, run_id)

        model_input_payload = events.append.call_args_list[0].kwargs["payload"]
        assert "[system] sys" in model_input_payload["content"]
        assert "[user] q" in model_input_payload["content"]
