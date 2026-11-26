"""Assignments and worker requirements (execution §4.9).

An assignment offers one attempt to one matching worker. Terminal rows (``completed``, ``expired``,
``cancelled``) never come back: a continuation of the same attempt is a new row (``reissue``). Only
``retry_later`` returns a leased row to ``available`` (same row, later ``available_at``). L2 reap rows
name the interrupted stage record (all unit kinds) and, for agent stages only, the step.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from typing import Literal

    from skm.kernel.ids import AttemptId, HostId, RunId, TaskId, WorkerId, WorkspaceId
    from skm.modules.execution.domain.environment import EnvironmentKind
    from skm.modules.execution.domain.ids import AssignmentId, ExternalEffectId, StageRecordId, StepId
    from skm.modules.execution.domain.session import RouteRef
    from skm.modules.execution.domain.workflow.stage_inputs import StageMode

__all__ = [
    "ASSIGNMENT_TRANSITIONS",
    "TERMINAL_ASSIGNMENT_STATES",
    "Assignment",
    "AssignmentState",
    "StageInstruction",
    "WorkerOffer",
    "WorkerRequirements",
    "reissue",
    "requirement_mismatches",
    "retry_later",
    "transition_assignment",
    "worker_matches",
]


class AssignmentState(StrEnum):
    AVAILABLE = "available"
    LEASED = "leased"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


TERMINAL_ASSIGNMENT_STATES: Final = frozenset(
    {AssignmentState.COMPLETED, AssignmentState.EXPIRED, AssignmentState.CANCELLED}
)

_S = AssignmentState
# (source, target) pairs of §4.9; "— -> available" is the creation of a row
ASSIGNMENT_TRANSITIONS: Final = frozenset(
    {
        (_S.AVAILABLE, _S.LEASED),  # claim_assignment
        (_S.LEASED, _S.AVAILABLE),  # release_assignment(retry_later), same row
        (_S.LEASED, _S.COMPLETED),  # release(waiting|done|paused|cancelled), non-worker NextAction, task end
        (_S.LEASED, _S.EXPIRED),  # expire_leases; continuation is a new row
        (_S.AVAILABLE, _S.CANCELLED),  # cancel_run, carry_forward, pause_run, rule L3
        (_S.LEASED, _S.CANCELLED),  # cancel_run, carry_forward_result (never pause_run)
    }
)


@dataclass(frozen=True, slots=True)
class WorkerRequirements:
    capabilities: frozenset[str]
    required_host_id: HostId | None
    required_labels: frozenset[str]
    environment_kind: EnvironmentKind
    isolation_profiles: frozenset[str]


@dataclass(frozen=True, slots=True)
class Assignment:
    id: AssignmentId
    run_id: RunId
    task_id: TaskId
    attempt_id: AttemptId
    workspace_id: WorkspaceId
    state: AssignmentState
    available_at: datetime
    requirements: WorkerRequirements
    priority: int
    last_fencing_token: int
    reconcile_effect_id: ExternalEffectId | None
    reap_stage_record_id: StageRecordId | None
    reap_step_id: StepId | None
    created_at: datetime
    row_version: int

    def __post_init__(self) -> None:
        problems: list[str] = []
        if self.priority < 0 or self.last_fencing_token < 0 or self.row_version < 1:
            problems.append("priority >= 0, last_fencing_token >= 0, row_version >= 1")
        pinned = self.requirements.required_host_id is not None
        if self.reap_step_id is not None and self.reap_stage_record_id is None:
            problems.append("reap_step_id (agent only) comes with reap_stage_record_id")
        if self.reap_stage_record_id is not None and not pinned:
            problems.append("an L2 reap assignment is pinned to the environment host")
        if self.reconcile_effect_id is not None and (not pinned or self.reap_stage_record_id is not None):
            problems.append("a reconcile assignment is pinned to its host and is not a reap barrier")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "assignment invariants violated: " + "; ".join(problems),
                details={"assignment_id": str(self.id), "violations": list(problems)},
            )


@dataclass(frozen=True, slots=True)
class StageInstruction:
    kind: Literal["run_stage", "release", "wait"]
    stage_id: str | None = None
    stage_type: str | None = None
    mode: StageMode | None = None
    round_no: int | None = None
    params: JsonObject | None = None
    input_digest: str | None = None
    not_before: datetime | None = None
    route_override: RouteRef | None = None
    environment: JsonObject | None = None
    release_reason: str | None = None


@dataclass(frozen=True, slots=True)
class WorkerOffer:
    worker_id: WorkerId
    host_id: HostId
    capabilities: frozenset[str]
    labels: frozenset[str]
    environment_kinds: frozenset[EnvironmentKind]
    isolation_profiles: frozenset[str]
    reaped_steps: tuple[JsonObject, ...]
    offered_runtimes: frozenset[str] = frozenset()


def requirement_mismatches(requirements: WorkerRequirements, offer: WorkerOffer) -> tuple[str, ...]:
    """Every requirement the offer does not meet (empty: the worker fits); the names feed diagnostics."""
    found: list[str] = []
    if not requirements.capabilities <= offer.capabilities:
        found.append("capabilities")
    if requirements.required_host_id not in (None, offer.host_id):
        found.append("required_host_id")
    if not requirements.required_labels <= offer.labels:
        found.append("required_labels")
    if requirements.environment_kind not in offer.environment_kinds:
        found.append("environment_kind")
    if not requirements.isolation_profiles <= offer.isolation_profiles:
        found.append("isolation_profiles")
    return tuple(found)


def worker_matches(requirements: WorkerRequirements, offer: WorkerOffer) -> bool:
    """capabilities ⊆, host ∈ {None, worker host}, labels ⊆, environment kind ∈, isolation profiles ⊆."""
    return not requirement_mismatches(requirements, offer)


def transition_assignment(assignment: Assignment, to: AssignmentState) -> Assignment:
    """Apply one change of §4.9; a terminal row never changes again (``INVALID_TRANSITION``)."""
    to = AssignmentState(to)
    if (assignment.state, to) not in ASSIGNMENT_TRANSITIONS:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            f"assignment cannot go from {assignment.state} to {to}",
            details={"assignment_id": str(assignment.id), "from": assignment.state.value, "to": to.value},
        )
    return dataclasses.replace(assignment, state=to, row_version=assignment.row_version + 1)


def retry_later(assignment: Assignment, *, available_at: datetime) -> Assignment:
    """``release_assignment(retry_later)``: the same row becomes available again after the backoff.

    The token counter stays, so the next claim of this row gets a greater token.
    """
    released = transition_assignment(assignment, AssignmentState.AVAILABLE)
    return dataclasses.replace(released, available_at=available_at)


def reissue(
    previous: Assignment,
    *,
    new_id: AssignmentId,
    now: datetime,
    available_at: datetime | None = None,
    requirements: WorkerRequirements | None = None,
    reap_stage_record_id: StageRecordId | None = None,
    reap_step_id: StepId | None = None,
) -> Assignment:
    """A new ``available`` row continuing the same attempt after ``previous`` ended.

    The old row stays terminal; the new row continues the token sequence of the attempt so the fence
    stays monotonic, and an old claim fails on the assignment id anyway. An L2 barrier names the stage
    record and, for an agent stage, its step.
    """
    if previous.state not in TERMINAL_ASSIGNMENT_STATES:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "only a finished assignment is reissued",
            details={"assignment_id": str(previous.id), "state": previous.state.value},
        )
    if new_id == previous.id:
        raise error_for(ErrorCode.INVALID_TRANSITION, "a reissue is a new assignment row")
    return Assignment(
        id=new_id,
        run_id=previous.run_id,
        task_id=previous.task_id,
        attempt_id=previous.attempt_id,
        workspace_id=previous.workspace_id,
        state=AssignmentState.AVAILABLE,
        available_at=now if available_at is None else available_at,
        requirements=previous.requirements if requirements is None else requirements,
        priority=previous.priority,
        last_fencing_token=previous.last_fencing_token,
        reconcile_effect_id=None,
        reap_stage_record_id=reap_stage_record_id,
        reap_step_id=reap_step_id,
        created_at=now,
        row_version=1,
    )
