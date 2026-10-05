"""The generated human views of a v3 plan: view-models, rendering, staleness (dossier §5, §13).

``render_all`` writes only the files whose bytes change; ``render_all(plan, check=True)`` reports the stale
ones without writing. Output is a pure function of the plan JSON and ``log.jsonl`` — no clock, no paths.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from . import lifecycle, store
from .model import SATISFYING, STATUS_LABEL, TERMINAL, ItemStatus, id_sort_key
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
    statuses = [lifecycle.status_of(plan, i) for i in lifecycle.phase_items(plan, phase_id)]
    return "🟡 In progress" if any(s != "todo" for s in statuses) else "⬜ Not started"


def _strings(value: Any) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _actor_text(actor: Any) -> str:
    if not isinstance(actor, dict):
        return ""
    return "/".join(str(actor[k]) for k in ("provider", "model", "effort") if actor.get(k))


def build_model(plan: store.Plan) -> dict:
    """Plain dict with every pre-formatted value the templates need."""
    doc = plan.plan
    order = lifecycle.phase_order(plan)
    phases, all_items = [], []
    for phase_id in order:
        phase = plan.phases[phase_id]
        items = lifecycle.phase_items(plan, phase_id)
        all_items += items
        done = sum(1 for i in items if lifecycle.status_of(plan, i) in SATISFYING)
        closed = phase.get("closed")
        phases.append({
            "id": phase_id, "title": line(phase.get("title")), "title_cell": cell(phase.get("title")), "design": phase.get("design", ""),
            "progress": f"{done}/{len(items)}", "status_label": _phase_label(plan, phase_id),
            "path": f"phases/{phase_id}/phase.json",
            "closed": {"at": closed.get("at", ""), "result_label": _item_label(closed.get("result", "")),
                       "summary": closed.get("summary", "")} if isinstance(closed, dict) else None,
            "items": [{"id": i, "title": cell(plan.items[i].get("title")), "status_label": _item_label(lifecycle.status_of(plan, i)),
                       "route": _route_text(plan.items[i].get("route")), "updated": plan.items[i].get("updated_at", "")}
                      for i in items],
        })
    done_total = sum(1 for i in all_items if lifecycle.status_of(plan, i) in SATISFYING)
    granted = lifecycle.granted_gates(plan)
    frontier = lifecycle.next(plan, granted=granted)
    batches, number = [], 0
    for phase_id in order:
        for batch in lifecycle.batches_of(plan, phase_id):
            number += 1
            members = lifecycle.batch_members(plan, phase_id, batch)
            route = lifecycle.route_of(plan, members)
            batches.append({
                "n": number, "phase": phase_id, "batch": cell(batch.get("id")),
                "command": f"task:plan-run {doc.get('id', plan.root.name)} {' '.join(members)}",
                "route": _route_text(route), "state": cell(lifecycle.batch_state(plan, phase_id, batch, frontier, granted)),
            })
    decisions = [(k, d) for k, d in plan.decisions.items()]
    open_questions = [(k, d) for k, d in decisions if d.get("status") == "open"]
    blocked = [i for i in all_items if lifecycle.status_of(plan, i) == "blocked"]
    events = [event for _, event, _ in store.log_lines(plan.root) if event]
    cutoff = max((n for n, e in enumerate(events) if e.get("type") == "phase_closed"), default=-1)
    finished = sorted((i for i in all_items if lifecycle.status_of(plan, i) in TERMINAL and lifecycle.status_of(plan, i) != "blocked"),
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
            ("Plan ID", doc.get("id")), ("Short ID", doc.get("short_id")), ("Title", doc.get("title")),
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
        "next": {"exact": frontier.exact, "has_launch": bool(frontier.launch),
                 "claude": (frontier.launch or {}).get("claude", ""), "codex": (frontier.launch or {}).get("codex", "")},
        "finished": [{"id": i, "status_label": _item_label(lifecycle.status_of(plan, i)),
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
