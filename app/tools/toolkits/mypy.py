from app import skills
from app.tools.base import Toolkit


class MypyTools(Toolkit):
    namespace = "mypy"
    skills = "testing-skills.md"

    def __init__(self):
        ...

    def check(self, args: list[str] | None = None) -> str:
        """Type-check Python code with mypy."""
        ...