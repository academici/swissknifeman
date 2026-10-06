"""Read-only plan queries. No locks, writes, view parsing or content truncation."""
from __future__ import annotations

import copy
from datetime import datetime
from hashlib import sha256
import json
from typing import Mapping, Sequence

from . import context, edges, refs, store
from .model import PHASE_ID, PlanError, parse_ref


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


def get(plan: store.Plan, ref: str, *, section: str | None = None,
        fields: Sequence[str] | None = None, repos: Mapping[str, str] | None = None) -> dict:
    """One complete document, optionally narrowed to a knowledge section or top-level fields."""
    _plan, kind, source, embedded_section = _target(plan, ref, repos)
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
    return {"ref": ref, "kind": kind, "doc": doc}


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
