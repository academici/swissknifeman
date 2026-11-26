"""Grok CLI permission flag rendering, read-only tool exclusions, and denial hints."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import Final

from skm.modules.runtimes.domain.request import AgentRequest

__all__: list[str] = []

READ_ONLY_DISALLOWED_TOOLS: Final[tuple[str, ...]] = (
    "search_replace",
    "write",
    "spawn_subagent",
    "scheduler_create",
    "scheduler_delete",
    "workflow",
    "image_gen",
    "image_edit",
    "image_to_video",
    "reference_to_video",
)

_SAFE_PROG_RE: Final = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")


@dataclass(frozen=True, slots=True)
class RenderedPermissions:
    """Rendered Grok CLI permission and restriction flags for a single step."""

    argv: tuple[str, ...]
    writable: bool
    disable_web_search: bool


def render_permission_flags(request: AgentRequest) -> RenderedPermissions:
    """Render ``--permission-mode bypassPermissions`` plus read-only/network restrictions.

    Note: ``bypassPermissions`` safety relies strictly on host containment
    (``landlock`` or ``container``), enforced in ``launch.build_launch_plan`` before spawn.
    """
    writable = bool(request.permissions.fs_write.allow)
    disable_web_search = request.permissions.network.mode == "none"

    flags: list[str] = ["--permission-mode", "bypassPermissions"]
    if not writable:
        flags.extend(("--disallowed-tools", ",".join(READ_ONLY_DISALLOWED_TOOLS)))
    if disable_web_search:
        flags.append("--disable-web-search")

    return RenderedPermissions(
        argv=tuple(flags),
        writable=writable,
        disable_web_search=disable_web_search,
    )


def denial_hint(tool: str, tool_input: object) -> str:
    """Produce a bounded, secret-free diagnostic hint for a denied Grok tool call."""
    clean_tool = tool.strip()
    if clean_tool in (
        "write",
        "search_replace",
        "Edit",
        "Write",
        "image_gen",
        "image_edit",
        "image_to_video",
        "reference_to_video",
    ):
        return "filesystem write denied by step permission policy"
    if clean_tool in ("run_terminal_command", "Bash"):
        if isinstance(tool_input, dict):
            raw_cmd = tool_input.get("command")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            if isinstance(raw_cmd, str) and raw_cmd.strip():
                first = posixpath.basename(raw_cmd.strip().split()[0])
                if _SAFE_PROG_RE.fullmatch(first):
                    return f"shell command '{first}' denied by step command policy"
        return "shell command denied by step command policy"
    if clean_tool in ("read", "glob", "grep", "Read", "Glob", "Grep"):
        return "filesystem read denied by step permission policy"
    if clean_tool in ("web_search", "fetch_url", "WebFetch", "WebSearch"):
        return "network access denied by step permission policy"
    if clean_tool.startswith("mcp__"):
        return "MCP tool call denied by step permission policy"
    return "tool call denied by step permission policy"
