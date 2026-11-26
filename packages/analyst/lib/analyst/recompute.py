"""analyst recompute — deterministic recalculation confidence + numeric state-machine.

Source of truth - events.ndjson (append-only signal flow). recompute reads the log,
decays over time, aggregates S/N and tests, thinks confidence (confidence.py) and
moves state BY NUMBERS - WITHOUT daemon (on-demand), deterministic and recoverable
from logs (at fixed `--now` snapshot is reproduced).

Invariant (P1): `candidate→curated` — ALWAYS human. Here, with the numerical
thresholds curated is only MARKED «ready» (flag in audit), but does NOT move automatically.
Demout - soft (`move_lesson` in deprecated: re-write+unlink, file is saved, not deleted).
Auto-transition `ephemeral→candidate` allowed (machine shooting range) when N≥threshold & conf≥0.6 & tests≥1;
thresholds N adaptive to project activity for low-activity (adaptive_thresholds, see tuning.md).
"""
import json
import os

from aicore.config import ConfigError

from . import confidence as C
from . import lessons
from aicore.util.cli import parse_args
from aicore.util.term import die, now_iso, parse_iso
from .settings import DEFAULT_THRESHOLDS, load_thresholds

# ── numeric gates state-machine (§5) ────────────────────────────────────────
# Defaults of the user-tunable gates (the values live in settings.Thresholds; a project, machine or
# environment setting overrides them through the `thresholds` argument of the functions below).
CANDIDATE_MIN_N = DEFAULT_THRESHOLDS.candidate_min_n        # volume of observations for cars ephemeral→candidate
CANDIDATE_MIN_CONF = DEFAULT_THRESHOLDS.candidate_min_conf
CURATED_MIN_N = DEFAULT_THRESHOLDS.curated_min_n         # numeric threshold «ready for curated» (but the transition is human)
CURATED_MIN_CONF = DEFAULT_THRESHOLDS.curated_min_conf
CURATED_MIN_PASSRATE = DEFAULT_THRESHOLDS.curated_min_passrate
DEPRECATE_CONF = DEFAULT_THRESHOLDS.deprecate_conf       # drawdown below → soft-demo (candidate) / flag (curated)
CANDIDATE_MIN_N_FLOOR = DEFAULT_THRESHOLDS.candidate_min_n_floor   # lower adaptive threshold bar candidate (D2)


def adaptive_thresholds(project_sessions, thresholds=DEFAULT_THRESHOLDS):
    """Thresholds N transitions adapted to the overall project activity (D2, tuning.md).

    Inactive project (Σ sessions_total all events < CURATED_MIN_N) physically not
    will dial N≥15/50 → lessons are stuck in «eternal ephemeral». Lowering the bar
    proportional to activity, maintaining static proportion candidate:curated:

        candidate = max(FLOOR, project_sessions // 5)                # formula D2
        curated   = max(candidate, round(candidate × CURATED/CANDIDATE))  # same proportion

    When project_sessions ≥ CURATED_MIN_N enough data → static (15, 50).
    Net: (int) → (int, int). Deterministic. The threshold is never higher than the static one."""
    t = thresholds
    if project_sessions >= t.curated_min_n:
        return t.candidate_min_n, t.curated_min_n
    cand = max(t.candidate_min_n_floor, int(project_sessions) // 5)
    cur = max(cand, round(cand * t.curated_min_n / t.candidate_min_n))
    return cand, cur


# ── time (event age from aicore.util.term.parse_iso) ─────────────
def day_bucket(ts_event, ts_now):
    """Event age in days (floor, bucket=BUCKET_DAYS), ≥0. Unparsing ts → 0 (protective)."""
    a, b = parse_iso(ts_event), parse_iso(ts_now)
    if a is None or b is None:
        return 0
    secs = (b - a).total_seconds()
    return max(0, int(secs // (C.BUCKET_DAYS * 86400)))


# ── event aggregate (clean at a given now_ts) ─────────────────────────────
def aggregate_events(events, now_ts):
    """Reduce the events of one lesson into scalars + days_since last observed.
    Returns {S,N,tests_total,tests_passed,days_since,event_count,last_ts}."""
    S = N = tt = tp = 0
    last_ts = None
    last_dt = None
    for e in events:
        N += int(e.get("sessions_total", 0) or 0)
        S += int(e.get("sessions_success", 0) or 0)
        tt += int(e.get("tests_total", 0) or 0)
        tp += int(e.get("tests_passed", 0) or 0)
        ts = e.get("ts")
        # chronological max by DISCONTINUED time (not lexicographically - tolerates
        # fractional seconds/offsets, where string comparisons lie)
        dt = parse_iso(ts) if ts else None
        if dt is not None and (last_dt is None or dt > last_dt):
            last_dt, last_ts = dt, ts
    days = day_bucket(last_ts, now_ts) if last_ts else 0
    return {"S": S, "N": N, "tests_total": tt, "tests_passed": tp,
            "days_since": days, "event_count": len(events), "last_ts": last_ts}


def _passrate(tt, tp):
    return (tp / tt) if tt > 0 else 0.0


def snapshot_fields(agg, conf, now_ts):
    """Additive snapshot fields for the lesson (don't break P1-diagram). Determined when now_ts."""
    decay = C.time_decay(agg["days_since"])
    return {
        "sessions_total": agg["N"],
        "sessions_success": agg["S"],
        "tests_total": agg["tests_total"],
        "tests_passed": agg["tests_passed"],
        "S_decayed": round(agg["S"] * decay, 4),
        "N_decayed": round(agg["N"] * decay, 4),
        "confidence": round(conf, 4),
        "confidence_tier": C.tier(conf),
        "recomputed_at": now_ts,
    }


# ── numeric state-machine (clean: state+numbers → solution) ────────────────────
def decide_transition(state, agg, conf,
                      candidate_min_n=None, curated_min_n=None, thresholds=DEFAULT_THRESHOLDS):
    """(new_state, action, note) by numbers. curated — NOT auto (flag only «ready»).

    candidate_min_n/curated_min_n — effective thresholds N (default static;
    recompute_project transmits adaptive ones from the project activity, see adaptive_thresholds).
    action ∈ {promote, deprecate, curated-ready, curated-decay, unchanged}."""
    t = thresholds
    if candidate_min_n is None:
        candidate_min_n = t.candidate_min_n
    if curated_min_n is None:
        curated_min_n = t.curated_min_n
    N = agg["N"]
    tt = agg["tests_total"]
    if state == "ephemeral":
        if N >= candidate_min_n and conf >= t.candidate_min_conf and tt >= 1:
            return "candidate", "promote", f"N≥{candidate_min_n} & conf≥{t.candidate_min_conf} & tests≥1"
        return "ephemeral", "unchanged", ""
    if state == "candidate":
        if conf < t.deprecate_conf:
            return "deprecated", "deprecate", f"conf {conf:.2f} < {t.deprecate_conf} (soft)"
        pr = _passrate(tt, agg["tests_passed"])
        if N >= curated_min_n and conf >= t.curated_min_conf and pr >= t.curated_min_passrate:
            # invariant P1: in curated is moved ONLY by a person - there is only a flag here
            return "candidate", "curated-ready", f"numbers for curated yes (N≥{curated_min_n}) — need a person"
        return "candidate", "unchanged", ""
    if state == "curated":
        if conf < t.deprecate_conf:
            # curated man-blessed: not auto-demoting, marking for review
            return "curated", "curated-decay", f"conf {conf:.2f} < {t.deprecate_conf} — for human review"
        return "curated", "unchanged", ""
    return state, "unchanged", ""


# ── application (IO) ──────────────────────────────────────────────────────────
def recompute_project(project_path, now_ts, *, dry_run=False, thresholds=DEFAULT_THRESHOLDS):
    """Recalculate all active (not deprecated) lessons from events.ndjson. Returns
    list of results. dry_run — only counts, does not write anything to disk."""
    events = lessons.read_events(project_path)
    by_id = {}
    project_sessions = 0
    for e in events:
        project_sessions += int(e.get("sessions_total", 0) or 0)
        lid = e.get("id")
        if lid:
            by_id.setdefault(lid, []).append(e)
    # adaptive thresholds based on total project activity (low-active does not stick to ephemeral)
    cand_min, cur_min = adaptive_thresholds(project_sessions, thresholds)

    results = []
    for L, st in lessons.list_lessons(project_path):
        if st == "deprecated":
            continue
        lid = L["id"]
        evs = by_id.get(lid)
        if not evs:
            results.append({"id": lid, "state": st, "action": "no-events",
                            "confidence": None, "tier": None, "note": "no events"})
            continue
        agg = aggregate_events(evs, now_ts)
        conf = C.confidence(agg["S"], agg["N"], agg["days_since"])
        new_state, action, note = decide_transition(st, agg, conf, cand_min, cur_min, thresholds)
        results.append({"id": lid, "state": st, "new_state": new_state,
                        "confidence": round(conf, 4), "tier": C.tier(conf),
                        "action": action, "note": note,
                        "N": agg["N"], "S": agg["S"], "days_since": agg["days_since"]})
        if dry_run:
            continue

        # 1) atomic snapshot in the current state
        lessons.save_lesson(project_path, dict(L, **snapshot_fields(agg, conf, now_ts)), st)
        # 2) jumps by numbers (curated — NOT here)
        if action == "promote":
            lessons.move_lesson(project_path, lid, "candidate")
            lessons.audit_append(project_path, {
                "action": "recompute-promote", "id": lid, "from": st, "to": "candidate",
                "by": "auto", "confidence": round(conf, 4), "note": note})
        elif action == "deprecate":
            lessons.move_lesson(project_path, lid, "deprecated")
            lessons.audit_append(project_path, {
                "action": "recompute-deprecate", "id": lid, "from": st, "to": "deprecated",
                "by": "auto", "confidence": round(conf, 4), "note": note})
        elif action in ("curated-ready", "curated-decay"):
            lessons.audit_append(project_path, {
                "action": "recompute-flag", "id": lid, "state": st, "flag": action,
                "by": "auto", "confidence": round(conf, 4), "note": note})
    return results


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_recompute(env, argv):
    """analyst recompute [--now ISO] [--dry-run] [--json]
    — recalculate confidence lessons from events.ndjson and apply numeric state-machine."""
    opts, _ = parse_args(argv, {"--now": "str", "--project": "str",
                                "--dry-run": "bool", "--json": "bool"})
    if opts["help"]:
        print("analyst recompute [--now ISO] [--dry-run] [--json]\n"
              "  Deterministic recalculation confidence from events.ndjson + numeric\n"
              "  state-machine: auto ephemeral→candidate; curated — human only;\n"
              "  drawdown → soft-deprecate (file is not deleted). There is no demon.")
        return
    now_ts = opts["now"] or now_iso()
    if opts["now"] and parse_iso(now_ts) is None:
        die("--now: pending ISO UTC view 2026-07-01T00:00:00Z")

    ppath = os.getcwd()
    try:
        thresholds = load_thresholds(ppath)
    except ConfigError as err:
        die(str(err))
    results = recompute_project(ppath, now_ts, dry_run=opts["dry_run"], thresholds=thresholds)

    if opts["json"]:
        print(json.dumps({"now": now_ts, "dry_run": opts["dry_run"],
                          "results": results}, ensure_ascii=False, indent=2))
        return

    moved = [r for r in results if r["action"] in ("promote", "deprecate")]
    flags = [r for r in results if r["action"] in ("curated-ready", "curated-decay")]
    print(f"\nanalyst recompute — {len(results)} lesson(ov) @ {now_ts}"
          f"{' (dry-run)' if opts['dry_run'] else ''}\n")
    for r in results:
        if r["action"] in ("no-events",):
            continue
        arrow = f" → {r['new_state']}" if r.get("new_state") and r["new_state"] != r["state"] else ""
        print(f"  [{r['tier']} {r['confidence']}] {r['id']} ({r['state']}{arrow})"
              f"  N={r.get('N')} d={r.get('days_since')}"
              f"{('  ⚑ ' + r['note']) if r['action'].startswith('curated') else ''}")
    print()
    if flags:
        print(f"⚑ {len(flags)} ready(s) to human attention (curated — human only): "
              "analyst promote <id> --to curated")
    if moved and not opts["dry_run"]:
        print(f"✓ applied transitions: {len(moved)} (see audit.ndjson)")
    print()
