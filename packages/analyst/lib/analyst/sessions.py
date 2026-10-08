"""analyst sessions — weekly median token overhead by LIVE jsonl-transcripts
Claude Code (`~/.claude/projects/<encoded-cwd>/<sid>.jsonl`), NOT by `usage-trend.ndjson`
run-report (that source reads `token_report.py` — another one here: raw transcripts
sessions available even without the hook enabled run-report).

Reference logic - scratchpad-script `analyze_sessions.py` (session 4af788f3, SCRIPT OUT
REPO - only the extract of the algorithm has been moved here):
  - `first_turn_overhead` = input + cache_creation FIRST assistant-session records
    (not the sum of all - a single source of mathematics now `core.usage.feed_event`,
    see edit `aicore/usage.py`, no need to duplicate it here);
  - `fresh_per_turn` = (Σinput + Σcache_creation) / turns (`turns` = number
    assistant-events, `core.usage.finish(...)["msgs"]`);
  - transcript path: `~/.claude/projects/<encoded-cwd>/<session_id>.jsonl`.

Coding cwd (TESTED by reading live directories `~/.claude/projects/*` this
cars, not guessed): Claude Code replaces EVERY `/` absolute path to `-`
(presenter `/` → presenter `-` directory name) — confirmed on ~20 live projects
of different nesting. Behavior for literals `.`/`_` inside path segments NOT
managed to double-check on live directories (among connected projects of such paths
no) — if `analyst sessions` does not find directory for project with dot/underscore
on the way, it's ESCALATION-REQUIRED, and not a reason to change the encoding at random (see Escalation
Needed P5.3 in phases/P5.md).

Weekly key - ISO-calendar week (`%G-W%V`) first session timestamp
(`ts_min` battery). `--weeks N` — latest N weeks for which there are sessions.
Trend-warn (TK): median `first_turn_overhead` weeks N has grown >20% by week N-1 —
simple comparison of medians, without exotics (stdlib `statistics`, without pandas/numpy). Compare
only CALENDARLY adjacent weeks (`_is_next_iso_week`) — when skipping weeks (no sessions)
warn is not printed so as not to confuse rupture with relapse."""
import json
import os
import statistics
from datetime import date, datetime
from pathlib import Path

from core import usage as core_usage

from .common import HOME, die, parse_args, warn

TREND_WARN_MULT = 1.2   # >20% increase in median week-over-week (TK)
TOP_ANOMALIES = 5


# ── paths/encoding cwd ──────────────────────────────────────────────────────────
def encode_cwd(cwd):
    """abs-path → transcript directory name (see module docstring: '/' → '-',
    confirmed live `~/.claude/projects/*`)."""
    p = os.path.abspath(os.path.expanduser(str(cwd)))
    return p.replace(os.sep, "-")


def sessions_dir(cwd, home=None):
    base = Path(home) if home else HOME
    return base / ".claude" / "projects" / encode_cwd(cwd)


def _session_files(cwd, home=None):
    d = sessions_dir(cwd, home=home)
    if not d.is_dir():
        return []
    return sorted(d.glob("*.jsonl"))


# ── metrics for one session ──────────────────────────────────────────────────────────
def _week_key(ts):
    """ISO-week ('2026-W28') from ISO-timestamp; None on garbage/absence -
    session without a specific week is not bucketed (honest degradation)."""
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def session_metrics(path):
    """Read-only provider acquisition from a local transcript.

    This source is allowed only as bounded legacy input: it neither normalizes raw bodies
    nor writes `.claude`; absent neutral usage semantics remain absent rather than invented.
    """
    acc = core_usage.new_acc()
    try:
        for ev in core_usage.iter_jsonl(path):
            core_usage.feed_event(acc, ev)
    except Exception:
        return None
    agg = core_usage.finish(acc, label=Path(path).stem)
    if agg["msgs"] == 0:
        return None
    week = _week_key(acc.get("ts_min"))
    if week is None:
        return None
    fresh = (agg["in"] + agg["cache_creation"]) / agg["msgs"]
    return {
        "session": Path(path).stem, "week": week, "ts_min": acc.get("ts_min"),
        "first_turn_overhead": agg["first_turn_overhead"], "turns": agg["msgs"],
        "in": agg["in"], "cache_creation": agg["cache_creation"],
        "cache_read": agg["cache_read"], "out": agg["out"],
        "fresh_per_turn": fresh,
    }


def load_sessions(cwd, home=None):
    """Metrics of all sessions of the project, in ascending order of time. [] — directory/no sessions
    (not an error: the project might not start from this cwd — honest emptiness)."""
    rows = []
    for f in _session_files(cwd, home=home):
        m = session_metrics(f)
        if m is not None:
            rows.append(m)
    rows.sort(key=lambda r: r["ts_min"] or "")
    return rows


# ── weekly aggregation ────────────────────────────────────────────────────────────
def _median(values):
    return statistics.median(values) if values else None


def _is_next_iso_week(prev_week, cur_week):
    """True, if cur_week — CALENDAR next ISO-week for prev_week (without
    gaps between them, not just a neighboring index in the list of present weeks)."""
    py, pw = (int(x) for x in prev_week.split("-W"))
    cy, cw = (int(x) for x in cur_week.split("-W"))
    prev_monday = date.fromisocalendar(py, pw, 1)
    cur_monday = date.fromisocalendar(cy, cw, 1)
    return (cur_monday - prev_monday).days == 7


def weekly_buckets(rows):
    """{week: [session-metrics...]} — group by ISO-week."""
    buckets = {}
    for r in rows:
        buckets.setdefault(r["week"], []).append(r)
    return buckets


def build_report(cwd, weeks=None, home=None):
    """Clean report build (without die/print). None — no sessions at all (need to be distinguished
    from «there are sessions, but the window weeks empty» — this does not happen here: weeks is already cutting
    non-empty list of weeks)."""
    rows = load_sessions(cwd, home=home)
    if not rows:
        return None
    buckets = weekly_buckets(rows)
    weeks_sorted = sorted(buckets)
    if weeks:
        weeks_sorted = weeks_sorted[-weeks:]

    weekly = []
    for wk in weeks_sorted:
        wrows = buckets[wk]
        overheads = [r["first_turn_overhead"] for r in wrows if r["first_turn_overhead"] is not None]
        fresh = [r["fresh_per_turn"] for r in wrows if r["fresh_per_turn"] is not None]
        weekly.append({
            "week": wk, "sessions": len(wrows),
            "median_first_turn_overhead": _median(overheads),
            "median_fresh_per_turn": _median(fresh),
        })

    warnings = []
    for i in range(1, len(weekly)):
        prev, cur = weekly[i - 1], weekly[i]
        pm, cm = prev["median_first_turn_overhead"], cur["median_first_turn_overhead"]
        if pm and cm and cm > TREND_WARN_MULT * pm and _is_next_iso_week(prev["week"], cur["week"]):
            growth_pct = (cm / pm - 1) * 100
            warnings.append(
                f"{prev['week']}→{cur['week']}: median first_turn_overhead has grown "
                f"on {growth_pct:.0f}% ({pm:.0f}→{cm:.0f}) — context-incident recurrence?")

    window_rows = [r for r in rows if r["week"] in weeks_sorted]
    top_anomalies = sorted(
        window_rows, key=lambda r: r["first_turn_overhead"] or 0, reverse=True
    )[:TOP_ANOMALIES]

    return {
        "cwd": str(cwd), "sessions_dir": str(sessions_dir(cwd, home=home)),
        "weeks_requested": weeks, "weeks": weekly,
        "sessions_total": len(rows), "sessions_window": len(window_rows),
        "trend_warnings": warnings, "top_anomalies": top_anomalies,
    }


# ── human readable output ────────────────────────────────────────────────────────
def _fmt_k(n):
    if n is None:
        return "—"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    return f"{n / 1000:.1f}k" if abs(n) >= 1000 else str(int(n))


def _print_human(rep):
    print(f"\nanalyst sessions — {rep['cwd']}")
    print(f"  transcript directory: {rep['sessions_dir']}")
    print(f"  sessions total: {rep['sessions_total']} · in the window: {rep['sessions_window']}\n")
    if not rep["weeks"]:
        print("  Empty - no weeks in the window.\n")
        return
    print(f"  {'week':<10} {'sessions':>7} {'median first_turn_overhead':>28} "
          f"{'median fresh/turn':>19}")
    for w in rep["weeks"]:
        print(f"  {w['week']:<10} {w['sessions']:>7} "
              f"{_fmt_k(w['median_first_turn_overhead']):>28} "
              f"{_fmt_k(w['median_fresh_per_turn']):>19}")
    if rep["top_anomalies"]:
        print("\n  top anomalies (max. first_turn_overhead in the window):")
        for r in rep["top_anomalies"]:
            print(f"    · {r['session']} ({r['week']}): {_fmt_k(r['first_turn_overhead'])}")
    print()


# ── CLI ────────────────────────────────────────────────────────────────────────────
def _project_path(env, opts):
    """--project ID → local_path from the registry config.json (same pattern as
    `token_report._cmd_all_projects`/`scan.enabled_projects` — do not duplicate the resolve).
    Without --project — current directory (like everyone else P1 analyst)."""
    pid = opts.get("project")
    if not pid:
        return os.getcwd()
    from .scan import enabled_projects, load_projects

    cfg = env.default_config
    if not Path(cfg).is_file():
        die(f"project registry not found: {cfg} — --project needed config.json "
            "(monorepo ecosystem root)")
    projects = enabled_projects(load_projects(cfg))
    match = next((p for p in projects if p["id"] == pid), None)
    if match is None:
        die(f"project '{pid}' not found in enabled-registry: {cfg}")
    return os.path.expanduser(match["local_path"])


def cmd_sessions(env, argv):
    """analyst sessions [--project P] [--weeks N] [--json] — weekly medians
    first_turn_overhead/fresh-per-turn from the living jsonl-session transcripts
    (`~/.claude/projects/<encoded-cwd>/*.jsonl`) + trend-warn week-over-week >20%
    median growth first_turn_overhead."""
    opts, _ = parse_args(argv, {"--project": "str", "--weeks": "str", "--json": "bool"})
    if opts["help"]:
        print("analyst sessions [--project P] [--weeks N] [--json]\n"
              "  Weekly medians first_turn_overhead/fresh-per-turn from the living\n"
              "  jsonl-session transcripts (~/.claude/projects/<encoded-cwd>/*.jsonl).\n"
              "  --project P — resolve local_path by id from config.json (node registry);\n"
              "  without --project — current directory.\n"
              "  Warn in stderr, if median first_turn_overhead weeks rose >20%\n"
              "  to previous week (relapse-signal context-incident).")
        return

    weeks = None
    if opts["weeks"]:
        try:
            weeks = int(opts["weeks"])
        except ValueError:
            die(f"--weeks expects an integer, received: {opts['weeks']}")
        if weeks <= 0:
            die("--weeks must be positive")

    cwd = _project_path(env, opts)
    rep = build_report(cwd, weeks=weeks)
    if rep is None:
        die(f"no sessions: {sessions_dir(cwd)} — no jsonl-transcripts for this cwd "
            "(the project was not launched from here, or the directory encoding is different - see. "
            "docstring analyst/sessions.py)")

    if opts["json"]:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_human(rep)
    for w in rep["trend_warnings"]:
        warn(w)
