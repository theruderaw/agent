from pathlib import Path

from app.tools.base import Toolkit


class PythonTools(Toolkit):
    namespace = "python"

    def __init__(self):
        self.root = Path(__file__).parent.parent.parent.parent.resolve()

    def run(self, code: str) -> str:
        """Execute Python code."""
        ...

    def venv(self, path: str) -> str:
        """Create a Python virtual environment."""
        ...