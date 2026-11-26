"""Own payload schema inventory and the domain names of execution events (execution §9).

Event DTOs and their registration belong to codegen and the application layer; the domain only names
which event a transition records, so the transition tables can state it and tests can check K3:
``TaskAccepted`` is recorded only on entering the terminal ``accepted`` status, while the acceptance
decision taken before integration is ``AcceptanceDecided``.
"""

from __future__ import annotations

import re
from enum import StrEnum

__all__ = ["EVENT_TYPES", "ExecutionEvent", "event_type"]

EVENT_TYPES: tuple[str, ...] = (
    "urn:skm:execution:event:acceptance-decided:v1",
    "urn:skm:execution:event:assignment-leased:v1",
    "urn:skm:execution:event:attempt-ownership-lost:v1",
    "urn:skm:execution:event:attempt-started:v1",
    "urn:skm:execution:event:autopilot-state-changed:v1",
    "urn:skm:execution:event:budget-exhausted:v1",
    "urn:skm:execution:event:check-completed:v1",
    "urn:skm:execution:event:decision-answered:v1",
    "urn:skm:execution:event:decision-requested:v1",
    "urn:skm:execution:event:deviation-accepted:v1",
    "urn:skm:execution:event:external-effect-outcome-unknown:v1",
    "urn:skm:execution:event:external-effect-recorded:v1",
    "urn:skm:execution:event:followups-created:v1",
    "urn:skm:execution:event:integration-completed:v1",
    "urn:skm:execution:event:lease-expired:v1",
    "urn:skm:execution:event:manual-verdict-recorded:v1",
    "urn:skm:execution:event:monitor-evaluated:v1",
    "urn:skm:execution:event:output-sealed:v1",
    "urn:skm:execution:event:readiness-reported:v1",
    "urn:skm:execution:event:recovery-circuit-opened:v1",
    "urn:skm:execution:event:review-completed:v1",
    "urn:skm:execution:event:review-requested:v1",
    "urn:skm:execution:event:run-cancelled:v1",
    "urn:skm:execution:event:run-created:v1",
    "urn:skm:execution:event:run-finished:v1",
    "urn:skm:execution:event:run-paused:v1",
    "urn:skm:execution:event:run-reconfigured:v1",
    "urn:skm:execution:event:run-resumed:v1",
    "urn:skm:execution:event:run-started:v1",
    "urn:skm:execution:event:run-waiting:v1",
    "urn:skm:execution:event:runtime-start-admitted:v1",
    "urn:skm:execution:event:stage-completed:v1",
    "urn:skm:execution:event:stage-recovered:v1",
    "urn:skm:execution:event:stage-started:v1",
    "urn:skm:execution:event:step-observation-recorded:v1",
    "urn:skm:execution:event:task-accepted:v1",
    "urn:skm:execution:event:task-assigned:v1",
    "urn:skm:execution:event:task-created:v1",
    "urn:skm:execution:event:task-failed:v1",
    "urn:skm:execution:event:task-ready:v1",
    "urn:skm:execution:event:task-rework-required:v1",
    "urn:skm:execution:event:task-skipped:v1",
    "urn:skm:execution:event:task-wait-changed:v1",
)


class ExecutionEvent(StrEnum):
    """Domain names of the events a run, task or attempt transition records."""

    ACCEPTANCE_DECIDED = "AcceptanceDecided"
    ATTEMPT_OWNERSHIP_LOST = "AttemptOwnershipLost"
    ATTEMPT_STARTED = "AttemptStarted"
    DECISION_ANSWERED = "DecisionAnswered"
    DECISION_REQUESTED = "DecisionRequested"
    FOLLOWUPS_CREATED = "FollowupsCreated"
    INTEGRATION_COMPLETED = "IntegrationCompleted"
    LEASE_EXPIRED = "LeaseExpired"
    MANUAL_VERDICT_RECORDED = "ManualVerdictRecorded"
    RUN_CANCELLED = "RunCancelled"
    RUN_CREATED = "RunCreated"
    RUN_FINISHED = "RunFinished"
    RUN_PAUSED = "RunPaused"
    RUN_RESUMED = "RunResumed"
    RUN_STARTED = "RunStarted"
    RUN_WAITING = "RunWaiting"
    STAGE_COMPLETED = "StageCompleted"
    TASK_ACCEPTED = "TaskAccepted"
    TASK_ASSIGNED = "TaskAssigned"
    TASK_CREATED = "TaskCreated"
    TASK_FAILED = "TaskFailed"
    TASK_READY = "TaskReady"
    TASK_REWORK_REQUIRED = "TaskReworkRequired"
    TASK_SKIPPED = "TaskSkipped"
    TASK_WAIT_CHANGED = "TaskWaitChanged"


def event_type(event: ExecutionEvent) -> str:
    """The payload schema URN of ``event`` (``TaskAccepted`` → ``…:event:task-accepted:v1``)."""
    slug = re.sub(r"(?<!^)(?=[A-Z])", "-", event.value).lower()
    urn = f"urn:skm:execution:event:{slug}:v1"
    if urn not in EVENT_TYPES:
        raise KeyError(urn)
    return urn
