"""Deterministic, complete JSON input for an executor. Human views never supply context."""
from __future__ import annotations

import copy
import glob
import json
from pathlib import Path
import re

from . import edges, execution, refs, settings, store
from .model import ITEM_ID, TERMINAL, PlanError, item_phase, parse_ref

PACK_DIR = "context"
LESSON_TYPES = ("deviation", "blocker", "difficulty", "assumption")
PACK_MODES = ("legacy", "scoped")
UPSTREAM_KEYS = ("id", "title", "status", "summary", "deliverables", "artifacts")
RESULT_KEYS = ("notes", "deviations", "pending", "escalation", "commits")
PHASE_KEYS = ("id", "title", "goal", "deliverables", "contract", "closed")
PROJECTION_NOTE = ("reads[].included names the pack key that already holds the source; "
                   "upstream and phase_dependencies are summaries, read them by ref for the full record")


def pack_mode(plan: store.Plan) -> str:
    """``settings.context_pack``; a plan that does not set it keeps the legacy pack."""
    mode = plan.plan.get("settings", {}).get("context_pack")
    return mode if mode in PACK_MODES else "legacy"


def budget_bytes(plan: store.Plan) -> int:
    """The pack size warning threshold in bytes; it is a report limit, never a trim."""
    return settings.for_plan(plan).get("context.budget_kb") * 1024


def policy(plan: store.Plan) -> dict:
    """The loop policies the commands follow: review rounds per item and owning corrections per review."""
    config = settings.for_plan(plan)
    return {"review_rounds_max": config.get("policy.review_rounds_max"),
            "corrections_max": config.get("policy.corrections_max")}


def scope_reason(doc: dict, item_id: str, phase_id: str, mode: str) -> str | None:
    """Why a document or decision reaches the pack of ``item_id``: item, phase, global, unbound (legacy only) or None."""
    applies = doc.get("applies_to") or []
    if item_id in applies:
        return "item"
    if phase_id in applies:
        return "phase"
    if doc.get("global") is True:
        return "global"
    if not applies and mode == "legacy":
        return "unbound"
    return None


def extract_section(text: str, section: str) -> str | None:
    """Select a supporting Markdown section, including children and ignoring fenced headings."""
    headings, fenced = [], False
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
        elif not fenced and (match := re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)):
            headings.append((index, len(match[1]), match[2]))
    plain = lambda t: " ".join(re.sub(r"[`*_]", "", t).split()).lower()
    number = re.match(r"^§\s*(\d+(?:\.\d+)*)", section)
    target = plain(section)
    for mode in range(3):
        for position, (start, level, title) in enumerate(headings):
            match = re.match(r"^(?:§\s*)?(\d+(?:\.\d+)*)\.?(?=\s|$)", title)
            matches = (bool(match and match[1] == number[1]) if number else
                       (plain(title) == target if mode == 0 else
                        plain(title).startswith(target) if mode == 1 else target in plain(title)))
            if matches:
                end = next((i for i, other, _ in headings[position + 1:] if other <= level), len(lines))
                return "\n".join(lines[start + 1:end]).strip("\n")
    return None


def _resolve(plan: store.Plan, path: str) -> Path | None:
    rel = path.removeprefix("@plan/")
    if ".." in re.split(r"[\\/]", rel) or rel.startswith(("/", "~")):
        return None
    base = plan.root if path.startswith("@plan/") else plan.source_root
    if base is None:  # no checkout bound on this machine: a repository path has no base
        return None
    target = base / rel
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError:
        return None
    return target


def human_view(plan: store.Plan, path: str) -> bool:
    """Plan Markdown and anything under a human-view directory cannot supply agent input."""
    target = _resolve(plan, path)
    if target is None:
        return False
    resolved = target.resolve()
    roots = [plan.root.resolve()]
    roots += [p for p in resolved.parents if (p / "plan.json").is_file() and p != roots[0]]
    for root in roots:
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            continue
        return relative.parts[:1] == ("views",) or relative.suffix.lower() == ".md"
    return False


def _exists(plan: store.Plan, path: str) -> bool:
    target = _resolve(plan, path)
    return bool(target and (glob.glob(str(target)) if re.search(r"[*?\[]", path) else target.exists()))


def _reads(item: dict) -> list[dict]:
    return [r for r in item.get("reads", []) if isinstance(r, dict)
            and (isinstance(r.get("path"), str) or isinstance(r.get("ref"), str))]


def normalize_read(plan: store.Plan, read: dict) -> dict:
    """A read by ``ref`` becomes the read of its JSON source by ``path`` (the ``ref`` is kept); a path read is returned
    as is. A ref that does not resolve to a source gets no ``path``."""
    ref = read.get("ref")
    if not isinstance(ref, str):
        return read
    entry = copy.deepcopy(read)
    try:
        parsed = parse_ref(ref)
    except ValueError:
        return entry
    path = None
    if parsed.plan is None:
        if parsed.kind == "knowledge":
            source = plan.path("document", parsed.target)
        elif parsed.kind == "artifact":
            found = edges.locate(plan, ref)
            source = found.get("path") if found else None
        else:
            source = plan.path(parsed.kind, parsed.target)
        path = f"@plan/{plan.rel(source)}" if isinstance(source, Path) else source
    if path:
        entry["path"] = path
    if parsed.section and not entry.get("section"):
        entry["section"] = parsed.section
    return entry


def _pending_producer(plan: store.Plan, item_id: str, path: str) -> str | None:
    seen, stack = set(), list(plan.items[item_id].get("depends_on", []))
    while stack:
        dep = stack.pop()
        if dep in seen or dep not in plan.items:
            continue
        seen.add(dep)
        doc = plan.items[dep]
        # An open dependency produces the path when it declares it as an output artifact or as a file it creates.
        if doc.get("status") not in TERMINAL and (
                any(a.get("role") == "output" and a.get("path") == path for a in doc.get("artifacts", []))
                or any(t.get("change") == "create" and t.get("path") == path for t in doc.get("task_files", []))):
            return dep
        stack.extend(doc.get("depends_on", []))
    return None


def missing_reads(plan: store.Plan, item_id: str) -> list[str]:
    missing = []
    unbound = plan.source_root is None
    for read in _reads(plan.items[item_id]):
        if not read.get("required"):
            continue
        path = normalize_read(plan, read).get("path")
        if unbound and isinstance(path, str) and not path.startswith("@plan/"):
            continue  # repository path without a bound checkout: cannot be verified (check warns source_unbound)
        exists = path is not None and _exists(plan, path)
        if path is None or (not exists and _pending_producer(plan, item_id, path) is None):
            missing.append(path or read["ref"])
        elif read.get("ref") and exists and read_entry(plan, read).get("error"):
            # An existing JSON source does not guarantee that its required section is readable.
            missing.append(read["ref"] + (f"#{read['section']}" if read.get("section") else ""))
    return missing


def read_entry(plan: store.Plan, read: dict) -> dict:
    """Inline requested supporting sections, with no reading quota or content truncation."""
    read = normalize_read(plan, read)
    path = read.get("path")
    if path is None:  # a ref that names no readable source
        return {**copy.deepcopy(read), "exists": False}
    if human_view(plan, path):
        raise PlanError("HUMAN_VIEW", f"{path} is human-only plan content; reference its JSON source")
    entry = copy.deepcopy(read)
    target = _resolve(plan, path)
    entry["exists"] = _exists(plan, path)
    if not target or not target.is_file():
        return entry
    try:
        if path.endswith(".json"):
            value = json.loads(target.read_text(encoding="utf-8"))
            if read.get("section") and isinstance(value, dict) and "sections" in value:
                sections = value["sections"] if isinstance(value["sections"], list) else []
                fragment = parse_ref(read["ref"]).section if read.get("ref") else None
                selected = [s for s in sections if isinstance(s, dict) and
                            (s.get("id") == read["section"] or (not fragment and s.get("title") == read["section"]))]
                if not selected:
                    entry["error"] = "section not found"
                value = {**value, "sections": selected}
            entry["content"] = value
        elif read.get("section") and path.endswith(".md"):
            value = extract_section(target.read_text(encoding="utf-8"), read["section"])
            if value is None:
                entry["error"] = "section not found"
            else:
                entry["content"] = value
    except (OSError, ValueError) as exc:
        entry["error"] = str(exc)
    return entry


def selected_decisions(plan: store.Plan, item_id: str, *, repos=None) -> list[dict]:
    selected, foreign = [], []
    item = plan.items[item_id]
    for ref in item.get("decisions", []):
        parsed = parse_ref(ref)
        if parsed.plan is None and parsed.target in plan.decisions:
            selected.append(parsed.target)
        else:
            foreign.append(refs.resolve(plan, ref, repos=repos))
    mode, phase_id = pack_mode(plan), item_phase(item_id)
    for key, doc in plan.decisions.items():
        if doc.get("status") == "accepted" and scope_reason(doc, item_id, phase_id, mode) is not None:
            selected.append(key)
    return [copy.deepcopy(plan.decisions[k]) for k in dict.fromkeys(selected)] + foreign


def _summary(doc: dict, keys: tuple) -> dict:
    return {k: copy.deepcopy(doc[k]) for k in keys if k in doc}


def _project_upstream(doc: dict) -> dict:
    """A finished dependency as the executor needs it: identity, summary, deliverables and the outcome."""
    entry = _summary(doc, UPSTREAM_KEYS)
    result = doc.get("result")
    outcome = _summary(result, RESULT_KEYS) if isinstance(result, dict) else {}
    if outcome:
        entry["result"] = outcome
    return entry


def _project_phase(doc: dict) -> dict:
    return _summary(doc, PHASE_KEYS)


def _source_key(plan: store.Plan, item_id: str, pack: dict, path: str) -> str | None:
    """The pack key that already holds the JSON source at ``path``, if any."""
    held = {f"@plan/{plan.rel(plan.path('plan'))}": "plan", f"@plan/{plan.rel(plan.path('brief'))}": "brief",
            f"@plan/{plan.rel(plan.path('phase', item_phase(item_id)))}": "phase",
            f"@plan/{plan.rel(plan.path('item', item_id))}": "item"}
    held.update({f"@plan/{plan.rel(plan.path('document', d['id']))}": "documents"
                 for d in pack["documents"] if "id" in d})
    held.update({f"@plan/{plan.rel(plan.path('decision', d['id']))}": "decisions"
                 for d in pack["decisions"] if isinstance(d.get("id"), str) and d["id"] in plan.decisions})
    return held.get(path)


def duplicate_target(plan: store.Plan, item_id: str, pack: dict, index: int) -> str | None:
    """Where ``pack["reads"][index]`` already lives in the pack: a pack key, ``reads/<j>`` (the first read of the same
    path and section), or None. A read of a dependency file is an explicit request for the full record and stays."""
    entry = pack["reads"][index]
    path = entry.get("path")
    if not isinstance(path, str):
        return None
    key = _source_key(plan, item_id, pack, path)
    if key:
        return key
    for earlier in range(index):
        other = pack["reads"][earlier]
        if other.get("path") == path and other.get("section") == entry.get("section"):
            return f"reads/{earlier}"
    return None


def _dedupe_reads(plan: store.Plan, item_id: str, pack: dict) -> None:
    """Replace the content of a read that the pack already carries with the key that holds it."""
    targets = [duplicate_target(plan, item_id, pack, i) for i in range(len(pack["reads"]))]
    for entry, target in zip(pack["reads"], targets):
        if target:
            entry.pop("content", None)
            entry["included"] = target


def collect(plan: store.Plan, item_id: str, *, with_scout: bool = True, repos=None) -> dict:
    if item_id not in plan.items:
        raise PlanError("REF_UNKNOWN", f"unknown item {item_id!r}")
    from . import lifecycle, units

    item, phase_id, mode = plan.items[item_id], item_phase(item_id), pack_mode(plan)
    related = [r["ref"] for r in item.get("related", [])]
    upstream = [copy.deepcopy(plan.items[d]) for d in dict.fromkeys([*item.get("depends_on", []), *related])
                if d in plan.items]
    near = {d["id"] for d in upstream}
    lessons = []
    for event in store.read_log(plan.root):
        target = event.get("item")
        phase = event.get("phase") or (item_phase(target) if target and ITEM_ID.fullmatch(target) else None)
        if event.get("type") in LESSON_TYPES and (phase == phase_id or target in near):
            lessons.append(event)
    name, source = execution.scenario(plan, item_id)
    result = {
        "ref": f"{plan.plan.get('short_id') or plan.plan['id']}.{item_id}", "plan": copy.deepcopy(plan.plan),
        "brief": copy.deepcopy(plan.brief), "phase": copy.deepcopy(plan.phases.get(phase_id, {})),
        "item": copy.deepcopy(item), "decisions": selected_decisions(plan, item_id, repos=repos), "upstream": upstream,
        "phase_dependencies": [copy.deepcopy(plan.phases[d]) for d in lifecycle._phase_deps(plan, phase_id)
                               if d in plan.phases],
        "reads": [read_entry(plan, r) for r in _reads(item)], "lessons": lessons,
        "documents": [copy.deepcopy(d) for d in plan.documents.values()
                      if scope_reason(d, item_id, phase_id, mode) is not None],
        "units": [copy.deepcopy(plan.units[f"{item_id}/{u}"]) for u in units.unit_ids(plan, item_id)],
        "orchestration": {**units.policy(plan, item_id), "scenario": name, "scenario_source": source},
        "ready_units": units.ready(plan, item_id),
        "policy": policy(plan),
    }
    batch = lifecycle.batch_context(plan, phase_id, item_id)
    if batch:
        result["batch"] = batch
    if mode == "scoped":
        result["projection"] = {"mode": mode, "note": PROJECTION_NOTE}
        result["upstream"] = [_project_upstream(d) for d in result["upstream"]]
        result["phase_dependencies"] = [_project_phase(d) for d in result["phase_dependencies"]]
        _dedupe_reads(plan, item_id, result)
    scout = plan.root / PACK_DIR / f"{item_id}.scout.json"
    if with_scout and scout.is_file():
        result["scout"] = json.loads(scout.read_text(encoding="utf-8"))
    return result


def render(plan: store.Plan, item_id: str, *, with_scout: bool = True, repos=None) -> str:
    return json.dumps(collect(plan, item_id, with_scout=with_scout, repos=repos), ensure_ascii=False, indent=2) + "\n"


def build(plan: store.Plan, item_id: str, *, repos=None) -> Path:
    path = plan.root / PACK_DIR / f"{item_id}.json"
    store.atomic_write(path, render(plan, item_id, repos=repos))
    return path
