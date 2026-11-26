"""Run tasks compiled from the planning execution graph (execution §4.4-4.5, §7.1 ``start_run``; K14).

The input is the planning graph in its wire form (``urn:skm:planning:view:execution-graph:v1``): the
domain does not import planning, the application passes ``planning.public.compile_execution_graph`` of the
run's own revision. Every task keeps the revision entity identity it was compiled from; every planning
edge becomes a ``blocks`` edge with its planning reasons. ``plan_acceptance`` exists only in a full run
whose workflow has that stage.

Selection (K14): the chosen tasks (``task_keys`` and the tasks of ``phases``; all when both are empty),
cut by ``stop_after`` inclusively, plus every prerequisite that is not proven satisfied. An ancestor is
satisfied only by equal complete compatibility evidence of the same entity accepted in another run of
the plan; a matching name, spec or Git trailer is not evidence. A gate is compiled only when all its
members are; a dependent of a gate left out keeps waiting for the gate's compiled members instead.
"""

from __future__ import annotations

import graphlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, NoReturn, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import EntityId, TaskId
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.carry_forward import compare_compatibility
from skm.modules.execution.domain.execution_bundle import RunSelection, SatisfiedTask
from skm.modules.execution.domain.task import (
    GATE_KINDS,
    PathPattern,
    ReviewMode,
    Task,
    TaskKind,
    TaskStatus,
)
from skm.modules.execution.domain.workflow.definition import StageType

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import datetime

    from skm.kernel.ids import RevisionId, RunId, WorkspaceId
    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.blocking_reason import BlockingReason
    from skm.modules.execution.domain.carry_forward import CompatibilityInputs
    from skm.modules.execution.domain.contracts import ExecutionPolicy
    from skm.modules.execution.domain.workflow.definition import WorkflowDefinition

__all__ = [
    "GATE_MEMBER_REASONS",
    "PLAN_ACCEPTANCE_KEY",
    "CompiledRunTasks",
    "EdgeKind",
    "SatisfiedEvidence",
    "SelectionRequest",
    "TaskEdge",
    "TaskFacts",
    "compile_run_tasks",
    "gate_members",
    "prerequisites",
    "ready_task_ids",
]

PLAN_ACCEPTANCE_KEY: Final = "PLAN#accept"
GATE_MEMBER_REASONS: Final = frozenset({"ITEM_MEMBER", "PHASE_MEMBER"})
_SATISFYING: Final = frozenset({TaskStatus.ACCEPTED, TaskStatus.SKIPPED})
_PHASE_REVIEW: Final = {"off": ReviewMode.WAIVED, "on_risk": ReviewMode.SELF, "always": ReviewMode.REQUIRED}


class EdgeKind(StrEnum):
    BLOCKS = "blocks"
    BATCH = "batch"
    INTEGRATION = "integration"
    GATE_MEMBER = "gate_member"


# ``batch`` edges group tasks for joint scheduling; they never block readiness
_ORDERING: Final = frozenset({EdgeKind.BLOCKS, EdgeKind.INTEGRATION, EdgeKind.GATE_MEMBER})


@dataclass(frozen=True, slots=True)
class TaskEdge:
    run_id: RunId
    dependent_task_id: TaskId
    prerequisite_task_id: TaskId
    kind: EdgeKind
    reasons: frozenset[str]


@dataclass(frozen=True, slots=True)
class TaskFacts:
    """Spec facts the graph view does not carry: the work kind and the required review profile."""

    work_kind: str
    review_profile: str | None = None


@dataclass(frozen=True, slots=True)
class SelectionRequest:
    """``StartRun.selection``; keys are graph display keys and phase keys."""

    task_keys: tuple[str, ...] = ()
    phases: tuple[str, ...] = ()
    stop_after: str | None = None


@dataclass(frozen=True, slots=True)
class SatisfiedEvidence:
    """A task of the same entity accepted in another run of the plan and the evidence of both sides.

    The domain proves only what this value carries: the same revision entity and equal complete
    compatibility evidence (a missing target baseline or binding is never compatible). It carries no
    source run, plan or status, so that the source task is ``accepted``, belongs to another run of the
    same plan and that ``source``/``target`` were loaded from trusted records is the obligation of the
    ``execution.start_run`` handler that builds it (execution §7.1 step 3, K14); the exact effect
    receipt and reachability of the satisfied ancestor are re-proven by ``prepare_environment``.
    """

    source_task_id: TaskId
    source_entity_id: EntityId
    source: CompatibilityInputs
    target: CompatibilityInputs


@dataclass(frozen=True, slots=True)
class CompiledRunTasks:
    tasks: tuple[Task, ...]
    edges: tuple[TaskEdge, ...]
    selection: RunSelection | None
    compiler_version: int


@dataclass(frozen=True, slots=True)
class _Node:
    key: str
    kind: TaskKind
    entity_id: EntityId
    phase_key: str
    review: str | None
    write_scope: tuple[PathPattern, ...] | None


def compile_run_tasks(  # noqa: PLR0913
    graph: JsonObject,
    workflow: WorkflowDefinition,
    policy: ExecutionPolicy,
    selection: SelectionRequest | None,
    satisfied: Mapping[str, SatisfiedEvidence],
    *,
    run_id: RunId,
    workspace_id: WorkspaceId,
    revision_id: RevisionId,
    new_task_id: Callable[[], UUID],
    now: datetime,
    facts: Mapping[str, TaskFacts] | None = None,
) -> CompiledRunTasks:
    """Tasks (all ``blocked``) and edges of a new run; deterministic for the same input and ids.

    Errors: the graph of another revision or malformed → ``SCHEMA_INVALID``; an unknown selection key →
    ``NOT_FOUND`` (``details.keys``); an empty result → ``NO_TASKS``; a cycle → ``DEPENDENCY_CYCLE``.
    """
    version, nodes, order, planning_edges, batches = _parse(graph, revision_id)
    position = {key: index for index, key in enumerate(order)}
    prerequisites_of: dict[str, dict[str, frozenset[str]]] = {key: {} for key in nodes}
    for dependent, prerequisite, reasons in planning_edges:
        prerequisites_of[dependent][prerequisite] = reasons

    if selection is None:
        compiled, dropped = set(nodes), set[str]()
        reached_satisfied: dict[str, SatisfiedEvidence] = {}
    else:
        compiled, dropped, reached_satisfied = _select(nodes, prerequisites_of, selection, satisfied)
    if not compiled:
        raise error_for(ErrorCode.NO_TASKS, "the selection compiles no task")

    ids = {key: TaskId(new_task_id()) for key in sorted(compiled, key=position.__getitem__)}
    edges = _edges(run_id, ids, compiled, dropped, prerequisites_of, batches, position)
    with_plan = selection is None and any(
        stage.type is StageType.PLAN_ACCEPTANCE for stage in workflow.stages
    )
    plan_id: TaskId | None = TaskId(new_task_id()) if with_plan else None
    if plan_id is not None:
        edges.extend(
            TaskEdge(run_id, plan_id, ids[key], EdgeKind.GATE_MEMBER, frozenset())
            for key in sorted(ids, key=position.__getitem__)
            if nodes[key].kind is TaskKind.PHASE_GATE
        )
    _check_acyclic(edges)

    waits: dict[TaskId, list[str]] = {}
    for edge in edges:
        if edge.kind in _ORDERING:
            waits.setdefault(edge.dependent_task_id, []).append(str(edge.prerequisite_task_id))
    tasks = [
        _task(
            nodes[key],
            ids[key],
            position[key],
            run_id,
            workspace_id,
            policy,
            facts,
            waits.get(ids[key], []),
            now,
        )
        for key in ids
    ]
    if plan_id is not None:
        tasks.append(_plan_acceptance(plan_id, len(order), run_id, workspace_id, waits.get(plan_id, []), now))

    run_selection = None
    if selection is not None:
        run_selection = RunSelection(
            task_keys=selection.task_keys,
            phases=selection.phases,
            stop_after=selection.stop_after,
            compiled_keys=tuple(ids),
            satisfied=tuple(
                SatisfiedTask(key, reached_satisfied[key].source_task_id)
                for key in sorted(reached_satisfied, key=position.__getitem__)
            ),
        )
    return CompiledRunTasks(tuple(tasks), tuple(edges), run_selection, version)


def prerequisites(task_id: TaskId, edges: Sequence[TaskEdge]) -> tuple[TaskId, ...]:
    """Tasks that must be accepted or skipped before ``task_id`` (batch edges excluded)."""
    return tuple(
        edge.prerequisite_task_id
        for edge in edges
        if edge.dependent_task_id == task_id and edge.kind in _ORDERING
    )


def ready_task_ids(tasks: Sequence[Task], edges: Sequence[TaskEdge]) -> tuple[TaskId, ...]:
    """``blocked`` tasks whose every prerequisite is ``accepted`` or ``skipped`` (T1/T29), by position.

    A failed, cancelled or superseded prerequisite never makes a dependent ready.
    """
    status = {task.id: task.status for task in tasks}
    ready = [
        task
        for task in tasks
        if task.status is TaskStatus.BLOCKED
        and all(status.get(found) in _SATISFYING for found in prerequisites(task.id, edges))
    ]
    return tuple(task.id for task in sorted(ready, key=lambda task: (task.position, str(task.id))))


def gate_members(task: Task, edges: Sequence[TaskEdge]) -> tuple[TaskId, ...]:
    """Members of a gate: prerequisites by ``ITEM_MEMBER``/``PHASE_MEMBER`` or by ``gate_member`` edges."""
    return tuple(
        edge.prerequisite_task_id
        for edge in edges
        if edge.dependent_task_id == task.id
        and (
            edge.kind is EdgeKind.GATE_MEMBER
            or (edge.kind is EdgeKind.BLOCKS and edge.reasons & GATE_MEMBER_REASONS)
        )
    )


# ---------------------------------------------------------------- selection


def _select(
    nodes: Mapping[str, _Node],
    prerequisites_of: Mapping[str, Mapping[str, frozenset[str]]],
    selection: SelectionRequest,
    satisfied: Mapping[str, SatisfiedEvidence],
) -> tuple[set[str], set[str], dict[str, SatisfiedEvidence]]:
    """Compiled keys, gates left out for a missing member, and the satisfied ancestors met."""
    phases = {node.phase_key for node in nodes.values()}
    unknown = sorted(
        {key for key in selection.task_keys if key not in nodes}
        | {key for key in selection.phases if key not in phases}
        | (
            {selection.stop_after}
            if selection.stop_after is not None and selection.stop_after not in nodes
            else set()
        )
    )
    if unknown:
        raise error_for(ErrorCode.NOT_FOUND, "unknown selection keys", details={"keys": list(unknown)})
    chosen = set(selection.task_keys) | {
        key for key, node in nodes.items() if node.phase_key in selection.phases
    }
    if not selection.task_keys and not selection.phases:
        chosen = set(nodes)
    if selection.stop_after is not None:
        chosen &= _ancestors(selection.stop_after, prerequisites_of) | {selection.stop_after}

    proven = {key: evidence for key, evidence in satisfied.items() if _proven(key, evidence, nodes)}
    compiled: set[str] = set()
    reached: dict[str, SatisfiedEvidence] = {}
    stack = sorted(chosen)
    while stack:
        key = stack.pop()
        if key in compiled:
            continue
        if key not in chosen and key in proven:
            reached[key] = proven[key]
            continue
        compiled.add(key)
        stack.extend(sorted(prerequisites_of[key]))

    dropped: set[str] = set()
    changed = True
    while changed:  # a gate leaves when a member is missing, which may remove an enclosing gate
        changed = False
        for key in sorted(compiled):
            if nodes[key].kind in GATE_KINDS and not _members(key, prerequisites_of) <= compiled:
                compiled.discard(key)
                dropped.add(key)
                changed = True
    return compiled, dropped, reached


def _members(key: str, prerequisites_of: Mapping[str, Mapping[str, frozenset[str]]]) -> set[str]:
    return {found for found, reasons in prerequisites_of[key].items() if reasons & GATE_MEMBER_REASONS}


def _proven(key: str, evidence: SatisfiedEvidence, nodes: Mapping[str, _Node]) -> bool:
    """Same entity and equal complete compatibility evidence; anything else keeps the task in the run."""
    node = nodes.get(key)
    if node is None or node.entity_id != evidence.source_entity_id:
        return False
    return compare_compatibility(evidence.source, evidence.target).compatible


def _ancestors(key: str, prerequisites_of: Mapping[str, Mapping[str, frozenset[str]]]) -> set[str]:
    found: set[str] = set()
    stack = list(prerequisites_of[key])
    while stack:
        current = stack.pop()
        if current not in found:
            found.add(current)
            stack.extend(prerequisites_of[current])
    return found


# ---------------------------------------------------------------- edges and tasks


def _edges(
    run_id: RunId,
    ids: Mapping[str, TaskId],
    compiled: set[str],
    dropped: set[str],
    prerequisites_of: Mapping[str, Mapping[str, frozenset[str]]],
    batches: Sequence[tuple[str, tuple[str, ...]]],
    position: Mapping[str, int],
) -> list[TaskEdge]:
    pairs: dict[tuple[str, str], set[str]] = {}

    def compiled_prerequisites(key: str) -> Iterable[str]:
        # a left-out gate passes its compiled prerequisites on; a satisfied task is simply done
        for found in prerequisites_of[key]:
            if found in compiled:
                yield found
            elif found in dropped:
                yield from compiled_prerequisites(found)

    for dependent in compiled:
        for prerequisite, reasons in prerequisites_of[dependent].items():
            targets = [prerequisite] if prerequisite in compiled else []
            if prerequisite in dropped:
                targets = list(compiled_prerequisites(prerequisite))
            for target in targets:
                pairs.setdefault((dependent, target), set()).update(reasons)
    edges = [
        TaskEdge(run_id, ids[dependent], ids[prerequisite], EdgeKind.BLOCKS, frozenset(reasons))
        for (dependent, prerequisite), reasons in sorted(
            pairs.items(), key=lambda item: (position[item[0][0]], position[item[0][1]])
        )
    ]
    linked = {frozenset(pair) for pair in pairs}
    for _, members in batches:
        present = sorted((key for key in members if key in compiled), key=position.__getitem__)
        edges.extend(
            TaskEdge(run_id, ids[member], ids[present[0]], EdgeKind.BATCH, frozenset({"BATCH_REQUIRED"}))
            for member in present[1:]
            if frozenset((member, present[0])) not in linked
        )
    return edges


def _check_acyclic(edges: Sequence[TaskEdge]) -> None:
    sorter: graphlib.TopologicalSorter[TaskId] = graphlib.TopologicalSorter()
    for edge in edges:
        if edge.kind in _ORDERING:
            sorter.add(edge.dependent_task_id, edge.prerequisite_task_id)
    try:
        sorter.prepare()
    except graphlib.CycleError as exc:
        cycle = cast("list[TaskId]", exc.args[1])
        raise error_for(
            ErrorCode.DEPENDENCY_CYCLE,
            "the run task graph has a cycle",
            details={"cycle": [str(found) for found in cycle]},
        ) from exc


def _task(  # noqa: PLR0913
    node: _Node,
    task_id: TaskId,
    position: int,
    run_id: RunId,
    workspace_id: WorkspaceId,
    policy: ExecutionPolicy,
    facts: Mapping[str, TaskFacts] | None,
    waits: Sequence[str],
    now: datetime,
) -> Task:
    gate = node.kind in GATE_KINDS
    fact = None if facts is None else facts.get(node.key)
    if node.kind is TaskKind.UNIT:
        review = ReviewMode.SELF
    elif node.kind is TaskKind.PHASE_GATE:
        review = _PHASE_REVIEW.get(str(policy.get("phase_review", "off")), ReviewMode.WAIVED)
    else:
        review = ReviewMode(node.review) if node.review is not None else ReviewMode.REQUIRED
    return Task(
        id=task_id,
        run_id=run_id,
        workspace_id=workspace_id,
        kind=node.kind,
        spec_entity_id=node.entity_id,
        display_key=node.key,
        origin=None,
        position=position,
        status=TaskStatus.BLOCKED,
        work_kind="review" if gate else (fact.work_kind if fact is not None else "code"),
        review_mode=review,
        review_profile=None if fact is None else fact.review_profile,
        declared_write_scope=() if gate else node.write_scope,
        required_host_id=None,
        current_attempt_id=None,
        accepted_attempt_id=None,
        accepted_output_id=None,
        check_fix_rounds=0,
        review_rounds=0,
        attempt_count=0,
        blocking_reason=_waiting(task_id, node.key, waits, now),
        row_version=1,
    )


def _plan_acceptance(
    task_id: TaskId,
    position: int,
    run_id: RunId,
    workspace_id: WorkspaceId,
    waits: Sequence[str],
    now: datetime,
) -> Task:
    return Task(
        id=task_id,
        run_id=run_id,
        workspace_id=workspace_id,
        kind=TaskKind.PLAN_ACCEPTANCE,
        spec_entity_id=None,
        display_key=PLAN_ACCEPTANCE_KEY,
        origin=None,
        position=position,
        status=TaskStatus.BLOCKED,
        work_kind="review",
        review_mode=ReviewMode.WAIVED,
        review_profile=None,
        declared_write_scope=(),
        required_host_id=None,
        current_attempt_id=None,
        accepted_attempt_id=None,
        accepted_output_id=None,
        check_fix_rounds=0,
        review_rounds=0,
        attempt_count=0,
        blocking_reason=_waiting(task_id, PLAN_ACCEPTANCE_KEY, waits, now),
        row_version=1,
    )


def _waiting(task_id: TaskId, key: str, waits: Sequence[str], now: datetime) -> BlockingReason:
    return blocking_reason(
        BlockingCode.BLOCKED_BY_DEPENDENCY,
        task_id=task_id,
        refs={"prerequisite_task_ids": list(waits)},
        now=now,
        message=f"{key} waits for {len(waits)} prerequisite task(s)",
    )


# ---------------------------------------------------------------- graph parsing


def _parse(
    graph: JsonObject, revision_id: RevisionId
) -> tuple[
    int, dict[str, _Node], list[str], list[tuple[str, str, frozenset[str]]], list[tuple[str, tuple[str, ...]]]
]:
    try:
        version = graph["compiler_version"]
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            _bad("compiler_version", "compiler_version is a positive integer")
        if str(graph["revision_id"]) != str(revision_id):
            _bad("revision_id", "the graph belongs to another revision than the run")
        nodes: dict[str, _Node] = {}
        for raw in _list(graph["tasks"]):
            node = _node(_dict(raw))
            if node.key in nodes:
                _bad("tasks", f"duplicate task key {node.key}")
            nodes[node.key] = node
        edges: list[tuple[str, str, frozenset[str]]] = []
        for raw in _list(graph["edges"]):
            edge = _dict(raw)
            dependent, prerequisite = str(edge["dependent"]), str(edge["prerequisite"])
            if dependent not in nodes or prerequisite not in nodes or dependent == prerequisite:
                _bad("edges", f"edge {dependent} <- {prerequisite} names unknown or equal tasks")
            # planning reasons, stored as UNIT_DEPENDS_ON, PHASE_MEMBER, … (run_task_edges.reasons)
            reasons = frozenset(str(reason).upper() for reason in _list(edge["reasons"]))
            edges.append((dependent, prerequisite, reasons))
        order = [str(key) for key in _list(graph["topological_order"])]
        if sorted(order) != sorted(nodes):
            _bad("topological_order", "topological_order lists every task once")
        # ``batch`` is the field name of the earlier graph example; the view uses ``batch_key``.
        # Work tasks of a required batch start together; its gates follow their members.
        batches = [
            (
                str(_dict(raw).get("batch_key", _dict(raw).get("batch"))),
                tuple(
                    str(key)
                    for key in _list(_dict(raw)["tasks"])
                    if str(key) in nodes and nodes[str(key)].kind not in GATE_KINDS
                ),
            )
            for raw in _list(graph.get("batch_groups", []))
            if _dict(raw).get("mode") == "required"
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise error_for(ErrorCode.SCHEMA_INVALID, f"invalid execution graph: {exc}") from exc
    return version, nodes, order, edges, batches


def _node(raw: Mapping[str, JsonValue]) -> _Node:
    kind = TaskKind(str(raw["task_kind"]))
    if kind not in {TaskKind.UNIT, TaskKind.ITEM, TaskKind.ITEM_GATE, TaskKind.PHASE_GATE}:
        _bad("task_kind", f"the planning graph has no {kind} tasks")
    # ``phase``/``item`` are the field names of the earlier graph example; the view uses ``*_key``
    phase = raw.get("phase_key", raw.get("phase"))
    scope = raw.get("write_scope")
    patterns = None
    if scope is not None:
        patterns = tuple(
            PathPattern(str(_dict(entry)["mount"]), str(_dict(entry)["pattern"])) for entry in _list(scope)
        )
    review = raw.get("review")
    return _Node(
        key=str(raw["task_key"]),
        kind=kind,
        entity_id=EntityId(UUID(str(raw["entity_id"]))),
        phase_key=str(phase),
        review=None if review is None else str(review),
        write_scope=patterns,
    )


def _list(value: JsonValue | object) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError("expected an array")
    return cast("list[JsonValue]", value)


def _dict(value: JsonValue | object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError("expected an object")
    return cast("dict[str, JsonValue]", value)


def _bad(field: str, message: str) -> NoReturn:
    raise error_for(ErrorCode.SCHEMA_INVALID, message, details={"field": field})
