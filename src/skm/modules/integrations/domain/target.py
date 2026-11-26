"""Integration targets, surfaces, and target capability contracts (integrations §4.1)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

from .contracts import HookBinding

if TYPE_CHECKING:
    from .hook_events import HookSurfaceId

__all__ = [
    "Surface",
    "SurfaceSupport",
    "TargetCapabilities",
    "TargetId",
]


class TargetId(StrEnum):
    ANTIGRAVITY = "antigravity"
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    CURSOR = "cursor"
    GEMINI_CLI = "gemini_cli"
    GROK = "grok"


class Surface(StrEnum):
    INSTRUCTIONS = "instructions"
    SKILLS = "skills"
    PERMISSIONS = "permissions"
    HOOKS = "hooks"
    MCP = "mcp"
    AGENTS = "agents"


class SurfaceSupport(StrEnum):
    NATIVE = "native"
    CONFIG_NATIVE = "config_native"
    HOOK_NATIVE = "hook_native"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class TargetCapabilities:
    target: TargetId
    surfaces: Mapping[Surface, SurfaceSupport]
    hook_surfaces: Mapping[HookSurfaceId, HookBinding]
    tested_client_version: str
    verified_at: date
