from app import skills
from app.tools.base import Toolkit


class RuffTools(Toolkit):
    namespace = "ruff"
    skills = "testing-skills.md"

    def __init__(self):
        ...

    def check(self, args: list[str] | None = None) -> str:
        """Check Python code with Ruff."""
        ...

    def format(self, args: list[str] | None = None) -> str:
        """Format Python code with Ruff."""
        ...