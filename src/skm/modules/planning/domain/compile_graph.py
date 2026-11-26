"""Execution graph v1: one deterministic task graph for preview and execution (planning §5.4).

Pure domain code. Units, items, item gates and phase gates become tasks; unit, item, phase, batch and
plan ordering become edges ``dependent <- prerequisite`` with the reasons that produced them. Cycles are
looked for on the compiled graph, so a cycle that only closes through a phase gate is found as well.
Work-policy overrides are carried as raw declared facts (the task's ``entity_id`` is the unit or item that
declared them, ``item_key`` the item); settings defaults, locks and caps are resolved by execution.
"""

from __future__ import annotations

import graphlib
import heapq
import itertools
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.planning.domain.display_keys import parse_check_ref, parse_unit_ref
from skm.modules.planning.domain.execution_constraints import PathRule
from skm.modules.planning.domain.item import AuthorityKind, ExternalGate, OwnerGate
from skm.modules.planning.domain.phase import Strategy
from skm.modules.planning.domain.review_requirement import RequiredReview, ReviewMode, SelfReview
from skm.modules.planning.domain.specification import EntityKind

if TYPE_CHECKING:
    from collections.abc import Iterable

    from skm.kernel.ids import EntityId, RevisionId
    from skm.modules.planning.domain.item import Authority, Item, Route, WorkPolicyOverride
    from skm.modules.planning.domain.phase import BatchMode, Phase
    from skm.modules.planning.domain.review_requirement import ReviewRequirement
    from skm.modules.planning.domain.specification import Specification
    from skm.modules.planning.domain.unit import Unit

COMPILER_VERSION: Final = 1

type OrderKey = tuple[int, int, int, int]


class TaskKind(StrEnum):
    UNIT = "unit"
    ITEM = "item"
    ITEM_GATE = "item_gate"
    PHASE_GATE = "phase_gate"


@dataclass(frozen=True, slots=True)
class CheckBinding:
    check_key: str
    check_id: EntityId


@dataclass(frozen=True, slots=True)
class TaskNode:
    task_key: str
    task_kind: TaskKind
    entity_id: EntityId
    entity_kind: EntityKind
    phase_key: str
    item_key: str | None
    checks: tuple[CheckBinding, ...]
    review: ReviewMode | None
    criteria: tuple[str, ...]
    route: Route | None
    item_work_policy: WorkPolicyOverride | None
    unit_work_policy: WorkPolicyOverride | None
    write_scope: tuple[PathRule, ...] | None
    authority: AuthorityKind
    materials: tuple[EntityId, ...]


class EdgeReason(StrEnum):
    UNIT_DEPENDS_ON = "unit_depends_on"
    UNIT_PARENT = "unit_parent"
    UNIT_SEQUENTIAL = "unit_sequential"
    ITEM_MEMBER = "item_member"
    ITEM_DEPENDS_ON = "item_depends_on"
    PHASE_MEMBER = "phase_member"
    PHASE_DEPENDS_ON = "phase_depends_on"
    PHASE_SEQUENTIAL = "phase_sequential"
    BATCH_ORDER = "batch_order"
    PLAN_SEQUENTIAL = "plan_sequential"


@dataclass(frozen=True, slots=True)
class TaskEdge:
    dependent: str
    prerequisite: str
    reasons: frozenset[EdgeReason]


@dataclass(frozen=True, slots=True)
class BatchGroup:
    phase_key: str
    batch_key: str
    mode: BatchMode
    tasks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionGraph:
    compiler_version: int
    revision_id: RevisionId | None
    tasks: tuple[TaskNode, ...]
    edges: tuple[TaskEdge, ...]
    batch_groups: tuple[BatchGroup, ...]
    topological_order: tuple[str, ...]


def item_gate_key(item_key: str) -> str:
    return f"{item_key}#gate"


def phase_gate_key(phase_key: str) -> str:
    return f"{phase_key}#gate"


def compile_execution_graph(spec: Specification, revision_id: RevisionId | None = None) -> ExecutionGraph:
    """Compile ``spec`` (a draft when ``revision_id`` is ``None``); the same input gives the same graph.

    Unknown references are skipped: reporting them is the job of the validation rules. A cycle raises
    ``ValidationFailed(DEPENDENCY_CYCLE, details={"cycle": [task_key, ...]})``: the path follows the edges
    from prerequisite to dependent and repeats its first task at the end.
    """
    return _Compiler(spec).compile(revision_id)


@dataclass(frozen=True, slots=True)
class _ItemTasks:
    item: Item
    tasks: tuple[str, ...]  # unit tasks then the gate, or the item task alone
    entries: tuple[str, ...]
    sink: str


class _Compiler:
    def __init__(self, spec: Specification) -> None:
        self._spec = spec
        self._order: dict[str, OrderKey] = {}
        self._nodes: list[TaskNode] = []
        self._edges: dict[tuple[str, str], set[EdgeReason]] = {}
        self._items: dict[str, _ItemTasks] = {}
        self._checks = {f"{check.owner}:{check.key}": check for check in spec.checks}

    def compile(self, revision_id: RevisionId | None) -> ExecutionGraph:
        spec = self._spec
        phase_items = {phase.key: spec.items_of(phase.key) for phase in spec.phases}
        for phase_pos, phase in enumerate(spec.phases):
            items = phase_items[phase.key]
            for item_pos, item in enumerate(items):
                self._add_item(item, phase_pos, item_pos)
            checks = self._bind(f"{check.owner}:{check.key}" for check in spec.checks_of(phase.key))
            self._add_node(
                _phase_gate_node(phase, checks, self._materials(phase.key)), (phase_pos, len(items), 0, 0)
            )
        unit_tasks = {node.task_key for node in self._nodes if node.task_kind is TaskKind.UNIT}
        for items in phase_items.values():
            for item in items:
                self._item_edges(item, unit_tasks)
        for phase_pos, phase in enumerate(spec.phases):
            self._phase_edges(phase, phase_pos, phase_items[phase.key])
        if spec.execution_constraints.strategy is Strategy.SEQUENTIAL:
            ordered = [self._items[item.key] for items in phase_items.values() for item in items]
            self._chain(ordered, EdgeReason.PLAN_SEQUENTIAL)
        self._nodes.sort(key=lambda node: self._order[node.task_key])
        edges = tuple(
            TaskEdge(dependent, prerequisite, frozenset(reasons))
            for (dependent, prerequisite), reasons in sorted(
                self._edges.items(), key=lambda entry: (self._order[entry[0][0]], self._order[entry[0][1]])
            )
        )
        self._require_acyclic()
        return ExecutionGraph(
            COMPILER_VERSION,
            revision_id,
            tuple(self._nodes),
            edges,
            self._batch_groups(),
            self._topological(),
        )

    # ------------------------------------------------------------------ tasks

    def _add_node(self, node: TaskNode, order: OrderKey) -> None:
        self._order[node.task_key] = order
        self._nodes.append(node)

    def _add_item(self, item: Item, phase_pos: int, item_pos: int) -> None:
        spec = self._spec
        units = spec.units_of(item.key)
        review = _review_mode(item.review)
        authority = _authority_kind(item.authority)
        criteria = tuple(criterion.key for criterion in spec.criteria_of(item.key))
        if not units:
            self._add_node(
                TaskNode(
                    task_key=item.key,
                    task_kind=TaskKind.ITEM,
                    entity_id=item.id,
                    entity_kind=EntityKind.ITEM,
                    phase_key=item.phase,
                    item_key=item.key,
                    checks=self._bind(f"{check.owner}:{check.key}" for check in spec.checks_of(item.key)),
                    review=review,
                    criteria=criteria,
                    route=item.route,
                    item_work_policy=item.work_policy,
                    unit_work_policy=None,
                    write_scope=_hint_scope(item),
                    authority=authority,
                    materials=self._materials(item.phase, item.key),
                ),
                (phase_pos, item_pos, 0, 0),
            )
            return
        bound: set[str] = set()
        for unit_pos, unit in enumerate(units):
            checks = self._bind(parse_check_ref(ref, default_owner=item.key) for ref in unit.checks)
            bound.update(binding.check_key for binding in checks)
            self._add_node(
                TaskNode(
                    task_key=unit.key,
                    task_kind=TaskKind.UNIT,
                    entity_id=unit.id,
                    entity_kind=EntityKind.UNIT,
                    phase_key=item.phase,
                    item_key=item.key,
                    checks=checks,
                    review=None,
                    criteria=tuple(criterion.key for criterion in spec.criteria_of(unit.key)),
                    route=unit.route if unit.route is not None else item.route,
                    item_work_policy=item.work_policy,
                    unit_work_policy=unit.work_policy,
                    write_scope=_unit_scope(unit),
                    authority=authority,
                    materials=self._materials(item.phase, item.key, unit.key),
                ),
                (phase_pos, item_pos, 0, unit_pos),
            )
        gate_checks = (
            key
            for key in (f"{check.owner}:{check.key}" for check in spec.checks_of(item.key))
            if key not in bound
        )
        self._add_node(
            TaskNode(
                task_key=item_gate_key(item.key),
                task_kind=TaskKind.ITEM_GATE,
                entity_id=item.id,
                entity_kind=EntityKind.ITEM,
                phase_key=item.phase,
                item_key=item.key,
                checks=self._bind(gate_checks),
                review=review,
                criteria=criteria,
                route=None,
                item_work_policy=item.work_policy,
                unit_work_policy=None,
                write_scope=(),
                authority=authority,
                materials=self._materials(item.phase, item.key),
            ),
            (phase_pos, item_pos, 1, 0),
        )

    def _bind(self, keys: Iterable[str]) -> tuple[CheckBinding, ...]:
        bindings: dict[str, CheckBinding] = {}
        for key in keys:
            check = self._checks.get(key)
            if check is not None and key not in bindings:
                bindings[key] = CheckBinding(key, check.id)
        return tuple(bindings.values())

    def _materials(self, *scope: str) -> tuple[EntityId, ...]:
        return tuple(
            material.id
            for material in self._spec.materials
            if material.is_global or any(key in material.applies_to for key in scope)
        )

    # ------------------------------------------------------------------ edges

    def _edge(self, dependent: str, prerequisite: str, reason: EdgeReason) -> None:
        self._edges.setdefault((dependent, prerequisite), set()).add(reason)

    def _item_edges(self, item: Item, unit_keys: set[str]) -> None:
        """Edges inside one item, then its entries and sink (computed before any edge between items).

        ``unit_keys`` are the compiled unit tasks: a unit whose item is not compiled has no task, so an edge
        to it is skipped like any other unknown reference.
        """
        units = self._spec.units_of(item.key)
        if not units:
            self._items[item.key] = _ItemTasks(item, (item.key,), (item.key,), item.key)
            return
        gate = item_gate_key(item.key)
        siblings: dict[str | None, list[str]] = {}
        for unit in units:
            for ref in unit.depends_on:
                target = parse_unit_ref(ref, owner_item=item.key)
                if target in unit_keys:
                    self._edge(unit.key, target, EdgeReason.UNIT_DEPENDS_ON)
            parent = None if unit.parent is None else parse_unit_ref(unit.parent, owner_item=item.key)
            if parent is not None and parent in unit_keys:
                self._edge(parent, unit.key, EdgeReason.UNIT_PARENT)
            siblings.setdefault(parent, []).append(unit.key)
        if item.unit_strategy is Strategy.SEQUENTIAL:
            for group in siblings.values():
                for previous, following in itertools.pairwise(group):
                    self._edge(following, previous, EdgeReason.UNIT_SEQUENTIAL)
        for unit in units:
            self._edge(gate, unit.key, EdgeReason.ITEM_MEMBER)
        tasks = (*(unit.key for unit in units), gate)
        entries = tuple(task for task in tasks if not any((task, other) in self._edges for other in tasks))
        self._items[item.key] = _ItemTasks(item, tasks, entries, gate)

    def _link(self, dependent: _ItemTasks, prerequisite: _ItemTasks, reason: EdgeReason) -> None:
        for entry in dependent.entries:
            self._edge(entry, prerequisite.sink, reason)

    def _chain(self, ordered: list[_ItemTasks], reason: EdgeReason) -> None:
        for previous, following in itertools.pairwise(ordered):
            self._link(following, previous, reason)

    def _phase_edges(self, phase: Phase, phase_pos: int, items: tuple[Item, ...]) -> None:
        gate = phase_gate_key(phase.key)
        known = {other.key for other in self._spec.phases}
        members = [self._items[item.key] for item in items]
        for member in members:
            for dep in member.item.depends_on:
                target = self._items.get(dep)
                if target is not None:
                    self._link(member, target, EdgeReason.ITEM_DEPENDS_ON)
            self._edge(gate, member.sink, EdgeReason.PHASE_MEMBER)
        if phase.depends_on is not None:
            deps = [dep for dep in phase.depends_on if dep in known]
        else:
            deps = [self._spec.phases[phase_pos - 1].key] if phase_pos else []
        for dep in deps:
            if members:
                for member in members:
                    for entry in member.entries:
                        self._edge(entry, phase_gate_key(dep), EdgeReason.PHASE_DEPENDS_ON)
            else:
                self._edge(gate, phase_gate_key(dep), EdgeReason.PHASE_DEPENDS_ON)
        if phase.strategy is Strategy.SEQUENTIAL:
            self._chain(members, EdgeReason.PHASE_SEQUENTIAL)
        batches = [self._batch_items(batch.items) for batch in phase.batches]
        for earlier, later in itertools.pairwise(batches):
            for following in later:
                for previous in earlier:
                    self._link(following, previous, EdgeReason.BATCH_ORDER)

    def _batch_items(self, keys: tuple[str, ...]) -> list[_ItemTasks]:
        return [self._items[key] for key in dict.fromkeys(keys) if key in self._items]

    def _batch_groups(self) -> tuple[BatchGroup, ...]:
        groups: list[BatchGroup] = []
        for phase in self._spec.phases:
            for batch in phase.batches:
                tasks = {task for member in self._batch_items(batch.items) for task in member.tasks}
                ordered = tuple(sorted(tasks, key=self._order.__getitem__))
                groups.append(BatchGroup(phase.key, batch.key, batch.mode, ordered))
        return tuple(groups)

    # ------------------------------------------------------------------ order and cycles

    def _successors(self) -> dict[str, list[str]]:
        """Prerequisite -> its dependents, each list in ``order_key``."""
        successors: dict[str, list[str]] = {node.task_key: [] for node in self._nodes}
        for dependent, prerequisite in self._edges:
            successors[prerequisite].append(dependent)
        for following in successors.values():
            following.sort(key=self._order.__getitem__)
        return successors

    def _require_acyclic(self) -> None:
        sorter: graphlib.TopologicalSorter[str] = graphlib.TopologicalSorter()
        for node in self._nodes:
            sorter.add(node.task_key)
        for dependent, prerequisite in self._edges:
            sorter.add(dependent, prerequisite)
        try:
            sorter.prepare()
        except graphlib.CycleError:
            cycle = _first_cycle([node.task_key for node in self._nodes], self._successors())
            raise ValidationFailed(
                ErrorCode.DEPENDENCY_CYCLE,
                f"dependency cycle: {' -> '.join(cycle)}",
                details={"cycle": list(cycle)},
            ) from None

    def _topological(self) -> tuple[str, ...]:
        """Kahn's algorithm; among the ready tasks the smallest ``order_key`` always goes first."""
        successors = self._successors()
        indegree = {node.task_key: 0 for node in self._nodes}
        for dependent, _ in self._edges:
            indegree[dependent] += 1
        ready = [(self._order[key], key) for key, count in indegree.items() if count == 0]
        heapq.heapify(ready)
        order: list[str] = []
        while ready:
            _, key = heapq.heappop(ready)
            order.append(key)
            for dependent in successors[key]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    heapq.heappush(ready, (self._order[dependent], dependent))
        return tuple(order)


def _first_cycle(ordered: list[str], successors: dict[str, list[str]]) -> tuple[str, ...]:
    """The first cycle a depth-first walk meets, following dependents in ``order_key`` from each task.

    Iterative, so a long chain cannot exhaust the interpreter stack; the result is closed by its first task.
    """
    visited: set[str] = set()
    for root in ordered:
        if root in visited:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        on_path: dict[str, int] = {root: 0}
        visited.add(root)
        while stack:
            task, index = stack[-1]
            following = successors[task]
            if index == len(following):
                stack.pop()
                del on_path[task]
                continue
            stack[-1] = (task, index + 1)
            successor = following[index]
            if successor in on_path:
                path = [entry for entry, _ in stack[on_path[successor] :]]
                return (*path, successor)
            if successor not in visited:
                visited.add(successor)
                on_path[successor] = len(stack)
                stack.append((successor, 0))
    raise AssertionError("graphlib reported a cycle the walk did not find")


def _phase_gate_node(
    phase: Phase, checks: tuple[CheckBinding, ...], materials: tuple[EntityId, ...]
) -> TaskNode:
    """A phase gate carries no review, route or work policy of its own: execution applies settings only."""
    return TaskNode(
        task_key=phase_gate_key(phase.key),
        task_kind=TaskKind.PHASE_GATE,
        entity_id=phase.id,
        entity_kind=EntityKind.PHASE,
        phase_key=phase.key,
        item_key=None,
        checks=checks,
        review=None,
        criteria=(),
        route=None,
        item_work_policy=None,
        unit_work_policy=None,
        write_scope=(),
        authority=AuthorityKind.ROUTINE,
        materials=materials,
    )


def _review_mode(review: ReviewRequirement) -> ReviewMode:
    if isinstance(review, RequiredReview):
        return ReviewMode.REQUIRED
    if isinstance(review, SelfReview):
        return ReviewMode.SELF
    return ReviewMode.WAIVED


def _authority_kind(authority: Authority) -> AuthorityKind:
    if isinstance(authority, OwnerGate):
        return AuthorityKind.OWNER_GATE
    if isinstance(authority, ExternalGate):
        return AuthorityKind.EXTERNAL_GATE
    return AuthorityKind.ROUTINE


def _unit_scope(unit: Unit) -> tuple[PathRule, ...] | None:
    """Declared write scope of a unit; none declared is unknown (``None``), not "writes nothing"."""
    rules = tuple(dict.fromkeys(PathRule(entry.mount, entry.pattern) for entry in unit.write_scope))
    return rules or None


def _hint_scope(item: Item) -> tuple[PathRule, ...] | None:
    """Footprint of an item without units: its change hints; none is unknown and conflicts with everything."""
    rules = tuple(dict.fromkeys(PathRule(hint.mount, hint.pattern) for hint in item.change_hints))
    return rules or None
