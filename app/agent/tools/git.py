import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3] / "workspace/agent-repo"


def _run_git(*args: str) -> str:
    """
    Run a git command in the repo root and return its stdout.
    Raises RuntimeError with git's stderr on non-zero exit, so failures
    surface cleanly through the agent's TOOL_FAILED / retry path instead
    of crashing the process.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or f"git {' '.join(args)} failed with no output"
        )

    return result.stdout.strip() or f"git {' '.join(args)} completed with no output"


def _extract_real_path(path: str) -> str:
    """
    Normalizes an LLM-provided file path by stripping hallucinated parent folders
    that do not exist in REPO_ROOT.

    Examples:
      "./workspace/agent-repo/hello.txt" -> "hello.txt" (if hello.txt exists)
      "./hello.txt"                      -> "hello.txt"
      "src/main.py"                      -> "src/main.py" (if src/ exists)
      "workspace/hello.txt"              -> "hello.txt" (if workspace doesn't exist)
    """
    # Remove leading './' and any leading '/'
    clean_path = path.lstrip("./").lstrip("/")
    if not clean_path:
        return path

    parts = Path(clean_path).parts
    if not parts:
        return clean_path

    # Walk from the full path down to just the basename.
    # Return the first candidate that exists in the repo root.
    for i in range(len(parts), 0, -1):
        candidate = str(Path(*parts[-i:]))  # Take the last 'i' parts
        target = REPO_ROOT / candidate
        if target.exists():
            return candidate

    # Fallback: nothing exists, return just the basename as a best guess.
    return parts[-1]


def git_pull() -> str:
    return _run_git("pull")


def git_add(files: list[str]) -> str:
    if not files:
        raise ValueError("git_add requires at least one file")

    # Extract the real paths using the universal extractor
    normalized = [_extract_real_path(f) for f in files]
    return _run_git("add", *normalized)


def git_commit(message: str) -> str:
    if not message or not message.strip():
        raise ValueError("git_commit requires a non-empty message")
    return _run_git("commit", "-m", f"AGENT-COMMIT {message}")


def git_push() -> str:
    return _run_git("push")


def git_push_set_upstream(branch_name: str) -> str:
    if not branch_name or not branch_name.strip():
        raise ValueError("git_push_set_upstream requires a branch_name")
    return _run_git("push", "--set-upstream", "origin", branch_name)


def git_checkout_new_branch(branch_name: str) -> str:
    if not branch_name or not branch_name.strip():
        raise ValueError("git_checkout_new_branch requires a branch_name")
    return _run_git("checkout", "-b", branch_name)


def git_checkout(branch_name: str) -> str:
    if not branch_name or not branch_name.strip():
        raise ValueError("git_checkout requires a branch_name")
    return _run_git("checkout", branch_name)


def git_branch_delete(branch_name: str) -> str:
    if not branch_name or not branch_name.strip():
        raise ValueError("git_branch_delete requires a branch_name")
    return _run_git("branch", "-d", branch_name)


def git_clone(url: str, destination: str = ".") -> str:
    """
    Clone a remote repository into the repo root (REPO_ROOT).
    The destination is relative to REPO_ROOT; defaults to '.'.
    """
    if not url or not url.strip():
        raise ValueError("git_clone requires a non-empty URL")
    if not destination or not destination.strip():
        raise ValueError("git_clone requires a non-empty destination")
    return _run_git("clone", url.strip(), destination.strip())