"""Context pack of an item (dossier §7): everything the executor needs, built from the plan JSON.

``build`` writes ``<plan>/context/<item>.md``; ``render`` returns the same text without writing. The pack is a
deterministic function of the plan JSON, its log, the files its ``reads`` and ``task_files`` name, and the optional
``context/<item>.scout.md`` map — no generation timestamp. Empty sections are omitted. Its size is printed for
information only; there is no size gate (D2).
"""
from __future__ import annotations

import glob as _glob
from pathlib import Path
import re

from . import lifecycle, store, units, views
from .model import ITEM_ID, SATISFYING, TERMINAL, PlanError, id_sort_key, item_phase, parse_ref
from .templating import render as _render_template

PACK_DIR = "context"
LESSON_TYPES = ("deviation", "blocker", "difficulty", "assumption")
MAX_LESSONS = 10
DEFAULT_MAX_INLINE_LINES = 200
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_NUMBER = re.compile(r"^(?:§\s*)?(\d+(?:\.\d+)*)\.?(?=\s|$)")
_SECTION_NUMBER = re.compile(r"^§\s*(\d+(?:\.\d+)*)")
_GLOB_CHARS = re.compile(r"[*?\[]")


# ---------------------------------------------------------------- Markdown sections

def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """``(line index, level, text)`` of every heading outside fenced code blocks."""
    found, fenced = [], False
    for index, text in enumerate(lines):
        if _FENCE.match(text):
            fenced = not fenced
        elif not fenced and (match := _HEADING.match(text)):
            found.append((index, len(match[1]), match[2]))
    return found


def _plain(text: str) -> str:
    return " ".join(re.sub(r"[`*_]", "", text).split()).lower()


def _find_heading(headings: list[tuple[int, int, str]], section: str) -> int | None:
    wanted = " ".join(section.split())
    number = _SECTION_NUMBER.match(wanted)
    if number:  # `§N` names the numbered heading itself, whatever text follows
        for position, (_, _, text) in enumerate(headings):
            if (match := _NUMBER.match(text)) and match[1] == number[1]:
                return position
        return None
    target = _plain(wanted)
    for matches in (lambda t: t == target, lambda t: t.startswith(target), lambda t: target in t):
        for position, (_, _, text) in enumerate(headings):
            if matches(_plain(text)):
                return position
    return None


def extract_section(text: str, section: str) -> str | None:
    """Body of the Markdown section ``section``, or None when no heading matches.

    ``section`` is a heading text (case-insensitive: exact, then prefix, then substring) or ``§N`` / ``§N.M``
    naming the heading whose number is N. The body runs to the next heading of the same or a higher level;
    fenced code blocks never count as headings.
    """
    lines = text.splitlines()
    headings = _headings(lines)
    position = _find_heading(headings, section)
    if position is None:
        return None
    start, level, _ = headings[position]
    end = len(lines)
    for index, other, _t in headings[position + 1:]:
        if other <= level:
            end = index
            break
    body = lines[start + 1:end]
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(body)


# ---------------------------------------------------------------- paths and reads

def _resolve(plan: store.Plan, path: str) -> Path | None:
    """Filesystem location of a repo-relative or ``@plan/`` path; None when it would leave its base."""
    rel = path.removeprefix("@plan/")
    if ".." in re.split(r"[\\/]", rel) or rel.startswith(("/", "~")):
        return None
    return (plan.root if path.startswith("@plan/") else plan.repo_root) / rel


def _exists(plan: store.Plan, path: str) -> bool:
    target = _resolve(plan, path)
    if target is None:
        return False
    return bool(_glob.glob(str(target))) if _GLOB_CHARS.search(path) else target.exists()


def _pending_producer(plan: store.Plan, item_id: str, path: str) -> str | None:
    """A not yet terminal dependency (transitively) of ``item_id`` whose ``artifacts`` output is ``path``."""
    seen: set[str] = set()
    stack = list(plan.items[item_id].get("depends_on") or [])
    while stack:
        dep = stack.pop()
        if dep in seen or dep not in plan.items:
            continue
        seen.add(dep)
        doc = plan.items[dep]
        if lifecycle.status_of(plan, dep) not in TERMINAL and any(
                isinstance(a, dict) and a.get("role") == "output" and a.get("path") == path
                for a in doc.get("artifacts") or []):
            return dep
        stack.extend(doc.get("depends_on") or [])
    return None


def _reads(item: dict) -> list[dict]:
    return [r for r in item.get("reads") or [] if isinstance(r, dict) and isinstance(r.get("path"), str)]


def missing_reads(plan: store.Plan, item_id: str) -> list[str]:
    """Required reads of ``item_id`` that do not exist and are not outputs of a pending dependency."""
    return [read["path"] for read in _reads(plan.items[item_id])
            if read.get("required") is True and not _exists(plan, read["path"])
            and _pending_producer(plan, item_id, read["path"]) is None]


# ---------------------------------------------------------------- view-model

def _list(value) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _block(items: list[str]) -> dict | None:
    return {"items": [views.line(i) for i in items]} if items else None


def _read_entry(plan: store.Plan, item_id: str, number: int, read: dict, max_lines: int) -> dict:
    path, section = read["path"], read.get("section")
    note, inline = "", ""
    producer = None if _exists(plan, path) else _pending_producer(plan, item_id, path)
    if producer:
        note = f" [pending: produced by {producer}]"
    elif not _exists(plan, path):
        note = " [missing]"
    elif section and path.endswith(".md") and (target := _resolve(plan, path)) is not None and target.is_file():
        try:
            body = extract_section(target.read_text(encoding="utf-8"), section)
        except (OSError, UnicodeDecodeError):
            note = " [unreadable]"
        else:
            if body is None:
                note = " [section not found]"
            elif len(body.splitlines()) > max_lines:
                note = f" [section has {len(body.splitlines())} lines; read it from the file]"
            elif body:
                inline = "\n".join(f"   > {text}".rstrip() for text in body.splitlines())
    return {"n": number, "path": path, "section": f" {section}" if section else "", "why": views.line(read.get("why")),
            "required": " (required)" if read.get("required") is True else "", "note": note, "inline": inline}


def _decisions(plan: store.Plan, item_id: str) -> list[dict]:
    phase_id = item_phase(item_id)
    chosen: list[str] = []
    foreign: list[str] = []
    for ref in _list(plan.items[item_id].get("decisions")):
        try:
            parsed = parse_ref(ref)
        except ValueError:
            continue
        if parsed.plan is None and parsed.target in plan.decisions:
            chosen.append(parsed.target)
        elif parsed.plan is not None:
            foreign.append(ref)
    for key in sorted(plan.decisions, key=id_sort_key):
        applies = _list(plan.decisions[key].get("applies_to"))
        if key not in chosen and plan.decisions[key].get("status") == "accepted" and (item_id in applies or phase_id in applies):
            chosen.append(key)
    rows = []
    for key in dict.fromkeys(chosen):
        doc = plan.decisions[key]
        status = doc.get("status", "")
        if status == "open":
            status, text = "OPEN — ask/decide before relying", doc.get("question") or doc.get("title", "")
        else:
            if status == "superseded":
                status = f"superseded by {doc.get('superseded_by')}"
            text = doc.get("decision") or doc.get("question") or doc.get("title", "")
        rows.append({"id": key, "status": status, "text": views.line(text),
                     "consequences": "; ".join(views.line(c) for c in _list(doc.get("consequences")))})
    rows += [{"id": ref, "status": "other plan; not loaded", "text": "", "consequences": ""} for ref in foreign]
    return rows


def _upstream(plan: store.Plan, item_id: str) -> list[dict]:
    item = plan.items[item_id]
    related = [r["ref"] for r in item.get("related") or [] if isinstance(r, dict) and isinstance(r.get("ref"), str)]
    rows = []
    for dep in dict.fromkeys([*_list(item.get("depends_on")), *related]):
        if dep not in plan.items:
            continue
        doc = plan.items[dep]
        result = doc.get("result") if isinstance(doc.get("result"), dict) else {}
        notes = views.line(result.get("notes") or doc.get("title"))
        for label, key in (("deviations", "deviations"), ("pending", "pending")):
            if _list(result.get(key)):
                notes += f" ({label}: {'; '.join(views.line(t) for t in _list(result[key]))})"
        outputs = [a["path"] for a in doc.get("artifacts") or []
                   if isinstance(a, dict) and a.get("role") == "output" and isinstance(a.get("path"), str)]
        rows.append({"id": dep, "status_label": views._item_label(lifecycle.status_of(plan, dep)), "notes": notes,
                     "outputs": f" Outputs: {', '.join(outputs)}" if outputs else ""})
    return rows


def _lessons(plan: store.Plan, item_id: str) -> list[dict]:
    """Friction events of this phase and of related items, newest first, at most ``MAX_LESSONS``."""
    phase_id, item = item_phase(item_id), plan.items[item_id]
    near = {d for d in _list(item.get("depends_on")) if d in plan.items}
    near |= {r["ref"] for r in item.get("related") or [] if isinstance(r, dict) and r.get("ref") in plan.items}
    rows = []
    for _, event, _ in store.log_lines(plan.root):
        if not event or event.get("type") not in LESSON_TYPES:
            continue
        target = event.get("item") if isinstance(event.get("item"), str) else None
        phase = event.get("phase") or (item_phase(target) if target and ITEM_ID.fullmatch(target) else None)
        if phase == phase_id or target in near:
            rows.append({"when": str(event.get("ts", ""))[11:16], "target": target or phase or "plan",
                         "type": event["type"], "summary": views.line(event.get("summary")),
                         "follow_up": f" → {views.line(event['next'])}" if event.get("next") else ""})
    return rows[::-1][:MAX_LESSONS]


def _check_row(label: str, check: dict) -> dict:
    return {"label": label, "cmd": check.get("cmd", ""), "expect": views.line(check.get("expect")),
            "kind": check.get("kind", ""), "cwd": f", cwd: {check['cwd']}" if check.get("cwd") else ""}


def _model(plan: store.Plan, item_id: str, max_lines: int, *, with_scout: bool = True) -> dict:
    if item_id not in plan.items:
        raise PlanError("REF_UNKNOWN", f"unknown item {item_id!r}")
    item, phase_id = plan.items[item_id], item_phase(item_id)
    phase = plan.phases.get(phase_id, {})
    short = plan.plan.get("short_id") or plan.plan.get("id", plan.root.name)
    batch = lifecycle.next_batch_id(plan, phase_id, item_id)
    batch_text = ""
    if batch:
        holder = [b for b in lifecycle.batches_of(plan, phase_id) if b.get("id") == batch][0]
        names = [f"{m} ✓" if m != item_id and lifecycle.status_of(plan, m) in SATISFYING else m
                 for m in lifecycle.batch_members(plan, phase_id, holder)]
        batch_text = f" · Batch {batch} ({', '.join(names)})"
    scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
    contract = phase.get("contract") if isinstance(phase.get("contract"), dict) else {}
    contract_text = " · ".join(f"{key} {'; '.join(views.line(t) for t in _list(contract.get(key)))}"
                               for key in ("consumes", "produces", "boundaries") if _list(contract.get(key)))
    phase_text = "\n\n".join(t for t in (
        f"Phase {phase_id} — {views.line(phase.get('title'))}" + (f": {views.line(phase.get('goal'))}" if phase.get("goal") else ""),
        str(phase.get("context") or "").strip()) if t)
    context = {"phase_text": phase_text, "contract": contract_text, "pitfalls": _block(_list(phase.get("pitfalls"))),
               "rules": _block(_list(plan.plan.get("rules")))}
    reads = [_read_entry(plan, item_id, n, read, max_lines) for n, read in enumerate(_reads(item), start=1)]
    hints = []
    for hint in (h for h in item.get("task_files") or [] if isinstance(h, dict) and isinstance(h.get("path"), str)):
        mark = "glob" if _GLOB_CHARS.search(hint["path"]) else ("exists" if _exists(plan, hint["path"]) else "new")
        hints.append(f"{hint['path']} ({hint.get('change', 'any')}, {mark})"
                     + (f" — {views.line(hint['note'])}" if hint.get("note") else ""))
    artifacts = [f"{a.get('role')}: {a['path']}" + (f" — {views.line(a['note'])}" if a.get("note") else "")
                 for a in item.get("artifacts") or [] if isinstance(a, dict) and isinstance(a.get("path"), str)]
    examples = [f"{e['path']}" + (f" {e['section']}" if e.get("section") else "")
                for e in item.get("examples") or [] if isinstance(e, dict) and isinstance(e.get("path"), str)]
    guide = {"rules": _block(_list(item.get("rules"))), "guidance": str(item.get("guidance") or "").strip(),
             "examples": _block(examples)}
    checks = [_check_row(c.get("id", ""), c) for c in item.get("validation") or [] if isinstance(c, dict)]
    if lifecycle.phase_items(plan, phase_id)[-1:] == [item_id]:
        checks += [_check_row(f"Phase {c.get('id', '')}", c) for c in phase.get("validation") or [] if isinstance(c, dict)]
    scout_path = plan.root / PACK_DIR / f"{item_id}.scout.md"
    scout = scout_path.read_text(encoding="utf-8").strip() if with_scout and scout_path.is_file() else ""
    decisions, upstream, lessons = _decisions(plan, item_id), _upstream(plan, item_id), _lessons(plan, item_id)
    return {
        "ref": f"{short}.{item_id}", "title": views.line(item.get("title")), "plan_title": views.line(plan.plan.get("title")),
        "plan_ref": short, "item": item_id, "phase": phase_id, "batch": batch_text,
        "route": views._route_text(item.get("route")),
        "summary": str(item.get("summary") or "").strip(), "why": str(item.get("why") or "").strip(),
        "plan_goal": str(plan.plan.get("goal") or "").strip(),
        "scope": {"include": _list(scope.get("include")), "exclude": _list(scope.get("exclude")),
                  "has_exclude": bool(_list(scope.get("exclude")))} if _list(scope.get("include")) else None,
        "context": context if any(context.values()) else None,
        "decisions": {"items": decisions} if decisions else None,
        "upstream": {"items": upstream} if upstream else None,
        "reads": {"items": reads} if reads else None,
        "files": _block(hints), "units": units.pack_section(plan, item_id), "artifacts": _block(artifacts),
        "lessons": {"items": lessons} if lessons else None,
        "guide": guide if any(guide.values()) else None,
        "checks": checks, "deliverables": "; ".join(views.line(d) for d in _list(item.get("deliverables"))),
        "scout": scout,
    }


# ---------------------------------------------------------------- public API

def render(plan: store.Plan, item_id: str, *, max_inline_lines: int = DEFAULT_MAX_INLINE_LINES,
           with_scout: bool = True) -> str:
    """The pack text of ``item_id`` (no file is written); ends with one informational size line.

    ``with_scout=False`` leaves out the scout map, so the scout itself reads the deterministic pack.
    """
    model = _model(plan, item_id, max_inline_lines, with_scout=with_scout)
    text = _render_template(views._load_template("context"), model,
                            lambda partial: views._load_template(f"_{partial}")).rstrip("\n") + "\n"
    return f"{text}\n_Pack size: {len(text)} chars ≈ {len(text) // 4} tokens (informational; no limit)._\n"


def build(plan: store.Plan, item_id: str, *, max_inline_lines: int = DEFAULT_MAX_INLINE_LINES) -> Path:
    """Write ``context/<item>.md`` under the plan directory and return its path."""
    text = render(plan, item_id, max_inline_lines=max_inline_lines)
    path = plan.root / PACK_DIR / f"{item_id}.md"
    store.atomic_write(path, text)
    return path
