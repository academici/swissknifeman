"""Pure 17-row file reconciliation decision function (integrations §4.4)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from skm.kernel.error_codes import ErrorCode

from .desired import DesiredFile
from .observed import AppliedFileRecord, FileKind, ObservedFile
from .ownership import ManagedBoundary, Ownership, empty_managed_digest

__all__ = [
    "DIAG_ADOPTED_IDENTICAL",
    "DIAG_LEFT_MODIFIED",
    "DIAG_MISSING_RESTORED",
    "DIAG_SOURCE_CHANGED",
    "DIAG_UNMANAGED_TARGET",
    "FileDecision",
    "FileDecisionKind",
    "decide_file",
    "is_safe_relative_path",
    "is_shared_projection_path",
]

DIAG_ADOPTED_IDENTICAL: Final[str] = "INTEGRATION_ADOPTED_IDENTICAL"
DIAG_UNMANAGED_TARGET: Final[str] = "INTEGRATION_UNMANAGED_TARGET"
DIAG_MISSING_RESTORED: Final[str] = "INTEGRATION_MISSING_RESTORED"
DIAG_SOURCE_CHANGED: Final[str] = "INTEGRATION_SOURCE_CHANGED"
DIAG_LEFT_MODIFIED: Final[str] = "INTEGRATION_LEFT_MODIFIED"


class FileDecisionKind(StrEnum):
    NOOP = "noop"
    CREATE = "create"
    UPDATE = "update"
    ADOPT_CLEAN = "adopt_clean"
    CONFLICT_WRITE_NEW = "conflict_write_new"
    ADOPT_REQUIRED = "adopt_required"
    BOUNDARY_INVALID = "boundary_invalid"
    REMOVE_OWNED = "remove_owned"
    LEAVE_MODIFIED = "leave_modified"
    UNSAFE_TARGET = "unsafe_target"


@dataclass(frozen=True, slots=True)
class FileDecision:
    relative_path: str
    kind: FileDecisionKind
    diagnostic: str | None
    expected_observed_managed_digest: str | None
    expected_observed_whole_digest: str | None

    @property
    def needs_pre_image(self) -> bool:
        """True when an in-place UPDATE overwrites content not backed by our prior apply."""
        return self.kind is FileDecisionKind.UPDATE and self.diagnostic != DIAG_SOURCE_CHANGED


def is_shared_projection_path(path: str, boundary: ManagedBoundary) -> bool:
    return path.startswith(".agents/skills/") or (
        path == "AGENTS.md" and boundary.ownership is Ownership.MANAGED_BLOCK
    )


def is_safe_relative_path(relative_path: str) -> bool:
    """Return True if ``relative_path`` is a clean relative POSIX path within a checkout."""
    if not relative_path or "\x00" in relative_path:
        return False
    if relative_path.startswith(("/", "\\")) or "\\" in relative_path:
        return False
    if len(relative_path) >= 2 and relative_path[0].isalpha() and relative_path[1] == ":":
        return False
    segments = relative_path.split("/")
    return not any(seg in ("", ".", "..") for seg in segments)


def _decide_undesired(
    rel_path: str,
    applied: AppliedFileRecord,
    observed: ObservedFile,
    exp_managed: str | None,
    exp_whole: str | None,
) -> FileDecision:
    """Evaluate Rows 14-16 when ``desired`` is None and ``applied`` is present."""
    if not observed.exists:
        return FileDecision(rel_path, FileDecisionKind.REMOVE_OWNED, None, None, None)
    if (
        observed.boundary_valid
        and observed.managed_digest is not None
        and observed.managed_digest == applied.applied_managed_digest
    ):
        return FileDecision(rel_path, FileDecisionKind.REMOVE_OWNED, None, exp_managed, exp_whole)
    return FileDecision(
        rel_path,
        FileDecisionKind.LEAVE_MODIFIED,
        DIAG_LEFT_MODIFIED,
        exp_managed,
        exp_whole,
    )


def _decide_unapplied_existing(
    rel_path: str,
    desired: DesiredFile,
    obs_digest: str,
    exp_managed: str | None,
    exp_whole: str | None,
) -> FileDecision:
    """Evaluate Rows 4-8 when ``applied`` is None and the target file exists with a valid boundary."""
    if obs_digest == desired.managed_digest:
        return FileDecision(
            rel_path,
            FileDecisionKind.ADOPT_CLEAN,
            DIAG_ADOPTED_IDENTICAL,
            exp_managed,
            exp_whole,
        )
    if desired.boundary.ownership is Ownership.MANAGED_FILE:
        return FileDecision(
            rel_path,
            FileDecisionKind.ADOPT_REQUIRED,
            DIAG_UNMANAGED_TARGET,
            exp_managed,
            exp_whole,
        )
    if obs_digest == empty_managed_digest(desired.boundary):
        return FileDecision(rel_path, FileDecisionKind.UPDATE, None, exp_managed, exp_whole)
    return FileDecision(
        rel_path,
        FileDecisionKind.ADOPT_REQUIRED,
        DIAG_UNMANAGED_TARGET,
        exp_managed,
        exp_whole,
    )


def _decide_applied_existing(
    rel_path: str,
    desired: DesiredFile,
    applied: AppliedFileRecord,
    obs_digest: str,
    exp_managed: str | None,
    exp_whole: str | None,
    *,
    force_conflicts: bool,
) -> FileDecision:
    """Evaluate Rows 10-13 when ``applied`` is present and the target file exists with a valid boundary."""
    app_digest = applied.applied_managed_digest
    des_digest = desired.managed_digest
    if obs_digest == app_digest:
        if app_digest == des_digest:
            return FileDecision(rel_path, FileDecisionKind.NOOP, None, exp_managed, exp_whole)
        return FileDecision(
            rel_path,
            FileDecisionKind.UPDATE,
            DIAG_SOURCE_CHANGED,
            exp_managed,
            exp_whole,
        )
    if obs_digest == des_digest:
        return FileDecision(rel_path, FileDecisionKind.ADOPT_CLEAN, None, exp_managed, exp_whole)
    conflict_kind = FileDecisionKind.UPDATE if force_conflicts else FileDecisionKind.CONFLICT_WRITE_NEW
    return FileDecision(
        rel_path,
        conflict_kind,
        ErrorCode.PROJECTION_CONFLICT.value,
        exp_managed,
        exp_whole,
    )


def decide_file(
    desired: DesiredFile | None,
    applied: AppliedFileRecord | None,
    observed: ObservedFile,
    *,
    safe: bool,
    force_conflicts: bool = False,
) -> FileDecision:
    """Evaluate the 17-row reconciliation matrix (§4.4) without side effects."""
    rel_path = (
        desired.relative_path
        if desired is not None
        else (applied.relative_path if applied is not None else observed.relative_path)
    )
    exp_managed = observed.managed_digest if observed.exists else None
    exp_whole = observed.whole_digest if observed.exists else None

    is_unsafe = (
        not safe
        or observed.outside_root
        or observed.is_symlink
        or observed.effective_kind not in (FileKind.MISSING, FileKind.REGULAR)
        or not is_safe_relative_path(rel_path)
        or not is_safe_relative_path(observed.relative_path)
    )
    if is_unsafe:
        return FileDecision(
            rel_path,
            FileDecisionKind.UNSAFE_TARGET,
            ErrorCode.INTEGRATION_UNSAFE_TARGET.value,
            exp_managed,
            exp_whole,
        )

    if desired is None:
        if applied is None:
            return FileDecision(rel_path, FileDecisionKind.NOOP, None, exp_managed, exp_whole)
        return _decide_undesired(rel_path, applied, observed, exp_managed, exp_whole)

    if not observed.exists:
        diag = None if applied is None else DIAG_MISSING_RESTORED
        return FileDecision(rel_path, FileDecisionKind.CREATE, diag, None, None)

    if not observed.boundary_valid or observed.managed_digest is None:
        return FileDecision(
            rel_path,
            FileDecisionKind.BOUNDARY_INVALID,
            ErrorCode.INTEGRATION_BOUNDARY_INVALID.value,
            exp_managed,
            exp_whole,
        )

    if applied is None:
        return _decide_unapplied_existing(rel_path, desired, observed.managed_digest, exp_managed, exp_whole)
    return _decide_applied_existing(
        rel_path,
        desired,
        applied,
        observed.managed_digest,
        exp_managed,
        exp_whole,
        force_conflicts=force_conflicts,
    )
