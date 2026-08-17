# app/tools/toolkits/filesystem.py
from pathlib import Path
import os
import re
import shutil

from app.tools.base import Toolkit


class FilesystemTools(Toolkit):
    namespace = "file-system"

    def __init__(self):
        self.root = Path(__file__).parent.parent.parent.parent
        self.workspace = (self.root / "workspace").resolve()

    def _resolve(self, path: str) -> Path:
        """Resolve a path against the workspace root and enforce the sandbox boundary."""
        p = (self.workspace / path).resolve()
        if self.workspace not in p.parents and p != self.workspace:
            raise PermissionError(f"'{path}' resolves outside the workspace")
        return p

    def read_path(self, path: str) -> str:
        """Read and return the text contents of a file at the given path."""
        p = self._resolve(path)
        if not p.is_file():
            raise FileNotFoundError(f"No such file: {path}")
        return p.read_text()

    def write_path(self, path: str, content: str, append: bool = False) -> str:
        """Write text content to a file at the given path, creating it if it doesn't exist."""
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a" if append else "w") as f:
            f.write(content)
        return f"wrote {len(content)} chars to {path}"

    def list_dir(self, path: str) -> list[str]:
        """List the names of files and folders inside a directory."""
        p = self._resolve(path)
        if not p.is_dir():
            raise NotADirectoryError(f"No such directory: {path}")
        return sorted(os.listdir(p))

    def exists(self, path: str) -> bool:
        """Check whether a file or directory exists at the given path."""
        p = self._resolve(path)
        return p.exists()

    def make_dir(self, path: str, exist_ok: bool = True) -> str:
        """Create a directory, including any missing parent directories."""
        p = self._resolve(path)
        p.mkdir(parents=True, exist_ok=exist_ok)
        return f"created directory {path}"

    def delete_path(self, path: str, recursive: bool = False) -> str:
        """Delete a file, or a directory if recursive is true."""
        p = self._resolve(path)
        if p.is_dir():
            if not recursive:
                raise IsADirectoryError(f"'{path}' is a directory; pass recursive=True to delete it")
            shutil.rmtree(p)
        elif p.is_file():
            p.unlink()
        else:
            raise FileNotFoundError(f"No such file or directory: {path}")
        return f"deleted {path}"

    def move_path(self, source: str, destination: str) -> str:
        """Move or rename a file or directory."""
        src = self._resolve(source)
        dst = self._resolve(destination)
        shutil.move(src, dst)
        return f"moved {source} -> {destination}"

    def copy_path(self, source: str, destination: str) -> str:
        """Copy a file to a new location."""
        src = self._resolve(source)
        dst = self._resolve(destination)
        shutil.copy2(src, dst)
        return f"copied {source} -> {destination}"

    def patch_path(self, path: str, old_str: str, new_str: str, replace_all: bool = False) -> str:
        """Replace text in a file. By default old_str must match exactly once; pass replace_all to replace every occurrence."""
        p = self._resolve(path)
        if not p.is_file():
            raise FileNotFoundError(f"No such file: {path}")

        contents = p.read_text()
        count = contents.count(old_str)

        if count == 0:
            raise ValueError(f"'{old_str}' not found in {path}")
        if not replace_all and count > 1:
            raise ValueError(
                f"'{old_str}' matches {count} times in {path}; pass replace_all=True to replace all"
            )

        contents = contents.replace(old_str, new_str)
        p.write_text(contents)
        return f"patched {path} ({count} replacement{'s' if count != 1 else ''})"

    def find(self, pattern: str, path: str = ".") -> list[str]:
        """Find files whose name matches a glob pattern, searched recursively from the given path."""
        p = self._resolve(path)
        if not p.is_dir():
            raise NotADirectoryError(f"No such directory: {path}")
        matches = sorted(str(m.relative_to(self.workspace)) for m in p.rglob(pattern))
        return matches

    def grep(self, pattern: str, path: str = ".") -> list[dict]:
        """Search for a regex pattern inside files, recursively from the given path, returning matching lines."""
        p = self._resolve(path)
        if not p.is_dir():
            raise NotADirectoryError(f"No such directory: {path}")

        regex = re.compile(pattern)
        results = []
        for file_path in p.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                text = file_path.read_text()
            except (UnicodeDecodeError, PermissionError):
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    results.append({
                        "path": str(file_path.relative_to(self.workspace)),
                        "line": line_no,
                        "text": line,
                    })
        return results

    def stat(self, path: str) -> dict:
        """Get metadata about a file or directory: size, type, and modified time."""
        p = self._resolve(path)
        if not p.exists():
            raise FileNotFoundError(f"No such file or directory: {path}")
        s = p.stat()
        return {
            "path": path,
            "type": "directory" if p.is_dir() else "file",
            "size_bytes": s.st_size,
            "modified_time": s.st_mtime,
        }