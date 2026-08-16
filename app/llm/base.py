from abc import ABC, abstractmethod

from app.llm.models import LLMResponse, Message

class LLM(ABC):
    @abstractmethod
    async def generate(self, messages: list[Message]) -> LLMResponse:
        ...