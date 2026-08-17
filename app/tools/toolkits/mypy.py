from app.tools.base import Toolkit


class MypyTools(Toolkit):
    namespace = "mypy"

    def __init__(self):
        ...

    def check(self, args: list[str] | None = None) -> str:
        """Type-check Python code with mypy."""
        ...