"""Checked owner snapshots and stage cancellation with the standard reap barrier."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import AttemptId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application._worker_protocol import verify_current_lease
from skm.modules.execution.domain.assignment import Assignment, AssignmentState
from skm.modules.execution.domain.attempt import SelectedStage
from skm.modules.execution.domain.lease import Lease, WorkerClaim
from skm.modules.execution.domain.session import RouteRef
from skm.modules.execution.domain.stage_record import StageRecord
from skm.modules.execution.domain.step import AttemptStep, StepState
from skm.modules.execution.ports import AssignmentRepository, RunRepository, StageRepository, StepRepository


@dataclass(frozen=True, slots=True)
class LiveOwner:
    assignment: Assignment
    lease: Lease
    stage: StageRecord | None
    step: AttemptStep | None


def current_owner(uow: UnitOfWork, attempt_id: AttemptId | None, *, lock: bool = False) -> LiveOwner | None:
    if attempt_id is None:
        return None
    assignments = uow.repo(AssignmentRepository)
    stages = uow.repo(StageRepository)
    for observed in assignments.for_attempt(attempt_id):
        if observed.reconcile_effect_id is not None or observed.state is not AssignmentState.LEASED:
            continue
        assignment = assignments.get(observed.id, for_update=lock)
        lease = assignments.lease(assignment.id, for_update=lock)
        now = uow.repo(RunRepository).now()
        if lease is None or lease.expires_at <= now or lease.fencing_token != assignment.last_fencing_token:
            continue
        stage = stages.started_without_result(attempt_id)
        if stage is not None and stage.fencing_token != lease.fencing_token:
            stage = None
        if stage is not None and lock:
            stage = stages.get(stage.id, for_update=True)
        if lock:
            claim = WorkerClaim(assignment.id, attempt_id, lease.worker_id, lease.fencing_token)
            verify_current_lease(uow, assignment, lease, claim, now)
        step = (
            None
            if stage is None
            else next(
                (
                    item
                    for item in uow.repo(StepRepository).for_stage(stage.id)
                    if item.state is StepState.STARTED
                ),
                None,
            )
        )
        return LiveOwner(assignment, lease, stage, step)
    return None


def controlled_selection(selected: SelectedStage, pending: JsonObject) -> SelectedStage:
    route, actor = pending.get("reroute_task"), pending.get("override_actor")
    if isinstance(route, dict):
        selected = replace(
            selected, route_override=RouteRef(str(route["runtime_id"]), str(route["model"]), None)
        )
    if isinstance(actor, dict):
        selected = replace(selected, params={**selected.params, "operator_profile": actor["profile"]})
    return selected


def cancellation_code(stage: StageRecord) -> str | None:
    code = (stage.outcome or {}).get("cancel_code")
    return code if isinstance(code, str) else None


def require_not_stopping(stage: StageRecord) -> None:
    if cancellation_code(stage):
        raise error_for(ErrorCode.LEASE_LOST, "stage is pending cancellation and reconciliation")


def request_stop(
    uow: UnitOfWork,
    ctx: Any,
    stage: StageRecord,
    assignment: Assignment,
    lease: Lease,
    now: datetime,
    *,
    code: str,
) -> bool:
    stages = uow.repo(StageRepository)
    grace = int(value(ctx.config, "execution.supervisor.grace_seconds", 60) or 60)
    if not stages.request_cancel(
        stage.id,
        assignment.id,
        lease.fencing_token,
        now,
        now,
        grace_deadline_at=now + timedelta(seconds=grace),
    ):
        return False
    requested = stages.get(stage.id, for_update=True)
    stages.save(replace(requested, outcome={**(requested.outcome or {}), "cancel_code": code}))
    return True
