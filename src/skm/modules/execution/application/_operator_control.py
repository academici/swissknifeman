"""Operator changes are journaled under the run and current worker ownership locks."""

from dataclasses import replace
from typing import Any, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import RunId, TaskId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._control import lock_run
from skm.modules.execution.application._live_control import current_owner, request_stop
from skm.modules.execution.application.loaders import load_effective_bundle
from skm.modules.execution.domain.live_control import IncidentGate
from skm.modules.execution.domain.task import TERMINAL_TASK_STATUSES
from skm.modules.execution.generated.commands import AbortStep, OverrideActor, RerouteTask, SteerTask
from skm.modules.execution.generated.results import LiveControlResult
from skm.modules.execution.ports import AttemptRepository, RunRepository, StepRepository, TaskRepository
from skm.modules.extensions import public as extensions


def handle(
    cmd: RerouteTask | OverrideActor | SteerTask | AbortStep, ctx: Any, uow: UnitOfWork
) -> LiveControlResult:
    run = lock_run(uow, RunId(cmd.run_id), cmd.expected_row_version)
    task = uow.repo(TaskRepository).get(TaskId(cmd.task_id), for_update=True)
    if task.run_id != run.id:
        raise error_for(ErrorCode.NOT_FOUND, "task does not belong to this run")
    if task.status in TERMINAL_TASK_STATUSES:
        raise error_for(ErrorCode.INVALID_TRANSITION, "task is terminal")
    if task.current_attempt_id is not None:
        uow.repo(AttemptRepository).get(task.current_attempt_id, for_update=True)
    owner = current_owner(uow, task.current_attempt_id, lock=True)
    assignment_id = owner.assignment.id if owner else None
    token = owner.lease.fencing_token if owner else None
    step_id = owner.step.id if owner and owner.step else None
    if (assignment_id, token, step_id) != (
        cmd.expected_assignment_id,
        cmd.expected_fencing_token,
        cmd.expected_step_id,
    ):
        raise error_for(ErrorCode.VERSION_CONFLICT, "task execution ownership changed")
    if not cmd.reason.strip():
        raise error_for(ErrorCode.SCHEMA_INVALID, "a nonempty reason is required")
    now = uow.repo(RunRepository).now()
    if isinstance(cmd, AbortStep):
        if owner is None or owner.stage is None or step_id is None:
            raise error_for(ErrorCode.INVALID_TRANSITION, "task has no active step to abort")
        if not request_stop(uow, ctx, owner.stage, owner.assignment, owner.lease, now, code="STEP_ABORTED"):
            raise error_for(ErrorCode.VERSION_CONFLICT, "stage cancellation is already pending")
        return _save(uow, ctx, run, task.id, "abort_step", {}, cmd.reason, token, now, stop_after=step_id)
    kind, details = _adjustment(uow, ctx, run.id, cmd)
    repo = uow.repo(StepRepository)
    repo.save_live_controls(task.id, {**repo.live_controls(task.id), kind: details})
    return _save(uow, ctx, run, task.id, kind, details, cmd.reason, token, now)


def _adjustment(
    uow: UnitOfWork, ctx: Any, run_id: RunId, cmd: RerouteTask | OverrideActor | SteerTask
) -> tuple[str, JsonObject]:
    if isinstance(cmd, RerouteTask):
        runtime, model = cmd.runtime_id.strip(), cmd.model.strip()
        if not runtime or not model:
            raise error_for(ErrorCode.SCHEMA_INVALID, "runtime and model are required")
        return "reroute_task", {"runtime_id": runtime, "model": model}
    if isinstance(cmd, OverrideActor):
        key = cmd.actor_profile.strip()
        if not key:
            raise error_for(ErrorCode.SCHEMA_INVALID, "actor profile is required")
        pinned = load_effective_bundle(uow, run_id).bundle.resource_pins.packs
        profile = extensions.resolve_resource(
            uow,
            extensions.ResourceKind.AGENT_PROFILE,
            key,
            config=ctx.config,
            pins=cast("extensions.PackPins", pinned),
        )
        return "override_actor", {"profile": key, "role": str(profile.manifest["role"])}
    if not cmd.instructions.strip():
        raise error_for(ErrorCode.SCHEMA_INVALID, "steering instructions are empty")
    return "steer_task", {"instructions": cmd.instructions.strip()}


def _save(  # noqa: PLR0913 -- audit row and response share the locked command data
    uow: UnitOfWork,
    ctx: Any,
    run: Any,
    task_id: TaskId,
    kind: str,
    details: JsonObject,
    reason: str,
    token: int | None,
    now: Any,
    *,
    stop_after: Any = None,
) -> LiveControlResult:
    gate_id: UUID = ctx.ids.new_id()
    uow.repo(StepRepository).add_incident_gate(
        IncidentGate(gate_id, task_id, stop_after, token, kind, ctx.actor.principal_id, reason, details, now)
    )
    updated = replace(run, row_version=run.row_version + 1)
    uow.repo(RunRepository).save(updated, expected_version=run.row_version)
    return LiveControlResult(
        gate_id=gate_id,
        row_version=updated.row_version,
        effective="next_step" if stop_after is None else "cancellation_requested",
    )
