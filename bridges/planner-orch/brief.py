"""Execution-input projection (exec/v1): the task for a worker, cut from the full context pack.

``build`` maps ``context.collect`` into the ``execution-input`` document by the ``brief-mapping`` table of
``knowledge/task-changes``. It is read-only: no ``PlanLock``, no plan or log writes, no ``context/`` pack. Lifecycle
instructions and the report API never enter the document; the full pack stays reachable through ``context_refs``.

Run as ``plan.py bridge planner-orch brief <plan> <item> [--unit U#] [--inline-reads] [--out FILE] [--repo NAME=PATH]``.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import sys

import partners

partners.use_aicore()
from aicore.util.digest import canonical_json_bytes, sha256_hex  # noqa: E402

context, store, _model = partners.planner_engine("plan.context", "plan.store", "plan.model")
ITEM_ID, PlanError, item_phase = _model.ITEM_ID, _model.PlanError, _model.item_phase
TERMINAL = {str(getattr(status, "value", status)) for status in _model.TERMINAL}

SCHEMA = "urn:swissknifeman:orch:exec:execution-input:v1"
CONTRACT_VERSION = "exec/v1"
TOOL = "planner-orch brief"
REPORT = ["summary", "changed_paths", "checks_run", "evidence", "open_issues"]
ESCALATION = ["A required read is missing or contradicts the goal",
              "An acceptance check cannot pass without leaving scope"]
LIFECYCLE_PHRASES = (
    "report_api", "report API", "plan.py start", "plan.py finish", "unit return", "planner:plan-run",
)
_UNIT_ID = re.compile(r"^U[0-9]+$", re.ASCII)
_DECISION_KEYS = ("title", "status", "decision", "rationale")
_FOREIGN_KEYS = ("ref", "loaded", *_DECISION_KEYS, "source", "reason")
_LESSON_KEYS = ("type", "summary", "ts", "item", "impact", "next")


def canonical_digest(doc: dict) -> str:
    """sha256 of canonical JSON without ``digest`` and without the ``@`` suffix of ``input_id`` (exec/v1 conventions)."""
    payload = {key: value for key, value in doc.items() if key != "digest"}
    if isinstance(payload.get("input_id"), str):
        payload["input_id"] = payload["input_id"].rsplit("@", 1)[0]
    return sha256_hex(canonical_json_bytes(payload))


def _task_version() -> str:
    try:
        manifest = partners.require_planner_root() / ".claude-plugin" / "plugin.json"
        return str(json.loads(manifest.read_text(encoding="utf-8"))["version"])
    except (OSError, ValueError, KeyError):
        return "unknown"


def _plan_dir(plan: store.Plan) -> str:
    try:
        return plan.root.resolve().relative_to(plan.repo_root.resolve()).as_posix()
    except ValueError:
        return plan.root.as_posix()


def _has_float(value) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_has_float(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_float(item) for item in value)
    return False


def _read(plan: store.Plan, entry: dict, inline: bool) -> dict:
    """Existing files get ``sha256`` of their bytes; ``inline`` adds the full UTF-8 text when no content is attached."""
    entry = copy.deepcopy(entry)
    if not isinstance(entry.get("path"), str):
        raise PlanError("REF_UNRESOLVED", f"read ref {entry.get('ref')!r} has no readable source path")
    entry.pop("ref", None)  # exec/v1 reads are closed and path-based; the ref only lives in the context pack
    if "content" in entry and _has_float(entry["content"]):
        # canonical JSON (the input digest) has no floats: a schema with ``"default": 0.6`` travels as its JSON text
        entry["content"] = json.dumps(entry["content"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    target = context._resolve(plan, entry["path"]) if entry.get("exists") else None
    if target is None or not target.is_file():
        return entry
    try:
        data = target.read_bytes()
    except OSError as exc:
        entry["error"] = str(exc)
        return entry
    entry["sha256"] = sha256_hex(data)
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
        if "loaded" in doc:  # reference to another plan, resolved by refs.resolve
            refs.append({key: copy.deepcopy(doc[key]) for key in _FOREIGN_KEYS if key in doc})  # exec/v1 is closed
        else:
            refs.append({"ref": doc["id"], "loaded": True,
                         **{key: doc[key] for key in _DECISION_KEYS if doc.get(key) is not None}})
    return refs


def _unresolved(plan: store.Plan, pack: dict) -> list[str]:
    """Other-plan decisions the item requires that did not load as accepted; the coordinator must not guess them."""
    required = set(pack["item"].get("decisions", []))
    return [f"{d['ref']} ({d.get('reason') or 'status ' + str(d.get('status'))})" for d in pack["decisions"]
            if d.get("ref") in required and context.parse_ref(d["ref"]).plan is not None
            and (not d.get("loaded") or d.get("status") != "accepted")]


def _checks(item: dict, unit: dict | None, plan: store.Plan | None = None, item_id: str | None = None) -> list[dict]:
    """The checks of the input; the item that closes its phase (every other item of the phase is terminal) also gets
    the broad checks of the phase (``phase.validation``) marked ``cadence: phase``: the full pass runs there, once."""
    if unit is None:
        checks = copy.deepcopy(item.get("validation", []))
        if plan is not None and item_id is not None:
            checks += _phase_checks(plan, item_id, {c.get("id") for c in checks if isinstance(c, dict)})
        return checks
    by_id = {c["id"]: c for c in item.get("validation", [])}  # as units.brief
    return [copy.deepcopy(by_id[c] if isinstance(c, str) else c) for c in unit.get("checks", [])]


def _phase_checks(plan: store.Plan, item_id: str, taken: set) -> list[dict]:
    phase = plan.phases.get(item_phase(item_id), {})
    broad = [c for c in phase.get("validation") or [] if isinstance(c, dict) and c.get("id") not in taken]
    if not broad:
        return []
    others = [i for i in phase.get("items") or [] if isinstance(i, str) and i != item_id and i in plan.items]
    if any(plan.items[i].get("status", "todo") not in TERMINAL for i in others):
        return []
    return [dict(copy.deepcopy(check), cadence="phase") for check in broad]


def _context_refs(plan: store.Plan, pack: dict, plan_dir: str) -> list[dict]:
    refs = [{"kind": "pack", "ref": pack["ref"], "path": f"{plan_dir}/{context.PACK_DIR}/{pack['item']['id']}.json"}]
    for doc in pack["documents"]:
        ref = {"kind": "document", "ref": f"knowledge/{doc['id']}", "path": f"{plan_dir}/knowledge/{doc['id']}.json"}
        source = plan.path("document", doc["id"])
        if source.is_file():
            ref["sha256"] = sha256_hex(source.read_bytes())
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


def _strings(value, path=""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _strings(child, f"{path}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _strings(child, f"{path}/{index}")


def verify(plan: store.Plan, item_id: str, doc: dict, *, unit_id: str | None = None) -> list[str]:
    """Omissions of ``doc`` against its sources (knowledge/task-changes, T2): ``"<field>: <what is missing>"`` lines."""
    item = plan.items[item_id]
    unit = plan.units[f"{item_id}/{unit_id}"] if unit_id else None
    phase = plan.phases.get(item_phase(item_id), {})
    missing = []
    checks = doc.get("acceptance", {}).get("checks", [])
    expected = _checks(item, unit, plan, item_id)
    if not expected:
        missing.append("acceptance.checks: no acceptance check")
    for check in expected:
        if check not in checks:
            missing.append(f"acceptance.checks: missing {check.get('id', check) if isinstance(check, dict) else check}")
    constraints = doc.get("constraints", [])
    for source, texts in (("plan.rules", plan.plan.get("rules")), ("phase.pitfalls", phase.get("pitfalls")),
                          ("item.rules", item.get("rules"))):
        for index, text in enumerate(texts or []):
            if {"text": text, "source": f"{source}[{index}]"} not in constraints:
                missing.append(f"constraints: missing {source}[{index}]")
    if unit and unit.get("instructions") and {"text": unit["instructions"], "source": "unit.instructions"} not in constraints:
        missing.append("constraints: missing unit.instructions")
    reads = {(r.get("path"), r.get("section")) for r in doc.get("reads", [])}
    for read in (item.get("reads") or []) + ((unit or {}).get("reads") or []):
        read = context.normalize_read(plan, read)
        if read.get("required") and (read.get("path"), read.get("section")) not in reads:
            missing.append(f"reads: missing {read.get('path') or read.get('ref')}"
                           + (f"#{read['section']}" if read.get("section") else ""))
    refs = {d.get("ref") for d in doc.get("decisions", [])}
    for ref in item.get("decisions", []):
        parsed = context.parse_ref(ref)
        if (parsed.target if parsed.plan is None and parsed.target in plan.decisions else ref) not in refs:
            missing.append(f"decisions: missing {ref}")
    scope, source_scope = doc.get("scope", {}), item["scope"]
    if scope.get("include") != source_scope["include"]:
        missing.append("scope.include: differs from the item")
    if scope.get("exclude") != source_scope.get("exclude", []):
        missing.append("scope.exclude: differs from the item")
    if not str(doc.get("goal") or "").strip():
        missing.append("goal: empty")
    if not (doc.get("route") or {}).get("minimum"):
        missing.append("route.minimum: missing")
    if doc.get("acceptance", {}).get("deliverables", []) != item.get("deliverables", []):
        missing.append("deliverables: differ from the item")
    plan_rules = {f"/constraints/{i}/text" for i, c in enumerate(constraints)
                  if isinstance(c, dict) and str(c.get("source", "")).startswith("plan.rules")}
    for path, text in _strings(doc):
        if path.startswith("/provenance") or path in plan_rules:
            continue
        phrase = next((p for p in LIFECYCLE_PHRASES if p in text), None)
        if phrase:
            missing.append(f"{path}: lifecycle phrase {phrase!r}")
    return missing


def build(plan: store.Plan, item_id: str, *, unit_id: str | None = None, inline_reads: bool = False,
          repos=None) -> dict:
    """Execution-input of ``item_id`` (or of its unit ``unit_id``). ``repos`` maps repository names to roots (``refs.resolve``)."""
    if not isinstance(item_id, str) or not ITEM_ID.fullmatch(item_id):
        raise PlanError("REF_INVALID", f"invalid item id {item_id!r}")
    if item_id not in plan.items:
        raise PlanError("REF_UNKNOWN", f"unknown item {item_id!r}")
    unit = None
    if unit_id is not None:
        if not isinstance(unit_id, str) or not _UNIT_ID.fullmatch(unit_id):
            raise PlanError("REF_INVALID", f"invalid unit id {unit_id!r}")
        if f"{item_id}/{unit_id}" not in plan.units:
            raise PlanError("REF_UNKNOWN", f"unknown unit {item_id}/{unit_id!r}")
        unit = plan.units[f"{item_id}/{unit_id}"]
    phase_id = item_phase(item_id)
    if plan.phases.get(phase_id, {}).get("design") == "skeleton":
        raise PlanError("PHASE_NOT_DETAILED", f"{phase_id} is a skeleton; detail it before briefing {item_id}")
    missing = context.missing_reads(plan, item_id)
    if missing:
        raise PlanError("READ_MISSING", f"required reads are missing: {', '.join(missing)}")
    pack = context.collect(plan, item_id, with_scout=True, repos=repos)
    unresolved = _unresolved(plan, pack)
    if unresolved:
        raise PlanError("REF_UNRESOLVED", f"required decisions of other plans are not resolved: {'; '.join(unresolved)}")
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
                       "source_digest": sha256_hex(context.render(plan, item_id, with_scout=False, repos=repos).encode("utf-8")),
                       "generated_by": {"tool": TOOL, "task_version": _task_version()}},
        "goal": unit["goal"] if unit is not None else f"{item['title']}: {item['summary']}",
        "scope": scope,
        "acceptance": {"checks": _checks(item, unit, plan, item_id), "deliverables": copy.deepcopy(item.get("deliverables", []))},
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
    missing = verify(plan, item_id, doc, unit_id=unit_id)
    if missing:
        raise PlanError("BRIEF_INCOMPLETE", "; ".join(missing))
    doc["digest"] = canonical_digest(doc)
    doc["input_id"] += f"@{doc['digest'][:12]}"
    return doc


def render(plan: store.Plan, item_id: str, *, unit_id: str | None = None, inline_reads: bool = False,
           repos=None) -> str:
    doc = build(plan, item_id, unit_id=unit_id, inline_reads=inline_reads, repos=repos)
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def check_out(plan: store.Plan, out: str | Path) -> Path:
    """Destination of ``--out``: a new or existing file outside the plan directory (plan data is written by the API only)."""
    if not str(out).strip():
        raise PlanError("OUT_INVALID", "--out needs a file path")
    target = Path(out).expanduser().resolve()
    if target.is_dir():
        raise PlanError("OUT_INVALID", f"{out} is a directory; name a file")
    try:
        target.relative_to(plan.root.resolve())
    except ValueError:
        return target
    raise PlanError("OUT_INVALID", f"{out} is inside the plan directory; plan files are written only by plan.py verbs")


def write(plan: store.Plan, item_id: str, out: str | Path, *, unit_id: str | None = None,
          inline_reads: bool = False, repos=None) -> Path:
    """Build, then atomically write the brief to ``out``; every refusal happens before anything is written."""
    target = check_out(plan, out)
    store.atomic_write(target, render(plan, item_id, unit_id=unit_id, inline_reads=inline_reads, repos=repos))
    return target


def _repo_mapping(text: str) -> tuple[str, str]:
    name, sep, path = text.partition("=")
    if not sep or not re.fullmatch(r"[a-z0-9-]+", name) or not path:
        raise argparse.ArgumentTypeError("expected NAME=PATH, for example swissknifeman=/work/swissknifeman")
    return name, path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="plan.py bridge planner-orch brief",
                                     description="execution-input (exec/v1) of an item or unit, read-only")
    parser.add_argument("plan", help="plan id, PLAN<N> or path")
    parser.add_argument("item")
    parser.add_argument("--unit", metavar="U#", help="brief one unit of the item")
    parser.add_argument("--inline-reads", action="store_true", help="embed the full text of existing text reads")
    parser.add_argument("--out", type=Path, help="write the document to FILE instead of stdout")
    parser.add_argument("--repo", action="append", default=[], type=_repo_mapping, metavar="NAME=PATH",
                        help="repository root of references to another repository (repeatable)")
    parser.add_argument("--plans-root", type=Path, default=None, help="plans/ directory (default: nearest up from cwd)")
    args = parser.parse_args(argv)
    try:
        plan = store.load_plan(store.resolve_plan_dir(args.plan, args.plans_root))
        if args.out is None:
            print(render(plan, args.item, unit_id=args.unit, inline_reads=args.inline_reads, repos=dict(args.repo)),
                  end="")
        else:
            print(write(plan, args.item, args.out, unit_id=args.unit, inline_reads=args.inline_reads,
                        repos=dict(args.repo)))
    except PlanError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"IO_ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
