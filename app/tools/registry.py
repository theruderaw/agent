"""
registry.py

Builds a ToolRegistry from all available toolkits and writes their
combined schemas to tools.json in the same folder, grouped by toolkit.

Run: python -m app.tools.toolkits to autogenerate tools.json
"""

import json
from pathlib import Path

from app.tools.base import ToolRegistry
from app.tools.toolkits.communication import CommunicationTools
from app.tools.toolkits.database import DatabaseTools
from app.tools.toolkits.environment import EnvironmentTools
from app.tools.toolkits.filesystem import FilesystemTools
from app.tools.toolkits.git import GitTools
from app.tools.toolkits.http import HttpTools
from app.tools.toolkits.model import ModelTools
from app.tools.toolkits.mypy import MypyTools
from app.tools.toolkits.pip import PipTools
from app.tools.toolkits.process import ProcessTools
from app.tools.toolkits.python import PythonTools
from app.tools.toolkits.ruff import RuffTools
from app.tools.toolkits.search import SearchTools
from app.tools.toolkits.storage import StorageTools
from app.tools.toolkits.time import TimeTools
from app.tools.toolkits.uvicorn import UvicornTools
from app.tools.toolkits.pytest import PytestTools


# --------------------------------------------------------------------------
# Toolkits
#
# Add each new toolkit's import above and its instance below.
# Nothing else in this file needs to change as toolkits are added.
# --------------------------------------------------------------------------

TOOLKITS = [
    CommunicationTools(),
    DatabaseTools(),
    EnvironmentTools(),
    FilesystemTools(),
    GitTools(),
    HttpTools(),
    ModelTools(),
    MypyTools(),
    # PipTools(),
    ProcessTools(),
    # PytestTools(),
    # PythonTools(),
    # RuffTools(),
    SearchTools(),
    StorageTools(),
    TimeTools(),
    # UvicornTools(),
]


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for toolkit in TOOLKITS:
        registry.register_toolkit(toolkit)
    return registry


def main() -> None:
    registry = build_registry()
    schemas = registry.schemas_by_toolkit()

    out_path = Path(__file__).parent / "tools.json"
    out_path.write_text(json.dumps(schemas, indent=2))

    print(f"Registered {len(registry.list())} tool(s): {registry.list()}")
    print(f"Wrote schemas to {out_path}")


if __name__ == "__main__":
    main()