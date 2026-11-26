"""Persist workflow interventions under the same run lock as their continuation."""

from dataclasses import replace
from typing import Any
from uuid import UUID

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._live_control import current_owner
from skm.modules.execution.application._worker_dtos import digest, document
from skm.modules.execution.application.loaders import find_task_work_policy
from skm.modules.execution.domain.blocking_reason import BlockingCode
from skm.modules.execution.domain.decision_request import DecisionKind
from skm.modules.execution.domain.ids import StepId
from skm.modules.execution.domain.live_control import IncidentGate
from skm.modules.execution.domain.run import RunStatus, pause
from skm.modules.execution.domain.workflow.actions import ESCALATION_OPTIONS, Escalate, RunStage
from skm.modules.execution.domain.workflow.definition import StageType
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.ports import RunRepository, StageRepository, StepRepository, TaskRepository

REPAIR_ACTION_DIGEST = "REPAIR_ACTION_DIGEST"
REPAIR_REVIEW_REQUIRED = "REPAIR_REVIEW_REQUIRED"


def journal(uow: UnitOfWork, ctx: Any, task_id: Any, reason: str, details: JsonObject) -> None:
    repo = uow.repo(StepRepository)
    if any(g.details == details for g in repo.incident_gates(task_id)):
        return
    repo.add_incident_gate(
        IncidentGate(
            ctx.ids.new_id(),
            task_id,
            None,
            None,
            "steer_task",
            ctx.actor.principal_id,
            reason,
            details,
            uow.repo(RunRepository).now(),
        )
    )


def is_repair(stage: Any) -> bool:
    return (
        stage.mode in {StageMode.REWORK, StageMode.FINAL_CORRECTION} or REPAIR_ACTION_DIGEST in stage.params
    )


def repair_action(uow: UnitOfWork, state: Any, stage: Any) -> JsonObject:
    """Bind the executable instruction to the original task, policy and input candidate."""
    work_policy = find_task_work_policy(uow, state.task.id)
    return {
        "work_policy_digest": None if work_policy is None else work_policy.digest,
        "executor_route": document(state.attempt.executor_route),
        "task_id": str(state.task.id),
        "attempt_id": str(state.attempt.id),
        "revision_id": str(state.run.revision_id),
        "workflow_id": str(state.run.workflow_resource_version_id),
        "input_output_id": str(state.attempt.current_output_id),
        "scope_digest": digest(
            {"declared": state.task.declared_write_scope, "granted": state.task.granted_write_scope}
        ),
        "policy_digest": digest(state.effective_policy),
        "review_mode": state.task.review_mode.value,
        "review_profile": state.task.review_profile,
        "stage_id": stage.stage_id,
        "stage_type": str(stage.stage_type),
        "mode": stage.mode.value,
        "round": stage.round_no,
        "feedback": document(
            (stage.feedback or FeedbackRefs()) if isinstance(stage, RunStage) else stage.feedback_refs
        ),
        "route": document(stage.route_override),
        "params": {
            k: v for k, v in stage.params.items() if k not in {REPAIR_ACTION_DIGEST, REPAIR_REVIEW_REQUIRED}
        },
    }


def repair_incident(state: Any, action: RunStage) -> str:
    """Group repeated evidence by the stable plan checks and logical findings of this task."""
    return digest(
        {
            "task": str(state.task.id),
            "executor_stage": action.stage_id,
            "checks": sorted(
                {
                    str(c.check_spec_id)
                    for c in state.checks
                    if c.required and c.state.value in {"failed", "error", "unknown"}
                }
            ),
            "findings": sorted(
                {f.finding_key for f in state.findings if f.state.value in {"open", "confirmed"}}
            ),
        }
    )


def gate_action(uow: UnitOfWork, ctx: Any, state: Any, action: Any) -> Any:
    if not state.run.autopilot:
        return action
    base: JsonObject = {
        "attempt_id": str(state.attempt.id),
        "source_stage_id": str(state.history.entries[-1].record.id) if state.history.entries else None,
    }
    if isinstance(action, RunStage) and is_repair(action):
        incident = repair_incident(state, action)
        base["incident_key"] = incident
        marker = digest(repair_action(uow, state, action))
        markers = {
            REPAIR_ACTION_DIGEST: marker,
            REPAIR_REVIEW_REQUIRED: state.task.review_mode.value == "required",
        }
        gates = [
            g
            for g in uow.repo(StepRepository).incident_gates(state.task.id)
            if g.details.get("branch") == "B" and g.details.get("incident_key") == incident
        ]
        if any(g.details.get(REPAIR_ACTION_DIGEST) == marker for g in gates):
            return replace(action, params={**action.params, **markers})
        if len(gates) < 2 and all(g.details.get("source_stage_id") != base["source_stage_id"] for g in gates):
            journal(
                uow,
                ctx,
                state.task.id,
                "repair",
                {**base, "branch": "B", "authority": "coordinator", **markers},
            )
            return replace(action, params={**action.params, **markers})
        action = Escalate(
            DecisionKind.ESCALATION,
            "REPAIR_LIMIT_REACHED",
            {"code": "REPAIR_LIMIT_REACHED", "options": list(ESCALATION_OPTIONS)},
            BlockingCode.WAITING_OWNER,
        )
    if isinstance(action, Escalate):
        journal(
            uow,
            ctx,
            state.task.id,
            action.code,
            {**base, "branch": "C", "authority": "owner", "code": action.code},
        )
    elif isinstance(action, RunStage) and action.mode in {StageMode.RETRY, StageMode.RESUME_INTERRUPTED}:
        journal(
            uow,
            ctx,
            state.task.id,
            action.mode.value,
            {**base, "branch": "A", "authority": "coordinator", "action": action.mode.value},
        )
    return action


def verify_repair(uow: UnitOfWork, ctx: Any, state: Any, selected: Any) -> Any:
    """Seal a pre-upgrade continuation on first use and verify subsequent admissions."""
    gates = [
        g for g in uow.repo(StepRepository).incident_gates(state.task.id) if g.details.get("branch") == "B"
    ]
    if (
        REPAIR_ACTION_DIGEST not in selected.params
        and not gates
        and selected.input_output_id == state.attempt.current_output_id
    ):
        legacy = RunStage(
            selected.stage_id,
            StageType(selected.stage_type),
            selected.mode,
            selected.round_no,
            selected.params,
            selected.not_before,
            selected.route_override,
            selected.feedback_refs,
        )
        sealed = gate_action(uow, ctx, state, legacy)
        return replace(selected, params=sealed.params)
    marker = selected.params.get(REPAIR_ACTION_DIGEST)
    if (
        selected.input_output_id != state.attempt.current_output_id
        or marker != digest(repair_action(uow, state, selected))
        or not any(
            g.details.get(REPAIR_ACTION_DIGEST) == marker
            and g.details.get(REPAIR_REVIEW_REQUIRED) is selected.params.get(REPAIR_REVIEW_REQUIRED)
            for g in gates
        )
    ):
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "Repair instruction differs from the authorized action",
            details={"reason": REPAIR_ACTION_DIGEST},
        )
    return selected


def bind_repair_output(
    uow: UnitOfWork, ctx: Any, fenced: Any, output: Any, previous: Any, reviewer_fix: bool
) -> None:
    """Bind the sealed output to the admitted repair, including a reviewer's authorized successor."""
    if not fenced.run.autopilot or output.produced_by_step_id is None:
        return
    repo = uow.repo(StepRepository)
    marker = repo.get(output.produced_by_step_id).admission.get(REPAIR_ACTION_DIGEST)
    if marker is None and reviewer_fix and previous is not None:
        marker = next(
            (
                g.details.get(REPAIR_ACTION_DIGEST)
                for g in repo.incident_gates(fenced.task.id)
                if g.details.get("action") == "repair_output"
                and g.details.get("output_id") == str(previous.id)
            ),
            None,
        )
    if isinstance(marker, str):
        journal(
            uow,
            ctx,
            fenced.task.id,
            "sealed repair output",
            {
                "action": "repair_output",
                "attempt_id": str(fenced.attempt.id),
                "output_id": str(output.id),
                REPAIR_ACTION_DIGEST: marker,
            },
        )


def schedule_boundary(uow: UnitOfWork, ctx: Any, state: Any, raw: str, reason: str) -> None:
    if len(reason) > 2000:
        raise error_for(ErrorCode.SCHEMA_INVALID, "stop_after reason exceeds 2000 characters")
    if state.current_run_id is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "campaign has no current run")
    run = uow.repo(RunRepository).get(state.current_run_id, for_update=True)
    repo = uow.repo(StepRepository)
    step = repo.get(StepId(UUID(raw)))
    stage = uow.repo(StageRepository).get(step.stage_record_id)
    if stage.run_id != run.id or run.project_id != state.project_id or not run.autopilot:
        raise error_for(ErrorCode.INVALID_REFERENCE, "step is outside the current campaign")
    task = uow.repo(TaskRepository).get(stage.task_id, for_update=True)
    owner = current_owner(uow, task.current_attempt_id, lock=True)
    if owner is None or owner.step is None or owner.step.id != step.id:
        raise error_for(ErrorCode.VERSION_CONFLICT, "stop_after requires the current fenced step")
    authority = "owner" if ctx.actor.kind is PrincipalKind.HUMAN else "coordinator"
    if any(
        g.stop_after == step.id
        and g.details.get("action") == "stop_after"
        and g.details.get("authority") in {authority, "owner"}
        for g in repo.incident_gates(task.id)
    ):
        return
    repo.add_incident_gate(
        IncidentGate(
            ctx.ids.new_id(),
            task.id,
            step.id,
            owner.lease.fencing_token,
            "abort_step",
            ctx.actor.principal_id,
            reason or "stop_after",
            {"action": "stop_after", "authority": authority},
            ctx.clock.now(),
        )
    )


def honor_boundary(uow: UnitOfWork, fenced: Any, stage: Any, closed: Any) -> None:
    if not fenced.run.autopilot or fenced.run.status not in {RunStatus.WAITING, RunStatus.RUNNING}:
        return
    repo = uow.repo(StepRepository)
    steps = {s.id for s in closed if s.stage_record_id == stage.id}
    # An owner can strengthen a coordinator's pending hold at the same boundary.
    for gate in sorted(
        repo.incident_gates(fenced.task.id), key=lambda g: g.details.get("authority") != "owner"
    ):
        if (
            gate.stop_after not in steps
            or gate.fencing_token != stage.fencing_token
            or gate.details.get("action") != "stop_after"
        ):
            continue
        owner = gate.details.get("authority") == "owner"
        updated = pause(
            fenced.run,
            source="owner" if owner else "system",
            reason=gate.reason,
            stop_code=None if owner else "AUTOPILOT_STOPPED",
        )
        uow.repo(RunRepository).save(updated, expected_version=fenced.run.row_version)
        emit(
            uow,
            updated,
            "run-paused",
            {
                "by": str(gate.actor_id),
                "reason": gate.reason,
                "stop_code": updated.stop_code,
                "pause_source": updated.pause_source,
            },
            cause("wait_changed"),
        )
        fenced.run = updated
        return
