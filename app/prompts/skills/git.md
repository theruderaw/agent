# Git Skill

You now have access to additional git tools for version control. Only use
them when the task actually involves git operations (staging, committing,
branching, pushing, pulling). Do not reach for these tools on unrelated
tasks just because they are available.

## Operating Context
- The git repository root for ALL operations is the `workspace/` directory.
- All file paths provided to git tools MUST be relative to `workspace/`.
- You are strictly prohibited from referencing files outside `workspace/`.

## Available git tools

- git_pull: pulls the latest changes for the current branch from its remote.
  arguments: {}

- git_add: stages one or more files for commit.
  PATH RULE: All paths are relative to `workspace/`.
  Examples (based on the actual structure inside `workspace/`):
  - File directly in `workspace/` (e.g., `calc.py`, `nums.txt`, `test.txt`) -> use: {"files": ["calc.py"]}
  - File in `workspace/agent-repo/` (e.g., `README.md`) -> use: {"files": ["agent-repo/README.md"]}
  - Do NOT prefix with `workspace/` or `./`.
  - Do NOT try to add files from outside `workspace/` (like `app/`, `test/`, or root files like `index.txt`).
  arguments: {"files": ["<path relative to workspace/>", ...]}

- git_commit: commits currently staged changes. The tool itself prepends
  "AGENT-COMMIT " to whatever message you provide — do NOT include that
  prefix yourself, and do not claim a commit happened unless this tool
  actually executed successfully.
  arguments: {"message": "<commit message, no prefix>"}

- git_push: pushes the current branch to its already-configured upstream.
  arguments: {}

- git_push_set_upstream: pushes a branch to origin and sets it as that
  branch's upstream. Use this the first time a new local branch is pushed.
  arguments: {"branch_name": "<branch name>"}

- git_checkout_new_branch: creates a new branch and switches to it.
  arguments: {"branch_name": "<new branch name>"}

- git_checkout: switches to an existing branch.
  arguments: {"branch_name": "<existing branch name>"}

- git_branch_delete: deletes a local branch. This fails (by design) if the
  branch has unmerged changes rather than silently.

- git_clone: clones a remote repo into the `workspace/` directory (or a given subdirectory inside `workspace/`).
  arguments: {"url": "<repo url>", "destination": "<optional path relative to workspace/, defaults to '.'>"}