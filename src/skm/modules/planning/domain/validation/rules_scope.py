"""Scope rules: mounts, write scopes, their overlap and coverage (planning §5.7, module ``scope``).

Patterns are compared by the may-overlap rule of ``globs`` (unknown overlaps) and covered by its ``covers``
(unknown is not covered). Only declared footprints are reported as overlapping: a task without a declared
footprint conflicts with everything for the scheduler (§5.5) but is not a defect of the plan.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Final

from skm.kernel.errors import ValidationFailed
from skm.modules.planning.domain.compile_graph import TaskKind
from skm.modules.planning.domain.execution_constraints import PathRule
from skm.modules.planning.domain.item import Item, WorkKind
from skm.modules.planning.domain.reads import RepositoryPathRead
from skm.modules.planning.domain.unit import Unit
from skm.modules.planning.domain.validation.context import Locator, ValidationSettings
from skm.modules.planning.domain.validation.findings import FindingCode, finding, pointer_of
from skm.modules.planning.domain.validation.globs import covers, globs_overlap
from skm.modules.planning.domain.validation.rules_dependencies import graph_of, placement_is_sound

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from skm.kernel.ids import EntityId
    from skm.kernel.json_types import JsonValue
    from skm.modules.planning.domain.compile_graph import TaskNode
    from skm.modules.planning.domain.reads import Read
    from skm.modules.planning.domain.validation.context import ValidationContext
    from skm.modules.planning.domain.validation.findings import Finding

_WRITING_KINDS: Final = frozenset({WorkKind.CODE, WorkKind.CONFIG, WorkKind.TEST, WorkKind.DOCS})
_TEST_NAMES: Final = ("test_*", "*_test.*", "*.test.*", "*.spec.*", "*Test.*")
type _Mount = tuple[str, EntityId | None, str | None, str]  # (entity key, entity id, pointer, mount)


def _read_mounts(
    key: str, entity_id: EntityId, reads: Iterable[Read], group: str, loc: Locator
) -> Iterator[_Mount]:
    for n, read in enumerate(reads):
        if isinstance(read, RepositoryPathRead):
            yield key, entity_id, loc.pointer(key, group, n, "mount"), read.mount


def _item_mounts(ctx: ValidationContext, loc: Locator) -> Iterator[_Mount]:
    for phase in ctx.spec.phases:
        yield from _read_mounts(phase.key, phase.id, phase.supporting, "supporting", loc)
    for item in ctx.spec.items:
        yield from _read_mounts(item.key, item.id, item.reads, "reads", loc)
        yield from _read_mounts(item.key, item.id, item.examples, "examples", loc)
        for n, hint in enumerate(item.change_hints):
            yield item.key, item.id, loc.pointer(item.key, "change_hints", n, "mount"), hint.mount
        for n, artifact in enumerate(item.artifacts):
            yield item.key, item.id, loc.pointer(item.key, "artifacts", n, "mount"), artifact.mount


def _unit_mounts(ctx: ValidationContext, loc: Locator) -> Iterator[_Mount]:
    for unit in ctx.spec.units:
        yield from _read_mounts(unit.key, unit.id, unit.reads, "reads", loc)
        for n, entry in enumerate(unit.write_scope):
            yield unit.key, unit.id, loc.pointer(unit.key, "write_scope", n, "mount"), entry.mount
        for n, output in enumerate(unit.outputs):
            yield unit.key, unit.id, loc.pointer(unit.key, "outputs", n, "mount"), output.mount
        if unit.command is not None:
            cwd = unit.command.definition.cwd
            yield unit.key, unit.id, loc.pointer(unit.key, "command", "definition", "cwd", "mount"), cwd.mount


def _mounts(ctx: ValidationContext) -> Iterator[_Mount]:
    """Every mount the document names, with the entity that names it and the pointer of the mount."""
    loc = Locator(ctx.document)
    yield from _item_mounts(ctx, loc)
    yield from _unit_mounts(ctx, loc)
    for check in ctx.spec.checks:
        cwd = getattr(check.definition, "cwd", None)
        if cwd is not None:
            key = f"{check.owner}:{check.key}"
            yield key, check.id, loc.pointer(key, "definition", "cwd", "mount"), cwd.mount
    for material in ctx.spec.materials:
        if material.mount is not None:
            key = f"material/{material.key}"
            yield key, material.id, loc.pointer(key, "mount"), material.mount
    for n, rule in enumerate(ctx.spec.execution_constraints.forbidden_paths):
        pointer = pointer_of("execution_constraints", "forbidden_paths", n, "mount")
        yield "execution_constraints", None, pointer, rule.mount


def mount_unknown(ctx: ValidationContext) -> Iterator[Finding]:
    for key, entity_id, pointer, mount in _mounts(ctx):
        if mount not in ctx.project_mounts:
            yield finding(
                FindingCode.MOUNT_UNKNOWN,
                f"{key} names mount {mount}, which the project does not have",
                key=key,
                entity_id=entity_id,
                pointer=pointer,
                details={"mount": mount},
            )


def _footprints(ctx: ValidationContext) -> Iterator[tuple[str, EntityId, str, PathRule]]:
    """``(entity key, id, pointer of the pattern, rule)`` of every change hint and unit write scope entry."""
    loc = Locator(ctx.document)
    for item in ctx.spec.items:
        for n, hint in enumerate(item.change_hints):
            yield (
                item.key,
                item.id,
                loc.pointer(item.key, "change_hints", n, "pattern") or "",
                PathRule(hint.mount, hint.pattern),
            )
    for unit in ctx.spec.units:
        for n, entry in enumerate(unit.write_scope):
            yield (
                unit.key,
                unit.id,
                loc.pointer(unit.key, "write_scope", n, "pattern") or "",
                PathRule(entry.mount, entry.pattern),
            )


def forbidden_path_conflict(ctx: ValidationContext) -> Iterator[Finding]:
    forbidden = ctx.spec.execution_constraints.forbidden_paths
    for key, entity_id, pointer, rule in _footprints(ctx):
        for barred in forbidden:
            if rule.mount == barred.mount and globs_overlap(rule.pattern, barred.pattern):
                yield finding(
                    FindingCode.FORBIDDEN_PATH_CONFLICT,
                    f"{key} may write {rule.mount}:{rule.pattern}, which overlaps the forbidden "
                    f"{barred.mount}:{barred.pattern}",
                    key=key,
                    entity_id=entity_id,
                    pointer=pointer,
                    details={
                        "path": f"{rule.mount}:{rule.pattern}",
                        "forbidden": f"{barred.mount}:{barred.pattern}",
                    },
                )


def write_scope_empty(ctx: ValidationContext) -> Iterator[Finding]:
    """Writing work without a footprint: an item with no change hints and no scoped unit, else each such unit.

    A unit task writes only within its own ``write_scope`` (item change hints do not reach it), so a
    writing unit without one can never be granted a write. A finding for the whole item covers its units.
    """
    loc = Locator(ctx.document)
    for item in ctx.spec.items:
        units = ctx.spec.units_of(item.key)
        if (
            item.work_kind in _WRITING_KINDS
            and not item.change_hints
            and not any(unit.write_scope for unit in units)
        ):
            yield _item_without_footprint(item, loc)
            continue
        for unit in units:
            kind = unit.work_kind or item.work_kind
            if kind in _WRITING_KINDS and not unit.write_scope:
                yield finding(
                    FindingCode.WRITE_SCOPE_EMPTY,
                    f"{unit.key} is {kind.value} work but declares no write scope",
                    key=unit.key,
                    entity_id=unit.id,
                    pointer=loc.pointer(unit.key, "write_scope"),
                    details={"work_kind": kind.value},
                )


def _item_without_footprint(item: Item, loc: Locator) -> Finding:
    return finding(
        FindingCode.WRITE_SCOPE_EMPTY,
        f"{item.key} is {item.work_kind.value} work but declares no change hints and no unit write scope",
        key=item.key,
        entity_id=item.id,
        pointer=loc.pointer(item.key, "change_hints"),
        details={"work_kind": item.work_kind.value},
    )


def _is_test_path(path: str) -> bool:
    parts = [part for part in path.split("/") if part not in ("", ".")]
    if any(part in ("tests", "test") for part in parts):
        return True
    name = parts[-1] if parts else ""
    return any(fnmatchcase(name, pattern) for pattern in _TEST_NAMES)


def write_scope_no_tests(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    suffixes = ValidationSettings.of(ctx.settings).code_suffixes
    for item in ctx.spec.items:
        scopes = [entry.pattern for unit in ctx.spec.units_of(item.key) for entry in unit.write_scope]
        declared = [*(h.pattern for h in item.change_hints), *scopes]
        # What the item writes is what its hints create or modify and what its units' write scopes name.
        hinted = [h.pattern for h in item.change_hints if h.change in ("create", "modify")]
        written = list(dict.fromkeys([*hinted, *scopes]))
        code = [path for path in written if path.endswith(suffixes)] if suffixes else []
        if not code or any(_is_test_path(path) for path in declared):
            continue
        code_paths: list[JsonValue] = [*code[:10]]
        yield finding(
            FindingCode.WRITE_SCOPE_NO_TESTS,
            f"{item.key} changes code ({', '.join(code[:3])}{', ...' if len(code) > 3 else ''}) "
            "but names no test path",
            key=item.key,
            entity_id=item.id,
            pointer=loc.pointer(item.key, "change_hints"),
            details={"code_paths": code_paths},
        )


class _Order:
    """Which tasks are ordered by a path (either way): the prerequisites closure, computed once."""

    def __init__(self, prerequisites: dict[str, list[str]]) -> None:
        self._prerequisites = prerequisites
        self._below: dict[str, frozenset[str]] = {}

    def below(self, task: str) -> frozenset[str]:
        if task not in self._below:
            found: set[str] = set()
            stack = list(self._prerequisites[task])
            while stack:
                node = stack.pop()
                if node not in found:
                    found.add(node)
                    stack.extend(self._prerequisites[node])
            self._below[task] = frozenset(found)
        return self._below[task]

    def ordered(self, first: str, second: str) -> bool:
        return second in self.below(first) or first in self.below(second)


def _declared(ctx: ValidationContext, task: TaskNode, loc: Locator) -> list[tuple[PathRule, str]]:
    """The footprint of a unit or item task as ``(rule, pointer of its pattern)``; empty if undeclared."""
    entity = ctx.spec.entity(task.entity_id)
    if isinstance(entity, Unit):
        return [
            (PathRule(e.mount, e.pattern), loc.pointer(entity.key, "write_scope", n, "pattern") or "")
            for n, e in enumerate(entity.write_scope)
        ]
    if isinstance(entity, Item):
        return [
            (PathRule(h.mount, h.pattern), loc.pointer(entity.key, "change_hints", n, "pattern") or "")
            for n, h in enumerate(entity.change_hints)
        ]
    return []


def _overlaps(
    ctx: ValidationContext,
) -> Iterator[tuple[TaskNode, TaskNode, Sequence[tuple[PathRule, PathRule]], str]]:
    """Tasks with declared, overlapping footprints, no path between them: ``(first, second, hits, pointer)``.

    ``pointer`` is the pattern of ``second`` that overlaps ``first``.
    """
    if not placement_is_sound(ctx.spec):
        return
    graph = graph_of(ctx.spec)
    if isinstance(graph, ValidationFailed):
        return  # a cycle leaves no order to judge by; dependency_cycle reports it
    prerequisites: dict[str, list[str]] = {node.task_key: [] for node in graph.tasks}
    for edge in graph.edges:
        prerequisites[edge.dependent].append(edge.prerequisite)
    order = _Order(prerequisites)
    loc = Locator(ctx.document)
    writers = [
        (task, declared)
        for task in graph.tasks
        if task.task_kind in (TaskKind.UNIT, TaskKind.ITEM)
        for declared in (_declared(ctx, task, loc),)
        if declared
    ]
    for n, (second, theirs) in enumerate(writers):
        for first, mine in writers[:n]:
            hits = [
                (a, b)
                for a, _ in mine
                for b, _ in theirs
                if a.mount == b.mount and globs_overlap(a.pattern, b.pattern)
            ]
            if hits and not order.ordered(first.task_key, second.task_key):
                pointer = next(where for rule, where in theirs if rule == hits[0][1])
                yield first, second, hits, pointer


def write_scope_overlap(ctx: ValidationContext) -> Iterator[Finding]:
    for first, second, hits, pointer in _overlaps(ctx):
        if first.item_key == second.item_key:
            yield _overlap(FindingCode.WRITE_SCOPE_OVERLAP, first, second, hits, pointer)


def write_scope_overlap_cross_item(ctx: ValidationContext) -> Iterator[Finding]:
    for first, second, hits, pointer in _overlaps(ctx):
        if first.item_key != second.item_key:
            yield _overlap(FindingCode.WRITE_SCOPE_OVERLAP_CROSS_ITEM, first, second, hits, pointer)


def _overlap(
    code: FindingCode,
    first: TaskNode,
    second: TaskNode,
    hits: Sequence[tuple[PathRule, PathRule]],
    pointer: str,
) -> Finding:
    paths: list[JsonValue] = [
        *dict.fromkeys(f"{rule.mount}:{rule.pattern}" for pair in hits for rule in pair)
    ]
    return finding(
        code,
        f"{second.task_key} and {first.task_key} may write the same path and nothing orders them",
        key=second.task_key,
        entity_id=second.entity_id,
        pointer=pointer,
        details={"with": first.task_key, "paths": paths},
    )


def write_scope_uncovered(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    items = {item.key: item for item in ctx.spec.items}
    for unit in ctx.spec.units:
        item = items.get(unit.key.split("/", 1)[0])
        if item is None or not item.change_hints:
            continue
        for n, entry in enumerate(unit.write_scope):
            if any(h.mount == entry.mount and covers(entry.pattern, h.pattern) for h in item.change_hints):
                continue
            yield finding(
                FindingCode.WRITE_SCOPE_UNCOVERED,
                f"{entry.mount}:{entry.pattern} of {unit.key} is not covered by a change hint of {item.key}",
                key=unit.key,
                entity_id=unit.id,
                pointer=loc.pointer(unit.key, "write_scope", n, "pattern"),
                details={"path": f"{entry.mount}:{entry.pattern}", "item": item.key},
            )


RULES: Final = (
    forbidden_path_conflict,
    mount_unknown,
    write_scope_empty,
    write_scope_no_tests,
    write_scope_overlap,
    write_scope_overlap_cross_item,
    write_scope_uncovered,
)
