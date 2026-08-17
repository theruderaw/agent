# Git Skills

## Purpose

Manage Git repositories through controlled version-control workflows.

Git operations are performed against the current repository root. Repository paths are constrained to the configured repository boundary, while repository creation and cloning are constrained to the workspace.

## Tools

* `git:status` — inspect repository state.
* `git:diff` — inspect unstaged changes.
* `git:log` — inspect recent commits.
* `git:show` — inspect a specific commit.
* `git:add` — stage files.
* `git:commit` — create a commit.
* `git:restore` — discard changes or unstage files.
* `git:branch` — list or create branches.
* `git:checkout` — switch branches or commits.
* `git:merge` — merge a branch.
* `git:rebase` — rebase onto a branch or commit.
* `git:fetch` — retrieve remote references without merging.
* `git:pull` — fetch and merge remote changes.
* `git:push` — publish local commits.
* `git:stash` — save or reapply uncommitted changes.
* `git:clone` — clone a repository into the workspace.
* `git:init` — initialize a repository inside the workspace.

## Core Workflow

For repository modifications, prefer the following sequence:

1. Inspect repository state with `git:status`.
2. Inspect relevant files and existing changes.
3. Make the requested changes using the appropriate filesystem tools.
4. Run relevant verification before committing.
5. Inspect the resulting changes with `git:diff`.
6. Stage only the intended paths with `git:add`.
7. Commit when a commit is requested or required by the task.
8. Push only when explicitly authorized.

Do not commit merely because changes were made.

Do not push merely because a commit exists.

## Inspect Repository State

Use `git:status` before making consequential repository changes.

The status identifies:

* current branch;
* staged files;
* modified files;
* untracked files.

Use `git:diff` to inspect unstaged modifications.

Use `git:log` when commit history is relevant.

Use `git:show` when the contents and metadata of a particular commit need to be inspected.

### Existing changes

Never assume existing modifications were created by the current task.

Before staging or restoring files, distinguish between:

* changes produced by the current task;
* changes that already existed.

Do not discard unrelated user changes.

## Change Workflow

Git does not modify project files through the normal development workflow.

Use filesystem tools to create or modify files, then use Git tools to inspect and record those changes.

Typical sequence:

```text id="n7v0z1"
git:status
→ filesystem inspection/modification
→ verification
→ git:diff
→ git:add
→ git:commit
```

Inspect the diff before committing.

Stage only files belonging to the intended change.

## Commit Workflow

Before committing:

1. Check repository status.
2. Review the relevant diff.
3. Confirm that only intended files are staged.
4. Ensure relevant tests or verification have passed.
5. Create the commit with a meaningful message.

The commit tool automatically prefixes commit messages with:

```text id="q6k4mp"
AI COMMIT:
```

Therefore, the message supplied to `git:commit` should describe the change itself rather than manually adding the prefix.

Example:

```text id="5zq4jr"
git:commit(message="add filesystem skill documentation")
```

produces a commit message beginning with `AI COMMIT:`.

## Branch Workflow

Use `git:branch` without a name to inspect existing branches.

To create a branch:

```text id="6y3j8r"
git:branch(name="feature/name")
```

Use `git:checkout` to switch the working tree to an existing branch or commit.

Before switching branches, inspect the working tree with `git:status`.

Do not casually switch branches when uncommitted changes could be affected.

## Remote Workflow

### Fetch

Use `git:fetch` when remote references need to be updated without changing the current working tree.

### Pull

`git:pull` fetches and merges remote changes.

Before pulling:

1. Inspect the current branch.
2. Inspect working-tree state.
3. Ensure local changes will not be unintentionally overwritten.

### Push

`git:push` publishes local commits.

Pushing is an external side effect and should require explicit authorization from the task context.

Do not infer permission to push merely from permission to commit.

## Merge Workflow

Before merging:

1. Inspect the current branch.
2. Inspect working-tree state.
3. Confirm the branch to merge.
4. Perform the merge.
5. Inspect the resulting repository state.
6. Resolve conflicts if necessary.
7. Verify the resulting code.

Do not assume a merge succeeded solely because the tool was invoked.

## Rebase Workflow

Rebase rewrites commit history.

Before rebasing:

1. Inspect repository status.
2. Confirm the intended base.
3. Ensure relevant local work is safely represented.
4. Perform the rebase.
5. Verify repository state.

Treat rebase as a higher-risk operation than an ordinary working-tree modification.

Do not push rewritten history without explicit authorization.

## Stash Workflow

Use:

```text id="4cm2zn"
git:stash(action="push")
```

to temporarily save uncommitted changes.

A stash message may be supplied when pushing.

Use:

```text id="o6p7at"
git:stash(action="pop")
```

to reapply the most recent stash.

`message` is valid only for `push`.

Use stash when preserving the current working state is necessary for another Git operation. Do not use it merely to hide unrelated changes.

## Restore Workflow

`git:restore` has two distinct purposes.

### Discard working-tree changes

```text id="r8f4hx"
git:restore(paths=[...], staged=false)
```

This discards unstaged modifications.

This is destructive and should only be used when the relevant changes are known to be disposable.

### Unstage files

```text id="p2c6wb"
git:restore(paths=[...], staged=true)
```

This removes files from the index without discarding their working-tree changes.

Prefer this when the goal is simply to correct staging.

## Clone Workflow

`git:clone` clones a remote repository into a workspace location.

Before cloning:

1. Validate the requested destination.
2. Ensure the destination does not already exist.
3. Confirm the requested repository URL is appropriate.

The toolkit rejects `ext::` transport URLs.

After cloning, the toolkit changes its active repository root to the newly cloned repository.

## Initialize Repository

`git:init` creates or initializes a repository inside the workspace.

The destination must either:

* not exist, in which case it is created; or
* exist as an empty directory.

A non-empty existing directory is rejected.

After initialization, the toolkit changes its active repository root to the new repository.

## Safety Rules

### Path boundaries

Repository file paths are resolved relative to the repository root.

Paths that escape the repository root are rejected.

Clone and initialization destinations are constrained to the workspace.

### Argument safety

Git values that can be interpreted as references, branch names, remotes, URLs, or similar arguments are rejected when they begin with `-`.

Git path arguments are passed after `--` where supported to prevent them from being interpreted as options.

### Destructive operations

The following operations can destroy or rewrite work:

* `git:restore`
* `git:merge`
* `git:rebase`
* `git:stash`
* `git:pull`
* `git:checkout`
* `git:push`

Use them only when their effects are consistent with the requested workflow.

## Failure Handling

Git command failures are returned as `GitCommandError` and contain:

* command arguments;
* exit code;
* stdout;
* stderr.

A failed Git operation should be treated as an unsuccessful workflow step.

Do not assume repository state after a failed operation. Inspect it before continuing when the operation could have partially changed repository state.

## Completion Criteria

A Git task is complete when:

1. The requested repository operation has succeeded.
2. The resulting repository state has been inspected where appropriate.
3. Only intended files are modified or staged.
4. Verification relevant to the change has passed.
5. A commit exists only when committing was requested.
6. Remote state is changed only when explicitly authorized.
