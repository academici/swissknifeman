"""The generated human views of a v3 plan: view-models, rendering, staleness (dossier §5, §13).

``render_all`` writes only the files whose bytes change; ``render_all(plan, check=True)`` reports the stale
ones without writing. Output is a pure function of the plan JSON and ``log.jsonl`` — no clock, no paths.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from . import store
from .model import CLASS_ORDER, EFFORT_ORDER, SATISFYING, STATUS_LABEL, TERMINAL, ItemStatus, id_sort_key
from .templating import TemplateError, render

TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "templates" / "plan"
VIEW_FILES = ("index.md", "plan.md", "roadmap.md", "status.md", "handoff.md", "open-questions.md")
GUARD_FILES = ("AGENTS.md", "CLAUDE.md")
GENERATED = VIEW_FILES + GUARD_FILES
PLAN_STATUS_LABEL = {"active": "🟡 Active", "paused": "⏸ Paused", "done": "🟢 Done", "archived": "📦 Archived"}
FRICTION_TYPES = ("blocker", "deviation", "difficulty")


def cell(value: Any) -> str:
    """Make ``value`` safe for a Markdown table cell: escape ``|`` and collapse whitespace and newlines."""
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip().replace("|", "\\|")


def line(value: Any) -> str:
    """Single-line text for headings and bullets: collapse whitespace and newlines."""
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()


def render_all(plan: store.Plan, check: bool = False) -> list[str]:
    """Render the six views and the provider guard files; return the names written (or stale, with ``check``)."""
    model = build_model(plan)
    guard = _render_template("agents", model)
    files = {name: _render_template(name.removesuffix(".md"), model) for name in VIEW_FILES}
    files.update({name: guard for name in GUARD_FILES})
    changed = []
    for name, text in files.items():
        path = plan.root / name
        try:
            current = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = None
        if current != text:
            changed.append(name)
            if not check:
                store.atomic_write(path, text)
    return changed


def _load_template(name: str) -> str:
    try:
        return (TEMPLATE_DIR / f"{name}.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise TemplateError(f"missing template {name!r}: {exc}") from exc


def _render_template(name: str, model: dict) -> str:
    text = render(_load_template(name), model, lambda partial: _load_template(f"_{partial}"))
    return text.rstrip("\n") + "\n"  # one trailing newline, whatever the last section left behind


# ---------------------------------------------------------------- scheduling (dossier §6.1, local until P2.1)

def _status(plan: store.Plan, item_id: str) -> str:
    return plan.items[item_id].get("status", "todo")


def _route(plan: store.Plan, items: list[str]) -> dict | None:
    routes = [plan.items[i].get("route") for i in items if isinstance(plan.items[i].get("route"), dict)]
    if not routes:
        return None
    return {"class": max((r.get("class") for r in routes), key=lambda c: CLASS_ORDER.index(c) if c in CLASS_ORDER else -1),
            "effort": max((r.get("effort") for r in routes), key=lambda e: EFFORT_ORDER.index(e) if e in EFFORT_ORDER else -1)}


def _granted_gates(plan: store.Plan) -> set[str]:
    """Gates with a ``gate_granted`` event whose ``data.gate`` names them."""
    return {event["data"]["gate"] for _, event, _ in store.log_lines(plan.root)
            if event and event.get("type") == "gate_granted" and isinstance(event.get("data"), dict)
            and isinstance(event["data"].get("gate"), str)}


def _phase_order(plan: store.Plan) -> list[str]:
    phases = plan.plan.get("phases")
    return [p for p in phases if p in plan.phases] if isinstance(phases, list) else []


def _batch_members(plan: store.Plan, phase_id: str, batch: dict) -> list[str]:
    declared = plan.phases[phase_id].get("items")
    order = {item: n for n, item in enumerate(declared)} if isinstance(declared, list) else {}
    members = [i for i in batch.get("items", []) if isinstance(i, str) and i in plan.items] \
        if isinstance(batch.get("items"), list) else []
    return sorted(members, key=lambda i: order.get(i, len(order)))


def _batches(plan: store.Plan, phase_id: str) -> list[dict]:
    batches = plan.phases[phase_id].get("batches")
    return [b for b in batches if isinstance(b, dict)] if isinstance(batches, list) else []


def _ready(plan: store.Plan, phase_id: str, batch: dict, granted: set[str]) -> tuple[list[str], str | None]:
    """Ready members of ``batch`` in phase order, and the first reason a member had to wait."""
    pending = [i for i in _batch_members(plan, phase_id, batch) if _status(plan, i) not in TERMINAL]
    ready: list[str] = []
    reason = None
    for item_id in pending:
        doc = plan.items[item_id]
        deps = doc.get("depends_on") if isinstance(doc.get("depends_on"), list) else []
        unmet = next((d for d in deps if d in plan.items and _status(plan, d) not in SATISFYING and d not in ready), None)
        authority = doc.get("authority") if isinstance(doc.get("authority"), dict) else {}
        if unmet is not None:
            why = (f"blocked {unmet} — {(plan.items[unmet].get('result') or {}).get('escalation') or 'no escalation text'}"
                   if _status(plan, unmet) == "blocked" else unmet)
        elif authority.get("kind") == "owner_gate" and authority.get("gate") not in granted:
            why = f"gate {authority.get('gate')}"
        else:
            ready.append(item_id)
            continue
        reason = reason or f"waiting: {why}"
    if batch.get("mode") == "required" and len(ready) != len(pending):
        return [], reason
    return ready, reason


def _next_batch(plan: store.Plan) -> dict:
    """Semantic Next of the plan (dossier §6.1): kind, exact text, target and launch lines."""
    plan_id = plan.plan.get("id", plan.root.name)

    def result(kind: str, exact: str, **extra) -> dict:
        data = {"kind": kind, "exact": exact, "phase": None, "batch": None, "items": [], "route": None, "launch": None}
        data.update(extra)
        return data

    order = _phase_order(plan)
    if not order:
        return result("waiting", "waiting: no phases yet (add-phase)")
    granted = _granted_gates(plan)
    for index, phase_id in enumerate(order):
        phase = plan.phases[phase_id]
        if phase.get("closed"):
            continue
        deps = phase.get("depends_on") if isinstance(phase.get("depends_on"), list) else ([order[index - 1]] if index else [])
        unmet = [d for d in deps if d in plan.phases and not plan.phases[d].get("closed")]
        if unmet:
            return result("waiting", f"waiting: {unmet[0]}", phase=phase_id)
        if phase.get("design") != "detailed":
            command = f"task:plan-design {plan_id} {phase_id}"
            return result("design-phase", f"design-phase: {command}", phase=phase_id,
                          launch={"claude": f"/{command}", "codex": f"$ {command}"})
        for batch in _batches(plan, phase_id):
            members = _batch_members(plan, phase_id, batch)
            if all(_status(plan, i) in TERMINAL for i in members):
                continue
            ready, reason = _ready(plan, phase_id, batch, granted)
            if not ready:
                return result("waiting", reason or f"waiting: batch {batch.get('id')}", phase=phase_id, batch=batch.get("id"))
            command = f"task:plan-run {plan_id} {' '.join(ready)}"
            return result("run-items", f"run-items: {command}", phase=phase_id, batch=batch.get("id"), items=ready,
                          route=_route(plan, ready), launch={"claude": f"/{command}", "codex": f"$ {command}"})
        return result("waiting", f"waiting: {phase_id} closure (finish the last item)", phase=phase_id)
    if plan.plan.get("status") != "archived":
        command = f"task:plan-close {plan_id} archive"
        return result("archive", f"archive: {command}", launch={"claude": f"/{command}", "codex": f"$ {command}"})
    return result("terminal", "terminal: plan done")


def _batch_state(plan: store.Plan, phase_id: str, batch: dict, frontier: dict, granted: set[str]) -> str:
    members = _batch_members(plan, phase_id, batch)
    if plan.phases[phase_id].get("design") != "detailed":
        return "design-required"
    if members and all(_status(plan, i) in TERMINAL for i in members):
        return "done"
    if any(_status(plan, i) == "in_progress" for i in members):
        return "in progress"
    if frontier["kind"] == "run-items" and (frontier["phase"], frontier["batch"]) == (phase_id, batch.get("id")):
        return "ready"
    order = _phase_order(plan)
    deps = plan.phases[phase_id].get("depends_on")
    deps = deps if isinstance(deps, list) else ([order[order.index(phase_id) - 1]] if order.index(phase_id) else [])
    for dep in deps:
        if dep in plan.phases and not plan.phases[dep].get("closed"):
            return f"waiting: {dep}"
    for earlier in _batches(plan, phase_id):
        if earlier is batch:
            break
        if any(_status(plan, i) not in TERMINAL for i in _batch_members(plan, phase_id, earlier)):
            return f"waiting: {earlier.get('id')}"
    _, reason = _ready(plan, phase_id, batch, granted)
    return reason or "waiting"


# ---------------------------------------------------------------- view-model

def _natural(identifier: str) -> tuple:
    try:
        return (0, id_sort_key(identifier))
    except ValueError:
        return (1, identifier)


def _item_label(status: str) -> str:
    try:
        return STATUS_LABEL[ItemStatus(status)]
    except ValueError:
        return str(status)


def _route_text(route: Any) -> str:
    return f"{route.get('class')}/{route.get('effort')}" if isinstance(route, dict) else ""


def _phase_label(plan: store.Plan, phase_id: str) -> str:
    phase = plan.phases[phase_id]
    closed = phase.get("closed")
    if isinstance(closed, dict):
        return _item_label(closed.get("result", ""))
    if phase.get("design") != "detailed":
        return "⬜ Skeleton"
    statuses = [_status(plan, i) for i in _phase_items(plan, phase_id)]
    return "🟡 In progress" if any(s != "todo" for s in statuses) else "⬜ Not started"


def _phase_items(plan: store.Plan, phase_id: str) -> list[str]:
    declared = plan.phases[phase_id].get("items")
    return [i for i in declared if isinstance(i, str) and i in plan.items] if isinstance(declared, list) else []


def _strings(value: Any) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _actor_text(actor: Any) -> str:
    if not isinstance(actor, dict):
        return ""
    return "/".join(str(actor[k]) for k in ("provider", "model", "effort") if actor.get(k))


def build_model(plan: store.Plan) -> dict:
    """Plain dict with every pre-formatted value the templates need."""
    doc = plan.plan
    order = _phase_order(plan)
    phases, all_items = [], []
    for phase_id in order:
        phase = plan.phases[phase_id]
        items = _phase_items(plan, phase_id)
        all_items += items
        done = sum(1 for i in items if _status(plan, i) in SATISFYING)
        closed = phase.get("closed")
        phases.append({
            "id": phase_id, "title": line(phase.get("title")), "title_cell": cell(phase.get("title")), "design": phase.get("design", ""),
            "progress": f"{done}/{len(items)}", "status_label": _phase_label(plan, phase_id),
            "path": f"phases/{phase_id}/phase.json",
            "closed": {"at": closed.get("at", ""), "result_label": _item_label(closed.get("result", "")),
                       "summary": closed.get("summary", "")} if isinstance(closed, dict) else None,
            "items": [{"id": i, "title": cell(plan.items[i].get("title")), "status_label": _item_label(_status(plan, i)),
                       "route": _route_text(plan.items[i].get("route")), "updated": plan.items[i].get("updated_at", "")}
                      for i in items],
        })
    done_total = sum(1 for i in all_items if _status(plan, i) in SATISFYING)
    frontier = _next_batch(plan)
    granted = _granted_gates(plan)
    batches, number = [], 0
    for phase_id in order:
        for batch in _batches(plan, phase_id):
            number += 1
            members = _batch_members(plan, phase_id, batch)
            route = _route(plan, members)
            batches.append({
                "n": number, "phase": phase_id, "batch": cell(batch.get("id")),
                "command": f"task:plan-run {doc.get('id', plan.root.name)} {' '.join(members)}",
                "route": _route_text(route), "state": cell(_batch_state(plan, phase_id, batch, frontier, granted)),
            })
    decisions = [(k, d) for k, d in plan.decisions.items()]
    open_questions = [(k, d) for k, d in decisions if d.get("status") == "open"]
    blocked = [i for i in all_items if _status(plan, i) == "blocked"]
    events = [event for _, event, _ in store.log_lines(plan.root) if event]
    cutoff = max((n for n, e in enumerate(events) if e.get("type") == "phase_closed"), default=-1)
    finished = sorted((i for i in all_items if _status(plan, i) in TERMINAL and _status(plan, i) != "blocked"),
                      key=lambda i: ((plan.items[i].get("result") or {}).get("finished_at", ""), _natural(i)), reverse=True)[:5]
    contracts = doc.get("contracts") if isinstance(doc.get("contracts"), dict) else {}
    exported = [c for c in contracts.get("exported", []) if isinstance(c, dict)] if isinstance(contracts.get("exported"), list) else []
    consumed = [c for c in contracts.get("consumed", []) if isinstance(c, dict)] if isinstance(contracts.get("consumed"), list) else []
    settings = doc.get("settings") if isinstance(doc.get("settings"), dict) else {}
    return {
        "id": doc.get("id", plan.root.name), "short_id": doc.get("short_id", ""), "title": line(doc.get("title")),
        "status_label": PLAN_STATUS_LABEL.get(doc.get("status"), str(doc.get("status", ""))),
        "goal": doc.get("goal", ""), "context": doc.get("context", ""),
        "meta": [{"key": key, "value": cell(value)} for key, value in (
            ("Plan ID", doc.get("id")), ("Short ID", doc.get("short_id")), ("Title", doc.get("title")), ("Layout", "v3"),
            ("Status", doc.get("status")), ("Repository", doc.get("repository")), ("Owner", doc.get("owner")),
            ("Authoring Model", _actor_text(doc.get("authoring"))), ("Design Audit", settings.get("design_audit")))],
        "has_non_goals": bool(_strings(doc.get("non_goals"))), "non_goals": _strings(doc.get("non_goals")),
        "has_rules": bool(_strings(doc.get("rules"))), "rules": _strings(doc.get("rules")),
        "has_contracts": bool(exported or consumed),
        "exported": [{k: cell(c.get(k)) for k in ("name", "version", "status", "consumers")} for c in exported],
        "consumed": [{k: cell(c.get(k)) for k in ("name", "donor", "pinned", "reaction")} for c in consumed],
        "phases": phases, "batches": batches,
        "decisions": [{"id": k, "title": cell(d.get("title")), "status": d.get("status", ""), "date": d.get("date", "")}
                      for k, d in decisions],
        "totals": {"done": done_total, "total": len(all_items)},
        "updated": str(doc.get("updated_at", ""))[:10], "date": str(doc.get("updated_at", ""))[:10],
        "next": {"exact": frontier["exact"], "has_launch": bool(frontier["launch"]),
                 "claude": (frontier["launch"] or {}).get("claude", ""), "codex": (frontier["launch"] or {}).get("codex", "")},
        "finished": [{"id": i, "status_label": _item_label(_status(plan, i)),
                      "notes": line(((plan.items[i].get("result") or {}).get("notes")) or plan.items[i].get("title"))}
                     for i in finished],
        "friction": [{"ts": e.get("ts", ""), "type": e.get("type", ""), "target": e.get("item") or e.get("phase") or "plan",
                      "summary": line(e.get("summary")), "follow_up": line(e.get("next"))}
                     for e in events[cutoff + 1:] if e.get("type") in FRICTION_TYPES],
        "question_count": len(open_questions),
        "questions": [{"id": k, "title": line(d.get("title")), "question": d.get("question", ""),
                       "options": [{"id": o.get("id", ""), "text": line(o.get("text"))} for o in d.get("options", [])
                                   if isinstance(o, dict)] if isinstance(d.get("options"), list) else [],
                       "applies": ", ".join(_strings(d.get("applies_to")))} for k, d in open_questions],
        "blocked": {"items": [{"id": i, "title": line(plan.items[i].get("title")),
                               "escalation": line((plan.items[i].get("result") or {}).get("escalation") or "no escalation text")}
                              for i in blocked]} if blocked else None,
    }
