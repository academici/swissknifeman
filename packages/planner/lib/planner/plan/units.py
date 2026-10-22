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

from . import check as _check, lifecycle, settings, store
from .model import ITEM_ID, PlanError, id_sort_key

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
            "rework": (unit.get("outcome") or {}).get("notes", "") if rework else ""}


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


def _check_worker(plan: store.Plan, need: Mapping, worker: Mapping, target: str) -> str:
    """Validate the unit route and pool policy; return ``ok`` or ``ROUTE_MODEL_UNKNOWN`` in warn mode."""
    lifecycle.validate_route(dict(need), worker, target)
    admitted = lifecycle.admitted_class(worker["provider"], worker["model"])
    if admitted is None and settings.refuse_unknown_model(plan):
        raise PlanError("ROUTE_MODEL_UNKNOWN", f"{worker['provider']}/{worker['model']} is not in the model pool")
    if admitted is not None and lifecycle._rank(lifecycle.CLASS_ORDER, admitted) < lifecycle._rank(
            lifecycle.CLASS_ORDER, need.get("class")):
        raise PlanError("ROUTE_UNDERSHOOT", f"{target} needs class {need.get('class')}; "
                                            f"{worker['provider']}/{worker['model']} is admitted as {admitted}")
    if worker.get("effort") and lifecycle._rank(lifecycle.EFFORT_ORDER, worker["effort"]) < lifecycle._rank(
            lifecycle.EFFORT_ORDER, need.get("effort")):
        raise PlanError("ROUTE_UNDERSHOOT", f"{target} needs effort {need.get('effort')}; "
                                            f"worker runs {worker['effort']}")
    return "ok" if admitted is not None else "ROUTE_MODEL_UNKNOWN"


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
        verdict = _check_worker(p, need, worker, f"{item_id}/{unit_id}")
        unit["status"], unit["outcome"] = "dispatched", {"agent": worker, "at": store.now()}
        executor = lifecycle._actor_doc(p, actor, item_id)
        event = _delegate(p, item_id, unit_id, "dispatched", unit, executor,
                          route=verdict if verdict != "ok" else None)
        lifecycle._commit(p, [("unit", f"{item_id}/{unit_id}", unit)], [event], lock)
        _write_brief(p, item_id, unit_id)
        return brief_path(p.root, item_id, unit_id)


def _attempt_seen(p: store.Plan, item_id: str, unit_id: str, attempt_id: str) -> str | None:
    """Status the ``delegate`` event of ``attempt_id`` registered for the unit, or None (latest wins)."""
    seen = None
    for _, event, _ in store.log_lines(p.root):
        if (event and event.get("type") == "delegate" and event.get("item") == item_id
                and event.get("attempt_id") == attempt_id and (event.get("data") or {}).get("unit") == unit_id):
            seen = (event.get("data") or {}).get("status")
    return seen


def _outcome_differs(outcome: Mapping, status: str, attempt_id: str, notes: str, changed: Iterable[str],
                     evidence: Iterable[str] = ()) -> bool:
    """Whether a repeat of the latest transition reports other notes, paths or evidence than the outcome."""
    if outcome.get("attempt_id") != attempt_id:
        return False  # later transitions replaced the outcome; the logged status is all that is left to compare
    changed, evidence = list(changed), list(evidence)
    if outcome.get("evidence", []) != evidence:  # evidence belongs to this transition only, so absence must match
        return True
    if status == "returned":  # a return replaces both fields, so absence must match too
        return outcome.get("notes", "") != (notes or "") or outcome.get("changed", []) != changed
    return bool(notes and outcome.get("notes") != notes or changed and outcome.get("changed") != changed)


def _unit_check_ids(p: store.Plan, item_id: str, unit: Mapping) -> set[str]:
    """Check ids a unit may prove: the item's validation and the unit's own checks."""
    known = {c["id"] for c in p.items[item_id].get("validation", []) if isinstance(c, dict) and "id" in c}
    known |= {c if isinstance(c, str) else c.get("id") for c in unit.get("checks", [])
              if isinstance(c, str) or isinstance(c, dict)}
    return known


def _transition(plan, item_id: str, unit_id: str, status: str, allowed: tuple[str, ...], *, notes: str = "",
                changed: Iterable[str] = (), minutes: int | None = None, need_notes: bool = False,
                actor: Mapping | None = None, back_to: str | None = None, executed_by: Mapping | None = None,
                attempt_id: str | None = None, evidence: Mapping[str, str] | None = None) -> bool:
    """Move a unit to ``status`` (stored as ``back_to`` when set: a rework goes straight back to ``dispatched``).

    True when ``attempt_id`` already registered this transition and nothing was written. The attempt is looked
    up in the log, so a repeat stays a no-op after later transitions; while it is still the latest transition its
    notes, changed paths and evidence must match too, else ``ATTEMPT_CONFLICT``.

    ``evidence`` (``V#`` -> check-evidence file of ``<item>/<U#>``) lands in ``outcome.evidence``; a failing one is
    ``CHECKS_RED``. Unit checks are never recorded as exits.
    """
    evidence = dict(evidence or {})
    registrar = lifecycle._given_actor(actor)
    executed_by = lifecycle._given_actor(executed_by)
    attempt_id = lifecycle.need_attempt(attempt_id)
    with lifecycle._mutation(plan) as (p, lock):
        unit = copy.deepcopy(_need_unit(p, item_id, unit_id))
        proven = lifecycle.load_evidence(p, f"{item_id}/{unit_id}", evidence, _unit_check_ids(p, item_id, unit))
        paths = list(dict.fromkeys(evidence[i] for i in sorted(evidence, key=id_sort_key)))
        if attempt_id is not None:
            seen = _attempt_seen(p, item_id, unit_id, attempt_id)
            if seen is not None:
                if seen != status or _outcome_differs(unit.get("outcome") or {}, status, attempt_id, notes, changed,
                                                      paths):
                    raise PlanError("ATTEMPT_CONFLICT", f"attempt {attempt_id} already registered "
                                                        f"{item_id}/{unit_id} {seen} with other outcome")
                return True
        if unit.get("status") not in allowed:
            raise PlanError("UNIT_STATE", f"{item_id}/{unit_id} is {unit.get('status')}; "
                                          f"{status} needs {' or '.join(allowed)}")
        if need_notes and not (notes or "").strip():
            raise PlanError("NOTES_REQUIRED", f"{status} needs --notes")
        if minutes is not None and (isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 0):
            raise PlanError("MINUTES_INVALID", "--minutes is a non-negative integer")
        red = [f"{i}={code}" for i, code in sorted(proven.items(), key=lambda kv: id_sort_key(kv[0])) if code != 0]
        if red:
            raise PlanError("CHECKS_RED", f"{item_id}/{unit_id} evidence shows failed check(s): {', '.join(red)}")
        executor = lifecycle._actor_doc(p, actor, item_id)
        outcome = dict(unit.get("outcome") or {})
        outcome.setdefault("agent", executor)
        if executed_by is not None and not (executed_by["provider"] == outcome["agent"].get("provider")
                                            and executed_by["model"] == outcome["agent"].get("model")):
            _check_worker(p, unit.get("route") or {}, executed_by, f"{item_id}/{unit_id}")
        outcome["at"] = store.now()
        for key in ("registered_by", "attempt_id", "evidence"):  # they describe one transition only
            outcome.pop(key, None)
        if status == "returned":  # a fresh report replaces the notes of an earlier round
            outcome.pop("notes", None)
            outcome.pop("changed", None)
        if notes:
            outcome["notes"] = notes
        if changed:
            outcome["changed"] = list(changed)
        if minutes is not None:
            outcome["minutes"] = minutes
        if paths:
            outcome["evidence"] = paths
        round_no = None
        if status == "reworked":
            round_no = 1 + sum(1 for _, e, _ in store.log_lines(p.root)
                             if e and e.get("type") == "delegate" and e.get("item") == item_id
                             and (e.get("data") or {}).get("unit") == unit_id
                             and (e.get("data") or {}).get("status") == "reworked")
        acting = outcome["agent"] if status == "returned" else executor
        attribution = {}
        if executed_by is not None:
            attribution["executed_by"] = executed_by
        if registrar is not None and not lifecycle.same_actor(registrar, acting):
            attribution["registered_by"] = registrar
        if attempt_id is not None:
            attribution["attempt_id"] = attempt_id
        outcome.update({k: v for k, v in attribution.items() if k != "executed_by"})
        unit["status"], unit["outcome"] = back_to or status, outcome
        event = _delegate(p, item_id, unit_id, status, unit, acting, minutes=minutes, rework=round_no)
        event.update(attribution)
        lifecycle._commit(p, [("unit", f"{item_id}/{unit_id}", unit)], [event], lock)
        if status == "reworked":
            _write_brief(p, item_id, unit_id, rework=True)
        return False


def return_unit(plan, item_id: str, unit_id: str, *, notes: str = "", changed: Iterable[str] = (),
                minutes: int | None = None, actor: Mapping | None = None, executed_by: Mapping | None = None,
                attempt_id: str | None = None) -> bool:
    """The worker reports: ``dispatched -> returned``; True when ``attempt_id`` was already registered."""
    return _transition(plan, item_id, unit_id, "returned", ("dispatched",), notes=notes, changed=changed,
                       minutes=minutes, actor=actor, executed_by=executed_by, attempt_id=attempt_id)


def accept(plan, item_id: str, unit_id: str, *, notes: str = "", minutes: int | None = None,
           actor: Mapping | None = None, attempt_id: str | None = None,
           evidence: Mapping[str, str] | None = None) -> bool:
    """The executor reviewed and tested the piece: ``returned -> accepted``; True when already registered.

    ``evidence`` maps ``V#`` to check-evidence files of the unit; their paths land in ``outcome.evidence``.
    """
    return _transition(plan, item_id, unit_id, "accepted", ("returned",), notes=notes, minutes=minutes, actor=actor,
                       attempt_id=attempt_id, evidence=evidence)


def rework(plan, item_id: str, unit_id: str, *, notes: str, actor: Mapping | None = None) -> None:
    """The executor sends the piece back: ``returned -> dispatched`` with ``notes``; the brief is rewritten."""
    _transition(plan, item_id, unit_id, "reworked", ("returned",), notes=notes, need_notes=True, actor=actor,
                back_to="dispatched")


def reject(plan, item_id: str, unit_id: str, *, notes: str, actor: Mapping | None = None) -> None:
    """The executor drops the piece (and does it itself or skips it): ``dispatched|returned -> rejected``."""
    _transition(plan, item_id, unit_id, "rejected", ("dispatched", "returned"), notes=notes, need_notes=True,
                actor=actor)
