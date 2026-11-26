"""Leases and the monotonic fence (execution §4.9, «Leases и fencing»).

A worker acts on an attempt only under the lease of a ``leased`` assignment: the claim names the
assignment, the attempt, the worker and the fencing token, and all of them are checked together with the
expiry (``verify_fence``). Each issue of one assignment row takes ``last_fencing_token + 1``; a reissue
is a new row (``assignment.reissue``), so an old claim is refused by the assignment id alone.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.modules.execution.domain.assignment import AssignmentState, transition_assignment

if TYPE_CHECKING:
    from skm.kernel.ids import AttemptId, WorkerId
    from skm.kernel.json_types import JsonObject
    from skm.modules.execution.domain.assignment import Assignment
    from skm.modules.execution.domain.ids import AssignmentId

__all__ = [
    "UNIT_KINDS",
    "Lease",
    "ProcessIdentity",
    "WorkerClaim",
    "issue_lease",
    "next_fencing_token",
    "renew_lease",
    "verify_fence",
]

# owners of observed processes (adapters §5.3): a role step, a check run or a Git effect
UNIT_KINDS: Final = frozenset({"step", "check", "git_effect"})


@dataclass(frozen=True, slots=True)
class WorkerClaim:
    assignment_id: AssignmentId
    attempt_id: AttemptId
    worker_id: WorkerId
    fencing_token: int


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    """Observed identity of one process unit; ``ownership.owner`` binds it to its unit.

    ``ownership`` is the durable owner record (kind/ref/host/worker/attempt/stage_record_id, ``unit_kind``,
    ``unit_id`` and owner nonce). A leader PID alone never proves that the unit stopped.
    """

    pid: int | None
    pgid: int | None
    started_at: datetime
    ownership: JsonObject
    boot_id: str | None = None
    session_ref: str | None = None
    start_ticks: int | None = None

    @property
    def unit_key(self) -> tuple[str, str]:
        """``(unit_kind, unit_id)`` from ``ownership.owner``; malformed ownership is ``SCHEMA_INVALID``."""
        owner = self.ownership.get("owner")
        if isinstance(owner, dict):
            kind = owner.get("unit_kind")
            unit = owner.get("unit_id")
            if isinstance(kind, str) and kind in UNIT_KINDS and isinstance(unit, str) and unit:
                return kind, unit
        raise error_for(
            ErrorCode.SCHEMA_INVALID,
            "process ownership names its unit (owner.unit_kind step|check|git_effect and owner.unit_id)",
            details={"field": "ownership.owner"},
        )


@dataclass(frozen=True, slots=True)
class Lease:
    assignment_id: AssignmentId
    worker_id: WorkerId
    fencing_token: int
    expires_at: datetime
    last_heartbeat_at: datetime
    process_identity: ProcessIdentity | None
    offered_runtimes: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.fencing_token < 1:
            raise error_for(
                ErrorCode.SCHEMA_INVALID, "a lease token is >= 1", details={"field": "fencing_token"}
            )
        if self.last_heartbeat_at > self.expires_at:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "a heartbeat is not after the expiry",
                details={"field": "last_heartbeat_at"},
            )


def verify_fence(lease: Lease | None, assignment: Assignment, claim: WorkerClaim, now: datetime) -> Lease:
    """``LEASE_LOST`` unless the claim holds the live lease of this leased assignment for this attempt.

    Refused when: there is no lease; the lease or the assignment is another one; another worker holds it;
    the token differs (older or newer); the lease expired (``expires_at <= now``); the assignment is not
    ``leased``; the assignment belongs to another attempt.
    """
    if lease is None:
        raise _lease_lost(claim, "no_lease")
    reason: str | None = None
    if claim.assignment_id != assignment.id or lease.assignment_id != assignment.id:
        reason = "other_assignment"
    elif assignment.attempt_id != claim.attempt_id:
        reason = "other_attempt"
    elif lease.worker_id != claim.worker_id:
        reason = "other_worker"
    elif lease.fencing_token != claim.fencing_token:
        reason = "stale_token"
    elif lease.expires_at <= now:
        reason = "expired"
    elif assignment.state is not AssignmentState.LEASED:
        reason = "not_leased"
    if reason is not None:
        raise _lease_lost(claim, reason)
    return lease


def _lease_lost(claim: WorkerClaim, reason: str) -> SkmError:
    return error_for(
        ErrorCode.LEASE_LOST,
        f"lease of assignment {claim.assignment_id} is not held: {reason}",
        details={
            "reason": reason,
            "assignment_id": str(claim.assignment_id),
            "attempt_id": str(claim.attempt_id),
            "fencing_token": claim.fencing_token,
        },
    )


def next_fencing_token(assignment: Assignment) -> int:
    """The token of the next issue of this assignment row: strictly greater than every earlier one."""
    return assignment.last_fencing_token + 1


def issue_lease(
    assignment: Assignment,
    *,
    worker_id: WorkerId,
    now: datetime,
    ttl: timedelta,
    offered_runtimes: frozenset[str] = frozenset(),
) -> tuple[Assignment, Lease]:
    """``claim_assignment``: ``available -> leased`` with the next token, and the lease of that token."""
    if ttl <= timedelta(0):
        raise error_for(ErrorCode.SCHEMA_INVALID, "a lease lives a positive time", details={"field": "ttl"})
    if assignment.available_at > now:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "the assignment is not available yet",
            details={
                "assignment_id": str(assignment.id),
                "available_at": assignment.available_at.isoformat(),
            },
        )
    token = next_fencing_token(assignment)
    leased = transition_assignment(assignment, AssignmentState.LEASED)
    leased = dataclasses.replace(leased, last_fencing_token=token)
    lease = Lease(assignment.id, worker_id, token, now + ttl, now, None, offered_runtimes)
    return leased, lease


def renew_lease(
    lease: Lease,
    assignment: Assignment,
    claim: WorkerClaim,
    *,
    now: datetime,
    ttl: timedelta,
    process_identity: ProcessIdentity | None = None,
) -> Lease:
    """Heartbeat under a verified fence; the token never changes and the first identity is kept."""
    verify_fence(lease, assignment, claim, now)
    identity = lease.process_identity if lease.process_identity is not None else process_identity
    return dataclasses.replace(lease, expires_at=now + ttl, last_heartbeat_at=now, process_identity=identity)
