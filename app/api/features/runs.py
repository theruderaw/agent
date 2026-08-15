from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.agent.runtime import run_agent, resume_agent
from app.db.database import get_events, get_session, get_run
from app.db.models import AgentRun


router = APIRouter(
    prefix="/agent/runs",
    tags=["Runs"]
)


class RunRequest(BaseModel):
    prompt: str


class UserAction(BaseModel):
    message: str


class RunResponse(BaseModel):
    run_id: UUID
    status: Literal["completed", "waiting_for_user", "refused"]
    answer: str | None = None
    question: str | None = None
    reason: str | None = None


def _to_run_response(run_id: UUID, result) -> RunResponse:
    if isinstance(result, str):
        return RunResponse(run_id=run_id, status="completed", answer=result)

    if result.action == "ask_user":
        return RunResponse(run_id=run_id, status="waiting_for_user", question=result.question)

    if result.action == "refuse":
        return RunResponse(run_id=run_id, status="refused", reason=result.reason)

    raise HTTPException(500, f"Unexpected agent result: {result!r}")


@router.post('/', response_model=RunResponse)
def add_run(
    payload: RunRequest,
):
    try:
        run_id, result = run_agent(payload.prompt)
    except ValueError as e:
        raise HTTPException(500, str(e))

    return _to_run_response(run_id, result)

@router.get('/')
def get_runs(
    session: Session = Depends(get_session)
):
    res = session.exec(
        select(AgentRun)
        .order_by(AgentRun.created_at.desc())
    )

    return res.all()


@router.get("/{run_id}")
def get_run_by_id(
    run_id: UUID
):
    try:
        return get_run(run_id)
    except ValueError:
        raise HTTPException(404, "Run not found")


@router.get("/{run_id}/events")
def get_events_by_run(
    run_id: UUID,
    reverse: bool = Query(default=False)
):
    try:
        res = get_events(
            run_id=run_id
        )
        return res if not reverse else res[::-1]
    except ValueError:
        raise HTTPException(404, "Run not found")
    
@router.post("/{run_id}")
def respond(run_id: UUID,payload: UserAction):
    try:
        run_id, result = resume_agent(run_id, payload.message)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return _to_run_response(run_id, result)