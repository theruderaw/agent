"""
app/runtime/util.py

Shared helpers for the runtime: prompt building, LLM call/parse, constants.
"""

from __future__ import annotations

import json
from uuid import UUID

from pydantic import ValidationError

from app.agent.models import (
    AgentAction,
    agent_action_adapter,
)
from app.db.models import EventType
from app.db.repository import EventRepository
from app.llm.base import LLM
from app.llm.models import LLMResponse, Message
from app.runtime.context import RunContext
from app.skills.loader import SkillLoader
from app.tools.base import ToolRegistry


class ModelParseError(Exception):
    def __init__(self, content: str, reason: str):
        self.content = content
        self.reason = reason
        super().__init__(reason)


SYSTEM_PROMPT = (
    "You are a helpful coding assistant. You have access to tools.\n"
    "Always respond with exactly one JSON object matching one of the action schemas below.\n"
    "Do not wrap the JSON in markdown. Do not add commentary outside the JSON.\n\n"

    "Action schemas:\n"
    '{ "action": "tool_call", "tool": "<exact tool name>", "arguments": {...} }\n'
    '{ "action": "skill_request", "skill": "<name>" }\n'
    '{ "action": "ask_user", "question": "..." }\n'
    '{ "action": "final", "content": "..." }\n'
    '{ "action": "refuse", "reason": "..." }\n\n'

    "IMPORTANT — tool calls:\n"
    "- For a tool call, the 'action' field MUST be exactly 'tool_call'.\n"
    "- Put the exact tool name in the 'tool' field.\n"
    "- The 'tool' field MUST exactly match one of the names listed in Available tools.\n"
    "- NEVER put a tool name in the 'action' field.\n"
    "- The 'arguments' object MUST match that tool's input_schema.\n"
    "- Do not put the tool name or operation name inside 'arguments'.\n"
    "- Do not invent arguments that are not in the input_schema.\n\n"

    "Example tool call:\n"
    '{ "action": "tool_call", "tool": "file-system:read_path", '
    '"arguments": { "path": "hello.txt" } }\n'
)


def build_tools_section(registry: ToolRegistry) -> str:
    lines = [
        "Available tools:",
        "Use the exact tool name shown in the 'name' field.",
        "Do not put the tool name in 'arguments'.",
    ]

    for tool in registry.schemas():
        lines.append(json.dumps(tool, separators=(",", ":")))

    return "\n".join(lines)


def build_messages(
    ctx: RunContext,
    registry: ToolRegistry,
    skill_loader: SkillLoader,
) -> list[Message]:
    messages: list[Message] = []

    system_parts = [SYSTEM_PROMPT]

    system_parts.append(build_tools_section(registry))

    for skill_name in ctx.loaded_skills:
        try:
            skill = skill_loader.load(skill_name)
            system_parts.append(f"[Skill: {skill_name}]\n{skill.content}")
        except Exception:
            pass

    messages.append(Message(role="system", content="\n\n".join(system_parts)))

    for msg in ctx.messages:
        messages.append(Message(role=msg.role, content=msg.content))

    return messages


async def call_llm(
    llm: LLM,
    messages: list[Message],
    events: EventRepository,
    run_id: UUID,
) -> tuple[LLMResponse, AgentAction]:
    prompt_text = "\n".join(f"[{m.role}] {m.content[:500]}" for m in messages)

    await events.append(
        run_id=run_id,
        event_type=EventType.MODEL_INPUT,
        payload={"content": prompt_text},
    )

    response = await llm.generate(messages)

    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as e:
        raise ModelParseError(
            response.content,
            f"Invalid JSON: {e}",
        ) from e

    try:
        action = agent_action_adapter.validate_python(payload)
    except ValidationError as e:
        raise ModelParseError(
            response.content,
            f"Invalid action schema: {e}",
        ) from e

    await events.append(
        run_id=run_id,
        event_type=EventType.MODEL_OUTPUT,
        payload={
            "content": response.content,
            "action": payload,
        },
    )

    return response, action


if __name__ == "__main__":
    from app.tools.registry import build_registry

    registry = build_registry()
    tools_section = build_tools_section(registry)
    print(SYSTEM_PROMPT + "\n" + tools_section)