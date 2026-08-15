import json
from typing import Any
from uuid import UUID

from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import AgentRun, AgentEvent
from app.agent.state import State


DATABASE_URL = "sqlite:///agent.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


def init_db():
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)

def create_run() -> UUID:
    with get_session() as session:
        run = AgentRun(
            status=State.START,
        )
        
        session.add(run)
        session.commit()
        session.refresh(run)
        return run.run_id

def get_run(run_id: UUID) -> AgentRun:
    with get_session() as session:
        run = session.get(AgentRun,run_id)
        if not run:
            raise ValueError("Run not Found")
        return run

def set_run(run_id:UUID,status: State) -> None:
    with get_session() as session:
        run = session.get(AgentRun,run_id)
        if not run:
            raise ValueError("Run not found")
        run.status = status
        session.commit()

def add_run_iter(run_id:UUID) -> None:
    with get_session() as session:
        run = session.get(AgentRun,run_id)
        if not run:
            raise ValueError("Run not found")
        run.iteration += 1
        session.commit()

def append_event(
    run_id: UUID,
    event_type: str,
    payload: Any
) -> None:
    with get_session() as session:
        event = AgentEvent(
            run_id = run_id,
            sequence = _get_latest_event_sequence(run_id) + 1,
            event_type=event_type,
            payload=json.dumps(payload,default=str)
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        

def get_events(run_id: UUID) -> list[AgentEvent]:
    with get_session() as session:
        get_run(run_id)
        result = session.exec(
            select(AgentEvent)
            .where(AgentEvent.run_id == run_id)
            .order_by(AgentEvent.sequence)
        )
        events = result.all()
        for e in events:
            e.payload = json.loads(e.payload)
        return events      

def _get_latest_event_sequence(run_id: UUID) -> int:
    with get_session() as session:
        get_run(run_id)
        result = session.exec(
            select(AgentEvent)
            .where(AgentEvent.run_id == run_id)
            .order_by(AgentEvent.sequence.desc())
        )
        events = result.first()
        return events.sequence if events else -1

def get_last_events(run_id: UUID, limit: int = 7) -> list[AgentEvent]:
    with Session(engine) as session:
        events = session.exec(
            select(AgentEvent)
            .where(AgentEvent.run_id == run_id)
            .order_by(AgentEvent.sequence.desc())
            .limit(limit)
        ).all()
        for e in events:
            e.payload = json.loads(e.payload)
        return list(reversed(events))

if __name__ == "__main__":
    init_db()
    