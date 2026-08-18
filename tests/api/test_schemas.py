"""Tests for app/api/schemas.py — Pydantic schemas."""

from datetime import datetime, timezone
from uuid import uuid4

from app.api.schemas import (
    EventListResponse,
    EventResponse,
    RunCreate,
    RunResponse,
    UserInputRequest,
    UserInputResponse,
)


class TestRunCreate:
    def test_construction(self):
        rc = RunCreate()
        assert rc.model_dump() == {}


class TestRunResponse:
    def test_construction(self):
        now = datetime.now(timezone.utc)
        rr = RunResponse(
            run_id=uuid4(),
            state="model_call",
            created_at=now,
            updated_at=now,
        )
        assert rr.state == "model_call"
        assert rr.final_response is None
        assert rr.error is None

    def test_with_optional_fields(self):
        now = datetime.now(timezone.utc)
        rr = RunResponse(
            run_id=uuid4(),
            state="final",
            created_at=now,
            updated_at=now,
            final_response="done",
            error=None,
        )
        assert rr.final_response == "done"
        assert rr.error is None

    def test_with_error(self):
        now = datetime.now(timezone.utc)
        rr = RunResponse(
            run_id=uuid4(),
            state="failed",
            created_at=now,
            updated_at=now,
            error="something broke",
        )
        assert rr.error == "something broke"

    def test_missing_required_field_raises(self):
        import pytest
        with pytest.raises(Exception):
            RunResponse(state="x")  # missing run_id, created_at, updated_at


class TestEventResponse:
    def test_construction(self):
        now = datetime.now(timezone.utc)
        er = EventResponse(
            event_type="user_input",
            payload={"input": "hi"},
            sequence=1,
            created_at=now,
        )
        assert er.event_type == "user_input"
        assert er.payload == {"input": "hi"}
        assert er.sequence == 1


class TestEventListResponse:
    def test_construction(self):
        elr = EventListResponse(events=[])
        assert elr.events == []

    def test_with_events(self):
        now = datetime.now(timezone.utc)
        er = EventResponse(
            event_type="final",
            payload={"content": "done"},
            sequence=5,
            created_at=now,
        )
        elr = EventListResponse(events=[er])
        assert len(elr.events) == 1


class TestUserInputRequest:
    def test_construction(self):
        req = UserInputRequest(input="hello")
        assert req.input == "hello"

    def test_missing_input_raises(self):
        import pytest
        with pytest.raises(Exception):
            UserInputRequest()


class TestUserInputResponse:
    def test_construction(self):
        resp = UserInputResponse(run_id=uuid4(), state="waiting_for_user")
        assert resp.state == "waiting_for_user"
