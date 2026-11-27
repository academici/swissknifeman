"""Desired projection inputs and rendered file contracts (integrations §4.2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from skm.kernel.error_codes import ErrorCode
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
from .target import Surface, SurfaceSupport, TargetCapabilities, TargetId

__all__ = [
    "DesiredFile",
    "DesiredProjection",
    "HostSubscriptionEvent",
    "ProjectionInputs",
    "unsupported_surface_diagnostics",
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


def unsupported_surface_diagnostics(
    target: TargetId, inputs: ProjectionInputs, capabilities: TargetCapabilities
) -> tuple[Diagnostic, ...]:
    active = (
        (Surface.INSTRUCTIONS, bool(inputs.instructions_core or inputs.instructions_project)),
        (Surface.SKILLS, bool(inputs.skills)),
        (Surface.PERMISSIONS, bool(inputs.permissions)),
        (Surface.HOOKS, bool(inputs.hook_modes or inputs.host_subscription_events)),
        (Surface.MCP, bool(inputs.mcp_servers)),
        (Surface.AGENTS, bool(inputs.agents)),
    )
    return tuple(
        {
            "code": ErrorCode.CAPABILITY_UNAVAILABLE.value,
            "severity": "info",
            "target": target.value,
            "surface": s.value,
            "message": f"surface {s.value!r} is unsupported by target {target.value!r}",
        }
        for s, has_data in active
        if has_data and capabilities.surfaces.get(s, SurfaceSupport.UNSUPPORTED) is SurfaceSupport.UNSUPPORTED
    )
