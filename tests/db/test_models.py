"""Tests for app/db/models.py — utc_now, model defaults, EventType enum."""

from datetime import datetime, timezone

from app.db.models import Event, EventType, Run, ToolExecution, utc_now
from app.state.state import State


class TestUtcNow:
    def test_returns_utc_datetime(self):
        result = utc_now()
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_returns_recent_time(self):
        before = datetime.now(timezone.utc)
        result = utc_now()
        after = datetime.now(timezone.utc)
        assert before <= result <= after

    def test_returns_utc_timezone(self):
        result = utc_now()
        assert result.tzinfo == timezone.utc


class TestEventType:
    def test_all_expected_types_exist(self):
        expected = [
            "USER_INPUT",
            "MODEL_INPUT",
            "MODEL_OUTPUT",
            "TOOL_CALL",
            "TOOL_RESULT",
            "TOOL_FAILED",
            "SKILL_RECEIVED",
            "ASK_USER",
            "FINAL",
            "REFUSED",
        ]
        for name in expected:
            assert hasattr(EventType, name)

    def test_enum_values_are_strings(self):
        for member in EventType:
            assert isinstance(member.value, str)

    def test_user_input_value(self):
        assert EventType.USER_INPUT.value == "user_input"

    def test_model_input_value(self):
        assert EventType.MODEL_INPUT.value == "model_input"

    def test_model_output_value(self):
        assert EventType.MODEL_OUTPUT.value == "model_output"

    def test_tool_call_value(self):
        assert EventType.TOOL_CALL.value == "tool_call"

    def test_tool_result_value(self):
        assert EventType.TOOL_RESULT.value == "tool_result"

    def test_tool_failed_value(self):
        assert EventType.TOOL_FAILED.value == "tool_failed"

    def test_skill_received_value(self):
        assert EventType.SKILL_RECEIVED.value == "skill_received"

    def test_ask_user_value(self):
        assert EventType.ASK_USER.value == "ask_user"

    def test_final_value(self):
        assert EventType.FINAL.value == "final"

    def test_refused_value(self):
        assert EventType.REFUSED.value == "refused"

    def test_count(self):
        assert len(EventType) == 11


class TestRunModel:
    def test_construction_with_state(self):
        run = Run(state=State.START)
        assert run.state == State.START
        assert run.final_response is None
        assert run.error is None

    def test_state_field_accepts_string(self):
        run = Run(state="model_call")
        assert run.state == "model_call"


class TestEventModel:
    def test_construction(self):
        event = Event(
            run_id=None,
            event_type=EventType.USER_INPUT,
            payload={"input": "hi"},
            sequence=1,
        )
        assert event.event_type == EventType.USER_INPUT
        assert event.payload == {"input": "hi"}
        assert event.sequence == 1


class TestToolExecutionModel:
    def test_construction(self):
        te = ToolExecution(tool_name="x:y", arguments={"a": 1})
        assert te.tool_name == "x:y"
        assert te.arguments == {"a": 1}
        assert te.success is False
        assert te.result is None
        assert te.error is None
        assert te.completed_at is None
