# app/tools/toolkits/model.py

from app.tools.base import Toolkit


class ModelTools(Toolkit):
    namespace = "model"

    def __init__(self):
        pass

    async def invoke(self, prompt: str) -> str:
        """Send a prompt to a language model and return its response."""
        raise NotImplementedError("Model invocation is not implemented yet.")