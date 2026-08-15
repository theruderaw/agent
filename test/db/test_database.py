from app.db.database import (
    append_event,
    create_run,
    get_events,
    get_run,
)


def test_create_run():
    run_id = create_run()

    run = get_run(run_id)

    assert run.run_id == run_id
    assert run.status == "start"


def test_append_and_get_events():
    run_id = create_run()

    append_event(
        run_id=run_id,
        event_type="RUN_STARTED",
        payload="{}",
    )

    append_event(
        run_id=run_id,
        event_type="MODEL_STARTED",
        payload="{}",
    )

    events = get_events(run_id)

    assert len(events) == 2
    assert events[0].sequence == 0
    assert events[0].event_type == "RUN_STARTED"
    assert events[1].sequence == 1
    assert events[1].event_type == "MODEL_STARTED"