"""
app/skills/loader.py

Skill loader: locates a skill by name and loads its markdown content
from the skills directory (docs/ by default).

Skills provide instructions/context only — no execution. See spec
section 27 for the tools/skills separation this module respects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


class SkillNotFoundError(Exception):
    """Raised when a requested skill does not exist on disk."""

    def __init__(self, skill_name: str, search_dir: Path):
        self.skill_name = skill_name
        self.search_dir = search_dir
        super().__init__(
            f"Skill '{skill_name}' not found in {search_dir} "
            f"(expected file: {skill_name}.md)"
        )


class InvalidSkillNameError(Exception):
    """Raised when a skill name contains characters that could escape
    the skills directory (path traversal, absolute paths, etc.)."""

    def __init__(self, skill_name: str):
        self.skill_name = skill_name
        super().__init__(f"Invalid skill name: '{skill_name}'")


# Only allow simple names: letters, numbers, underscore, hyphen.
# No slashes, no dots (besides the extension we append ourselves),
# no leading/trailing whitespace tricks.
_VALID_SKILL_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class Skill:
    name: str
    path: Path
    content: str


class SkillLoader:
    """Loads skill markdown files by name from a configured directory."""

    def __init__(self, skills_dir: str | Path):
        self.skills_dir = Path(skills_dir).resolve()

    def _validate_name(self, skill_name: str) -> None:
        if not skill_name or not _VALID_SKILL_NAME.match(skill_name):
            raise InvalidSkillNameError(skill_name)

    def _resolve_path(self, skill_name: str) -> Path:
        self._validate_name(skill_name)
        candidate = (self.skills_dir / f"{skill_name}.md").resolve()

        # Defense in depth: even with the name regex above, make sure
        # the resolved path is still inside skills_dir.
        if self.skills_dir not in candidate.parents and candidate != self.skills_dir:
            raise InvalidSkillNameError(skill_name)

        return candidate

    def exists(self, skill_name: str) -> bool:
        try:
            path = self._resolve_path(skill_name)
        except InvalidSkillNameError:
            return False
        return path.is_file()

    def load(self, skill_name: str) -> Skill:
        """Locate skillname.md in skills_dir and return its content.

        Raises SkillNotFoundError if the file doesn't exist.
        Raises InvalidSkillNameError if the name is unsafe.
        """
        path = self._resolve_path(skill_name)

        if not path.is_file():
            raise SkillNotFoundError(skill_name, self.skills_dir)

        content = path.read_text(encoding="utf-8")
        return Skill(name=skill_name, path=path, content=content)

    def list_available(self) -> list[str]:
        """Return names (without .md) of all skills currently on disk."""
        if not self.skills_dir.is_dir():
            return []
        return sorted(p.stem for p in self.skills_dir.glob("*.md"))