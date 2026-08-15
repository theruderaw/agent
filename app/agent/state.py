from enum import StrEnum
from app.agent.models import AgentAction


class State(StrEnum):
    START = "start"
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_FAILED = "tool_failed"
    WAITING_FOR_USER = "waiting_for_user"
    FINAL = "final"
    REFUSED = "refused"
    STOP = "stop"
    FAILED = "failed"
    
    
def next_state(state:State,action:AgentAction | None = None) -> State:
    if state == State.START:
        return State.MODEL_CALL
    elif state == State.MODEL_CALL:
        if action == None:
            raise ValueError("Invalid Action")
        if action.action == 'ask_user':
            return State.WAITING_FOR_USER
        elif action.action == 'tool_call':
            return State.TOOL_CALL
        elif action.action == 'refuse':
            return State.REFUSED
        elif action.action == 'final':
            return State.FINAL
    elif state == State.TOOL_CALL:
        return State.TOOL_RESULT
    elif state == State.TOOL_RESULT:
        return State.MODEL_CALL
    elif state == State.WAITING_FOR_USER:
        return State.MODEL_CALL
    elif state == State.FINAL or state == State.REFUSED:
        return State.STOP
    else:
        return State.FAILED