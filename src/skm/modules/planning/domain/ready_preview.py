"""Ready-task preview over the compiled graph (planning §5.5).

Port of legacy ``parallel.ready_set`` / ``lifecycle.route_groups`` onto graph tasks. There is no execution
state: the caller says which tasks count as done and which owner gates as granted. The preview reads the
graph and the specification only; it resolves no work-policy defaults and writes nothing back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from skm.modules.planning.domain.compile_graph import TaskKind
from skm.modules.planning.domain.item import Effort, ExternalGate, ModelClass, OwnerGate, Route, RouteFloor
from skm.modules.planning.domain.phase import BatchMode, DesignState
from skm.modules.planning.domain.validation.globs import globs_overlap

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Literal

    from skm.modules.planning.domain.compile_graph import BatchGroup, ExecutionGraph, TaskNode
    from skm.modules.planning.domain.execution_constraints import PathRule
    from skm.modules.planning.domain.specification import Specification


@dataclass(frozen=True, slots=True)
class Lane:
    kind: Literal["task", "gate", "batch"]
    tasks: tuple[str, ...]
    route: Route | None
    batch_key: str | None  # "<phase>/<batch>" for a required batch lane


@dataclass(frozen=True, slots=True)
class Waiting:
    task: str
    reason: Literal["dependencies", "design_required", "owner_gate", "external_gate", "batch_incomplete"]
    detail: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LaneConflict:
    task: str
    with_task: str
    reason: Literal["write_scope_overlap", "footprint_unknown"]
    paths: tuple[str, ...]  # "<mount>:<pattern>" of each overlapping pair, this task's first; () when unknown


@dataclass(frozen=True, slots=True)
class RouteGroup:
    route: Route
    lanes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ReadyPreview:
    limit: int
    assume_done: tuple[str, ...]
    assume_granted: tuple[str, ...]
    lanes: tuple[Lane, ...]
    conflicts: tuple[LaneConflict, ...]
    waiting: tuple[Waiting, ...]
    deferred: tuple[str, ...]
    route_groups: tuple[RouteGroup, ...]


_CLASS_ORDER = tuple(ModelClass)
_EFFORT_ORDER = tuple(Effort)


def preview_ready(
    graph: ExecutionGraph,
    spec: Specification,
    *,
    assume_done: frozenset[str],
    assume_granted: frozenset[str],
    limit: int,
) -> ReadyPreview:
    """Lanes that could start side by side once ``assume_done`` is done, and why every other task cannot."""
    cap = spec.execution_constraints.max_parallel_units
    limit = min(limit, cap or limit)
    preview = _Preview(graph, spec, assume_done, assume_granted)
    candidates, waiting = preview.candidates()
    lanes, conflicts, deferred = _select(candidates, preview.tasks, limit)
    position = preview.position
    return ReadyPreview(
        limit=limit,
        assume_done=tuple(
            sorted(assume_done, key=lambda key: (key not in position, position.get(key, 0), key))
        ),
        assume_granted=tuple(sorted(assume_granted)),
        lanes=lanes,
        conflicts=conflicts,
        waiting=waiting,
        deferred=deferred,
        route_groups=_route_groups(lanes),
    )


class _Preview:
    def __init__(
        self, graph: ExecutionGraph, spec: Specification, done: frozenset[str], granted: frozenset[str]
    ) -> None:
        self._done = done
        self._granted = granted
        self.tasks: dict[str, TaskNode] = {task.task_key: task for task in graph.tasks}
        self.position = {task.task_key: n for n, task in enumerate(graph.tasks)}
        self._graph = graph
        self._phases = {phase.key: phase for phase in spec.phases}
        self._items = {item.key: item for item in spec.items}
        prerequisites: dict[str, list[str]] = {key: [] for key in self.tasks}
        for edge in graph.edges:
            prerequisites[edge.dependent].append(edge.prerequisite)
        for keys in prerequisites.values():
            keys.sort(key=self.position.__getitem__)
        self._prerequisites = prerequisites
        self._required = {
            task: group
            for group in graph.batch_groups
            if group.mode is BatchMode.REQUIRED
            for task in group.tasks
        }

    def candidates(self) -> tuple[list[Lane], tuple[Waiting, ...]]:
        """Steps 2-7: every task not done is either a candidate lane (alone or with its batch) or waits."""
        lanes: list[Lane] = []
        waiting: list[Waiting] = []
        placed: set[str] = set()
        batches: dict[tuple[str, str], tuple[str, ...]] = {}
        for task in self._graph.tasks:
            key = task.task_key
            if key in self._done or key in placed:
                continue
            reason = self._unmet(task) or self._hold(task)
            if reason is not None:
                waiting.append(reason)
                continue
            group = self._required.get(key)
            if group is None:
                lanes.append(Lane("gate" if _is_gate(task) else "task", (key,), task.route, None))
                continue
            name = (group.phase_key, group.batch_key)
            if name not in batches:
                batches[name] = self._entries_not_ready(group)
                if not batches[name]:
                    members = tuple(
                        member
                        for member in group.tasks
                        if member not in self._done
                        and self._unmet(self.tasks[member]) is None
                        and self._hold(self.tasks[member]) is None
                    )
                    placed.update(members)
                    route = _lane_route([self.tasks[member] for member in members])
                    lanes.append(Lane("batch", members, route, f"{group.phase_key}/{group.batch_key}"))
                    continue
            waiting.append(Waiting(key, "batch_incomplete", batches[name]))
        return lanes, tuple(waiting)

    def _unmet(self, task: TaskNode) -> Waiting | None:
        unmet = tuple(key for key in self._prerequisites[task.task_key] if key not in self._done)
        return Waiting(task.task_key, "dependencies", unmet) if unmet else None

    def _hold(self, task: TaskNode) -> Waiting | None:
        """Design state of the task's phase, then the authority of its item (steps 4-5)."""
        phase = self._phases.get(task.phase_key)
        if phase is not None and phase.design_state is DesignState.SKELETON:
            return Waiting(task.task_key, "design_required", (task.phase_key,))
        item = None if task.item_key is None else self._items.get(task.item_key)
        if item is None:
            return None
        authority = item.authority
        if isinstance(authority, OwnerGate):
            identity = authority.gate or authority.label or ""
            if identity not in self._granted:
                return Waiting(task.task_key, "owner_gate", (identity,))
        if isinstance(authority, ExternalGate):
            return Waiting(task.task_key, "external_gate", (authority.gate or authority.label or "",))
        return None

    def _entries_not_ready(self, group: BatchGroup) -> tuple[str, ...]:
        """Entries of the batch's items that keep it from starting together (legacy ``ready_members``).

        An entry is ready when it is done, or nothing holds it and every prerequisite is done, a task of
        another item of the same batch included: an entry waiting on its batch would leave only part of it
        to start.
        """
        by_item: dict[str | None, list[str]] = {}
        for key in group.tasks:
            by_item.setdefault(self.tasks[key].item_key, []).append(key)
        missing: list[str] = []
        for tasks in by_item.values():
            inside = set(tasks)
            for key in tasks:
                if inside.intersection(self._prerequisites[key]) or key in self._done:
                    continue
                task = self.tasks[key]
                if self._unmet(task) is not None or self._hold(task) is not None:
                    missing.append(key)
        return tuple(missing)


def _select(
    candidates: list[Lane], tasks: dict[str, TaskNode], limit: int
) -> tuple[tuple[Lane, ...], tuple[LaneConflict, ...], tuple[str, ...]]:
    """Step 8: candidates in order; a clash with an accepted lane is a conflict, past ``limit`` deferred.

    The writers of a batch lane start side by side as well, so a clash between two of them rejects the batch.
    """
    lanes: list[Lane] = []
    conflicts: list[LaneConflict] = []
    deferred: list[str] = []
    taken: list[TaskNode] = []
    for lane in candidates:
        writers = [tasks[key] for key in lane.tasks if not _is_gate(tasks[key])]
        clash = _first_clash(writers, taken) or _first_inner_clash(writers)
        if clash is not None:
            conflicts.append(clash)
            continue
        if len(lanes) >= limit:
            deferred.extend(lane.tasks)
            continue
        lanes.append(lane)
        taken.extend(writers)
    return tuple(lanes), tuple(conflicts), tuple(deferred)


def _is_gate(task: TaskNode) -> bool:
    return task.task_kind in (TaskKind.ITEM_GATE, TaskKind.PHASE_GATE)


def _first_clash(writers: Sequence[TaskNode], taken: Sequence[TaskNode]) -> LaneConflict | None:
    for task in writers:
        for other in taken:
            if task.write_scope is None or other.write_scope is None:
                return LaneConflict(task.task_key, other.task_key, "footprint_unknown", ())
            paths: dict[str, None] = {}
            for mine in task.write_scope:
                for theirs in other.write_scope:
                    if _rules_overlap(mine, theirs):
                        paths[f"{mine.mount}:{mine.pattern}"] = None
                        paths[f"{theirs.mount}:{theirs.pattern}"] = None
            if paths:
                return LaneConflict(task.task_key, other.task_key, "write_scope_overlap", tuple(paths))
    return None


def _first_inner_clash(writers: Sequence[TaskNode]) -> LaneConflict | None:
    """The first writer of a lane that clashes with an earlier one, by the rules of ``_first_clash``."""
    for n in range(1, len(writers)):
        clash = _first_clash(writers[n : n + 1], writers[:n])
        if clash is not None:
            return clash
    return None


def _rules_overlap(left: PathRule, right: PathRule) -> bool:
    return left.mount == right.mount and globs_overlap(left.pattern, right.pattern)


def _lane_route(tasks: Sequence[TaskNode]) -> Route | None:
    """Maximum class and maximum effort over the declared routes.

    Runtime, model and correction are kept only when every route agrees on them.
    """
    routes = [task.route for task in tasks if task.route is not None]
    if not routes:
        return None
    runtime = _common([route.runtime for route in routes])
    correction: RouteFloor | None = _common([route.correction for route in routes])
    return Route(
        max((route.model_class for route in routes), key=_CLASS_ORDER.index),
        max((route.effort for route in routes), key=_EFFORT_ORDER.index),
        runtime,
        None if runtime is None else _common([route.model for route in routes]),
        correction,
    )


def _common[T](values: list[T]) -> T | None:
    return values[0] if all(value == values[0] for value in values) else None


def _route_groups(lanes: tuple[Lane, ...]) -> tuple[RouteGroup, ...]:
    """Lanes with the same route, in lane order; lanes without a route ride with the first group (legacy)."""
    groups: dict[Route, list[int]] = {}
    free: list[int] = []
    for index, lane in enumerate(lanes):
        if lane.route is None:
            free.append(index)
        else:
            groups.setdefault(lane.route, []).append(index)
    out = [RouteGroup(route, tuple(indexes)) for route, indexes in groups.items()]
    if out and free:
        out[0] = RouteGroup(out[0].route, tuple(sorted((*out[0].lanes, *free))))
    return tuple(out)
