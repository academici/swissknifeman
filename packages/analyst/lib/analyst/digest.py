"""analyst digest — deterministic extraction of CANDIDATE lessons from run-report run.

Primary source - run-report (SessionEnd-hook harness writes <project>/.claude/runs/<sid>.json,
having already distilled the transcript). digest takes ONLY high-precision signals (not «guesses insights»
— is a conscious boundary MVP):

  A. resolved-failure — check (test/lint) fell and then passed in the same run
     («worked after N attempts») → lesson-gotcha with evidence test-pass;
  B. workaround — agent explicitly wrote a bypass in dev-loop-signal (devloop.workarounds);
  C. pathology — detector `analyst.pathology.detect` found pathology With ready remediation
     (file-reread/tool-error-loop/protected-write/no-verify) And the code RECIDATES: the same
     pathology encountered ≥2 times in the last 5 runs of the project. One-time operation -
     noise of one session, does not create a lesson (the rest is a signal for `maind analyze`, not for memory);
  D. workflow_relaunch — run-report hook (P1.2, `_lib.py`) has already grouped calls `Workflow`
     by `runId`/name and gave the finished group `{name, count, statuses}` when `count ≥
     _WF_RELAUNCH_MIN`. Diagnostic, non-alarm signal (
     ): «work flow script required N iterations resume/debugging
     within one session» — not an error (standard `resumeFromRunId`-pattern), but the candidate is a lesson
     «bring the script in isolation dev-loop, not in the main interactive session».

Candidates are written in ephemeral (LOCAL, unreviewed). The person clarifies the essence of the fix at `analyst review`;
promoter - human only. Extractors A/B — PURE functions (run_report → [lesson]) for the sake of
testability; C (`extract_pathologies`) — conscious exception to this rule: rule
relapse requires looking at the HISTORY of the project runs, and not just the current one run_report, therefore
she reads (read-only) `<project>/.claude/runs/*.json` — IO is limited to reading, does not write anything.
Protective: any missing/broken field run-report is skipped, digest does not crash."""
import json
import os
import re
from pathlib import Path

from aicore.config import ConfigError

from aicore.util.cli import parse_args
from aicore.util.io import safe_load_json
from aicore.util.term import die
from .pathology import detect as detect_pathologies
from .run_reports import find_run_report
from .lessons import (ACTIVE_STATES, add_candidate, audit_append,
                      classify_consolidation, event_append, jaccard,
                      new_lesson, similar_lessons)
from .runs import neutral_run_report
from .settings import DEFAULT_THRESHOLDS, load_thresholds

_SIMILAR_CMD = 0.6   # threshold «essentially the same command» for pair fail→pass

# ── filter «real check vs reconnaissance» for signal A ──────────────────────
# Hook (run-report/_lib.py TEST_PAT/LINT_PAT) puts in bash.tests/lints ANY command
# with runner substring - including reconnaissance like `ls .bin | grep -E 'vitest|pest'`.
# Like this «fell→passed» couple gives trash lesson (trigger≈action, nothing to fix).
# Cutting it off: a lesson from resolved-failure only makes sense if the command ACTUALLY executes
# test/lint-runner, and does not search for his name with a grep and does not break through the presence through `|| ...`.

# Runner actually STARTS: name in command position (after the separator/started,
# incl. `vendor/bin/pest`, `npm test`), not an argument grep/ls. `\b(?<![-/])` doesn't catch
# `--test`/`some/test`; for `vendor/bin/pest` and `npm test` — explicit subexpressions.
_RUNNER_EXEC = re.compile(
    r"(?:(?:^|[;&|]\s*|\bcd\s+\S+\s+|\bxargs\s+)"
    r"(?:pytest|phpunit|pest|jest|vitest|unittest|ruff|flake8|pylint|mypy|eslint|"
    r"phpstan|psalm|pint|black|isort|tsc|prettier|composer|py_compile)\b"
    r"|vendor/bin/(?:pest|phpunit|pint|phpstan|psalm)\b"
    r"|(?:npm|yarn|pnpm)\s+(?:run\s+)?(?:test|lint)\b"
    r"|(?:go|cargo)\s+test\b"
    # Laravel: `php artisan test` (+ keys like --filter) and Sail-wrapper `sail test`
    # (documented shortcut Sail on `artisan test`, sail/bin/sail) — N2a: without
    # this thread resolves the dominant runner Laravel-ecosystem stack, loop
    # training did not see any «fell→passed» on it.
    r"|(?:php\s+artisan|sail)\s+test\b"
    r"|(?<![\w.])(?:validate|test)\.sh\b)", re.I)  # path scripts/validate.sh — is STARTING

# Explicit reconnaissance: a command CONTAINING the runner name only as a search argument
# (`grep … vitest`, `ls … | grep pest`) — not a performance, but a test of presence (what
# would be the suffix - `|| echo NO`, `2>/dev/null` — she didn't have). N2b: blanket failure
# one fact of existence `||` in the team hacked and legitimate guard-patterns (`pytest ||
# exit 1`, `... | xargs pytest`) — the runner is actually executed there and its exit-code
# defines a branch `||`, discard such resolved-failure is incorrect; discrimination
# «sample vs run» and so does the check below (runner in the first segment before
# `|`/`;`/`&`).
_DIAGNOSTIC_CMD = re.compile(r"\b(?:grep|rg|ag|find|ls|cat|which|command\s+-v)\b", re.I)


def _is_real_check(cmd):
    """True, if the command actually RUN the test/lint runner (and does not search for it with grep).
    Cuts diagnostic noise from the signal A — resolved-failure on such a pair would give
    lesson with trigger≈action, in which there is nothing to repair."""
    if not cmd or not _RUNNER_EXEC.search(cmd):
        return False
    # runner is mentioned ONLY as an intelligence argument, there is no real launch → noise
    if _DIAGNOSTIC_CMD.search(cmd) and not _RUNNER_EXEC.search(re.split(r"[|;&]", cmd)[0]):
        return False
    return True

# source run-report — single run_reports.find_run_report (reveals ~ on the way)

# ── signal C: recurrent pathologies (pathology + relapse rule) ─────────
PATHOLOGY_WINDOW = DEFAULT_THRESHOLDS.pathology_window       # relapse rule: window of how many last runs we look at
PATHOLOGY_MIN_HITS = DEFAULT_THRESHOLDS.pathology_min_hits   # code must occur in at least this many runs of the window

# Codes with ready remediation → potential lesson (upon relapse). Other codes
# pathology.detect — signals for analyze/dashboard, do NOT go into memory (no
# specific «what to do», only diagnosis - nothing to teach the agent).
_PATHOLOGY_REMEDIATIONS = {
    "file-reread": "keep the read card; to re-apply use "
                   "notes/plan, not re-read",
    "tool-error-loop": "after 2 identical tool failures, change the approach, don’t hammer",
    "protected-write": "generated-do not edit pack files - overrides in "
                       ".claude/rules/*-overrides.md",
    "no-verify": "changed the code - run tests before the session ends",
}


def _fmt_num(v):
    """Compact number string for evidence-tags: float without long tail, the rest str()."""
    if isinstance(v, float):
        return str(round(v, 3))
    return str(v)


def _recent_run_reports(project_path, current, limit=PATHOLOGY_WINDOW):
    """Latest `limit` run-report'ov of the project (current is guaranteed among them - even
    if it has not yet reached the disk/there is an outdated version under the same session_id).

    Read the rest from the disk `<project>/.claude/runs/*.json`, fresh by mtime first;
    broken/not-dict files are skipped (safe_load_json). Cheap: run-report — compact JSON."""
    runs_dir = Path(os.path.expanduser(str(project_path))) / ".claude" / "runs"
    on_disk = []
    if runs_dir.is_dir():
        files = sorted((p for p in runs_dir.glob("*.json") if p.is_file()),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files:
            rec = safe_load_json(p, None)
            if isinstance(rec, dict):
                on_disk.append(rec)
    cur_sid = current.get("session_id") if isinstance(current, dict) else None
    if cur_sid:
        on_disk = [r for r in on_disk if r.get("session_id") != cur_sid]
    reports = ([current] if isinstance(current, dict) else []) + on_disk
    return reports[:limit]


def _pathology_hit_counts(project_path, current, thresholds=DEFAULT_THRESHOLDS):
    """{code: how many runs from the window contain ≥1 find this code}. detect driving
    for each window run separately - it’s clean and cheap (see pathology.py)."""
    counts = {}
    for rr in _recent_run_reports(project_path, current, thresholds.pathology_window):
        for code in {f.get("code") for f in detect_pathologies(rr)}:
            counts[code] = counts.get(code, 0) + 1
    return counts


# ── extractors (clean) ─────────────────────────────────────────────────────
def _check_entries(run_report):
    """[{command, ok}] tests+lint run (protective, only with non-empty command)."""
    bash = run_report.get("bash") or {}
    out = []
    for key in ("tests", "lints"):
        for e in (bash.get(key) or []):
            if isinstance(e, dict) and e.get("command"):
                out.append(e)
    return out


def extract_resolved_failures(run_report, *, scope, project):
    """Signal A: command that crashed and then passed (by Jaccard ≥ threshold) → gotcha."""
    sid = run_report.get("session_id") or ""
    files = run_report.get("files_changed") or []
    # only REAL runner runs - reconnaissance/probing (`grep vitest`, `... || echo`)
    # hook puts in bash.tests by substring, but the lesson from it is garbage (see _is_real_check).
    entries = [e for e in _check_entries(run_report) if _is_real_check(e.get("command", ""))]
    failed = [e for e in entries if not e.get("ok", True)]
    passed = [e for e in entries if e.get("ok", True)]
    out, seen = [], set()
    for f in failed:
        fcmd = f.get("command", "")
        if fcmd in seen:
            continue
        best = max((jaccard(fcmd, p.get("command", "")) for p in passed), default=0.0)
        if best < _SIMILAR_CMD:
            continue
        seen.add(fcmd)
        attempts = sum(1 for e in entries if jaccard(fcmd, e.get("command", "")) >= _SIMILAR_CMD)
        top_files = [Path(x).name for x in files[:3]]
        trigger = f"check crashed and was fixed in the run: {fcmd}"
        # action — pure semantic text (Jaccard/surfacing); counters+files → meta;
        # instructions for reviewer → review_hint (do not go into memory).
        action = f"fix the reason why the check failed: {fcmd}"
        out.append(new_lesson(
            trigger=trigger, action=action, kind="gotcha", scope=scope,
            session_id=sid, project=project, detector="resolved-failure",
            evidence=[f"session:{sid}", "test-pass", f"attempts:{attempts}"],
            meta={"attempts": attempts, "files": top_files},
            review_hint="Specify the ESSENCE of the fix when review (what exactly was corrected).",
            tests_total=attempts, tests_passed=max(attempts - 1, 0)))
    return out


def extract_workarounds(run_report, *, scope, project):
    """Signal B: explicitly written dev-loop workarounds (devloop.workarounds) → gotcha."""
    sid = run_report.get("session_id") or ""
    devloop = run_report.get("devloop") or {}
    out, seen = [], set()
    for w in (devloop.get("workarounds") or []):
        text = w if isinstance(w, str) else json.dumps(w, ensure_ascii=False)
        text = " ".join(text.split()).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        trigger = f"the situation required a workaround: {text[:60]}"
        out.append(new_lesson(
            trigger=trigger, action=text, kind="gotcha", scope=scope,
            session_id=sid, project=project, detector="workaround",
            evidence=[f"session:{sid}", "workaround"]))
    return out


def extract_pathologies(run_report, project_path, thresholds=DEFAULT_THRESHOLDS):
    """Signal C: run pathologies (`analyst.pathology.detect`) with ready-made remediation
    And a relapse - the same code was encountered ≥PATHOLOGY_MIN_HITS times in the last
    PATHOLOGY_WINDOW project runs (current inclusive). One-time trigger
    lesson does not create (noise of one session); codes without remediation in _PATHOLOGY_REMEDIATIONS
    don't go to lessons at all (are signals for analyze, not for memory).

    scope/project are derived from project_path (as in cmd_digest) — signature intentional
    (run_report, project_path), and not (run_report, *, scope, project): C need a real one
    project path to read the run history (see docstring module about IO-exception)."""
    if not isinstance(run_report, dict):
        return []
    findings = detect_pathologies(run_report)
    if not findings:
        return []
    project = Path(os.path.expanduser(str(project_path))).name
    scope = f"project:{project}"
    sid = run_report.get("session_id") or ""
    hit_counts = None  # we think lazily: the story is read only if the report contains candidate code at all
    out, seen = [], set()
    for f in findings:
        code = f.get("code")
        remediation = _PATHOLOGY_REMEDIATIONS.get(code)
        if not remediation or code in seen:
            continue
        if hit_counts is None:
            hit_counts = _pathology_hit_counts(project_path, run_report, thresholds)
        hits = hit_counts.get(code, 0)
        if hits < thresholds.pathology_min_hits:
            continue
        seen.add(code)
        trigger = (f"recurrence of run pathology «{code}» ({hits}/{thresholds.pathology_window} "
                  f"last runs): {f.get('evidence') or ''}")
        out.append(new_lesson(
            trigger=trigger, action=remediation, kind="gotcha", scope=scope,
            session_id=sid, project=project, detector=code,
            evidence=[f"session:{sid}", f"recurred:{hits}/{thresholds.pathology_window}",
                     f"metric:{_fmt_num(f.get('metric'))}",
                     f"threshold:{_fmt_num(f.get('threshold'))}"],
            meta={"severity": f.get("severity"), "data": f.get("data") or {}}))
    return out


def extract_workflow_relaunch(run_report, *, scope, project):
    """Signal D: slice `workflow_relaunch` run-report'a - ready-made groups
    `{name, count, statuses}` are already filtered by the threshold hook `_WF_RELAUNCH_MIN`.
    Diagnostic candidate, not «error»: N resume/relaunch one workflow in one
    sessions - proxy «script is unstable, debugged on the fly inside the main session»
    ."""
    sid = run_report.get("session_id") or ""
    out = []
    for g in (run_report.get("workflow_relaunch") or []):
        if not isinstance(g, dict) or not g.get("name") or not g.get("count"):
            continue
        name, count, statuses = g["name"], g["count"], g.get("statuses") or {}
        trigger = f"workflow «{name}» restarted/summarized {count}× in one session"
        action = ("bring the workflow script to a stable state in an isolated "
                  "dev-loop BEFORE the fan-out, do not debug it with edits inside the main "
                  "interactive session (resumeFromRunId after Edit — normal, but frequent "
                  "repetition signals the immaturity of the just written script)")
        out.append(new_lesson(
            trigger=trigger, action=action, kind="gotcha", scope=scope,
            session_id=sid, project=project, detector="workflow-relaunch",
            evidence=[f"session:{sid}", f"count:{count}"],
            meta={"name": name, "statuses": statuses}))
    return out


def extract_candidates(run_report, *, scope, project, project_path=None, thresholds=DEFAULT_THRESHOLDS):
    """All high-precision run candidates (A + B + C + D). Duplicates by id collapse onto records.

    project_path — optional (backwards compatible clean A/B-calls without path to
    disk, see tests): without it signal C (requires run history) simply won't start."""
    if not isinstance(run_report, dict):
        return []
    out = (extract_resolved_failures(run_report, scope=scope, project=project)
           + extract_workarounds(run_report, scope=scope, project=project)
           + extract_workflow_relaunch(run_report, scope=scope, project=project))
    if project_path is not None:
        out += extract_pathologies(run_report, project_path, thresholds)
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_digest(env, argv):
    """analyst digest [--cwd] [--session UUID] [--dry-run] [--json]
    — extract candidate lessons from fresh run-report in .claude/analyst/lessons/ephemeral/."""
    opts, _ = parse_args(argv, {"--cwd": "bool", "--session": "str",
                                "--project": "str", "--dry-run": "bool", "--json": "bool"})
    if opts["help"]:
        print("analyst digest [--cwd] [--session UUID] [--dry-run] [--json]\n"
              "  Deterministically extracts candidate lessons from run-report run "
              "(resolved-failure / workaround / recurrent pathology) → ephemeral. "
              "The promoter is a person.")
        return

    ppath = os.getcwd()
    try:
        thresholds = load_thresholds(ppath)
    except ConfigError as err:
        die(str(err))
    rr = neutral_run_report(ppath, opts["session"] or None)
    # D90 projection has no raw-shaped bash/workflow/workaround evidence.  Digest consumes
    # it only once a future neutral semantic explicitly carries those fields; otherwise this
    # is the bounded legacy Claude reader fallback, never fabricated zero/default evidence.
    if not isinstance(rr, dict) or not any(key in rr for key in ("bash", "workflows", "devloop")):
        rr = find_run_report(ppath, opts["session"] or None)
    if not rr:
        die("no run-report in .claude/runs — enable run capture: "
            "harness hooks --target . --run-report on, then run a session Claude Code")

    project = Path(os.path.abspath(ppath)).name
    scope = f"project:{project}"
    cands = extract_candidates(rr, scope=scope, project=project, project_path=ppath, thresholds=thresholds)

    if opts["dry_run"] or opts["json"]:
        payload = {"session": rr.get("session_id"), "project": project,
                   "candidates": [{"id": c["id"], "kind": c["kind"], "detector": c["provenance"]["detector"],
                                   "trigger": c["trigger"]} for c in cands]}
        if opts["json"]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"\nanalyst digest (dry-run) — session {payload['session']}: "
                  f"{len(cands)} candidate(ov)\n")
            for c in payload["candidates"]:
                print(f"  • [{c['detector']}] {c['trigger']}")
            print()
        return

    created = skipped = 0
    for L in cands:
        # semantic dedup (P-6): NOOP by mem0-classifications = duplicate active
        # lesson (same situation AND action) → are not fertile. add_candidate only catches accurate id.
        sim = similar_lessons(ppath, L["trigger"], L["action"],
                              states=ACTIVE_STATES, threshold=0.4)
        if classify_consolidation(L["trigger"], L["action"], sim)["action"] == "NOOP":
            skipped += 1
            continue
        _lesson, was_new = add_candidate(ppath, L)
        if not was_new:
            skipped += 1
            continue
        created += 1
        audit_append(ppath, {"action": "digest", "id": L["id"],
                             "detector": L["provenance"]["detector"],
                             "session": rr.get("session_id"), "state": "ephemeral"})
        # signal event for confidence: run where the lesson is «worked» (fix/round passed).
        # append-only; recompute will restore S/N from events.ndjson (not from this counter).
        event_append(ppath, {"id": L["id"], "source": "digest",
                             "session": rr.get("session_id"),
                             "sessions_total": 1, "sessions_success": 1,
                             "tests_total": int(L.get("tests_total", 0)),
                             "tests_passed": int(L.get("tests_passed", 0))})

    print(f"\nanalyst digest — session {rr.get('session_id')}: "
          f"{created} new(s) candidate(ov) in ephemeral"
          f"{f', {skipped} missing (take/similar to existing)' if skipped else ''}.")
    if created:
        print("  See: analyst review   ·   promoter (person): analyst promote <id>\n")
    else:
        print("  No new high-precision signals were found in the run.\n")
