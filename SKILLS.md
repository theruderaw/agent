# Agent System Development

Use this skill when implementing, debugging, or modifying an agent system.

## Development approach

Inspect the existing implementation before making changes.

Trace definitions, references, and callers with code search and LSP when useful.

Prefer existing abstractions and conventions over introducing new ones.

Make the smallest change that satisfies the task.

## Architecture

Keep these concerns separate:

```text
agent   → actions and domain models
state   → state transitions
runtime → execution
tools   → executable capabilities
skills  → instructions and context
llm     → model abstraction
db      → persistence
api     → external interface
```

Do not duplicate responsibilities across these boundaries.

## State machine

Keep state transitions deterministic.

A transition function should decide what happens next, not perform side effects.

Do not put database access, LLM calls, tool execution, or other I/O inside pure transition logic.

## Actions and LLM output

Treat model output as untrusted input.

Parse and validate model output through the existing `AgentAction` type before execution.

Invalid model output must remain an explicit failure.

Do not silently coerce or ignore invalid actions.

## Tools

Tools are execution capabilities.

Use the existing registry and tool abstraction rather than hardcoding tool behavior into the runtime.

Validate tool arguments before execution.

Keep tool failures observable and recoverable where the runtime supports recovery.

## Skills

Skills provide reusable instructions, procedures, and context.

Do not put executable behavior into a skill when it belongs in a tool or application module.

Keep skills focused on one coherent capability or workflow.

## Persistence

Keep persistence behind the existing repository abstraction.

Do not bypass the repository from runtime code unless the architecture explicitly requires it.

Treat durable state and events as the source of truth for recoverable execution.

## LLM integration

The runtime should depend on the LLM abstraction rather than a concrete provider implementation.

Provider-specific concerns such as HTTP communication, response extraction, and timeouts belong in the adapter layer.

## Verification

After changing code:

1. Run focused tests for the changed behavior.
2. Use LSP or static checks when relevant.
3. Run broader tests when the change crosses module boundaries.

Never hide failed tests, runtime errors, or incomplete verification.

## External documentation

When framework or library behavior is unclear:

```text
discover
  ↓
retrieve authoritative documentation
  ↓
understand
  ↓
implement
  ↓
verify
```

Prefer official documentation.

Distill useful knowledge into skills instead of copying substantial source documentation verbatim.
