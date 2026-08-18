from app import skills
from app.tools.base import Toolkit


class PytestTools(Toolkit):
    namespace = "pytest"
    skills = "testing-skills.md"

    def __init__(self):
        ...

    def run(self, args: list[str] | None = None) -> str:
        """Run pytest with the given arguments."""
        ...