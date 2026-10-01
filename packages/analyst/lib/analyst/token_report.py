"""analyst token-report — token report on slices (model/role) + two-layer baseline.

Source - `<project>/.claude/analyze/usage-trend.ndjson` (writes SessionEnd-hook run-report,
see `packages/harness/configs/claude-code/hooks/run-report/run-report.py:_append_trend`,
SCHEMA=2). Trend LINE Format (tested by reading the hook - not made up):
`{ts, session, in, out, cache_read, cache_creation, by_model:{model:{in,out}},
tools_total, files_changed, agents, wall_s, retr_chars}`.

Double layer baseline:
  - **rolling** — median+p90 out (+median in) latest `ROLLING_K` trend lines
    (`statistics.median`/`statistics.quantiles(n=10)`, stdlib) — same formula and same K=20,
    which is already using `maind.analyze.tokens_slice` (sessional ATTENTION during live run).
    token-report applies it aggregately, across the session window, and not to one current run.
  - **pinned** — `--baseline set --note "..."` freezes rolling-status of the current window in
    `<project>/.claude/analyze/baseline.json`. The format MUST match what the reader is reading
    `maind.analyze._read_baseline` (done by wave 1, DO NOT touch): `totals.median_out`
    primary, `by_model.<model>.median_out` — fallback. Our file is a superset (adds
    `median_in`/`p90_out`/`note`/`sessions`/`generated_at`) — maind simply does not read these fields.

`--vs-baseline` without pin (LOW-phase audit finding P8 plan
): NOT request error - rolling-report itself
is complete and useful without comparison. `cmd_token_report` prints `warn()` in stderr
(mild degradation, exit=0), the same pattern as neighboring commands in the absence
optional data (`promote.py`: did not come to mind → warn; `scan.py`: empty registry →
warn) — die() reserved for true lack of data (no trend at all).

Regression-flag (TK): `out > 1.3×rolling.median_out` OR `out > rolling.p90_out`.
(This is NOT the same threshold as `maind analyze` per-session ATTENTION — there `max(1.5×median, p90)`
for ONE live session; here the threshold is softer and aggregated - different sensitivity is conscious.)

Slices: `--by model` — real trend field `by_model` (partition in/out by model INSIDE
each session, written by the hook itself). `--by role` (label agent) — the trend does NOT store it (only
by_model), so read the full `<project>/.claude/runs/<session>.json` (`usage.agents[].label`)
for each window session - the same pattern read-only read run-report'ov that is already using
`digest._recent_run_reports`. Retention `.claude/runs/` shorter than trend (default 30 files
versus 2000 trend lines) — sessions without a saved file simply fall out of the slice `role`
(honest degradation, without zeros and inventions).

`--by phase` (workflows[].name) — **ESCALATION-REQUIRED, not implemented**: neither trend nor complete
run-report DO NOT carry tokens at the individual level workflow (`workflows[]` — this is only
`{name, status, summary}`, without in/out) — there is nothing to bind specific tokens to a phase in the current
diagram run-report (harness). The hook format outside the scope needs to be improved P4.1. `--by phase` politely
falls with this explanation without making up the distribution."""
import json
import os
import statistics
from pathlib import Path

from .common import (atomic_write_json, die, find_run_report, now_iso, parse_args,
                     read_ndjson, safe_load_json, warn)

TREND_REL = Path(".swissknife") / "analytics" / "usage-trend.ndjson"
BASELINE_REL = Path(".swissknife") / "analyst" / "baseline.json"
_LEGACY_TREND_REL = Path(".claude") / "analyze" / "usage-trend.ndjson"
_LEGACY_BASELINE_REL = Path(".claude") / "analyze" / "baseline.json"

ROLLING_K = 20          # window rolling-baseline — matches _TREND_K in maind.analyze
MIN_BASELINE_N = 3      # less - nothing to compare with (like _TREND_MIN_N in maind.analyze)
REGRESSION_MULT = 1.3   # Technical specification: regression = out > 1.3×median OR out > p90
SUPPORTED_BY = ("model", "role", "phase")


# ── paths/read ────────────────────────────────────────────────────────────────
def trend_path(project_path):
    return Path(os.path.expanduser(str(project_path))) / TREND_REL


def baseline_path(project_path):
    return Path(os.path.expanduser(str(project_path))) / BASELINE_REL


def read_trend(project_path):
    """Lines usage-trend.ndjson in recording order (append-only, old → new).
    [] if there is no file/empty - source best-effort (writes a hook, hook errors are not a barrier)."""
    rows = read_ndjson(trend_path(project_path))
    if rows:
        return rows
    return read_ndjson(Path(os.path.expanduser(str(project_path))) / _LEGACY_TREND_REL)


def read_pinned_baseline(project_path):
    """<project>/.claude/analyze/baseline.json → {median_out, median_in, p90_out, note,
    generated_at, sessions}. None — no file/broken/without totals.median_out (same contract,
    what maind.analyze._read_baseline: totals.median_out — required format field)."""
    data = safe_load_json(baseline_path(project_path), None)
    if not isinstance(data, dict):
        data = safe_load_json(Path(os.path.expanduser(str(project_path))) / _LEGACY_BASELINE_REL, None)
    if not isinstance(data, dict):
        return None
    totals = data.get("totals")
    if not isinstance(totals, dict) or not isinstance(totals.get("median_out"), (int, float)):
        return None
    return {"median_out": totals.get("median_out"), "median_in": totals.get("median_in"),
           "p90_out": totals.get("p90_out"), "note": data.get("note"),
           "generated_at": data.get("generated_at"), "sessions": data.get("sessions")}


# ── statistics (stdlib) ─────────────────────────────────────────────────────────
def rolling_stats(rows):
    """Median/p90 out (+median in) on a set of trend lines. None when < MIN_BASELINE_N
    lines - there is nothing to compare with, honestly we don’t count (do not slip in noise statistics
    at 1-2 points like the real one baseline)."""
    if len(rows) < MIN_BASELINE_N:
        return None
    outs = [r.get("out", 0) or 0 for r in rows]
    ins = [r.get("in", 0) or 0 for r in rows]
    return {
        "n": len(rows),
        "median_out": statistics.median(outs),
        "median_in": statistics.median(ins),
        "p90_out": statistics.quantiles(outs, n=10, method="inclusive")[-1],
    }


def is_regression(out_value, stats):
    """out_value > 1.3×median OR > p90 (TK). False, if you haven't gained stats yet
    (stats=None) or median zero (has nothing to compare with - we can’t divide by 0)."""
    if not stats or not stats.get("median_out"):
        return False
    return out_value > REGRESSION_MULT * stats["median_out"] or out_value > stats["p90_out"]


# ── slices ────────────────────────────────────────────────────────────────────────
def slice_by_model(rows):
    """{model: {sessions, in, out}} — partition of trend lines by `by_model` (real field
    usage-trend.ndjson, writes run-report._append_trend — partition in/out by model inside
    each session)."""
    buckets = {}
    for r in rows:
        bm = r.get("by_model")
        if not isinstance(bm, dict):
            continue
        for model, vals in bm.items():
            if not isinstance(vals, dict):
                continue
            b = buckets.setdefault(model, {"sessions": 0, "in": 0, "out": 0})
            b["sessions"] += 1
            b["in"] += vals.get("in", 0) or 0
            b["out"] += vals.get("out", 0) or 0
    return buckets


def slice_by_role(project_path, rows):
    """{label: {sessions, in, out}} — partition by label agent (usage.agents[].label
    FULL run-report'ah, `<project>/.claude/runs/<session>.json`; trend label does not store).
    Returns (buckets, {sessions_total, sessions_matched}) — matched honestly shows
    how many window sessions actually got into the slice (retention runs/ shorter than trend)."""
    buckets = {}
    matched = 0
    for r in rows:
        sid = r.get("session")
        if not sid:
            continue
        rr = find_run_report(project_path, session=sid)
        agents = ((rr or {}).get("usage") or {}).get("agents") or []
        if not agents:
            continue
        matched += 1
        for a in agents:
            if not isinstance(a, dict):
                continue
            label = a.get("label") or "?"
            b = buckets.setdefault(label, {"sessions": 0, "in": 0, "out": 0})
            b["sessions"] += 1
            b["in"] += a.get("in", 0) or 0
            b["out"] += a.get("out", 0) or 0
    return buckets, {"sessions_total": len(rows), "sessions_matched": matched}


def _model_series(rows):
    """{model: {"in": [...], "out": [...]}} — session rows per model (for baseline-pin:
    median/p90 are calculated according to the LIST of values, not according to the amount - see. build_baseline_doc)."""
    series = {}
    for r in rows:
        bm = r.get("by_model")
        if not isinstance(bm, dict):
            continue
        for model, vals in bm.items():
            if not isinstance(vals, dict):
                continue
            s = series.setdefault(model, {"in": [], "out": []})
            s["in"].append(vals.get("in", 0) or 0)
            s["out"].append(vals.get("out", 0) or 0)
    return series


# ── report assembly (clean - without die) ──────────────────────────────────────────────
def compute_report(project_path, *, sessions=None, by="model", vs_baseline=False):
    """Clean (without side effects die) report assembly. None — no trend at all (needed
    distinguish «no project/trend» from «empty slice» — `--all-projects` continues on
    other projects, single `cmd_token_report` turns None in polite die).

    rolling-baseline is ALWAYS calculated according to the latest `ROLLING_K` trend lines (fixed
    window like `_TREND_K` in maind.analyze) — REGARDLESS `sessions` (is the REPORT window,
    may already be/is wider than the basic one: report window ⊆/⊇ baseline window, both - «latest N»)."""
    all_rows = read_trend(project_path)
    if not all_rows:
        return None
    window_n = sessions or ROLLING_K
    window = all_rows[-window_n:]
    baseline_rows = all_rows[-ROLLING_K:]
    stats = rolling_stats(baseline_rows)

    pinned = read_pinned_baseline(project_path) if vs_baseline else None

    sess_rows = []
    for r in window:
        out = r.get("out", 0) or 0
        row = {"session": r.get("session"), "ts": r.get("ts"),
              "in": r.get("in", 0) or 0, "out": out,
              "regression": is_regression(out, stats)}
        if pinned:
            row["ratio_pinned"] = (out / pinned["median_out"]) if pinned.get("median_out") else None
        sess_rows.append(row)

    role_meta = None
    if by == "role":
        buckets, role_meta = slice_by_role(project_path, window)
    else:  # "model" (the only other supported option at this stage is phase is cut off above)
        buckets = slice_by_model(window)

    slice_rows = []
    for key in sorted(buckets):
        b = buckets[key]
        n = b["sessions"] or 1
        avg_out = b["out"] / n
        row = {"key": key, "sessions": b["sessions"], "in": b["in"], "out": b["out"],
              "avg_out": avg_out,
              "ratio_median": (avg_out / stats["median_out"]) if stats and stats.get("median_out") else None,
              "regression": is_regression(avg_out, stats)}
        if pinned:
            row["ratio_pinned"] = (avg_out / pinned["median_out"]) if pinned.get("median_out") else None
        slice_rows.append(row)

    return {
        "project": str(project_path), "by": by,
        "sessions_requested": window_n, "sessions_window": len(window),
        "sessions_total_in_trend": len(all_rows),
        "rolling": stats,
        "sessions": sess_rows,
        "slices": slice_rows,
        "role_meta": role_meta,
        "regression_count": sum(1 for s in sess_rows if s["regression"]),
        "vs_baseline_requested": bool(vs_baseline),
        "pinned_baseline": pinned,
    }


def build_baseline_doc(rows, note):
    """Snapshot for `.claude/analyze/baseline.json`. Format COMPATIBLE with
    `maind.analyze._read_baseline` (`totals.median_out` — required contract field,
    DO NOT rename without synchronous editing maind); `by_model.<model>.median_out` —
    him fallback-path, also saved. None — rows < MIN_BASELINE_N, nothing to pin."""
    stats = rolling_stats(rows)
    if stats is None:
        return None
    doc = {
        "generated_at": now_iso(),
        "note": note,
        "sessions": stats["n"],
        "totals": {"median_out": stats["median_out"], "median_in": stats["median_in"],
                  "p90_out": stats["p90_out"]},
        "by_model": {},
    }
    for model, s in _model_series(rows).items():
        outs, ins = s["out"], s["in"]
        p90 = (statistics.quantiles(outs, n=10, method="inclusive")[-1]
              if len(outs) >= 2 else float(outs[0]))
        doc["by_model"][model] = {"sessions": len(outs), "median_out": statistics.median(outs),
                                  "median_in": statistics.median(ins), "p90_out": p90}
    return doc


def pin_baseline(project_path, sessions, note):
    """--baseline set --note "..." → .claude/analyze/baseline.json (atomically, core.io).
    die — no trend OR not enough series (< MIN_BASELINE_N); in both cases NOTHING
    we don’t write (validation to a single side effect)."""
    all_rows = read_trend(project_path)
    if not all_rows:
        die(f"no token trend: {trend_path(project_path)} — nothing to pin "
            f"(enable hook run-report: harness hooks --target . --run-report on)")
    window_n = sessions or ROLLING_K
    rows = all_rows[-window_n:]
    doc = build_baseline_doc(rows, note)
    if doc is None:
        die(f"not enough sessions for baseline: {len(rows)} < {MIN_BASELINE_N} "
            f"— run more sessions, then repeat --baseline set")
    atomic_write_json(baseline_path(project_path), doc)
    return doc


# ── human readable output ────────────────────────────────────────────────────────
def _fmt_k(n):
    """Compact 'thousandth' number (48501 → '48k'), like _fmt_tokens_k in maind.analyze —
    a unified visual language of token numbers across repo."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    return f"{n / 1000:.0f}k" if abs(n) >= 1000 else str(int(n))


def _print_human(rep):
    print(f"\nanalyst token-report — {rep['project']}  ·  slice: {rep['by']}\n")
    print(f"  window: {rep['sessions_window']}/{rep['sessions_total_in_trend']} sessions "
          f"(requested {rep['sessions_requested']})")
    stats = rep["rolling"]
    if stats:
        print(f"  rolling baseline (K={ROLLING_K}, N={stats['n']}): "
              f"median out {_fmt_k(stats['median_out'])} · p90 out {_fmt_k(stats['p90_out'])}")
    else:
        print(f"  rolling baseline: not enough history (< {MIN_BASELINE_N} sessions) — "
              "regression flag is not considered yet")
    if rep.get("vs_baseline_requested"):
        pinned = rep.get("pinned_baseline")
        if pinned:
            print(f"  pinned baseline:  median out {_fmt_k(pinned['median_out'])}"
                  f"  ({pinned.get('note') or '—'} · {pinned.get('generated_at') or '?'})")
        else:
            print("  pinned baseline:  not installed - "
                  "analyst token-report --baseline set --note \"...\"")
    if rep.get("role_meta"):
        m = rep["role_meta"]
        print(f"  role-slice: {m['sessions_matched']}/{m['sessions_total']} sessions with "
              "preserved run-report'ohm (retention .claude/runs shorter than trend)")

    if not rep["slices"]:
        print("\n  Empty - there is no data in the window to slice (there are sessions, but they haven't matched).\n")
        return

    print(f"\n  {'slice':<28} {'sessions':>7} {'out (amount)':>13} {'out (avg.)':>12} "
          f"{'vs median':>11}  flag")
    for row in rep["slices"]:
        ratio = f"{row['ratio_median']:.1f}×" if row.get("ratio_median") is not None else "—"
        flag = "⚠ REGRESS" if row["regression"] else ""
        print(f"  {row['key']:<28} {row['sessions']:>7} {_fmt_k(row['out']):>13} "
              f"{_fmt_k(row['avg_out']):>12} {ratio:>11}  {flag}")

    print(f"\n  sessions with individual regression (window): "
          f"{rep['regression_count']}/{rep['sessions_window']}\n")


# ── CLI ────────────────────────────────────────────────────────────────────────────
def _cmd_all_projects(env, sessions, by, vs_baseline, as_json):
    """--all-projects: bypass config.json:projects[] (same registry/filter that analyst
    scan — reuse enabled_projects/load_projects, do not duplicate). Project without
    trend → honest line «no trend», does not stop crawling other projects."""
    from .scan import enabled_projects, load_projects

    cfg = env.default_config
    if not Path(cfg).is_file():
        die(f"project registry not found: {cfg} — --all-projects needed config.json "
            "(monorepo ecosystem root)")
    projects = enabled_projects(load_projects(cfg))
    if not projects:
        warn("no enabled-projects in the registry")

    results = []
    for pr in projects:
        ppath = os.path.expanduser(pr["local_path"])
        rep = compute_report(ppath, sessions=sessions, by=by, vs_baseline=vs_baseline)
        if rep is None:
            results.append({"project": pr["id"], "path": ppath, "error": "no token trend"})
            continue
        rep["project_id"] = pr["id"]
        results.append(rep)

    if as_json:
        print(json.dumps({"by": by, "projects": results}, ensure_ascii=False, indent=2))
        return

    print(f"\nanalyst token-report --all-projects — {len(projects)} project(ov) · slice: {by}\n")
    if not results:
        print("  (no projects in the registry)\n")
        return
    for rep in results:
        if rep.get("error"):
            print(f"  · {rep['project']}: {rep['error']}")
            continue
        print(f"── {rep['project_id']} " + "─" * max(2, 50 - len(rep["project_id"])))
        _print_human(rep)
    print()


def cmd_token_report(env, argv):
    """analyst token-report [--sessions N] [--by model|role] [--vs-baseline]
    [--all-projects] [--json]  ·  analyst token-report --baseline set --note "..."
    — token report on slices usage-trend.ndjson + two-layer baseline (rolling K=20 +
    pinned). --by phase not available (see docstring module - ESCALATION-REQUIRED)."""
    opts, _ = parse_args(argv, {
        "--sessions": "str", "--by": "str", "--vs-baseline": "bool",
        "--all-projects": "bool", "--json": "bool",
        "--baseline": "str", "--note": "str",
    })
    if opts["help"]:
        print("analyst token-report [--sessions N] [--by model|role] [--vs-baseline] "
              "[--all-projects] [--json]\n"
              "analyst token-report --baseline set --note \"...\"\n"
              "  Token report on slices usage-trend.ndjson: rolling-baseline (median+p90\n"
              "  latest K=20) + regression-flag (out > 1.3×median OR > p90).\n"
              "  --vs-baseline adds comparison with pinned .claude/analyze/baseline.json\n"
              "  (reads it and maind analyze). --baseline set kicks the current window.\n"
              "  If --vs-baseline is requested and baseline not stammered - WARN in stderr, report\n"
              "  still under construction (mild degradation, not request error).\n"
              "  ATTENTION: --by phase not available - run-report does not store tokens at level\n"
              "  workflows[] (only name/status/summary). Available: model, role.")
        return

    by = opts["by"] or "model"
    if by not in SUPPORTED_BY:
        die(f"--by is waiting model|role|phase, received: {by}")
    if by == "phase":
        die("--by phase not available: run-report stores workflows[] WITHOUT tokens (only "
            "name/status/summary) — bind out/in to the phase there is nothing with the current circuit run-report "
            "(ESCALATION-REQUIRED — modification of the hook format outside the scope P4.1). "
            "Available: --by model, --by role.")

    sessions = None
    if opts["sessions"]:
        try:
            sessions = int(opts["sessions"])
        except ValueError:
            die(f"--sessions expects an integer, received: {opts['sessions']}")
        if sessions <= 0:
            die("--sessions must be positive")

    if opts["baseline"]:
        if opts["baseline"] != "set":
            die(f"--baseline only supports the value 'set', received: {opts['baseline']}")
        if opts["all_projects"]:
            die("--baseline set works for one project (current directory) — "
                "--all-projects not supported")
        note = (opts["note"] or "").strip()
        if not note:
            die('--baseline set requires --note "..." (why pin - can be seen in release-discipline)')
        ppath = os.getcwd()
        doc = pin_baseline(ppath, sessions, note)
        if opts["json"]:
            print(json.dumps({"written": str(baseline_path(ppath)), **doc},
                             ensure_ascii=False, indent=2))
        else:
            print(f"\n✓ baseline pinned: {baseline_path(ppath)}")
            print(f"  N={doc['sessions']} · median out {_fmt_k(doc['totals']['median_out'])} "
                  f"· p90 out {_fmt_k(doc['totals']['p90_out'])}")
            print(f"  note: {doc['note']}\n")
        return

    if opts["all_projects"]:
        _cmd_all_projects(env, sessions, by, opts["vs_baseline"], opts["json"])
        return

    ppath = os.getcwd()
    rep = compute_report(ppath, sessions=sessions, by=by, vs_baseline=opts["vs_baseline"])
    if rep is None:
        die(f"no token trend: {trend_path(ppath)} — enable hook run-report "
            f"(harness hooks --target . --run-report on) and run at least one session")
    # --vs-baseline without pin - NOT request error (die): rolling-the report itself is complete and
    # useful, comparisons (ratio_pinned) just go out None (see compute_report) — same
    # mild degradation, the same as neighboring commands in the absence of optional data
    # (promote.py: did not come to mind → warn, not die; scan.py: empty registry → warn).
    # Before this edit there was no signal at all (naked print without WARN: — silent degradation,
    # LOW-audit finding P8: inconsistent with die/warn-package convention).
    if opts["vs_baseline"] and not rep.get("pinned_baseline"):
        warn("--vs-baseline was requested, but pinned baseline not installed - comparison "
             "missing (report continues): analyst token-report --baseline set "
             "--note \"...\"")
    if opts["json"]:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_human(rep)
