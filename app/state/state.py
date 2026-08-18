from enum import StrEnum

from app.agent.models import AgentAction


class State(StrEnum):
    START = "start"
    MODEL_CALL = "model_call"

    SKILL_REQUESTED = "skill_requested"

    TOOL_CALL = "tool_call"

    WAITING_FOR_USER = "waiting_for_user"

    FINAL = "final"
    REFUSED = "refused"

    STOP = "stop"
    FAILED = "failed"
    
def next_state(
    state: State,
    action: AgentAction | None = None,
) -> State:
    if state == State.START:
        return State.WAITING_FOR_USER

    if state == State.MODEL_CALL:
        if action is None:
            raise ValueError("AgentAction required in MODEL_CALL")

        if action.action == "ask_user":
            return State.WAITING_FOR_USER

        if action.action == "skill_request":
            return State.SKILL_REQUESTED

        if action.action == "tool_call":
            return State.TOOL_CALL

        if action.action == "refuse":
            return State.REFUSED

        if action.action == "final":
            return State.FINAL

    if state == State.SKILL_REQUESTED:
        return State.MODEL_CALL
    
    if state == State.TOOL_CALL:
        return State.MODEL_CALL

    if state == State.WAITING_FOR_USER:
        return State.MODEL_CALL

    if state in (State.FINAL, State.REFUSED):
        return State.STOP

    raise ValueError(f"Invalid state transition from {state}")