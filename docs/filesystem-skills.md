# Filesystem Skill

## Purpose

Manage files and directories within the agent workspace.

This skill provides controlled filesystem operations while enforcing the workspace sandbox boundary.

## Scope

All filesystem paths are resolved relative to the workspace root.

The agent must not attempt to access paths outside the workspace.

The filesystem toolkit enforces this boundary through path resolution. Paths that resolve outside the workspace are rejected.

## Tools

* `file-system:exists` — check whether a path exists.
* `file-system:find` — recursively locate files by glob pattern.
* `file-system:grep` — recursively search file contents using a regular expression.
* `file-system:list_dir` — list directory contents.
* `file-system:stat` — inspect file or directory metadata.
* `file-system:read_path` — read a text file.
* `file-system:write_path` — create or overwrite a text file.
* `file-system:patch_path` — replace specific text in an existing file.
* `file-system:make_dir` — create a directory.
* `file-system:copy_path` — copy a file.
* `file-system:move_path` — move or rename a file or directory.
* `file-system:delete_path` — delete a file or directory.

## Workflow

### 1. Locate

Before modifying an unknown file:

1. Determine the relevant path from the task.
2. Use `file-system:exists` when the path is expected to be known.
3. Use `file-system:find` when the location must be discovered.
4. Use `file-system:list_dir` when the directory structure needs inspection.

Do not recursively inspect the entire workspace unless the task requires it.

### 2. Inspect

Read only the files necessary to understand the requested operation.

Use:

* `file-system:read_path` for known files.
* `file-system:grep` for targeted content searches.
* `file-system:stat` when file metadata is relevant.

For a modification, inspect the existing contents before changing them unless the file is explicitly being created from scratch.

### 3. Modify

Choose the least destructive operation that satisfies the task.

Use `file-system:write_path` when:

* creating a new file;
* replacing the complete contents of a file;
* explicitly writing a complete new version.

Use `file-system:patch_path` when:

* changing part of an existing file;
* preserving unrelated content is important;
* the target text can be identified precisely.

Prefer `patch_path` over rewriting an entire existing file when the requested change is localized.

### 4. Create directories

Use `file-system:make_dir` when a required directory does not exist.

`write_path` automatically creates missing parent directories, so a separate directory creation step is unnecessary when writing a file already provides the required directory structure.

### 5. Move or copy

Use `file-system:move_path` for relocation or renaming.

Use `file-system:copy_path` when the original should remain unchanged.

Verify the source and destination paths before performing the operation.

### 6. Delete

Deletion is destructive.

Before deleting:

1. Confirm that the target is the intended path.
2. Use `file-system:exists` when existence is uncertain.
3. Use `file-system:list_dir` or `file-system:stat` when the target's contents or type matters.

Use `recursive=true` only when deleting a directory and its contents is intentional.

Do not use recursive deletion as a substitute for deleting an individual file.

### 7. Verify

After a modification, verify the resulting filesystem state when the operation is consequential or when correctness cannot be established from the tool result alone.

Examples:

* read a newly written file;
* check that a moved file exists at its destination;
* check that a deleted path no longer exists;
* inspect a patched file when the modification is important.

## Common Workflows

### Read a file

```text
read_path(path)
```

### Find and inspect a file

```text
find(pattern, path)
→ read_path(path)
```

### Search a codebase

```text
grep(pattern, path)
```

Use `grep` when searching by content is more appropriate than searching by filename.

### Modify a specific section

```text
read_path(path)
→ patch_path(path, old_str, new_str)
→ read_path(path)
```

The initial read establishes the exact text to modify. `patch_path` fails if `old_str` is absent or, unless `replace_all=true`, appears more than once.

### Create a file

```text
write_path(path, content)
```

### Rename or relocate

```text
exists(source)
→ move_path(source, destination)
→ exists(destination)
```

### Delete

```text
exists(path)
→ delete_path(path)
→ exists(path)
```

For directories, inspect the directory before using recursive deletion when its contents are not already known.

## Safety and Constraints

### Workspace boundary

Every operation is restricted to the workspace.

Do not attempt to bypass the sandbox using:

* `..` traversal;
* absolute paths;
* symlink-based escapes;
* alternate path representations.

The toolkit resolves paths and rejects paths outside the workspace.

### Text files

`read_path`, `write_path`, `patch_path`, and `grep` operate on text.

Do not assume arbitrary binary files can be safely read or modified with these tools.

`grep` skips files that cannot be decoded as text or cannot be read due to permissions.

### Exact patching

`patch_path` performs literal string replacement, not semantic code editing.

When `replace_all=false`:

* zero matches → failure;
* one match → replacement;
* multiple matches → failure.

Use `replace_all=true` only when replacing every occurrence is intentional.

### Destructive operations

`delete_path`, overwriting through `write_path`, and broad `patch_path` replacements can destroy existing data.

Prefer targeted modifications and explicit verification.

## Completion Criteria

A filesystem task is complete when:

1. The requested filesystem operation has been performed.
2. The resulting state is consistent with the task.
3. No operation crossed the workspace boundary.
4. Consequential modifications have been verified where appropriate.
