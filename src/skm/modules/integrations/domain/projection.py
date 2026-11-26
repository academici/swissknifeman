"""Projection state transitions, plan records, and pure write materialization (integrations §4.9)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, NewType
from uuid import UUID

from skm.kernel.ids import ProjectId, WorkspaceId
from skm.modules.workspace.public import CheckoutBindingId

from .conflict_names import conflict_path
from .contracts import Diagnostic
from .decisions import FileDecision, FileDecisionKind
from .desired import DesiredFile
from .managed_block import replace_blocks
from .merged_json import dumps_merged_json_bytes, merge_owned, parse_json_document
from .merged_toml import merge_owned_toml, parse_toml
from .observed import AppliedFileRecord
from .ownership import ManagedBoundary, Ownership, empty_managed_digest
from .target import Surface, TargetId

__all__ = [
    "PROJECTION_TRANSITIONS",
    "ApplyOutcome",
    "LocalPreImage",
    "LocalPreImageKey",
    "PlannedWrite",
    "Projection",
    "ProjectionId",
    "ProjectionPlan",
    "ProjectionState",
    "build_planned_write",
    "can_transition_projection",
    "is_empty_document",
    "next_state_after_apply",
]

ProjectionId = NewType("ProjectionId", UUID)


class ProjectionState(StrEnum):
    PENDING = "pending"
    IN_SYNC = "in_sync"
    DRIFTED = "drifted"
    FAILED = "failed"
    REMOVED = "removed"


PROJECTION_TRANSITIONS: Mapping[ProjectionState, frozenset[ProjectionState]] = MappingProxyType(
    {
        ProjectionState.PENDING: frozenset(
            {
                ProjectionState.IN_SYNC,
                ProjectionState.FAILED,
                ProjectionState.DRIFTED,
                ProjectionState.REMOVED,
            }
        ),
        ProjectionState.IN_SYNC: frozenset(
            {
                ProjectionState.PENDING,
                ProjectionState.DRIFTED,
                ProjectionState.FAILED,
                ProjectionState.REMOVED,
                ProjectionState.IN_SYNC,
            }
        ),
        ProjectionState.DRIFTED: frozenset(
            {
                ProjectionState.IN_SYNC,
                ProjectionState.PENDING,
                ProjectionState.FAILED,
                ProjectionState.REMOVED,
                ProjectionState.DRIFTED,
            }
        ),
        ProjectionState.FAILED: frozenset(
            {
                ProjectionState.IN_SYNC,
                ProjectionState.PENDING,
                ProjectionState.DRIFTED,
                ProjectionState.REMOVED,
                ProjectionState.FAILED,
            }
        ),
        ProjectionState.REMOVED: frozenset(
            {
                ProjectionState.PENDING,
                ProjectionState.IN_SYNC,
            }
        ),
    }
)


def can_transition_projection(current: ProjectionState, target: ProjectionState) -> bool:
    """Return True if ``current -> target`` is permitted by ``PROJECTION_TRANSITIONS``."""
    return ProjectionState(target) in PROJECTION_TRANSITIONS[ProjectionState(current)]


def next_state_after_apply(
    conflicts: Sequence[str] | int | bool,
    failed: Sequence[Any] | int | bool,
    left_modified: Sequence[str] | int | bool = (),
) -> ProjectionState:
    """Pure transition after apply: failed -> FAILED; conflicts -> DRIFTED; else IN_SYNC."""
    _ = left_modified
    if bool(failed):
        return ProjectionState.FAILED
    if bool(conflicts):
        return ProjectionState.DRIFTED
    return ProjectionState.IN_SYNC


@dataclass(frozen=True, slots=True)
class Projection:
    id: ProjectionId
    workspace_id: WorkspaceId
    project_id: ProjectId
    checkout_binding_id: CheckoutBindingId
    target: TargetId
    state: ProjectionState
    desired_digest: str | None
    applied_desired_digest: str | None
    renderer_version: str | None
    applied_at: datetime | None
    drift_checked_at: datetime | None
    row_version: int


@dataclass(frozen=True, slots=True)
class LocalPreImage:
    """A recorded before-state. None contents mean the path did not exist."""

    contents: bytes | None
    verified_absence: bool = True


@dataclass(frozen=True, slots=True)
class LocalPreImageKey:
    project_id: ProjectId
    binding_id: CheckoutBindingId
    target: TargetId
    relative_path: str


@dataclass(frozen=True, slots=True)
class ProjectionPlan:
    project_id: ProjectId
    checkout_binding_id: CheckoutBindingId
    target: TargetId
    desired_digest: str
    inputs_digest: str
    renderer_version: str
    base_projection_row_version: int | None
    decisions: tuple[FileDecision, ...]
    writes: tuple[PlannedWrite, ...]
    diagnostics: tuple[Diagnostic, ...]
    plan_digest: str


@dataclass(frozen=True, slots=True)
class PlannedWrite:
    relative_path: str
    decision: FileDecisionKind
    boundary: ManagedBoundary
    surface: Surface
    new_bytes: bytes | None
    write_path: str
    expected_observed_whole_digest: str | None
    needs_pre_image: bool
    managed_digest_after: str | None


@dataclass(frozen=True, slots=True)
class ApplyOutcome:
    target: TargetId
    projection_id: ProjectionId
    state: ProjectionState
    written: tuple[str, ...]
    conflicts: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]
    adopted_clean: tuple[str, ...]
    left_modified: tuple[str, ...]


def _render_desired_into_base(desired: DesiredFile, base_bytes: bytes | None) -> bytes:
    boundary = desired.boundary
    if boundary.ownership is Ownership.MANAGED_FILE:
        return desired.managed_bytes
    if boundary.ownership is Ownership.MANAGED_BLOCK:
        return replace_blocks(base_bytes or b"", desired.managed_bytes, boundary.block_ids)
    if boundary.ownership is Ownership.MERGED_JSON:
        base_doc = parse_json_document(base_bytes) if base_bytes is not None else {}
        managed_doc = parse_json_document(desired.managed_bytes)
        return dumps_merged_json_bytes(merge_owned(base_doc, managed_doc, boundary.owned_keys))
    if boundary.ownership is Ownership.MERGED_TOML:
        base_text = base_bytes.decode("utf-8") if base_bytes is not None else ""
        managed_doc = parse_toml(desired.managed_bytes.decode("utf-8"))
        return merge_owned_toml(base_text, managed_doc, boundary.owned_keys).encode("utf-8")
    raise ValueError("INTEGRATION_BOUNDARY_INVALID")


def is_empty_document(boundary: ManagedBoundary, data: bytes) -> bool:
    """True when ``data`` is what an emptied document of this ``boundary`` looks like."""
    try:
        if boundary.ownership in (Ownership.MANAGED_BLOCK, Ownership.MERGED_TOML):
            return not data.strip()
        if boundary.ownership is Ownership.MERGED_JSON:
            return not parse_json_document(data)
    except ValueError:
        return False
    return False


def _build_remove_owned_write(
    decision: FileDecision,
    applied: AppliedFileRecord | None,
    observed_bytes: bytes | None,
) -> PlannedWrite | None:
    if applied is None:
        raise ValueError("applied is required for REMOVE_OWNED")
    if decision.expected_observed_whole_digest is None:
        return None
    boundary = applied.boundary
    if boundary.ownership is Ownership.MANAGED_FILE:
        removed_bytes: bytes | None = None
        after_digest: str | None = None
    elif boundary.ownership is Ownership.MANAGED_BLOCK:
        removed_bytes = replace_blocks(observed_bytes or b"", b"", boundary.block_ids)
        after_digest = empty_managed_digest(boundary)
    elif boundary.ownership is Ownership.MERGED_JSON:
        base_doc = parse_json_document(observed_bytes or b"{}\n")
        removed_bytes = dumps_merged_json_bytes(merge_owned(base_doc, {}, boundary.owned_keys))
        after_digest = empty_managed_digest(boundary)
    elif boundary.ownership is Ownership.MERGED_TOML:
        base_text = (observed_bytes or b"").decode("utf-8")
        removed_bytes = merge_owned_toml(base_text, {}, boundary.owned_keys).encode("utf-8")
        after_digest = empty_managed_digest(boundary)
    else:
        raise ValueError("INTEGRATION_BOUNDARY_INVALID")
    return PlannedWrite(
        relative_path=decision.relative_path,
        decision=FileDecisionKind.REMOVE_OWNED,
        boundary=boundary,
        surface=applied.surface,
        new_bytes=removed_bytes,
        write_path=decision.relative_path,
        expected_observed_whole_digest=decision.expected_observed_whole_digest,
        needs_pre_image=False,
        managed_digest_after=after_digest,
    )


def build_planned_write(
    decision: FileDecision,
    *,
    desired: DesiredFile | None,
    applied: AppliedFileRecord | None = None,
    observed_bytes: bytes | None = None,
) -> PlannedWrite | None:
    """Materialize a ``PlannedWrite`` for mutating decisions, or ``None`` when no write occurs."""
    kind = decision.kind
    if kind is FileDecisionKind.REMOVE_OWNED:
        return _build_remove_owned_write(decision, applied, observed_bytes)
    if kind not in (
        FileDecisionKind.CREATE,
        FileDecisionKind.UPDATE,
        FileDecisionKind.CONFLICT_WRITE_NEW,
    ):
        return None
    if desired is None:
        raise ValueError(f"desired is required for {kind.value}")

    base = None if kind is FileDecisionKind.CREATE else observed_bytes
    new_bytes = _render_desired_into_base(desired, base)
    write_path = (
        conflict_path(decision.relative_path)
        if kind is FileDecisionKind.CONFLICT_WRITE_NEW
        else decision.relative_path
    )
    expected_whole = decision.expected_observed_whole_digest if kind is FileDecisionKind.UPDATE else None
    return PlannedWrite(
        relative_path=decision.relative_path,
        decision=kind,
        boundary=desired.boundary,
        surface=desired.surface,
        new_bytes=new_bytes,
        write_path=write_path,
        expected_observed_whole_digest=expected_whole,
        needs_pre_image=decision.needs_pre_image if kind is FileDecisionKind.UPDATE else False,
        managed_digest_after=desired.managed_digest,
    )
