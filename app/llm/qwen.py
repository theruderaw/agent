import json
import httpx
from app.llm.base import LLM
from app.llm.models import Message, LLMResponse

class LLMError(Exception):
    """Custom exception for LLM failures."""
    pass

class Qwen(LLM):
    def __init__(self, client: httpx.AsyncClient, url: str, model: str):
        self.client = client
        self.url = url.rstrip("/")
        self.model = model

    async def generate(self, messages: list[Message]) -> LLMResponse:
        # Requirement 33: Explicit timeouts (connect, read, write)
        timeout = httpx.Timeout(
            connect=5.0,
            read=30.0,
            write=10.0,
            pool=10.0,
        )

        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "format": "json",
        }

        try:
            response = await self.client.post(
                f"{self.url}/api/chat",
                json=payload,
                timeout=timeout,  # Prevents indefinite hanging (Requirement 33)
            )
            response.raise_for_status()  # Raises on 4xx/5xx

            data = response.json()
            
            # Requirement 32: Extract the actual content, not the raw Ollama envelope
            content = data.get("message", {}).get("content")
            if content is None:
                raise LLMError("Ollama response missing 'message.content'")
            
            # The runtime receives a clean LLMResponse, not an Ollama-specific dict
            return LLMResponse(content=content)

        except httpx.TimeoutException as e:
            raise LLMError(f"LLM request timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            raise LLMError(f"LLM returned HTTP {e.response.status_code}: {e.response.text}") from e
        except (json.JSONDecodeError, KeyError) as e:
            raise LLMError(f"Invalid response format from Ollama: {e}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"LLM communication failed: {e}") from e