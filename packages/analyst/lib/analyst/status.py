"""analyst status / compact — store visibility and deterministic reduction events-log.

`status` — read-only summary (counters by state, last date digest/recompute,
curated-ready, promote_failed). `compact` — consolidate old events `events.ndjson` into one
snapshot-event for the lesson, saving the amounts (S/N/tests) and MAX ts groups to `recompute` before and
after gave the SAME confidence (aggregate depends only on the amounts and age of the last event)."""
import json
import os

from aicore.config import ConfigError

from . import lessons
from . import recompute as R
from aicore.util.cli import parse_args
from aicore.util.io import atomic_write_text
from aicore.util.term import die, parse_iso
from .settings import DEFAULT_THRESHOLDS, load_thresholds


# ── status ────────────────────────────────────────────────────────────────────
def _is_curated_ready(lesson, curated_min_n=None, thresholds=DEFAULT_THRESHOLDS):
    """The candidate entered the NUMBERS for curated (threshold recompute)? Transition is still a person.
    curated_min_n — effective (adaptive) threshold; None → static curated_min_n of `thresholds`."""
    conf = lesson.get("confidence")
    if conf is None:
        return False
    if curated_min_n is None:
        curated_min_n = thresholds.curated_min_n
    n = int(lesson.get("sessions_total", 0) or 0)
    tt = int(lesson.get("tests_total", 0) or 0)
    tp = int(lesson.get("tests_passed", 0) or 0)
    pr = (tp / tt) if tt > 0 else 0.0
    return (n >= curated_min_n and conf >= thresholds.curated_min_conf
            and pr >= thresholds.curated_min_passrate)


def _last_ts(records, pred):
    """Maximum (by parsed time) ts among records that satisfy pred. None — no."""
    best = None
    for r in records:
        if not pred(r):
            continue
        ts = r.get("ts")
        dt = parse_iso(ts) if ts else None
        if dt is not None and (best is None or dt > best[0]):
            best = (dt, ts)
    return best[1] if best else None


def build_status(project_path, thresholds=DEFAULT_THRESHOLDS):
    """Lesson Story Summary (read-only, without mutations). Dates - from append-only audit.ndjson."""
    counts = {st: 0 for st in lessons.STATES}
    promote_failed = 0
    curated_ready = 0
    events = lessons.read_events(project_path)
    # adaptive threshold curated — is the same as what I would use recompute (project activity)
    project_sessions = sum(int(e.get("sessions_total", 0) or 0) for e in events)
    _, cur_min = R.adaptive_thresholds(project_sessions, thresholds)
    for L, st in lessons.list_lessons(project_path):
        counts[st] += 1
        if L.get("promote_failed"):
            promote_failed += 1
        if st == "candidate" and _is_curated_ready(L, cur_min, thresholds):
            curated_ready += 1
    audit = lessons.read_audit(project_path)
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "curated_ready": curated_ready,
        "promote_failed": promote_failed,
        "events": len(events),
        "last_digest": _last_ts(audit, lambda a: a.get("action") == "digest"),
        "last_recompute": _last_ts(
            audit, lambda a: str(a.get("action", "")).startswith("recompute")),
    }


def cmd_status(env, argv):
    """analyst status [--json] — lesson story summary (read-only, without mutations)."""
    opts, _ = parse_args(argv, {"--project": "str", "--json": "bool"})
    if opts["help"]:
        print("analyst status [--json]\n"
              "  Read-only summary: counters by state, curated-ready, promote_failed,\n"
              "  number of events, dates of last digest/recompute. Doesn't change anything.")
        return
    ppath = os.getcwd()
    try:
        st = build_status(ppath, load_thresholds(ppath))
    except ConfigError as err:
        die(str(err))
    if opts["json"]:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return
    c = st["counts"]
    print(f"\nanalyst status — {st['total']} lesson(ov)\n")
    for state in lessons.STATES:
        print(f"  {state:<11} {c[state]}")
    print(f"\n  curated-ready:  {st['curated_ready']}  (there are numbers - we need a person)")
    print(f"  promote_failed: {st['promote_failed']}"
          + ("  → forwarded: analyst promote --retry-failed" if st["promote_failed"] else ""))
    print(f"  events:        {st['events']}")
    print(f"  last digest:    {st['last_digest'] or '—'}")
    print(f"  last recompute: {st['last_recompute'] or '—'}\n")


# ── compact ─────────────────────────────────────────────────────────────────
def compact_events(events, before_dt):
    """Reduce events with `ts < before_dt` (or ALL when before_dt=None) into one snapshot-event
    for the lesson. Saves amounts (S/N/tests) and MAX ts groups → recompute gives the same confidence.
    Events without id / without parsing ts / with `ts >= before_dt` remain as is.
    Returns (new_events, {compacted, snapshots, kept}). Clean (without I/O)."""
    old_by_id = {}
    kept = []
    for e in events:
        lid = e.get("id")
        ts = e.get("ts")
        dt = parse_iso(ts) if ts else None
        eligible = bool(lid) and dt is not None and (before_dt is None or dt < before_dt)
        if not eligible:
            kept.append(e)
            continue
        old_by_id.setdefault(lid, []).append((dt, e))
    snapshots = []
    for lid, items in old_by_id.items():
        _max_dt, max_e = max(items, key=lambda it: it[0])
        snapshots.append({
            "id": lid, "source": "compact", "ts": max_e.get("ts"),
            "sessions_total": sum(int(e.get("sessions_total", 0) or 0) for _, e in items),
            "sessions_success": sum(int(e.get("sessions_success", 0) or 0) for _, e in items),
            "tests_total": sum(int(e.get("tests_total", 0) or 0) for _, e in items),
            "tests_passed": sum(int(e.get("tests_passed", 0) or 0) for _, e in items),
            "compacted": True, "compacted_count": len(items),
        })
    new_events = kept + snapshots
    new_events.sort(key=lambda e: (e.get("ts") or ""))
    return new_events, {"compacted": sum(len(v) for v in old_by_id.values()),
                        "snapshots": len(snapshots), "kept": len(kept)}


def cmd_compact(env, argv):
    """analyst compact [--before ISO] [--dry-run] [--json] — consolidate old events into snapshot."""
    opts, _ = parse_args(argv, {"--before": "str", "--project": "str",
                                "--dry-run": "bool", "--json": "bool"})
    if opts["help"]:
        print("analyst compact [--before ISO] [--dry-run] [--json]\n"
              "  Consolidate events events.ndjson (older --before, or ALL) into one snapshot\n"
              "  for the lesson. Amounts and ages of the last event are stored → recompute gives\n"
              "  the same confidence. --dry-run — just show, don't write anything.")
        return
    before_dt = None
    if opts["before"]:
        before_dt = parse_iso(opts["before"])
        if before_dt is None:
            die("--before: pending ISO UTC view 2026-07-01T00:00:00Z")
    ppath = os.getcwd()
    events = lessons.read_events(ppath)
    new_events, stats = compact_events(events, before_dt)

    if opts["json"]:
        print(json.dumps({"before": opts["before"] or None, "dry_run": opts["dry_run"],
                          **stats, "events_after": len(new_events)},
                         ensure_ascii=False, indent=2))
    if stats["compacted"] == 0:
        if not opts["json"]:
            print("Nothing to compact (no matching events).")
        return
    if opts["dry_run"]:
        if not opts["json"]:
            print(f"[dry-run] would collapse {stats['compacted']} events → "
                  f"{stats['snapshots']} snapshot; would only be left {len(new_events)}.")
        return

    content = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in new_events)
    atomic_write_text(lessons.events_path(ppath), content)
    lessons.audit_append(ppath, {"action": "compact", "before": opts["before"] or None,
                                 **stats, "events_after": len(new_events)})
    if not opts["json"]:
        print(f"Collapsed {stats['compacted']} events → {stats['snapshots']} snapshot. "
              f"events.ndjson: {len(new_events)} records.")
