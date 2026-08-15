import pytest

from app.agent.models import (
    AskUser,
    FinalAnswer,
    Refuse,
    SkillRequest,
    ToolCall,
)
from app.state.state import State, next_state


# ─────────────────────────────────────────────
# START
# ─────────────────────────────────────────────

def test_start_to_model_call():
    assert next_state(State.START) == State.MODEL_CALL


# ─────────────────────────────────────────────
# MODEL CALL
# ─────────────────────────────────────────────

def test_model_call_to_model_output():
    assert next_state(State.MODEL_CALL) == State.MODEL_OUTPUT


# ─────────────────────────────────────────────
# MODEL OUTPUT
# ─────────────────────────────────────────────

def test_model_output_requires_action():
    with pytest.raises(ValueError, match="AgentAction required"):
        next_state(State.MODEL_OUTPUT)


def test_model_output_tool_call():
    action = ToolCall(
        tool="filesystem.read",
        arguments={"path": "hello.txt"},
    )

    assert (
        next_state(
            State.MODEL_OUTPUT,
            action=action,
        )
        == State.TOOL_CALL
    )


def test_model_output_skill_request():
    action = SkillRequest(
        skill="git",
    )

    assert (
        next_state(
            State.MODEL_OUTPUT,
            action=action,
        )
        == State.SKILL_REQUESTED
    )


def test_model_output_ask_user():
    action = AskUser(
        question="Proceed?",
    )

    assert (
        next_state(
            State.MODEL_OUTPUT,
            action=action,
        )
        == State.WAITING_FOR_USER
    )


def test_model_output_final():
    action = FinalAnswer(
        content="Done.",
    )

    assert (
        next_state(
            State.MODEL_OUTPUT,
            action=action,
        )
        == State.FINAL
    )


def test_model_output_refuse():
    action = Refuse(
        reason="I cannot perform that action.",
    )

    assert (
        next_state(
            State.MODEL_OUTPUT,
            action=action,
        )
        == State.REFUSED
    )


# ─────────────────────────────────────────────
# SKILLS
# ─────────────────────────────────────────────

def test_skill_requested_to_skill_received():
    assert (
        next_state(State.SKILL_REQUESTED)
        == State.SKILL_RECEIVED
    )


def test_skill_received_to_model_call():
    assert (
        next_state(State.SKILL_RECEIVED)
        == State.MODEL_CALL
    )


# ─────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────

def test_tool_call_requires_completion_result():
    with pytest.raises(
        ValueError,
        match="tool_completed required",
    ):
        next_state(State.TOOL_CALL)


def test_tool_call_to_tool_result():
    assert (
        next_state(
            State.TOOL_CALL,
            tool_completed=True,
        )
        == State.TOOL_RESULT
    )


def test_tool_call_to_tool_failed():
    assert (
        next_state(
            State.TOOL_CALL,
            tool_completed=False,
        )
        == State.TOOL_FAILED
    )


def test_tool_result_to_model_call():
    assert (
        next_state(State.TOOL_RESULT)
        == State.MODEL_CALL
    )


def test_tool_failed_to_model_call():
    assert (
        next_state(State.TOOL_FAILED)
        == State.MODEL_CALL
    )


# ─────────────────────────────────────────────
# USER
# ─────────────────────────────────────────────

def test_waiting_for_user_to_model_call():
    assert (
        next_state(State.WAITING_FOR_USER)
        == State.MODEL_CALL
    )


# ─────────────────────────────────────────────
# TERMINAL STATES
# ─────────────────────────────────────────────

def test_final_to_stop():
    assert (
        next_state(State.FINAL)
        == State.STOP
    )


def test_refused_to_stop():
    assert (
        next_state(State.REFUSED)
        == State.STOP
    )


# ─────────────────────────────────────────────
# INVALID / TERMINAL TRANSITIONS
# ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "state",
    [
        State.STOP,
        State.FAILED,
    ],
)
def test_terminal_states_reject_transition(state):
    with pytest.raises(
        ValueError,
        match="Invalid state transition",
    ):
        next_state(state)