"""Load trusted gate facts and persist control-plane acceptance in the transition UoW."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._control import live_guard
from skm.modules.execution.application._events import emit
from skm.modules.execution.application._json_reads import integer, obj
from skm.modules.execution.application._plain import plain
from skm.modules.execution.application._primitives import attempt_effect_ids
from skm.modules.execution.application._state import load_state
from skm.modules.execution.application.stages.gate_facts import members, required_checks
from skm.modules.execution.domain.acceptance import Accepted, record_acceptance
from skm.modules.execution.domain.gate_range import range_bounds
from skm.modules.execution.domain.gates import GateInputs, decide_gate
from skm.modules.execution.domain.review import ReviewClearance
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.domain.task import TaskKind, TaskStatus
from skm.modules.execution.ports import (
    AcceptanceRepository,
    EffectRepository,
    ExecutionQueries,
    OutputRepository,
    TaskRepository,
)
from skm.modules.execution.public import StageOutcome

if TYPE_CHECKING:
    from collections.abc import Sequence

    from skm.kernel.ids import RunId, TaskId
    from skm.modules.execution.domain.task import Task


class PhaseGate:
    stage_type = "phase_gate"
    side = "control_plane"
    params_schema_urn = "urn:skm:execution:workflow:v1"

    def decide(self, request: Any, ctx: Any, uow: UnitOfWork) -> StageOutcome:
        state, _ = load_state(uow, request.task["task_id"])
        return decide(state, ctx, uow, {})

    def run(self, _request: Any, _deps: Any) -> Any:
        raise error_for(ErrorCode.INVALID_TRANSITION, "gate decisions belong to the control plane")


def inputs(uow: UnitOfWork, ctx: Any, state: Any, *, empty: bool = False) -> GateInputs:
    policy_ok = True
    try:
        live_guard(uow, ctx, state.run)
    except SkmError:
        policy_ok = False
    own_members = members(uow, state)
    tasks = uow.repo(TaskRepository).list_for_run(state.run.id)
    skipped: frozenset[Any] = frozenset()
    # Completed skip requests are retained in the immutable run event stream, not open_for_task.
    queries = uow.repo(ExecutionQueries)
    head = queries.head_run_seq(state.run.id)
    after = 0
    while after < head:
        events = queries.run_events(state.run.id, after, head, 100)
        if not events:
            break
        skipped |= frozenset(
            UUID(str(obj(e["payload"], "payload")["task_id"]))
            for e in events
            if "task-skipped" in str(e.get("event_type", e.get("type", "")))
        )
        after = max(integer(e["stream_seq"], "stream_seq") for e in events)
    clearance = None
    last = state.history.last()
    if (
        last
        and state.reviews
        and last.record.stage_type == "agent_step"
        and last.record.outcome_kind is StageOutcomeKind.SUCCESS
    ):
        clearance = ReviewClearance.CLEARED_BY_TRIAGE
    return GateInputs(
        state.task,
        own_members,
        state.output,
        state.checks,
        state.manual,
        state.reviews,
        state.findings,
        uow.repo(AcceptanceRepository).deviations_for_task(state.task.id),
        policy_ok,
        required_checks(uow, state),
        skipped,
        tuple(t for t in tasks if t.kind is TaskKind.FOLLOWUP),
        clearance,
        empty,
    )


def carried_sources(uow: UnitOfWork, run_id: RunId, work: Sequence[Task]) -> dict[TaskId, Task]:
    targets = {task.id for task in work if task.accepted_output_id is None}
    if not targets:
        return {}
    tasks = uow.repo(TaskRepository)
    sources: dict[TaskId, Task] = {}
    for evidence in uow.repo(AcceptanceRepository).carry_forwards_for_run(run_id):
        if evidence.decision != "accepted" or evidence.target_task_id not in targets:
            continue
        source = tasks.get(evidence.source_task_id)
        if source.status is not TaskStatus.ACCEPTED or (
            source.run_id,
            source.accepted_attempt_id,
            source.accepted_output_id,
        ) != (evidence.source_run_id, evidence.source_attempt_id, evidence.source_output_id):
            raise error_for(ErrorCode.CHECKOUT_MISMATCH, "carry-forward source acceptance is unavailable")
        sources[evidence.target_task_id] = source
    return sources


def bounds(uow: UnitOfWork, state: Any, *, pinned: bool = False) -> tuple[Any, ...]:
    work = members(uow, state, work_only=True)
    sources = carried_sources(uow, state.run.id, work)
    runs = {state.run.id, *(source.run_id for source in sources.values())}
    task_repo = uow.repo(TaskRepository)
    tasks = [task for run_id in runs for task in task_repo.list_for_run(run_id)]
    effects: list[Any] = []
    outputs: list[Any] = []
    for task in tasks:
        if task.accepted_output_id is not None:
            outputs.append(uow.repo(OutputRepository).get(task.accepted_output_id))
        if task.accepted_attempt_id is None:
            continue
        effects.extend(
            uow.repo(EffectRepository).get(effect_id)
            for effect_id in attempt_effect_ids(uow, task.accepted_attempt_id)
        )
    heads = (
        None
        if not pinned or state.output is None
        else {str(m.repository_id): m.head_commit for m in state.output.manifest.mounts}
    )
    return range_bounds(work, outputs, effects, heads=heads, carried_sources=sources)


def validate_range(uow: UnitOfWork, state: Any) -> None:
    if state.output is None:
        raise error_for(ErrorCode.CHECKOUT_MISMATCH, "gate has no range output")
    proven = {b.repository_id: b for b in bounds(uow, state, pinned=True)}
    mounts = state.output.manifest.mounts
    if set(proven) != {str(m.repository_id) for m in mounts} or any(
        (m.base_commit, m.head_commit, m.tree_sha)
        != (
            proven[str(m.repository_id)].base,
            proven[str(m.repository_id)].head,
            proven[str(m.repository_id)].tree_sha,
        )
        for m in mounts
    ):
        raise error_for(ErrorCode.CHECKOUT_MISMATCH, "range output differs from immutable receipts")


def persist(
    uow: UnitOfWork, ctx: Any, state: Any, result: Any, why: Any, *, coverage: Any = None
) -> StageOutcome:
    clearance = result.clearance if isinstance(result, Accepted) else ReviewClearance.WAIVED
    decision = record_acceptance(
        result,
        clearance=clearance,
        decision_id=ctx.ids.new_id(),
        task=state.task,
        attempt=state.attempt,
        output=state.output,
        actor_id=ctx.actor.principal_id,
        now=ctx.clock.now(),
    )
    if coverage is not None:
        decision = replace(decision, basis=replace(decision.basis, coverage_report=coverage.to_json()))
    uow.repo(AcceptanceRepository).add_decision(decision)
    payload: dict[str, Any] = {"acceptance_decision_id": str(decision.id)}
    if coverage is not None:
        payload.update(coverage=coverage.to_json(), diagnostics=list(coverage.diagnostics))
    if isinstance(result, Accepted):
        emit(
            uow,
            state.run,
            "acceptance-decided",
            {
                "task_id": str(state.task.id),
                "attempt_id": str(state.attempt.id),
                "output_id": None if state.output is None else str(state.output.id),
                "acceptance_decision_id": str(decision.id),
                "clearance": result.clearance.value,
            },
            why,
        )
        return StageOutcome(StageOutcomeKind.ACCEPTED, payload)
    return StageOutcome(StageOutcomeKind.NOT_ACCEPTABLE, {**payload, "reasons": plain(result.reasons)})


def decide(state: Any, ctx: Any, uow: UnitOfWork, why: Any, *, empty: bool = False) -> StageOutcome:
    if not empty:
        validate_range(uow, state)
    return persist(uow, ctx, state, decide_gate(inputs(uow, ctx, state, empty=empty)), why)
