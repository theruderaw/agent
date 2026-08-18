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

def test_start_to_waiting_for_user():
    assert next_state(State.START) == State.WAITING_FOR_USER


# ─────────────────────────────────────────────
# MODEL CALL — valid transitions
# ─────────────────────────────────────────────

def test_model_call_to_tool_call():
    action = ToolCall(
        tool="filesystem.read",
        arguments={"path": "hello.txt"},
    )
    assert next_state(State.MODEL_CALL, action=action) == State.TOOL_CALL


def test_model_call_to_skill_requested():
    action = SkillRequest(skill="git")
    assert next_state(State.MODEL_CALL, action=action) == State.SKILL_REQUESTED


def test_model_call_to_waiting_for_user():
    action = AskUser(question="Proceed?")
    assert next_state(State.MODEL_CALL, action=action) == State.WAITING_FOR_USER


def test_model_call_to_final():
    action = FinalAnswer(content="Done.")
    assert next_state(State.MODEL_CALL, action=action) == State.FINAL


def test_model_call_to_refused():
    action = Refuse(reason="Cannot do that.")
    assert next_state(State.MODEL_CALL, action=action) == State.REFUSED


# ─────────────────────────────────────────────
# MODEL CALL — invalid
# ─────────────────────────────────────────────

def test_model_call_requires_action():
    with pytest.raises(ValueError, match="AgentAction required"):
        next_state(State.MODEL_CALL)


# ─────────────────────────────────────────────
# TOOL CALL
# ─────────────────────────────────────────────

def test_tool_call_to_model_call():
    assert next_state(State.TOOL_CALL) == State.MODEL_CALL


# ─────────────────────────────────────────────
# SKILL REQUESTED
# ─────────────────────────────────────────────

def test_skill_requested_to_model_call():
    assert next_state(State.SKILL_REQUESTED) == State.MODEL_CALL


# ─────────────────────────────────────────────
# WAITING FOR USER
# ─────────────────────────────────────────────

def test_waiting_for_user_to_model_call():
    assert next_state(State.WAITING_FOR_USER) == State.MODEL_CALL


# ─────────────────────────────────────────────
# TERMINAL
# ─────────────────────────────────────────────

def test_final_to_stop():
    assert next_state(State.FINAL) == State.STOP


def test_refused_to_stop():
    assert next_state(State.REFUSED) == State.STOP


# ─────────────────────────────────────────────
# INVALID TRANSITIONS
# ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "state",
    [
        State.STOP,
        State.FAILED,
    ],
)
def test_terminal_states_reject_transition(state):
    with pytest.raises(ValueError, match="Invalid state transition"):
        next_state(state)
