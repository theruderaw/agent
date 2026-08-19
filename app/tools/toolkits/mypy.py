from app import skills
from app.tools.base import Toolkit


class MypyTools(Toolkit):
    namespace = "mypy"
    skills = "testing-skills"

    def __init__(self):
        ...

    def check(self, args: list[str] | None = None) -> str:
        """Type-check Python code with mypy."""
        raise NotImplementedError("mypy:check is not implemented yet")