"""Tool calls checked by policy: the closed set of call kinds and their canonical tool names (policy §5.3).

These value types are shared by ``classify`` and ``check_tool_call``; keeping them apart from both lets
``tool_call`` import ``classify`` at module level without an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "FileDelete",
    "FileEdit",
    "FileRead",
    "FileWrite",
    "McpCall",
    "RunCommand",
    "ToolCall",
    "WebAccess",
    "tool_name",
]


@dataclass(frozen=True, slots=True)
class FileRead:
    path: str


@dataclass(frozen=True, slots=True)
class FileWrite:
    path: str


@dataclass(frozen=True, slots=True)
class FileEdit:
    path: str


@dataclass(frozen=True, slots=True)
class FileDelete:
    path: str


@dataclass(frozen=True, slots=True)
class RunCommand:
    command: str
    cwd: str


@dataclass(frozen=True, slots=True)
class WebAccess:
    tool: str  # web.fetch | web.search
    url: str | None
    query: str | None


@dataclass(frozen=True, slots=True)
class McpCall:
    server: str
    tool: str


type ToolCall = FileRead | FileWrite | FileEdit | FileDelete | RunCommand | WebAccess | McpCall


def tool_name(call: ToolCall) -> str:
    if isinstance(call, McpCall):
        return f"mcp:{call.server}/{call.tool}"
    if isinstance(call, WebAccess):
        return call.tool
    if isinstance(call, FileRead):
        return "fs.read"
    if isinstance(call, FileWrite):
        return "fs.write"
    if isinstance(call, FileEdit):
        return "fs.edit"
    return "fs.delete" if isinstance(call, FileDelete) else "shell.run"
