import asyncio
import shlex
from pathlib import Path
from typing import TypedDict

from app.tools.base import Toolkit


class GitCommandError(RuntimeError):
    """Raised when a git subprocess exits with a non-zero return code."""

    def __init__(self, args: list[str], returncode: int, stdout: str, stderr: str):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            f"git {' '.join(shlex.quote(a) for a in args)} "
            f"failed with exit code {returncode}: {stderr.strip()}"
        )


class GitCommandResult(TypedDict):
    stdout: str
    stderr: str
    returncode: int


class GitStatusResponse(TypedDict):
    branch: str
    staged: list[str]
    modified: list[str]
    untracked: list[str]


class GitCommitInfo(TypedDict):
    hash: str
    author: str
    date: str
    message: str


class GitTools(Toolkit):
    namespace = "git"
    skills = "git-skills"

    def __init__(self):
        self.root = Path(__file__).parent.parent.parent.parent.resolve()
        self.proj_root = (self.root / "workspace").resolve()
        self.repo_root = self.root

    @staticmethod
    def _reject_flag_like(value: str, label: str) -> None:
        """Guard against option/flag injection for values interpolated into git commands."""
        if value.startswith("-"):
            raise ValueError(f"{label} must not begin with '-'")

    async def _run(
        self, *args: str, cwd: Path | None = None
    ) -> GitCommandResult:
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(cwd or self.repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        stdout = stdout_bytes.decode()
        stderr = stderr_bytes.decode()

        if process.returncode != 0:
            raise GitCommandError(list(args), process.returncode, stdout, stderr)

        return {"stdout": stdout, "stderr": stderr, "returncode": process.returncode}

    def _path(self, path: str) -> str:
        resolved = (self.repo_root / path).resolve()
        resolved.relative_to(self.repo_root)
        return str(resolved.relative_to(self.repo_root))

    async def status(self) -> GitStatusResponse:
        """Show the current branch, and which files are staged, modified, or untracked."""
        result = await self._run("status", "--porcelain=v1", "-b")

        lines = result["stdout"].splitlines()

        if not lines:
            return {
                "branch": "",
                "staged": [],
                "modified": [],
                "untracked": [],
            }

        branch_line = lines[0]
        branch = branch_line[3:].split("...", 1)[0]

        staged: list[str] = []
        modified: list[str] = []
        untracked: list[str] = []

        for line in lines[1:]:
            code = line[:2]
            path = line[3:]

            if code == "??":
                untracked.append(path)
                continue

            if code[0] != " ":
                staged.append(path)

            if code[1] != " ":
                modified.append(path)

        return {
            "branch": branch,
            "staged": staged,
            "modified": modified,
            "untracked": untracked,
        }

    async def diff(self, path: str | None = None) -> str:
        """Show unstaged changes, optionally scoped to a single file path."""
        if path is None:
            result = await self._run("diff")
        else:
            result = await self._run("diff", "--", self._path(path))

        return result["stdout"]

    async def log(self, limit: int = 10) -> list[GitCommitInfo]:
        """List recent commits with their hash, author, date, and message."""
        if limit < 1:
            raise ValueError("limit must be greater than 0")

        result = await self._run(
            "log",
            f"-{limit}",
            "--format=%H%x1f%an%x1f%aI%x1f%s",
        )

        commits: list[GitCommitInfo] = []

        for line in result["stdout"].splitlines():
            commit_hash, author, date, message = line.split("\x1f", 3)

            commits.append(
                {
                    "hash": commit_hash,
                    "author": author,
                    "date": date,
                    "message": message,
                }
            )

        return commits

    async def show(self, ref: str) -> str:
        """Show the full diff and metadata for a single commit."""
        if not ref.strip():
            raise ValueError("ref must not be empty")
        self._reject_flag_like(ref, "ref")

        result = await self._run("show", "--stat", "--patch", "--", ref)
        return result["stdout"]

    async def add(self, paths: list[str]) -> str:
        """Stage the given file paths for the next commit."""
        if not paths:
            raise ValueError("paths must not be empty")

        safe_paths = [self._path(path) for path in paths]

        result = await self._run(
            "add",
            "--",
            *safe_paths,
        )

        return result["stdout"]

    async def commit(self, message: str) -> str:
        """Commit currently staged changes with the given commit message."""
        if not message.strip():
            raise ValueError("commit message must not be empty")

        result = await self._run(
            "commit",
            "-m",
            f"AI COMMIT: {message}",
        )

        return result["stdout"]

    async def restore(
        self,
        paths: list[str],
        staged: bool = False,
    ) -> str:
        """Discard unstaged changes to the given files, or unstage them if staged is true."""
        if not paths:
            raise ValueError("paths must not be empty")

        safe_paths = [self._path(path) for path in paths]

        if staged:
            result = await self._run(
                "restore",
                "--staged",
                "--",
                *safe_paths,
            )
        else:
            result = await self._run(
                "restore",
                "--",
                *safe_paths,
            )

        return result["stdout"]

    async def branch(self, name: str | None = None) -> list[str] | str:
        """List all branches, or create a new branch if a name is given."""
        if name is None:
            result = await self._run(
                "branch",
                "--format=%(refname:short)",
            )

            return result["stdout"].splitlines()

        if not name.strip():
            raise ValueError("branch name must not be empty")
        self._reject_flag_like(name, "branch name")

        result = await self._run("branch", "--", name)

        return result["stdout"]

    async def checkout(self, ref: str) -> str:
        """Switch the working directory to the given branch or commit."""
        if not ref.strip():
            raise ValueError("ref must not be empty")
        self._reject_flag_like(ref, "ref")

        result = await self._run("checkout", "--", ref)

        return result["stdout"]

    async def merge(self, branch: str) -> str:
        """Merge the given branch into the current branch."""
        if not branch.strip():
            raise ValueError("branch must not be empty")
        self._reject_flag_like(branch, "branch")

        result = await self._run("merge", "--", branch)

        return result["stdout"]

    async def rebase(self, onto: str) -> str:
        """Rebase the current branch onto the given branch or commit."""
        if not onto.strip():
            raise ValueError("onto must not be empty")
        self._reject_flag_like(onto, "onto")

        result = await self._run("rebase", "--", onto)

        return result["stdout"]

    async def fetch(self, remote: str = "origin") -> str:
        """Download new commits and branches from a remote without merging them."""
        if not remote.strip():
            raise ValueError("remote must not be empty")
        self._reject_flag_like(remote, "remote")

        result = await self._run("fetch", "--", remote)

        return result["stdout"]

    async def pull(
        self,
        remote: str = "origin",
        branch: str | None = None,
    ) -> str:
        """Fetch from a remote and merge into the current branch."""
        if not remote.strip():
            raise ValueError("remote must not be empty")
        self._reject_flag_like(remote, "remote")

        if branch is None:
            result = await self._run("pull", "--", remote)
        else:
            if not branch.strip():
                raise ValueError("branch must not be empty")
            self._reject_flag_like(branch, "branch")

            result = await self._run("pull", "--", remote, branch)

        return result["stdout"]

    async def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
    ) -> str:
        """Push local commits on the current branch to a remote."""
        if not remote.strip():
            raise ValueError("remote must not be empty")
        self._reject_flag_like(remote, "remote")

        if branch is None:
            result = await self._run("push", "--", remote)
        else:
            if not branch.strip():
                raise ValueError("branch must not be empty")
            self._reject_flag_like(branch, "branch")

            result = await self._run("push", "--", remote, branch)

        return result["stdout"]

    async def stash(
        self,
        action: str = "push",
        message: str | None = None,
    ) -> str:
        """Save uncommitted changes aside (push), or reapply the most recent stash (pop)."""
        if action not in {"push", "pop"}:
            raise ValueError("action must be either 'push' or 'pop'")

        if action == "push":
            if message is None:
                result = await self._run("stash", "push")
            else:
                if not message.strip():
                    raise ValueError("stash message must not be empty")

                result = await self._run("stash", "push", "-m", message)
        else:
            if message is not None:
                raise ValueError("message is only valid for stash push")

            result = await self._run("stash", "pop")

        return result["stdout"]

    async def clone(self, url: str, destination: str) -> str:
        """Clone a remote Git repository into the workspace."""
        if not url.strip():
            raise ValueError("url must not be empty")
        self._reject_flag_like(url, "url")
        if url.lower().startswith("ext::"):
            raise ValueError("ext:: transport URLs are not permitted")

        destination_path = (self.proj_root / destination).resolve()

        destination_path.relative_to(self.proj_root)

        if destination_path.exists():
            raise ValueError(
                f"destination already exists: {destination}"
            )

        result = await self._run(
            "clone",
            "--",
            url,
            str(destination_path),
            cwd=self.proj_root,
        )

        self.repo_root = destination_path

        return result["stdout"]

    async def init(self, destination: str) -> str:
        """Initialize a new Git repository inside the workspace."""
        if not destination.strip():
            raise ValueError("destination must not be empty")

        destination_path = (self.proj_root / destination).resolve()
        destination_path.relative_to(self.proj_root)

        if destination_path.exists():
            if not destination_path.is_dir():
                raise ValueError(
                    f"destination is not a directory: {destination}"
                )

            if any(destination_path.iterdir()):
                raise ValueError(
                    f"destination is not empty: {destination}"
                )
        else:
            destination_path.mkdir(parents=True)

        result = await self._run("init", cwd=destination_path)

        self.repo_root = destination_path

        return result["stdout"]