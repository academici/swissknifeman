"""Deterministic, complete JSON input for an executor. Human views never supply context."""
from __future__ import annotations

import copy
import glob
import json
from pathlib import Path
import re

from . import store
from .model import ITEM_ID, TERMINAL, PlanError, item_phase, parse_ref

PACK_DIR = "context"
LESSON_TYPES = ("deviation", "blocker", "difficulty", "assumption")


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
    base = plan.root if path.startswith("@plan/") else plan.repo_root
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
    return [r for r in item.get("reads", []) if isinstance(r, dict) and isinstance(r.get("path"), str)]


def _pending_producer(plan: store.Plan, item_id: str, path: str) -> str | None:
    seen, stack = set(), list(plan.items[item_id].get("depends_on", []))
    while stack:
        dep = stack.pop()
        if dep in seen or dep not in plan.items:
            continue
        seen.add(dep)
        doc = plan.items[dep]
        if doc.get("status") not in TERMINAL and any(
                a.get("role") == "output" and a.get("path") == path for a in doc.get("artifacts", [])):
            return dep
        stack.extend(doc.get("depends_on", []))
    return None


def missing_reads(plan: store.Plan, item_id: str) -> list[str]:
    return [r["path"] for r in _reads(plan.items[item_id])
            if r.get("required") and not _exists(plan, r["path"])
            and _pending_producer(plan, item_id, r["path"]) is None]


def read_entry(plan: store.Plan, read: dict) -> dict:
    """Inline requested supporting sections, with no reading quota or content truncation."""
    path = read["path"]
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
                selected = [s for s in sections if isinstance(s, dict) and
                            (s.get("id") == read["section"] or s.get("title") == read["section"])]
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


def selected_decisions(plan: store.Plan, item_id: str) -> list[dict]:
    selected, foreign = [], []
    item = plan.items[item_id]
    for ref in item.get("decisions", []):
        parsed = parse_ref(ref)
        if parsed.plan is None and parsed.target in plan.decisions:
            selected.append(parsed.target)
        else:
            foreign.append({"ref": ref, "loaded": False})
    for key, doc in plan.decisions.items():
        applies = doc.get("applies_to", [])
        if doc.get("status") == "accepted" and (not applies or item_id in applies or item_phase(item_id) in applies):
            selected.append(key)
    return [copy.deepcopy(plan.decisions[k]) for k in dict.fromkeys(selected)] + foreign


def collect(plan: store.Plan, item_id: str, *, with_scout: bool = True) -> dict:
    if item_id not in plan.items:
        raise PlanError("REF_UNKNOWN", f"unknown item {item_id!r}")
    from . import lifecycle, units

    item, phase_id = plan.items[item_id], item_phase(item_id)
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
    result = {
        "ref": f"{plan.plan['short_id']}.{item_id}", "plan": copy.deepcopy(plan.plan),
        "brief": copy.deepcopy(plan.brief), "phase": copy.deepcopy(plan.phases.get(phase_id, {})),
        "item": copy.deepcopy(item), "decisions": selected_decisions(plan, item_id), "upstream": upstream,
        "phase_dependencies": [copy.deepcopy(plan.phases[d]) for d in lifecycle._phase_deps(plan, phase_id)
                               if d in plan.phases],
        "reads": [read_entry(plan, r) for r in _reads(item)], "lessons": lessons,
        "documents": [copy.deepcopy(d) for d in plan.documents.values()
                      if not d.get("applies_to") or item_id in d["applies_to"] or phase_id in d["applies_to"]],
        "units": [copy.deepcopy(plan.units[f"{item_id}/{u}"]) for u in units.unit_ids(plan, item_id)],
        "orchestration": units.policy(plan, item_id), "ready_units": units.ready(plan, item_id),
    }
    scout = plan.root / PACK_DIR / f"{item_id}.scout.json"
    if with_scout and scout.is_file():
        result["scout"] = json.loads(scout.read_text(encoding="utf-8"))
    return result


def render(plan: store.Plan, item_id: str, *, with_scout: bool = True) -> str:
    return json.dumps(collect(plan, item_id, with_scout=with_scout), ensure_ascii=False, indent=2) + "\n"


def build(plan: store.Plan, item_id: str) -> Path:
    path = plan.root / PACK_DIR / f"{item_id}.json"
    store.atomic_write(path, render(plan, item_id))
    return path
