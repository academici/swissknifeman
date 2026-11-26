"""Dependency rules: cycles and batches (planning §5.7, module ``dependencies``).

A cycle is looked for on the graph *without* batch ordering first: a cycle that only the batch barrier closes
is a batch that waits for a later batch, reported once as ``batch_order_conflict``, not as
``dependency_cycle``.
A cycle that the barriers of several phases close together has no such batch to blame; the complete graph is
then judged and its cycle is a ``dependency_cycle``, so that no cycle the compiler rejects goes unreported.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.planning.domain.compile_graph import EdgeReason, compile_execution_graph
from skm.modules.planning.domain.validation.context import Locator
from skm.modules.planning.domain.validation.findings import FindingCode, finding, pointer_of

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skm.kernel.json_types import JsonValue
    from skm.modules.planning.domain.compile_graph import ExecutionGraph
    from skm.modules.planning.domain.specification import Specification
    from skm.modules.planning.domain.validation.context import ValidationContext
    from skm.modules.planning.domain.validation.findings import Finding


def graph_of(spec: Specification, *, batches: bool = True) -> ExecutionGraph | ValidationFailed:
    """The execution graph of ``spec``, or the cycle error; ``batches=False`` leaves the batch barrier out.

    Any other failure of the compiler is a defect and propagates.
    """
    if not batches:
        spec = dataclasses.replace(
            spec, phases=tuple(dataclasses.replace(p, batches=()) for p in spec.phases)
        )
    try:
        return compile_execution_graph(spec)
    except ValidationFailed as error:
        if error.code is ErrorCode.DEPENDENCY_CYCLE:
            return error
        raise


def placement_is_sound(spec: Specification) -> bool:
    """Do the keys of items and units agree with the phases and items they sit in?

    A graph built from a document that contradicts itself (``key_prefix_mismatch``) places tasks where their
    keys deny they belong, so a cycle or an overlap found in it would be an artefact of the misplacement. The
    graph rules then stay silent and the placement error is the finding to fix first.
    """
    item_keys = {item.key for item in spec.items}
    return all(item.key.startswith(f"{item.phase}.") for item in spec.items) and all(
        unit.key.split("/", 1)[0] in item_keys for unit in spec.units
    )


def _batches_are_sound(spec: Specification) -> bool:
    """Does every batch list only items of its own phase, and each item at most once?

    A barrier built from batches that contradict this orders an item against itself or against another phase's
    items: a cycle in it is an artefact of ``batch_foreign`` / ``batch_multiple``, the findings to fix first.
    """
    owner = {item.key: item.phase for item in spec.items}
    listed = [(phase.key, key) for phase in spec.phases for batch in phase.batches for key in batch.items]
    return len({key for _, key in listed}) == len(listed) and all(
        owner.get(key) == phase for phase, key in listed
    )


def _owner(task_key: str) -> str:
    """The item (or phase) of a task: ``P1.1/U2`` and ``P1.1#gate`` -> ``P1.1``, ``P1#gate`` -> ``P1``."""
    return task_key.split("#", 1)[0].split("/", 1)[0]


def _cycle_finding(ctx: ValidationContext, error: ValidationFailed) -> Finding:
    raw = error.details.get("cycle")
    cycle: list[JsonValue] = [str(task) for task in raw] if isinstance(raw, list) else []
    key = _owner(str(cycle[0])) if cycle else None
    owner = next((e for e in (*ctx.spec.items, *ctx.spec.phases) if e.key == key), None)
    return finding(
        FindingCode.DEPENDENCY_CYCLE,
        f"dependency cycle: {' -> '.join(map(str, cycle))}",
        key=key,
        entity_id=None if owner is None else owner.id,
        pointer=None if key is None else Locator(ctx.document).pointer(key, "depends_on"),
        details={"cycle": cycle},
    )


def dependency_cycle(ctx: ValidationContext) -> Iterator[Finding]:
    if not placement_is_sound(ctx.spec):
        return
    result = graph_of(ctx.spec, batches=False)
    if isinstance(result, ValidationFailed):
        yield _cycle_finding(ctx, result)
        return
    if not _batches_are_sound(ctx.spec):
        return
    complete = graph_of(ctx.spec)
    if isinstance(complete, ValidationFailed) and next(_batch_conflicts(ctx), None) is None:
        yield _cycle_finding(
            ctx, complete
        )  # closed by batch barriers alone, and no one batch waits for a later


def batch_foreign(ctx: ValidationContext) -> Iterator[Finding]:
    items = {item.key: item for item in ctx.spec.items}
    for p, phase in enumerate(ctx.spec.phases):
        for b, batch in enumerate(phase.batches):
            for n, key in enumerate(batch.items):
                item = items.get(key)
                if item is None or item.phase == phase.key:
                    continue
                yield finding(
                    FindingCode.BATCH_FOREIGN,
                    f"batch {phase.key}/{batch.key} lists {key}, an item of phase {item.phase}",
                    key=key,
                    entity_id=item.id,
                    pointer=pointer_of("phases", p, "batches", b, "items", n),
                    details={"batch": f"{phase.key}/{batch.key}", "item_phase": item.phase},
                )


def batch_multiple(ctx: ValidationContext) -> Iterator[Finding]:
    items = {item.key: item for item in ctx.spec.items}
    seen: dict[str, str] = {}
    for p, phase in enumerate(ctx.spec.phases):
        for b, batch in enumerate(phase.batches):
            for n, key in enumerate(batch.items):
                here = f"{phase.key}/{batch.key}"
                if key not in seen:
                    seen[key] = here
                    continue
                item = items.get(key)
                yield finding(
                    FindingCode.BATCH_MULTIPLE,
                    f"{key} is listed in more than one batch: {seen[key]} and {here}",
                    key=key,
                    entity_id=None if item is None else item.id,
                    pointer=pointer_of("phases", p, "batches", b, "items", n),
                    details={"first_batch": seen[key], "batch": here},
                )


def batch_unassigned(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    for phase in ctx.spec.phases:
        if not phase.batches:
            continue
        listed = {key for batch in phase.batches for key in batch.items}
        for item in ctx.spec.items_of(phase.key):
            if item.key not in listed:
                yield finding(
                    FindingCode.BATCH_UNASSIGNED,
                    f"{item.key} is in none of the batches of {phase.key}",
                    key=item.key,
                    entity_id=item.id,
                    pointer=loc.pointer(phase.key, "batches"),
                    details={"phase": phase.key},
                )


def batch_order_conflict(ctx: ValidationContext) -> Iterator[Finding]:
    yield from _batch_conflicts(ctx)


def _batch_conflicts(ctx: ValidationContext) -> Iterator[Finding]:
    if not placement_is_sound(ctx.spec):
        return
    graph = graph_of(ctx.spec, batches=False)
    if isinstance(graph, ValidationFailed):
        return  # the cycle is reported by dependency_cycle; reachability needs an acyclic graph
    prerequisites: dict[str, list[str]] = {node.task_key: [] for node in graph.tasks}
    for edge in graph.edges:
        if edge.reasons != frozenset({EdgeReason.BATCH_ORDER}):
            prerequisites[edge.dependent].append(edge.prerequisite)
    tasks_of: dict[str, list[str]] = {}
    for node in graph.tasks:
        if node.item_key is not None:
            tasks_of.setdefault(node.item_key, []).append(node.task_key)
    reach: dict[str, frozenset[str]] = {}

    def below(task: str) -> frozenset[str]:
        if task not in reach:
            found: set[str] = set()
            stack = list(prerequisites[task])
            while stack:
                node = stack.pop()
                if node not in found:
                    found.add(node)
                    stack.extend(prerequisites[node])
            reach[task] = frozenset(found)
        return reach[task]

    loc = Locator(ctx.document)
    items = {item.key: item for item in ctx.spec.items}
    for phase in ctx.spec.phases:
        for k, earlier in enumerate(phase.batches):
            for later in phase.batches[k + 1 :]:
                for a in earlier.items:
                    waits = set[str]().union(*(below(t) for t in tasks_of.get(a, ())))
                    for b in later.items:
                        if a == b or not waits.intersection(tasks_of.get(b, ())):
                            continue
                        item = items.get(a)
                        has_deps = item is not None and bool(item.depends_on)
                        yield finding(
                            FindingCode.BATCH_ORDER_CONFLICT,
                            f"{a} of batch {phase.key}/{earlier.key} waits for {b} of the later batch "
                            f"{phase.key}/{later.key}",
                            key=a,
                            entity_id=None if item is None else item.id,
                            pointer=loc.pointer(a, "depends_on")
                            if has_deps
                            else loc.pointer(phase.key, "batches"),
                            details={
                                "batch": f"{phase.key}/{earlier.key}",
                                "waits_for": b,
                                "waits_batch": f"{phase.key}/{later.key}",
                            },
                        )


RULES: Final = (batch_foreign, batch_multiple, batch_order_conflict, batch_unassigned, dependency_cycle)
