"""Apply the pure acceptance invariant and retain the immutable decision before integration."""

from __future__ import annotations

from typing import Any, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._control import live_guard
from skm.modules.execution.application._events import emit
from skm.modules.execution.application._incident_gate import REPAIR_ACTION_DIGEST, REPAIR_REVIEW_REQUIRED
from skm.modules.execution.application._plain import plain
from skm.modules.execution.application._state import load_state
from skm.modules.execution.application._worker_events import observed_binding
from skm.modules.execution.application.stages.gate_facts import check_definitions
from skm.modules.execution.domain.acceptance import (
    AcceptanceReason,
    Accepted,
    NotAcceptable,
    decide_acceptance,
    record_acceptance,
)
from skm.modules.execution.domain.review import ReviewClearance
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.domain.step import is_output_author
from skm.modules.execution.domain.task import TaskKind
from skm.modules.execution.ports import AcceptanceRepository, EvidenceBindingRepository, StepRepository
from skm.modules.execution.public import StageOutcome
from skm.modules.planning import public as planning
from skm.modules.runtimes.public import observed_model_family


class AcceptanceGate:
    stage_type = "acceptance_gate"
    side = "control_plane"
    params_schema_urn = "urn:skm:execution:workflow:v1"

    def decide(self, request: Any, ctx: Any, uow: UnitOfWork) -> StageOutcome:
        state, _ = load_state(uow, request.task["task_id"])
        params: Any = request.instruction.params or {}
        clearance = ReviewClearance(params.get("clearance", "self"))
        return decide(state, clearance, ctx, uow, {})

    def run(self, _request: Any, _deps: Any) -> Any:
        raise error_for(ErrorCode.INVALID_TRANSITION, "acceptance belongs to the control plane")


def decide(state: Any, clearance: Any, ctx: Any, uow: UnitOfWork, why: Any) -> StageOutcome:
    output = state.output
    policy_ok = True
    try:
        live_guard(uow, ctx, state.run)
    except SkmError:
        policy_ok = False
    evidence = True
    version_ids = (
        []
        if output is None
        else [v for v, _ in uow.repo(EvidenceBindingRepository).for_owner("output", output.id)]
    )
    if version_ids:
        try:
            artifacts.require_ready_versions(uow, state.run.workspace_id, version_ids)
        except SkmError:
            evidence = False
    revision_id = state.run.revision_id
    spec = None if revision_id is None else planning.get_revision_specification(uow, revision_id)
    required_checks = [c.id for c in check_definitions(uow, state.run, state.task) if c.required]
    steps = [step for entry in state.history.entries for step in entry.steps]
    output_producer = None if output is None else output.produced_by_step_id
    authors = [step for step in steps if is_output_author(step, output_producer)]
    review_req: Any = {}
    entity = state.task.spec_entity_id
    requirement = None if spec is None or entity is None else spec.review_requirement_for(entity)
    if requirement is not None and state.task.kind is TaskKind.ITEM:
        review_req.update(plain(requirement))
    elif getattr(requirement, "independence", None) == "separate_runtime":
        review_req["independence"] = "separate_runtime"
    review_req["executor_step_ids"] = [str(step.id) for step in authors]
    if review_req.get("independence") == "separate_runtime":
        observed = {str(step.id): observed_identity(step) for step in steps}
        review_req["executor_identities"] = [observed[str(step.id)] for step in authors]
        review_req["reviewer_identities"] = {
            str(step.id): observed[str(step.id)] for step in steps if step.role.value == "reviewer"
        }
    if output is not None and output.produced_by_step_id is not None:
        step = uow.repo(StepRepository).get(output.produced_by_step_id)
        result_doc: Any = plain(step.result or {})
        self_check: Any = result_doc.get("self_check", {})
        review_req["self_check"] = (
            isinstance(self_check, dict) and cast("Any", self_check).get("performed") is True
        )
    if output is None:
        result = NotAcceptable((AcceptanceReason("OUTPUT_NOT_CURRENT", {}),))
    else:
        result = decide_acceptance(
            state.task,
            state.attempt,
            output,
            state.checks,
            state.manual,
            state.reviews,
            state.findings,
            uow.repo(AcceptanceRepository).deviations_for_task(state.task.id),
            review_req,
            clearance,
            policy_ok,
            not state.budget.get("unmetered", False),
            True,
            evidence,
            bool(version_ids),
            required_checks=required_checks,
        )
    if state.run.autopilot:
        result = repair_acceptance(uow, state, clearance, result)
    decision = record_acceptance(
        result,
        clearance=clearance,
        decision_id=ctx.ids.new_id(),
        task=state.task,
        attempt=state.attempt,
        output=output,
        actor_id=ctx.actor.principal_id,
        now=ctx.clock.now(),
    )
    uow.repo(AcceptanceRepository).add_decision(decision)
    if isinstance(result, Accepted):
        emit(
            uow,
            state.run,
            "acceptance-decided",
            {
                "task_id": str(state.task.id),
                "attempt_id": str(state.attempt.id),
                "output_id": None if output is None else str(output.id),
                "acceptance_decision_id": str(decision.id),
                "clearance": result.clearance.value,
            },
            why,
        )
        return StageOutcome(StageOutcomeKind.ACCEPTED, {"acceptance_decision_id": str(decision.id)})
    return StageOutcome(StageOutcomeKind.NOT_ACCEPTABLE, {"reasons": plain(result.reasons)})


def repair_acceptance(
    uow: UnitOfWork, state: Any, clearance: Any, result: Accepted | NotAcceptable
) -> Accepted | NotAcceptable:
    gates = [
        g.details
        for g in uow.repo(StepRepository).incident_gates(state.task.id)
        if g.details.get("attempt_id") == str(state.attempt.id)
    ]
    action = next((row for row in reversed(gates) if row.get("branch") == "B"), None)
    if action is None:
        return result
    marker = action[REPAIR_ACTION_DIGEST]
    reasons = list(result.reasons) if isinstance(result, NotAcceptable) else []
    if state.output is None or not any(
        row.get("action") == "repair_output"
        and row.get("output_id") == str(state.output.id)
        and row.get(REPAIR_ACTION_DIGEST) == marker
        for row in gates
    ):
        reasons.append(AcceptanceReason(REPAIR_ACTION_DIGEST, {"action_digest": marker}))
    if action.get(REPAIR_REVIEW_REQUIRED) and (
        clearance is not ReviewClearance.GREEN or any(reason.code.startswith("REVIEW_") for reason in reasons)
    ):
        reasons.append(AcceptanceReason(REPAIR_REVIEW_REQUIRED, {"action_digest": marker}))
    return NotAcceptable(tuple(reasons)) if reasons else result


def observed_identity(step: Any) -> dict[str, str | None] | None:
    binding = observed_binding(step.route_snapshot, step.runtime_observation)
    if binding is None:
        return None
    runtime = binding["runtime_id"]
    return {"runtime": runtime, "family": observed_model_family(runtime, binding["provider_reported_model"])}
