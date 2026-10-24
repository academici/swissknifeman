"""Authoring mutations of a v4 plan: create, add phase/item/decision, merge-patch, push, batches.

Each mutation is lock -> load fresh snapshot -> change -> validate every changed document -> save ->
regenerate views. A refused mutation leaves every file byte-identical. ``plan`` is a ``store.Plan``
(refreshed in place after the mutation), a plan directory path or a plan reference.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
from datetime import date as _date
from pathlib import Path
import re
from typing import Any, Iterator

from planner.integration import events as emission

from . import lifecycle, query, settings, store, views, workspace
from .model import SHORT_ID, PlanError, parse_ref

_DIR_ID = re.compile(r"^(\d{4}\.\d{2}\.\d{2})-№([1-9][0-9]*)-[A-Z][A-Z0-9-]*$", re.ASCII)
_UNIT_REF = re.compile(r"^(P[0-9]+\.[0-9]+)/(U[0-9]+)$")
_PLAN_TITLE_PREFIX = re.compile(r"^Plan №[1-9][0-9]* —")

# Top-level fields no authoring verb may change: identity and lifecycle-owned state.
OWNED_FIELDS = {
    "plan": frozenset({"$schema", "id", "short_id", "created", "updated_at", "status"}),
    "brief": frozenset({"$schema"}),
    "phase": frozenset({"$schema", "id", "design", "closed", "readiness"}),
    "item": frozenset({"$schema", "id", "status", "result", "updated_at"}),
    "unit": frozenset({"$schema", "id", "item", "status", "outcome", "updated_at"}),
    "decision": frozenset({"$schema", "id"}),
    "document": frozenset({"$schema", "id"}),
}
GITIGNORE = "context/\n.lock\nviews/\n"


def _schema_const(kind: str) -> str:
    return f"urn:swissknifeman:task:plan:{kind}:v1"


def _after_mutation(plan: store.Plan) -> None:
    """Regenerate the human views inside the mutation's lock; only changed files are written."""
    views.render_all(plan)


def _lock_timeout(plan_root: Path) -> float:
    """Seconds to wait for the lock of the plan in ``plan_root`` (``lock.timeout_seconds``)."""
    return float(settings.for_root(Path(plan_root).parent).get("lock.timeout_seconds"))


@contextmanager
def _mutation(plan) -> Iterator[store.Plan]:
    root = plan.root if isinstance(plan, store.Plan) else store.resolve_plan_dir(plan)
    with store.PlanLock(root, timeout=_lock_timeout(root)):
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
            {"phase": p.phases, "item": p.items, "decision": p.decisions, "unit": p.units,
             "document": p.documents}[kind][key] = doc


def _expect_revision(doc: Any, expected: str | None) -> None:
    """Compare the document's revision with ``expected`` inside the lock; a mismatch refuses before any write."""
    if expected is None:
        return
    current = query.revision_of(doc)
    if current != expected:
        raise PlanError("PLAN_REVISION_CONFLICT", f"the document changed since revision {expected}; now {current}")


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
    """One row per distinct plan directory in ``plans/`` and ``plans/archive/``: id and Short ID from ``plan.json``."""
    rows: dict[str, dict] = {}
    for path in store.plan_dirs(plans_root):
        row = rows.setdefault(path.name, {"id": path.name, "short_id": None})
        if row["short_id"] is None:
            row["short_id"] = store.short_id_of(path)
    return list(rows.values())


def _new_plan_settings(config) -> dict:
    """The ``settings`` of a new plan from ``new_plan.*``; empty ``language`` and ``commit_scope`` and an optional
    ``evidence`` are not written."""
    result = {"design_audit": config.get("new_plan.design_audit"), "scout": config.get("new_plan.scout"),
              "context_pack": config.get("new_plan.context_pack")}
    if config.get("new_plan.evidence") == "required":
        result["evidence"] = "required"
    if config.get("new_plan.language"):
        result["language"] = config.get("new_plan.language")
    if config.get("new_plan.commit_scope"):
        result["commit"] = {"scope": config.get("new_plan.commit_scope")}
    return result


def default_repository(plans_root: str | Path) -> str:
    """The repository name a new plan records: the folder name of the checkout the plans belong to (the bound checkout for
    the plans of a workspace project), else the name of the folder that holds ``plans_root``."""
    real = Path(plans_root).resolve()
    if workspace.workspace_project_of(real) is not None:
        source = workspace.source_root_of(real)
        if source is not None:
            return source.name
    return real.parent.name


def new_plan(codename: str, title: str, *, plans_root: str | Path, repository: str, owner: str,
             authoring: dict, message: str, date: str | None = None, message_date: str | None = None,
             channel: str | None = None) -> store.Plan:
    """Create plan.json, brief.json, .gitignore, .gitattributes and log.jsonl for a new plan.

    The identity is allocated from the plans already present: the next ``№N`` of the day and the next
    ``PLAN<N>`` above every live and archived plan.
    """
    plans_root = Path(plans_root)
    if not isinstance(message, str) or not message.strip():
        raise PlanError("MESSAGE_REQUIRED", "the first owner message is required (brief.messages needs one)")
    date = date or _date.today().strftime("%Y.%m.%d")
    if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", date):
        raise PlanError("PLAN_DATE_INVALID", f"expected YYYY.MM.DD, received {date!r}")
    if codename is None or not re.fullmatch(r"[A-Z][A-Z0-9-]*", codename):
        raise PlanError("PLAN_CODENAME_INVALID", f"code name must match [A-Z][A-Z0-9-]*, received {codename!r}")
    rows = _identities(plans_root)
    ordinal = max((int(m[2]) for row in rows if (m := _DIR_ID.match(row["id"])) and m[1] == date), default=0) + 1
    plan_id = f"{date}-№{ordinal}-{codename}"
    if any(row["id"] == plan_id for row in rows):
        raise PlanError("PLAN_EXISTS", f"plan {plan_id} already exists")
    if not _PLAN_TITLE_PREFIX.match(title):
        title = f"Plan №{ordinal} — {title}"
    taken = [int(row["short_id"][4:]) for row in rows if SHORT_ID.fullmatch(row["short_id"] or "")]
    short_id = f"PLAN{max(taken, default=0) + 1}"
    root = plans_root / plan_id
    if (root / "plan.json").exists():
        raise PlanError("PLAN_EXISTS", f"{root} already holds a plan")

    created = date.replace(".", "-")
    plan_doc = {
        "$schema": _schema_const("plan"), "id": plan_id, "short_id": short_id, "title": title, "status": "active",
        "created": created, "updated_at": store.now(), "repository": repository, "owner": owner,
        "authoring": copy.deepcopy(authoring), "goal": title, "context": title, "phases": [],
        "settings": _new_plan_settings(settings.for_root(plans_root)),
    }
    brief_message = {"id": "M1", "date": message_date or created, "text": message}
    if channel:
        brief_message["channel"] = channel
    brief_doc = {"$schema": _schema_const("brief"), "messages": [brief_message], "requirements": []}
    event = store.new_event("plan_created", f"plan {short_id} created", authoring, data={"plan_id": plan_id})
    store.check_doc(plan_doc, "plan", "plan.json")  # refuse before the directory or lock file exists
    store.check_doc(brief_doc, "brief", "brief.json")
    store.check_doc(event, "log-event", "log event")
    with store.PlanLock(root, timeout=_lock_timeout(root)) as lock:
        store.save_many([(root / "plan.json", plan_doc, "plan"), (root / "brief.json", brief_doc, "brief")])
        (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
        for name in (".ignore", ".cursorignore"):
            (root / name).write_text(store.SEARCH_IGNORE, encoding="utf-8")
        store.ensure_gitattributes(root)
        store.append_log(root, event, lock=lock)
        plan = store.load_plan(root)
        _after_mutation(plan)
        announce = [lifecycle.plan_created_event(plan)]
        project_root = lifecycle.event_project_root(plan)
    emission.emit_all(announce, project_root=project_root, plan_id=plan_id)
    return plan


# ---------------------------------------------------------------- add phase / item / decision

def _reject_owned_data(kind: str, data: dict | None) -> dict:
    data = dict(data or {})
    _guard_owned(kind, data)
    return data


def add_phase(plan, title: str, *, data: dict | None = None) -> str:
    """Add a skeleton phase and append it to ``plan.phases``; returns the phase id."""
    extra = _reject_owned_data("phase", data)
    with _mutation(plan) as p:
        existing = set(p.phases) | set(p.plan.get("phases", []))
        phase_id = f"P{_next_number('P', existing)}"
        doc = {"$schema": _schema_const("phase"), "id": phase_id, "title": title, "design": "skeleton",
               "goal": title, "items": [], "batches": []}
        doc.update(copy.deepcopy(extra))
        doc["title"] = title
        plan_doc = copy.deepcopy(p.plan)
        plan_doc["phases"] = [*plan_doc.get("phases", []), phase_id]
        _commit(p, [("phase", phase_id, doc), ("plan", None, plan_doc)])
    return phase_id


def add_item(plan, phase: str, title: str, *, data: dict | None = None, batch: str | None = None) -> str:
    """Add the next ``Pn.m``; detailed phases require complete data. Join ``batch`` or get a solo batch."""
    extra = _reject_owned_data("item", data)
    with _mutation(plan) as p:
        if phase not in p.phases:
            raise PlanError("REF_UNKNOWN", f"unknown phase {phase!r}")
        config = settings.for_plan(p)
        phase_doc = copy.deepcopy(p.phases[phase])
        existing = set(phase_doc.get("items", [])) | {key for key in p.items if key.startswith(f"{phase}.")}
        number = _next_number(f"{phase}.", existing)
        item_id = f"{phase}.{number}"
        doc = {
            "$schema": _schema_const("item"), "id": item_id, "title": title, "status": "todo",
            "summary": "Outcome placeholder", "why": "From plan goal",
            "scope": {"include": ["to be designed"], "exclude": []},
            "route": {"class": config.get("new_item.route_class"), "effort": config.get("new_item.route_effort")},
            "review": {"mode": config.get("new_item.review_mode")}, "authority": {"kind": "routine"},
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
        if phase_doc.get("design") == "detailed":
            from . import check
            # save_many supplies the final timestamp; the proposed graph needs a schema-valid one too.
            candidate = {**doc, "updated_at": p.plan["updated_at"]}
            store.check_doc(candidate, "item", item_id)
            proposed = copy.deepcopy(p)
            proposed.items[item_id], proposed.phases[phase] = candidate, phase_doc
            incomplete = [i for i in check.check(proposed) if i.level == "error" and i.code == "incomplete"
                          and i.where.startswith(f"phases/{phase}/{item_id}.json/")]
            if incomplete:
                raise PlanError("PHASE_DETAILED", "add the item with complete data via --file, or reopen design",
                                incomplete)
            _refuse_new_errors(p, "item", item_id, candidate, proposed=proposed)
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

def resolve_target(p: store.Plan, ref: str) -> tuple[str, str, dict]:
    """Resolve a phase (``P1``), item (``P1.2``), decision (``D3``) or unit (``P1.2/U1``) of this plan."""
    if ref in ("plan", "brief"):
        return ref, None, getattr(p, ref)
    if ref.startswith("knowledge/"):
        key = ref.removeprefix("knowledge/").removesuffix(".json")
        if key not in p.documents:
            raise PlanError("REF_UNKNOWN", f"unknown document {key!r}")
        return "document", key, p.documents[key]
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
    table = {"phase": p.phases, "item": p.items, "decision": p.decisions}.get(kind)
    if table is None:
        raise PlanError("REF_INVALID", f"{ref!r} names a {kind}, not a phase, item, decision or unit")
    if ref not in table:
        raise PlanError("REF_UNKNOWN", f"unknown {kind} {ref!r}")
    return kind, ref, table[ref]


def patch(plan, ref: str, merge_patch_doc: dict, *, expected_revision: str | None = None) -> None:
    """Apply an RFC 7386 merge patch to the stable fields of a phase, item, decision or unit.

    ``expected_revision`` (``query.revision_of`` of the document) is compared under the lock."""
    if not isinstance(merge_patch_doc, dict):
        raise PlanError("PATCH_INVALID", "a merge patch must be a JSON object")
    with _mutation(plan) as p:
        kind, key, doc = resolve_target(p, ref)
        _expect_revision(doc, expected_revision)
        _guard_owned(kind, merge_patch_doc)
        changed = merge_patch(doc, merge_patch_doc)
        _refuse_new_errors(p, kind, key, changed)
        _commit(p, [(kind, key, changed)])


def push(plan, ref: str, field: str, value: Any, *, expected_revision: str | None = None) -> None:
    """Append ``value`` to an array field; ``field`` may be dotted (``scope.include``).

    ``expected_revision`` is compared under the lock, as in ``patch``."""
    parts = field.split(".")
    with _mutation(plan) as p:
        kind, key, doc = resolve_target(p, ref)
        _expect_revision(doc, expected_revision)
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
        _refuse_new_errors(p, kind, key, doc)
        _commit(p, [(kind, key, doc)])


def set_batches(plan, phase: str, batches: list) -> None:
    """Replace ``phase.batches`` without introducing errors in a detailed phase."""
    with _mutation(plan) as p:
        if phase not in p.phases:
            raise PlanError("REF_UNKNOWN", f"unknown phase {phase!r}")
        doc = copy.deepcopy(p.phases[phase])
        doc["batches"] = copy.deepcopy(batches)
        _refuse_new_errors(p, "phase", phase, doc)
        _commit(p, [("phase", phase, doc)])


def set_plan(plan, merge_patch_doc: dict, *, expected_revision: str | None = None) -> None:
    """Merge-patch plan.json (goal, context, rules, links, settings, ...); identity and status stay owned."""
    if not isinstance(merge_patch_doc, dict):
        raise PlanError("PATCH_INVALID", "a merge patch must be a JSON object")
    with _mutation(plan) as p:
        _expect_revision(p.plan, expected_revision)
        _guard_owned("plan", merge_patch_doc)
        _commit(p, [("plan", None, merge_patch(p.plan, merge_patch_doc))])


def set_brief(plan, merge_patch_doc: dict, *, expected_revision: str | None = None) -> None:
    """Merge-patch brief.json (messages, requirements, constraints, ...)."""
    if not isinstance(merge_patch_doc, dict):
        raise PlanError("PATCH_INVALID", "a merge patch must be a JSON object")
    with _mutation(plan) as p:
        _expect_revision(p.brief, expected_revision)
        _guard_owned("brief", merge_patch_doc)
        changed = merge_patch(p.brief, merge_patch_doc)
        _refuse_new_errors(p, "brief", None, changed)
        _commit(p, [("brief", None, changed)])


def add_document(plan, data: dict) -> str:
    """Add a schema-backed knowledge document; `knowledge/<id>` is its authoring reference."""
    doc = copy.deepcopy(data)
    doc.setdefault("$schema", _schema_const("document"))
    store.check_doc(doc, "document", "document")
    with _mutation(plan) as p:
        if doc["id"] in p.documents:
            raise PlanError("ID_DUPLICATE", f"document {doc['id']} already exists")
        _commit(p, [("document", doc["id"], doc)])
    return doc["id"]


def apply(plan, patches: list[dict]) -> None:
    """Validate a group of merge patches as one proposed graph, then commit all changed documents."""
    if not isinstance(patches, list) or not patches:
        raise PlanError("PATCH_INVALID", "apply needs a non-empty array of {ref, patch} objects")
    with _mutation(plan) as p:
        proposed, changed = copy.deepcopy(p), {}
        for entry in patches:
            if not isinstance(entry, dict) or set(entry) != {"ref", "patch"} or not isinstance(entry["patch"], dict):
                raise PlanError("PATCH_INVALID", "each entry must contain only ref and an object patch")
            kind, key, doc = resolve_target(proposed, entry["ref"])
            _guard_owned(kind, entry["patch"])
            doc = merge_patch(doc, entry["patch"])
            store.check_doc(doc, kind, entry["ref"])
            if kind in ("plan", "brief"):
                setattr(proposed, kind, doc)
            else:
                table = {"phase": proposed.phases, "item": proposed.items, "unit": proposed.units,
                         "decision": proposed.decisions, "document": proposed.documents}[kind]
                table[key] = doc
            changed[(kind, key)] = doc
        _check_proposed(proposed)
        _commit(p, [(kind, key, doc) for (kind, key), doc in changed.items()])


def _refuse_new_errors(p: store.Plan, kind: str, key: str | None, doc: dict, *,
                       proposed: store.Plan | None = None) -> None:
    """Refuse a single-document edit that makes ``check`` report a new error on a link field (D11: no dangling
    link through set/push), or any new error of the edited detailed phase. Pre-existing errors do not block edits."""
    from . import check, edges
    store.check_doc(doc, kind, f"{kind} {key or ''}".strip())  # a schema violation keeps its own refusal
    if proposed is None:
        proposed = copy.deepcopy(p)
        if kind in ("plan", "brief"):
            setattr(proposed, kind, doc)
        else:
            {"phase": proposed.phases, "item": proposed.items, "unit": proposed.units,
             "decision": proposed.decisions, "document": proposed.documents}[kind][key] = doc
    phase_id = check.owner_phase(proposed, check.Issue("error", "", key or "", "")) \
        if kind in ("phase", "item", "unit") else None
    detailed = phase_id is not None and proposed.phases.get(phase_id, {}).get("design") == "detailed"
    known = {(i.where, i.message) for i in check.check(p) if i.level == "error"}
    link_places = {edge.where for edge in edges.edges(proposed)}
    new = [i for i in check.check(proposed) if i.level == "error" and (i.where, i.message) not in known
           and ((detailed and check.owner_phase(proposed, i) == phase_id)
                or any(i.where == place or i.where.startswith(place + "/") for place in link_places))]
    if new:
        raise PlanError("PLAN_INVALID", "; ".join(f"{i.where}: {i.message}" for i in new), new)


def _check_proposed(proposed: store.Plan) -> None:
    """Refuse a proposed graph that ``check`` reports errors for; nothing has been written yet."""
    from . import check
    errors = [i for i in check.check(proposed) if i.level == "error"]
    if errors:
        raise PlanError("PLAN_INVALID", "; ".join(f"{i.where}: {i.message}" for i in errors), errors)


# ---------------------------------------------------------------- links and artifacts (D11)

LINK_KINDS = ("depends_on", "related", "decision", "applies_to", "unit_depends_on")


def _local_ref(ref: str, what: str):
    try:
        parsed = parse_ref(ref)
    except ValueError:
        raise PlanError("REF_INVALID", f"invalid {what} reference {ref!r}") from None
    if parsed.plan is not None:
        raise PlanError("REF_QUALIFIED", f"{what} {ref!r} points to another plan; links stay inside one plan")
    return parsed


def _link_slot(p: store.Plan, kind: str, source: str, target: str, relation: str | None, note: str | None):
    """Where the link ``source -> target`` of ``kind`` lives: ``(doc kind, key, doc, field, entry, same)``.

    ``entry`` is the stored form of the link and ``same(candidate)`` tells whether a stored element is this edge.
    The table of fields is ``edges.LINK_FIELDS``; this maps the closed write kinds onto it.
    """
    if kind not in LINK_KINDS:
        raise PlanError("KIND_UNKNOWN", f"link kind {kind!r} is not one of {', '.join(LINK_KINDS)}")
    if kind != "related" and (relation is not None or note is not None):
        raise PlanError("LINK_INVALID", f"--relation and --note belong to related links, not {kind}")
    if kind == "related" and not relation:
        raise PlanError("LINK_INVALID", "a related link needs --relation")
    doc_kind, key, doc = resolve_target(p, source)
    dest = _local_ref(target, "link target")
    starts = {"depends_on": ("phase", "item"), "related": ("item",), "decision": ("item",),
              "applies_to": ("decision", "document"), "unit_depends_on": ("unit",)}[kind]
    ends = {"depends_on": doc_kind, "decision": "decision", "unit_depends_on": "unit"}.get(kind)
    if doc_kind not in starts:
        raise PlanError("LINK_INVALID", f"{kind} starts from {' or '.join(starts)}, not from {source!r} ({doc_kind})")
    if ends and dest.kind != ends:
        raise PlanError("LINK_INVALID", f"{kind} from {source} must end at a {ends}, {target!r} is a {dest.kind}")
    if kind == "related":
        entry = {"ref": target, "relation": relation, **({"note": note} if note else {})}
        return doc_kind, key, doc, "related", entry, \
            lambda held: isinstance(held, dict) and held.get("ref") == target and held.get("relation") == relation
    if kind == "unit_depends_on":
        if dest.target.split("/")[0] != key.split("/")[0]:
            raise PlanError("LINK_INVALID", f"unit dependencies stay inside one item: {source} -> {target}")
        target = dest.target.split("/")[1]  # stored as the bare unit id of the same item
    field = {"depends_on": "depends_on", "unit_depends_on": "depends_on", "decision": "decisions",
             "applies_to": "applies_to"}[kind]
    return doc_kind, key, doc, field, target, target.__eq__


def _write_proposed(p: store.Plan, doc_kind: str, key, doc: dict, ref: str) -> None:
    """Schema-check ``doc``, graph-check the plan with it in place, then commit it alone."""
    store.check_doc(doc, doc_kind, ref)
    proposed = copy.deepcopy(p)
    if doc_kind in ("plan", "brief"):
        setattr(proposed, doc_kind, doc)
    else:
        {"phase": proposed.phases, "item": proposed.items, "unit": proposed.units,
         "decision": proposed.decisions, "document": proposed.documents}[doc_kind][key] = doc
    _check_proposed(proposed)
    _commit(p, [(doc_kind, key, doc)])


def link(plan, source: str, target: str, *, kind: str, relation: str | None = None, note: str | None = None) -> bool:
    """Add the typed link ``source -> target`` as one checked mutation; True when it was written.

    A repeat of an existing edge is a no-op (a related link refreshes its note). The status and result of an item
    are never touched. A proposed graph with any ``check`` error is refused and nothing is written.
    """
    with _mutation(plan) as p:
        doc_kind, key, doc, field, entry, same = _link_slot(p, kind, source, target, relation, note)
        doc = copy.deepcopy(doc)
        stored = doc.get(field)
        if stored is not None and not isinstance(stored, list):
            raise PlanError("FIELD_NOT_ARRAY", f"{field!r} of {source} is not an array")
        stored = doc.setdefault(field, [])
        index = next((i for i, existing in enumerate(stored) if same(existing)), None)
        if index is None:
            stored.append(entry)
        elif kind == "related" and note and stored[index].get("note") != note:
            stored[index] = entry
        else:
            return False
        _write_proposed(p, doc_kind, key, doc, source)
    return True


def unlink(plan, source: str, target: str, *, kind: str, relation: str | None = None) -> bool:
    """Remove the typed link ``source -> target``; True when it was there. A missing edge is a no-op.

    The target is not resolved, so a dangling link can be removed; the proposed graph is still checked.
    """
    with _mutation(plan) as p:
        doc_kind, key, doc, field, _entry, same = _link_slot(p, kind, source, target, relation, None)
        stored = doc.get(field)
        if not isinstance(stored, list) or not any(same(existing) for existing in stored):
            return False
        doc = copy.deepcopy(doc)
        doc[field] = [existing for existing in doc[field] if not same(existing)]
        _write_proposed(p, doc_kind, key, doc, source)
    return True


def add_artifact(plan, item: str, path: str, role: str, *, artifact_id: str | None = None) -> bool:
    """Declare an input or output artifact of ``item``; True when it was written.

    An artifact is the pair ``(path, role)``: a repeat is a no-op, a repeat that names another id is refused.
    Id uniqueness, the input -> output path match and the id's resolution are the ``check`` rules.
    """
    with _mutation(plan) as p:
        doc_kind, key, doc = resolve_target(p, item)
        if doc_kind != "item":
            raise PlanError("LINK_INVALID", f"artifacts belong to an item, {item!r} is a {doc_kind}")
        doc = copy.deepcopy(doc)
        entries = doc.get("artifacts")
        if entries is not None and not isinstance(entries, list):
            raise PlanError("FIELD_NOT_ARRAY", f"artifacts of {item} is not an array")
        entries = doc.setdefault("artifacts", [])
        current = next((e for e in entries if isinstance(e, dict) and e.get("path") == path and e.get("role") == role),
                       None)
        if current is not None:
            if artifact_id is not None and current.get("id") not in (None, artifact_id):
                raise PlanError("LINK_INVALID", f"{role} artifact {path!r} of {item} already has id {current['id']!r}")
            if artifact_id is None or current.get("id") == artifact_id:
                return False
            current["id"] = artifact_id
        else:
            entries.append({"path": path, "role": role, **({"id": artifact_id} if artifact_id else {})})
        _write_proposed(p, doc_kind, key, doc, item)
    return True
