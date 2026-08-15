from typing import Annotated, Any, Literal
from pydantic import BaseModel,Field, TypeAdapter


class ToolCall(BaseModel):
    action: Literal["tool_call"] = "tool_call"
    tool: str
    arguments: dict[str,Any]


class SkillRequest(BaseModel):
    action: Literal["skill_request"] = "skill_request"
    skill: str


class AskUser(BaseModel):
    action: Literal["ask_user"] = "ask_user"
    question: str


class FinalAnswer(BaseModel):
    action: Literal["final"] = "final"
    content: str


class Refuse(BaseModel):
    action: Literal["refuse"] = "refuse"
    reason: str


AgentAction = Annotated[
    ToolCall
    | SkillRequest
    | AskUser
    | FinalAnswer
    | Refuse,
    Field(discriminator="action"),
]

agent_action_adapter = TypeAdapter(AgentAction)