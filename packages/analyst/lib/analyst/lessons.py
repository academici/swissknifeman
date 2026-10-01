"""Lesson Repository analyst — file store with scalars, provenance and audit.

Per-project layout (LOCAL, privacy-by-directories from ECC):
    <project>/.claude/analyst/
      lessons/{ephemeral,candidate,curated,deprecated}/<id>.json
      audit.ndjson        # append-only: who/when/that promoted (provenance)

Invariants (data-integrity):
- lesson recording - atomic (core.atomic_write_json: tmp + os.replace);
- state transition - atomic re-write to a new directory + unlink old (lesson is not double);
- audit - append-only ndjson (is not overwritten, only appended);
- lesson carries only SCALARS (portable, deterministic); raw materials/we don't put secrets inside.

Confidence-arithmetic (Beta/decay) and state-machine-gates by numbers - phase P3; here MVP
stores raw material counters (sessions_total/…), transitions are made by a person through `analyst promote`."""
import hashlib
import json
import os
import re
from pathlib import Path

from .common import (atomic_write_json, now_iso, read_ndjson, safe_load_json,
                     sanitize)

STATES = ("ephemeral", "candidate", "curated", "deprecated")
KINDS = ("heuristic", "procedure", "gotcha")

# Order «activity»: active lessons that we consider against diff/duplicates (not deprecated).
ACTIVE_STATES = ("curated", "candidate", "ephemeral")


# ── paths ─────────────────────────────────────────────────────────────────────
def project_dir(project_path):
    """New human-curated analyst state; legacy Claude state remains read-only fallback."""
    return Path(os.path.expanduser(str(project_path))) / ".swissknife" / "analyst"


def legacy_project_dir(project_path):
    return Path(os.path.expanduser(str(project_path))) / ".claude" / "analyst"


def lessons_dir(project_path):
    return project_dir(project_path) / "lessons"


def state_dir(project_path, state):
    if state not in STATES:
        raise ValueError(f"unknown state: {state}")
    return lessons_dir(project_path) / state


def audit_path(project_path):
    return project_dir(project_path) / "audit.ndjson"


def events_path(project_path):
    """<project>/.claude/analyst/events.ndjson — append-only signal flow confidence.
    Separate from audit.ndjson (that - provenance of transitions); here are observation scalars
    (sessions_total/success, tests_total/passed), of which recompute will be restored."""
    return project_dir(project_path) / "events.ndjson"


# ── lesson outline ──────────────────────────────────────────────────────────────
def make_lesson_id(trigger, action, session=""):
    """Deterministic id: slug(trigger) + short hash(trigger|action|session).
    The hash gives uniqueness when matching slug'ah; determinism - testability."""
    slug = sanitize(trigger)[:48] or "lesson"
    h = hashlib.sha1(f"{trigger}\x00{action}\x00{session}".encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{h}"


def new_lesson(*, trigger, action, kind="heuristic", scope, session_id="",
               project="", detector="", evidence=None, source="digest",
               tests_total=0, tests_passed=0, meta=None, review_hint=""):
    """Collect lesson dictionary (scalars + provenance). state always 'ephemeral' at the input.

    `action` — PURE semantic text (on it Jaccard-dedup and surfacing to memory).
    Non-text (attempt counters, affected files) → `meta`; instructions for reviewer →
    `review_hint`. `meta`/`review_hint` do NOT go into memory (surface reads only
    trigger/action/evidence) — token-saving + clean Jaccard."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    trigger = " ".join((trigger or "").split()).strip()
    action = " ".join((action or "").split()).strip()
    ts = now_iso()
    return {
        "id": make_lesson_id(trigger, action, session_id),
        "kind": kind,
        "trigger": trigger,
        "action": action,
        "evidence": list(evidence or []),
        "meta": dict(meta or {}),
        "review_hint": " ".join((review_hint or "").split()).strip(),
        "created_at": ts,
        "last_used_at": ts,
        "sessions_total": 1,
        "sessions_success": 0,
        "tests_total": int(tests_total),
        "tests_passed": int(tests_passed),
        "state": "ephemeral",
        "scope": scope,
        "source": source,
        "supersedes": None,
        "provenance": {"session_id": session_id, "project": project, "detector": detector},
    }


# ── read ───────────────────────────────────────────────────────────────────
def _iter_state(project_path, state):
    seen = set()
    for base in (project_dir(project_path), legacy_project_dir(project_path)):
        d = base / "lessons" / state
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.json")):
            rec = safe_load_json(p, None)
            if isinstance(rec, dict) and rec.get("id") not in seen:
                seen.add(rec.get("id"))
                yield rec


def list_lessons(project_path, state=None):
    """[(lesson, state)] for one condition or for all (ok STATES)."""
    states = (state,) if state else STATES
    out = []
    for st in states:
        for rec in _iter_state(project_path, st):
            out.append((rec, st))
    return out


def find_lesson(project_path, lesson_id):
    """(lesson, state) first match by id (order STATES) or (None, None)."""
    for st in STATES:
        for base in (project_dir(project_path), legacy_project_dir(project_path)):
            p = base / "lessons" / st / f"{lesson_id}.json"
            if p.is_file():
                rec = safe_load_json(p, None)
                if isinstance(rec, dict):
                    return rec, st
    return None, None


# ── entry / transitions ────────────────────────────────────────────────────────
def save_lesson(project_path, lesson, state=None):
    """Atomically write a lesson to its state directory (or state-override).
    Returns the path. Duplicates by id within one state are overwritten (idempotent)."""
    st = state or lesson.get("state") or "ephemeral"
    lesson = dict(lesson, state=st)
    dst = state_dir(project_path, st) / f"{lesson['id']}.json"
    atomic_write_json(dst, lesson)
    return dst


def add_candidate(project_path, lesson):
    """Write a candidate lesson from digest in ephemeral, if so id isn't there yet.
    Returns (lesson, created: bool). Already exists in ANY state → do not touch."""
    existing, _st = find_lesson(project_path, lesson["id"])
    if existing is not None:
        return existing, False
    save_lesson(project_path, lesson, "ephemeral")
    return lesson, True


def move_lesson(project_path, lesson_id, new_state):
    """Atomically translate the lesson into new_state: re-write to a new directory + unlink old
    (lesson does not double between states). Returns (lesson, old_state, new_state).
    die-no semantics - caller checks None."""
    if new_state not in STATES:
        raise ValueError(f"unknown state: {new_state}")
    lesson, old_state = find_lesson(project_path, lesson_id)
    if lesson is None:
        return None, None, None
    if old_state == new_state:
        return lesson, old_state, new_state
    lesson = dict(lesson, state=new_state, last_used_at=now_iso())
    save_lesson(project_path, lesson, new_state)
    old_path = state_dir(project_path, old_state) / f"{lesson_id}.json"
    try:
        old_path.unlink(missing_ok=True)
    except OSError:
        pass
    return lesson, old_state, new_state


# ── audit (append-only provenance) ────────────────────────────────────────────
def audit_append(project_path, record):
    """Add one entry to audit.ndjson (append-only, never overwrite).
    Adds ts, if it is not there. Creates a directory. Additional recording - opening in 'a'."""
    rec = dict(record)
    rec.setdefault("ts", now_iso())
    path = audit_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return rec


def read_audit(project_path):
    """List of entries audit.ndjson (skips broken lines). [] if there is no file."""
    return read_ndjson(audit_path(project_path))


# ── events (append-only signal flow confidence) ───────────────────────────
def event_append(project_path, record):
    """Add a signal event to events.ndjson (append-only, add-on only).
    Adds ts, if it is not there. From this log recompute restores confidence."""
    rec = dict(record)
    rec.setdefault("ts", now_iso())
    path = events_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return rec


def read_events(project_path):
    """List of events events.ndjson (skips broken lines). [] if there is no file."""
    return read_ndjson(events_path(project_path))


# ── similarity (Jaccard, stdlib) ──────────────────────────────────────────────
# compile at module level (re.compile is idempotent, does not crash on import): without
# module-global-states and lazy-init — package convention + no race in tests with reload.
_WORD_RE = re.compile(r"[a-za-z0-9]{3,}")


def _tokens(text):
    """Many tokens (lower, alphanumeric words only ≥3 characters)."""
    return set(_WORD_RE.findall((text or "").lower()))


def jaccard(a, b):
    """Jaccard on two string tokens. 0.0 if both are empty."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def similar_lessons(project_path, trigger, action, *, states=ACTIVE_STATES,
                    threshold=0.4, exclude_id=None):
    """[(lesson, state, score)] active lessons similar to (trigger+action) by Jaccard
    ≥ threshold, descending score. For diff in review and dedupa during promotion."""
    query = f"{trigger} {action}"
    out = []
    for st in states:
        for rec in _iter_state(project_path, st):
            if exclude_id and rec.get("id") == exclude_id:
                continue
            score = jaccard(query, f"{rec.get('trigger', '')} {rec.get('action', '')}")
            if score >= threshold:
                out.append((rec, st, round(score, 3)))
    out.sort(key=lambda t: t[2], reverse=True)
    return out


# ── consolidation (mem0-taxonomy, in human-gate) ─────────────────────────────
# Thresholds in pairs (similarity trigger, similarity action) — pure heuristics (stdlib):
CONSOLIDATE_TRIGGER_HIGH = 0.6   # «same situation»
CONSOLIDATE_ACTION_HIGH = 0.6    # «same action»
CONSOLIDATE_ACTION_LOW = 0.2     # actions diverge → contradiction


def classify_consolidation(trigger, action, similar):
    """mem0-taxonomy for candidate vs similar active lessons (auto-resolve NO -
    only a recommendation to a person). similar: [(lesson, state, score)] from similar_lessons.

    Returns {"action": ADD|UPDATE|NOOP|CONFLICT, "target": id|None, "reason": str}:
      NOOP     — duplicate (same situation AND same action);
      CONFLICT — contradiction (same situation, action diverges) → flag-and-ask;
      UPDATE   — specifies an existing (same situation, the action has evolved);
      ADD      — new knowledge (no relatives / loosely coupled only).
    """
    best = None  # (trigger_sim, action_sim, lesson, state) with max. trigger_sim
    for L, st, _score in similar:
        tsim = jaccard(trigger, L.get("trigger", ""))
        asim = jaccard(action, L.get("action", ""))
        if best is None or tsim > best[0]:
            best = (tsim, asim, L, st)
    if best is None:
        return {"action": "ADD", "target": None, "reason": "no similar active"}
    tsim, asim, L, st = best
    tid = L.get("id")
    if tsim >= CONSOLIDATE_TRIGGER_HIGH and asim >= CONSOLIDATE_ACTION_HIGH:
        return {"action": "NOOP", "target": tid, "reason": f"duplicate {tid} [{st}]"}
    if tsim >= CONSOLIDATE_TRIGGER_HIGH and asim < CONSOLIDATE_ACTION_LOW:
        return {"action": "CONFLICT", "target": tid,
                "reason": f"same situation, different action → conflict with {tid} [{st}]"}
    if tsim >= CONSOLIDATE_TRIGGER_HIGH:
        return {"action": "UPDATE", "target": tid, "reason": f"clarifies {tid} [{st}]"}
    return {"action": "ADD", "target": tid, "reason": f"linked to {tid} [{st}], but new"}
