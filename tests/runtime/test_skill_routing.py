"""
Tests for skill/tool routing behavior — verifies the runtime correctly
orchestrates skill loading before tool execution, and that the system
prompt makes the tool registry authoritative.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agent.models import (
    AskUser,
    FinalAnswer,
    Refuse,
    SkillRequest,
    ToolCall,
    agent_action_adapter,
)
from app.db.models import EventType
from app.llm.models import Message
from app.runtime.context import ContextMessage, RunContext
from app.runtime.util import (
    SYSTEM_PROMPT,
    build_messages,
    build_skills_section,
    build_tools_section,
)
from app.state.state import State


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


class SearchRegistry:
    """Registry that exposes a search:search tool."""

    def schemas(self):
        return [
            {
                "name": "search:search",
                "description": "Run a web search",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
                "skills": "research-skills.md",
            },
        ]

    def dispatch(self, tool, arguments):
        return FakeToolResult(
            ok=True,
            data={"results": [{"title": "news", "content": "today's news"}]},
        )


class FilesystemRegistry:
    """Registry that exposes a file-system:read_path tool."""

    def schemas(self):
        return [
            {
                "name": "file-system:read_path",
                "description": "Read a text file",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                "skills": "filesystem-skills.md",
            },
        ]

    def dispatch(self, tool, arguments):
        return FakeToolResult(ok=True, data={"content": "hello world"})


class EmptyRegistry:
    """Registry with no tools — should cause refusal."""

    def schemas(self):
        return []

    def dispatch(self, tool, arguments):
        return FakeToolResult(ok=False, error="no tools registered")


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


def make_session():
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.get = AsyncMock()
    session.exec = AsyncMock()
    return session


def make_ctx(run_id, state=State.MODEL_CALL, loaded_skills=None):
    return RunContext(
        run_id=run_id,
        state=state,
        loaded_skills=loaded_skills or set(),
    )


def llm_response(action_dict):
    return json.dumps(action_dict)


# ---------------------------------------------------------------------------
# 1. SYSTEM_PROMPT makes tool registry authoritative
# ---------------------------------------------------------------------------


class TestSystemPromptAuthority:
    def test_prompt_forbids_claiming_missing_capability(self):
        assert "NEVER say you cannot access the internet" in SYSTEM_PROMPT

    def test_prompt_requires_checking_available_tools_first(self):
        assert "Available tools" in SYSTEM_PROMPT
        assert "ground truth" in SYSTEM_PROMPT

    def test_prompt_only_allows_refuse_when_no_tool_exists(self):
        assert "Only use 'refuse' when there is genuinely no tool" in SYSTEM_PROMPT

    def test_prompt_tells_model_to_request_skills_for_tools(self):
        assert "skill_request" in SYSTEM_PROMPT

    def test_prompt_mentions_search_for_current_information(self):
        assert "current information" in SYSTEM_PROMPT
        assert "web research" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# 2. Research skill request
# ---------------------------------------------------------------------------


class TestResearchSkillRequest:
    @pytest.mark.asyncio
    async def test_search_request_requests_research_skill_first(self):
        """When the user asks for web search, the model should request research-skills."""
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)
        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        skill_action = {"action": "skill_request", "skill": "research-skills"}
        search_action = {
            "action": "tool_call",
            "tool": "search:search",
            "arguments": {"query": "today's news in India"},
        }
        final_action = {"action": "final", "content": "Here are the results."}

        llm = FakeLLM([
            llm_response(skill_action),
            llm_response(search_action),
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
                run_id,
                session,
                llm,
                SearchRegistry(),
                FakeSkillLoader(
                    available=["research-skills"],
                    skills={"research-skills": "# Research\nUse search:search for web queries."},
                ),
            )

        assert "research-skills" in ctx.loaded_skills
        tool_msgs = [m for m in ctx.messages if m.role == "tool"]
        assert len(tool_msgs) == 1
        assert ctx.state == State.FINAL


# ---------------------------------------------------------------------------
# 3. Filesystem skill request
# ---------------------------------------------------------------------------


class TestFilesystemSkillRequest:
    @pytest.mark.asyncio
    async def test_read_file_requests_filesystem_skill_first(self):
        """When the user asks to read a file, the model should request filesystem-skills."""
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)
        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        skill_action = {"action": "skill_request", "skill": "filesystem-skills"}
        tool_action = {
            "action": "tool_call",
            "tool": "file-system:read_path",
            "arguments": {"path": "hello.txt"},
        }
        final_action = {"action": "final", "content": "File contents loaded."}

        llm = FakeLLM([
            llm_response(skill_action),
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
                run_id,
                session,
                llm,
                FilesystemRegistry(),
                FakeSkillLoader(
                    available=["filesystem-skills"],
                    skills={"filesystem-skills": "# FS\nUse file-system tools."},
                ),
            )

        assert "filesystem-skills" in ctx.loaded_skills
        tool_msgs = [m for m in ctx.messages if m.role == "tool"]
        assert len(tool_msgs) == 1
        assert ctx.state == State.FINAL


# ---------------------------------------------------------------------------
# 4. Refusal when no suitable capability exists
# ---------------------------------------------------------------------------


class TestRefusalWhenNoCapability:
    @pytest.mark.asyncio
    async def test_refuse_when_no_tools_available(self):
        """With an empty registry, the model should refuse (or the runtime should handle it)."""
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)
        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        refuse_action = {
            "action": "refuse",
            "reason": "No tools available for this task.",
        }
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
            MockRunRepo.return_value.update_state = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()

            await execute_run(run_id, session, llm, EmptyRegistry(), FakeSkillLoader())

        assert ctx.state == State.REFUSED


# ---------------------------------------------------------------------------
# 5. Model cannot claim lack of internet when search:search is available
# ---------------------------------------------------------------------------


class TestSearchToolPreventsFalseRefusal:
    def test_search_tool_in_prompt(self):
        """The build_tools_section output must include search:search."""
        registry = SearchRegistry()
        section = build_tools_section(registry)
        assert "search:search" in section

    def test_prompt_forbids_internet_refusal(self):
        """The system prompt must explicitly forbid claiming no internet access."""
        assert "search the web" in SYSTEM_PROMPT.lower() or "internet" in SYSTEM_PROMPT.lower()

    @pytest.mark.asyncio
    async def test_search_tool_call_validates(self):
        """A search tool call action validates through AgentAction adapter."""
        action = agent_action_adapter.validate_python({
            "action": "tool_call",
            "tool": "search:search",
            "arguments": {"query": "today's news in India"},
        })
        assert isinstance(action, ToolCall)
        assert action.tool == "search:search"
        assert action.arguments["query"] == "today's news in India"


# ---------------------------------------------------------------------------
# 6. Tool execution works after skill loading
# ---------------------------------------------------------------------------


class TestToolExecutionAfterSkillLoad:
    @pytest.mark.asyncio
    async def test_tool_result_appears_in_messages(self):
        """After skill load + tool call, the tool result should be in context messages."""
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)
        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        skill_action = {"action": "skill_request", "skill": "research-skills"}
        search_action = {
            "action": "tool_call",
            "tool": "search:search",
            "arguments": {"query": "python news"},
        }
        final_action = {"action": "final", "content": "Done."}

        llm = FakeLLM([
            llm_response(skill_action),
            llm_response(search_action),
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
                run_id,
                session,
                llm,
                SearchRegistry(),
                FakeSkillLoader(
                    available=["research-skills"],
                    skills={"research-skills": "# Research\nUse search:search."},
                ),
            )

        tool_msgs = [m for m in ctx.messages if m.role == "tool"]
        assert len(tool_msgs) == 1
        tool_payload = json.loads(tool_msgs[0].content)
        assert "result" in tool_payload

        assistant_msgs = [m for m in ctx.messages if m.role == "assistant"]
        assert len(assistant_msgs) == 3


# ---------------------------------------------------------------------------
# 7. State transitions remain valid
# ---------------------------------------------------------------------------


class TestStateTransitions:
    @pytest.mark.asyncio
    async def test_skill_request_then_tool_call_transitions(self):
        """Full cycle: MODEL_CALL -> skill_request -> MODEL_CALL -> tool_call -> MODEL_CALL -> final."""
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)
        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        actions = [
            {"action": "skill_request", "skill": "research-skills"},
            {"action": "tool_call", "tool": "search:search", "arguments": {"query": "test"}},
            {"action": "final", "content": "result"},
        ]
        llm = FakeLLM([llm_response(a) for a in actions])

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
                run_id,
                session,
                llm,
                SearchRegistry(),
                FakeSkillLoader(
                    available=["research-skills"],
                    skills={"research-skills": "# Research\nUse search."},
                ),
            )

        assert ctx.state == State.FINAL
        assert "research-skills" in ctx.loaded_skills

    @pytest.mark.asyncio
    async def test_refuse_transitions_to_refused_state(self):
        """Refuse action transitions to REFUSED terminal state."""
        from app.runtime.runtime import execute_run

        run_id = uuid4()
        run = FakeRun(id=run_id, state=State.MODEL_CALL)
        ctx = make_ctx(run_id, State.MODEL_CALL)
        session = make_session()
        session.commit = AsyncMock()

        refuse_action = {"action": "refuse", "reason": "Cannot do that."}
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
            MockRunRepo.return_value.update_state = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()

            await execute_run(run_id, session, llm, EmptyRegistry(), FakeSkillLoader())

        assert ctx.state == State.REFUSED


# ---------------------------------------------------------------------------
# 8. Prompt includes skills and tools sections correctly
# ---------------------------------------------------------------------------


class TestPromptSections:
    def test_skills_section_lists_available_skills(self):
        loader = FakeSkillLoader(available=["research-skills", "filesystem-skills"])
        section = build_skills_section(loader, set())
        assert "research-skills" in section
        assert "filesystem-skills" in section
        assert "Available skills" in section

    def test_tools_section_includes_search_tool(self):
        registry = SearchRegistry()
        section = build_tools_section(registry)
        assert "search:search" in section

    def test_tools_section_includes_skills_field(self):
        registry = SearchRegistry()
        section = build_tools_section(registry)
        assert "research-skills.md" in section

    def test_build_messages_includes_all_sections(self):
        ctx = make_ctx(uuid4(), loaded_skills={"research-skills"})
        registry = SearchRegistry()
        loader = FakeSkillLoader(
            available=["research-skills"],
            skills={"research-skills": "# Research\nUse search."},
        )
        messages = build_messages(ctx, registry, loader)
        system_content = messages[0].content
        assert "Available tools:" in system_content
        assert "search:search" in system_content
        assert "Loaded skills" in system_content
        assert "research-skills" in system_content
        assert "[Skill: research-skills]" in system_content
