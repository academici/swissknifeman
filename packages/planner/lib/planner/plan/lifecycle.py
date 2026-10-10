"""Lifecycle of a v4 plan: semantic Next and the verbs that move items, phases and the plan (dossier §6).

``next`` is a pure function of a ``Plan`` snapshot (gate grants come from the caller or the log). Every verb
refuses before it writes: all checks run inside the plan lock on a fresh snapshot, then item, phase, plan
documents and log events are saved together and the views are regenerated. A refusal is a ``PlanError`` with
a stable code; it appends no event and leaves every file byte-identical. Lifecycle-owned fields (``status``,
``result``, ``phase.closed``, ``phase.design``, ``plan.status``) are written only here.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
from typing import Any, Iterable, Iterator, Mapping

from planner import COMMAND_NAMESPACE
from planner.command_catalog import load_routing_metadata
from planner.integration import events as emission

from . import settings, store
from .model import (CLASS_ORDER, EFFORT_ORDER, ITEM_ID, PHASE_ID, SATISFYING, TERMINAL, ItemStatus, PlanError,
                    id_sort_key, parse_ref, phase_status)

ROUTING_PATH = Path(__file__).resolve().parents[3] / "configs" / "command-routing.json"
FRICTION_TYPES = ("deviation", "blocker", "difficulty", "assumption", "note")
FINISH_STATUSES = ("done", "done_with_deviations", "blocked", "skipped")
_OPTION_ID = re.compile(r"^[A-Z]$")
_GATE = re.compile(r"^[A-Z0-9-]+$")
ATTEMPT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)  # schemas/plan/v1 defs.attemptId
_CHECK_ID = re.compile(r"^V[0-9]+$")
_GIT_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_EVIDENCE_KEYS = ("evidence_id", "started_at", "finished_at")
_PRODUCER_KINDS = ("engine", "executor", "human")
DECISION_TEXT_LIMIT = 4096  # characters of a decision in planner.decision.accepted


# ---------------------------------------------------------------- reading a plan

def status_of(plan: store.Plan, item_id: str) -> str:
    return plan.items[item_id].get("status", "todo")


def phase_order(plan: store.Plan) -> list[str]:
    phases = plan.plan.get("phases")
    return [p for p in phases if p in plan.phases] if isinstance(phases, list) else []


def phase_items(plan: store.Plan, phase_id: str) -> list[str]:
    declared = plan.phases[phase_id].get("items")
    return [i for i in declared if isinstance(i, str) and i in plan.items] if isinstance(declared, list) else []


def batches_of(plan: store.Plan, phase_id: str) -> list[dict]:
    batches = plan.phases[phase_id].get("batches")
    return [b for b in batches if isinstance(b, dict)] if isinstance(batches, list) else []


def batch_members(plan: store.Plan, phase_id: str, batch: dict) -> list[str]:
    """Members of ``batch`` that exist, in phase order."""
    declared = plan.phases[phase_id].get("items")
    order = {item: n for n, item in enumerate(declared)} if isinstance(declared, list) else {}
    members = [i for i in batch.get("items", []) if isinstance(i, str) and i in plan.items] \
        if isinstance(batch.get("items"), list) else []
    return sorted(members, key=lambda i: order.get(i, len(order)))


def _rank(order: tuple[str, ...], value: Any) -> int:
    return order.index(value) if value in order else -1


def route_of(plan: store.Plan, items: Iterable[str]) -> dict | None:
    """Maximum class and maximum effort over the routes of ``items``; None when none declares a route."""
    routes = [plan.items[i].get("route") for i in items if isinstance(plan.items[i].get("route"), dict)]
    if not routes:
        return None
    value = {"class": max((r.get("class") for r in routes), key=lambda c: _rank(CLASS_ORDER, c)),
             "effort": max((r.get("effort") for r in routes), key=lambda e: _rank(EFFORT_ORDER, e))}
    for field in ("provider", "model", "settings"):
        selections = [r[field] for r in routes if field in r]
        if selections and all(v == selections[0] for v in selections):
            value[field] = copy.deepcopy(selections[0])
    return value


def granted_gates(plan: store.Plan) -> set[str]:
    """Gates with a ``gate_granted`` event whose ``data.gate`` names them."""
    return {event["data"]["gate"] for _, event, _ in store.log_lines(plan.root)
            if event and event.get("type") == "gate_granted" and isinstance(event.get("data"), dict)
            and isinstance(event["data"].get("gate"), str)}


def _phase_deps(plan: store.Plan, phase_id: str) -> list[str]:
    order = phase_order(plan)
    deps = plan.phases[phase_id].get("depends_on")
    if isinstance(deps, list):
        return [d for d in deps if d in plan.phases]
    index = order.index(phase_id) if phase_id in order else 0
    return [order[index - 1]] if index else []


def _blocked_text(plan: store.Plan, item_id: str) -> str:
    escalation = (plan.items[item_id].get("result") or {}).get("escalation") or "no escalation text"
    return f"blocked {item_id} — {escalation}"


def _unmet_dependency(plan: store.Plan, item_id: str, satisfied: Iterable[str]) -> str | None:
    """Reason text of the first dependency of ``item_id`` that neither is satisfying nor is in ``satisfied``."""
    doc = plan.items[item_id]
    deps = doc.get("depends_on") if isinstance(doc.get("depends_on"), list) else []
    satisfied = set(satisfied)
    for dep in deps:  # the builtin next() is shadowed by this module's next(plan)
        if dep in plan.items and status_of(plan, dep) not in SATISFYING and dep not in satisfied:
            return _blocked_text(plan, dep) if status_of(plan, dep) == "blocked" else dep
    return None


def _gate_wait(plan: store.Plan, item_id: str, granted: set[str]) -> str | None:
    authority = plan.items[item_id].get("authority")
    authority = authority if isinstance(authority, dict) else {}
    identity = authority.get("gate") or authority.get("label")
    if authority.get("kind") == "owner_gate" and identity not in granted:
        return f"gate {identity}"
    if authority.get("kind") == "external_gate":
        return f"external gate {identity}"
    return None


def ready_members(plan: store.Plan, phase_id: str, batch: dict, granted: set[str]) -> tuple[list[str], str | None]:
    """Ready members of ``batch`` in phase order, and the first reason a member had to wait."""
    pending = [i for i in batch_members(plan, phase_id, batch) if status_of(plan, i) not in TERMINAL]
    ready: list[str] = []
    reason = None
    for item_id in pending:
        why = _unmet_dependency(plan, item_id, ready) or _gate_wait(plan, item_id, granted)
        if why is None:
            ready.append(item_id)
        else:
            reason = reason or why
    if batch.get("mode") == "required" and len(ready) != len(pending):
        return [], reason
    return ready, reason


# ---------------------------------------------------------------- next

@dataclass(frozen=True)
class Next:
    """The one semantic next step of a plan; ``exact`` is its single-line text."""

    kind: str  # run-items | design-phase | waiting | archive | terminal
    reason: str = ""
    phase: str | None = None
    batch: str | None = None
    items: tuple[str, ...] = ()
    route: dict | None = None
    command: str | None = None

    @property
    def exact(self) -> str:
        return f"{self.kind}: {self.command or self.reason}"

    @property
    def launch(self) -> dict | None:
        if self.command is None:
            return None
        return {"claude": f"/{self.command}", "codex": f"$ {self.command}"}

    def as_dict(self) -> dict:
        return {"kind": self.kind, "exact": self.exact, "phase": self.phase, "batch": self.batch,
                "items": list(self.items), "route": self.route, "launch": self.launch,
                "command": self.command, "reason": self.reason}


def next(plan: store.Plan, *, granted: set[str] | None = None) -> Next:  # noqa: A001 — dossier §6.1 name
    """Semantic Next of ``plan`` (dossier §6.1). ``granted`` defaults to the gates found in the log."""
    plan_id = plan.plan.get("id", plan.root.name)
    if plan.plan.get("status") == "paused":
        pause = plan.plan.get("pause") if isinstance(plan.plan.get("pause"), dict) else {}
        return Next("waiting", f"paused: {pause.get('reason', 'source pause reason missing')}")
    order = phase_order(plan)
    if not order:
        return Next("waiting", "no phases yet (add-phase)")
    granted = granted_gates(plan) if granted is None else granted
    blocked_phase = None  # first closed phase with a blocked item: independent work continues, the plan cannot end
    for phase_id in order:
        phase = plan.phases[phase_id]
        closed = phase.get("closed")
        if closed:
            if blocked_phase is None and any(status_of(plan, i) == "blocked" for i in phase_items(plan, phase_id)):
                blocked_phase = phase_id
            continue
        unmet = [d for d in _phase_deps(plan, phase_id) if not plan.phases[d].get("closed")]
        if unmet:
            return Next("waiting", unmet[0], phase=phase_id)
        if phase.get("design") != "detailed":
            return Next("design-phase", phase=phase_id, command=f"{COMMAND_NAMESPACE}:plan-design {plan_id} {phase_id}")
        for batch in batches_of(plan, phase_id):
            members = batch_members(plan, phase_id, batch)
            if all(status_of(plan, i) in TERMINAL for i in members):
                continue
            ready, reason = ready_members(plan, phase_id, batch, granted)
            if not ready:
                return Next("waiting", reason or f"batch {batch.get('id')}", phase=phase_id, batch=batch.get("id"))
            return Next("run-items", phase=phase_id, batch=batch.get("id"), items=tuple(ready),
                        route=route_of(plan, ready), command=f"{COMMAND_NAMESPACE}:plan-run {plan_id} {' '.join(ready)}")
        if all(status_of(plan, i) in TERMINAL for i in phase_items(plan, phase_id)):  # finished in other trees
            return Next("waiting", f"{phase_id} closure: plan.py reconcile {plan_id}", phase=phase_id)
        return Next("waiting", f"{phase_id} closure (finish the last item)", phase=phase_id)
    if blocked_phase is not None:
        blocked = first_blocked(plan, blocked_phase)
        return Next("waiting", _blocked_text(plan, blocked), phase=blocked_phase)
    if plan.plan.get("status") != "archived":
        return Next("archive", command=f"{COMMAND_NAMESPACE}:plan-close {plan_id} archive")
    return Next("terminal", "plan done")


def first_blocked(plan: store.Plan, phase_id: str) -> str:
    """First blocked item of ``phase_id``."""
    return [i for i in phase_items(plan, phase_id) if status_of(plan, i) == "blocked"][0]


def batch_state(plan: store.Plan, phase_id: str, batch: dict, frontier: Next, granted: set[str]) -> str:
    """Roadmap state of one batch: done, in progress, ready, design-required or ``waiting[: why]``."""
    members = batch_members(plan, phase_id, batch)
    if plan.phases[phase_id].get("design") != "detailed":
        return "design-required"
    if members and all(status_of(plan, i) in TERMINAL for i in members):
        return "done"
    if any(status_of(plan, i) == "in_progress" for i in members):
        return "in progress"
    if frontier.kind == "run-items" and (frontier.phase, frontier.batch) == (phase_id, batch.get("id")):
        return "ready"
    for dep in _phase_deps(plan, phase_id):
        if not plan.phases[dep].get("closed"):
            return f"waiting: {dep}"
    for earlier in batches_of(plan, phase_id):
        if earlier is batch:
            break
        if any(status_of(plan, i) not in TERMINAL for i in batch_members(plan, phase_id, earlier)):
            return f"waiting: {earlier.get('id')}"
    _, reason = ready_members(plan, phase_id, batch, granted)
    return f"waiting: {reason}" if reason else "waiting"


# ---------------------------------------------------------------- route pool

def admitted_class(provider: str, model: str, routing_path: str | Path | None = None) -> str | None:
    """Highest model class (economy < implementation < frontier) the pool grants ``provider``/``model``.

    Lookup is by entry id (or alias), then by pattern (``re.fullmatch``); ``status: retired`` entries are
    skipped. None when the provider or the model is not in the pool, or its roles name no class.
    """
    try:
        metadata = load_routing_metadata(Path(routing_path) if routing_path else ROUTING_PATH)
    except ValueError as exc:
        raise PlanError("ROUTING_UNAVAILABLE", f"cannot read command-routing.json: {exc}") from exc
    mapping = metadata["mappings"].get(provider)
    inventory = mapping.get("model_inventory") if isinstance(mapping, dict) else None
    entries = inventory.get("entries") if isinstance(inventory, dict) else None
    live = [e for e in entries or [] if isinstance(e, dict) and e.get("status") != "retired"]
    matched = [e for e in live if model == e.get("id") or model in e.get("aliases", [])]
    if not matched:
        matched = [e for e in live if any(re.fullmatch(p, model) for p in e.get("patterns", []))]
    ranks = [_rank(CLASS_ORDER, role) for e in matched for role in e.get("roles", []) if role in CLASS_ORDER]
    return CLASS_ORDER[max(ranks)] if ranks else None


def _route_verdict(plan: store.Plan, items: list[str], actor: dict) -> str:
    """``ok`` or ``ROUTE_MODEL_UNKNOWN``; ``ROUTE_UNDERSHOOT`` when the class or effort is too low."""
    admitted = admitted_class(actor["provider"], actor["model"])
    for item_id in items:
        need = plan.items[item_id].get("route") or {}
        if admitted is not None and _rank(CLASS_ORDER, admitted) < _rank(CLASS_ORDER, need.get("class")):
            raise PlanError("ROUTE_UNDERSHOOT", f"{item_id} needs class {need.get('class')}; "
                                                f"{actor['provider']}/{actor['model']} is admitted as {admitted}")
        effort = actor.get("effort")
        if effort and _rank(EFFORT_ORDER, effort) < _rank(EFFORT_ORDER, need.get("effort")):
            raise PlanError("ROUTE_UNDERSHOOT", f"{item_id} needs effort {need.get('effort')}; actor runs {effort}")
    return "ok" if admitted is not None else "ROUTE_MODEL_UNKNOWN"


# ---------------------------------------------------------------- mutation plumbing

@contextmanager
def _mutation(plan) -> Iterator[tuple[store.Plan, store.PlanLock]]:
    """Lock -> fresh snapshot -> body -> views; the caller's ``Plan`` object is refreshed afterwards."""
    from . import views  # views imports this module for scheduling

    root = plan.root if isinstance(plan, store.Plan) else store.resolve_plan_dir(plan)
    timeout = float(settings.for_root(root.parent).get("lock.timeout_seconds"))
    with store.PlanLock(root, timeout=timeout) as lock:
        fresh = store.load_plan(root)
        yield fresh, lock
        views.render_all(fresh)  # reached only when the body did not raise
    if isinstance(plan, store.Plan):
        plan.adopt(fresh)


def _commit(p: store.Plan, changes: list[tuple[str, str | None, dict]], events: list[dict], lock) -> None:
    """Validate events and documents, save the documents, append the events, fold changes into ``p``."""
    for event in events:
        store.check_doc(event, "log-event", "log event")
    store.save_many([(p.path(kind, key), doc, kind) for kind, key, doc in changes])
    for kind, key, doc in changes:
        if kind in ("plan", "brief"):
            setattr(p, kind, doc)
        else:
            {"phase": p.phases, "item": p.items, "decision": p.decisions, "unit": p.units}[kind][key] = doc
    for event in events:
        store.append_log(p.root, event, lock=lock)


# ---------------------------------------------------------------- planner.* events

def event_project_root(p: store.Plan) -> Path | None:
    """The project whose journal receives the events of ``p`` (``None``: the machine journal)."""
    return settings.project_root_of(p.root.parent)


def _event_data(p: store.Plan, title: str, **fields: Any) -> dict:
    """Common fields of the data of every ``planner.*`` event, then ``fields`` without the empty ones."""
    data = {"plan_id": p.plan["id"]}
    if p.plan.get("short_id"):
        data["short_id"] = p.plan["short_id"]
    data["title"] = title
    if p.plan.get("repository"):
        data["repository"] = p.plan["repository"]
    data.update({key: value for key, value in fields.items() if value is not None})
    return data


def _route_data(route: Mapping | None) -> dict | None:
    wanted = {key: route[key] for key in ("class", "effort") if isinstance(route, Mapping) and route.get(key)}
    return wanted or None


def plan_created_event(p: store.Plan) -> tuple[str, dict]:
    return "planner.plan.created", _event_data(p, p.plan["title"], created=p.plan.get("created"))


def _phase_closed_event(p: store.Plan, phase_id: str) -> tuple[str, dict]:
    closed = p.phases[phase_id]["closed"]
    return "planner.phase.closed", _event_data(p, p.phases[phase_id]["title"], phase_id=phase_id,
                                               result=closed["result"], closed_at=closed["at"],
                                               summary=closed.get("summary"))


def _plan_closed_event(p: store.Plan, closed_at: str) -> tuple[str, dict]:
    statuses = [status_of(p, item_id) for item_id in p.items]
    counts = {"items": len(statuses)}
    counts.update({status.value: statuses.count(status.value) for status in ItemStatus if status in TERMINAL})
    phases = [{"id": phase_id, "title": p.phases[phase_id]["title"], "status": p.phases[phase_id]["closed"]["result"]}
              for phase_id in phase_order(p)]
    return "planner.plan.closed", _event_data(p, p.plan["title"], status="done", goal=p.plan.get("goal"),
                                              closed_at=closed_at, phases=phases, counts=counts)


def _closure_events(p: store.Plan, phases: Iterable[str], plan_done: bool, now: str) -> list[tuple[str, dict]]:
    """``planner.phase.closed`` per closed phase, then ``planner.plan.closed`` when the plan ended; ``p`` holds the
    saved state."""
    events = [_phase_closed_event(p, phase_id) for phase_id in phases]
    if plan_done:
        events.append(_plan_closed_event(p, now))
    return events


def _actor_doc(p: store.Plan, actor: Mapping | None, item: str | None = None) -> dict:
    """The acting identity: explicit, else the item's executor, else the plan's authoring actor."""
    if actor:
        return dict(actor)
    executor = (p.items[item].get("result") or {}).get("executor") if item in p.items else None
    if isinstance(executor, dict):
        return dict(executor)
    authoring = p.plan.get("authoring")
    return dict(authoring) if isinstance(authoring, dict) else {"provider": "unknown", "model": "unknown"}


def _given_actor(actor: Mapping | None) -> dict | None:
    """``actor`` without empty fields, or None when nothing was given."""
    cleaned = {k: v for k, v in dict(actor or {}).items() if v}
    return cleaned or None


def same_actor(a: Mapping | None, b: Mapping | None) -> bool:
    """Same provider and model, and no field both name differently (a registrar rarely knows the session)."""
    if not a or not b:
        return False
    return all(a[k] == b[k] for k in a.keys() & b.keys()) and all(a.get(k) == b.get(k) for k in ("provider", "model"))


def need_attempt(attempt_id: str | None) -> str | None:
    """``attempt_id`` when it is a valid ``defs.attemptId``; ``ATTEMPT_ID_INVALID`` otherwise."""
    if attempt_id is not None and not ATTEMPT_ID.fullmatch(attempt_id):
        raise PlanError("ATTEMPT_ID_INVALID", f"--attempt-id {attempt_id!r} must match {ATTEMPT_ID.pattern}")
    return attempt_id


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _load_evidence(p: store.Plan, item_ref: str, check_id: str, path: str) -> int:
    """Exit of check ``check_id`` proven by the check-evidence file at ``path`` (repo-relative or ``@plan/``).

    Planner check-evidence field contract (schemas/plan/v1/check-evidence.schema.json): a structural stdlib check of
    the key fields; any non-empty ``$schema`` passes (D19), so documents of external producers need no conversion.
    A command carries its observed ``exit``; a manual procedure carries a ``verdict``, mapped to 0 (``pass``) or 1
    (``fail``) — no shell exit is invented for it. ``item_ref`` is ``P1.2`` or ``P1.2/U1``; the evidence must name it and the check.
    """
    from . import context  # context imports this module for scheduling

    def invalid(field: str, why: str) -> PlanError:
        return PlanError("EVIDENCE_INVALID", f"{check_id} evidence {path}: {field} {why}")

    target = context._resolve(p, path) if isinstance(path, str) and path else None
    if target is None or not target.is_file():
        raise invalid("file", "must exist inside the repository or the plan directory")
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise invalid("file", f"is not readable JSON ({error})") from None
    if not isinstance(doc, dict):
        raise invalid("document", "must be a JSON object")
    if not _text(doc.get("$schema")):
        raise invalid("$schema", "is required")
    for field in _EVIDENCE_KEYS:
        if not _text(doc.get(field)):
            raise invalid(field, "is required")
    producer = doc.get("producer")
    if not isinstance(producer, dict) or producer.get("kind") not in _PRODUCER_KINDS:
        raise invalid("producer.kind", f"must be one of {', '.join(_PRODUCER_KINDS)}")
    if not isinstance(doc.get("check_id"), str) or not _CHECK_ID.fullmatch(doc["check_id"]):
        raise invalid("check_id", "must match V<n>")
    subject = f"{p.plan.get('short_id') or p.plan['id']}.{item_ref}"
    if doc["check_id"] != check_id or doc.get("subject") != subject:
        raise PlanError("EVIDENCE_SUBJECT", f"{path} proves {doc.get('subject')!r} {doc['check_id']}, "
                                            f"not {subject!r} {check_id}")
    candidate = doc.get("candidate")
    if not isinstance(candidate, dict) or not isinstance(candidate.get("head"), str) \
            or not _GIT_SHA.fullmatch(candidate["head"]):
        raise invalid("candidate.head", "must be a 7-40 character lowercase hex Git revision")
    procedure = doc.get("procedure")
    if not isinstance(procedure, dict):
        raise invalid("procedure", "must be an object")
    command, manual = _text(procedure.get("cmd")), _text(procedure.get("procedure"))
    if command == manual or ("cmd" in procedure and "procedure" in procedure):
        raise invalid("procedure", "needs exactly one non-empty cmd or procedure")
    if command:
        if "verdict" in doc:
            raise invalid("verdict", "belongs to a manual procedure, not a command")
        if isinstance(doc.get("exit"), bool) or not isinstance(doc.get("exit"), int):
            raise invalid("exit", "must be the integer exit of the command")
        return doc["exit"]
    if "exit" in doc:
        raise invalid("exit", "is never recorded for a manual procedure; use verdict")
    if doc.get("verdict") not in ("pass", "fail"):
        raise invalid("verdict", "must be pass or fail")
    if not _text(doc.get("observation")):
        raise invalid("observation", "is required for a manual procedure")
    return 0 if doc["verdict"] == "pass" else 1


def load_evidence(p: store.Plan, item_ref: str, evidence: Mapping[str, str], known: Iterable[str]) -> dict[str, int]:
    """``{V#: exit}`` of every evidence file; ``CHECK_UNKNOWN`` for a check outside ``known``."""
    unknown = sorted(set(evidence) - set(known))
    if unknown:
        raise PlanError("CHECK_UNKNOWN", f"{item_ref} declares no check {', '.join(unknown)}")
    return {check_id: _load_evidence(p, item_ref, check_id, path) for check_id, path in evidence.items()}


def _need_phase(p: store.Plan, phase_id: str) -> dict:
    if phase_id not in p.phases:
        raise PlanError("REF_UNKNOWN", f"unknown phase {phase_id!r}")
    return p.phases[phase_id]


def _need_item(p: store.Plan, item_id: str) -> dict:
    if item_id not in p.items:
        raise PlanError("REF_UNKNOWN", f"unknown item {item_id!r}")
    return p.items[item_id]


def _item_phase(item_id: str) -> str:
    return item_id.split(".", 1)[0]


# ---------------------------------------------------------------- start

def next_batch_id(p: store.Plan, phase_id: str, item_id: str) -> str | None:
    """Id of the batch that holds ``item_id``, or None."""
    for batch in batches_of(p, phase_id):
        if item_id in (batch.get("items") or []):
            return batch.get("id")
    return None


def shown_path(path: Path) -> str:
    """``path`` relative to the working directory when it lies below it, else absolute."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def validate_route(route: dict, actor: Mapping, target: str) -> None:
    """Explicit selections are portable pins; semantic class/effort remain minimums."""
    for field in ("provider", "model"):
        if route.get(field) and route[field] != actor.get(field):
            raise PlanError("ROUTE_MISMATCH", f"{target} selects {field} {route[field]!r}")
    if route.get("effort") and (route.get("model") or actor.get("effort")):
        if not actor.get("effort") or _rank(EFFORT_ORDER, actor["effort"]) < _rank(EFFORT_ORDER, route["effort"]):
            raise PlanError("ROUTE_UNDERSHOOT", f"{target} needs effort {route['effort']}")


@dataclass(frozen=True)
class StartResult:
    items: tuple[str, ...]
    phase: str
    batch: str | None
    route: str  # "ok" | "ROUTE_MODEL_UNKNOWN"
    resumed: tuple[str, ...]
    packs: tuple[Path, ...] = ()  # context packs, one per item, in request order
    scouts: tuple[str, ...] = ()  # one outcome line per scouted item (``scout <item>: ok (…)``)

    def text(self, plan_id: str) -> str:
        lines = [f"started {', '.join(self.items)} (phase {self.phase}"
                 + (f", batch {self.batch}" if self.batch else "") + f"; route {self.route})"]
        if self.resumed:
            lines.append(f"resumed: {', '.join(self.resumed)} (started_at kept)")
        if self.packs:
            lines.extend(self.scouts)
            lines.append("context packs: " + ", ".join(shown_path(pack) for pack in self.packs))
            lines.append(f"Read {shown_path(self.packs[0])} first.")
        lines.append(f"finish each with: plan.py finish {plan_id} <item> --status done --check V1=0 --notes …")
        return "\n".join(lines)


def _owner_conflict(doc: Mapping, actor: Mapping) -> dict | None:
    """The executor that owns the attempt of an ``in_progress`` item when ``actor`` is another one, else ``None``.

    Ownership is the ``session`` of ``result.executor``: it is checked only when both sides name a session, so
    plans and calls without one keep resuming as before.
    """
    result = doc.get("result") if isinstance(doc.get("result"), dict) else {}
    prior = result.get("executor") if isinstance(result.get("executor"), dict) else {}
    if doc.get("status") != "in_progress" or not prior.get("session") or not actor.get("session"):
        return None
    if prior["session"] != actor["session"] or prior.get("provider") != actor.get("provider"):
        return dict(prior)
    return None


def start(plan, items: Iterable[str], actor: Mapping, *, grants: Iterable[str] = (),
          scout: bool | None = None, registrar: Mapping | None = None, take_over: bool = False) -> StartResult:
    """Move ``items`` (one detailed phase) to ``in_progress``; an ``in_progress`` item is resumed.

    ``actor`` is the executor (route-checked, stored as ``result.executor``); ``registrar`` is who called and
    only lands in the ``start`` event as ``registered_by``.

    One session owns the attempt of an ``in_progress`` item: another session starting it is refused with
    ``ITEM_OWNED`` unless ``take_over`` hands the attempt over (the ``start`` event then records the previous
    executor in ``data.take_over``). ``finish`` does not check ownership.

    ``scout`` asks the provider's weak model for a context map after the start (D3); ``None`` follows
    ``plan.settings.scout``. A scout failure never fails the start.
    """
    requested = list(items)
    grants = list(grants)
    registrar = _given_actor(registrar)
    with _mutation(plan) as (p, lock):
        actor = {k: v for k, v in dict(actor).items() if v}
        if not actor.get("provider") or not actor.get("model"):
            raise PlanError("ACTOR_REQUIRED", "start needs --actor PROVIDER/MODEL[/EFFORT]")
        if registrar is not None and not (registrar.get("provider") and registrar.get("model")):
            raise PlanError("ACTOR_REQUIRED", "--registrar needs PROVIDER/MODEL[/EFFORT]")
        if not requested:
            raise PlanError("ITEMS_REQUIRED", "name at least one item to start")
        if len(set(requested)) != len(requested):
            raise PlanError("ITEMS_DUPLICATE", "an item is listed twice")
        for item_id in requested:
            if not ITEM_ID.fullmatch(item_id) or item_id not in p.items:
                raise PlanError("REF_UNKNOWN", f"unknown item {item_id!r}")
        phase_id = _item_phase(requested[0])
        if any(_item_phase(i) != phase_id for i in requested):
            raise PlanError("ITEMS_SPAN_PHASES", f"items {', '.join(requested)} belong to more than one phase")
        phase = _need_phase(p, phase_id)
        if phase.get("design") != "detailed":
            raise PlanError("PHASE_NOT_DETAILED", f"{phase_id} is a skeleton; design it first "
                                                  f"(plan.py design-done after detailing)")
        for item_id in requested:
            if status_of(p, item_id) not in ("todo", "in_progress"):
                raise PlanError("ITEM_NOT_STARTABLE", f"{item_id} is {status_of(p, item_id)}; use reopen to redo it")
        owners = {item_id: _owner_conflict(p.items[item_id], actor) for item_id in requested}
        for item_id, owner in owners.items():
            if owner and not take_over:
                since = (p.items[item_id].get("result") or {}).get("started_at")
                raise PlanError("ITEM_OWNED", f"{item_id} is in progress by {owner.get('provider')}/{owner.get('model')} "
                                              f"session {owner['session']} since {since}; resume it from that session "
                                              f"or start --take-over")
        for dep in _phase_deps(p, phase_id):
            if not p.phases[dep].get("closed"):
                raise PlanError("DEPENDENCY_NOT_READY", f"phase {phase_id} waits for phase {dep}")
            if p.phases[dep]["closed"].get("result") == "blocked":
                raise PlanError("DEPENDENCY_NOT_READY", f"phase {dep} is closed as blocked")
        for position, item_id in enumerate(requested):
            unmet = _unmet_dependency(p, item_id, requested[:position])
            if unmet:
                raise PlanError("DEPENDENCY_NOT_READY", f"{item_id} waits for {unmet}")
        known_gates = {(d.get("authority") or {}).get("gate") or (d.get("authority") or {}).get("label")
                       for d in p.items.values() if (d.get("authority") or {}).get("kind") == "owner_gate"}
        for gate in grants:
            if gate not in known_gates:
                raise PlanError("GATE_UNKNOWN", f"no item declares owner gate {gate!r}")
        granted = granted_gates(p) | set(grants)
        for item_id in requested:
            wait = _gate_wait(p, item_id, granted)
            if wait:
                if (p.items[item_id].get("authority") or {}).get("kind") == "external_gate":
                    raise PlanError("EXTERNAL_GATE", f"{item_id} needs {wait}; reconcile the external evidence first")
                raise PlanError("GATE_NOT_GRANTED", f"{item_id} needs {wait} (plan.py grant, or start --grant)")
        verdict = _route_verdict(p, requested, actor)
        for item_id in requested:
            validate_route(p.items[item_id].get("route") or {}, actor, item_id)
        from . import context  # context imports this module for scheduling

        missing = [f"{i}: {path}" for i in requested for path in context.missing_reads(p, i)]
        if missing:
            raise PlanError("READ_MISSING", f"required read(s) missing — {'; '.join(missing)}")
        # Resolve inputs before any lifecycle state is written.
        for item_id in requested:
            context.collect(p, item_id, with_scout=False)

        now = store.now()
        changes, events, resumed = [], [], []
        gate_events = [store.new_event("gate_granted", f"gate {gate} granted at start", actor, phase=phase_id,
                                       data={"gate": gate, "via": "start"})
                       for gate in grants if gate not in granted_gates(p)]
        for item_id in requested:
            doc = copy.deepcopy(p.items[item_id])
            prior = doc.get("result") if isinstance(doc.get("result"), dict) else {}
            if doc.get("status") == "in_progress":
                resumed.append(item_id)
            result = dict(prior) if doc.get("status") == "in_progress" else {}
            result.setdefault("started_at", now)
            result["executor"] = actor
            doc["status"], doc["result"] = "in_progress", result
            changes.append(("item", item_id, doc))
            batch_id = next_batch_id(p, phase_id, item_id)
            data = {"requested": requested, "route": verdict}
            if owners[item_id]:
                data["take_over"] = {"previous": owners[item_id]}
            event = store.new_event(
                "start", f"start {item_id}" + (f" (batch {batch_id})" if batch_id else ""), actor,
                item=item_id, phase=phase_id, data=data)
            if registrar is not None:
                event["registered_by"] = registrar
            events.append(event)
        _commit(p, changes, gate_events + events, lock)
        announce = [("planner.item.started", _event_data(
            p, p.items[item_id]["title"], item_id=item_id, phase_id=phase_id,
            executor={key: actor[key] for key in ("provider", "model", "effort", "session") if actor.get(key)},
            route=_route_data(p.items[item_id].get("route")), resumed=item_id in resumed,
            take_over=True if owners[item_id] else None)) for item_id in requested]
        project_root, plan_id = event_project_root(p), p.plan["id"]
        packs = tuple(context.build(p, item_id) for item_id in requested)
        result = StartResult(tuple(requested), phase_id, next_batch_id(p, phase_id, requested[0]), verdict,
                             tuple(resumed), packs)
        wanted = (p.plan.get("settings") or {}).get("scout") == "auto" if scout is None else scout
        root = p.root
    emission.emit_all(announce, project_root=project_root, plan_id=plan_id)
    if not wanted:
        return result
    from . import scout as scout_map  # scout imports this module for the plan lock

    scouts = tuple(scout_map.run(root, item_id, actor["provider"]).text(item_id) for item_id in requested)
    fresh = store.load_plan(root)  # the pack is rebuilt with section 13 (or without it after a failure)
    if isinstance(plan, store.Plan):
        plan.adopt(fresh)
    packs = tuple(context.build(fresh, item_id) for item_id in requested)
    return StartResult(result.items, result.phase, result.batch, result.route, result.resumed, packs, scouts)


# ---------------------------------------------------------------- finish

@dataclass(frozen=True)
class FinishResult:
    item: str
    status: str
    phase_closed: str | None  # closure result when this finish closed the phase
    plan_done: bool
    next: Next
    already_registered: bool = False  # the same attempt was registered before: nothing was written
    attempt_id: str | None = None

    def text(self) -> str:
        if self.already_registered:
            return f"{self.item} already registered (attempt {self.attempt_id})\nnext: {self.next.exact}"
        lines = [f"{self.item} {self.status}"]
        if self.phase_closed:
            lines.append(f"phase {_item_phase(self.item)} closed: {self.phase_closed}")
        if self.plan_done:
            lines.append("plan done")
        lines.append(f"next: {self.next.exact}")
        return "\n".join(lines)


def _recorded_checks(doc: dict) -> dict[str, int]:
    result = doc.get("result") if isinstance(doc.get("result"), dict) else {}
    return {c["id"]: c["exit"] for c in result.get("checks", []) if isinstance(c, dict) and "id" in c and "exit" in c}


def _check_evidence(doc: dict) -> dict[str, str]:
    result = doc.get("result") if isinstance(doc.get("result"), dict) else {}
    return {c["id"]: c["evidence"] for c in result.get("checks", []) if isinstance(c, dict) and "id" in c and "evidence" in c}


def _closure_summary(statuses: list[str]) -> str:
    counts = [(s.value, statuses.count(s.value)) for s in ItemStatus if statuses.count(s.value)]
    return f"{len(statuses)} item(s): " + ", ".join(f"{n} {name}" for name, n in counts)


def _plan_done(p: store.Plan, closing: Mapping[str, dict]) -> bool:
    """Every phase is closed without ``blocked`` once the phase documents in ``closing`` are saved."""
    results = [(closing.get(pid) or p.phases[pid]).get("closed") for pid in phase_order(p)]
    return bool(results) and all(isinstance(c, dict) and c.get("result") != "blocked" for c in results)


def _closure(p: store.Plan, phase_id: str, statuses: Iterable[str], actor_doc: dict, now: str,
             via: str | None = None) -> tuple[list[tuple[str, str | None, dict]], list[dict], bool]:
    """Closure of ``phase_id`` from its item ``statuses``: the phase change, its ``phase_closed`` event and
    whether that closure ends the plan. Nothing while an item is still open. The caller writes the plan."""
    statuses = list(statuses)
    closure = phase_status(statuses)
    if closure is None:
        return [], [], False
    phase_doc = copy.deepcopy(p.phases[phase_id])
    phase_doc["closed"] = {"at": now, "result": closure, "summary": _closure_summary(statuses)}
    event = store.new_event("phase_closed", f"{phase_id} closed: {closure}", actor_doc, phase=phase_id,
                            data={"result": closure, **({"via": via} if via else {})})
    return [("phase", phase_id, phase_doc)], [event], _plan_done(p, {phase_id: phase_doc})


def _done_plan(p: store.Plan) -> tuple[str, None, dict]:
    plan_doc = copy.deepcopy(p.plan)
    plan_doc["status"] = "done"
    return "plan", None, plan_doc


def finish(plan, item_id: str, status: str, *, notes: str = "", checks: Mapping[str, int] | None = None,
           deviations: Iterable[str] = (), pending: Iterable[str] = (), escalation: str | None = None,
           commits: Iterable[str] = (), decision: str | None = None, actor: Mapping | None = None,
           executed_by: Mapping | None = None, attempt_id: str | None = None,
           evidence: Mapping[str, str] | None = None) -> FinishResult:
    """Record the outcome of ``item_id``; closes the phase, and the plan, when it was the last open piece.

    ``actor`` is the registrar; ``executed_by`` (route-checked) replaces ``result.executor``. A repeat of the
    recorded ``attempt_id`` with the same status and checks writes nothing (``already_registered``); any other
    repeat of it is ``ATTEMPT_CONFLICT``.

    ``evidence`` maps ``V#`` to a check-evidence file: its exit is the recorded check result and its path the
    check's ``evidence``; a ``checks`` exit that disagrees is ``EVIDENCE_CONFLICT``. With
    ``plan.settings.evidence == "required"`` a done item needs evidence for every acceptance check.
    """
    checks, deviations, pending, commits = dict(checks or {}), list(deviations), list(pending), list(commits)
    evidence = dict(evidence or {})
    registrar, executed_by, attempt_id = _given_actor(actor), _given_actor(executed_by), need_attempt(attempt_id)
    with _mutation(plan) as (p, lock):
        item = copy.deepcopy(_need_item(p, item_id))
        if status not in FINISH_STATUSES:
            raise PlanError("STATUS_INVALID", f"status must be one of {', '.join(FINISH_STATUSES)}")
        phase_id = _item_phase(item_id)
        known = {c["id"] for c in item.get("validation", []) if isinstance(c, dict)}
        known |= {c["id"] for c in p.phases[phase_id].get("validation", []) if isinstance(c, dict)}
        proven = load_evidence(p, item_id, evidence, known)
        conflict = sorted((i for i in proven if i in checks and checks[i] != proven[i]), key=id_sort_key)
        if conflict:
            raise PlanError("EVIDENCE_CONFLICT", "; ".join(f"--check {i}={checks[i]} but {evidence[i]} proves exit "
                                                           f"{proven[i]}" for i in conflict))
        checks.update(proven)
        prior = item.get("result") if isinstance(item.get("result"), dict) else {}
        if attempt_id is not None and prior.get("attempt_id") == attempt_id:
            recorded = _recorded_checks(item)
            proofs = _check_evidence(item)
            if item.get("status") != status or any(recorded.get(i) != code for i, code in checks.items()) \
                    or any(proofs.get(i) != path for i, path in evidence.items()):
                raise PlanError("ATTEMPT_CONFLICT", f"attempt {attempt_id} already registered {item_id} as "
                                                    f"{item.get('status')} with other outcome")
            return FinishResult(item_id, item["status"], None, p.plan.get("status") == "done", next(p),
                                already_registered=True, attempt_id=attempt_id)
        current = item.get("status", "todo")
        if current != "in_progress" and not (status == "skipped" and current == "todo"):
            raise PlanError("NOT_STARTED", f"{item_id} is {current}; start it first"
                                           + (" (use reopen to redo a finished item)" if current in TERMINAL else ""))
        if status in ("done", "done_with_deviations"):
            open_units = sorted(key.split("/")[1] for key, unit in p.units.items()
                                if key.startswith(f"{item_id}/") and unit.get("status") not in ("accepted", "rejected"))
            if open_units:
                raise PlanError("UNITS_OPEN", f"{item_id} has units still out: {', '.join(open_units)} "
                                              "(plan.py unit … accept|reject|rework)")
        unknown = sorted(set(checks) - known)
        if unknown:
            raise PlanError("CHECK_UNKNOWN", f"{item_id} declares no check {', '.join(unknown)}")
        recorded = _recorded_checks(item)
        recorded.update(checks)
        acceptance = [c["id"] for c in item.get("validation", []) if isinstance(c, dict) and c.get("kind") == "acceptance"]
        missing = [i for i in acceptance if i not in recorded]
        red = [i for i in acceptance if i in recorded and recorded[i] != 0]
        if status == "done":
            if red:
                raise PlanError("CHECKS_RED", f"acceptance check(s) failed: {', '.join(f'{i}={recorded[i]}' for i in red)}")
            if missing:
                raise PlanError("CHECKS_MISSING", f"acceptance check(s) not recorded: {', '.join(missing)} (--check V1=0)")
        elif status == "done_with_deviations":
            if missing:
                raise PlanError("CHECKS_MISSING", f"acceptance check(s) not recorded: {', '.join(missing)} (--check V1=0)")
            if not deviations:
                raise PlanError("DEVIATION_REQUIRED", "done_with_deviations needs at least one --deviation")
        elif status == "blocked":
            if not escalation:
                raise PlanError("ESCALATION_REQUIRED", "blocked needs --escalation: what the owner must decide or provide")
        else:  # skipped
            if not decision:
                raise PlanError("DECISION_REQUIRED", "skipped needs --decision D#: an accepted decision that skips the item")
            try:
                ref = parse_ref(decision)
            except ValueError:
                raise PlanError("DECISION_REQUIRED", f"{decision!r} is not a decision reference") from None
            if ref.kind != "decision":
                raise PlanError("DECISION_REQUIRED", f"{decision!r} is not a decision reference")
            if ref.plan is None and p.decisions.get(ref.target, {}).get("status") != "accepted":
                raise PlanError("DECISION_REQUIRED", f"decision {decision} is not an accepted decision of this plan")

        # A check re-recorded without evidence loses the evidence of its earlier result.
        proofs = {i: path for i, path in _check_evidence(item).items() if i not in checks}
        proofs.update(evidence)
        if status in ("done", "done_with_deviations") and (p.plan.get("settings") or {}).get("evidence") == "required":
            unproven = [i for i in acceptance if i not in proofs]
            if unproven:
                raise PlanError("EVIDENCE_REQUIRED", f"plan settings.evidence is required; acceptance check(s) without "
                                                     f"evidence: {', '.join(unproven)} (--evidence V1=PATH)")

        if executed_by is not None:
            _route_verdict(p, [item_id], executed_by)
            validate_route(item.get("route") or {}, executed_by, item_id)

        now = store.now()
        result = {key: prior[key] for key in ("started_at", "executor") if key in prior}
        if executed_by is not None:
            result["executor"] = executed_by
        executor = result.get("executor")
        # New keys appear only with explicit flags, so the record of the old flow stays byte-compatible.
        attribution = {}
        if (executed_by or registrar) and executor:
            attribution["executed_by"] = executor
        if registrar and not same_actor(registrar, executor):
            attribution["registered_by"] = registrar
        if attempt_id is not None:
            attribution["attempt_id"] = attempt_id
        result.update({k: v for k, v in attribution.items() if k != "executed_by"})
        result["finished_at"] = now
        for key, value in (("notes", notes), ("deviations", deviations), ("pending", pending),
                           ("escalation", escalation), ("commits", commits), ("decision", decision)):
            if value:
                result[key] = value
        ordered = sorted(recorded, key=id_sort_key)
        stamped = {c["id"]: c["at"] for c in prior.get("checks", []) if isinstance(c, dict) and "id" in c}
        stamped.update({i: now for i in checks})
        if recorded:
            result["checks"] = [{"id": i, "exit": recorded[i], "at": stamped.get(i, now),
                                 **({"evidence": proofs[i]} if i in proofs else {})} for i in ordered]
        paths = list(dict.fromkeys(proofs[i] for i in ordered if i in proofs))
        if paths:
            result["evidence"] = paths
        item["status"], item["result"] = status, result
        actor_doc = _actor_doc(p, registrar or executed_by, item_id)
        changes: list[tuple[str, str | None, dict]] = [("item", item_id, item)]
        events = [store.new_event("finish", f"{item_id} {status}", actor_doc, item=item_id, phase=phase_id,
                                  data={"status": status, "checks": {i: recorded[i] for i in ordered}})]
        events[0].update(attribution)

        after = {**{i: status_of(p, i) for i in phase_items(p, phase_id)}, item_id: status}
        closing, closed_events, plan_done = _closure(p, phase_id, after.values(), actor_doc, now)
        changes += closing
        events += closed_events
        if plan_done:
            changes.append(_done_plan(p))
        _commit(p, changes, events, lock)
        closure = closing[0][2]["closed"]["result"] if closing else None
        announce = [("planner.item.finished", _event_data(
            p, p.items[item_id]["title"], item_id=item_id, phase_id=phase_id, status=status, attempt_id=attempt_id,
            checks={i: recorded[i] for i in ordered} or None, commits=commits or None,
            deviation_count=len(deviations)))]
        announce += _closure_events(p, [phase_id] if closing else [], plan_done, now)
        project_root, plan_id = event_project_root(p), p.plan["id"]
        outcome = FinishResult(item_id, status, closure, plan_done, next(p))
    emission.emit_all(announce, project_root=project_root, plan_id=plan_id)
    return outcome


# ---------------------------------------------------------------- reconcile

@dataclass(frozen=True)
class ReconcileResult:
    closed: tuple[tuple[str, str], ...]  # (phase, closure result) in plan order
    plan_done: bool
    next: Next

    def text(self) -> str:
        lines = [f"phase {phase} closed: {result}" for phase, result in self.closed]
        if self.plan_done:
            lines.append("plan done")
        lines.append(f"next: {self.next.exact}" if lines else f"nothing to reconcile\nnext: {self.next.exact}")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {"closed": [{"phase": phase, "result": result} for phase, result in self.closed],
                "plan_done": self.plan_done, "next": self.next.as_dict()}


def reconcile(plan, actor: Mapping | None = None) -> ReconcileResult:
    """Integrator closure after parallel trees merged: close every open phase whose items are all terminal,
    then the plan. Idempotent: with nothing to close it appends no event and writes no file."""
    with _mutation(plan) as (p, lock):
        actor_doc, now = _actor_doc(p, _given_actor(actor)), store.now()
        changes: list[tuple[str, str | None, dict]] = []
        events: list[dict] = []
        closing: dict[str, dict] = {}
        for phase_id in phase_order(p):
            members = phase_items(p, phase_id)
            if p.phases[phase_id].get("closed") or not members:
                continue
            phase_changes, phase_events, _ = _closure(p, phase_id, [status_of(p, i) for i in members], actor_doc, now,
                                                      via="reconcile")
            if phase_changes:
                closing[phase_id] = phase_changes[0][2]
                changes += phase_changes
                events += phase_events
        plan_done = p.plan.get("status") not in ("done", "archived") and _plan_done(p, closing)
        if plan_done:
            changes.append(_done_plan(p))
        if changes:
            _commit(p, changes, events, lock)
        closed = tuple((phase_id, doc["closed"]["result"]) for phase_id, doc in closing.items())
        announce = _closure_events(p, closing, plan_done, now)
        project_root, plan_id = event_project_root(p), p.plan["id"]
        result = ReconcileResult(closed, plan_done, next(p))
    emission.emit_all(announce, project_root=project_root, plan_id=plan_id)
    return result


# ---------------------------------------------------------------- log, decisions, grants

def log(plan, target: str, type: str, summary: str, impact: str | None = None,  # noqa: A002
        next: str | None = None, refs: Iterable[str] = (), actor: Mapping | None = None) -> dict:  # noqa: A002
    """Append a friction event for an item or a phase; returns the event."""
    with _mutation(plan) as (p, lock):
        if type not in FRICTION_TYPES:
            raise PlanError("LOG_TYPE_INVALID", f"type must be one of {', '.join(FRICTION_TYPES)}")
        if ITEM_ID.fullmatch(target):
            _need_item(p, target)
            where = {"item": target, "phase": _item_phase(target)}
        elif PHASE_ID.fullmatch(target):
            _need_phase(p, target)
            where = {"phase": target}
        else:
            raise PlanError("REF_INVALID", f"target must be an item or a phase, received {target!r}")
        event = store.new_event(type, summary, _actor_doc(p, actor, where.get("item")), impact=impact, next=next,
                                refs=list(refs), **where)
        _commit(p, [], [event], lock)
        return event


def decide(plan, decision_id: str, accept: str, rationale: str, by: str = "agent",
           actor: Mapping | None = None) -> dict:
    """Turn an open question into an accepted decision: ``accept`` is an option id or the decision text."""
    with _mutation(plan) as (p, lock):
        if decision_id not in p.decisions:
            raise PlanError("REF_UNKNOWN", f"unknown decision {decision_id!r}")
        doc = copy.deepcopy(p.decisions[decision_id])
        if doc.get("status") != "open":
            raise PlanError("DECISION_NOT_OPEN", f"{decision_id} is {doc.get('status')}, not open")
        if by not in ("owner", "agent"):
            raise PlanError("BY_INVALID", "by must be owner or agent")
        if not rationale or not rationale.strip():
            raise PlanError("RATIONALE_REQUIRED", "a rationale is required")
        if not accept or not accept.strip():
            raise PlanError("ACCEPT_REQUIRED", "name the option id or write the decision text")
        options = {o.get("id"): o for o in doc.get("options", []) if isinstance(o, dict)}
        if _OPTION_ID.fullmatch(accept) and options:
            if accept not in options:
                raise PlanError("OPTION_UNKNOWN", f"{decision_id} has no option {accept!r} ({', '.join(options)})")
            text, option = f"{accept} — {options[accept]['text']}", accept
        else:
            text, option = accept, None
        doc.update(status="accepted", decision=text, rationale=rationale, answered_by=by)
        event = store.new_event("decision", f"{decision_id} accepted", _actor_doc(p, actor), data={
            "id": decision_id, "by": by, **({"option": option} if option else {})})
        _commit(p, [("decision", decision_id, doc)], [event], lock)
        announce = [("planner.decision.accepted", _event_data(
            p, doc["title"], decision_id=decision_id, decision=text if len(text) <= DECISION_TEXT_LIMIT
            else text[:DECISION_TEXT_LIMIT - 1] + "…", answered_by=by,
            applies_to=list(doc.get("applies_to") or []) or None))]
        project_root, plan_id = event_project_root(p), p.plan["id"]
    emission.emit_all(announce, project_root=project_root, plan_id=plan_id)
    return doc


def supersede(plan, old: str, new: str, actor: Mapping | None = None) -> None:
    """``new`` (accepted) replaces ``old``: sets ``superseded_by``/``supersedes`` and the old status."""
    with _mutation(plan) as (p, lock):
        for ref in (old, new):
            if ref not in p.decisions:
                raise PlanError("REF_UNKNOWN", f"unknown decision {ref!r}")
        if old == new:
            raise PlanError("DECISION_SELF_SUPERSEDE", "a decision cannot supersede itself")
        if p.decisions[old].get("status") == "superseded":
            raise PlanError("DECISION_SUPERSEDED", f"{old} is already superseded by {p.decisions[old].get('superseded_by')}")
        if p.decisions[new].get("status") != "accepted":
            raise PlanError("DECISION_NOT_ACCEPTED", f"{new} must be accepted before it can supersede {old}")
        old_doc, new_doc = copy.deepcopy(p.decisions[old]), copy.deepcopy(p.decisions[new])
        old_doc.update(status="superseded", superseded_by=new)
        new_doc["supersedes"] = sorted({*new_doc.get("supersedes", []), old}, key=id_sort_key)
        event = store.new_event("decision", f"{new} supersedes {old}", _actor_doc(p, actor),
                                data={"id": new, "supersedes": old})
        _commit(p, [("decision", old, old_doc), ("decision", new, new_doc)], [event], lock)


def grant(plan, gate: str, note: str, actor: Mapping | None = None) -> Next:
    """Record an owner gate grant; ``note`` quotes the owner's message. Granting twice is a no-op."""
    with _mutation(plan) as (p, lock):
        if not _GATE.fullmatch(gate or ""):
            raise PlanError("GATE_INVALID", f"gate must match [A-Z0-9-]+, received {gate!r}")
        if not note or not note.strip():
            raise PlanError("NOTE_REQUIRED", "--note must quote the owner's message that grants the gate")
        if not any((d.get("authority") or {}).get("kind") == "owner_gate"
                   and ((d.get("authority") or {}).get("gate") or (d.get("authority") or {}).get("label")) == gate
                   for d in p.items.values()):
            raise PlanError("GATE_UNKNOWN", f"no item declares owner gate {gate!r}")
        if gate not in granted_gates(p):
            event = store.new_event("gate_granted", f"gate {gate} granted", _actor_doc(p, actor),
                                    data={"gate": gate, "note": note})
            _commit(p, [], [event], lock)
        return next(p)


# ---------------------------------------------------------------- design-done, reopen, archive

CONTEXT_WARNINGS = ("context_unbound", "brief_duplicate", "context_heavy", "context_legacy")


def design_report(plan, phase_id: str) -> dict:
    """Pack-size and knowledge-binding report of a detailed phase; read-only, a failure is reported, not raised."""
    from . import budget, check  # budget imports context, check imports views; both import this module

    try:
        p = store.load_plan(store.resolve_plan_dir(plan))
        items = phase_items(p, phase_id)
        report = {"phase": phase_id, "detailed": p.phases[phase_id].get("design") == "detailed",
                  "mode": None, "budget_bytes": None, "items": [], "warnings": [], "phase_documents_unread": []}
        for item_id in items:
            m = budget.measure(p, item_id)
            report["mode"], report["budget_bytes"] = m["mode"], m["budget_bytes"]
            report["items"].append({"item": item_id, "bytes": m["bytes"], "over_budget": m["over_budget"],
                                    "top": m["sources"][:3], "unbound_bytes": m["unbound"]["bytes"],
                                    "duplicate_bytes": m["duplicates"]["bytes"]})
        report["warnings"] = [{"code": i.code, "where": i.where, "message": i.message}
                              for i in check.check(p) if i.code in CONTEXT_WARNINGS]
        read = {str(r.get("ref")).split("#", 1)[0] for item_id in items
                for r in p.items[item_id].get("reads") or [] if isinstance(r, dict) and r.get("ref")}
        scope = {phase_id, *items}
        report["phase_documents_unread"] = sorted(
            f"knowledge/{doc_id}" for doc_id, doc in p.documents.items()
            if scope & set(doc.get("applies_to") or []) and f"knowledge/{doc_id}" not in read)
        return report
    except (PlanError, OSError) as exc:
        return {"phase": phase_id, "detailed": True, "error": str(exc), "items": [], "warnings": [],
                "phase_documents_unread": []}


def design_done(plan, phase_id: str, actor: Mapping | None = None) -> dict:
    """Mark ``phase_id`` detailed after ``check`` (as if detailed) found no error in it; returns ``design_report``."""
    from . import check  # check imports views, views imports this module

    with _mutation(plan) as (p, lock):
        root = p.root
        phase = _need_phase(p, phase_id)
        if phase.get("design") != "detailed":
            probe = copy.deepcopy(p)
            probe.phases[phase_id]["design"] = "detailed"
            errors = [i for i in check.check(probe) if i.level == "error" and i.where.startswith(f"phases/{phase_id}/")]
            if not phase_items(p, phase_id) and not errors:
                raise PlanError("DESIGN_INCOMPLETE", f"{phase_id} has no items")
            if errors:
                shown = "; ".join(f"{i.where}: {i.message}" for i in errors[:3])
                more = f" (+{len(errors) - 3} more)" if len(errors) > 3 else ""
                raise PlanError("DESIGN_INCOMPLETE", f"{len(errors)} error(s) in {phase_id}: {shown}{more}")
            doc = copy.deepcopy(phase)
            doc["design"] = "detailed"
            event = store.new_event("design_done", f"{phase_id} design done", _actor_doc(p, actor), phase=phase_id)
            _commit(p, [("phase", phase_id, doc)], [event], lock)
    return design_report(root, phase_id)


def reopen(plan, item_id: str, reason: str, actor: Mapping | None = None) -> None:
    """Terminal item -> ``todo``; clears its result and the closure of its phase (owner amendment path)."""
    with _mutation(plan) as (p, lock):
        item = copy.deepcopy(_need_item(p, item_id))
        current = item.get("status")
        if current not in {s.value for s in TERMINAL}:
            raise PlanError("NOT_TERMINAL", f"{item_id} is {current}; only a finished item can be reopened")
        if not reason or not reason.strip():
            raise PlanError("REASON_REQUIRED", "--reason is required")
        phase_id = _item_phase(item_id)
        item["status"], item["result"] = "todo", None
        changes: list[tuple[str, str | None, dict]] = [("item", item_id, item)]
        if p.phases[phase_id].get("closed"):
            phase_doc = copy.deepcopy(p.phases[phase_id])
            phase_doc["closed"] = None
            changes.append(("phase", phase_id, phase_doc))
        if p.plan.get("status") == "done":
            plan_doc = copy.deepcopy(p.plan)
            plan_doc["status"] = "active"
            changes.append(("plan", None, plan_doc))
        event = store.new_event("note", f"reopen {item_id}: {reason}", _actor_doc(p, actor), item=item_id, phase=phase_id,
                                data={"reopened_from": current})
        _commit(p, changes, [event], lock)


def archive(plan, *, force: bool = False, reason: str | None = None, actor: Mapping | None = None) -> Path:
    """Mark the plan ``archived`` and move its directory to ``plans/archive/<id>``; returns the new path."""
    with _mutation(plan) as (p, lock):
        if p.root.parent.name == store.ARCHIVE:
            raise PlanError("ALREADY_ARCHIVED", f"{p.root.name} is already under {store.ARCHIVE}/")
        if p.plan.get("status") != "done":
            if not force:
                raise PlanError("PLAN_NOT_DONE", f"plan is {p.plan.get('status')}; finish every phase or use --force --reason")
            if not reason or not reason.strip():
                raise PlanError("REASON_REQUIRED", "--force needs --reason")
        target = p.root.parent / store.ARCHIVE / p.root.name
        if target.exists():
            raise PlanError("ARCHIVE_EXISTS", f"{target} already exists")
        plan_doc = copy.deepcopy(p.plan)
        plan_doc["status"] = "archived"
        event = store.new_event("archived", f"plan {p.plan.get('short_id', p.root.name)} archived", _actor_doc(p, actor),
                                data={"forced": True, "reason": reason} if p.plan.get("status") != "done" else None)
        _commit(p, [("plan", None, plan_doc)], [event], lock)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p.root), str(target))
        p.root = target  # the views are regenerated at the new location when the mutation ends
        return target
