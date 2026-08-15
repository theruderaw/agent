# agent-poc

A small tool-using LLM agent, backed by a local [Ollama](https://ollama.com) model
(Qwen 2.5 Coder), a FastAPI HTTP layer, and a SQLite-backed run/event log.

The agent runs a strict loop: on each turn the model must emit exactly one
JSON action — `tool_call`, `ask_user`, `refuse`, or `final` — validated
against a Pydantic schema. Every transition is persisted as an event, so a
run's full reasoning trace can be replayed from the database.

## Architecture

```
app/
  agent/
    runtime.py      # the core loop: prompt -> model -> action -> (tool | pause | stop)
    models.py        # AgentAction schema (tool_call / ask_user / refuse / final)
    state.py         # State enum + state machine transitions
    registry.py       # maps tool names -> callables
    llms/qwen.py      # Ollama client wrapper (system prompt, decoding options)
    tools/            # calculator, filesystem (read/write), get_time, hcf/lcm
  api/
    main.py           # FastAPI app, mounts the runs router + static/
    features/runs.py  # POST /agent/runs, GET/POST .../{run_id}, .../events
  db/
    database.py        # SQLModel session helpers (create_run, append_event, ...)
    models.py           # AgentRun, AgentEvent tables
  prompts/
    sys_prompt_test.py  # the system prompt the model is run under
static/index.html        # minimal frontend served at /
workspace/                # sandbox directory the read_file/write_file tools operate in
```

### The agent loop (`runtime.py`)

Each iteration:

1. Build a prompt (original task + recent event context) and call the model.
2. Parse the response into an `AgentAction`. Invalid JSON gets fed back to
   the model as an error and retried, up to `MAX_ITERATIONS` (15).
3. Dispatch on `action.action`:
   - **`tool_call`** — look up the tool by name, run it, append the result
     as context, and loop again. Unknown tools and tool exceptions are
     reported back to the model rather than crashing the run.
   - **`final`** — persist the answer, mark the run `stop`, and return.
   - **`ask_user`** — persist the question, mark the run `waiting_for_user`,
     and return immediately (this pauses the run rather than ending it).
   - **`refuse`** — persist the reason, mark the run `stop`, and return.
4. If `MAX_ITERATIONS` is exceeded without a terminal action, the run is
   marked `failed` and a `ValueError` is raised.

`run_agent(prompt)` starts a new run; `resume_agent(run_id, message)`
continues a run that's sitting in `waiting_for_user`, re-injecting the
original task, the question that was asked, and the user's answer.

### Available tools

| Tool | Arguments | Notes |
|---|---|---|
| `calculator` | `expression`, `precise?` | Evaluates a basic arithmetic expression |
| `read_file` | `path` | Relative to the project root; path-traversal is blocked |
| `write_file` | `path`, `data` | Creates or overwrites; same traversal guard |
| `get_time` | — | Returns current UTC time |

Tools are registered in `app/agent/registry.py`; `TOOL_NAMES` in
`app/agent/tools/__init__.py` is asserted to match the registry at import
time, so adding a tool in one place and forgetting the other fails fast.

## Setup

1. **Install Python deps**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Install and run Ollama**, then pull the models referenced in `.env`:

   ```bash
   ollama serve
   ollama pull qwen2.5-coder:3b
   ollama pull qwen2.5-coder:7b
   ```

3. **Configure `.env`** (not committed — see `.gitignore`):

   ```
   PRIMARY_MODEL=qwen2.5-coder:3b
   SECONDARY_MODEL=qwen2.5-coder:7b
   ```

   `call_qwen(prompt, thinking=True)` uses `SECONDARY_MODEL` by default and
   `PRIMARY_MODEL` when `thinking=False`.

4. **Run the API server**

   ```bash
   uvicorn app.api.main:app --reload
   ```

   This serves the agent endpoints under `/agent/runs` and the static
   frontend at `/`. `init_db()` runs on startup and creates `agent.db`
   (a local SQLite file — gitignored, safe to delete to reset all history).

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/agent/runs/` | Start a run: `{"prompt": "..."}` |
| `GET` | `/agent/runs/` | List all runs |
| `GET` | `/agent/runs/{run_id}` | Get a run's status |
| `GET` | `/agent/runs/{run_id}/events` | Get a run's full event trace (`?reverse=true` to flip order) |
| `POST` | `/agent/runs/{run_id}` | Resume a run waiting on `ask_user`: `{"message": "..."}` |

A run response looks like:

```json
{
  "run_id": "...",
  "status": "completed",       // or "waiting_for_user" / "refused"
  "answer": "...",              // present when completed
  "question": "...",            // present when waiting_for_user
  "reason": "..."                // present when refused
}
```

## Tests

Tests live under `test/`, split by how much live infrastructure they need.

```bash
pytest                     # everything
pytest test/agent/test_state.py test/agent/test_tools.py test/db/  # fast, no LLM/server needed
pytest test/agent/test_runtime.py -k unit   # mocked runtime tests, no live model
```

- **Pure unit tests** (`test/agent/test_state.py`, `test/agent/test_tools.py`,
  `test/db/test_database.py`, and the `test_unit_*` cases in
  `test/agent/test_runtime.py`) — deterministic, mock `call_qwen`, no Ollama
  or running server required.
- **Real-model tests** (most of `test/agent/test_runtime.py`,
  `test/agent/test_qwen.py`) — call the actual local model via Ollama.
  Requires `ollama serve` and the models pulled per Setup above. Since these
  hit a real LLM, expect occasional non-determinism even with the pinned
  decoding options in `qwen.py` (`temperature=0.2`, `seed=0`).
- **Integration tests** (`test/api/test_runs.py`) — hit a live HTTP server.
  Requires **both** `ollama serve` and `uvicorn app.api.main:app --reload`
  running at `http://localhost:8000` before running this file.

## Known rough edges

- No `.env` validation on startup — a missing/misspelled model name in
  `.env` fails inside the Ollama call rather than at startup.
- `runtime.py` uses `print()` for debug output instead of structured
  logging.
- `agent.db` and `.env` were previously committed to git; they've been
  removed from tracking (see `.gitignore`) but still exist in git history.