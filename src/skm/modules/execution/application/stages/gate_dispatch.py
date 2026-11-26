"""Gate-specific facts at scheduler/readiness/worker boundaries, without host IO."""

from dataclasses import replace
from typing import Any

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application.stages import phase_gate
from skm.modules.execution.application.stages.gate_facts import required_checks
from skm.modules.execution.domain.task import GATE_KINDS, TaskKind
from skm.modules.execution.domain.workflow.definition import gate_workflow_violations
from skm.modules.execution.ports import AcceptanceRepository


def select(uow: UnitOfWork, state: Any, workflow: Any, action: Any) -> Any:
    if state.task.kind not in GATE_KINDS or state.task.kind is TaskKind.PLAN_AUDIT:
        return action
    violations = gate_workflow_violations(
        workflow, state.task, required_checks=bool(required_checks(uow, state))
    )
    if violations:
        raise error_for(
            ErrorCode.NOT_ACCEPTABLE, "GATE_UNSUPPORTED_BY_WORKFLOW", details={"rule": "R13_gates"}
        )
    if action.stage_type.value == "prepare_environment":
        return replace(
            action,
            params={
                **action.params,
                "baseline_strategy": "gate_range",
                "gate_range": [b.to_json() for b in phase_gate.bounds(uow, state)],
            },
        )
    if action.stage_type.value == "run_checks":
        return replace(action, params={**action.params, "scope": "gate"})
    if action.stage_type.value == "agent_review":
        params = {**action.params, "audit_scope": "range"}
        if params.get("reviewer_with_fix") is True:
            params.update(reviewer_with_fix=False, profile=state.task.review_profile or "reviewer")
        return replace(action, params=params)
    return action


def require_done(uow: UnitOfWork, ctx: Any, state: Any, workflow: Any, why: Any) -> None:
    """A Done marker alone cannot replace gate acceptance or silently drop required checks/review."""
    if state.task.kind not in GATE_KINDS or state.task.kind is TaskKind.PLAN_AUDIT:
        return
    decisions = uow.repo(AcceptanceRepository).decisions_for_task(state.task.id)
    current = [
        d
        for d in decisions
        if d.attempt_id == state.attempt.id and d.output_id == state.attempt.current_output_id
    ]
    if current and current[-1].decision == "accepted":
        return
    violations = gate_workflow_violations(
        workflow, state.task, required_checks=bool(required_checks(uow, state))
    )
    if violations:
        raise error_for(
            ErrorCode.NOT_ACCEPTABLE, "GATE_UNSUPPORTED_BY_WORKFLOW", details={"rule": "R13_gates"}
        )
    if state.task.kind is TaskKind.PLAN_ACCEPTANCE:
        raise error_for(ErrorCode.NOT_ACCEPTABLE, "plan Done requires persisted coverage acceptance")
    outcome = phase_gate.decide(state, ctx, uow, why, empty=state.output is None)
    if outcome.kind != "accepted":
        raise error_for(ErrorCode.NOT_ACCEPTABLE, "gate acceptance invariants are unmet")
