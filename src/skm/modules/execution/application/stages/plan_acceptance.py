"""Plan acceptance and retained coverage evidence, using the frozen planning revision."""

from typing import Any, override

from skm.kernel.ids import FileVersionId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._json_report import retain_json_report
from skm.modules.execution.application._plain import plain
from skm.modules.execution.application._state import load_state
from skm.modules.execution.application.stages import phase_gate
from skm.modules.execution.domain.gates import decide_plan_acceptance
from skm.modules.execution.ports import (
    AcceptanceRepository,
    CheckRepository,
    TaskRepository,
)
from skm.modules.execution.public import StageOutcome
from skm.modules.planning import public as planning


class PlanAcceptance(phase_gate.PhaseGate):
    stage_type = "plan_acceptance"

    @override
    def decide(self, request: Any, ctx: Any, uow: UnitOfWork) -> StageOutcome:
        state, _ = load_state(uow, request.task["task_id"])
        params: Any = request.instruction.params or {}
        return decide(state, ctx, uow, {}, coverage_mode=params.get("coverage", "required"))


def decide(
    state: Any, ctx: Any, uow: UnitOfWork, why: Any, *, coverage_mode: Any = "required"
) -> StageOutcome:
    phase_gate.validate_range(uow, state)
    gate = phase_gate.inputs(uow, ctx, state)
    tasks = uow.repo(TaskRepository).list_for_run(state.run.id)
    spec = planning.get_revision_specification(uow, state.run.revision_id)
    decisions = tuple(d for t in tasks for d in uow.repo(AcceptanceRepository).decisions_for_task(t.id))
    checks = tuple(
        c
        for t in tasks
        if t.accepted_output_id is not None
        for c in uow.repo(CheckRepository).for_output(t.accepted_output_id)
    )
    deviations = tuple(d for t in tasks for d in uow.repo(AcceptanceRepository).deviations_for_task(t.id))
    result, report = decide_plan_acceptance(
        gate, plain(spec), tasks, decisions, coverage_mode, checks=checks, deviations=deviations
    )
    register_coverage(uow, ctx, state, report.to_json())
    return phase_gate.persist(uow, ctx, state, result, why, coverage=report)


def register_coverage(uow: UnitOfWork, ctx: Any, state: Any, document: Any) -> FileVersionId:
    return retain_json_report(
        uow,
        ctx,
        state,
        document,
        title=f"Coverage for {state.task.display_key}",
        filename=f"coverage-{state.attempt.id}.json",
        source_ref=f"coverage:{state.attempt.id}",
    )
