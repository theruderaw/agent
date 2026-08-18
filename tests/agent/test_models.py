"""Tests for app/agent/models.py — discriminated union validation."""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.agent.models import (
    AgentAction,
    AskUser,
    FinalAnswer,
    Refuse,
    SkillRequest,
    ToolCall,
    agent_action_adapter,
)


# ─────────────────────────────────────────────
# Individual model construction
# ─────────────────────────────────────────────

class TestToolCall:
    def test_construction(self):
        tc = ToolCall(tool="fs:read", arguments={"path": "x"})
        assert tc.action == "tool_call"
        assert tc.tool == "fs:read"
        assert tc.arguments == {"path": "x"}

    def test_default_action(self):
        tc = ToolCall(tool="a", arguments={})
        assert tc.action == "tool_call"

    def test_empty_arguments(self):
        tc = ToolCall(tool="a", arguments={})
        assert tc.arguments == {}


class TestSkillRequest:
    def test_construction(self):
        sr = SkillRequest(skill="git")
        assert sr.action == "skill_request"
        assert sr.skill == "git"

    def test_default_action(self):
        sr = SkillRequest(skill="x")
        assert sr.action == "skill_request"


class TestAskUser:
    def test_construction(self):
        au = AskUser(question="which one?")
        assert au.action == "ask_user"
        assert au.question == "which one?"

    def test_default_action(self):
        au = AskUser(question="q")
        assert au.action == "ask_user"


class TestFinalAnswer:
    def test_construction(self):
        fa = FinalAnswer(content="the answer")
        assert fa.action == "final"
        assert fa.content == "the answer"

    def test_default_action(self):
        fa = FinalAnswer(content="x")
        assert fa.action == "final"


class TestRefuse:
    def test_construction(self):
        r = Refuse(reason="cannot")
        assert r.action == "refuse"
        assert r.reason == "cannot"

    def test_default_action(self):
        r = Refuse(reason="x")
        assert r.action == "refuse"


# ─────────────────────────────────────────────
# Discriminated union validation
# ─────────────────────────────────────────────

class TestAgentActionAdapter:
    def test_tool_call(self):
        payload = {"action": "tool_call", "tool": "fs:read", "arguments": {"path": "x"}}
        action = agent_action_adapter.validate_python(payload)
        assert isinstance(action, ToolCall)
        assert action.tool == "fs:read"

    def test_skill_request(self):
        payload = {"action": "skill_request", "skill": "git"}
        action = agent_action_adapter.validate_python(payload)
        assert isinstance(action, SkillRequest)
        assert action.skill == "git"

    def test_ask_user(self):
        payload = {"action": "ask_user", "question": "which?"}
        action = agent_action_adapter.validate_python(payload)
        assert isinstance(action, AskUser)
        assert action.question == "which?"

    def test_final(self):
        payload = {"action": "final", "content": "done"}
        action = agent_action_adapter.validate_python(payload)
        assert isinstance(action, FinalAnswer)
        assert action.content == "done"

    def test_refuse(self):
        payload = {"action": "refuse", "reason": "no"}
        action = agent_action_adapter.validate_python(payload)
        assert isinstance(action, Refuse)
        assert action.reason == "no"

    def test_unknown_action_raises(self):
        with pytest.raises(Exception):
            agent_action_adapter.validate_python({"action": "unknown"})

    def test_missing_action_field_raises(self):
        with pytest.raises(Exception):
            agent_action_adapter.validate_python({"tool": "x"})

    def test_empty_dict_raises(self):
        with pytest.raises(Exception):
            agent_action_adapter.validate_python({})

    def test_tool_call_missing_tool_raises(self):
        with pytest.raises(Exception):
            agent_action_adapter.validate_python({"action": "tool_call", "arguments": {}})

    def test_tool_call_missing_arguments_raises(self):
        with pytest.raises(Exception):
            agent_action_adapter.validate_python({"action": "tool_call", "tool": "x"})

    def test_final_missing_content_raises(self):
        with pytest.raises(Exception):
            agent_action_adapter.validate_python({"action": "final"})

    def test_refuse_missing_reason_raises(self):
        with pytest.raises(Exception):
            agent_action_adapter.validate_python({"action": "refuse"})

    def test_ask_user_missing_question_raises(self):
        with pytest.raises(Exception):
            agent_action_adapter.validate_python({"action": "ask_user"})

    def test_skill_request_missing_skill_raises(self):
        with pytest.raises(Exception):
            agent_action_adapter.validate_python({"action": "skill_request"})

    def test_extra_fields_ignored(self):
        payload = {"action": "final", "content": "done", "extra": "ignored"}
        action = agent_action_adapter.validate_python(payload)
        assert isinstance(action, FinalAnswer)

    def test_tool_call_with_empty_arguments(self):
        payload = {"action": "tool_call", "tool": "x", "arguments": {}}
        action = agent_action_adapter.validate_python(payload)
        assert isinstance(action, ToolCall)
        assert action.arguments == {}

    def test_tool_call_with_nested_arguments(self):
        payload = {"action": "tool_call", "tool": "x", "arguments": {"a": {"b": 1}, "c": [1, 2]}}
        action = agent_action_adapter.validate_python(payload)
        assert isinstance(action, ToolCall)
        assert action.arguments == {"a": {"b": 1}, "c": [1, 2]}

    def test_empty_string_action_raises(self):
        with pytest.raises(Exception):
            agent_action_adapter.validate_python({"action": ""})

    def test_integer_action_raises(self):
        with pytest.raises(Exception):
            agent_action_adapter.validate_python({"action": 123})

    def test_none_action_raises(self):
        with pytest.raises(Exception):
            agent_action_adapter.validate_python({"action": None})
