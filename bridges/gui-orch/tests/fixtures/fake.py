"""Fake `swissknifeman orch ...`: canned answers of the conductor CLI by argv; every call is logged to $HOME/umbrella.log.

Scenarios (the wrappers umbrella-*): ok, empty (no runs), fail (exit 4 with ANSI noise), garbage (exit 0, not JSON),
missing (every run is RUN_UNKNOWN), escape (observe prints a report path outside the reports folder), symlink (the
report is a symlink to a file outside it).
"""
import json
import os
import sys

RUNS = [
    {"run_id": "cnd-new", "status": "running", "reason_code": None, "created": "2026-10-17T09:00:00Z",
     "items": ["P2.1", "P2.2"], "resumes": 1},
    {"run_id": "cnd-old", "status": "finished", "reason_code": None, "created": "2026-10-16T10:00:00Z",
     "items": ["P1.1"], "resumes": 0},
    {"run_id": "cnd-bad", "status": "unreadable"},
    {"run_id": "cnd-orphaned", "status": "orphaned", "reason_code": "RUN_ORPHANED", "owner": None},
]
OWNER = {"pid": 123, "host": "test-host", "started_at": "2026-10-17T09:00:00Z", "command": "run"}
RUNS[0]["owner"] = OWNER
USED = {"provider": "codex", "model": "recorded-model", "effort": "high", "class": "implementation",
        "argv": ["PRIVATE_ARGV"], "env": {"TOKEN": "PRIVATE_ENV"}}
STATUS = {
    "status": "running", "reason_code": None, "run": "cnd-new", "lines": 12, "last_ts": "2026-10-17T09:05:00Z",
    "current": {"item": "P2.2", "stage": "executor.1", "role": "executor", "route": "claude-code", "since": "2026-10-17T09:04:00Z"},
    "beacon": None,
    "items": [
        {"item": "P2.1", "stages": 4, "outcome": "done", "reason_code": None, "last": {"stage": "close", "verdict": "pass", "ts": "t"}},
        {"item": "P2.2", "stages": 1, "outcome": None, "last": {"stage": "scout", "verdict": None, "ts": "t"}},
        {"item": "P2.3", "stages": 2, "outcome": "blocked", "reason_code": "REVIEW_FAILED", "last": {"stage": "review.1", "verdict": "fail", "ts": "t"}},
        {"item": "P2.4", "stages": 3, "outcome": "done_with_deviations", "reason_code": None, "last": None},
        {"item": "P2.5", "stages": 0, "outcome": "weird", "reason_code": None, "last": None},
    ],
    "tokens": {"input": 1200, "output": 340}, "stop": None,
    "agents": [{"agent_run_id": "a1", "role": "executor", "step": "executor.1", "status": "running",
                "tokens": {"input": 10, "output": 5}}],
}
STATUS.update(lease=OWNER, limits={"items": {"P2.1": {"tokens_max": 100, "tokens_hard_max": 200},
                                           "P2.2": {"tokens_max": 0, "tokens_hard_max": 0}},
                                  "run_tokens_hard_max": {"value": 0, "source": "defaults"}, "limit_raises": []},
              beacons=[])
STATUS["items"][0].update(tokens={"input": 80, "output": 30}, usage_incomplete=False, routes={"executor": USED})
STATUS["items"][1].update(tokens={"input": 0, "output": 0}, usage_incomplete=True, routes={})
PROMPT = {"blocks": [{"kind": "input", "origin": "claim", "tokens": 42, "sha256": "a" * 64,
                       "text": "PRIVATE_PROMPT_TEXT", "argv": ["PRIVATE_ARGV"]}],
          "excluded": [{"kind": "skill", "reason": "not applicable", "id": "PRIVATE_EXCLUDED_ID", "text": "PRIVATE_TEXT"}],
          "budgets": {name: {"tokens": value} for name, value in (("core", 42), ("supporting", 0), ("retrieval", 0))},
          "text": "PRIVATE_WHOLE_PROMPT"}
QUESTIONS = {"run": "cnd-new", "questions": [
    {"item": "P2.3", "id": "Q1", "revision": 1, "kind": "decision", "text": "Which \x1b[31mshell\x1b[0m?", "answered": False,
     "age_s": 120, "overdue": True},
    {"item": "P2.4", "id": "Q2", "revision": 2, "kind": "clarification", "text": "Wording?", "answered": True,
     "age_s": 5, "overdue": False}]}
DOCTOR = [
    {"$schema": "urn:swissknifeman:aicore:check-result:v1", "check_id": "orch.conductor-gitignore", "status": "ok",
     "category": "config", "observed": "the conductor runtime folder is ignored", "evidence": [".swissknifeman/x"]},
    {"$schema": "urn:swissknifeman:aicore:check-result:v1", "check_id": "orch.sandbox", "status": "warn",
     "category": "config", "observed": "the provider sandbox cannot start \x1b[1mhere\x1b[0m",
     "evidence": ["bwrap: /usr/bin/bwrap", "bwrap-user-net-namespaces: Operation not permitted"]},
    {"$schema": "urn:swissknifeman:aicore:check-result:v1", "check_id": "aicore.ext", "status": "ok",
     "category": "integration", "observed": "not an orch check", "evidence": []},
]
REPORT = "# Observer report\n\nRun cnd-new.\n\n- <script>alert(1)</script>\n"


def main(scenario):
    home = os.environ.get("HOME", "/")
    with open(os.path.join(home, "umbrella.log"), "a", encoding="utf-8") as log:
        log.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\n")
    args = sys.argv[1:]
    if args == ["units", "list", "--json"]:
        print(json.dumps({"units": [{"id": "aicore", "root": os.environ["FAKE_AICORE_ROOT"]}]}))
        return 0
    if scenario == "fail":
        sys.stderr.write("\x1b[31mCONFIG_INVALID: broken \x1b[0mconfiguration\n")
        return 4
    if scenario == "garbage":
        sys.stdout.write("not json at all")
        return 0
    if args[:1] != ["orch"]:
        sys.stderr.write("USAGE: only orch is faked\n")
        return 2
    rest = args[1:]
    if rest[:2] == ["route", "explain"]:
        print(json.dumps({"used": USED, "available_now": {"route": {"provider": "claude-code", "model": "current-model",
                                                                   "effort": "high", "class": "implementation",
                                                                   "argv": ["PRIVATE_ARGV"], "env": "PRIVATE_ENV"},
                                                          "available": True, "stop": None}}))
        return 0
    if rest[:1] == ["doctor"]:
        print(json.dumps(DOCTOR))
        return 0
    if rest[:1] != ["conduct"]:
        sys.stderr.write("USAGE: unknown\n")
        return 2
    verb, tail = rest[1], rest[2:]
    run = tail[tail.index("--run") + 1] if "--run" in tail else None
    if verb == "gates":
        print(json.dumps({"cleared": [tail[-1]]} if "--clear" in tail else
                         {"gates": [{"provider": "codex", "until": "2026-10-20T20:00:00Z", "class": "quota",
                                     "code": "PROVIDER_QUOTA", "set_by": "cnd-new"}]}))
        return 0
    if verb in ("run", "resume", "continue", "answer", "release"):
        print(json.dumps({"ok": True, "verb": verb}))
        return 0
    if verb == "runs":
        rows = [] if scenario == "empty" else RUNS
        if "--limit" in tail:
            rows = rows[:int(tail[tail.index("--limit") + 1])]
        print(json.dumps({"runs": rows}))
        return 0
    if scenario in ("empty", "missing") or (run and run not in ("cnd-new", "cnd-old", "cnd-orphaned", "cnd-stopped", "cnd-waiting")):
        sys.stderr.write(f"RUN_UNKNOWN: no conductor run {run or ''} in /x\n")
        return 1
    if verb == "status":
        doc = dict(STATUS)
        if run in ("cnd-orphaned", "cnd-stopped"):
            doc.update(status=run[4:], lease=None, reason_code="RUN_ORPHANED" if run == "cnd-orphaned" else None)
        if run == "cnd-waiting":
            doc.update(status="waiting", lease=None, reason_code="WAITING_DECISION",
                       waiting=[{"item": "P2.3", "question_ids": ["Q1", "esc-1"], "since": "2026-10-23T12:00:00Z"}])
        print(json.dumps(doc))
        return 0
    if verb == "prompt" and tail[:1] == ["explain"]:
        print(json.dumps(PROMPT))
        return 0
    if verb == "timeline":
        print(json.dumps({"run": run, "item": None, "intervals": [
            {"item": "P2.1", "stage": "executor.1", "role": "executor", "route": "codex/gpt-6-sol/high",
             "start": "2026-10-20T10:00:01Z", "end": "2026-10-20T10:05:00Z", "duration_s": 299, "status": "interrupted"},
            {"item": "P2.1", "stage": "executor.1", "role": "executor", "route": "codex/gpt-6-sol/high",
             "start": "2026-10-20T11:00:02Z", "end": "2026-10-20T11:00:12Z", "duration_s": 10, "status": "done",
             "verdict": "done sk-" + "T" * 60},
            {"item": "P2.1", "stage": "checks.1", "role": "deterministic", "route": None,
             "start": "2026-10-20T11:00:13Z", "end": None, "duration_s": None, "status": "open"}]}))
        return 0
    if verb == "questions":
        print(json.dumps(QUESTIONS))
        return 0
    if verb == "observe":
        folder = os.path.join(os.getcwd(), ".swissknifeman", "orch", "reports", run)
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, "observer.md")
        outside = os.path.join(home, "outside.md")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("SECRET OUTSIDE\n")
        if scenario == "symlink":
            if os.path.lexists(target):
                os.unlink(target)
            os.symlink(outside, target)
        else:
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(REPORT)
        print(json.dumps({"json": os.path.join(folder, "observer.json"),
                          "markdown": outside if scenario == "escape" else target}))
        return 0
    sys.stderr.write("USAGE: unknown verb\n")
    return 2
