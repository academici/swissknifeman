"""Deterministic dispatch admission; pending scopes protect writes without using capacity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from skm.kernel.ids import AttemptId, RepositoryId
from skm.kernel.path_globs import globs_overlap

from .run import RunStatus
from .task import GATE_KINDS, TERMINAL_TASK_STATUSES, TaskStatus
from .task_graph import prerequisites

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.ids import HostId, TaskId

    from .run import Run
    from .task import PathPattern, Task
    from .task_graph import TaskEdge


UNSCHEDULABLE_STATUSES = TERMINAL_TASK_STATUSES | {
    TaskStatus.BLOCKED,
    TaskStatus.MANUAL_PENDING,
    TaskStatus.AWAITING_DECISION,
}


@dataclass(frozen=True, slots=True)
class SchedulingInput:
    run: Run
    tasks: tuple[Task, ...]
    edges: tuple[TaskEdge, ...]
    in_flight: tuple[Task, ...]
    pending_scopes: tuple[Task, ...]
    max_units: int
    batch_groups: Mapping[TaskId, str]
    existing_checkout_repos_busy: frozenset[RepositoryId]
    integration_hosts: Mapping[RepositoryId, HostId]
    integration_targets: Mapping[RepositoryId, str]
    target_hosts: Mapping[tuple[RepositoryId, str], HostId]
    mount_repositories: Mapping[str, RepositoryId] = field(default_factory=dict[str, RepositoryId])
    eligible_ids: frozenset[TaskId] | None = None
    existing_checkout_repos_busy_by_attempt: Mapping[AttemptId, frozenset[RepositoryId]] = field(
        default_factory=dict[AttemptId, frozenset[RepositoryId]]
    )


def write_scope(task: Task) -> tuple[PathPattern, ...] | None:
    if task.kind in GATE_KINDS or task.work_kind in {"research", "review"}:
        return ()
    return task.declared_write_scope


def scopes_overlap(left: Task, right: Task) -> bool:
    """Unknown writes conflict with every nonempty writer; never with a read-only unit."""
    a, b = write_scope(left), write_scope(right)
    if a == () or b == ():
        return False
    if a is None or b is None:
        return True
    return any(x.mount == y.mount and globs_overlap(x.pattern, y.pattern) for x in a for y in b)


def repositories(task: Task, inputs: SchedulingInput) -> frozenset[RepositoryId]:
    scope = write_scope(task)
    if scope == ():
        return frozenset()
    if scope is None or not inputs.mount_repositories:
        return frozenset(inputs.integration_targets) | inputs.existing_checkout_repos_busy
    return frozenset(
        inputs.mount_repositories[p.mount] for p in scope if p.mount in inputs.mount_repositories
    )


def required_host(task: Task, inputs: SchedulingInput) -> tuple[HostId | None, str | None]:
    hosts = {task.required_host_id} - {None}
    for repo in repositories(task, inputs):
        hosts.update(
            host
            for host in (
                inputs.integration_hosts.get(repo),
                inputs.target_hosts.get((repo, inputs.integration_targets.get(repo, ""))),
            )
            if host is not None
        )
    if len(hosts) > 1:
        return None, "INTEGRATION_HOST_MISMATCH"
    return next(iter(hosts), None), None


def refusal(task: Task, inputs: SchedulingInput) -> str | None:
    _, conflict = required_host(task, inputs)
    if conflict:
        return conflict
    busy = inputs.existing_checkout_repos_busy
    if task.current_attempt_id is not None:
        busy = inputs.existing_checkout_repos_busy_by_attempt.get(task.current_attempt_id, busy)
    if repositories(task, inputs) & busy:
        return "CHECKOUT_BUSY"
    states = {t.id: t.status for t in inputs.tasks}
    if any(
        states.get(tid) not in {TaskStatus.ACCEPTED, TaskStatus.SKIPPED}
        for tid in prerequisites(task.id, inputs.edges)
    ):
        return "BLOCKED_BY_DEPENDENCY"
    return None


def select_assignable(inputs: SchedulingInput, *, limit: int | None = None) -> tuple[TaskId, ...]:
    """Oldest position first; a required batch reserves capacity before younger work.

    The application supplies only eligible continuation candidates. Active units are
    distinct attempts, even if their task appears in several sources. Pending rows
    reserve scopes but claim repeats the live dispatch ceiling under the run lock.
    """
    if inputs.run.status is not RunStatus.RUNNING:
        return ()
    active = {t.current_attempt_id or t.id for t in inputs.in_flight}
    slots = max(0, inputs.max_units - len(active))
    if limit is not None:
        slots = min(slots, max(0, limit))
    protected = list({t.id: t for t in (*inputs.in_flight, *inputs.pending_scopes)}.values())
    ordered = sorted(inputs.tasks, key=lambda t: (t.position, str(t.id)))
    eligible = {
        t.id: t
        for t in ordered
        if (inputs.eligible_ids is None or t.id in inputs.eligible_ids)
        and t.status not in UNSCHEDULABLE_STATUSES
        and (t.current_attempt_id or t.id) not in active
        and refusal(t, inputs) is None
    }
    chosen: list[TaskId] = []
    visited: set[TaskId] = set()
    for task in ordered:
        if task.id not in eligible or task.id in visited:
            continue
        group = inputs.batch_groups.get(task.id)
        members = [t for t in ordered if inputs.batch_groups.get(t.id) == group] if group else [task]
        visited.update(t.id for t in members)
        if any(t.id not in eligible for t in members):
            continue
        if any(scopes_overlap(t, p) for t in members for p in protected if t.id != p.id):
            continue
        if any(scopes_overlap(a, b) for i, a in enumerate(members) for b in members[i + 1 :]):
            continue
        if len(members) > slots:
            break
        chosen.extend(t.id for t in members)
        slots -= len(members)
        protected.extend(members)
    return tuple(chosen)
