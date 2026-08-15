import re
from pathlib import Path

from app.prompts.sys_prompt_test import SYSTEM_PROMPT

SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# name -> keywords that trigger loading this skill's content.
# Keyword matching is a simple heuristic (no extra model call, no added
# latency): if the task text mentions any of these words, the skill's
# content is appended to the base system prompt for that call.
SKILL_TRIGGERS: dict[str, tuple[str, ...]] = {
    "git": (
        "git", "commit", "push", "pull", "branch",
        "checkout", "merge", "repo", "repository",
    ),
}


def _matches(task_text: str, keywords: tuple[str, ...]) -> bool:
    text = task_text.lower()
    return any(
        re.search(rf"\b{re.escape(kw)}\b", text)
        for kw in keywords
    )


def relevant_skills(task_text: str) -> list[str]:
    """Return the names of skills whose triggers match the given text."""
    return [
        name
        for name, keywords in SKILL_TRIGGERS.items()
        if _matches(task_text, keywords)
    ]


def _load_skill_content(name: str) -> str:
    path = SKILLS_DIR / f"{name}.md"
    return path.read_text()


def build_system_prompt(task_text: str) -> str:
    """
    Build the system prompt for a given call: the base SYSTEM_PROMPT plus
    any skill content whose triggers match the task text. Falls back to
    the base prompt alone (matching the previous static behavior) when no
    skills are relevant.
    """
    parts = [SYSTEM_PROMPT]

    for name in relevant_skills(task_text):
        parts.append(_load_skill_content(name))

    return "\n\n".join(parts)