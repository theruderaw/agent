from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.schemas import (
    EventListResponse,
    EventResponse,
    RunCreate,
    RunResponse,
    UserInputRequest,
    UserInputResponse,
)
from app.db.database import get_session
from app.db.repository import EventRepository, RunRepository
from app.state.state import State
from app.worker.tasks import execute_run_task

router = APIRouter()


@router.post("/runs", response_model=RunResponse, status_code=201)
async def create_run(
    _body: RunCreate | None = None,
    session: AsyncSession = Depends(get_session),
):
    repo = RunRepository(session)
    run_id = await repo.create()
    await session.commit()

    execute_run_task.delay(str(run_id))

    run = await repo.get(run_id)
    return RunResponse(
        run_id=run.id,
        state=run.state,
        created_at=run.created_at,
        updated_at=run.updated_at,
        final_response=run.final_response,
        error=run.error,
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    repo = RunRepository(session)
    try:
        run = await repo.get(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found")

    return RunResponse(
        run_id=run.id,
        state=run.state,
        created_at=run.created_at,
        updated_at=run.updated_at,
        final_response=run.final_response,
        error=run.error,
    )


@router.get("/runs/{run_id}/events", response_model=EventListResponse)
async def get_events(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    run_repo = RunRepository(session)
    try:
        await run_repo.get(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found")

    event_repo = EventRepository(session)
    events = await event_repo.get(run_id)

    return EventListResponse(
        events=[
            EventResponse(
                event_type=e.event_type,
                payload=e.payload,
                sequence=e.sequence,
                created_at=e.created_at,
            )
            for e in events
        ]
    )


@router.post("/runs/{run_id}/input", response_model=UserInputResponse)
async def send_user_input(
    run_id: UUID,
    body: UserInputRequest,
    session: AsyncSession = Depends(get_session),
):
    repo = RunRepository(session)
    try:
        run = await repo.get(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.state != State.WAITING_FOR_USER:
        raise HTTPException(
            status_code=409,
            detail=f"Run is in state '{run.state}', not waiting for user input",
        )

    execute_run_task.delay(str(run_id), user_input=body.input)

    run = await repo.get(run_id)
    return UserInputResponse(
        run_id=run.id,
        state=run.state,
    )
