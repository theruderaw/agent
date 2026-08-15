from typing import Callable
from app.agent.tools import TOOL_NAMES
from app.agent.tools.calculator import calculator
from app.agent.tools.filesystem import read_file, write_file, list_directory
from app.agent.tools.time import get_time
from app.agent.tools.git import (
    git_pull,
    git_clone,
    git_add,
    git_commit,
    git_push,
    git_push_set_upstream,
    git_checkout_new_branch,
    git_checkout,
    git_branch_delete,
)

TOOLS: dict[str, Callable] = {
    "calculator": calculator,
    "read_file": read_file,
    "write_file":write_file,
    "list_directory":list_directory,
    "get_time": get_time,
    "git_pull": git_pull,
    "git_clone": git_clone,
    "git_add": git_add,
    "git_commit": git_commit,
    "git_push": git_push,
    "git_push_set_upstream": git_push_set_upstream,
    "git_checkout_new_branch": git_checkout_new_branch,
    "git_checkout": git_checkout,
    "git_branch_delete": git_branch_delete,
}

assert set(TOOLS.keys()) == set(TOOL_NAMES)  # catches drift if you add a tool and forget one side

def get_tool(tool: str) -> Callable:
    if tool in TOOLS:
        return TOOLS[tool]
    raise ValueError(f"Tool {tool} not found")