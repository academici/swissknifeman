"""The generated human views of a v4 plan: view-models, rendering, staleness (dossier §5, §13).

``render_all`` writes only the files whose bytes change; ``render_all(plan, check=True)`` reports the stale
ones without writing. Output is a pure function of the plan JSON and ``log.jsonl`` — no clock, no paths.
"""
from __future__ import annotations

from pathlib import Path
import json
import re
import sys
from typing import Any

from .. import COMMAND_NAMESPACE
from . import lifecycle, store
from . import settings as plan_config
from .model import SATISFYING, STATUS_LABEL, TERMINAL, ItemStatus, id_sort_key
from .templating import TemplateError, render

TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "templates" / "plan"
VIEW_FILES = ("index.md", "plan.md", "roadmap.md", "status.md", "handoff.md", "open-questions.md")
VIEW_DIR = "views"
GENERATED = tuple(f"{VIEW_DIR}/{name}" for name in VIEW_FILES)
PLAN_STATUS_LABEL = {"active": "🟡 Active", "paused": "⏸ Paused", "done": "🟢 Done", "archived": "📦 Archived"}
FRICTION_TYPES = ("blocker", "deviation", "difficulty")


def cell(value: Any) -> str:
    """Make ``value`` safe for a Markdown table cell: escape ``|`` and collapse whitespace and newlines."""
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip().replace("|", "\\|")


def line(value: Any) -> str:
    """Single-line text for headings and bullets: collapse whitespace and newlines."""
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()


def render_all(plan: store.Plan, check: bool = False) -> list[str]:
    """Render human views. Never create agent instruction files inside a plan."""
    model = build_model(plan)
    overrides = _override_dir(plan)
    files = {f"{VIEW_DIR}/{name}": _render_template(name.removesuffix(".md"), model, overrides)
             for name in VIEW_FILES}
    documents = [("brief", "brief.json", plan.brief)]
    for kind, table in (("phase", plan.phases), ("item", plan.items), ("unit", plan.units),
                        ("decision", plan.decisions), ("document", plan.documents)):
        documents += [(kind, plan.path(kind, key).relative_to(plan.root).as_posix(), doc) for key, doc in table.items()]
    for kind, source, doc in documents:
        doc = json.loads(store.canonical_dump(doc, kind))
        name = f"{VIEW_DIR}/{source.removesuffix('.json')}.md"
        fields = []
        for key, value in doc.items():
            if key in ("$schema", "id", "title", "sections") or value is None:
                continue
            if isinstance(value, str):
                body = value
            elif isinstance(value, list) and all(isinstance(v, str) for v in value):
                body = "\n".join(f"- {v}" for v in value)
            else:
                body = "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"
            fields.append({"title": key.replace("_", " ").capitalize(), "body": body})
        fields += [{"title": s["title"], "body": s["text"]} for s in doc.get("sections", [])]
        relative = "../" * len(Path(source).parts) + source
        files[name] = _render_template("document", {"title": doc.get("title", "Owner brief"),
                                                    "source": relative, "fields": fields}, overrides)
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
    expected = set(files)
    for path in sorted((plan.root / VIEW_DIR).rglob("*.md")):
        name = path.relative_to(plan.root).as_posix()
        if name not in expected:
            changed.append(name)
            if not check:
                path.unlink()
    return changed


_WARNED: set = set()


def _warn_once(code: str, subject: str, message: str) -> None:
    if (code, subject) not in _WARNED:
        _WARNED.add((code, subject))
        print(f"warning: {code}: {message}", file=sys.stderr)


def _override_dir(plan: store.Plan) -> Path | None:
    """The folder of replacement templates (``views.templates_dir``), or None for the built-in templates only."""
    folder = plan_config.for_plan(plan).path("views.templates_dir")
    if folder is None:
        return None
    if not folder.is_dir():
        _warn_once("VIEW_TEMPLATES_MISSING", str(folder),
                   f"views.templates_dir {str(folder)!r} is not a folder; using the built-in templates")
        return None
    for path in sorted(folder.glob("*.md")):
        if not (TEMPLATE_DIR / path.name).is_file():
            _warn_once("VIEW_TEMPLATE_UNKNOWN", str(path),
                       f"{path.name} in {str(folder)!r} replaces no built-in template and is ignored")
    return folder


def _load_template(name: str, overrides: Path | None = None) -> str:
    for folder in (overrides, TEMPLATE_DIR):
        if folder is None or not (folder / f"{name}.md").is_file():
            continue
        try:
            return (folder / f"{name}.md").read_text(encoding="utf-8")
        except OSError as exc:
            raise TemplateError(f"missing template {name!r}: {exc}") from exc
    raise TemplateError(f"missing template {name!r}: {TEMPLATE_DIR / (name + '.md')}")


def _render_template(name: str, model: dict, overrides: Path | None = None) -> str:
    text = render(_load_template(name, overrides), model, lambda partial: _load_template(f"_{partial}", overrides))
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


def _review_text(plan: store.Plan, members: list) -> str:
    """What the plan says of the review of these pieces: per mode, and who reads them when it is requested."""
    modes: dict = {}
    for item_id in members:
        review = plan.items[item_id].get("review")
        review = review if isinstance(review, dict) else {}
        reviewer = review.get("reviewer") if isinstance(review.get("reviewer"), dict) else {}
        who = "/".join(str(reviewer[k]) for k in ("provider", "model", "effort") if reviewer.get(k)) or str(reviewer.get("class") or "")
        label = str(review.get("mode") or "unset") + (f" {who}" if who and review.get("mode") == "requested" else "")
        modes.setdefault(label, []).append(item_id)
    return "; ".join(f"{label} ({', '.join(ids)})" if len(modes) > 1 else label for label, ids in modes.items())


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
            "path": f"phases/{phase_id}/phase.md",
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
                "command": f"{COMMAND_NAMESPACE}:plan-run {doc.get('id', plan.root.name)} {' '.join(members)}",
                "route": _route_text(route), "review": cell(_review_text(plan, members)), "state": cell(lifecycle.batch_state(plan, phase_id, batch, frontier, granted)),
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
            ("Pause", (doc.get("pause") or {}).get("reason") if isinstance(doc.get("pause"), dict) else None),
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
