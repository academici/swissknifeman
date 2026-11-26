"""Pure recovery authority and rolling circuit breaker rules (§5.17)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.session import (
    Fresh,
    Resume,
    SessionFacts,
    SessionFingerprint,
    decide_session,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from typing import Literal

    from skm.kernel.ids import AttemptId, FileVersionId, RunId, TaskId
    from skm.modules.execution.domain.contracts import ExecutionPolicy
    from skm.modules.execution.domain.ids import RecoveryRecordId, StageRecordId, StepId


@dataclass(frozen=True, slots=True)
class RecoveryRecord:
    id: RecoveryRecordId
    run_id: RunId
    task_id: TaskId
    attempt_id: AttemptId
    stage_record_id: StageRecordId
    step_id: StepId | None
    trigger: Literal["hung", "suspected_stall", "orphaned", "lease_expired"]
    steps_done: tuple[RecoveryStep, ...]
    snapshot_file_version_id: FileVersionId | None
    outcome: Literal["retried", "new_attempt", "escalated", "not_needed"] | None
    reason_codes: tuple[str, ...]
    at: datetime


def plan_recovery(facts: JsonObject, policy: ExecutionPolicy) -> tuple[RecoveryStep, ...]:
    if facts.get("legitimate_wait") is True:
        return (RecoveryStep.VERIFY_LEGIT,)
    diagnostic = tuple(RecoveryStep)[:3]
    mode = policy.get("recover", "notify")
    authorized = (
        facts.get("deadline_expired") is True
        or facts.get("authorized_cancel") is True
        or (facts.get("lease_expired") is True and facts.get("identity_verified") is True)
    )
    if mode == "notify" or not authorized:
        return diagnostic
    if mode not in {"resume", "stop_only"}:
        raise ValueError("unknown supervisor recovery mode")
    steps = list(RecoveryStep)
    if facts.get("identity_verified") is not True:
        steps = [s for s in steps if s not in {RecoveryStep.COOPERATIVE_CANCEL, RecoveryStep.KILL_GROUP}]
    return tuple(s for s in steps if mode == "resume" or s is not RecoveryStep.RETRY_STEP)


def breaker_open(records: Sequence[RecoveryRecord], policy: ExecutionPolicy, now: datetime) -> bool:
    since = now - timedelta(seconds=int(str(policy.get("window_seconds", 3600))))
    return sum(r.outcome in {"retried", "new_attempt"} and since < r.at <= now for r in records) >= int(
        str(policy.get("max_recoveries", 2))
    )


class RecoveryStep(StrEnum):
    VERIFY_LEGIT = "verify_legit"
    SNAPSHOT = "snapshot"
    VERIFY_IDENTITY = "verify_identity"
    COOPERATIVE_CANCEL = "cooperative_cancel"
    KILL_GROUP = "kill_group"
    RECONCILE = "reconcile"
    RETRY_STEP = "retry_step"


def safe_session_lost(
    nxt: SessionFingerprint,
    facts: SessionFacts,
    *,
    before_turn: bool,
    fallback_used: bool,
    external_effect_unknown: bool,
) -> Fresh | None:
    """One in-step fallback requires positive pre-turn evidence and an unchanged resume binding.

    None means ordinary retry/reconcile; it never authorizes repeating an uncertain effect.
    """
    if not before_turn or fallback_used or external_effect_unknown:
        return None
    if facts.admission_allows_resume.required:
        raise error_for(ErrorCode.ADMISSION_REFUSED, "required resume session was lost")
    decision = decide_session(nxt, facts)
    return Fresh("SESSION_LOST", True) if isinstance(decision, Resume) else None
