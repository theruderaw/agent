from pathlib import Path
from pydoc import text


PROJECT_ROOT = Path(__file__).resolve().parents[3] / "workspace"


def read_file(path: str) -> str:
    requested_path = (PROJECT_ROOT / path).resolve()

    try:
        requested_path.relative_to(PROJECT_ROOT)
    except ValueError:
        raise ValueError("Path is outside the allowed directory")

    if not requested_path.is_file():
        raise FileNotFoundError(f"No such file: {path}")

    return requested_path.read_text()

def write_file(path:str,data:str) -> str:
    requested_path = (PROJECT_ROOT / path).resolve()

    try:
        requested_path.relative_to(PROJECT_ROOT)
    except ValueError:
        raise ValueError("Path is outside the allowed directory")

    requested_path.write_text(data=data)
    return path

def list_directory(path: str = ".") -> str:
    """
    Returns a formatted tree listing of the given directory relative to workspace root.
    Directories are marked with a trailing '/'.
    """
    target = PROJECT_ROOT / path
    if not target.exists():
        return f"Error: '{path}' does not exist"
    if not target.is_dir():
        return f"Error: '{path}' is not a directory"

    def _walk_dir(p: Path, prefix: str = "") -> str:
        lines = []
        items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        for i, item in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            name = item.name + ("/" if item.is_dir() else "")
            lines.append(prefix + connector + name)
            if item.is_dir():
                extension = "    " if is_last else "│   "
                lines.append(_walk_dir(item, prefix + extension))
        return "\n".join(lines)

    return f"{target.relative_to(PROJECT_ROOT)}/\n" + _walk_dir(target)