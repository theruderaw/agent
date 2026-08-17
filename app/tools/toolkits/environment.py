# app/tools/toolkits/environment.py
import os
import platform
import sys
from typing import TypedDict

from app.tools.base import Toolkit

# Env var names matching any of these substrings (case-insensitive) are redacted.
_SECRET_MARKERS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "PRIVATE",
    "AUTH",
)

_REDACTED = "***REDACTED***"


class RuntimeInfo(TypedDict):
    python_version: str
    platform: str
    cwd: str


class EnvironmentInspectResult(TypedDict):
    variables: dict[str, str] | None
    runtime: RuntimeInfo


class EnvironmentTools(Toolkit):
    namespace = "environment"

    def __init__(self):
        ...

    def _is_secret(self, name: str) -> bool:
        upper = name.upper()
        return any(marker in upper for marker in _SECRET_MARKERS)

    async def inspect(self) -> EnvironmentInspectResult:
        """Show runtime configuration."""

        # variables = {
        #     name: (_REDACTED if self._is_secret(name) else value)
        #     for name, value in os.environ.items()
        # }

        runtime: RuntimeInfo = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "cwd": os.getcwd(),
        }

        return {"variables": None, "runtime": runtime}


if __name__ == "__main__":
    import asyncio
    import json

    async def _main() -> None:
        tools = EnvironmentTools()
        result = await tools.inspect()
        print(json.dumps(result, indent=2))

    asyncio.run(_main())