from typing import Annotated, Literal
from pydantic import BaseModel, Field, TypeAdapter

class ToolCallAction(BaseModel):
    action: Literal['tool_call']
    tool: str
    arguments: dict

class RefuseAction(BaseModel):
    action: Literal['refuse']
    reason: str

class AskUserAction(BaseModel):
    action: Literal["ask_user"]
    question: str

class FinalAction(BaseModel):
    action: Literal["final"]
    answer: str

AgentAction = Annotated[
    ToolCallAction | RefuseAction | AskUserAction | FinalAction,
    Field(discriminator="action"),
]

class UserAction(BaseModel):
    run_id: str
    message: str

action_adapter = TypeAdapter(AgentAction)
schema = action_adapter.json_schema()