"""Stage timeout cancellation and reap receipts, as both execution stores record them."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from skm.modules.execution.domain.health import reap_proven
from skm.modules.execution.domain.ids import RecoveryRecordId
from skm.modules.execution.domain.recovery import RecoveryRecord, RecoveryStep
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES, StageRecord

if TYPE_CHECKING:
    from skm.modules.execution.domain.assignment import Assignment, WorkerOffer
    from skm.modules.execution.domain.ids import AssignmentId
    from skm.modules.execution.domain.lease import Lease

__all__ = [
    "reap_barrier_satisfied",
    "reap_receipt",
    "timeout_cancel_outcome",
    "timeout_cancel_requested",
]


def reap_barrier_satisfied(stage: StageRecord | None, reap_step_id: object, worker: WorkerOffer) -> bool:
    """The worker reported the awaited step (if any) as reaped and proved every stage process dead."""
    return (
        reap_step_id is None or any(str(p.get("unit_id")) == str(reap_step_id) for p in worker.reaped_steps)
    ) and reap_proven(stage, worker)


def timeout_cancel_outcome(
    stage: StageRecord,
    assignment: Assignment,
    lease: Lease | None,
    *,
    assignment_id: AssignmentId,
    fencing_token: int,
    deadline_at: datetime,
    grace_deadline_at: datetime,
    now: datetime,
) -> dict[str, Any] | None:
    """The stage outcome recording a timeout cancel request, or ``None`` when it does not apply.

    The stage must be active under the same fencing token as the leased assignment of its attempt,
    and no cancel may have been requested yet.
    """
    if (
        stage.state not in ACTIVE_STAGE_STATES
        or stage.fencing_token != fencing_token
        or assignment.attempt_id != stage.attempt_id
        or assignment.state.value != "leased"
        or lease is None
        or lease.fencing_token != fencing_token
    ):
        return None
    outcome: dict[str, Any] = dict(stage.outcome or {})
    if outcome.get("timeout_requested_at"):
        return None
    outcome.update(
        timeout_requested_at=now.isoformat(),
        timeout_deadline_at=deadline_at.isoformat(),
        timeout_grace_deadline_at=grace_deadline_at.isoformat(),
        timeout_assignment_id=str(assignment_id),
        timeout_fencing_token=fencing_token,
    )
    return outcome


def timeout_cancel_requested(stage: StageRecord | None, fencing_token: int) -> bool:
    """A timeout cancel was requested for the open stage under ``fencing_token``."""
    outcome: Any = {} if stage is None else stage.outcome or {}
    return bool(
        stage
        and outcome.get("timeout_requested_at")
        and outcome.get("timeout_fencing_token") == fencing_token
    )


def reap_receipt(receipt_id: UUID, stage: StageRecord, now: datetime) -> RecoveryRecord:
    """The recovery record proving the OS stopped every process of a lease-expired stage."""
    return RecoveryRecord(
        RecoveryRecordId(receipt_id),
        stage.run_id,
        stage.task_id,
        stage.attempt_id,
        stage.id,
        None,
        "lease_expired",
        (RecoveryStep.VERIFY_IDENTITY,),
        None,
        "not_needed",
        ("OS_STOP_PROVEN",),
        now,
    )
