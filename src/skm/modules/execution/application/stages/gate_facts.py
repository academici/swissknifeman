"""Read-only gate facts from the run's task graph and revision: members, checks, enriched state."""

from dataclasses import replace
from typing import Any

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.domain.task import GATE_KINDS, TaskKind, TaskStatus
from skm.modules.execution.domain.task_graph import gate_members
from skm.modules.execution.ports import TaskRepository
from skm.modules.planning import public as planning


def members(uow: UnitOfWork, state: Any, *, work_only: bool = False) -> tuple[Any, ...]:
    repo = uow.repo(TaskRepository)
    tasks = {t.id: t for t in repo.list_for_run(state.run.id)}
    edges = repo.edges_for_run(state.run.id)
    if state.task.kind is TaskKind.PLAN_ACCEPTANCE:
        selected = tuple(t for t in tasks.values() if t.id != state.task.id)
    else:
        selected = tuple(tasks[tid] for tid in gate_members(state.task, edges))
    if not work_only:
        return selected
    found: dict[Any, Any] = {}
    pending = list(selected)
    seen: set[Any] = set()
    while pending:
        task = pending.pop()
        if task.id in seen:
            continue
        seen.add(task.id)
        if task.kind in GATE_KINDS:
            pending.extend(tasks[tid] for tid in gate_members(task, edges))
        elif task.status is TaskStatus.ACCEPTED:
            found[task.id] = task
    return tuple(found.values())


def enrich(uow: UnitOfWork, state: Any) -> Any:
    if state.task.kind not in GATE_KINDS or state.task.kind is TaskKind.PLAN_AUDIT:
        return state
    return replace(
        state,
        gate={
            "members": [{"task_id": str(t.id), "status": t.status.value} for t in members(uow, state)],
            "required_checks": [str(i) for i in sorted(required_checks(uow, state), key=str)],
            "followups": [
                str(t.id)
                for t in uow.repo(TaskRepository).list_for_run(state.run.id)
                if t.origin and t.origin.source_task_id == state.task.id
            ],
        },
    )


def required_checks(uow: UnitOfWork, state: Any) -> frozenset[Any]:
    spec = planning.get_revision_specification(uow, state.run.revision_id)
    if state.task.kind is TaskKind.PLAN_ACCEPTANCE:
        return frozenset(
            c.id for c in spec.checks if c.required and (c.owner == "plan" or c.rerun_after_integration)
        )
    graph = planning.compile_execution_graph(spec, state.run.revision_id)
    node = next((n for n in graph.tasks if n.task_key == state.task.display_key), None)
    bound: set[Any] = set() if node is None else {b.check_id for b in node.checks}
    return frozenset(c.id for c in spec.checks if c.required and c.id in bound)


def check_definitions(uow: UnitOfWork, run: Any, task: Any) -> tuple[Any, ...]:
    """Plan final-tip rechecks and standalone followup checks retain revision-owned definitions."""
    if run.revision_id is None:
        return ()
    if task.kind is TaskKind.FOLLOWUP:
        if task.origin is None or task.origin.source_task_id is None:
            raise error_for(ErrorCode.INVALID_REFERENCE, "followup requires its gate origin")
        source = uow.repo(TaskRepository).get(task.origin.source_task_id)
        if source.run_id != run.id:
            raise error_for(ErrorCode.INVALID_REFERENCE, "followup origin belongs to another run")
        return check_definitions(uow, run, source)
    spec = planning.get_revision_specification(uow, run.revision_id)
    if task.kind is TaskKind.PLAN_ACCEPTANCE:
        return tuple(c for c in spec.checks if c.owner == "plan" or c.rerun_after_integration)
    graph = planning.compile_execution_graph(spec, run.revision_id)
    node = next((n for n in graph.tasks if n.task_key == task.display_key), None)
    by_id = {check.id: check for check in spec.checks}
    return () if node is None else tuple(by_id[b.check_id] for b in node.checks)
