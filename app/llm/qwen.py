"""
app/llm/qwen.py

Ollama/Qwen LLM adapter.

Ollama gets a single flat structured-output schema because smaller Qwen
models can behave poorly with complex anyOf/oneOf schemas.

The runtime remains responsible for strict semantic validation through
agent_action_adapter.
"""

from __future__ import annotations

import json

import httpx

from app.llm.base import LLM
from app.llm.models import LLMResponse, Message


# ---------------------------------------------------------------------------
# Action format lookup
# ---------------------------------------------------------------------------

ACTION_FORMATS = {
    "tool_call": {
        "required": ["action", "tool", "arguments"],
        "description": (
            'Use when you need to execute a tool. '
            'action="tool_call", tool is the exact registered tool name, '
            "and arguments contains only that tool's arguments."
        ),
    },
    "skill_request": {
        "required": ["action", "skill"],
        "description": (
            'Use when you need to load a skill. '
            'action="skill_request" and skill is the skill name.'
        ),
    },
    "ask_user": {
        "required": ["action", "question"],
        "description": (
            'Use when you need information from the user. '
            'action="ask_user" and question contains the question.'
        ),
    },
    "final": {
        "required": ["action", "content"],
        "description": (
            'Use when the task is complete. '
            'action="final" and content contains the final response.'
        ),
    },
    "refuse": {
        "required": ["action", "reason"],
        "description": (
            'Use when the request must be refused. '
            'action="refuse" and reason contains the explanation.'
        ),
    },
}


# ---------------------------------------------------------------------------
# Ollama structured-output schema
#
# Deliberately FLAT.
#
# Do NOT use:
#   anyOf
#   oneOf
#   discriminator
#
# The model produces the object shape.
# Pydantic performs the final semantic validation afterward.
# ---------------------------------------------------------------------------

AGENT_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": list(ACTION_FORMATS.keys()),
        },
        "tool": {
            "type": "string",
        },
        "arguments": {
            "type": "object",
        },
        "skill": {
            "type": "string",
        },
        "question": {
            "type": "string",
        },
        "content": {
            "type": "string",
        },
        "reason": {
            "type": "string",
        },
    },
    "required": ["action"],
    "additionalProperties": False,
}


class LLMError(Exception):
    """Custom exception for LLM failures."""


class Qwen(LLM):
    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        model: str,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        write_timeout: float = 10.0,
        pool_timeout: float = 10.0,
    ):
        self.client = client
        self.url = url.rstrip("/")
        self.model = model
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.pool_timeout = pool_timeout

    def _format_instructions(self) -> str:
        """
        Return explicit per-action formatting rules.

        This is intentionally separate from the JSON schema. The schema
        constrains the outer JSON shape; these instructions tell Qwen which
        fields belong to each action.
        """

        lines = [
            "",
            "OUTPUT FORMAT RULES:",
            "",
            "Choose exactly ONE action.",
            "Only include fields belonging to that action.",
            "",
        ]

        for action, spec in ACTION_FORMATS.items():
            lines.append(f"{action}:")
            lines.append(f"- {spec['description']}")

            if action == "tool_call":
                lines.append(
                    '- Output exactly: '
                    '{"action":"tool_call","tool":"EXACT_TOOL_NAME","arguments":{...}}'
                )

            elif action == "skill_request":
                lines.append(
                    '- Output exactly: '
                    '{"action":"skill_request","skill":"SKILL_NAME"}'
                )

            elif action == "ask_user":
                lines.append(
                    '- Output exactly: '
                    '{"action":"ask_user","question":"QUESTION"}'
                )

            elif action == "final":
                lines.append(
                    '- Output exactly: '
                    '{"action":"final","content":"FINAL_RESPONSE"}'
                )

            elif action == "refuse":
                lines.append(
                    '- Output exactly: '
                    '{"action":"refuse","reason":"REASON"}'
                )

            lines.append("")

        lines.extend(
            [
                "NEVER do this:",
                '{"action":"ask_user","arguments":{"prompt":"..."}}',
                "",
                "NEVER do this:",
                '{"action":"ask_user","content":"..."}',
                "",
                "NEVER put a tool name in the action field.",
                "NEVER put operation names inside arguments.",
                "NEVER invent fields.",
            ]
        )

        return "\n".join(lines)

    async def generate(self, messages: list[Message]) -> LLMResponse:
        timeout = httpx.Timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=self.write_timeout,
            pool=self.pool_timeout,
        )

        # Add the action-format instructions to the system message.
        prepared_messages = list(messages)

        if prepared_messages and prepared_messages[0].role == "system":
            system_message = prepared_messages[0]

            prepared_messages[0] = Message(
                role="system",
                content=(
                    system_message.content
                    + "\n"
                    + self._format_instructions()
                ),
            )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in prepared_messages
            ],
            "stream": False,

            # Ollama structured output.
            "format": AGENT_ACTION_SCHEMA,
        }

        try:
            response = await self.client.post(
                f"{self.url}/api/chat",
                json=payload,
                timeout=timeout,
            )

            response.raise_for_status()

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                raise LLMError(
                    f"Invalid JSON response from Ollama: {e}"
                ) from e

            message = data.get("message")

            if not isinstance(message, dict):
                raise LLMError(
                    "Ollama response missing 'message' object"
                )

            content = message.get("content")

            if not isinstance(content, str):
                raise LLMError(
                    "Ollama response missing string 'message.content'"
                )

            return LLMResponse(content=content)

        except httpx.TimeoutException as e:
            raise LLMError(
                f"LLM request timed out: {e}"
            ) from e

        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"LLM returned HTTP {e.response.status_code}: "
                f"{e.response.text}"
            ) from e

        except httpx.HTTPError as e:
            raise LLMError(
                f"LLM communication failed: {e}"
            ) from e