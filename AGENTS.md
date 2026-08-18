# Agent Instructions

## Workspace

This repository contains two important directories:

* `./workspace` — the agent's working directory. Create and modify code here.
* `./agent` — reference material and agent implementation. Read from here when understanding how the system works.

Do not write generated application code into `./agent` unless explicitly instructed.

## General behavior

Before making changes:

1. Inspect the relevant files.
2. Understand the existing implementation.
3. Make the smallest change that solves the task.
4. Verify the result.

Prefer existing abstractions and conventions over creating new ones.

Use the available tools when they are appropriate:

* search and inspect before editing
* use LSP/code intelligence when useful
* run relevant tests or commands after changes

Do not invent file paths. Use paths that actually exist in the repository.

## Code changes

Write implementation code under `./workspace`.

Keep changes focused and avoid unnecessary rewrites.

Do not silently ignore errors, failed tests, or invalid model output.

When a task is ambiguous and the repository cannot resolve the ambiguity, ask the user.

## Documentation and skills

Use existing documentation and skills when relevant.

Skills provide reusable instructions and context; tools provide execution capabilities.

When external documentation is needed, prefer authoritative sources and distill what is learned rather than copying large sections verbatim.
