import json
import pytest
import httpx
from app.llm.qwen import Qwen
from app.llm.models import Message, LLMResponse

@pytest.mark.asyncio
async def test_qwen_generate():
    requests = []

    async def handler(request: httpx.Request):
        requests.append(request)  # Capture the request
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": '{"answer": "hello"}',
                }
            },
        )

    transport = httpx.MockTransport(handler)

    # Requirement 33: The client itself could have defaults, but we'll let the adapter handle timeouts.
    async with httpx.AsyncClient(transport=transport) as client:
        qwen = Qwen(
            client=client,
            url="http://localhost:11434",
            model="qwen2.5:3b",
        )

        messages = [
            Message(
                role="user",
                content="Say hello",
            )
        ]

        # Runtime receives an LLMResponse, not a raw dict
        result = await qwen.generate(messages)
        assert isinstance(result, LLMResponse)
        assert result.content == '{"answer": "hello"}'

    assert len(requests) == 1
    request = requests[0]

    # Validate the request details
    assert request.method == "POST"
    assert str(request.url) == "http://localhost:11434/api/chat"

    # ✅ FIX: 'Request' has no '.json()', so parse the body manually
    assert json.loads(request.content) == {
        "model": "qwen2.5:3b",
        "messages": [
            {"role": "user", "content": "Say hello"},
        ],
        "stream": False,
        "format": "json",
    }