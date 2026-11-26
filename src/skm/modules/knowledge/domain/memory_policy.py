"""Memory admission, lifetime, capacity and handoff replacement rules."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Protocol

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed, ValidationFailed

from .memory_entry import MemoryEntry, MemoryEntryId, MemoryState
from .memory_kind import REJECTED_JOURNAL_KINDS, MemoryKind
from .memory_scope import MemoryScope

REPOSITORY_COPY_RE = re.compile(
    r"^(?:AD\d{2}\b|P\d+(?:\.\d+)?\s+(?:closed[- ]green|designed|completed)\b)", re.IGNORECASE
)
_MEMORY_KINDS = frozenset(MemoryKind)
_UNCAPPED_KINDS = frozenset({MemoryKind.ACTIVE_HANDOFF, MemoryKind.HEALTH_PROBE})
_FUTURE_SKEW = timedelta(seconds=60)


class MemoryPolicySettings(Protocol):
    @property
    def default_ttl_hours(self) -> int: ...

    @property
    def max_ttl_hours(self) -> int: ...

    @property
    def health_probe_ttl_seconds(self) -> int: ...

    @property
    def max_live_per_scope(self) -> int: ...


def rejection_reason(kind: str, body: object, *, max_chars: int) -> str | None:
    if kind in REJECTED_JOURNAL_KINDS:
        return "repository_journal"
    if kind not in _MEMORY_KINDS:
        return "unsupported_category"
    if not isinstance(body, str) or not (stripped := body.strip()):
        return "empty"
    if len(body) > max_chars:
        return "oversized"
    if body.lstrip().startswith(("```", "# ", "## ", "{")):
        return "repository_copy"
    if kind != MemoryKind.ACTIVE_HANDOFF and REPOSITORY_COPY_RE.match(stripped):
        return "repository_copy"
    return None


def validate_memory_write(kind: str, body: str, *, max_chars: int) -> None:
    reason = rejection_reason(kind, body, max_chars=max_chars)
    if reason is not None:
        hint = (
            "not durable memory; keep plans, decisions, progress and code/git facts in repository artifacts; "
            f"use a short context/blocker/coordination or one active_handoff (max {max_chars} chars)"
        )
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "Memory write rejected", details={"reason": reason, "hint": hint}
        )


def ttl_for(kind: MemoryKind, requested_hours: float | None, settings: MemoryPolicySettings) -> timedelta:
    hours = settings.default_ttl_hours if requested_hours is None else requested_hours
    if isinstance(hours, bool) or not 0 < hours <= settings.max_ttl_hours:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Memory TTL must be within the configured range")
    if kind is MemoryKind.HEALTH_PROBE:
        seconds = min(hours * 3600, settings.health_probe_ttl_seconds)
        ttl = timedelta(seconds=seconds)
    else:
        ttl = timedelta(hours=hours)
    return max(ttl, timedelta.resolution)


def is_live(entry: MemoryEntry, now: datetime, settings: MemoryPolicySettings) -> bool:
    if entry.state is not MemoryState.LIVE:
        return False
    if now.utcoffset() is None:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Memory timestamps must be timezone-aware")
    created_at = entry.created_at.astimezone(UTC)
    expires_at = entry.expires_at.astimezone(UTC)
    now = now.astimezone(UTC)
    age = now - created_at
    return (
        expires_at > created_at
        and -_FUTURE_SKEW <= age < timedelta(hours=settings.max_ttl_hours)
        and now < expires_at
    )


def check_limits(live_in_scope: int, kind: MemoryKind, settings: MemoryPolicySettings) -> None:
    """Check capacity given the number of live entries subject to the scope cap."""
    if kind not in _UNCAPPED_KINDS and live_in_scope >= settings.max_live_per_scope:
        raise PreconditionFailed(ErrorCode.MEMORY_LIMIT_REACHED, "Memory scope is at capacity")


def check_handoff_replacement(
    scope: MemoryScope,
    kind: MemoryKind,
    current_handoff: MemoryEntry | None,
    expected_handoff_id: MemoryEntryId | None,
) -> None:
    """Check the CAS against the persisted live row under the caller's scope lock."""
    if kind is not MemoryKind.ACTIVE_HANDOFF:
        if expected_handoff_id is not None:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Expected handoff ID requires an active handoff")
        return
    current_id = None
    if current_handoff is not None:
        if current_handoff.scope != scope or current_handoff.kind is not MemoryKind.ACTIVE_HANDOFF:
            raise ValueError("Expected a handoff from the requested scope")
        if current_handoff.state is MemoryState.LIVE:
            current_id = current_handoff.id
    if current_id != expected_handoff_id:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT, "The active handoff changed", details={"reason": "handoff_changed"}
        )
