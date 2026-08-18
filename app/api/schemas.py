from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class RunCreate(BaseModel):
    pass


class RunResponse(BaseModel):
    run_id: UUID
    state: str
    created_at: datetime
    updated_at: datetime
    final_response: str | None = None
    error: str | None = None


class EventResponse(BaseModel):
    event_type: str
    payload: dict[str, Any]
    sequence: int
    created_at: datetime


class EventListResponse(BaseModel):
    events: list[EventResponse]


class UserInputRequest(BaseModel):
    input: str


class UserInputResponse(BaseModel):
    run_id: UUID
    state: str
