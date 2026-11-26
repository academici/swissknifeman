"""Desired projection inputs and rendered file contracts (integrations §4.2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from skm.kernel.ids import ProjectId

from .contracts import (
    AgentPayload,
    Diagnostic,
    InstructionBlock,
    McpServerSpec,
    NormalizedPermissions,
    SkillPayload,
    SourceRef,
)
from .hook_events import HookClass, HookEventKind, HookSurfaceId
from .hook_rules import HookMode
from .ownership import ManagedBoundary
from .profiles import PermissionProfile
from .target import Surface, TargetId

__all__ = [
    "DesiredFile",
    "DesiredProjection",
    "HostSubscriptionEvent",
    "ProjectionInputs",
]


@dataclass(frozen=True, slots=True)
class DesiredFile:
    target: TargetId
    surface: Surface
    relative_path: str
    boundary: ManagedBoundary
    managed_bytes: bytes
    managed_digest: str
    source_refs: tuple[SourceRef, ...]
    renderer: str
    executable: bool = False


@dataclass(frozen=True, slots=True)
class DesiredProjection:
    project_id: ProjectId
    targets: tuple[TargetId, ...]
    files: tuple[DesiredFile, ...]
    diagnostics: tuple[Diagnostic, ...]
    desired_digest: str


@dataclass(frozen=True, slots=True)
class HostSubscriptionEvent:
    kind: HookEventKind
    classes: tuple[HookClass, ...]


@dataclass(frozen=True, slots=True)
class ProjectionInputs:
    project_id: ProjectId
    target: TargetId
    instructions_core: InstructionBlock
    instructions_project: InstructionBlock
    skills: tuple[SkillPayload, ...]
    permissions: NormalizedPermissions
    profile: PermissionProfile
    hook_modes: Mapping[HookSurfaceId, HookMode]
    host_subscription_events: tuple[HostSubscriptionEvent, ...]
    mcp_servers: Mapping[str, McpServerSpec]
    agents: tuple[AgentPayload, ...]
    inputs_digest: str
    config_generation: int
    diagnostics: tuple[Diagnostic, ...]
