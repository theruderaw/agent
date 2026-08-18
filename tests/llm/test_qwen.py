"""Tests for app/llm/qwen.py — all error paths."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from app.agent.models import (
    agent_action_adapter,
)
from app.llm.models import Message
from app.llm.qwen import AGENT_ACTION_SCHEMA, LLMError, Qwen


@pytest.fixture
def client():
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def llm(client):
    return Qwen(client=client, url="http://localhost:11434", model="qwen2.5-coder:3b")


@pytest.mark.asyncio
async def test_generate_success(client, llm):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"role": "assistant", "content": '{"action":"final","content":"hi"}'}}
    mock_resp.raise_for_status = MagicMock()
    client.post.return_value = mock_resp

    resp = await llm.generate([Message(role="user", content="hello")])
    assert resp.content == '{"action":"final","content":"hi"}'


@pytest.mark.asyncio
async def test_generate_sends_format_schema(client, llm):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"role": "assistant", "content": "{}"}}
    mock_resp.raise_for_status = MagicMock()
    client.post.return_value = mock_resp

    await llm.generate([Message(role="user", content="hello")])

    call_kwargs = client.post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert payload["format"] == AGENT_ACTION_SCHEMA
    assert payload["model"] == "qwen2.5-coder:3b"
    assert payload["stream"] is False


@pytest.mark.asyncio
async def test_generate_trailing_slash_stripped(client):
    qwen = Qwen(client=client, url="http://localhost:11434/", model="m")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"role": "assistant", "content": "{}"}}
    mock_resp.raise_for_status = MagicMock()
    client.post.return_value = mock_resp

    await qwen.generate([Message(role="user", content="x")])
    assert client.post.call_args.args[0] == "http://localhost:11434/api/chat"


@pytest.mark.asyncio
async def test_timeout_raises_llm_error(client, llm):
    client.post.side_effect = httpx.TimeoutException("timed out")
    with pytest.raises(LLMError, match="timed out"):
        await llm.generate([Message(role="user", content="x")])


@pytest.mark.asyncio
async def test_http_status_error_raises_llm_error(client, llm):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "internal error"
    client.post.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=mock_resp
    )
    with pytest.raises(LLMError, match="HTTP 500"):
        await llm.generate([Message(role="user", content="x")])


@pytest.mark.asyncio
async def test_http_error_raises_llm_error(client, llm):
    client.post.side_effect = httpx.HTTPError("connection reset")
    with pytest.raises(LLMError, match="communication failed"):
        await llm.generate([Message(role="user", content="x")])


@pytest.mark.asyncio
async def test_missing_message_object_raises_llm_error(client, llm):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"not_message": True}
    mock_resp.raise_for_status = MagicMock()
    client.post.return_value = mock_resp

    with pytest.raises(LLMError, match="missing 'message' object"):
        await llm.generate([Message(role="user", content="x")])


@pytest.mark.asyncio
async def test_message_not_dict_raises_llm_error(client, llm):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": "not a dict"}
    mock_resp.raise_for_status = MagicMock()
    client.post.return_value = mock_resp

    with pytest.raises(LLMError, match="missing 'message' object"):
        await llm.generate([Message(role="user", content="x")])


@pytest.mark.asyncio
async def test_missing_content_raises_llm_error(client, llm):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"role": "assistant"}}
    mock_resp.raise_for_status = MagicMock()
    client.post.return_value = mock_resp

    with pytest.raises(LLMError, match="missing string 'message.content'"):
        await llm.generate([Message(role="user", content="x")])


@pytest.mark.asyncio
async def test_content_not_string_raises_llm_error(client, llm):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"role": "assistant", "content": 123}}
    mock_resp.raise_for_status = MagicMock()
    client.post.return_value = mock_resp

    with pytest.raises(LLMError, match="missing string 'message.content'"):
        await llm.generate([Message(role="user", content="x")])


@pytest.mark.asyncio
async def test_invalid_json_response_raises_llm_error(client, llm):
    mock_resp = MagicMock()
    mock_resp.json.side_effect = json.JSONDecodeError("err", "doc", 0)
    mock_resp.raise_for_status = MagicMock()
    client.post.return_value = mock_resp

    with pytest.raises(LLMError, match="Invalid JSON response"):
        await llm.generate([Message(role="user", content="x")])


def test_agent_action_schema_structure():
    assert AGENT_ACTION_SCHEMA["type"] == "object"
    assert AGENT_ACTION_SCHEMA["required"] == ["action"]
    assert AGENT_ACTION_SCHEMA["additionalProperties"] is False
    props = AGENT_ACTION_SCHEMA["properties"]
    assert props["action"]["enum"] == ["tool_call", "skill_request", "ask_user", "final", "refuse"]
    assert "tool" in props
    assert "arguments" in props
    assert "skill" in props
    assert "question" in props
    assert "content" in props
    assert "reason" in props


# ---------------------------------------------------------------------------
# Schema ↔ AgentAction compatibility
#
# Verify that JSON matching AGENT_ACTION_SCHEMA validates through the real
# Pydantic AgentAction adapter for every action type the model can produce.
# ---------------------------------------------------------------------------


ACTION_SAMPLES = [
    {
        "action": "tool_call",
        "tool": "file-system:read_path",
        "arguments": {"path": "hello.txt"},
    },
    {
        "action": "skill_request",
        "skill": "git",
    },
    {
        "action": "ask_user",
        "question": "Which file should I edit?",
    },
    {
        "action": "final",
        "content": "Here is the answer.",
    },
    {
        "action": "refuse",
        "reason": "I cannot do that.",
    },
]


class TestSchemaActionCompatibility:
    def test_all_action_types_validate(self):
        for sample in ACTION_SAMPLES:
            action = agent_action_adapter.validate_python(sample)
            assert action is not None
            assert hasattr(action, "action")

    def test_tool_call_fields(self):
        action = agent_action_adapter.validate_python(ACTION_SAMPLES[0])
        assert action.tool == "file-system:read_path"
        assert action.arguments == {"path": "hello.txt"}

    def test_skill_request_fields(self):
        action = agent_action_adapter.validate_python(ACTION_SAMPLES[1])
        assert action.skill == "git"

    def test_ask_user_fields(self):
        action = agent_action_adapter.validate_python(ACTION_SAMPLES[2])
        assert action.question == "Which file should I edit?"

    def test_final_fields(self):
        action = agent_action_adapter.validate_python(ACTION_SAMPLES[3])
        assert action.content == "Here is the answer."

    def test_refuse_fields(self):
        action = agent_action_adapter.validate_python(ACTION_SAMPLES[4])
        assert action.reason == "I cannot do that."

    def test_json_roundtrip(self):
        for sample in ACTION_SAMPLES:
            raw = json.dumps(sample, separators=(",", ":"))
            parsed = json.loads(raw)
            action = agent_action_adapter.validate_python(parsed)
            assert action is not None
            assert hasattr(action, "action")

    def test_extra_properties_ignored(self):
        sample = {
            "action": "final",
            "content": "ok",
            "extra_field": "should be ignored",
        }
        action = agent_action_adapter.validate_python(sample)
        assert action.content == "ok"

    def test_missing_required_field_rejected(self):
        sample = {"action": "tool_call", "tool": "fs:read"}
        with pytest.raises(ValidationError):
            agent_action_adapter.validate_python(sample)

    def test_unknown_action_rejected(self):
        sample = {"action": "unknown_action"}
        with pytest.raises(ValidationError):
            agent_action_adapter.validate_python(sample)
