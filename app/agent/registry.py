from typing import Callable
from app.agent.tools import TOOL_NAMES
from app.agent.tools.calculator import calculator
from app.agent.tools.filesystem import read_file, write_file
from app.agent.tools.time import get_time

TOOLS: dict[str, Callable] = {
    "calculator": calculator,
    "read_file": read_file,
    "write_file":write_file,
    "get_time": get_time,
}

assert set(TOOLS.keys()) == set(TOOL_NAMES)  # catches drift if you add a tool and forget one side

def get_tool(tool: str) -> Callable:
    if tool in TOOLS:
        return TOOLS[tool]
    raise ValueError(f"Tool {tool} not found")