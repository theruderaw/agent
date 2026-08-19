from app import skills
from app.tools.base import Toolkit


class UvicornTools(Toolkit):
    namespace = "uvicorn"
    skills = "python-skills"

    def __init__(self):
        ...

    def run(
        self,
        app: str,
        args: list[str] | None = None,
    ) -> str:
        """Run a Uvicorn ASGI application."""
        ...