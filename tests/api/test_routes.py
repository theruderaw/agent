"""Tests for app/api/routes.py — all 4 endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models import EventType, Run
from app.state.state import State


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _make_run(state=State.START, final_response=None, error=None):
    run = Run()
    run.id = uuid4()
    run.state = state
    run.final_response = final_response
    run.error = error
    run.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    run.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return run


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


# ─────────────────────────────────────────────
# POST /runs
# ─────────────────────────────────────────────


class TestCreateRun:
    @pytest.mark.asyncio
    async def test_create_run_201(self, mock_session):
        from app.api.routes import create_run

        run = _make_run()

        with (
            patch("app.api.routes.RunRepository") as MockRepo,
            patch("app.api.routes.execute_run_task") as mock_task,
        ):
            MockRepo.return_value.create = AsyncMock(return_value=run)

            result = await create_run(session=mock_session)

        assert result.run_id == run.id
        assert result.state == "start"
        mock_task.delay.assert_called_once_with(str(run.id))

    @pytest.mark.asyncio
    async def test_create_run_commits(self, mock_session):
        from app.api.routes import create_run

        run = _make_run()

        with (
            patch("app.api.routes.RunRepository") as MockRepo,
            patch("app.api.routes.execute_run_task"),
        ):
            MockRepo.return_value.create = AsyncMock(return_value=run)

            await create_run(session=mock_session)

        mock_session.commit.assert_awaited_once()


# ─────────────────────────────────────────────
# GET /runs/{run_id}
# ─────────────────────────────────────────────


class TestGetRun:
    @pytest.mark.asyncio
    async def test_get_run_success(self, mock_session):
        from app.api.routes import get_run

        run = _make_run(state=State.MODEL_CALL, final_response="done")

        with patch("app.api.routes.RunRepository") as MockRepo:
            MockRepo.return_value.get = AsyncMock(return_value=run)

            result = await get_run(run_id=run.id, session=mock_session)

        assert result.run_id == run.id
        assert result.state == "model_call"
        assert result.final_response == "done"

    @pytest.mark.asyncio
    async def test_get_run_not_found_404(self, mock_session):
        from app.api.routes import get_run

        with patch("app.api.routes.RunRepository") as MockRepo:
            MockRepo.return_value.get = AsyncMock(side_effect=ValueError("Run not found"))

            with pytest.raises(HTTPException) as exc_info:
                await get_run(run_id=uuid4(), session=mock_session)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_run_with_error(self, mock_session):
        from app.api.routes import get_run

        run = _make_run(state=State.FAILED, error="something broke")

        with patch("app.api.routes.RunRepository") as MockRepo:
            MockRepo.return_value.get = AsyncMock(return_value=run)

            result = await get_run(run_id=run.id, session=mock_session)

        assert result.state == "failed"
        assert result.error == "something broke"


# ─────────────────────────────────────────────
# GET /runs/{run_id}/events
# ─────────────────────────────────────────────


class TestGetEvents:
    @pytest.mark.asyncio
    async def test_get_events_success(self, mock_session):
        from app.api.routes import get_events

        run = _make_run()
        events = [
            MagicMock(
                event_type=EventType.USER_INPUT,
                payload={"input": "hi"},
                sequence=1,
                created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
            MagicMock(
                event_type=EventType.MODEL_OUTPUT,
                payload={"content": "{}"},
                sequence=2,
                created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
        ]

        with (
            patch("app.api.routes.RunRepository") as MockRunRepo,
            patch("app.api.routes.EventRepository") as MockEventRepo,
        ):
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockEventRepo.return_value.get = AsyncMock(return_value=events)

            result = await get_events(run_id=run.id, session=mock_session)

        assert len(result.events) == 2
        assert result.events[0].event_type == "user_input"
        assert result.events[0].sequence == 1

    @pytest.mark.asyncio
    async def test_get_events_run_not_found_404(self, mock_session):
        from app.api.routes import get_events

        with patch("app.api.routes.RunRepository") as MockRepo:
            MockRepo.return_value.get = AsyncMock(side_effect=ValueError("Run not found"))

            with pytest.raises(HTTPException) as exc_info:
                await get_events(run_id=uuid4(), session=mock_session)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_events_empty(self, mock_session):
        from app.api.routes import get_events

        run = _make_run()

        with (
            patch("app.api.routes.RunRepository") as MockRunRepo,
            patch("app.api.routes.EventRepository") as MockEventRepo,
        ):
            MockRunRepo.return_value.get = AsyncMock(return_value=run)
            MockEventRepo.return_value.get = AsyncMock(return_value=[])

            result = await get_events(run_id=run.id, session=mock_session)

        assert result.events == []


# ─────────────────────────────────────────────
# POST /runs/{run_id}/input
# ─────────────────────────────────────────────


class TestSendUserInput:
    @pytest.mark.asyncio
    async def test_send_input_success(self, mock_session):
        from app.api.routes import send_user_input
        from app.api.schemas import UserInputRequest

        run = _make_run(state=State.WAITING_FOR_USER)

        with (
            patch("app.api.routes.RunRepository") as MockRepo,
            patch("app.api.routes.EventRepository") as MockEventRepo,
            patch("app.api.routes.execute_run_task") as mock_task,
        ):
            MockRepo.return_value.get = AsyncMock(return_value=run)
            MockEventRepo.return_value.append = AsyncMock()

            body = UserInputRequest(input="hello agent")
            result = await send_user_input(run_id=run.id, body=body, session=mock_session)

        assert result.run_id == run.id
        assert result.state == "model_call"
        mock_task.delay.assert_called_once_with(str(run.id), user_input="hello agent")
        MockEventRepo.return_value.append.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_input_not_waiting_409(self, mock_session):
        from app.api.routes import send_user_input
        from app.api.schemas import UserInputRequest

        run = _make_run(state=State.MODEL_CALL)

        with patch("app.api.routes.RunRepository") as MockRepo:
            MockRepo.return_value.get = AsyncMock(return_value=run)

            body = UserInputRequest(input="hello")
            with pytest.raises(HTTPException) as exc_info:
                await send_user_input(run_id=run.id, body=body, session=mock_session)

        assert exc_info.value.status_code == 409
        assert "model_call" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_send_input_run_not_found_404(self, mock_session):
        from app.api.routes import send_user_input
        from app.api.schemas import UserInputRequest

        with patch("app.api.routes.RunRepository") as MockRepo:
            MockRepo.return_value.get = AsyncMock(side_effect=ValueError("Run not found"))

            body = UserInputRequest(input="x")
            with pytest.raises(HTTPException) as exc_info:
                await send_user_input(run_id=uuid4(), body=body, session=mock_session)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_send_input_from_final_state_409(self, mock_session):
        from app.api.routes import send_user_input
        from app.api.schemas import UserInputRequest

        run = _make_run(state=State.FINAL)

        with patch("app.api.routes.RunRepository") as MockRepo:
            MockRepo.return_value.get = AsyncMock(return_value=run)

            body = UserInputRequest(input="hi")
            with pytest.raises(HTTPException) as exc_info:
                await send_user_input(run_id=run.id, body=body, session=mock_session)

        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_send_input_from_failed_state_409(self, mock_session):
        from app.api.routes import send_user_input
        from app.api.schemas import UserInputRequest

        run = _make_run(state=State.FAILED)

        with patch("app.api.routes.RunRepository") as MockRepo:
            MockRepo.return_value.get = AsyncMock(return_value=run)

            body = UserInputRequest(input="hi")
            with pytest.raises(HTTPException) as exc_info:
                await send_user_input(run_id=run.id, body=body, session=mock_session)

        assert exc_info.value.status_code == 409
