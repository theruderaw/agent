from dataclasses import dataclass
from typing import Literal

@dataclass
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str


@dataclass
class LLMResponse:
    content: str
