"""Read-only plan queries. No locks, writes, view parsing or content truncation."""
from __future__ import annotations

import copy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Mapping, Sequence

from . import context, edges, refs, store
from .model import PHASE_ID, PlanError, id_sort_key, parse_ref


def _target(plan: store.Plan, ref: str, repos: Mapping[str, str] | None = None):
    if ref in ("plan", "brief"):
        return plan, ref, getattr(plan, ref), None
    try:
        parsed = parse_ref(ref)
    except ValueError:
        raise PlanError("REF_INVALID", f"invalid reference {ref!r}") from None
    target = plan
    local = ref
    if parsed.plan is not None:
        root, _same = refs._plans_root(plan, parsed.repo, repos)
        target = store.load_plan(refs._find_plan_dir(root, parsed.plan))
        local = ref.split(".", 1)[1]
    # Locate the whole document first, so a missing section has its own refusal.
    doc = edges.locate(target, local.split("#", 1)[0])
    if doc is None:
        raise PlanError("REF_UNKNOWN", f"unknown {parsed.kind} {ref!r}")
    kind = "document" if parsed.kind == "knowledge" else parsed.kind
    return target, kind, doc, parsed.section


REVISION = re.compile(r"sha256:[0-9a-f]{64}")


def revision_of(doc) -> str:
    """Revision of a whole document: ``sha256:`` + hex of its canonical JSON. ``get`` reports it and ``set``/``push``
    compare it under the plan lock (``--expected-revision``), so both must use this one function."""
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + sha256(text.encode("utf-8")).hexdigest()


def get(plan: store.Plan, ref: str, *, section: str | None = None,
        fields: Sequence[str] | None = None, repos: Mapping[str, str] | None = None) -> dict:
    """One complete document, optionally narrowed to a knowledge section or top-level fields.

    ``revision`` is that of the complete stored document, whatever the projection."""
    _plan, kind, source, embedded_section = _target(plan, ref, repos)
    revision = revision_of(source)
    if section is not None and embedded_section is not None and section != embedded_section:
        raise PlanError("SECTION_UNKNOWN", "section flag conflicts with the reference fragment")
    selected = section if section is not None else embedded_section
    doc = copy.deepcopy(source)
    if selected is not None:
        if kind != "document":
            raise PlanError("SECTION_UNKNOWN", "sections are available only for knowledge documents")
        matches = [s for s in doc.get("sections", []) if s.get("id") == selected]
        if not matches:
            raise PlanError("SECTION_UNKNOWN", f"unknown section {selected!r} in {ref!r}")
        doc["sections"] = matches
    if fields is not None:
        missing = [key for key in fields if key not in doc]
        if missing:
            raise PlanError("FIELD_UNKNOWN", f"unknown top-level fields: {', '.join(missing)}")
        doc = {key: doc[key] for key in fields}
    return {"ref": ref, "kind": kind, "doc": doc, "revision": revision}


_DONE_ITEM = ("done", "done_with_deviations", "skipped")


def plans_overview(plans_root) -> dict:
    """The live plans of a project, ascending by directory id, with their progress.

    ``archive`` and directories without ``plan.json`` are skipped; a plan whose ``plan.json`` cannot be read is listed
    as ``{"id": <directory>, "error": <code>}`` instead of failing the list.
    """
    root = Path(plans_root)
    rows = []
    for path in sorted(root.iterdir(), key=lambda p: p.name) if root.is_dir() else []:
        if not path.is_dir() or path.name == store.ARCHIVE or path.name.startswith(".") \
                or not (path / "plan.json").is_file():
            continue
        try:
            plan = store.load_plan(path)
        except (PlanError, OSError):
            rows.append({"id": path.name, "error": "PLAN_INVALID"})
            continue
        if any(name == "plan.json" for name, _message in plan.problems):
            rows.append({"id": path.name, "error": "PLAN_INVALID"})
            continue
        doc = plan.plan
        listed = [p for p in doc.get("phases", []) if p in plan.phases] if isinstance(doc.get("phases"), list) else []
        done = sum(1 for item in plan.items.values() if item.get("status") in _DONE_ITEM)
        rows.append({"id": doc.get("id") if isinstance(doc.get("id"), str) else path.name,
                     "short_id": doc.get("short_id"), "title": doc.get("title"), "status": doc.get("status"),
                     "updated_at": doc.get("updated_at"),
                     "progress": {"phases": len(plan.phases), "phases_closed": sum(1 for p in plan.phases.values() if p.get("closed")),
                                  "items": len(plan.items), "items_done": done}})
    return {"plans": rows}


_LIST_KINDS = {"items": "item", "phases": "phase", "decisions": "decision",
               "documents": "document", "knowledge": "document", "units": "unit"}


def _normalized_ref(plan: store.Plan, ref: str) -> str:
    if ref in ("plan", "brief"):
        return ref
    parsed = parse_ref(ref)
    if parsed.plan == plan.plan.get("short_id") and parsed.repo in (None, plan.plan.get("repository")):
        return ref.split(".", 1)[1]
    return ref


def _local_filter(plan: store.Plan, ref: str) -> str:
    """Validate a filter reference and normalize self-qualified references."""
    _target(plan, ref)
    if ref in ("plan", "brief"):
        return ref
    parsed = parse_ref(ref)
    if parsed.plan is not None:
        if parsed.plan != plan.plan.get("short_id") or parsed.repo not in (None, plan.plan.get("repository")):
            raise PlanError("REF_QUALIFIED", f"{ref!r} points to another plan")
        return ref.split(".", 1)[1]
    return ref


def list_rows(plan: store.Plan, kind: str, *, status: str | None = None, phase: str | None = None,
              applies_to: str | None = None) -> list[dict]:
    """Deterministically ordered lightweight rows; filters combine with AND."""
    kind = _LIST_KINDS.get(kind, kind)
    if kind not in ("phase", "item", "decision", "document", "unit"):
        raise PlanError("KIND_UNKNOWN", f"cannot list {kind!r}")
    if phase is not None:
        if not PHASE_ID.fullmatch(phase):
            raise PlanError("REF_INVALID", f"invalid phase {phase!r}")
        _target(plan, phase)
    if applies_to is not None:
        _target(plan, applies_to)
        applies_to = _normalized_ref(plan, applies_to)
    applies = {}
    if phase is not None or applies_to is not None:
        for edge in edges.edges(plan):
            if edge.kind == "applies_to":
                applies.setdefault(edge.source, set()).add(_normalized_ref(plan, edge.target))
    rows = []
    for doc_kind, key, ref, doc in edges.documents(plan):
        if doc_kind != kind or (status is not None and doc.get("status") != status):
            continue
        targets = applies.get(ref, set())
        if phase is not None:
            in_phase = key.split(".", 1)[0] == phase if kind in ("phase", "item", "unit") else any(
                t == phase or t.startswith(phase + ".") for t in targets)
            if not in_phase:
                continue
        if applies_to is not None and applies_to not in targets:
            continue
        rows.append({"ref": ref, "title": doc.get("title"), "status": doc.get("status")})
    return rows


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone is required")
        return parsed
    except ValueError:
        raise PlanError("SINCE_INVALID", f"invalid timestamp {value!r}; timezone is required") from None


def events(plan: store.Plan, *, item: str | None = None, types: Sequence[str] | None = None,
           since: str | None = None, limit: int | None = None) -> list[dict]:
    """Journal order, inclusive since; limit selects the latest matching events in that order."""
    if item is not None:
        item = _local_filter(plan, item)
        if item in ("plan", "brief") or parse_ref(item).kind != "item":
            raise PlanError("REF_INVALID", "--item requires an item reference")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 0):
        raise PlanError("LIMIT_INVALID", "limit must be a non-negative integer")
    after = _timestamp(since) if since is not None else None
    source = store.read_log(plan.root)
    for event in source:
        store.check_doc(event, "log-event", "journal event")
    rows = [e for e in source
            if (item is None or e.get("item") == item) and (types is None or e.get("type") in types)
            and (after is None or _timestamp(e["ts"]) >= after)]
    return rows if limit is None else (rows[-limit:] if limit else [])


_FOLLOWUP = re.compile(r"(follow_up|owner_decision)\(([a-z_]+)\): (.+)", re.S)


def followups(plan: store.Plan, *, open_only: bool = False) -> dict:
    """The ``follow_up(<class>): text`` and ``owner_decision(<class>): text`` entries of ``result.pending``, in item order.

    An entry is resolved when another item of the plan has a ``related`` link to its item with the relation
    ``follows_up`` (``plan.py link <new> <origin> --kind related --relation follows_up``); the link closes every
    follow-up of the origin item. Nothing is created or changed: work is never added without a decision.
    """
    resolved: dict[str, list[str]] = {}
    for edge in edges.edges(plan):
        if edge.kind == "related" and edge.relation == "follows_up" and edge.source != edge.target \
                and edge.source in plan.items and edge.target in plan.items:
            resolved.setdefault(edge.target, []).append(edge.source)
    rows = []
    for item_id in sorted(plan.items, key=id_sort_key):
        pending = (plan.items[item_id].get("result") or {}).get("pending")
        for entry in pending if isinstance(pending, list) else []:
            match = _FOLLOWUP.fullmatch(entry) if isinstance(entry, str) else None
            if match is None:
                continue
            by = sorted(set(resolved.get(item_id, [])), key=id_sort_key)
            if open_only and by:
                continue
            rows.append({"item": item_id, "phase": item_id.split(".")[0], "kind": match[1], "class": match[2],
                         "text": match[3], "entry": entry, "status": "resolved" if by else "open", "resolved_by": by})
    return {"plan": plan.plan.get("id"), "followups": rows}


def artifact(plan: store.Plan, ref: str, *, inline: bool = False,
             repos: Mapping[str, str] | None = None) -> dict:
    """Metadata and digest of declared artifact bytes; inline JSON or UTF-8 text on request."""
    target_plan, kind, entry, _section = _target(plan, ref, repos)
    if kind != "artifact":
        raise PlanError("REF_INVALID", "artifact requires an artifact/<id> reference")
    path = entry["path"]
    target = context._resolve(target_plan, path)
    if target is None:
        raise PlanError("PATH_INVALID", f"artifact path {path!r} escapes its root")
    if context.human_view(target_plan, path):
        raise PlanError("HUMAN_VIEW", f"{path} is human-only plan content; reference its JSON source")
    result = {"ref": ref, "path": path, "role": entry["role"], "exists": target.is_file(), "sha256": None}
    if result["exists"]:
        raw = target.read_bytes()
        result["sha256"] = sha256(raw).hexdigest()
        if inline:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise PlanError("CONTENT_INVALID", f"{path} is not UTF-8 text") from None
            if target.suffix.lower() == ".json":
                try:
                    result["content"] = json.loads(text)
                except ValueError:
                    raise PlanError("CONTENT_INVALID", f"{path} is not valid JSON") from None
            else:
                result["content"] = text
    return result


def _graph_ref(plan: store.Plan, ref: str) -> str:
    """Resolve local graph roots; foreign nodes are references only, never loaded."""
    try:
        local = _normalized_ref(plan, ref)
    except ValueError:
        raise PlanError("REF_INVALID", f"invalid reference {ref!r}") from None
    if local in ("plan", "brief") or parse_ref(local).plan is None:
        get(plan, local)  # includes section existence checks
    return local


def _node(plan: store.Plan, ref: str) -> dict:
    doc = None
    if ref in ("plan", "brief"):
        doc = getattr(plan, ref)
    elif ref.startswith("brief/"):
        doc = next((r for r in plan.brief.get("requirements", []) if r.get("id") == ref[6:]), None)
    elif parse_ref(ref).plan is None:
        doc = edges.locate(plan, ref)
    doc = doc or {}
    return {"ref": ref, "title": doc.get("title", doc.get("text")), "status": doc.get("status")}


def _links(plan: store.Plan, ref: str, graph: list[edges.Edge], *, direction: str,
           kinds: Sequence[str] | None, depth: int) -> dict:
    if direction not in ("out", "in", "both"):
        raise PlanError("DIRECTION_INVALID", "direction must be out, in or both")
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise PlanError("DEPTH_INVALID", "depth must be an integer >= 1")
    if kinds is not None and (not kinds or any(k not in edges.EDGE_KINDS for k in kinds)):
        raise PlanError("KIND_UNKNOWN", f"edge kinds must be among {', '.join(edges.EDGE_KINDS)}")
    root = _graph_ref(plan, ref)
    adjacent = {}
    for edge in graph:
        if kinds is not None and edge.kind not in kinds:
            continue
        source = _normalized_ref(plan, edge.source) if not edge.source.startswith("brief/") else edge.source
        target = _normalized_ref(plan, edge.target)
        key = (edge.kind, source, target, edge.relation or "", edge.note or "")
        data = {"from": source, "to": target, "kind": edge.kind}
        if edge.relation is not None:
            data["relation"] = edge.relation
        if edge.note is not None:
            data["note"] = edge.note
        if direction in ("out", "both"):
            adjacent.setdefault(source, []).append((target, key, data))
        if direction in ("in", "both"):
            adjacent.setdefault(target, []).append((source, key, data))
    visited, frontier, found = {root}, {root}, {}
    for _ in range(depth):
        following = set()
        for node in sorted(frontier):
            for other, key, data in adjacent.get(node, []):
                found[key] = data
                if other not in visited:
                    following.add(other)
        visited.update(following)
        frontier = following
        if not frontier:
            break
    node_refs = {root}
    for edge in found.values():
        node_refs.update((edge["from"], edge["to"]))
    return {"ref": ref, "edges": [found[key] for key in sorted(found)],
            "nodes": [_node(plan, node) for node in sorted(node_refs)]}


def links(plan: store.Plan, ref: str, *, direction: str = "both", kinds: Sequence[str] | None = None,
          depth: int = 1) -> dict:
    """Bounded BFS of the local edge table, preserving original edge direction and foreign refs."""
    return _links(plan, ref, edges.edges(plan), direction=direction, kinds=kinds, depth=depth)


def neighborhood(plan: store.Plan, item: str) -> dict:
    """Item, depth-one graph, and complete local decisions/knowledge relevant to it."""
    local = _graph_ref(plan, item)
    if local in ("plan", "brief") or parse_ref(local).kind != "item":
        raise PlanError("REF_INVALID", "neighborhood requires an item reference")
    if parse_ref(local).plan is not None:
        raise PlanError("REF_QUALIFIED", "neighborhood requires an item of this plan")
    graph = edges.edges(plan)
    result = _links(plan, item, graph, direction="both", kinds=None, depth=1)
    applicable, explicit_decisions, explicit_documents = {}, set(), set()
    for edge in graph:
        source = _normalized_ref(plan, edge.source) if not edge.source.startswith("brief/") else edge.source
        target = _normalized_ref(plan, edge.target)
        if edge.kind == "applies_to":
            applicable.setdefault(source, set()).add(target)
        if source == local:
            if edge.kind == "decision":
                explicit_decisions.add(target)
            elif edge.kind == "consumes" and target.startswith("knowledge/"):
                explicit_documents.add(target.split("#", 1)[0])
    phase = local.split(".", 1)[0]
    decisions, documents = [], []
    for kind, _key, ref, doc in edges.documents(plan):
        targets = applicable.get(ref, set())
        applies = not targets or local in targets or phase in targets
        if kind == "decision" and (ref in explicit_decisions or doc.get("status") == "accepted" and applies):
            decisions.append(copy.deepcopy(doc))
        elif kind == "document" and (applies or ref in explicit_documents):
            documents.append(copy.deepcopy(doc))
    return {**result, "item": copy.deepcopy(plan.items[local]), "decisions": decisions, "documents": documents}
