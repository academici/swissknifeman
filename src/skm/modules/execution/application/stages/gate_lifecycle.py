"""Gate followups and T29 range re-review without charging another attempts reservation."""

from dataclasses import replace
from typing import Any

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._control import close_attempt
from skm.modules.execution.application._events import emit, save_task, task_created
from skm.modules.execution.application._primitives import budget_accounts, clear_advance, move, save_attempt
from skm.modules.execution.application._state import effective_values, load_state
from skm.modules.execution.application.stages import phase_gate
from skm.modules.execution.application.stages.gate_facts import members, required_checks
from skm.modules.execution.domain.attempt import (
    Attempt,
    AttemptEndReason,
    AttemptState,
    ContinuationCause,
    SelectedStage,
    select_stage,
)
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.task import (
    GATE_KINDS,
    PathPattern,
    ReviewMode,
    TaskKind,
    TaskOrigin,
    TaskStatus,
    transition,
)
from skm.modules.execution.domain.task_graph import EdgeKind, TaskEdge
from skm.modules.execution.domain.workflow.actions import Ctx, RunStage
from skm.modules.execution.domain.workflow.definition import applies_to_kind
from skm.modules.execution.domain.workflow.engine import initial_selection
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs
from skm.modules.execution.ports import (
    AttemptRepository,
    BudgetRepository,
    OutputRepository,
    TaskRepository,
)


def followups(uow: UnitOfWork, ctx: Any, state: Any, action: Any, why: Any) -> str:
    scope = _scope(uow, state, action)
    _, values = effective_values(uow, state.run.id)
    created: list[JsonValue] = []
    ids = action.finding_ids or (None,)
    for index, fid in enumerate(ids):
        tid = ctx.ids.new_id()
        child = replace(
            state.task,
            id=tid,
            kind=TaskKind.FOLLOWUP,
            spec_entity_id=None,
            display_key=f"@followup/{tid}",
            origin=TaskOrigin(state.task.id, () if fid is None else (fid,), action.reason),
            declared_write_scope=scope,
            review_mode=ReviewMode.REQUIRED,
            position=state.task.position + index + 1,
            status=TaskStatus.READY,
            current_attempt_id=None,
            accepted_attempt_id=None,
            accepted_output_id=None,
            attempt_count=0,
            check_fix_rounds=0,
            review_rounds=0,
            blocking_reason=None,
            row_version=1,
        )
        edge = TaskEdge(state.run.id, state.task.id, tid, EdgeKind.GATE_MEMBER, frozenset())
        uow.repo(TaskRepository).add_synthetic(child, (edge,))
        uow.repo(BudgetRepository).add_accounts(budget_accounts(ctx, state.run.id, (tid,), values))
        task_created(uow, state.run, child, why)
        emit(uow, state.run, "task-ready", {"task_id": str(tid), "reason": "followup"}, why)
        created.append(str(tid))
    blocked = blocking_reason(
        BlockingCode.BLOCKED_BY_DEPENDENCY,
        task_id=state.task.id,
        refs={"prerequisite_task_ids": created},
        now=ctx.clock.now(),
        message="followups pending",
    )
    # Control-plane acceptance may be reached directly after preparation, before any checks/review.
    task = state.task
    if task.status in {TaskStatus.ASSIGNED, TaskStatus.EXECUTING}:
        task = move(uow, ctx, state.run, task, TaskStatus.CHECKING, why)
    if task.status is TaskStatus.MANUAL_PENDING:
        # E2 closes the manual wait through T11; T28 then blocks the control-plane gate.
        task = move(uow, ctx, state.run, task, TaskStatus.INTEGRATING, why)
    changed = transition(task, TaskStatus.BLOCKED, rule="T28", blocking=blocked)
    changed = replace(
        changed,
        review_rounds=max(task.review_rounds, task.check_fix_rounds + 1),
        check_fix_rounds=task.check_fix_rounds + 1,
    )
    save_task(uow, state.run, task, changed, why, ctx.clock.now())
    clear_advance(uow, state.attempt)
    emit(
        uow,
        state.run,
        "followups-created",
        {
            "task_id": str(task.id),
            "followup_task_ids": created,
            "reason": action.reason,
            "finding_keys": [f.finding_key for f in state.findings if f.id in action.finding_ids],
            "source_output_id": None if state.output is None else str(state.output.id),
            "check_execution_ids": [str(i) for i in action.check_execution_ids],
            "review_id": str(state.reviews[-1].id) if state.reviews else None,
        },
        why,
    )
    return "followups"


def _scope(uow: UnitOfWork, state: Any, action: Any) -> tuple[PathPattern, ...]:
    paths = {
        (str(f.location.get("mount", "")), str(f.location["path"]))
        for f in state.findings
        if f.id in action.finding_ids
    }
    if paths:
        return tuple(PathPattern(mount, path) for mount, path in sorted(paths))
    work = members(uow, state, work_only=True)
    scopes = [t.declared_write_scope for t in work]
    if any(s is None for s in scopes):
        # An unbounded member scope is not transferred to a gate followup: use observed member paths.
        sources = phase_gate.carried_sources(uow, state.run.id, work)
        outputs = uow.repo(OutputRepository)
        for task in work:
            source = sources.get(task.id)
            output_id = task.accepted_output_id if source is None else source.accepted_output_id
            if output_id is None:
                raise error_for(ErrorCode.CHECKOUT_MISMATCH, "gate member has no accepted output")
            paths.update((path.mount, path.path) for path in outputs.get(output_id).manifest.changed_paths)
        return tuple(PathPattern(m, p) for m, p in sorted(paths))
    return tuple(dict.fromkeys(p for scope in scopes for p in (scope or ())))


def rereview(uow: UnitOfWork, ctx: Any, run: Any, task: Any, why: Any) -> Any:
    """Called only when the graph proves all gate members/followups terminal."""
    repo = uow.repo(AttemptRepository)
    old = repo.get(task.current_attempt_id, for_update=True)
    close_attempt(uow, ctx, run, old, code="GATE_REREVIEW", reason=AttemptEndReason.GATE_REREVIEW)
    attempt = Attempt(
        ctx.ids.new_id(),
        run.id,
        task.id,
        run.workspace_id,
        repo.next_attempt_no(task.id),
        AttemptState.PREPARING,
        None,
        old.host_id,
        None,
        None,
        None,
        None,
        ctx.clock.now(),
        None,
        None,
    )
    ready = transition(task, TaskStatus.READY, rule="T29")
    ready = replace(ready, current_attempt_id=attempt.id)
    repo.add(attempt)
    save_task(uow, run, task, ready, why, ctx.clock.now())
    state, workflow = load_state(uow, task.id)
    # Select initial stage for the fresh attempt; the scheduler will assign this durable template.
    selection_state = replace(state, task=replace(ready, status=TaskStatus.ASSIGNED))
    decision = initial_selection(Ctx(selection_state, workflow, state.effective_policy, ctx.clock.now()))
    if not isinstance(decision.action, RunStage):
        raise error_for(ErrorCode.INVALID_TRANSITION, "gate rereview requires a prepare stage")
    action = decision.action
    action = replace(
        action,
        params={
            **action.params,
            "baseline_strategy": "gate_range",
            "gate_range": [b.to_json() for b in phase_gate.bounds(uow, state)],
        },
    )
    save_attempt(
        uow,
        select_stage(
            attempt,
            cause=ContinuationCause("followup", "A1", ("GATE_REREVIEW",)),
            stage=SelectedStage(
                action.stage_id,
                action.stage_type.value,
                action.mode,
                action.round_no,
                action.params,
                action.not_before,
                action.route_override,
                action.feedback or FeedbackRefs(),
                None,
                None,
            ),
            continuation_id=ctx.ids.new_id(),
        ),
    )
    emit(uow, run, "task-ready", {"task_id": str(task.id), "reason": "GATE_REREVIEW"}, why)
    assigned = transition(ready, TaskStatus.ASSIGNED, rule="T2")
    save_task(uow, run, ready, assigned, why, ctx.clock.now())
    return assigned


def open_empty_gate(uow: UnitOfWork, ctx: Any, run: Any, task: Any, why: Any) -> bool:
    """Open an attempt for a gate with no applicable stages after rechecking R13 with its frozen contract.

    True means the gate's members are accepted and the caller must apply Done to it.
    """
    if task.kind not in GATE_KINDS or task.kind is TaskKind.PLAN_AUDIT:
        return False
    state, workflow = load_state(uow, task.id)
    if any(applies_to_kind(s, task.kind) for s in workflow.stages):
        return False
    if required_checks(uow, state) or task.review_mode == "required":
        raise error_for(
            ErrorCode.NOT_ACCEPTABLE, "GATE_UNSUPPORTED_BY_WORKFLOW: required gate has no applicable workflow"
        )
    attempt = Attempt(
        ctx.ids.new_id(),
        run.id,
        task.id,
        run.workspace_id,
        uow.repo(AttemptRepository).next_attempt_no(task.id),
        AttemptState.RUNNING,
        None,
        None,
        None,
        None,
        None,
        None,
        ctx.clock.now(),
        None,
        None,
    )
    uow.repo(AttemptRepository).add(attempt)
    changed = replace(
        task,
        status=TaskStatus.ASSIGNED,
        current_attempt_id=attempt.id,
        blocking_reason=None,
        row_version=task.row_version + 1,
    )
    save_task(uow, run, task, changed, why, ctx.clock.now())
    state, _ = load_state(uow, task.id)
    outcome = phase_gate.decide(state, ctx, uow, why, empty=True)
    if outcome.kind != "accepted":
        raise error_for(ErrorCode.NOT_ACCEPTABLE, "empty gate has unfinished members")
    return True
