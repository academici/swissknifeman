"""Execution-input projection (exec/v1): the task for a worker, cut from the full context pack.

``build`` maps ``context.collect`` into the ``execution-input`` document by the ``brief-mapping`` table of
``knowledge/task-changes``. It is read-only: no ``PlanLock``, no plan or log writes, no ``context/`` pack. Lifecycle
instructions and the report API never enter the document; the full pack stays reachable through ``context_refs``.
"""
from __future__ import annotations

import copy
from hashlib import sha256
import json
from pathlib import Path

from . import context, store
from .model import PlanError, item_phase

SCHEMA = "urn:swissknifeman:orch:exec:execution-input:v1"
CONTRACT_VERSION = "exec/v1"
TOOL = "task/plan.py brief"
REPORT = ["summary", "changed_paths", "checks_run", "evidence", "open_issues"]
ESCALATION = ["A required read is missing or contradicts the goal",
              "An acceptance check cannot pass without leaving scope"]
_DECISION_KEYS = ("title", "status", "decision", "rationale")
_LESSON_KEYS = ("type", "summary", "ts", "item", "impact", "next")


def canonical_digest(doc: dict) -> str:
    """sha256 of canonical JSON without ``digest`` and without the ``@`` suffix of ``input_id`` (exec/v1 conventions)."""
    payload = {key: value for key, value in doc.items() if key != "digest"}
    if isinstance(payload.get("input_id"), str):
        payload["input_id"] = payload["input_id"].rsplit("@", 1)[0]
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _task_version() -> str:
    try:
        manifest = Path(__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json"
        return str(json.loads(manifest.read_text(encoding="utf-8"))["version"])
    except (OSError, ValueError, KeyError):
        return "unknown"


def _plan_dir(plan: store.Plan) -> str:
    try:
        return plan.root.resolve().relative_to(plan.repo_root.resolve()).as_posix()
    except ValueError:
        return plan.root.as_posix()


def _read(plan: store.Plan, entry: dict, inline: bool) -> dict:
    """Existing files get ``sha256`` of their bytes; ``inline`` adds the full UTF-8 text when no content is attached."""
    entry = copy.deepcopy(entry)
    target = context._resolve(plan, entry["path"]) if entry.get("exists") else None
    if target is None or not target.is_file():
        return entry
    try:
        data = target.read_bytes()
    except OSError as exc:
        entry["error"] = str(exc)
        return entry
    entry["sha256"] = sha256(data).hexdigest()
    if inline and "content" not in entry and "error" not in entry:
        try:
            entry["content"] = data.decode("utf-8")
        except UnicodeDecodeError:
            entry["error"] = "binary or non-utf8"
    return entry


def _constraints(pack: dict, unit: dict | None) -> list[dict]:
    found = []
    for source, texts in (("plan.rules", pack["plan"].get("rules")), ("phase.pitfalls", pack["phase"].get("pitfalls")),
                          ("item.rules", pack["item"].get("rules"))):
        found += [{"text": text, "source": f"{source}[{index}]"} for index, text in enumerate(texts or [])]
    if unit and unit.get("instructions"):
        found.append({"text": unit["instructions"], "source": "unit.instructions"})
    return found


def _decisions(pack: dict) -> list[dict]:
    refs = []
    for doc in pack["decisions"]:
        if "loaded" in doc:  # foreign reference; the resolver of external plans is P2.3
            refs.append(copy.deepcopy(doc))
        else:
            refs.append({"ref": doc["id"], "loaded": True,
                         **{key: doc[key] for key in _DECISION_KEYS if doc.get(key) is not None}})
    return refs


def _checks(item: dict, unit: dict | None) -> list[dict]:
    if unit is None:
        return copy.deepcopy(item.get("validation", []))
    by_id = {c["id"]: c for c in item.get("validation", [])}  # as units.brief
    return [copy.deepcopy(by_id[c] if isinstance(c, str) else c) for c in unit.get("checks", [])]


def _context_refs(plan: store.Plan, pack: dict, plan_dir: str) -> list[dict]:
    refs = [{"kind": "pack", "ref": pack["ref"], "path": f"{plan_dir}/{context.PACK_DIR}/{pack['item']['id']}.json"}]
    for doc in pack["documents"]:
        ref = {"kind": "document", "ref": f"knowledge/{doc['id']}", "path": f"{plan_dir}/knowledge/{doc['id']}.json"}
        source = plan.path("document", doc["id"])
        if source.is_file():
            ref["sha256"] = sha256(source.read_bytes()).hexdigest()
        refs.append(ref)
    return refs


def _upstream(pack: dict) -> list[dict]:
    result = []
    for doc in pack["upstream"]:
        outcome = doc.get("result") or {}
        entry = {"ref": doc["id"], "title": doc.get("title"), "status": doc.get("status"), "summary": doc.get("summary"),
                 "notes": outcome.get("notes"), "deliverables": doc.get("deliverables")}
        result.append({key: value for key, value in entry.items() if value is not None})
    return result


def build(plan: store.Plan, item_id: str, *, unit_id: str | None = None, inline_reads: bool = False,
          repos=None) -> dict:
    """Execution-input of ``item_id`` (or of its unit ``unit_id``). ``repos`` is reserved for the resolver of P2.3."""
    if item_id not in plan.items:
        raise PlanError("REF_UNKNOWN", f"unknown item {item_id!r}")
    unit = None
    if unit_id is not None:
        if f"{item_id}/{unit_id}" not in plan.units:
            raise PlanError("REF_UNKNOWN", f"unknown unit {item_id}/{unit_id!r}")
        unit = plan.units[f"{item_id}/{unit_id}"]
    phase_id = item_phase(item_id)
    if plan.phases.get(phase_id, {}).get("design") == "skeleton":
        raise PlanError("PHASE_NOT_DETAILED", f"{phase_id} is a skeleton; detail it before briefing {item_id}")
    missing = context.missing_reads(plan, item_id)
    if missing:
        raise PlanError("READ_MISSING", f"required reads are missing: {', '.join(missing)}")
    pack = context.collect(plan, item_id, with_scout=True)
    item, short = pack["item"], plan.plan.get("short_id") or plan.plan["id"]
    plan_dir = _plan_dir(plan)
    read_only = bool(unit is not None and not unit.get("files"))
    reads = list(pack["reads"])
    if unit is not None:
        reads += [context.read_entry(plan, r) for r in unit.get("reads", [])]
    gate = item.get("authority") or {}
    escalation = list(ESCALATION)
    if gate.get("kind") == "owner_gate":
        escalation.append(f"Owner gate {gate.get('gate', gate.get('label', ''))}: {gate.get('scope', '')}")
    scope = {"include": copy.deepcopy(item["scope"]["include"]), "exclude": copy.deepcopy(item["scope"].get("exclude", [])),
             "write_set": list(unit["files"]) if unit is not None else [t["path"] for t in item.get("task_files", [])],
             "read_only": read_only}
    doc = {
        "$schema": SCHEMA, "contract_version": CONTRACT_VERSION,
        "input_id": f"{short}.{item_id}" + (f"/{unit_id}" if unit_id else ""),
        "provenance": {"kind": "plan", "plan": short, "plan_dir": plan_dir, "item": item_id,
                       **({"unit": unit_id} if unit_id else {}),
                       "source_digest": sha256(context.render(plan, item_id, with_scout=False).encode("utf-8")).hexdigest(),
                       "generated_by": {"tool": TOOL, "task_version": _task_version()}},
        "goal": unit["goal"] if unit is not None else f"{item['title']}: {item['summary']}",
        "scope": scope,
        "acceptance": {"checks": _checks(item, unit), "deliverables": copy.deepcopy(item.get("deliverables", []))},
        "route": {"minimum": copy.deepcopy((unit if unit is not None else item).get("route"))},
        "result_contract": {"report": list(REPORT), "write_authority": "none" if read_only else "code_scope",
                            "commit_owner": "coordinator", "plan_mutation": "forbidden"},
        "escalation": escalation,
    }
    optional = {
        "why": item.get("why"), "guidance": item.get("guidance"), "sections": copy.deepcopy(item.get("sections")),
        "constraints": _constraints(pack, unit), "decisions": _decisions(pack),
        "reads": [_read(plan, r, inline_reads) for r in reads],
        "context_refs": _context_refs(plan, pack, plan_dir), "upstream": _upstream(pack),
        "lessons": [{key: e[key] for key in _LESSON_KEYS if key in e} for e in pack["lessons"]],
        "hints": [{"text": text, "source": "scout"} for text in pack.get("scout", {}).get("entries", [])],
    }
    doc.update({key: value for key, value in optional.items() if value})
    doc["digest"] = canonical_digest(doc)
    doc["input_id"] += f"@{doc['digest'][:12]}"
    return doc


def render(plan: store.Plan, item_id: str, *, unit_id: str | None = None, inline_reads: bool = False,
           repos=None) -> str:
    doc = build(plan, item_id, unit_id=unit_id, inline_reads=inline_reads, repos=repos)
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
