from pathlib import Path
from pydoc import text


PROJECT_ROOT = Path(__file__).resolve().parents[3]


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