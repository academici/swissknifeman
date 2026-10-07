"""Parallel-lane primitives: item footprint, pair conflict and the wait graph (read-only, stdlib-only).

A footprint is the product paths an item may write; ``None`` means unknown and conflicts with everything.
The wait graph says which item has to finish before another can start; it feeds ``check`` (deadlocks).
"""
from __future__ import annotations

from collections import deque
from typing import NamedTuple

from . import check as _check
from . import lifecycle, store
from .model import id_sort_key

ITEM_EDGE = "item"


class Conflict(NamedTuple):
    reason: str  # footprint_unknown | task_files_overlap
    pairs: list[tuple[str, str]]  # overlapping (path of a, path of b); empty for footprint_unknown


def footprint(plan: store.Plan, item_id: str) -> list[str] | None:
    """Declared ``task_files`` paths of ``item_id`` in declaration order; None when none are declared."""
    hints = plan.items[item_id].get("task_files")
    paths: list[str] = []
    for hint in hints if isinstance(hints, list) else []:
        path = hint.get("path") if isinstance(hint, dict) else None
        if isinstance(path, str) and path not in paths:
            paths.append(path)
    return paths or None


def conflict(fa: list[str] | None, fb: list[str] | None) -> Conflict | None:
    """Why two footprints cannot be written in parallel; None when they are provably disjoint."""
    if fa is None or fb is None:
        return Conflict("footprint_unknown", [])
    pairs = [(x, y) for x in fa for y in fb if _check.globs_overlap(_bare(x), _bare(y))]
    return Conflict("task_files_overlap", pairs) if pairs else None


def _bare(path: str) -> str:
    """``lib/x/`` and ``./lib/x`` name the directory ``lib/x``; ``globs_overlap`` compares segments literally."""
    while path.startswith("./"):
        path = path[2:]
    return path.rstrip("/") or path


def wait_edges(plan: store.Plan) -> dict[tuple[str, str], set[str]]:
    """``(item, awaited item) -> kinds``: ``item`` for ``depends_on``, ``phase:<Pn>`` for a phase dependency."""
    edges: dict[tuple[str, str], set[str]] = {}
    for phase_id in lifecycle.phase_order(plan):
        deps = lifecycle._phase_deps(plan, phase_id)
        for item_id in lifecycle.phase_items(plan, phase_id):
            declared = plan.items[item_id].get("depends_on")
            for dep in declared if isinstance(declared, list) else []:
                if dep in plan.items:
                    edges.setdefault((item_id, dep), set()).add(ITEM_EDGE)
            for dep_phase in deps:
                for awaited in lifecycle.phase_items(plan, dep_phase):
                    edges.setdefault((item_id, awaited), set()).add(f"phase:{dep_phase}")
    return edges


def wait_graph(plan: store.Plan) -> dict[str, set[str]]:
    """For every item, the items it waits for (explicit dependencies and every item of a dependency phase)."""
    graph: dict[str, set[str]] = {item_id: set() for item_id in plan.items}
    for (item_id, awaited) in wait_edges(plan):
        graph[item_id].add(awaited)
    return graph


class Deadlock(NamedTuple):
    items: list[str]  # cycle vertices, starting with the smallest id; the last waits for the first
    kinds: list[str]  # kind of the edge leaving each vertex: ``item`` or ``phase:<Pn>``

    def render(self) -> str:
        parts = []
        for item_id, kind in zip(self.items, self.kinds):
            parts.append(item_id)
            if kind != ITEM_EDGE:
                parts.append(f"(phase {kind.split(':', 1)[1]})")
        return " -> ".join([*parts, self.items[0]])


def deadlocks(plan: store.Plan) -> list[Deadlock]:
    """Wait cycles that mix item dependencies with phase dependencies.

    Pure item cycles and pure phase cycles are reported by ``check.cycles`` and not repeated here. The search is
    exhaustive over phase-only edges: each one is closed into a cycle through at least one item dependency.
    """
    edges = wait_edges(plan)
    out: dict[str, list[tuple[str, str]]] = {}
    for (src, dst) in sorted(edges, key=lambda e: (id_sort_key(e[0]), id_sort_key(e[1]))):
        out.setdefault(src, []).append((dst, ITEM_EDGE if ITEM_EDGE in edges[(src, dst)] else min(edges[(src, dst)])))
    found: dict[frozenset, Deadlock] = {}
    for (src, dst), kinds in sorted(edges.items(), key=lambda e: (id_sort_key(e[0][0]), id_sort_key(e[0][1]))):
        if ITEM_EDGE in kinds or src == dst:
            continue
        path = _path_with_item_edge(out, dst, src)
        if path is None:
            continue
        cycle = [(src, min(kinds)), *path]
        names = [vertex for vertex, _ in cycle]
        key = frozenset(names)
        if key not in found:
            start = min(range(len(names)), key=lambda i: id_sort_key(names[i]))
            rotated = cycle[start:] + cycle[:start]
            found[key] = Deadlock([v for v, _ in rotated], [k for _, k in rotated])
    minimal = [d for key, d in found.items() if not any(other < key for other in found)]  # drop composite cycles
    return sorted(minimal, key=lambda d: [id_sort_key(i) for i in d.items])


def _path_with_item_edge(out: dict[str, list[tuple[str, str]]], start: str, goal: str) -> list[tuple[str, str]] | None:
    """Shortest ``start -> goal`` walk using at least one item edge, as ``[(vertex, kind of edge leaving it)]``.

    The walk includes ``start`` and ends at the vertex whose edge reaches ``goal``'s successor; the caller
    prepends the closing edge. Breadth-first over ``(vertex, used an item edge)`` keeps the result deterministic.
    """
    begin = (start, False)
    parent: dict[tuple[str, bool], tuple[tuple[str, bool], str] | None] = {begin: None}
    queue = deque([begin])
    while queue:
        state = queue.popleft()
        vertex, used = state
        if vertex == goal and used:
            walk: list[tuple[str, str]] = []
            while parent[state] is not None:
                previous, kind = parent[state]
                walk.append((previous[0], kind))
                state = previous
            walk.reverse()
            return walk
        for nxt, kind in out.get(vertex, ()):
            following = (nxt, used or kind == ITEM_EDGE)
            if following not in parent:
                parent[following] = (state, kind)
                queue.append(following)
    return None
