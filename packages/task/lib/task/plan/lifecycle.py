"""Lifecycle of a v3 plan: semantic Next and the verbs that move items, phases and the plan (dossier §6).

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
from pathlib import Path
import re
import shutil
from typing import Any, Iterable, Iterator, Mapping

from task.command_catalog import load_routing_metadata

from . import store
from .model import (CLASS_ORDER, EFFORT_ORDER, ITEM_ID, PHASE_ID, SATISFYING, TERMINAL, ItemStatus, PlanError,
                    id_sort_key, parse_ref, phase_status)

ROUTING_PATH = Path(__file__).resolve().parents[3] / "configs" / "command-routing.json"
FRICTION_TYPES = ("deviation", "blocker", "difficulty", "assumption", "note")
FINISH_STATUSES = ("done", "done_with_deviations", "blocked", "skipped")
_OPTION_ID = re.compile(r"^[A-Z]$")
_GATE = re.compile(r"^[A-Z0-9-]+$")


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
    return {"class": max((r.get("class") for r in routes), key=lambda c: _rank(CLASS_ORDER, c)),
            "effort": max((r.get("effort") for r in routes), key=lambda e: _rank(EFFORT_ORDER, e))}


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
    if authority.get("kind") == "owner_gate" and authority.get("gate") not in granted:
        return f"gate {authority.get('gate')}"
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
            return Next("design-phase", phase=phase_id, command=f"task:plan-design {plan_id} {phase_id}")
        for batch in batches_of(plan, phase_id):
            members = batch_members(plan, phase_id, batch)
            if all(status_of(plan, i) in TERMINAL for i in members):
                continue
            ready, reason = ready_members(plan, phase_id, batch, granted)
            if not ready:
                return Next("waiting", reason or f"batch {batch.get('id')}", phase=phase_id, batch=batch.get("id"))
            return Next("run-items", phase=phase_id, batch=batch.get("id"), items=tuple(ready),
                        route=route_of(plan, ready), command=f"task:plan-run {plan_id} {' '.join(ready)}")
        return Next("waiting", f"{phase_id} closure (finish the last item)", phase=phase_id)
    if blocked_phase is not None:
        blocked = first_blocked(plan, blocked_phase)
        return Next("waiting", _blocked_text(plan, blocked), phase=blocked_phase)
    if plan.plan.get("status") != "archived":
        return Next("archive", command=f"task:plan-close {plan_id} archive")
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
    with store.PlanLock(root) as lock:
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
            {"phase": p.phases, "item": p.items, "decision": p.decisions}[kind][key] = doc
    for event in events:
        store.append_log(p.root, event, lock=lock)


def _actor_doc(p: store.Plan, actor: Mapping | None, item: str | None = None) -> dict:
    """The acting identity: explicit, else the item's executor, else the plan's authoring actor."""
    if actor:
        return dict(actor)
    executor = (p.items[item].get("result") or {}).get("executor") if item in p.items else None
    if isinstance(executor, dict):
        return dict(executor)
    authoring = p.plan.get("authoring")
    return dict(authoring) if isinstance(authoring, dict) else {"provider": "unknown", "model": "unknown"}


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


def start(plan, items: Iterable[str], actor: Mapping, *, grants: Iterable[str] = (),
          scout: bool | None = None) -> StartResult:
    """Move ``items`` (one detailed phase) to ``in_progress``; an ``in_progress`` item is resumed.

    ``scout`` asks the provider's weak model for a context map after the start (D3); ``None`` follows
    ``plan.settings.scout``. A scout failure never fails the start.
    """
    requested = list(items)
    grants = list(grants)
    with _mutation(plan) as (p, lock):
        actor = {k: v for k, v in dict(actor).items() if v}
        if not actor.get("provider") or not actor.get("model"):
            raise PlanError("ACTOR_REQUIRED", "start needs --actor PROVIDER/MODEL[/EFFORT]")
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
        for dep in _phase_deps(p, phase_id):
            if not p.phases[dep].get("closed"):
                raise PlanError("DEPENDENCY_NOT_READY", f"phase {phase_id} waits for phase {dep}")
            if p.phases[dep]["closed"].get("result") == "blocked":
                raise PlanError("DEPENDENCY_NOT_READY", f"phase {dep} is closed as blocked")
        for position, item_id in enumerate(requested):
            unmet = _unmet_dependency(p, item_id, requested[:position])
            if unmet:
                raise PlanError("DEPENDENCY_NOT_READY", f"{item_id} waits for {unmet}")
        known_gates = {(d.get("authority") or {}).get("gate") for d in p.items.values()
                       if (d.get("authority") or {}).get("kind") == "owner_gate"}
        for gate in grants:
            if gate not in known_gates:
                raise PlanError("GATE_UNKNOWN", f"no item declares owner gate {gate!r}")
        granted = granted_gates(p) | set(grants)
        for item_id in requested:
            wait = _gate_wait(p, item_id, granted)
            if wait:
                raise PlanError("GATE_NOT_GRANTED", f"{item_id} needs {wait} (plan.py grant, or start --grant)")
        verdict = _route_verdict(p, requested, actor)
        from . import context  # context imports this module for scheduling

        missing = [f"{i}: {path}" for i in requested for path in context.missing_reads(p, i)]
        if missing:
            raise PlanError("READ_MISSING", f"required read(s) missing — {'; '.join(missing)}")

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
            events.append(store.new_event(
                "start", f"start {item_id}" + (f" (batch {batch_id})" if batch_id else ""), actor,
                item=item_id, phase=phase_id, data={"requested": requested, "route": verdict}))
        _commit(p, changes, gate_events + events, lock)
        packs = tuple(context.build(p, item_id) for item_id in requested)
        result = StartResult(tuple(requested), phase_id, next_batch_id(p, phase_id, requested[0]), verdict,
                             tuple(resumed), packs)
        wanted = (p.plan.get("settings") or {}).get("scout") == "auto" if scout is None else scout
        root = p.root
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

    def text(self) -> str:
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


def _closure_summary(statuses: list[str]) -> str:
    counts = [(s.value, statuses.count(s.value)) for s in ItemStatus if statuses.count(s.value)]
    return f"{len(statuses)} item(s): " + ", ".join(f"{n} {name}" for name, n in counts)


def finish(plan, item_id: str, status: str, *, notes: str = "", checks: Mapping[str, int] | None = None,
           deviations: Iterable[str] = (), pending: Iterable[str] = (), escalation: str | None = None,
           commits: Iterable[str] = (), decision: str | None = None, actor: Mapping | None = None) -> FinishResult:
    """Record the outcome of ``item_id``; closes the phase, and the plan, when it was the last open piece."""
    checks, deviations, pending, commits = dict(checks or {}), list(deviations), list(pending), list(commits)
    with _mutation(plan) as (p, lock):
        item = copy.deepcopy(_need_item(p, item_id))
        if status not in FINISH_STATUSES:
            raise PlanError("STATUS_INVALID", f"status must be one of {', '.join(FINISH_STATUSES)}")
        current = item.get("status", "todo")
        if current != "in_progress" and not (status == "skipped" and current == "todo"):
            raise PlanError("NOT_STARTED", f"{item_id} is {current}; start it first"
                                           + (" (use reopen to redo a finished item)" if current in TERMINAL else ""))
        phase_id = _item_phase(item_id)
        known = {c["id"] for c in item.get("validation", []) if isinstance(c, dict)}
        known |= {c["id"] for c in p.phases[phase_id].get("validation", []) if isinstance(c, dict)}
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

        now = store.now()
        prior = item.get("result") if isinstance(item.get("result"), dict) else {}
        result = {key: prior[key] for key in ("started_at", "executor") if key in prior}
        result["finished_at"] = now
        for key, value in (("notes", notes), ("deviations", deviations), ("pending", pending),
                           ("escalation", escalation), ("commits", commits), ("decision", decision)):
            if value:
                result[key] = value
        ordered = sorted(recorded, key=id_sort_key)
        stamped = {c["id"]: c["at"] for c in prior.get("checks", []) if isinstance(c, dict) and "id" in c}
        stamped.update({i: now for i in checks})
        if recorded:
            result["checks"] = [{"id": i, "exit": recorded[i], "at": stamped.get(i, now)} for i in ordered]
        item["status"], item["result"] = status, result
        actor_doc = _actor_doc(p, actor, item_id)
        changes: list[tuple[str, str | None, dict]] = [("item", item_id, item)]
        events = [store.new_event("finish", f"{item_id} {status}", actor_doc, item=item_id, phase=phase_id,
                                  data={"status": status, "checks": {i: recorded[i] for i in ordered}})]

        after = {**{i: status_of(p, i) for i in phase_items(p, phase_id)}, item_id: status}
        closure = phase_status(after.values())
        plan_done = False
        if closure is not None:
            phase_doc = copy.deepcopy(p.phases[phase_id])
            phase_doc["closed"] = {"at": now, "result": closure, "summary": _closure_summary(list(after.values()))}
            changes.append(("phase", phase_id, phase_doc))
            events.append(store.new_event("phase_closed", f"{phase_id} closed: {closure}", actor_doc, phase=phase_id,
                                          data={"result": closure}))
            results = {pid: (phase_doc if pid == phase_id else p.phases[pid]).get("closed") for pid in phase_order(p)}
            if all(isinstance(c, dict) and c.get("result") != "blocked" for c in results.values()):
                plan_doc = copy.deepcopy(p.plan)
                plan_doc["status"] = "done"
                changes.append(("plan", None, plan_doc))
                plan_done = True
        _commit(p, changes, events, lock)
        return FinishResult(item_id, status, closure, plan_done, next(p))


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
        if not any((d.get("authority") or {}).get("gate") == gate for d in p.items.values()):
            raise PlanError("GATE_UNKNOWN", f"no item declares owner gate {gate!r}")
        if gate not in granted_gates(p):
            event = store.new_event("gate_granted", f"gate {gate} granted", _actor_doc(p, actor),
                                    data={"gate": gate, "note": note})
            _commit(p, [], [event], lock)
        return next(p)


# ---------------------------------------------------------------- design-done, reopen, archive

def design_done(plan, phase_id: str, actor: Mapping | None = None) -> None:
    """Mark ``phase_id`` detailed after ``check`` (as if detailed) found no error in it."""
    from . import check  # check imports views, views imports this module

    with _mutation(plan) as (p, lock):
        phase = _need_phase(p, phase_id)
        if phase.get("design") == "detailed":
            return
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
