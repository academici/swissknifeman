"""Atomic worker history and bounded, neutral runtime observations."""

from typing import Any
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._incident_gate import honor_boundary
from skm.modules.execution.application._primitives import schemas
from skm.modules.execution.application._worker_dtos import canonical_bytes, digest, document
from skm.modules.execution.domain.step import StepState, finish_step
from skm.modules.execution.ports import StepRepository


def refs(*items: tuple[str, Any]) -> list[Any]:
    return [{"kind": kind, "id": str(identity)} for kind, identity in items]


def stage_started(
    uow: UnitOfWork, fenced: Any, stage: Any, selected: Any, loaded: Any, steps: Any = ()
) -> None:
    emit(
        uow,
        fenced.run,
        "stage-started",
        {
            "task_id": str(fenced.task.id),
            "attempt_id": str(fenced.attempt.id),
            "stage_record_id": str(stage.id),
            "stage_id": stage.stage_id,
            "stage_type": stage.stage_type,
            "round_no": stage.round_no,
            "mode": stage.mode.value,
            "skipped_stage_ids": [],
            "input_digest": stage.input_digest,
            "input_output_id": None if selected.input_output_id is None else str(selected.input_output_id),
            "retry_of_id": None if selected.retry_of_id is None else str(selected.retry_of_id),
            "feedback_refs": document(selected.feedback_refs),
            "step_refs": [
                {
                    "step_id": str(s.id),
                    "role": s.role.value,
                    "purpose": s.purpose.value,
                    "seq": s.seq,
                    "parent_step_id": None if s.parent_step_id is None else str(s.parent_step_id),
                    "context_manifest_id": str(s.context_manifest_id),
                    "route_snapshot": document(s.route_snapshot),
                }
                for s in steps
            ],
            "session_mode": steps[0].session_mode if steps else None,
            "effective_config_digest": loaded.effective_config_digest,
            "reconfiguration_ids": [str(r) for r in loaded.reconfiguration_ids],
        },
        cause("stage_outcome", refs=refs(("stage", stage.id))),
    )


def precheck_observations(steps: Any, observations: Any) -> dict[Any, Any]:
    if len(observations) > 8:
        raise error_for(ErrorCode.SCHEMA_INVALID, "at most eight runtime observations")
    active = {s.id: s for s in steps if s.state is StepState.STARTED}
    result: dict[Any, Any] = {}
    for item in observations:
        step_id = UUID(item["step_id"])
        if step_id not in active or step_id in result:
            raise error_for(
                ErrorCode.INVALID_TRANSITION, "observation target is duplicate, foreign or terminal"
            )
        observation = item["observation"]
        if len(canonical_bytes(observation)) > 16_384:
            raise error_for(ErrorCode.SCHEMA_INVALID, "runtime observation exceeds 16 KiB")

        schemas().require_valid("urn:skm:runtimes:runtime-observation:v1", observation)
        if observation["request_id"] != str(step_id):
            raise error_for(ErrorCode.SCHEMA_INVALID, "observation request ID differs from target step")
        result[step_id] = observation
    return result


def close_steps(  # noqa: PLR0913 -- atomic stage data and terminal metadata
    uow: UnitOfWork,
    fenced: Any,
    stage: Any,
    steps: Any,
    *,
    successful: bool,
    observations: Any = None,
    result: Any = None,
    code: str | None = None,
    usage: Any = None,
    activity: Any = None,
    updates: Any = None,
) -> list[Any]:
    from dataclasses import replace

    closed: list[Any] = []
    for step in steps:
        if step.state is not StepState.STARTED:
            closed.append(step)
            continue
        observation: Any = None if observations is None else observations.get(step.id)
        updated = finish_step(
            step,
            state=StepState.SUCCEEDED if successful else StepState.FAILED,
            now=fenced.now,
            result=result if successful else None,
            error_code=code,
        )
        updated = replace(
            updated,
            runtime_observation=observation,
            usage=usage if step.id == steps[0].id else None,
            activity=activity,
            **({} if updates is None else updates.get(step.id, {})),
        )
        uow.repo(StepRepository).save(updated)
        closed.append(updated)
        emit(
            uow,
            fenced.run,
            "step-observation-recorded",
            {
                "task_id": str(stage.task_id),
                "attempt_id": str(stage.attempt_id),
                "stage_record_id": str(stage.id),
                "step_id": str(step.id),
                "role": step.role.value,
                "purpose": step.purpose.value,
                "seq": step.seq,
                "parent_step_id": None if step.parent_step_id is None else str(step.parent_step_id),
                "context_manifest_id": str(step.context_manifest_id),
                "route_snapshot": document(step.route_snapshot),
                "observation": observation,
                "observation_digest": None if observation is None else digest(observation),
                "binding_consistency": binding_consistency(step.route_snapshot, observation),
                "executed_by": executed_by(step.route_snapshot, observation),
            },
            cause("observation", refs=refs(("step", step.id))),
        )
    return closed


def binding_consistency(snapshot: Any, observation: Any) -> str:
    if snapshot is None or observation is None:
        return "unavailable"
    binding = observation["binding"]
    for key in ("runtime_id", "runtime_version", "adapter_version", "executable_sha256", "verification_key"):
        expected = snapshot.get(key) if key != "runtime_id" else snapshot["resolved"][key]
        if binding.get(key) is not None and expected is not None and binding[key] != expected:
            return "mismatch"
    return "matched"


def observed_binding(snapshot: Any, observation: Any) -> Any:
    if binding_consistency(snapshot, observation) != "matched":
        return None
    binding = observation["binding"]
    if binding["model_source"] != (
        "unavailable" if binding["provider_reported_model"] is None else "provider_stream"
    ):
        return None
    return binding


def executed_by(snapshot: Any, observation: Any) -> str | None:
    binding = observed_binding(snapshot, observation)
    if binding is None:
        return None
    runtime, model, effort = (
        binding["runtime_id"],
        binding["provider_reported_model"],
        binding.get("observed_effort"),
    )
    if model is not None and effort is not None:
        return f"{runtime}/{model}/{effort}"
    return runtime if model is None else f"{runtime}/{model}"


def stage_completed(uow: UnitOfWork, fenced: Any, stage: Any, steps: Any, *, diagnostics: Any = ()) -> None:
    outcome: Any = stage.outcome or {}
    emit(
        uow,
        fenced.run,
        "stage-completed",
        {
            "task_id": str(stage.task_id),
            "attempt_id": str(stage.attempt_id),
            "stage_record_id": str(stage.id),
            "stage_id": stage.stage_id,
            "stage_type": stage.stage_type,
            "state": stage.state.value,
            "outcome_kind": None if stage.outcome_kind is None else stage.outcome_kind.value,
            "error_code": stage.error_code,
            "diagnostics": document(diagnostics),
            "step_ids": [str(s.id) for s in steps],
            "step_states": [{"step_id": str(s.id), "state": s.state.value} for s in steps],
            "output_ids": [],
            "check_execution_ids": [],
            "review_ids": [],
            "decision_ids": [],
            "effect_ids": list(outcome.get("effect_ids", ())),
            "observation_refs": [
                {"step_id": str(s.id), "observation_digest": digest(s.runtime_observation)}
                for s in steps
                if s.runtime_observation is not None
            ],
            "timing": {
                "started_at": stage.started_at.isoformat(),
                "finished_at": stage.finished_at.isoformat(),
                "basis": "db_transition",
            },
            "coverage": "unavailable"
            if all(s.runtime_observation is None for s in steps)
            else "complete"
            if all(
                s.runtime_observation is not None
                and s.runtime_observation["capture"]["coverage"] == "complete"
                and binding_consistency(s.route_snapshot, s.runtime_observation) != "mismatch"
                for s in steps
            )
            else "partial",
        },
        cause("stage_outcome", refs=refs(("stage", stage.id))),
    )

    if steps:
        honor_boundary(uow, fenced, stage, steps)


def runtime_admitted(uow: UnitOfWork, fenced: Any, stage: Any, step: Any) -> None:
    emit(
        uow,
        fenced.run,
        "runtime-start-admitted",
        {
            "task_id": str(stage.task_id),
            "attempt_id": str(stage.attempt_id),
            "assignment_id": str(fenced.assignment.id),
            "stage_record_id": str(stage.id),
            "fencing_token": fenced.claim.fencing_token,
            "step_ids": [str(step.id)],
            "step_bindings": [
                {
                    "step_id": str(step.id),
                    "context_manifest_id": str(step.context_manifest_id),
                    "effective_config_digest": step.route_snapshot["effective_config_digest"],
                    "route_snapshot_digest": digest(step.route_snapshot),
                }
            ],
        },
        cause("stage_outcome", refs=refs(("stage", stage.id))),
    )
