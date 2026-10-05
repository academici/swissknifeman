"""Authoring mutations of a v3 plan: create, add phase/item/decision, merge-patch, push, batches.

Each mutation is lock -> load fresh snapshot -> change -> validate every changed document -> save ->
regenerate views. A refused mutation leaves every file byte-identical. ``plan`` is a ``store.Plan``
(refreshed in place after the mutation), a plan directory path or a plan reference.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
from datetime import date as _date
from importlib.util import find_spec
from pathlib import Path
import re
from typing import Any, Iterator

from . import store
from .model import PHASE_ID, PLAN_ID, SHORT_ID, PlanError, parse_ref

_DIR_ID = re.compile(r"^(\d{4}\.\d{2}\.\d{2})-№([1-9][0-9]*)-[A-Z][A-Z0-9-]*$", re.ASCII)
_SHORT_ROW = re.compile(r"^\s*\|\s*Short ID\s*\|\s*(PLAN[1-9][0-9]*)\s*\|\s*$")
_UNIT_REF = re.compile(r"^(P[0-9]+\.[0-9]+)/(U[0-9]+)$")
_PLAN_TITLE_PREFIX = re.compile(r"^Plan №[1-9][0-9]* —")
DEFAULT_ROUTE = {"class": "implementation", "effort": "high"}

# Top-level fields no authoring verb may change: identity and lifecycle-owned state.
OWNED_FIELDS = {
    "plan": frozenset({"$schema", "id", "short_id", "created", "updated_at", "status"}),
    "brief": frozenset({"$schema"}),
    "phase": frozenset({"$schema", "id", "design", "closed"}),
    "item": frozenset({"$schema", "id", "status", "result", "updated_at"}),
    "unit": frozenset({"$schema", "id", "item", "status", "outcome", "updated_at"}),
    "decision": frozenset({"$schema", "id"}),
}
GITIGNORE = "context/\n.lock\n"


def _schema_const(kind: str) -> str:
    return f"urn:swissknifeman:task:plan:{kind}:v1"


def _after_mutation(plan: store.Plan) -> None:
    """Regenerate the human views; ``views.py`` arrives with P1.3, until then this is a no-op."""
    if find_spec("task.plan.views") is None:
        return
    from . import views
    views.render_all(plan)


@contextmanager
def _mutation(plan) -> Iterator[store.Plan]:
    root = plan.root if isinstance(plan, store.Plan) else store.resolve_plan_dir(plan)
    with store.PlanLock(root):
        fresh = store.load_plan(root)
        yield fresh
        _after_mutation(fresh)  # reached only when the body did not raise
    if isinstance(plan, store.Plan):
        plan.adopt(fresh)


def _commit(p: store.Plan, changes: list[tuple[str, str | None, dict]]) -> None:
    """Validate and save ``(kind, key, doc)`` changes together, then fold them into the snapshot."""
    store.save_many([(p.path(kind, key), doc, kind) for kind, key, doc in changes])
    for kind, key, doc in changes:
        if kind in ("plan", "brief"):
            setattr(p, kind, doc)
        else:
            {"phase": p.phases, "item": p.items, "decision": p.decisions, "unit": p.units}[kind][key] = doc


def _guard_owned(kind: str, keys) -> None:
    owned = sorted(set(keys) & OWNED_FIELDS[kind])
    if owned:
        raise PlanError("FIELD_OWNED", f"{', '.join(owned)} of a {kind} is identity or lifecycle-owned; "
                                       "use the lifecycle verbs")


def merge_patch(target: Any, patch: Any) -> Any:
    """RFC 7386 JSON merge patch; ``null`` deletes a key. Returns a new value."""
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    result = copy.deepcopy(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = merge_patch(result.get(key), value)
    return result


def _next_number(prefix: str, ids) -> int:
    pattern = re.compile(rf"^{re.escape(prefix)}([0-9]+)$")
    return max((int(m[1]) for m in map(pattern.match, ids) if m), default=0) + 1


# ---------------------------------------------------------------- new plan

def _identities(plans_root: Path) -> list[dict]:
    """One row per distinct plan directory in ``plans/`` and ``plans/archive/``: id and Short ID.

    A v3 ``plan.json`` carries ``short_id``; a v2 plan still carries the ``| Short ID | PLAN<N> |`` row.
    """
    rows: dict[str, dict] = {}
    for path in store.plan_dirs(plans_root):
        row = rows.setdefault(path.name, {"id": path.name, "short_id": None})
        if row["short_id"] is None:
            row["short_id"] = store.short_id_of(path) or _v2_short_id(path / "plan.md")
    return list(rows.values())


def _v2_short_id(plan_md: Path) -> str | None:
    try:
        lines = plan_md.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    for line in lines[:60]:
        match = _SHORT_ROW.match(line)
        if match:
            return match.group(1)
    return None


def new_plan(codename: str | None, title: str, *, plans_root: str | Path, repository: str, owner: str,
             authoring: dict, message: str, date: str | None = None, message_date: str | None = None,
             plan_id: str | None = None, short_id: str | None = None, channel: str | None = None) -> store.Plan:
    """Create plan.json, brief.json, .gitignore and log.jsonl for a new plan, or adopt an explicit identity.

    Without ``plan_id``/``short_id`` the identity is allocated like ``plan_numbering.next_identity``: the
    next ``№N`` of the day and the next ``PLAN<N>`` above every live and archived plan. Explicit values
    adopt an existing identity (migration); the directory may already hold a v2 plan but never a plan.json.
    """
    plans_root = Path(plans_root)
    if not isinstance(message, str) or not message.strip():
        raise PlanError("MESSAGE_REQUIRED", "the first owner message is required (brief.messages needs one)")
    date = date or _date.today().strftime("%Y.%m.%d")
    if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", date):
        raise PlanError("PLAN_DATE_INVALID", f"expected YYYY.MM.DD, received {date!r}")
    rows = _identities(plans_root)
    ordinal = max((int(m[2]) for row in rows if (m := _DIR_ID.match(row["id"])) and m[1] == date), default=0) + 1
    if plan_id is None:
        if codename is None or not re.fullmatch(r"[A-Z][A-Z0-9-]*", codename):
            raise PlanError("PLAN_CODENAME_INVALID", f"code name must match [A-Z][A-Z0-9-]*, received {codename!r}")
        plan_id = f"{date}-№{ordinal}-{codename}"
        if any(row["id"] == plan_id for row in rows):
            raise PlanError("PLAN_EXISTS", f"plan {plan_id} already exists")
        if not _PLAN_TITLE_PREFIX.match(title):
            title = f"Plan №{ordinal} — {title}"
    elif not PLAN_ID.fullmatch(plan_id):
        raise PlanError("PLAN_ID_INVALID", f"invalid plan id {plan_id!r}")
    if short_id is None:
        taken = [int(row["short_id"][4:]) for row in rows if row["short_id"]]
        short_id = f"PLAN{max(taken, default=0) + 1}"
    elif not SHORT_ID.fullmatch(short_id):
        raise PlanError("SHORT_ID_INVALID", f"invalid short id {short_id!r}")
    clash = [row["id"] for row in rows if row["short_id"] == short_id and row["id"] != plan_id]
    if clash:
        raise PlanError("SHORT_ID_TAKEN", f"{short_id} already belongs to {clash[0]}")
    root = plans_root / plan_id
    if (root / "plan.json").exists():
        raise PlanError("PLAN_EXISTS", f"{root} already holds a v3 plan")

    created = date.replace(".", "-")
    plan_doc = {
        "$schema": _schema_const("plan"), "id": plan_id, "short_id": short_id, "title": title, "status": "active",
        "created": created, "updated_at": store.now(), "repository": repository, "owner": owner,
        "authoring": copy.deepcopy(authoring), "goal": title, "context": title, "phases": [],
        "settings": {"design_audit": "none", "scout": "off"},
    }
    brief_message = {"id": "M1", "date": message_date or created, "text": message}
    if channel:
        brief_message["channel"] = channel
    brief_doc = {"$schema": _schema_const("brief"), "messages": [brief_message], "requirements": []}
    event = store.new_event("plan_created", f"plan {short_id} created", authoring, data={"plan_id": plan_id})
    store.check_doc(plan_doc, "plan", "plan.json")  # refuse before the directory or lock file exists
    store.check_doc(brief_doc, "brief", "brief.json")
    store.check_doc(event, "log-event", "log event")
    with store.PlanLock(root) as lock:
        store.save_many([(root / "plan.json", plan_doc, "plan"), (root / "brief.json", brief_doc, "brief")])
        (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
        store.append_log(root, event, lock=lock)
        plan = store.load_plan(root)
        _after_mutation(plan)
    return plan


# ---------------------------------------------------------------- add phase / item / decision

def _reject_owned_data(kind: str, data: dict | None) -> dict:
    data = dict(data or {})
    _guard_owned(kind, data)
    return data


def add_phase(plan, title: str, *, phase_id: str | None = None, data: dict | None = None) -> str:
    """Add a skeleton phase and append it to ``plan.phases``; returns the phase id."""
    extra = _reject_owned_data("phase", data)
    with _mutation(plan) as p:
        existing = set(p.phases) | set(p.plan.get("phases", []))
        if phase_id is None:
            phase_id = f"P{_next_number('P', existing)}"
        elif not PHASE_ID.fullmatch(phase_id):
            raise PlanError("PHASE_ID_INVALID", f"invalid phase id {phase_id!r}")
        if phase_id in existing:
            raise PlanError("PHASE_EXISTS", f"phase {phase_id} already exists")
        doc = {"$schema": _schema_const("phase"), "id": phase_id, "title": title, "design": "skeleton",
               "goal": title, "items": [], "batches": []}
        doc.update(copy.deepcopy(extra))
        doc["title"] = title
        plan_doc = copy.deepcopy(p.plan)
        plan_doc["phases"] = [*plan_doc.get("phases", []), phase_id]
        _commit(p, [("phase", phase_id, doc), ("plan", None, plan_doc)])
    return phase_id


def add_item(plan, phase: str, title: str, *, data: dict | None = None, batch: str | None = None) -> str:
    """Add a skeleton item as the next ``Pn.m`` of ``phase``; it joins ``batch`` or gets a solo batch."""
    extra = _reject_owned_data("item", data)
    with _mutation(plan) as p:
        if phase not in p.phases:
            raise PlanError("REF_UNKNOWN", f"unknown phase {phase!r}")
        phase_doc = copy.deepcopy(p.phases[phase])
        existing = set(phase_doc.get("items", [])) | {key for key in p.items if key.startswith(f"{phase}.")}
        number = _next_number(f"{phase}.", existing)
        item_id = f"{phase}.{number}"
        doc = {
            "$schema": _schema_const("item"), "id": item_id, "title": title, "status": "todo",
            "summary": "Outcome placeholder", "why": "From plan goal",
            "scope": {"include": ["to be designed"], "exclude": []}, "route": dict(DEFAULT_ROUTE),
            "review": {"mode": "none"}, "authority": {"kind": "routine"},
            "rag": {"need": "none", "status": "not_needed"}, "result": None,
        }
        doc.update(copy.deepcopy(extra))
        doc["title"] = title
        phase_doc["items"] = [*phase_doc.get("items", []), item_id]
        batches = phase_doc.setdefault("batches", [])
        target = next((b for b in batches if b.get("id") == batch), None) if batch else None
        if target is not None:
            target["items"] = [*target.get("items", []), item_id]
        else:
            batches.append({"id": batch or f"B{phase}-{number}", "items": [item_id],
                            "mode": "recommended"})
        _commit(p, [("item", item_id, doc), ("phase", phase, phase_doc)])
    return item_id


def add_decision(plan, title: str, *, data: dict | None = None, actor: dict | None = None) -> str:
    """Add the next ``D#``: an open question by default, or whatever ``data`` declares."""
    extra = _reject_owned_data("decision", data)
    with _mutation(plan) as p:
        decision_id = f"D{_next_number('D', p.decisions)}"
        doc = {"$schema": _schema_const("decision"), "id": decision_id, "title": title,
               "date": store.now()[:10], "status": "open",
               "actor": copy.deepcopy(actor or p.plan.get("authoring") or {})}
        doc.update(copy.deepcopy(extra))
        doc["title"] = title
        if doc.get("status") == "open":
            doc.setdefault("question", title)
        _commit(p, [("decision", decision_id, doc)])
    return decision_id


# ---------------------------------------------------------------- patch / push / batches

def _target(p: store.Plan, ref: str) -> tuple[str, str, dict]:
    """Resolve a phase (``P1``), item (``P1.2``), decision (``D3``) or unit (``P1.2/U1``) of this plan."""
    if _UNIT_REF.fullmatch(ref):
        if ref not in p.units:
            raise PlanError("REF_UNKNOWN", f"unknown unit {ref!r}")
        return "unit", ref, p.units[ref]
    try:
        parsed = parse_ref(ref)
    except ValueError:
        raise PlanError("REF_INVALID", f"invalid reference {ref!r}") from None
    if parsed.plan is not None:
        raise PlanError("REF_QUALIFIED", f"{ref!r} points to another plan")
    kind = parsed.kind
    table = {"phase": p.phases, "item": p.items, "decision": p.decisions}[kind]
    if ref not in table:
        raise PlanError("REF_UNKNOWN", f"unknown {kind} {ref!r}")
    return kind, ref, table[ref]


def patch(plan, ref: str, merge_patch_doc: dict) -> None:
    """Apply an RFC 7386 merge patch to the stable fields of a phase, item, decision or unit."""
    if not isinstance(merge_patch_doc, dict):
        raise PlanError("PATCH_INVALID", "a merge patch must be a JSON object")
    with _mutation(plan) as p:
        kind, key, doc = _target(p, ref)
        _guard_owned(kind, merge_patch_doc)
        _commit(p, [(kind, key, merge_patch(doc, merge_patch_doc))])


def push(plan, ref: str, field: str, value: Any) -> None:
    """Append ``value`` to an array field; ``field`` may be dotted (``scope.include``)."""
    parts = field.split(".")
    with _mutation(plan) as p:
        kind, key, doc = _target(p, ref)
        _guard_owned(kind, parts[:1])
        doc = copy.deepcopy(doc)
        holder = doc
        for part in parts[:-1]:
            holder = holder.setdefault(part, {})
            if not isinstance(holder, dict):
                raise PlanError("FIELD_NOT_ARRAY", f"{field!r}: {part!r} is not an object")
        current = holder.setdefault(parts[-1], [])
        if not isinstance(current, list):
            raise PlanError("FIELD_NOT_ARRAY", f"{field!r} of {ref} is not an array")
        current.append(copy.deepcopy(value))
        _commit(p, [(kind, key, doc)])


def set_batches(plan, phase: str, batches: list) -> None:
    """Replace ``phase.batches``; membership consistency is reported by ``check``."""
    with _mutation(plan) as p:
        if phase not in p.phases:
            raise PlanError("REF_UNKNOWN", f"unknown phase {phase!r}")
        doc = copy.deepcopy(p.phases[phase])
        doc["batches"] = copy.deepcopy(batches)
        _commit(p, [("phase", phase, doc)])


def set_plan(plan, merge_patch_doc: dict) -> None:
    """Merge-patch plan.json (goal, context, rules, links, settings, ...); identity and status stay owned."""
    if not isinstance(merge_patch_doc, dict):
        raise PlanError("PATCH_INVALID", "a merge patch must be a JSON object")
    with _mutation(plan) as p:
        _guard_owned("plan", merge_patch_doc)
        _commit(p, [("plan", None, merge_patch(p.plan, merge_patch_doc))])


def set_brief(plan, merge_patch_doc: dict) -> None:
    """Merge-patch brief.json (messages, requirements, constraints, ...)."""
    if not isinstance(merge_patch_doc, dict):
        raise PlanError("PATCH_INVALID", "a merge patch must be a JSON object")
    with _mutation(plan) as p:
        _guard_owned("brief", merge_patch_doc)
        _commit(p, [("brief", None, merge_patch(p.brief, merge_patch_doc))])
