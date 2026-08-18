from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.state.state import State


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventType(StrEnum):
    MODEL_INPUT = "model_input"
    MODEL_OUTPUT = "model_output"

    SKILL_REQUESTED = "skill_requested"
    SKILL_RECEIVED = "skill_received"

    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_FAILED = "tool_failed"

    ASK_USER = "ask_user"
    USER_INPUT = "user_input"

    FINAL = "final"
    REFUSED = "refused"


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
    )

    state: State = Field(
        sa_column=Column(
            SAEnum(
                State,
                name="state",
                values_callable=lambda enum: [
                    member.value for member in enum
                ],
            ),
            nullable=False,
            index=True,
        ),
    )

    final_response: str | None = None
    error: str | None = None

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
        ),
    )

    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=utc_now,
        ),
    )


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
    )

    run_id: UUID = Field(
        foreign_key="runs.id",
        index=True,
    )
    # TODO(optimization): replace single-column index=True above with a
    # composite Index("run_id", "created_at") per §12 — needed for
    # efficient GET /runs/{run_id}/events ordering at scale.

    event_type: EventType = Field(
        sa_column=Column(
            SAEnum(
                EventType,
                name="eventtype",
                values_callable=lambda enum: [
                    member.value for member in enum
                ],
            ),
            nullable=False,
        )
    )

    sequence: int

    payload: dict[str, Any] = Field(
        sa_column=Column(
            JSONB,
            nullable=False,
        ),
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
        ),
    )
    
    def __init__(self, **data: Any):
        event_type = data.get("event_type")

        if not isinstance(event_type, EventType):
            raise ValueError(
                f"event_type must be an EventType, got {event_type!r}"
            )

        super().__init__(**data)


class ToolExecution(SQLModel, table=True):
    __tablename__ = "tool_executions"

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
    )

    run_id: UUID = Field(
        foreign_key="runs.id",
        index=True,
    )
    # TODO(optimization): replace single-column index=True above with a
    # composite Index("run_id", "started_at") per §12 — same reasoning
    # as Event, keyed on started_at instead of created_at.

    tool_name: str

    arguments: dict[str, Any] = Field(
        sa_column=Column(
            JSONB,
            nullable=False,
        ),
    )

    result: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(
            JSONB,
            nullable=True,
        ),
    )

    success: bool = False
    error: str | None = None

    started_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
        ),
    )

    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=True,
        ),
    )