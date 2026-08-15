import pytest

from app.agent.models import (
    AskUserAction,
    FinalAction,
    RefuseAction,
    ToolCallAction,
)
from app.agent.state import State, next_state


def test_start_to_model_call():
    assert next_state(State.START) == State.MODEL_CALL


def test_model_call_to_tool_call():
    action = ToolCallAction(
        action="tool_call",
        tool="inspect_openapi",
        arguments={},
    )

    assert next_state(State.MODEL_CALL, action) == State.TOOL_CALL


def test_model_call_to_waiting_for_user():
    action = AskUserAction(
        action="ask_user",
        question="Which API should I document?",
    )

    assert next_state(State.MODEL_CALL, action) == State.WAITING_FOR_USER


def test_model_call_to_refused():
    action = RefuseAction(
        action="refuse",
        reason="Not enough information.",
    )

    assert next_state(State.MODEL_CALL, action) == State.REFUSED


def test_model_call_to_final():
    action = FinalAction(
        action="final",
        answer="README generated successfully.",
    )

    assert next_state(State.MODEL_CALL, action) == State.FINAL


def test_tool_call_to_tool_result():
    assert next_state(State.TOOL_CALL) == State.TOOL_RESULT


def test_tool_result_to_model_call():
    assert next_state(State.TOOL_RESULT) == State.MODEL_CALL


def test_waiting_for_user_to_model_call():
    assert next_state(State.WAITING_FOR_USER) == State.MODEL_CALL


def test_final_to_stop():
    assert next_state(State.FINAL) == State.STOP


def test_refused_to_stop():
    assert next_state(State.REFUSED) == State.STOP


def test_invalid_action():
    with pytest.raises(ValueError, match="Invalid Action"):
        next_state(
            State.MODEL_CALL,
            None,
        )