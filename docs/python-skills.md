# Python Skills

## Purpose

Use Python to execute code or create isolated Python environments for computation, inspection, experimentation, and verification.

## Tools

* `python:run` — execute Python code.
* `python:venv` — create a Python virtual environment.

## Workflows

### Execute Python

Use `python:run` when Python execution is the appropriate way to:

* perform calculations;
* transform or inspect data;
* verify Python behavior;
* reproduce a Python-specific issue;
* perform small experiments;
* validate assumptions about Python libraries or runtime behavior.

Workflow:

```text
identify required computation
→ write minimal Python code
→ execute
→ inspect result
→ use result or refine experiment
```

Keep execution focused on the task. Do not use Python when a simpler tool is sufficient.

### Create a Virtual Environment

Use `python:venv` when an isolated Python environment is required.

Workflow:

```text
identify environment location
→ create virtual environment
→ use the environment for subsequent Python/package operations
```

Do not create a new virtual environment when an appropriate project environment already exists.

## Verification

When using Python to verify an implementation:

1. Reproduce the relevant behavior.
2. Test the expected case.
3. Test important edge cases when applicable.
4. Inspect the output rather than assuming execution succeeded.

Python execution succeeding only proves that the code executed; it does not establish that the result is correct.

## Failure Handling

If `python:run` fails:

1. Read the exception and traceback.
2. Identify whether the failure is caused by the code, environment, dependency, or input.
3. Make the smallest necessary correction.
4. Rerun the relevant experiment.

Do not suppress exceptions merely to obtain a successful execution.

## Environment Isolation

Prefer a virtual environment when:

* dependencies may conflict with the system environment;
* experimenting with package versions;
* reproducing a project-specific environment;
* installing dependencies that should not affect the global interpreter.

Do not use a virtual environment as a substitute for understanding the project's existing dependency configuration.

## Safety

Python execution can perform arbitrary operations available to the execution environment.

Before executing code that:

* modifies files;
* deletes data;
* accesses external resources;
* starts processes;
* installs packages;
* changes system state;

ensure that those side effects are actually required by the task.

Prefer read-only or self-contained experiments when possible.

## Completion Criteria

A Python workflow is complete when:

1. The required code was executed successfully.
2. The output was inspected.
3. The result answers the original verification or computation requirement.
4. Any relevant side effects or environment changes are understood.
