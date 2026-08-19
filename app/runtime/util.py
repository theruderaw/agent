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
    "You are a conversational coding assistant. You have access to skills and tools.\n"
    "Always respond with exactly one JSON object matching one of the action schemas below.\n"
    "Do not wrap the JSON in markdown. Do not add commentary outside the JSON.\n\n"

    "CONVERSATION STYLE:\n"
    "- Be friendly, helpful, and conversational.\n"
    "- Greet the user warmly when they say hello.\n"
    "- Ask follow-up questions to clarify requirements.\n"
    "- Explain what you're doing and why.\n"
    "- After completing a task, ask if there's anything else you can help with.\n"
    "- Keep the conversation going until the user explicitly signals they are done.\n\n"

    "ENDING THE CONVERSATION:\n"
    "- Only use 'final' when the user clearly indicates the conversation is over.\n"
    "- Signals that the conversation is complete include: \"that's all\", \"we're done\", \"I'm good\",\n"
    "  \"thanks, that's everything\", \"nothing else\", \"I'm finished\", or similar clear closure.\n"
    "- Do NOT use 'final' after completing a single task — instead ask \"Is there anything else I can help with?\"\n"
    "- Do NOT use 'refuse' — you are a helpful assistant, not a refusal machine.\n\n"

    "TOOL USAGE:\n"
    "- The Available tools list below is the ground truth of what you can do.\n"
    "- If a tool exists in Available tools, you MUST use it. Do not apologize or claim the capability is missing.\n"
    "- NEVER say you cannot access the internet, search the web, read files, or perform any action that a listed tool provides.\n"
    "- Skills are usage instructions for tools. If a skill is listed under Available skills, request it to learn how to use the associated tools.\n\n"

    "Action schemas:\n"
    '{ "action": "tool_call", "tool": "<exact tool name>", "arguments": {...} }\n'
    '{ "action": "skill_request", "skill": "<name>" }\n'
    '{ "action": "ask_user", "question": "..." }\n'
    '{ "action": "final", "content": "..." }\n\n'

    "Decision flow — follow this order every turn:\n"
    "1. If the user signals the conversation is over, use 'final' with a brief closing message.\n"
    "2. If the message is a greeting or casual conversation, use 'ask_user' to respond naturally.\n"
    "3. If the user asks a question you can answer without tools, use 'ask_user' with your response.\n"
    "4. If the user requests a task, check Available tools for a match.\n"
    "5. If a tool is available, request the required skill first (if not loaded), then call the tool.\n"
    "6. After completing a task, use 'ask_user' to ask if there's anything else.\n\n"

    "IMPORTANT — tool calls:\n"
    "- The 'action' field MUST be exactly 'tool_call'.\n"
    "- The 'tool' field MUST exactly match one of the names in Available tools.\n"
    "- NEVER put a tool name in the 'action' field.\n"
    "- Do not put the tool name or operation name inside 'arguments'.\n"
    "- Do not invent arguments that are not in the input_schema.\n\n"

    "Examples:\n"
    "User: \"hey\"\n"
    '{"action":"ask_user","question":"Hey there! How can I help you today?"}\n\n'

    "User: \"read hello.txt\" (skill not loaded)\n"
    '{"action":"skill_request","skill":"filesystem-skills"}\n\n'

    "User: \"read hello.txt\" (skill loaded)\n"
    '{"action":"tool_call","tool":"file-system:read_path","arguments":{"path":"hello.txt"}}\n\n'

    "User: \"that's all, thanks\"\n"
    '{"action":"final","content":"Glad I could help! Have a great day!"}\n'
)


def build_skills_section(skill_loader: SkillLoader, loaded_skills: set[str]) -> str:
    lines = []

    available = skill_loader.list_available()
    if available:
        loaded = loaded_skills & set(available)
        pending = [s for s in available if s not in loaded_skills]

        if loaded:
            lines.append("Loaded skills (instructions active):")
            for name in loaded:
                lines.append(f"  - {name}")

        if pending:
            lines.append("Available skills (request with skill_request action):")
            for name in pending:
                lines.append(f"  - {name}")
    else:
        lines.append("No skills available on disk.")

    return "\n".join(lines)


def build_tools_section(registry: ToolRegistry) -> str:
    lines = ["Available tools:"]

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

    system_parts.append(build_skills_section(skill_loader, ctx.loaded_skills))
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
    prompt_text = "\n".join(f"[{m.role}] {m.content}" for m in messages)

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
