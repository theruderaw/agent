from pydantic import TypeAdapter

from app.agent.models import AgentAction
from app.agent.llms.qwen import call_qwen


action_adapter = TypeAdapter(AgentAction)


def test_qwen_schema():
    response = call_qwen(
        prompt="Calculate 110 + 25",
        thinking=True,
    )

    print(f"\nQwen response: {response}")

    action = action_adapter.validate_json(response)

    print(f"Validated action: {action}")
    print(f"Action type: {type(action).__name__}")

    assert action.action == "tool_call"
    assert action.tool == "calculator"