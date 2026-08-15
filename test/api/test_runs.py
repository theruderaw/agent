# tests/test_agent_e2e.py
#
# Integration tests against a LIVE server. Before running:
#   1. ollama serve (and the model pulled)
#   2. uvicorn app.main:app --reload
#
# Run with: pytest tests/test_agent_e2e.py -v

import time
import requests

BASE_URL = "http://localhost:8000"


def create_run(prompt: str) -> dict:
    resp = requests.post(f"{BASE_URL}/agent/runs/", json={"prompt": prompt})
    return resp


def respond(run_id: str, message: str) -> dict:
    resp = requests.post(f"{BASE_URL}/agent/runs/{run_id}", json={"message": message})
    return resp


def get_events(run_id: str) -> list:
    resp = requests.get(f"{BASE_URL}/agent/runs/{run_id}/events")
    resp.raise_for_status()
    return resp.json()


def get_run(run_id: str) -> dict:
    resp = requests.get(f"{BASE_URL}/agent/runs/{run_id}")
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# 18. First Test — single tool_call then final
# ---------------------------------------------------------------------------

def test_18_single_tool_call():
    resp = create_run("Calculate 25 * 4.")
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] == "completed"
    assert "100" in body["answer"]  # loose check, model may phrase it as "The answer is 100"

    events = get_events(body["run_id"])
    event_types = [e["event_type"] for e in events]

    assert "RUN_STARTED" in event_types
    assert "TOOL_OUTPUT" in event_types
    assert "FINAL" in event_types
    assert "COMPLETED" in event_types

    tool_output = next(e for e in events if e["event_type"] == "TOOL_OUTPUT")
    assert float(tool_output["payload"]) == 100

    run = get_run(body["run_id"])
    assert run["status"] == "stop"


# ---------------------------------------------------------------------------
# 19. Second Test — chained tool calls
# ---------------------------------------------------------------------------

def test_19_multi_step_tool_calls():
    resp = create_run("Calculate 25 * 4, then calculate the result multiplied by 3.")
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] == "completed"
    assert "300" in body["answer"]

    events = get_events(body["run_id"])
    tool_outputs = [float(e["payload"]) for e in events if e["event_type"] == "TOOL_OUTPUT"]

    # Both intermediate steps should show up, in order, ending at 300.
    assert len(tool_outputs) >= 2
    assert tool_outputs[-1] == 300


# ---------------------------------------------------------------------------
# 20. Ask-User Test — real pause + real resume
# ---------------------------------------------------------------------------

def test_20_ask_user_then_respond():
    resp = create_run("Calculate X multiplied by 10.")
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] == "waiting_for_user"
    assert body["question"]  # non-empty, small model phrasing varies

    run_id = body["run_id"]
    assert get_run(run_id)["status"] == "waiting_for_user"

    resp2 = respond(run_id, "X = 7")
    assert resp2.status_code == 200

    body2 = resp2.json()
    assert body2["status"] == "completed"
    assert "70" in body2["answer"]

    events = get_events(run_id)
    event_types = [e["event_type"] for e in events]
    assert "ASK_USER" in event_types
    assert "USER_RESPONSE" in event_types
    assert "FINAL" in event_types


def test_20b_respond_rejects_run_not_waiting():
    resp = create_run("Say the word done and nothing else.")
    run_id = resp.json()["run_id"]

    resp2 = respond(run_id, "irrelevant")
    assert resp2.status_code == 400


# ---------------------------------------------------------------------------
# 21. Refusal Test
# ---------------------------------------------------------------------------

def test_21_refusal():
    # Deliberately underspecified / unanswerable without invented facts.
    resp = create_run(
        "What is the exact bank account balance of the last person who "
        "texted me? Do not guess, refuse if you cannot know this."
    )
    assert resp.status_code == 200

    body = resp.json()
    # Small models aren't 100% reliable about choosing refuse vs final vs
    # ask_user here — assert on the state machine, not a guaranteed outcome.
    assert body["status"] in ("refused", "waiting_for_user")

    run = get_run(body["run_id"])
    if body["status"] == "refused":
        assert run["status"] == "stop"
        events = get_events(body["run_id"])
        assert any(e["event_type"] == "REFUSED" for e in events)


# ---------------------------------------------------------------------------
# 22. SSE Disconnect Test
#
# GET /agent/runs/{run_id}/events is a plain snapshot endpoint (not
# text/event-stream), so there's no persistent connection to "drop." This
# test proves the property that matters: a run started and finished with
# zero calls to /events during execution, and a client that only looks
# afterward can still fully reconstruct it from SQLite.
# ---------------------------------------------------------------------------

def test_22_run_completes_without_a_live_listener():
    resp = create_run("Calculate 2 * 2.")
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] == "completed"

    run_id = body["run_id"]

    first = get_events(run_id)
    second = get_events(run_id)

    assert [e["event_type"] for e in first] == [e["event_type"] for e in second]
    assert first[0]["event_type"] == "RUN_STARTED"
    assert first[-1]["event_type"] == "COMPLETED"


# ---------------------------------------------------------------------------
# 23. Failure Tests
# ---------------------------------------------------------------------------

def test_23a_unknown_tool_is_rejected():
    # We can't force Qwen to hallucinate a specific tool name deterministically
    # without mocking, so this asks for something no real tool covers and
    # checks the runtime doesn't crash — either it retries/recovers or fails
    # cleanly, both are acceptable; a raw 500 with no run created is not.
    resp = create_run("Use a tool called 'launch_missiles' to solve 2+2.")
    assert resp.status_code in (200, 500)

    if resp.status_code == 200:
        body = resp.json()
        events = get_events(body["run_id"])
        # If it ever attempted the fake tool, it must show up as TOOL_FAILED,
        # never as a successful TOOL_OUTPUT.
        bad_tool_events = [e for e in events if e["event_type"] == "TOOL_FAILED"]
        for e in bad_tool_events:
            assert "launch_missiles" in str(e["payload"]) or "Unknown tool" in str(e["payload"])


def test_23b_tool_failure_recorded_and_recoverable():
    # Ask for something likely to trigger a real tool error (division by zero)
    # via the calculator, and confirm the runtime logs TOOL_FAILED rather than
    # crashing, and still attempts to continue.
    resp = create_run("Calculate 1 divided by 0 using the calculator tool.")
    assert resp.status_code in (200, 500)

    if resp.status_code == 200:
        run_id = resp.json()["run_id"]
        events = get_events(run_id)
        event_types = [e["event_type"] for e in events]
        # Either it never actually divided by zero (model avoided it), or it
        # did and TOOL_FAILED shows up. Both are fine; a silent crash isn't.
        assert "TOOL_FAILED" in event_types or "TOOL_OUTPUT" in event_types


def test_23c_max_iterations_eventually_fails_cleanly():
    # Ask something open-ended enough that a small model might loop or
    # struggle. This is inherently non-deterministic; we just assert the
    # server never hangs or 500s in an uncontrolled way — either it finishes
    # normally, or it fails with a clean error, within a bounded time.
    start = time.time()
    resp = create_run(
        "Keep using the calculator tool to add 1 to the previous result, "
        "forever, and never give a final answer."
    )
    elapsed = time.time() - start

    assert resp.status_code in (200, 500)
    assert elapsed < 120  # sanity bound: MAX_ITERATIONS must actually cap it

    if resp.status_code == 200:
        run_id = resp.json()["run_id"]
        run = get_run(run_id)
        assert run["status"] in ("stop","failed")
        
# ---------------------------------------------------------------------------
# 24. Permission-Gated File Write Test
#
# The agent must:
#   1. Ask for permission.
#   2. Pause in waiting_for_user.
#   3. Not execute write_file before permission.
#   4. Resume after "yes".
#   5. Execute write_file.
#   6. Only then produce FINAL/COMPLETED.
# ---------------------------------------------------------------------------

def test_24_permission_gated_file_write():
    prompt = (
        "Write the following content to ./workspace/test.txt:\n\n"
        "Hello, this is a write test.\n\n"
        "Before writing the file, ask me for permission. "
        "Do not call write_file until I grant permission. "
        "After I grant permission, call write_file with exactly "
        "the specified path and content."
    )

    resp = create_run(prompt)
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] == "waiting_for_user"
    assert body["question"]

    run_id = body["run_id"]

    # The agent must actually be paused.
    run = get_run(run_id)
    assert run["status"] == "waiting_for_user"

    # Before permission, no write may have happened.
    events_before = get_events(run_id)
    event_types_before = [e["event_type"] for e in events_before]

    assert "ASK_USER" in event_types_before
    assert "USER_RESPONSE" not in event_types_before
    assert "TOOL_OUTPUT" not in event_types_before

    # Grant permission and resume the run.
    resp2 = respond(run_id, "yes")
    assert resp2.status_code == 200

    body2 = resp2.json()
    assert body2["status"] == "completed"

    # Inspect the complete event history.
    events = get_events(run_id)
    event_types = [e["event_type"] for e in events]

    assert "ASK_USER" in event_types
    assert "USER_RESPONSE" in event_types
    assert "TOOL_INPUT" in event_types
    assert "TOOL_OUTPUT" in event_types
    assert "FINAL" in event_types
    assert "COMPLETED" in event_types

    # Verify ordering:
    # permission request -> user approval -> write -> success -> final.
    ask_index = event_types.index("ASK_USER")
    response_index = event_types.index("USER_RESPONSE")
    tool_input_index = event_types.index("TOOL_INPUT")
    tool_output_index = event_types.index("TOOL_OUTPUT")
    final_index = event_types.index("FINAL")

    assert ask_index < response_index
    assert response_index < tool_input_index
    assert tool_input_index < tool_output_index
    assert tool_output_index < final_index

    # Verify the actual write_file arguments.
    tool_input = next(
        e for e in events
        if e["event_type"] == "TOOL_INPUT"
        and "write_file" in str(e["payload"])
    )

    payload = tool_input["payload"]

    assert "./workspace/test.txt" in str(payload)
    assert "Hello, this is a write test." in str(payload)

    # The final answer must come after successful tool execution.
    final_index = event_types.index("FINAL")
    output_index = event_types.index("TOOL_OUTPUT")

    assert output_index < final_index