"""maind analyze — unified post-run run analysis «did everything work as it should?».

After the task-with-plan, the outcome sources are read separately (run-report hook, log Bash,
observer, git, health). analyze aggregates them into ONE report with a verdict GREEN/ATTENTION/RED —
read-only, degrades based on the presence of a source (no run-report → forensics: bash-log without codes
return + git; verdict is marked confidence=low, so as not to overpromise).

Primary source - run-report (SessionEnd-hook harness writes <project>/.claude/runs/<sid>.json
from transcript). Bow with RAG-discipline: dev-loop `tool_failures` (engine was unavailable →
fact not verified) are placed in the block «Unverified → REPEAT PASS».

stdlib-only; Env is passed explicitly. Reuses health.health_report, projects, core.run_cmd."""
import json
import os
from pathlib import Path

from ..analyst_source import run_lookup
from ..common import parse_args, read_ndjson_iter, run_cmd
from ..config import load_config
from ..health import _target


# ── source 1: run-report (primary) — read through `analyst runs show` (see analyst_source) ──
def run_report_source(ppath, session=None, project_id=None):
    """Run report, codegraph summary and neutral events of a project, read through analyst.

    Without analyst the source is ``unavailable`` with the reason (``PARTNER_UNAVAILABLE``,
    ``PARTNER_FAILED`` or ``PARTNER_BAD_OUTPUT``) and the analysis continues without a run report."""
    data, problem = run_lookup(ppath, session=session, project_id=project_id)
    if problem is not None:
        return {"status": "unavailable", "reason": problem["code"], "message": problem["message"],
                "report": None, "codegraph": None, "events": [], "diagnostics": [
                    {"code": problem["code"], "message": problem["message"]}]}
    lookup = data["lookup"]
    diagnostics = []
    if lookup.get("reason"):
        diagnostics.append({"code": lookup["reason"], "source": lookup.get("path")})
    return {"status": lookup["status"], "reason": lookup.get("reason"), "message": None,
            "report": data.get("report"), "codegraph": data.get("codegraph"),
            "events": data["events"], "diagnostics": diagnostics}


# ── source 2: log Bash (forensics; WITHOUT return codes - PreToolUse) ─────────
# patterns are the same as in run-report/_lib.py (conscious take: the hook is stand-alone, not imported).
_TEST_HINT = ("pytest", "phpunit", "pest", "jest", "vitest", "go test", "cargo test",
              "npm test", "npm run test", "yarn test", "unittest", "validate.sh", "test.sh")
_LINT_HINT = ("ruff", "flake8", "pylint", "mypy", "eslint", "pint", "phpstan", "psalm",
              "black", "isort", "tsc", "prettier", "py_compile")


def bash_log_forensics(env, project_path, session=None):
    """Command counter from ~/.claude/logs/bash-commands.jsonl by cwd-to the project prefix (+session).
    ATTENTION: the log is being written PreToolUse → WITHOUT return codes: it is clear that the test/lint DRIVEN, not
    passed (knows this run-report). None if the log is missing."""
    log = env.home / ".claude" / "logs" / "bash-commands.jsonl"
    if not log.is_file():
        return None
    base = os.path.abspath(os.path.expanduser(str(project_path)))
    total, tests, lints = 0, [], []
    try:
        for rec in read_ndjson_iter(log):
            cwd = rec.get("cwd") or ""
            if not (cwd == base or cwd.startswith(base + os.sep)):
                continue
            if session and rec.get("session") != session:
                continue
            cmd = (rec.get("command") or "")
            total += 1
            low = cmd.lower()
            if any(h in low for h in _TEST_HINT):
                tests.append(cmd[:160])
            if any(h in low for h in _LINT_HINT):
                lints.append(cmd[:160])
    except OSError:
        return None
    return {"total": total, "tests": tests, "lints": lints}


# ── source 3: observer (best-effort, schema not frozen) ───────────────────
def observer_forensics(project_path):
    """<project>/.claude/observer/runtime.jsonl: LOOP-alerts/errors. Scheme observer
    experimental → protective: we catch the signal by substring the raw string. None if there is no file."""
    f = Path(project_path) / ".claude" / "observer" / "runtime.jsonl"
    if not f.is_file():
        return None
    lines, alerts = 0, []
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                lines += 1
                low = line.lower()
                if ("loop" in low or "\"error\"" in low or "alert" in low) and len(alerts) < 20:
                    alerts.append(line[:200])
    except OSError:
        return None
    return {"lines": lines, "alerts": alerts}


# ── source 4: git ──────────────────────────────────────────────────────────
def git_status(project_path, base=None):
    """Clean working tree (porcelain) + optional diff --stat <base>...HEAD.
    None if not git-repository. base=None → working tree only (without guessing about the branch)."""
    path = str(project_path)
    porc = run_cmd(["git", "-C", path, "status", "--porcelain"], capture=True, check=False)
    if porc.returncode != 0:
        return None
    changed = [ln for ln in (porc.stdout or "").splitlines() if ln.strip()]
    out = {"dirty": bool(changed), "working_files": len(changed)}
    if base:
        diff = run_cmd(["git", "-C", path, "diff", "--stat", f"{base}...HEAD"],
                       capture=True, check=False)
        out["base"] = base
        out["diffstat"] = (diff.stdout or "").strip() if diff.returncode == 0 else None
        if diff.returncode != 0:
            out["diff_error"] = (diff.stderr or "").strip()[:200]
    return out


# ── source 6: unwatched lessons analyst (learning loop awaits man) ───
# ephemeral/candidate — lessons that digest extracted, but the person has not yet reviewed/promoted.
# Hoarding in silence (digest writes automatically, review — manually); analyze reminds me of them.
_PENDING_LESSON_STATES = ("ephemeral", "candidate")


def pending_lessons(project_path):
    """How many lessons analyst waiting for human review (ephemeral+candidate). 0 if there is no directory.
    Read-only file counter - analyst-store lives in <project>/.claude/analyst/lessons/<state>/."""
    roots = (Path(os.path.expanduser(str(project_path))) / ".swissknife" / "analyst" / "lessons",
             Path(os.path.expanduser(str(project_path))) / ".claude" / "analyst" / "lessons")
    total = 0
    seen = set()
    for base in roots:
        for state in _PENDING_LESSON_STATES:
            d = base / state
            if d.is_dir():
                for p in d.glob("*.json"):
                    key = (state, p.name)
                    if p.is_file() and key not in seen:
                        seen.add(key)
                        total += 1
    return total


def analytics_slice(events, session=None):
    """Neutral analytics consumer over the events analyst returned; no provider raw-path knowledge."""
    providers = sorted({event["provider_id"] for event in events})
    metrics = {}
    provenance = []
    for event in sorted(events, key=lambda item: (item["occurred_at"], item["event_id"])):
        for name, value in event["metrics"].items():
            metrics[name] = metrics.get(name, 0) + value
        provenance.append(dict(event["provenance"]))
    return {"events": len(events), "providers": providers,
            "run_report": {"contract_version": "1.0.0", "session_id": session,
                           "metrics": {name: metrics[name] for name in sorted(metrics)},
                           "provenance": provenance}}


# ── source 5: health (is the hub alive? reuse health_report) ────────────────
def health_slice(env, config, project):
    """Compact cut health_report (memory/graph/round-trip). None for any error -
    the health of the hub is orthogonal to the task, we don’t lose analysis because of it."""
    try:
        from ..health import health_report
        rep = health_report(env, config, project)
        return {"status": rep.get("status"), "memory_daemon": rep.get("memory_daemon"),
                "maind_mcp": rep.get("maind_mcp"), "roundtrip": rep.get("memory_roundtrip")}
    except Exception:
        return None


# ── verdict ──────────────────────────────────────────────────────────────────
def compute_verdict(run_report, git, observer, *, evidence_diagnostics=(), codegraph=None):
    """(verdict, confidence, red, reasons, repass) from collected slices.
    RED — failed test/work flow. ATTENTION — lint/tool-failures/deferred/workarounds/dirty
    tree/LOOP. repass — dev-loop tool_failures (engine was unavailable → fact not verified)."""
    red, reasons, repass = [], [], []
    confidence = "high" if run_report else "low"

    if run_report:
        bash = run_report.get("bash") or {}
        for t in bash.get("tests") or []:
            if isinstance(t, dict) and not t.get("ok", True):
                red.append(f"test failed: {t.get('command', '?')}")
        for wf in run_report.get("workflows") or []:
            if isinstance(wf, dict) and str(wf.get("status", "")).lower() in ("failed", "error"):
                red.append(f"work flow {wf.get('name', '?')}: {wf.get('status')}")
        for lint in bash.get("lints") or []:
            if isinstance(lint, dict) and not lint.get("ok", True):
                reasons.append(f"lint failed: {lint.get('command', '?')}")
        tf = run_report.get("tool_failures") or []
        if tf:
            reasons.append(f"tool-gaps in the transcript: {len(tf)}")
        dl = run_report.get("devloop") or {}
        if dl.get("deferred"):
            reasons.append(f"deferred (deferred): {len(dl['deferred'])}")
        if dl.get("workarounds"):
            reasons.append(f"workarounds (workarounds): {len(dl['workarounds'])}")
        if dl.get("open_questions"):
            reasons.append(f"open questions: {len(dl['open_questions'])}")
        for item in (dl.get("tool_failures") or []):
            repass.append(item if isinstance(item, str) else json.dumps(item, ensure_ascii=False))

        # memory observability/column (key run-report.maind — additive; old report → empty).
        maind = run_report.get("maind") or {}
        cg = codegraph or {}
        codegraph_calls = cg.get("calls", 0)
        by_name = (run_report.get("tools") or {}).get("by_name") or {}
        scan = sum(by_name.get(t, 0) for t in ("Read", "Grep", "Glob"))
        # INDIRECT heuristic: heavy file scanning at zero symbol-tools codegraph.
        if scan >= 30 and codegraph_calls == 0:
            reasons.append(f"codegraph not used for heavy scanning "
                           f"({scan} Read/Grep/Glob, codegraph ×0) — symbol-tools cheaper grep+read")
        recall = maind.get("memory_recall") or {}
        if recall.get("calls", 0) >= 2 and recall.get("found_total", 0) == 0:
            reasons.append(f"memory polled (recall ×{recall['calls']}), but empty/wrong address "
                           f"— check scope/filling (maind memory count)")

    for diagnostic in evidence_diagnostics:
        if diagnostic.get("code") == "RUN_REPORT_PROJECT_MISMATCH":
            reasons.append("RUN_REPORT_PROJECT_MISMATCH: alien run-report excluded from verdict")

    if git and git.get("dirty"):
        reasons.append(f"working tree is not clean: {git.get('working_files', '?')} file(ov)")
    if observer and observer.get("alerts"):
        reasons.append(f"observer-alerts: {len(observer['alerts'])}")

    if red:
        verdict = "RED"
    elif reasons or repass:
        verdict = "ATTENTION"
    else:
        verdict = "GREEN"
    return verdict, confidence, red, reasons, repass


# ── report assembly ────────────────────────────────────────────────────────────
def analyze_report(env, config, project, *, session=None, base=None, with_health=True):
    """Collect a complete analysis report of one project (read-only)."""
    pid = project["id"]
    local = project.get("local_path")
    ppath = os.path.expanduser(local) if local else os.getcwd()

    source = run_report_source(ppath, session, pid)
    run_report = source["report"]
    # bash-log correlated by REAL session run-report'a (in production session_id run-report ==
    # id sessions Claude == session in bash-log); explicit --session takes precedence.
    effective_session = session or (run_report or {}).get("session_id")
    bash_log = bash_log_forensics(env, ppath, effective_session)
    observer = observer_forensics(ppath)
    git = git_status(ppath, base)
    health = health_slice(env, config, project) if with_health else None

    diagnostics = source["diagnostics"]
    verdict, confidence, red, reasons, repass = compute_verdict(
        run_report, git, observer, evidence_diagnostics=diagnostics, codegraph=source["codegraph"])
    return {
        "project": pid, "path": ppath,
        "verdict": verdict, "confidence": confidence,
        "red": red, "reasons": reasons, "repass": repass,
        "run_report": run_report, "run_report_diagnostics": diagnostics,
        "run_report_source": {"status": source["status"], "reason": source["reason"]},
        "codegraph": source["codegraph"], "bash_log": bash_log,
        "observer": observer, "git": git, "health": health,
        "pending_lessons": pending_lessons(ppath),
        "analytics": analytics_slice(source["events"], effective_session),
    }


# ── human readable output ───────────────────────────────────────────────────
_ICON = {"GREEN": "✓", "ATTENTION": "⚠", "RED": "✗"}


def _print_human(rep):
    v = rep["verdict"]
    conf = "" if rep["confidence"] == "high" else "  (confidence: low — forensics without run-report)"
    print(f"\n{_ICON.get(v, '·')} mAInd analyze — project:{rep['project']} → {v}{conf}\n")

    rr = rep.get("run_report")
    print("run-report  " + "─" * 48)
    if rr:
        tools = rr.get("tools") or {}
        bash = rr.get("bash") or {}
        tpass = sum(1 for t in (bash.get("tests") or []) if t.get("ok"))
        tfail = sum(1 for t in (bash.get("tests") or []) if not t.get("ok"))
        lpass = sum(1 for x in (bash.get("lints") or []) if x.get("ok"))
        lfail = sum(1 for x in (bash.get("lints") or []) if not x.get("ok"))
        gen = (rr.get("generated_at") or "")[:16].replace("T", " ")
        print(f"  session:     {rr.get('session_id', '?')}  ({gen})")
        print(f"  tools: {tools.get('total', 0)}  · files changed: "
              f"{len(rr.get('files_changed') or [])}")
        md = rr.get("maind") or {}
        cg = rep.get("codegraph") or {}
        if md or cg.get("calls"):
            mem_calls = sum(v.get("calls", 0) for k, v in md.items() if k.startswith("memory_"))
            graph_calls = sum(v.get("calls", 0) for k, v in md.items() if k.startswith("graph_"))
            graph_found = sum(v.get("found_total", 0) for k, v in md.items() if k.startswith("graph_"))
            recall = md.get("memory_recall") or {}
            line = (f"  mAInd:      memory ×{mem_calls} "
                    f"(recall ×{recall.get('calls', 0)}→{recall.get('found_total', 0)} facts) · "
                    f"topology ×{graph_calls}→{graph_found} neighbors")
            if cg.get("calls"):
                ops = ", ".join(f"{k}×{v}" for k, v in sorted(cg.get("by_op", {}).items()))
                line += f" · codegraph ×{cg['calls']} ({ops})"
            print(line)
        print(f"  tests:      {tpass} ok / {tfail} FAIL     lint: {lpass} ok / {lfail} FAIL")
        if rr.get("workflows"):
            for wf in rr["workflows"]:
                print(f"    work flow {wf.get('name', '?')}: {wf.get('status', '?')}"
                      f"{('  — ' + wf['summary']) if wf.get('summary') else ''}")
        if rr.get("tool_failures"):
            print(f"  tool-failures: {len(rr['tool_failures'])}")
            for tf in rr["tool_failures"][:5]:
                print(f"    ✗ {tf.get('tool', '?')}: {tf.get('snippet', '')[:100]}")
    elif (rep.get("run_report_source") or {}).get("status") == "unavailable":
        print(f"  source unavailable ({rep['run_report_source']['reason']}) - forensics bash-log/git. "
              "Install analyst or set SKM_ANALYST_ROOT")
    else:
        print("  no - forensics bash-log/git. Enable: "
              "harness hooks --target <project> --run-report on")

    bl = rep.get("bash_log")
    print("\nbash-log (forensics · without return codes)  " + "─" * 14)
    if bl:
        print(f"  commands:     {bl['total']}  · test runs: {len(bl['tests'])}"
              f"  · lint runs: {len(bl['lints'])}")
        print("  (log PreToolUse — you can see WHAT they were chasing, did it pass; pass/fail — in run-report)")
    else:
        print("  no log ~/.claude/logs/bash-commands.jsonl")

    git = rep.get("git")
    print("\ngit  " + "─" * 55)
    if git:
        print(f"  tree:     {'NOT clean' if git.get('dirty') else 'clean'}"
              f"  ({git.get('working_files', 0)} uncommitted)")
        if git.get("diffstat") is not None:
            tail = git["diffstat"].splitlines()[-1] if git["diffstat"] else "no changes"
            print(f"  vs {git.get('base')}: {tail}")
    else:
        print("  not git-repository (or git not available)")

    if rep.get("observer"):
        ob = rep["observer"]
        print("\nobserver  " + "─" * 50)
        print(f"  entries: {ob['lines']}  · alerts (loop/error): {len(ob['alerts'])}")

    if rep.get("health"):
        h = rep["health"]
        print("\nhealth (hub)  " + "─" * 46)
        print(f"  status: {h.get('status')}  · memory-daemon: "
              f"{'up' if h.get('memory_daemon') else 'down'}  · round-trip: "
              f"{'ok' if h.get('roundtrip') else 'no'}")

    print("\nRESULT  " + "─" * 56)
    for r in rep["red"]:
        print(f"  ✗ {r}")
    for r in rep["reasons"]:
        print(f"  ⚠ {r}")
    if rep["repass"]:
        print("  Unverified → REPEAT PASS (engine was unavailable during formation):")
        for item in rep["repass"]:
            print(f"    ↻ {item}")
    if not (rep["red"] or rep["reasons"] or rep["repass"]):
        print("  ✓ clean run: tests/lint green, wood clean, bypass/no delays")
    # learning loop reminder (does not affect the verdict - the lessons are waiting for the person, not a running bug)
    pending = rep.get("pending_lessons") or 0
    if pending:
        print(f"  📚 {pending} lesson(ov) analyst waiting for review - analyst review · promote: analyst promote <id>")
    print()


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_analyze(env, argv):
    """maind analyze [--project ID | --cwd] [--session UUID] [--base B] [--json] [--no-health]
    — post-run analysis of the run: run-report + bash-log + observer + git + health → verdict."""
    opts, _ = parse_args(argv, {"--project": "str", "--cwd": "bool", "--session": "str",
                                "--base": "str", "--json": "bool", "--no-health": "bool"})
    if opts["help"]:
        print("maind analyze [--project ID | --cwd] [--session UUID] [--base B] "
              "[--json] [--no-health]\n"
              "  Post-run analysis «did everything work?»: run-report (primary) + bash-log + "
              "observer + git + health → GREEN/ATTENTION/RED.")
        return
    config, _src = load_config(env)
    project = _target(env, config, opts)
    rep = analyze_report(env, config, project, session=opts["session"] or None,
                         base=opts["base"] or None, with_health=not opts["no_health"])
    if opts["json"]:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_human(rep)
    # non-zero code on RED — to analyze was suitable as a gate in scripts
    if rep["verdict"] == "RED":
        raise SystemExit(1)
