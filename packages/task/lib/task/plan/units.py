"""Work units of an item (dossier §2.5.1, D3): the executor splits an item, hands pieces to other agents, integrates.

A unit is ``phases/<Pn>/<Pn.m>/<U#>.json``; its workspace ``<U#>/`` holds the generated ``brief.json`` and whatever the
worker writes. Lifecycle: ``todo -> dispatched -> returned -> accepted | rejected``; ``rework`` sends a returned unit back
to ``dispatched`` with new notes. Python never starts an agent: ``dispatch`` writes the brief and records the worker.
Every transition logs one ``delegate`` event. Refusals are ``PlanError`` codes and leave every file unchanged.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Iterable, Mapping

from . import check as _check, lifecycle, store, views
from .model import ITEM_ID, PlanError

UNIT_STATUSES = ("todo", "dispatched", "returned", "accepted", "reworked", "rejected")
OPEN = ("dispatched", "returned")
_OWNED = frozenset({"$schema", "id", "item", "status", "outcome", "updated_at"})


# ---------------------------------------------------------------- reading

def unit_ids(plan: store.Plan, item_id: str) -> list[str]:
    """Unit ids of ``item_id`` in the order of ``item.units`` (files not listed there follow, sorted)."""
    declared = [u for u in plan.items[item_id].get("units") or [] if isinstance(u, str)]
    present = {k.split("/")[1] for k in plan.units if k.startswith(f"{item_id}/")}
    return [u for u in declared if u in present] + sorted(present - set(declared))


def _reaches(deps: Mapping[str, Iterable[str]], start: str, goal: str) -> bool:
    stack, seen = list(deps.get(start, ())), set()
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node not in seen:
            seen.add(node)
            stack.extend(deps.get(node, ()))
    return False


def parallel_pairs(plan: store.Plan, item_id: str) -> list[tuple[str, str]]:
    """Pairs of unfinished units with no ``depends_on`` path between them and disjoint ``files`` (parallel-safe)."""
    docs = {u: plan.units[f"{item_id}/{u}"] for u in unit_ids(plan, item_id)}
    deps = {u: dependencies(plan, item_id, u) for u in docs}
    live = [u for u in docs if docs[u].get("status") not in ("accepted", "rejected")]
    pairs = []
    for index, a in enumerate(live):
        for b in live[index + 1:]:
            if _reaches(deps, a, b) or _reaches(deps, b, a):
                continue
            if not any(_check.globs_overlap(x, y) for x in _check._files(docs[a]) for y in _check._files(docs[b])):
                pairs.append((a, b))
    return pairs


# ---------------------------------------------------------------- JSON dispatch contract

def policy(plan: store.Plan, item_id: str) -> dict:
    value = {"strategy": "dag"}
    for doc in (plan.plan, plan.phases.get(item_id.split(".")[0], {}), plan.items[item_id]):
        if isinstance(doc.get("orchestration"), dict):
            value.update(doc["orchestration"])
    return value


def dependencies(plan: store.Plan, item_id: str, unit_id: str) -> list[str]:
    ids = unit_ids(plan, item_id)
    doc = plan.units[f"{item_id}/{unit_id}"]
    authored = doc.get("depends_on")
    deps = [d for d in authored if isinstance(d, str)] if isinstance(authored, list) else []
    deps += [u for u in ids if plan.units[f"{item_id}/{u}"].get("parent") == unit_id]
    if policy(plan, item_id)["strategy"] == "sequential":
        # Containers wait for their children; order only sibling nodes.
        siblings = [u for u in ids if plan.units[f"{item_id}/{u}"].get("parent") == doc.get("parent")]
        position = siblings.index(unit_id)
        if position:
            deps.append(siblings[position - 1])
    return list(dict.fromkeys(deps))


def ready(plan: store.Plan, item_id: str) -> list[dict]:
    """Dispatch candidates only; this function starts no agents and runs no commands."""
    candidates = []
    for u in unit_ids(plan, item_id):
        doc = plan.units[f"{item_id}/{u}"]
        if doc.get("status") not in ("todo", "reworked"):
            continue
        if any(plan.units.get(f"{item_id}/{d}", {}).get("status") != "accepted"
               for d in dependencies(plan, item_id, u)):
            continue
        candidates.append({"ref": f"{item_id}/{u}", "kind": doc.get("kind", "implementation"),
                           "mode": doc.get("mode", "either"), "route": copy.deepcopy(doc.get("route", {})),
                           "files": list(doc.get("files", []))})
    limit = policy(plan, item_id).get("max_parallel")
    running = sum(plan.units[f"{item_id}/{u}"].get("status") == "dispatched" for u in unit_ids(plan, item_id))
    return candidates[:max(0, limit - running)] if limit is not None else candidates


def brief_path(root: Path, item_id: str, unit_id: str) -> Path:
    return store.unit_path(root, item_id, unit_id).with_suffix("") / "brief.json"


def brief(plan: store.Plan, item_id: str, unit_id: str, *, rework: bool = False) -> dict:
    from . import context
    unit = _need_unit(plan, item_id, unit_id)
    item = plan.items[item_id]
    by_id = {c["id"]: c for c in item.get("validation", [])}
    identity = plan.plan.get("short_id") or plan.plan["id"]
    return {"ref": f"{identity}.{item_id}/{unit_id}", "unit": copy.deepcopy(unit),
            "context": context.collect(plan, item_id),
            "reads": [context.read_entry(plan, r) for r in unit.get("reads", [])],
            "checks": [copy.deepcopy(by_id[c] if isinstance(c, str) else c) for c in unit.get("checks", [])],
            "rework": (unit.get("outcome") or {}).get("notes", "") if rework else "",
            "report_api": {"verb": "unit return", "item": item_id, "unit": unit_id}}


def brief_text(plan: store.Plan, item_id: str, unit_id: str, *, rework: bool = False) -> str:
    return json.dumps(brief(plan, item_id, unit_id, rework=rework), ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------- mutations

def _need_item(p: store.Plan, item_id: str) -> dict:
    if not ITEM_ID.fullmatch(item_id or "") or item_id not in p.items:
        raise PlanError("REF_UNKNOWN", f"unknown item {item_id!r}")
    return p.items[item_id]


def _need_unit(p: store.Plan, item_id: str, unit_id: str) -> dict:
    _need_item(p, item_id)
    key = f"{item_id}/{unit_id}"
    if key not in p.units:
        raise PlanError("REF_UNKNOWN", f"unknown unit {key!r}")
    return p.units[key]


def _next_id(p: store.Plan, item_id: str) -> str:
    numbers = [int(u[1:]) for u in unit_ids(p, item_id)]
    return f"U{max(numbers, default=0) + 1}"


def _agent(text: str | Mapping) -> dict:
    if isinstance(text, Mapping):
        agent = {k: v for k, v in dict(text).items() if v}
    else:
        parts = str(text or "").split("/")
        if len(parts) not in (2, 3) or not all(parts):
            raise PlanError("AGENT_REQUIRED", "--agent PROVIDER/MODEL[/EFFORT] names the worker")
        agent = {"provider": parts[0], "model": parts[1], **({"effort": parts[2]} if len(parts) == 3 else {})}
    if not agent.get("provider") or not agent.get("model"):
        raise PlanError("AGENT_REQUIRED", "--agent PROVIDER/MODEL[/EFFORT] names the worker")
    return agent


def _delegate(p: store.Plan, item_id: str, unit_id: str, status: str, doc: dict, actor: dict, **extra) -> dict:
    agent = (doc.get("outcome") or {}).get("agent") or actor
    klass = lifecycle.admitted_class(agent["provider"], agent["model"]) or "unknown"
    data = {"unit": unit_id, "class": klass, "model": agent["model"], "status": status,
            **{k: v for k, v in extra.items() if v is not None}}
    return store.new_event("delegate", f"{item_id}/{unit_id} {status}", actor, item=item_id,
                           phase=item_id.split(".", 1)[0], data=data)


def _write_brief(p: store.Plan, item_id: str, unit_id: str, *, rework: bool = False) -> None:
    store.atomic_write(brief_path(p.root, item_id, unit_id), brief_text(p, item_id, unit_id, rework=rework))


def add_unit(plan, item_id: str, title: str, data: dict | None = None) -> str:
    """Add the next ``U#`` to ``item_id`` (creating its workspace); ``data`` supplies files, goal, route, mode, …"""
    extra = dict(data or {})
    owned = sorted(set(extra) & _OWNED)
    if owned:
        raise PlanError("FIELD_OWNED", f"{', '.join(owned)} of a unit is identity or lifecycle-owned")
    with lifecycle._mutation(plan) as (p, lock):
        item = _need_item(p, item_id)
        unit_id = _next_id(p, item_id)
        doc = {"$schema": "urn:swissknifeman:task:plan:unit:v1", "id": unit_id, "item": item_id, "title": title,
               "goal": title, "route": copy.deepcopy(item.get("route") or {"class": "implementation", "effort": "high"}),
               "mode": "either", "status": "todo", "outcome": None, "updated_at": store.now()}
        doc.update(copy.deepcopy(extra))
        doc["title"] = title
        item_doc = copy.deepcopy(item)
        item_doc["units"] = [*unit_ids(p, item_id), unit_id]
        probe = copy.deepcopy(p)
        probe.units[f"{item_id}/{unit_id}"] = doc
        probe.items[item_id] = item_doc
        unit_file = f"phases/{item_id.split('.', 1)[0]}/{item_id}/"
        errors = [i for i in _check.check(probe)
                  if i.level == "error" and (i.where.startswith((unit_file, f"{item_id}/")) or i.code == "units_list")
                  and (unit_id in i.where or unit_id in i.message)]
        if errors:
            raise PlanError("UNIT_INVALID", "; ".join(f"{i.where}: {i.message}" for i in errors[:3]))
        lifecycle._commit(p, [("unit", f"{item_id}/{unit_id}", doc), ("item", item_id, item_doc)], [], lock)
        return unit_id


def dispatch(plan, item_id: str, unit_id: str, agent, *, actor: Mapping | None = None) -> Path:
    """Record ``agent`` as the worker, write ``<U#>/brief.json`` and return its path. Python starts nobody."""
    with lifecycle._mutation(plan) as (p, lock):
        unit = copy.deepcopy(_need_unit(p, item_id, unit_id))
        if lifecycle.status_of(p, item_id) != "in_progress":
            raise PlanError("ITEM_NOT_IN_PROGRESS", f"{item_id} is {lifecycle.status_of(p, item_id)}; start it first")
        if unit.get("mode") == "self" and _agent(agent) != lifecycle._actor_doc(p, actor, item_id):
            raise PlanError("UNIT_SELF", f"{item_id}/{unit_id} requires the item executor")
        if unit.get("status") not in ("todo", "reworked"):
            raise PlanError("UNIT_STATE", f"{item_id}/{unit_id} is {unit.get('status')}; dispatch needs todo")
        waiting = [d for d in dependencies(p, item_id, unit_id)
                   if p.units.get(f"{item_id}/{d}", {}).get("status") != "accepted"]
        if waiting:
            raise PlanError("UNIT_DEPENDENCY", f"{item_id}/{unit_id} waits for accepted {', '.join(waiting)}")
        worker = _agent(agent)
        need = unit.get("route") or {}
        lifecycle.validate_route(need, worker, f"{item_id}/{unit_id}")
        policy_limit = policy(p, item_id).get("max_parallel")
        if policy_limit is not None and sum(d.get("status") == "dispatched" for k, d in p.units.items()
                                            if k.startswith(f"{item_id}/")) >= policy_limit:
            raise PlanError("PARALLEL_LIMIT", "all configured dispatch slots are occupied")
        admitted = lifecycle.admitted_class(worker["provider"], worker["model"])
        if admitted is not None and lifecycle._rank(lifecycle.CLASS_ORDER, admitted) < lifecycle._rank(
                lifecycle.CLASS_ORDER, need.get("class")):
            raise PlanError("ROUTE_UNDERSHOOT", f"{item_id}/{unit_id} needs class {need.get('class')}; "
                                                f"{worker['provider']}/{worker['model']} is admitted as {admitted}")
        if worker.get("effort") and lifecycle._rank(lifecycle.EFFORT_ORDER, worker["effort"]) < lifecycle._rank(
                lifecycle.EFFORT_ORDER, need.get("effort")):
            raise PlanError("ROUTE_UNDERSHOOT", f"{item_id}/{unit_id} needs effort {need.get('effort')}; "
                                                f"worker runs {worker['effort']}")
        unit["status"], unit["outcome"] = "dispatched", {"agent": worker, "at": store.now()}
        executor = lifecycle._actor_doc(p, actor, item_id)
        event = _delegate(p, item_id, unit_id, "dispatched", unit, executor)
        lifecycle._commit(p, [("unit", f"{item_id}/{unit_id}", unit)], [event], lock)
        _write_brief(p, item_id, unit_id)
        return brief_path(p.root, item_id, unit_id)


def _transition(plan, item_id: str, unit_id: str, status: str, allowed: tuple[str, ...], *, notes: str = "",
                changed: Iterable[str] = (), minutes: int | None = None, need_notes: bool = False,
                actor: Mapping | None = None, back_to: str | None = None) -> None:
    """Move a unit to ``status`` (stored as ``back_to`` when set: a rework goes straight back to ``dispatched``)."""
    with lifecycle._mutation(plan) as (p, lock):
        unit = copy.deepcopy(_need_unit(p, item_id, unit_id))
        if unit.get("status") not in allowed:
            raise PlanError("UNIT_STATE", f"{item_id}/{unit_id} is {unit.get('status')}; "
                                          f"{status} needs {' or '.join(allowed)}")
        if need_notes and not (notes or "").strip():
            raise PlanError("NOTES_REQUIRED", f"{status} needs --notes")
        if minutes is not None and (isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 0):
            raise PlanError("MINUTES_INVALID", "--minutes is a non-negative integer")
        executor = lifecycle._actor_doc(p, actor, item_id)
        outcome = dict(unit.get("outcome") or {})
        outcome.setdefault("agent", executor)
        outcome["at"] = store.now()
        if status == "returned":  # a fresh report replaces the notes of an earlier round
            outcome.pop("notes", None)
            outcome.pop("changed", None)
        if notes:
            outcome["notes"] = notes
        if changed:
            outcome["changed"] = list(changed)
        if minutes is not None:
            outcome["minutes"] = minutes
        round_no = None
        if status == "reworked":
            round_no = 1 + sum(1 for _, e, _ in store.log_lines(p.root)
                             if e and e.get("type") == "delegate" and e.get("item") == item_id
                             and (e.get("data") or {}).get("unit") == unit_id
                             and (e.get("data") or {}).get("status") == "reworked")
        unit["status"], unit["outcome"] = back_to or status, outcome
        event = _delegate(p, item_id, unit_id, status, unit, outcome["agent"] if status == "returned" else executor,
                          minutes=minutes, rework=round_no)
        lifecycle._commit(p, [("unit", f"{item_id}/{unit_id}", unit)], [event], lock)
        if status == "reworked":
            _write_brief(p, item_id, unit_id, rework=True)


def return_unit(plan, item_id: str, unit_id: str, *, notes: str = "", changed: Iterable[str] = (),
                minutes: int | None = None, actor: Mapping | None = None) -> None:
    """The worker reports: ``dispatched -> returned``."""
    _transition(plan, item_id, unit_id, "returned", ("dispatched",), notes=notes, changed=changed, minutes=minutes,
                actor=actor)


def accept(plan, item_id: str, unit_id: str, *, notes: str = "", minutes: int | None = None,
           actor: Mapping | None = None) -> None:
    """The executor reviewed and tested the piece: ``returned -> accepted``."""
    _transition(plan, item_id, unit_id, "accepted", ("returned",), notes=notes, minutes=minutes, actor=actor)


def rework(plan, item_id: str, unit_id: str, *, notes: str, actor: Mapping | None = None) -> None:
    """The executor sends the piece back: ``returned -> dispatched`` with ``notes``; the brief is rewritten."""
    _transition(plan, item_id, unit_id, "reworked", ("returned",), notes=notes, need_notes=True, actor=actor,
                back_to="dispatched")


def reject(plan, item_id: str, unit_id: str, *, notes: str, actor: Mapping | None = None) -> None:
    """The executor drops the piece (and does it itself or skips it): ``dispatched|returned -> rejected``."""
    _transition(plan, item_id, unit_id, "rejected", ("dispatched", "returned"), notes=notes, need_notes=True,
                actor=actor)
