# Agent System — Implementation Specification

## A. Core architecture

### 1. Project structure

Target:

```
app/
├── agent/
│   ├── __init__.py
│   └── models.py
├── api/
│   ├── __init__.py
│   └── ...
├── db/
│   ├── __init__.py
│   ├── database.py
│   ├── models.py
│   └── repository.py
├── llm/
│   ├── __init__.py
│   ├── base.py
│   └── qwen.py
├── runtime/
│   ├── __init__.py
│   ├── context.py
│   ├── runtime.py
│   └── worker.py
├── state/
│   ├── __init__.py
│   └── state.py
└── tools/
    ├── __init__.py
    ├── base.py
    ├── registry.py
    └── ...
```

Tests mirror the architecture.

---

## B. Agent domain

### 2. Agent actions

Keep the current discriminated union:

```
tool_call
skill_request
ask_user
final
refuse
```

No additional action types unless a concrete runtime requirement appears.

### 3. Action validation

All model output must pass through:

```
raw LLM output
        ↓
JSON parsing
        ↓
TypeAdapter(AgentAction)
        ↓
validated AgentAction
```

Invalid model output is a runtime error, not silently accepted.

### 4. State machine

Keep the current states:

```
START
MODEL_CALL
MODEL_OUTPUT

SKILL_REQUESTED
SKILL_RECEIVED

TOOL_CALL
TOOL_RESULT
TOOL_FAILED

WAITING_FOR_USER

FINAL
REFUSED

STOP
FAILED
```

### 5. State transitions

`next_state()` remains a pure function.

It must:

- not access DB
- not call LLM
- not execute tools
- not mutate context
- not perform I/O

### 6. State-machine tests

Every valid transition gets a test.

Every invalid transition gets a test.

Current 20 tests become the baseline.

---

# C. Persistence

### 7. Database

Use:

```
PostgreSQL
SQLAlchemy 2.x
psycopg 3
Alembic
```

Everything application-facing is async.

### 8. Async engine

Use:

```
AsyncEngine
AsyncSession
async_sessionmaker
```

No synchronous DB calls inside the runtime.

### 9. Run model

Create a `runs` table containing at minimum:

```
id
state
created_at
updated_at
final_response
error
```

Potentially:

```
user_id
metadata
```

later.

### 10. Event model

Create an append-only `events` table:

```
id
run_id
event_type
payload
created_at
```

Events provide the execution history.

### 11. Tool execution model

Create `tool_executions`:

```
id
run_id
tool_name
arguments
result
success
error
started_at
completed_at
```

This makes tool execution independently observable.

### 12. Database constraints

Enforce:

```
events.run_id → runs.id
tool_executions.run_id → runs.id
```

Use UUIDs for run/entity IDs.

Add appropriate indexes on:

```
events(run_id, created_at)
tool_executions(run_id, started_at)
runs(state)
```

### 13. Migrations

All schema changes go through Alembic.

No manual production schema manipulation.

---

# D. Repository

### 14. Repository boundary

Create:

```
app/db/repository.py
```

The runtime interacts with the repository rather than SQLAlchemy directly.

### 15. Repository operations

Minimum:

```
create_run()
get_run()
update_run_state()
set_final_response()
set_run_failed()

append_event()
get_events()

create_tool_execution()
complete_tool_execution()
```

### 16. Repository transactions

Operations that modify multiple records must use a transaction.

For example:

```
tool completes
    ↓
tool_execution updated
    ↓
event appended
    ↓
run state updated
```

These should be atomic where appropriate.

---

# E. Runtime context

### 17. RunContext

Create an in-memory representation of an executing run:

```
RunContext
├── run_id
├── state
├── current_action
├── messages
├── loaded_skills
├── tool_result
└── final_response
```

It represents **the current execution**, not the persistence layer.

### 18. Context loading

Runtime starts by:

```
run_id
 ↓
repository.get_run()
 ↓
construct RunContext
```

### 19. Context persistence

State changes are persisted after meaningful transitions.

The DB remains the durable source of truth.

---

# F. Runtime

### 20. Runtime loop

The runtime is responsible for executing the state machine:

```
load context
    ↓
inspect state
    ↓
perform state operation
    ↓
persist event/state
    ↓
calculate next state
    ↓
repeat
```

### 21. MODEL_CALL

Runtime:

1. builds model input
2. calls LLM asynchronously
3. records model input event
4. records model output event
5. transitions to `MODEL_OUTPUT`

### 22. MODEL_OUTPUT

Runtime validates the model response:

```
LLM output
 ↓
AgentAction
 ↓
next_state()
```

Then dispatches based on action.

### 23. Tool execution

For `ToolCall`:

```
MODEL_OUTPUT
 ↓
TOOL_CALL
 ↓
registry lookup
 ↓
validate arguments
 ↓
execute
 ↓
TOOL_RESULT / TOOL_FAILED
```

### 24. Tool failures

Tool failure is recoverable.

Record:

```
tool execution
error
event
```

Then return control to the model:

```
TOOL_FAILED → MODEL_CALL
```

The model gets the failure information.

---

# G. Skills

### 25. Skill loader

Create a skill subsystem capable of:

```
skill name
 ↓
locate skill
 ↓
load markdown
 ↓
validate existence
 ↓
return skill content
```

### 26. Skill lifecycle

Current state flow:

```
MODEL_OUTPUT
 ↓
SKILL_REQUESTED
 ↓
load skill
 ↓
SKILL_RECEIVED
 ↓
MODEL_CALL
```

Skill loading failure becomes an explicit runtime failure.

### 27. Skill isolation

Skills provide **instructions/context**, not arbitrary execution.

Tools provide execution capabilities.

Keep those concepts separate.

---

# H. Tools

### 28. Tool abstraction

Every tool exposes:

```
name
description
parameters/schema
execute()
```

### 29. Tool registry

Registry provides:

```
register()
get()
list()
schemas()
```

The model receives tool schemas generated from the registry.

### 30. Parameterized tools

Do not hardcode tool arguments into the runtime.

The flow should be:

```
LLM
 ↓
tool name + arguments
 ↓
registry
 ↓
tool
 ↓
Pydantic validation
 ↓
execute
```

This lets you grow from the current 12 tools toward the larger tool set without changing runtime architecture.

---

# I. LLM

### 31. LLM abstraction

Create an interface such as:

```
LLM
├── generate()
└── ...
```

The runtime should depend on this interface, **not Qwen directly**.

### 32. Qwen adapter

`app/llm/qwen.py` handles:

```
HTTP/Ollama communication
timeouts
response extraction
errors
```

The runtime receives a model response, not an Ollama-specific response object.

### 33. Async LLM calls

Use async HTTP.

Set explicit:

```
connect timeout
read timeout
write timeout
```

Don't allow indefinite model calls.

---

# J. Background execution

### 34. Worker boundary

Create:

```
app/runtime/worker.py
```

with something conceptually like:

```python
async def execute_run(run_id):
    ...
```

The worker calls the runtime.

### 35. API/background separation

The API should create/queue runs.

It should **not contain the agent loop**.

Architecture:

```
HTTP request
    ↓
create Run
    ↓
enqueue run
    ↓
return run_id
```

Worker:

```
run_id
 ↓
runtime
 ↓
agent execution
```

### 36. Initial worker implementation

Start with a simple async worker mechanism during development.

Do **not** introduce Celery/Redis until the runtime itself works.

Later:

```
Redis
 ↓
Celery worker
 ↓
execute_run()
```

The runtime shouldn't need to change.

---

# K. API

### 37. Run creation

Expose something like:

```
POST /runs
```

Creates a persisted run and schedules execution.

### 38. Run inspection

```
GET /runs/{run_id}
```

Returns:

```
state
created_at
updated_at
final_response
error
```

### 39. Event inspection

```
GET /runs/{run_id}/events
```

Returns execution history.

### 40. User continuation

For:

```
WAITING_FOR_USER
```

provide an endpoint such as:

```
POST /runs/{run_id}/input
```

The response becomes an event/input and resumes the run.

---

# L. Testing

### 41. Unit tests

Test independently:

```
state
actions
tools
registry
skills
repository
context
```

### 42. Runtime tests

Mock the LLM and tools.

Test complete paths:

```
prompt
 ↓
tool_call
 ↓
tool result
 ↓
final
```

and:

```
prompt
 ↓
skill request
 ↓
skill
 ↓
tool
 ↓
final
```

### 43. Failure tests

Explicitly test:

```
invalid LLM JSON
invalid AgentAction
unknown tool
invalid tool arguments
tool failure
skill missing
LLM timeout
DB failure
runtime exception
```

### 44. Integration tests

Use a real test database and test:

```
API
 ↓
DB
 ↓
worker
 ↓
runtime
 ↓
mocked LLM
 ↓
tool
```

---

# M. Operational requirements

### 45. Event logging

Every important execution step should produce an event.

Don't rely exclusively on application logs.

### 46. Run recovery

A run must be inspectable after process death.

The DB should tell you:

```
what state it reached
what tool was running
what happened before failure
```

### 47. Idempotency

Tool execution and run processing should eventually account for duplicate worker execution.

This becomes especially important once Redis/Celery is introduced.

### 48. Concurrency

Prevent two workers from simultaneously advancing the same run.

Use DB-level locking/claiming rather than trusting application-level flags.

### 49. Configuration

Move infrastructure configuration to environment variables:

```
DATABASE_URL
OLLAMA_URL
OLLAMA_MODEL
timeouts
worker settings
```

No credentials or machine-specific paths in source.

### 50. Definition of done

The first real version is complete when this works:

```
POST /runs
       ↓
persist Run
       ↓
worker picks Run
       ↓
MODEL_CALL
       ↓
MODEL_OUTPUT
       ↓
Qwen returns AgentAction
       ↓
tool / skill / user / final
       ↓
persist every meaningful event
       ↓
repeat
       ↓
FINAL / REFUSED
       ↓
STOP
```

with the entire run recoverable from PostgreSQL.

---