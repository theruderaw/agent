from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Enum
from sqlmodel import Field, SQLModel
from app.agent.state import State


class AgentRun(SQLModel, table=True):
    run_id: UUID = Field(default_factory=uuid4, primary_key=True)

    status: State = Field(
        default=State.START,
        sa_column=Column(
            Enum(
                State,
                values_callable=lambda enum: [member.value for member in enum],
            )
        ),
    )
    iteration: int = 0

    created_at: datetime = Field(
        default_factory=datetime.now
    )

    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime,
            default=datetime.now,
            onupdate=datetime.now,
        ),
    )


class AgentEvent(SQLModel, table=True):
    run_id: UUID = Field(
        foreign_key="agentrun.run_id",
        primary_key=True,
    )
    sequence: int = Field(primary_key=True)
    event_type: str
    payload: str
    created_at: datetime = Field(
        default_factory=datetime.now
    )