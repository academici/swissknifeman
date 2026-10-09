"""Parallel-lane primitives: item footprint, pair conflict and the wait graph (read-only, stdlib-only).

A footprint is the product paths an item may write; ``None`` means unknown and conflicts with everything.
The wait graph says which item has to finish before another can start; it feeds ``check`` (deadlocks).
``ready_set`` names the lanes that can run side by side across the whole plan.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import NamedTuple

from .. import COMMAND_NAMESPACE
from . import check as _check
from . import lifecycle, store
from .model import TERMINAL, PlanError, id_sort_key

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


@dataclass(frozen=True)
class ReadySet:
    """Lanes that can start together, plus everything that explains why other work is not among them."""

    plan: str
    limit: int
    lanes: list[dict] = field(default_factory=list)
    running: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    waiting: list[dict] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    next: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"plan": self.plan, "limit": self.limit, "lanes": self.lanes, "running": self.running,
                "conflicts": self.conflicts, "waiting": self.waiting, "deferred": self.deferred, "next": self.next}

    def render(self) -> str:
        lines = [f"{lane['lane']} {lane['kind']}: {lane['command']}"
                 + (f"  ({lane['route']['class']}/{lane['route']['effort']})" if lane["route"] else "")
                 for lane in self.lanes] or ["no ready lanes"]
        lines += [f"running {row['item']}" for row in self.running]
        for row in self.conflicts:
            lines.append(f"conflict {row['item']} ~ {row['with']}: "
                         + (" / ".join(row["paths"][0]) if row["paths"] else "footprint unknown"))
        for row in self.waiting:
            subject = row["item"] or row["phase"]
            lines.append(f"waiting {subject}: {row['reason']}" if subject else f"waiting: {row['reason']}")
        lines += [f"deferred {entry}" for entry in self.deferred]
        return "\n".join(lines)


def ready_set(plan: store.Plan, limit: int, *, granted: set[str] | None = None) -> ReadySet:
    """Lanes of the whole plan that are safe to run in parallel (read-only: no events, no files, no lock).

    ``limit`` is the requested number of simultaneous lanes, capped by ``orchestration.max_parallel`` of the plan;
    running items occupy slots and their footprints. Order follows the plan: phases, batches, items.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise PlanError("LIMIT_INVALID", "--parallel must be an integer >= 1")
    ceiling = _orchestration(plan.plan).get("max_parallel")
    if isinstance(ceiling, int) and not isinstance(ceiling, bool) and ceiling >= 1:
        limit = min(limit, ceiling)
    plan_id = plan.plan.get("id", plan.root.name)
    granted = lifecycle.granted_gates(plan) if granted is None else granted
    following = lifecycle.next(plan, granted=granted).as_dict()
    if plan.plan.get("status") == "paused":
        pause = plan.plan.get("pause") if isinstance(plan.plan.get("pause"), dict) else {}
        reason = f"paused: {pause.get('reason', 'source pause reason missing')}"
        return ReadySet(plan_id, limit, waiting=[{"phase": None, "item": None, "reason": reason}], next=following)

    order = lifecycle.phase_order(plan)
    running = [(phase_id, item_id) for phase_id in order for item_id in lifecycle.phase_items(plan, phase_id)
               if lifecycle.status_of(plan, item_id) == "in_progress"]
    taken: list[tuple[str, list[str] | None]] = [(item_id, footprint(plan, item_id)) for _, item_id in running]
    waiting: list[dict] = []
    candidates: list[dict] = []
    for phase_id in order:
        phase = plan.phases[phase_id]
        if phase.get("closed"):
            continue
        _collect_phase(plan, plan_id, phase_id, phase, granted, [i for p, i in running if p == phase_id],
                       candidates, waiting)

    lanes: list[dict] = []
    conflicts: list[dict] = []
    deferred: list[str] = []
    slots = max(limit - len(running), 0)
    for candidate in candidates:
        if candidate["kind"] == "run-items":
            found = _lane_conflict(plan, candidate["items"], taken)
            if found is not None:
                conflicts.append(found)
                continue
        if slots <= 0:
            deferred.extend(candidate["items"] if candidate["kind"] == "run-items" else [candidate["phase"]])
            continue
        slots -= 1
        lanes.append({"lane": f"L{len(lanes) + 1}", **candidate})
        if candidate["kind"] == "run-items":
            taken.extend((item_id, footprint(plan, item_id)) for item_id in candidate["items"])
    return ReadySet(plan_id, limit, lanes, [{"item": i, "phase": p} for p, i in running], conflicts, waiting,
                    deferred, following)


def _launch(command: str) -> dict:
    return {"claude": f"/{command}", "codex": f"$ {command}"}


def _lane(plan_id: str, phase_id: str, batch: str | None, items: list[str], route: dict | None) -> dict:
    command = f"{COMMAND_NAMESPACE}:plan-run {plan_id} {' '.join(items)}"
    return {"kind": "run-items", "phase": phase_id, "batch": batch, "items": items, "route": route,
            "command": command, "launch": _launch(command)}


def _collect_phase(plan, plan_id, phase_id, phase, granted, running_here, candidates, waiting) -> None:
    """Append the candidate lanes of one open phase, or the reason it contributes none."""
    for dep in lifecycle._phase_deps(plan, phase_id):
        closed = plan.phases[dep].get("closed")
        if not closed:
            waiting.append({"phase": phase_id, "item": None, "reason": dep})
            return
        if closed.get("result") == "blocked":
            waiting.append({"phase": phase_id, "item": None, "reason": f"phase {dep} is closed as blocked"})
            return
    if phase.get("design") != "detailed":
        command = f"{COMMAND_NAMESPACE}:plan-design {plan_id} {phase_id}"
        candidates.append({"kind": "design-phase", "phase": phase_id, "batch": None, "items": [], "route": None,
                           "command": command, "launch": _launch(command)})
        return
    members = lifecycle.phase_items(plan, phase_id)
    if all(lifecycle.status_of(plan, i) in TERMINAL for i in members):
        waiting.append({"phase": phase_id, "item": None, "reason": f"{phase_id} closure: plan.py reconcile {plan_id}"})
        return
    strategy = {**_orchestration(plan.plan), **_orchestration(phase)}.get("strategy", "dag")
    if strategy == "sequential" and running_here:
        waiting.append({"phase": phase_id, "item": None, "reason": f"{phase_id} is sequential; running {running_here[0]}"})
        return
    for batch in lifecycle.batches_of(plan, phase_id):
        pending = [i for i in lifecycle.batch_members(plan, phase_id, batch) if lifecycle.status_of(plan, i) not in TERMINAL]
        if not pending:
            continue
        batch_id = batch.get("id")
        todo = [i for i in pending if lifecycle.status_of(plan, i) == "todo"]
        if not todo:
            waiting.append({"phase": phase_id, "item": None, "reason": f"batch {batch_id} running"})
            return
        if batch.get("mode") == "required":
            ready, reason = lifecycle.ready_members(plan, phase_id, batch, granted)
            if not ready:
                waiting.append({"phase": phase_id, "item": None, "reason": reason or f"batch {batch_id}"})
                return
            candidates.append(_lane(plan_id, phase_id, batch_id, [i for i in ready if i in todo],
                                    lifecycle.route_of(plan, ready)))
            return
        first = len(candidates)
        for item_id in todo:
            why = lifecycle._unmet_dependency(plan, item_id, ()) or lifecycle._gate_wait(plan, item_id, granted)
            if why is not None:
                waiting.append({"phase": phase_id, "item": item_id, "reason": why})
            else:
                candidates.append(_lane(plan_id, phase_id, batch_id, [item_id], lifecycle.route_of(plan, [item_id])))
        if strategy == "sequential":  # one item at a time inside a sequential phase
            for extra in candidates[first + 1:]:
                waiting.append({"phase": phase_id, "item": extra["items"][0],
                                "reason": f"{phase_id} is sequential; {candidates[first]['items'][0]} first"})
            del candidates[first + 1:]
        return


def _orchestration(doc: dict) -> dict:
    value = doc.get("orchestration")
    return value if isinstance(value, dict) else {}


def _lane_conflict(plan: store.Plan, items: list[str], taken: list[tuple[str, list[str] | None]]) -> dict | None:
    """First clash of any item of a lane with the footprints already taken; None when the lane is free."""
    for item_id in items:
        mine = footprint(plan, item_id)
        for other, theirs in taken:
            found = conflict(mine, theirs)
            if found is not None:
                return {"item": item_id, "with": other, "reason": found.reason, "paths": [list(p) for p in found.pairs]}
    return None
