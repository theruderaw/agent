# app/tools/toolkits/process.py

from typing import TypedDict

from app.tools.base import Toolkit


class ProcessInfo(TypedDict):
    pid: int
    name: str
    status: str


class ProcessTools(Toolkit):
    namespace = "process"

    def __init__(self):
        ...

    async def ps(self) -> list[ProcessInfo]:
        """List currently running processes on the system."""
        raise NotImplementedError("process:ps is not implemented yet")

    async def start(self, command: str) -> int:
        """Start a background process and return its process ID."""
        raise NotImplementedError("process:start is not implemented yet")

    async def kill(self, pid: int) -> str:
        """Terminate a process that was started via the start tool."""
        raise NotImplementedError("process:kill is not implemented yet")