# Testing Skills

## Purpose

Verify that a change behaves as intended and detect regressions before considering the work complete.

Testing is a verification workflow, not simply running a test command.

## Tools

* `pytest:run` — execute pytest.
* `ruff:check` — check Python code with Ruff.
* `ruff:format` — format Python code with Ruff.
* `mypy:check` — type-check Python code with mypy.

## Workflow

### 1. Determine What Changed

Before testing:

1. Identify the files and behavior affected by the change.
2. Identify existing tests covering that behavior.
3. Determine whether the change requires new or modified tests.
4. Identify relevant static checks.

Do not run the entire test suite automatically when a narrower verification scope is sufficient.

### 2. Run Targeted Tests

Start with tests closest to the changed behavior.

```text id="x4m7v2"
change
→ identify relevant tests
→ pytest:run(targeted tests)
```

Targeted tests provide fast feedback while developing.

### 3. Run Broader Tests

After targeted tests pass, run the broader relevant test suite when the change could affect other components.

For a project-level change:

```text id="m2q8k4"
targeted tests
→ broader tests
```

Do not treat passing targeted tests as proof that unrelated integration behavior remains correct.

### 4. Static Analysis

Use `ruff:check` to identify Python linting and code-quality issues.

Use `mypy:check` when type correctness is relevant to the project.

A typical Python verification workflow is:

```text id="h8v3nc"
pytest
→ ruff check
→ mypy
```

The exact order may be adjusted when faster feedback is useful.

### 5. Formatting

Use `ruff:format` when formatting is required.

Formatting should not be treated as a substitute for testing.

After formatting code that affects behavior, rerun relevant tests.

### 6. Test Failures

When a test fails:

1. Read the failure output.
2. Identify whether the failure is caused by the current change.
3. Inspect the relevant implementation and test.
4. Make the smallest appropriate correction.
5. Rerun the failed test.
6. Rerun broader tests when necessary.

Do not repeatedly rerun a failing test without changing anything or obtaining additional information.

### 7. Distinguish Failures

A failed verification command does not necessarily mean the implementation is incorrect.

Determine whether the failure comes from:

* application behavior;
* an incorrect test;
* an environment problem;
* missing dependencies;
* configuration;
* type errors;
* lint errors;
* formatting;
* unrelated pre-existing failures.

Do not modify application code merely to make an unrelated environment failure disappear.

### 8. Regression Verification

When fixing a bug:

1. Reproduce or encode the problematic behavior.
2. Add or identify a regression test where appropriate.
3. Apply the fix.
4. Verify the regression test passes.
5. Run related tests.

The test should demonstrate the behavior that was previously incorrect.

## Test Selection

Prefer the smallest test scope that provides meaningful confidence.

Examples:

```text id="2j8nq6"
changed function
→ corresponding test
```

```text id="8k4p1c"
changed module
→ module tests
```

```text id="z6v2qm"
changed shared component
→ component tests
→ dependent/integration tests
```

```text id="r5c9yx"
broad architectural change
→ relevant test suite
```

Expand the scope when the change crosses component boundaries.

## Verification After Tool Changes

When modifying tools or infrastructure:

1. Test normal successful behavior.
2. Test important validation constraints.
3. Test expected failure conditions.
4. Test security boundaries where applicable.
5. Test interactions with dependent components.

For example, a sandboxed filesystem tool should not only test successful reads and writes; its boundary enforcement should also be tested.

## Completion Criteria

A testing workflow is complete when:

1. Relevant tests have been executed.
2. Important failures have been investigated.
3. Static checks relevant to the change have passed.
4. Required formatting has been applied.
5. Regression behavior has been verified when applicable.
6. Any remaining failures are understood and explicitly attributable.

A task should not be described as fully verified merely because one test command succeeded.
