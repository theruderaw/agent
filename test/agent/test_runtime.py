import operator
from pathlib import Path

import pytest
from unittest.mock import patch

from app.agent.runtime import run_agent, resume_agent
from app.db.database import get_events, get_run
from app.agent.state import State


NUMS_FILE = Path("./workspace/nums.txt")

# op name -> (python callable, symbol used in prompts, natural-language verb)
OPS = {
    "add": (operator.add, "+", "add"),
    "subtract": (operator.sub, "-", "subtract"),
    "multiply": (operator.mul, "*", "multiply"),
    "divide": (operator.truediv, "/", "divide"),
}


def _read_file_numbers() -> tuple[float, float]:
    """
    Read the two numbers out of workspace/nums.txt so tests assert against
    whatever is actually in the file rather than a hardcoded guess.
    Supports either "a, b" on one line or "a" / "b" on two lines.
    """
    raw = NUMS_FILE.read_text().strip()
    if "," in raw:
        parts = raw.split(",")
    else:
        parts = raw.splitlines()
    a, b = (float(p.strip()) for p in parts[:2])
    return a, b


def _format_expected(value: float) -> str:
    """
    Format a computed expected value the way it's likely to appear in a
    model's natural-language final answer: integers with no trailing
    '.0', floats rounded to a couple decimal places.
    """
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}"


def _result_contains_number(result: str, expected: float, tolerance: float = 0.01) -> bool:
    """
    Check whether a model's natural-language answer contains a number
    matching `expected`, tolerating formatting differences the model is
    free to choose: thousands separators ("4,213,713"), and differing
    decimal precision for non-integer results ("0.3596" vs "0.36").
    """
    assert isinstance(result, str), (
        f"Expected a final string answer but got {type(result).__name__}: {result!r}. "
        "The model likely chose ask_user/refuse instead of completing the task."
    )

    cleaned = result.replace(",", "")

    if expected == int(expected):
        return str(int(expected)) in cleaned

    # Pull out every number-looking substring and compare numerically
    # within tolerance, since the model may round to more or fewer
    # decimal places than we did.
    import re

    for match in re.findall(r"-?\d+\.\d+", cleaned):
        try:
            if abs(float(match) - expected) <= tolerance:
                return True
        except ValueError:
            continue
    return False


# ---------------------------------------------------------------------------
# Deliberate failure-mode tests (1 fail, 1 refuse, 1 ask_user) — mocked
# ---------------------------------------------------------------------------

def test_max_iterations():
    response = """
    {
        "action": "tool_call",
        "tool": "read_file",
        "arguments": {
            "path": "./workspace/nums.txt"
        }
    }
    """

    with patch("app.agent.runtime.call_qwen", return_value=response):
        with pytest.raises(ValueError, match="Exceeded reasoning depth"):
            run_agent("Keep reading the file.")


def test_ask_user():
    # NOTE: real model call, no mock. Relies on the model recognizing the
    # task is underspecified and choosing "ask_user" rather than guessing
    # or refusing. If this is flaky, tighten the prompt or fall back to
    # mocking call_qwen like the mocked version below does.
    run_id, result = run_agent(
        "Calculate X multiplied by 10. You are not told what X is — you "
        "must ask the user for it before doing anything else."
    )

    assert result.action == "ask_user"
    assert result.question

    events = get_events(run_id)

    # ask_user is a pause, not a terminus — no COMPLETED event follows it,
    # so ASK_USER is genuinely the last event.
    assert events[-1].event_type == "ASK_USER"
    assert events[-1].payload == result.question


def test_refuse():
    response = """
    {
        "action": "refuse",
        "reason": "I cannot help with that request."
    }
    """

    with patch("app.agent.runtime.call_qwen", return_value=response):
        run_id, result = run_agent("Do something the agent should refuse.")

    assert result.action == "refuse"
    assert result.reason == "I cannot help with that request."

    events = get_events(run_id)

    # refuse is a true terminus: REFUSED is followed by COMPLETED.
    assert events[-2].event_type == "REFUSED"
    assert events[-2].payload == "I cannot help with that request."
    assert events[-1].event_type == "COMPLETED"


# ---------------------------------------------------------------------------
# Sanity / persistence tests (real model)
# ---------------------------------------------------------------------------

def test_run_agent():
    run_id, result = run_agent("Calculate 110 + 25")

    print(f"\nFinal result: {result}")

    assert result is not None


def test_runtime_persists_run_and_events():
    run_id, result = run_agent("Calculate 120 + 25")

    assert result is not None
    assert "145" in result

    events = get_events(run_id)

    assert len(events) >= 4

    assert events[0].event_type == "RUN_STARTED"
    assert events[0].sequence == 0

    assert events[1].event_type == "MODEL_INPUT"
    assert events[1].sequence == 1
    assert events[1].payload == "Calculate 120 + 25"

    assert events[2].event_type == "MODEL_OUTPUT"
    assert events[2].sequence == 2
    assert events[2].payload

    # FINAL is the "why" event; COMPLETED (added after it) is the terminus.
    assert events[-2].event_type == "FINAL"
    assert events[-2].payload
    assert "145" in events[-2].payload
    assert events[-1].event_type == "COMPLETED"


def test_iterations():
    a, b = _read_file_numbers()
    expected = _format_expected(a + b)

    run_id, result = run_agent(
        "Calculate the sum of the two numbers in workspace/nums.txt and return result"
    )

    print(f"\nFinal result: {result}")

    assert result is not None
    assert expected in result

    events = get_events(run_id)

    event_types = [event.event_type for event in events]

    assert "TOOL_INPUT" in event_types
    assert "TOOL_OUTPUT" in event_types
    assert "FINAL" in event_types

    tool_input_index = event_types.index("TOOL_INPUT")
    tool_output_index = event_types.index("TOOL_OUTPUT")
    final_index = event_types.index("FINAL")

    assert tool_input_index < tool_output_index
    assert tool_output_index < final_index

    assert events[tool_output_index].payload
    assert expected in events[final_index].payload


# ---------------------------------------------------------------------------
# Arithmetic grid: 4 operations x 3 prompt scenarios, real model, no mocks.
# Expected values are computed at test time from the actual file contents,
# so these stay correct even if workspace/nums.txt changes.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("op_name", OPS.keys())
def test_direct_numbers(op_name):
    """Scenario 1: both numbers given directly in the prompt."""
    fn, symbol, verb = OPS[op_name]
    a, b = 48, 6  # chosen directly; nonzero divisor for divide

    expected = fn(a, b)
    prompt = f"Calculate {a} {symbol} {b}"

    run_id, result = run_agent(prompt)

    assert result is not None
    assert _result_contains_number(result, expected)


@pytest.mark.parametrize("op_name", OPS.keys())
def test_numbers_from_file(op_name):
    """Scenario 2: both numbers come from workspace/nums.txt."""
    fn, symbol, verb = OPS[op_name]
    a, b = _read_file_numbers()

    if op_name == "divide" and b == 0:
        pytest.skip("Second number in nums.txt is 0; cannot test division by it.")

    expected = fn(a, b)
    prompt = (
        f"{verb.capitalize()} the two numbers you can read from workspace/nums.txt, "
        f"in the order they appear (first number {symbol} second number)"
    )

    run_id, result = run_agent(prompt)

    assert result is not None
    assert _result_contains_number(result, expected)


@pytest.mark.parametrize("op_name", OPS.keys())
def test_user_number_against_file_sum(op_name):
    """
    Scenario 3: combine a number given in the prompt with the sum of the
    two numbers in workspace/nums.txt, e.g. $num - (file.a + file.b).
    """
    fn, symbol, verb = OPS[op_name]
    a, b = _read_file_numbers()
    file_sum = a + b
    user_num = 500  # arbitrary, chosen directly so it's under our control

    if op_name == "divide" and file_sum == 0:
        pytest.skip("Sum of numbers in nums.txt is 0; cannot test division by it.")

    expected = fn(user_num, file_sum)
    prompt = (
        f"Calculate {user_num} {symbol} the sum of the two numbers "
        f"in workspace/nums.txt"
    )

    run_id, result = run_agent(prompt)

    assert result is not None
    assert _result_contains_number(result, expected)


# ---------------------------------------------------------------------------
# Unit tests (mocked, deterministic) — fast regression suite, no live Ollama
# or filesystem tools needed. Matches the actual runtime.py API: run_agent
# and resume_agent both return (run_id, result) directly.
# ---------------------------------------------------------------------------

import json


def _json(action_dict) -> str:
    return json.dumps(action_dict)


def _fake_calculator(expression: str):
    return eval(expression)  # test-only


def test_unit_single_tool_call():
    responses = [
        _json({"action": "tool_call", "tool": "calculator", "arguments": {"expression": "25 * 4"}}),
        _json({"action": "final", "answer": "100"}),
    ]

    with patch("app.agent.runtime.call_qwen", side_effect=responses), \
         patch("app.agent.runtime.get_tool", return_value=_fake_calculator):
        run_id, result = run_agent("Calculate 25 * 4.")

    assert result == "100"
    assert get_run(run_id).status == State.STOP

    events = get_events(run_id)
    event_types = [e.event_type for e in events]
    assert "RUN_STARTED" in event_types
    assert "FINAL" in event_types
    assert "COMPLETED" in event_types

    tool_output = next(e for e in events if e.event_type == "TOOL_OUTPUT")
    assert tool_output.payload == 100


def test_unit_multi_step_tool_calls():
    responses = [
        _json({"action": "tool_call", "tool": "calculator", "arguments": {"expression": "25 * 4"}}),
        _json({"action": "tool_call", "tool": "calculator", "arguments": {"expression": "100 * 3"}}),
        _json({"action": "final", "answer": "300"}),
    ]

    with patch("app.agent.runtime.call_qwen", side_effect=responses), \
         patch("app.agent.runtime.get_tool", return_value=_fake_calculator):
        run_id, result = run_agent(
            "Calculate 25 * 4, then calculate the result multiplied by 3."
        )

    assert result == "300"

    events = get_events(run_id)
    tool_outputs = [e.payload for e in events if e.event_type == "TOOL_OUTPUT"]
    assert tool_outputs == [100, 300]


def test_unit_ask_user_then_resume():
    with patch("app.agent.runtime.call_qwen",
               side_effect=[_json({"action": "ask_user", "question": "What is X?"})]):
        run_id, result = run_agent("Calculate X multiplied by 10.")

    assert result.action == "ask_user"
    assert result.question == "What is X?"
    assert get_run(run_id).status == State.WAITING_FOR_USER

    resume_responses = [
        _json({"action": "tool_call", "tool": "calculator", "arguments": {"expression": "7 * 10"}}),
        _json({"action": "final", "answer": "70"}),
    ]

    with patch("app.agent.runtime.call_qwen", side_effect=resume_responses), \
         patch("app.agent.runtime.get_tool", return_value=_fake_calculator):
        run_id_2, result_2 = resume_agent(run_id, "X = 7")

    assert run_id_2 == run_id
    assert result_2 == "70"
    assert get_run(run_id).status == State.STOP

    events = get_events(run_id)
    event_types = [e.event_type for e in events]
    assert "ASK_USER" in event_types
    assert "USER_RESPONSE" in event_types
    assert "FINAL" in event_types


def test_unit_resume_rejects_run_not_waiting():
    with patch("app.agent.runtime.call_qwen",
               side_effect=[_json({"action": "final", "answer": "done"})]):
        run_id, _ = run_agent("Say done.")

    assert get_run(run_id).status == State.STOP

    with pytest.raises(ValueError, match="not waiting for user input"):
        resume_agent(run_id, "irrelevant")


def test_unit_refusal():
    responses = [
        _json({"action": "refuse", "reason": "Insufficient information."}),
    ]

    with patch("app.agent.runtime.call_qwen", side_effect=responses):
        run_id, result = run_agent("What is the secret?")

    assert result.action == "refuse"
    assert result.reason == "Insufficient information."
    assert get_run(run_id).status == State.STOP

    events = get_events(run_id)
    event_types = [e.event_type for e in events]
    assert "REFUSED" in event_types
    assert "COMPLETED" in event_types


def test_unit_invalid_json_recovers_on_retry():
    responses = [
        "not valid json",
        _json({"action": "final", "answer": "ok"}),
    ]

    with patch("app.agent.runtime.call_qwen", side_effect=responses):
        run_id, result = run_agent("Say ok.")

    assert result == "ok"

    events = get_events(run_id)
    assert any(e.event_type == "MODEL_OUTPUT_INVALID" for e in events)
    assert get_run(run_id).status == State.STOP


def test_unit_invalid_json_exhausts_retries():
    from app.agent.runtime import MAX_ITERATIONS

    responses = ["not valid json at all"] * MAX_ITERATIONS

    with patch("app.agent.runtime.call_qwen", side_effect=responses):
        with pytest.raises(ValueError, match="Exceeded reasoning depth"):
            run_agent("Calculate something.")


def test_unit_unknown_tool_recovers():
    responses = [
        _json({"action": "tool_call", "tool": "nonexistent_tool", "arguments": {}}),
        _json({"action": "final", "answer": "recovered"}),
    ]

    with patch("app.agent.runtime.call_qwen", side_effect=responses), \
         patch("app.agent.runtime.get_tool", return_value=None):
        run_id, result = run_agent("Do something.")

    assert result == "recovered"

    events = get_events(run_id)
    assert any(
        e.event_type == "TOOL_FAILED" and "Unknown tool" in str(e.payload)
        for e in events
    )


def test_unit_tool_exception_feeds_back_to_qwen():
    def broken_tool(**kwargs):
        raise ZeroDivisionError("division by zero")

    responses = [
        _json({"action": "tool_call", "tool": "calculator", "arguments": {"expression": "1 / 0"}}),
        _json({"action": "final", "answer": "handled the error"}),
    ]

    with patch("app.agent.runtime.call_qwen", side_effect=responses), \
         patch("app.agent.runtime.get_tool", return_value=broken_tool):
        run_id, result = run_agent("Divide by zero.")

    assert result == "handled the error"

    events = get_events(run_id)
    tool_failed = next(e for e in events if e.event_type == "TOOL_FAILED")
    assert "division by zero" in str(tool_failed.payload)


def test_unit_permission_gated_write():
    responses = [
        _json({
            "action": "ask_user",
            "question": "Do you give permission to write the file?"
        }),
        _json({
            "action": "tool_call",
            "tool": "write_file",
            "arguments": {
                "path": "./workspace/test.txt",
                "data": "Hello, this is a write test."
            }
        }),
        _json({
            "action": "final",
            "answer": "The file was written successfully."
        }),
    ]

    written = {}

    def fake_write_file(path: str, data: str):
        written["path"] = path
        written["data"] = data
        return path

    def fake_get_tool(name):
        if name == "write_file":
            return fake_write_file
        return None

    with patch(
        "app.agent.runtime.call_qwen",
        side_effect=responses
    ), patch(
        "app.agent.runtime.get_tool",
        side_effect=fake_get_tool
    ):
        run_id, result = run_agent(
            "Write 'Hello, this is a write test.' to "
            "./workspace/test.txt. Ask for permission first."
        )

    assert result.action == "ask_user"
    assert get_run(run_id).status == State.WAITING_FOR_USER

    # Resume after permission is granted.
    with patch(
        "app.agent.runtime.call_qwen",
        side_effect=responses[1:]
    ), patch(
        "app.agent.runtime.get_tool",
        side_effect=fake_get_tool
    ):
        run_id_2, result_2 = resume_agent(run_id, "yes")

    assert run_id_2 == run_id
    assert result_2 == "The file was written successfully."

    # The actual write tool must have executed.
    assert written["path"] == "./workspace/test.txt"
    assert written["data"] == "Hello, this is a write test."

    events = get_events(run_id)
    event_types = [e.event_type for e in events]

    assert "ASK_USER" in event_types
    assert "USER_RESPONSE" in event_types
    assert "TOOL_INPUT" in event_types
    assert "TOOL_OUTPUT" in event_types
    assert "FINAL" in event_types

    # Most important invariant:
    # permission -> write -> successful result -> final
    assert event_types.index("USER_RESPONSE") < event_types.index("TOOL_INPUT")
    assert event_types.index("TOOL_INPUT") < event_types.index("TOOL_OUTPUT")
    assert event_types.index("TOOL_OUTPUT") < event_types.index("FINAL")