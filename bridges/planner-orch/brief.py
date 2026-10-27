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
import os
from pathlib import Path
import re
import sys

import partners

partners.use_aicore()
from aicore.util.digest import canonical_json_bytes, sha256_hex  # noqa: E402

context, store, _model, _workspace = partners.planner_engine("plan.context", "plan.store", "plan.model",
                                                             "plan.workspace")
ITEM_ID, PlanError, item_phase = _model.ITEM_ID, _model.PlanError, _model.item_phase
TERMINAL = {str(getattr(status, "value", status)) for status in _model.TERMINAL}

SCHEMA = "urn:swissknifeman:orch:exec:execution-input:v1"
CONTRACT_VERSION = "exec/v1"
TOOL = "planner-orch brief"
REPORT = ["summary", "changed_paths", "checks_run", "evidence", "open_issues"]
ESCALATION = ["A required read is missing or contradicts the goal",
              "An acceptance check cannot pass without leaving scope"]
# Lifecycle commands the executor must never be told to run. The text of a plan may still *describe* them (a rule that
# says what must hold "before plan.py finish", a gate of the execution model): only an instruction to run one is refused.
LIFECYCLE_COMMANDS = ("plan.py start", "plan.py finish", "unit return", "planner:plan-run")
# The report API is a capability the executor does not have; any mention of it is refused.
LIFECYCLE_NAMES = ("report_api", "report API")
LIFECYCLE_PHRASES = LIFECYCLE_NAMES + LIFECYCLE_COMMANDS
_RUN_WORD = re.compile(
    r"\b(?:run|runs|running|execute|exec|call|calls|invoke|launch|issue|type|enter|apply|use|then|"
    r"запусти\w*|запуск\w*|вызов\w*|вызыв\w*|выполни\w*|исполни\w*|используй\w*|введи\w*|набери\w*|примени\w*)\b", re.I)
_NEGATION = re.compile(r"\b(?:never|not|no|don't|dont|mustn't|avoid|without|не|нельзя|никогда|запрещ\w*|без)\b|\bdo not\b", re.I)
_TEMPORAL = re.compile(r"(?:before|after|prior to|until|once|перед|до|после|пока)[\s`'\"«(]*$", re.I)  # names a moment
_SHELL_PREFIX = re.compile(r"(?:^|\s)(?:\$\s*|python3?\s+(?:\S*/)?)$")
_TOKEN = re.compile(r"[a-z][a-z0-9_]*", re.ASCII)  # a denied input of a role manifest is a bare token, not a sentence
_UNIT_ID = re.compile(r"^U[0-9]+$", re.ASCII)
_DECISION_KEYS = ("title", "status", "decision", "rationale")
_FOREIGN_KEYS = ("ref", "loaded", *_DECISION_KEYS, "question_key", "question_digest", "source", "reason")
_PACK_PROCESS_KEYS = ("batch", "orchestration", "ready_units", "policy")  # lifecycle and run policy: never the executor's
_LESSON_KEYS = ("type", "summary", "ts", "item", "impact", "next")
# Supplemental delivery is a worker view, not the coordinator pack. New source fields never gain delivery implicitly.
_WORKER_FIELDS = {
    "plan": ("id", "short_id", "title", "repository", "goal", "context", "non_goals", "rules", "links", "contracts", "sections"),
    "brief": ("requirements", "constraints", "environment", "out_of_scope", "sections"),
    "phase": ("id", "title", "goal", "context", "contract", "scope", "pitfalls", "validation", "deliverables",
              "assurance", "supporting", "sections"),
    "item": ("id", "title", "summary", "why", "scope", "depends_on", "related", "decisions", "skills", "task_files",
             "artifacts", "rules", "guidance", "examples", "validation", "deliverables", "authority", "sections"),
    "decision": ("id", "ref", "loaded", "title", "status", "decision", "rationale", "reason"),
    "document": ("id", "title", "sections", "applies_to", "global"),
}


def _worker_context(pack: dict) -> dict:
    """Missing worker contracts only; lifecycle, messages, actor records and other-item unit/run state stay with coordinator.

    Reads, lessons, route/review/research settings and the current unit's instructions already have their closed exec/v1
    projections. Their raw coordinator records must not acquire a second, wider authority through supplemental delivery.
    """
    def select(kind, value):
        return {key: copy.deepcopy(value[key]) for key in _WORKER_FIELDS[kind] if key in value}

    result = {kind: select(kind, pack[kind]) for kind in ("plan", "brief", "phase", "item")}
    # Runtime input declarations are coordinator provenance, not additional worker reads.
    if "artifacts" in result["item"]:
        result["item"]["artifacts"] = [a for a in result["item"]["artifacts"]
                                        if not (a.get("role") == "input" and str(a.get("path", "")).startswith("@plan/inputs/"))]
    item = pack["item"]
    if item.get("route"):
        result["item"]["route"] = _route_minimum(item["route"])
    if _research(item):
        result["item"]["research"] = _research(item)
    review = item.get("review") or {}
    if review:
        result["item"]["review"] = {key: copy.deepcopy(review[key]) for key in ("mode", "covers") if key in review}
    result["decisions"] = [select("decision", value) for value in pack.get("decisions", [])]
    result["documents"] = [select("document", value) for value in pack.get("documents", [])]
    result["phase_dependencies"] = [select("phase", value) for value in pack.get("phase_dependencies", [])]
    # The existing scoped outcome includes unresolved deviations/pending/escalations, never a fabricated green summary.
    result["upstream"] = [context._project_upstream(value) for value in pack.get("upstream", [])]
    return result


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


def _outside(plan: store.Plan) -> bool:
    """The plan directory is not inside its checkout (a plan in the workspace): the executor cannot read the plan files."""
    source = plan.source_root
    return source is None or not plan.root.resolve().is_relative_to(source.resolve())


def _plan_dir(plan: store.Plan) -> str:
    if _outside(plan):
        return "@plan"  # no absolute path of the workspace enters the brief
    try:
        return plan.root.resolve().relative_to(plan.repo_root.resolve()).as_posix()
    except ValueError:
        return plan.root.as_posix()


def _json_safe(value):
    """``value`` as it enters a canonical document: a value with floats travels as its JSON text."""
    if _has_float(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return copy.deepcopy(value)


def _scrub(value, secret: str):
    """``value`` with every occurrence of the absolute workspace path replaced by ``@workspace``."""
    if isinstance(value, str):
        # only a whole path: not the tail of a longer or relative path, not the head of a longer name
        return re.sub(r"(?<![\w.\-/])" + re.escape(secret) + r"(?![\w.\-])", "@workspace", value)
    if isinstance(value, dict):
        return {key: _scrub(child, secret) for key, child in value.items()}
    if isinstance(value, list):
        return [_scrub(child, secret) for child in value]
    return value


def _has_float(value) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_has_float(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_float(item) for item in value)
    return False


def _read(plan: store.Plan, entry: dict, inline: bool, *, outside: bool = False) -> dict:
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
        entry["error"] = "unreadable" if outside else str(exc)  # an OS message can carry the workspace path
        return entry
    entry["sha256"] = sha256_hex(data)
    if inline and "content" not in entry and "error" not in entry:
        try:
            entry["content"] = data.decode("utf-8")
        except UnicodeDecodeError:
            entry["error"] = "not-text" if outside else "binary or non-utf8"
    return entry


def _plan_content(plan: store.Plan, entry: dict) -> dict:
    """A plan read the pack already holds elsewhere (``included``) has no content; the executor gets its own text (the
    selected section of a document, not the whole of it)."""
    path = entry.get("path")
    if not (isinstance(path, str) and path.startswith("@plan/") and entry.get("included")):
        return entry
    again = {key: value for key, value in entry.items() if key not in ("included", "content", "exists", "sha256")}
    return context.read_entry(plan, again)


def _research(item: dict) -> dict | None:
    """The research need the designer set on the item (``rag.need``, ``rag.notes``); ``status`` and ``captures`` are plan state."""
    rag = item.get("rag")
    if not isinstance(rag, dict) or not rag.get("need"):
        return None
    return {"need": rag["need"], **({"notes": rag["notes"]} if rag.get("notes") else {})}


_ROUTE_KEYS = ("class", "effort", "provider", "model")  # exec/v1 $defs/route is closed


def _route_minimum(route: dict | None) -> dict:
    """The route of an item or unit projected to the exec/v1 minimum route: ``route.correction`` and ``route.settings`` of the
    plan stay out of the execution input (the claim answer carries the correction to the conductor)."""
    source = route or {}
    return {key: source[key] for key in _ROUTE_KEYS if key in source}


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
            origin = doc.get("origin") or {}  # a decision an orchestration run recorded names the question it answered
            refs.append({"ref": doc["id"], "loaded": True,
                         **{key: doc[key] for key in _DECISION_KEYS if doc.get(key) is not None},
                         **{key: origin[key] for key in ("question_key", "question_digest") if origin.get(key)}})
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


def _context_refs(plan: store.Plan, pack: dict, plan_dir: str, outside: bool = False,
                  context_delivery: str = "reference") -> list[dict]:
    refs = [{"kind": "pack", "ref": pack["ref"], "path": f"{plan_dir}/{context.PACK_DIR}/{pack['item']['id']}.json"}]
    if outside:  # the executor cannot open the pack file: it travels in the brief
        refs[0]["content"] = _json_safe(_worker_context(pack) if context_delivery == "supplement"
                                      else {k: v for k, v in pack.items() if k not in _PACK_PROCESS_KEYS})
        if context_delivery == "supplement":
            refs[0]["delivery"] = "supplement"
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


def lifecycle_phrase(text: str) -> str | None:
    """The lifecycle phrase ``text`` uses as an instruction, else None. ``report_api`` is refused wherever it appears. A
    lifecycle command is refused when the text tells the reader to run it: a run word before it in the same sentence
    (``run``, ``запусти``, ...) that no negation (``never``, ``не``) turns into a prohibition, a shell prompt or
    ``python plan.py`` in front of it, or a place inside a fenced code block. A description of a gate that only names it
    ("before plan.py finish: the checks are green") is no instruction."""
    name = next((phrase for phrase in LIFECYCLE_NAMES if phrase in text), None)
    if name:
        return name
    for phrase in LIFECYCLE_COMMANDS:
        for found in re.finditer(re.escape(phrase), text):
            before = text[:found.start()]
            clause = re.split(r"[.;!?\n]", before)[-1]
            if _SHELL_PREFIX.search(clause) or before.count("```") % 2 == 1:
                return phrase
            if _TEMPORAL.search(clause):
                continue  # "run the checks before plan.py finish" names the moment, it does not call the command
            if _RUN_WORD.search(clause) and not _NEGATION.search(clause):
                return phrase
    return None


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
        if path.startswith("/provenance") or path in plan_rules or ("/forbidden_inputs/" in path and _TOKEN.fullmatch(text)):
            continue  # a role manifest read by an item names the lifecycle inputs it is denied; that is data, not instruction
        phrase = lifecycle_phrase(text)
        if phrase:
            missing.append(f"{path}: lifecycle phrase {phrase!r}")
    return missing


def build(plan: store.Plan, item_id: str, *, unit_id: str | None = None, inline_reads: bool = False,
          repos=None, context_delivery: str = "reference") -> dict:
    """Execution-input of ``item_id`` (or of its unit ``unit_id``). ``repos`` maps repository names to roots (``refs.resolve``)."""
    if context_delivery not in ("reference", "supplement"):
        raise PlanError("CONTEXT_DELIVERY_INVALID", f"unknown context delivery {context_delivery!r}")
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
    # Like ``start``, check the required reads at the first claim only: an item in progress passed the check when it
    # started, and its own work may have deleted a read (a file the item retires).
    missing = [] if plan.items[item_id].get("status") == "in_progress" else context.missing_reads(plan, item_id)
    if missing:
        raise PlanError("READ_MISSING", f"required reads are missing: {', '.join(missing)}")
    pack = context.collect(plan, item_id, with_scout=True, repos=repos)
    unresolved = _unresolved(plan, pack)
    if unresolved:
        raise PlanError("REF_UNRESOLVED", f"required decisions of other plans are not resolved: {'; '.join(unresolved)}")
    item, short = pack["item"], plan.plan.get("short_id") or plan.plan["id"]
    outside = _outside(plan)
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
        "route": {"minimum": _route_minimum((unit if unit is not None else item).get("route"))},
        "result_contract": {"report": list(REPORT), "write_authority": "none" if read_only else "code_scope",
                            "commit_owner": "coordinator", "plan_mutation": "forbidden"},
        "escalation": escalation,
    }
    optional = {
        "why": item.get("why"), "guidance": item.get("guidance"), "sections": copy.deepcopy(item.get("sections")),
        "constraints": _constraints(pack, unit), "decisions": _decisions(pack),
        "reads": [_read(plan, _plan_content(plan, r) if outside else r,
                        inline_reads or (outside and str(r.get("path", "")).startswith("@plan/")), outside=outside)
                  for r in reads],
        "context_refs": _context_refs(plan, pack, plan_dir, outside, context_delivery), "upstream": _upstream(pack),
        "lessons": [{key: e[key] for key in _LESSON_KEYS if key in e} for e in pack["lessons"]],
        "hints": [{"text": _hint(entry), "source": "scout"} for entry in (pack.get("scout") or {}).get("entries", [])],
        "research": _research(item),
        "review_mode": (item.get("review") or {}).get("mode"),
        "review_route": _review_route(item), "review_rounds_max": (item.get("review") or {}).get("rounds_max"),
    }
    doc.update({key: value for key, value in optional.items() if value})
    missing = verify(plan, item_id, doc, unit_id=unit_id)
    if missing:
        raise PlanError("BRIEF_INCOMPLETE", "; ".join(missing))
    if outside:
        for secret in {str(_workspace.workspaces_root()), str(_workspace.workspaces_root().resolve())}:
            doc = _scrub(doc, secret)
    doc["digest"] = canonical_digest(doc)
    doc["input_id"] += f"@{doc['digest'][:12]}"
    return doc


def _hint(entry: dict) -> str:
    """A scout-map entry of the pack (``{path, symbol?, why}``) as the hint line ``path[:symbol] — why``; an entry that
    names no path is its text."""
    if not entry.get("path"):
        return entry["why"]
    return entry["path"] + (f":{entry['symbol']}" if entry.get("symbol") else "") + " — " + entry["why"]


def _review_route(item: dict) -> dict:
    """The reviewer the plan prefers for the item (``review.reviewer`` without its note); the conductor uses it when the run
    sets no reviewer of its own."""
    reviewer = (item.get("review") or {}).get("reviewer") or {}
    return {key: reviewer[key] for key in ("class", "provider", "model", "effort") if reviewer.get(key)}


def render(plan: store.Plan, item_id: str, *, unit_id: str | None = None, inline_reads: bool = False,
           repos=None, context_delivery: str = "reference") -> str:
    doc = build(plan, item_id, unit_id=unit_id, inline_reads=inline_reads, repos=repos, context_delivery=context_delivery)
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
          inline_reads: bool = False, repos=None, context_delivery: str = "reference") -> Path:
    """Build, then atomically write the brief to ``out``; every refusal happens before anything is written."""
    target = check_out(plan, out)
    store.atomic_write(target, render(plan, item_id, unit_id=unit_id, inline_reads=inline_reads, repos=repos,
                                     context_delivery=context_delivery))
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
    parser.add_argument("--context-delivery", choices=("reference", "supplement"),
                        default=os.environ.get("PLANNER_ORCH_CONTEXT_DELIVERY", "reference"),
                        help="workspace pack delivery (default: reference; env PLANNER_ORCH_CONTEXT_DELIVERY)")
    parser.add_argument("--out", type=Path, help="write the document to FILE instead of stdout")
    parser.add_argument("--repo", action="append", default=[], type=_repo_mapping, metavar="NAME=PATH",
                        help="repository root of references to another repository (repeatable)")
    parser.add_argument("--plans-root", type=Path, default=None, help="plans/ directory (default: nearest up from cwd)")
    args = parser.parse_args(argv)
    try:
        plan = store.load_plan(store.resolve_plan_dir(args.plan, args.plans_root))
        if args.out is None:
            print(render(plan, args.item, unit_id=args.unit, inline_reads=args.inline_reads, repos=dict(args.repo),
                         context_delivery=args.context_delivery),
                  end="")
        else:
            print(write(plan, args.item, args.out, unit_id=args.unit, inline_reads=args.inline_reads,
                        repos=dict(args.repo), context_delivery=args.context_delivery))
    except PlanError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"IO_ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
