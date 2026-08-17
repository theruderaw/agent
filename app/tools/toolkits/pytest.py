from app.tools.base import Toolkit


class PytestTools(Toolkit):
    namespace = "pytest"

    def __init__(self):
        ...

    def run(self, args: list[str] | None = None) -> str:
        """Run pytest with the given arguments."""
        ...