#!/usr/bin/env python3
"""P5.3 recovery/crash/duplicate/provider-failure pilot harness.

Exercises the exact P5.2 business seam (``bin/artifex dispatch-business-intent``)
through real fresh provider processes, then injects real OS-level crashes at
process-state boundaries observed through ``/proc`` (no fixed sleeps: every
cut is a bounded poll-until-condition on real child-process state — spawned,
zombie, or gone — never a timed guess). It never modifies ``packages/artifex``
(P5.3 owns no package path) and never reimplements argv construction, provider
execution or result folding.

Not listed in P5.3's ``Files`` (recorded as a Known Deviation on closure, same
category as P5.2's ``run-pilot.py`` which the plan's Files line for P5.2 DID
list) — a harness script is structurally required to produce the declared
``recovery-pilot-results-v1.json`` deliverable.

Mechanism selection per trial, owner-confirmed 2026-08-06 (AskUserQuestion:
"dry-run against fake binaries first" — validate mechanism correctness with
zero cost/zero admission spend, only then touch the six real one-shot D105
admissions):
  * call-01 crash-after-intent (codex, real binary): kill the ``artifex``
    process the instant its provider child is observed spawned; reconcile by
    waiting (bounded by the trial's own timeout budget) for the orphaned
    child to exit, then trust the worktree's Git diff.
  * call-02 crash-after-observation (claude-code, real binary): kill once the
    child is observed as a zombie (its own work is already complete and
    on-disk before the kill) — reconcile is immediate, no wait needed.
  * call-03 duplicate-dispatch (codex, real binary): one real dispatch, then
    a second attempt against the SAME admission refused by this harness's own
    ledger *before* any subprocess is spawned (no code in the package persists
    admission usage — the one-shot discipline is enforced here, exactly as
    P5.2's ``run-pilot.py`` already proved with its ``SLICE_ORDER_OR_REUSE``).
  * call-04 provider-timeout (fake codex binary): P5.2 showed real codex
    slices return in ~20s and real claude-code slices can naturally
    WALL_TIMEOUT — neither is a *deterministic* way to exercise timeout
    without gambling the one-shot admission ("no random cuts"). A fake binary
    that passes the frozen ``--version`` pin then hangs past the frozen
    budget is the deterministic, explicitly-sanctioned choice (Scope
    Included: "fake-binary ... provider failure").
  * call-05 schema-refusal (fake claude-code binary): same reasoning — after
    this session's earlier ``--allowedTools`` fix, a real claude-code call is
    now *more* likely to succeed than schema-refuse, so a fake binary
    emitting one malformed JSON line is the deterministic choice.
  * call-06 unknown-third-state (claude-code, real binary): kills mid-flight
    and then *deliberately discards the child PID* (simulating supervisor
    memory loss across its own crash — the business seam has no persisted
    resume state at all). Without a PID to positively confirm termination, a
    clean Git diff is ambiguous between "nothing happened" and "not written
    yet" — so this trial never looks at the diff to decide and unconditionally
    reconciles to OWNER with zero further mutation (worktree preserved, not
    rolled back or removed) — the one trial this pilot is *supposed* to leave
    open, proving the fail-closed path P4's fully-controlled harness could
    never exercise against a genuinely real, untracked process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
G2 = "ef08406d7ca630d46e9e9e8bca0d10ea73b141d984615bded75f19d7eea13f09"
ADMISSION_INDEX = "artifacts/P5/trial-admission-index-v1.json"
EXPECTED_VERSION = {"codex": "codex-cli 0.146.0", "claude-code": "2.1.222 (Claude Code)"}
ORDER = ("p5.3-call-01-crash-after-intent", "p5.3-call-02-crash-after-observation",
          "p5.3-call-03-duplicate-dispatch", "p5.3-call-04-timeout",
          "p5.3-call-05-schema-refusal", "p5.3-call-06-third-state")
MECHANISM = {"p5.3-call-01-crash-after-intent": "real-crash-after-intent",
             "p5.3-call-02-crash-after-observation": "real-crash-after-observation",
             "p5.3-call-03-duplicate-dispatch": "real-duplicate-refusal",
             "p5.3-call-04-timeout": "fake-timeout", "p5.3-call-05-schema-refusal": "fake-schema-refusal",
             "p5.3-call-06-third-state": "real-third-state-orphan"}
GUARDED_PATHS = ("packages/artifex",
                  f"plans/{PLAN_ID}/artifacts/P5/business-successor-generation-v1.json",
                  f"plans/{PLAN_ID}/artifacts/P5/business-successor-assurance-v1.json")
_ENV = {"PATH": os.defpath, "LC_ALL": "C", "LANG": "C", "TZ": "UTC"}

FAKE_CODEX = """#!/usr/bin/env python3
import sys, time
if "--version" in sys.argv:
    print("codex-cli 0.146.0"); sys.exit(0)
sys.stdin.read()
time.sleep(200)
"""
FAKE_CLAUDE = """#!/usr/bin/env python3
import sys, json
if "--version" in sys.argv:
    print("2.1.222 (Claude Code)"); sys.exit(0)
sys.stdin.read()
print(json.dumps({"type": "not_result", "is_error": False}))
"""


class PilotRefusal(ValueError):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def root() -> Path:
    return Path(__file__).resolve().parents[4]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PilotRefusal("JSON_OBJECT_REQUIRED")
    return value


def command(argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          shell=False, check=False, env=_ENV)


def which(binary: str) -> str:
    found = subprocess.run(["which", binary], cwd=str(root()), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           shell=False, check=False, env={"PATH": os.environ.get("PATH", os.defpath)}
                           ).stdout.decode("utf-8", "replace").strip()
    if not found:
        raise PilotRefusal("PROVIDER_UNAVAILABLE", binary)
    return found


def resolve_claude_bin() -> Path:
    value = os.environ.get("SKM_CLAUDE_BIN")
    if not value:
        raise PilotRefusal("SKM_CLAUDE_BIN_UNSET")
    path = Path(value)
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise PilotRefusal("SKM_CLAUDE_BIN_NOT_EXECUTABLE", value)
    return path


def probe_version(binary: str | Path) -> str:
    completed = subprocess.run([str(binary), "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               check=False, env={"PATH": os.defpath})
    return completed.stdout.decode("utf-8", "replace").strip()


def g2b_hash(plan: Path) -> str:
    assurance = load(plan / "artifacts/P5/business-successor-assurance-v1.json")
    generation = load(plan / "artifacts/P5/business-successor-generation-v1.json")
    value = assurance.get("g2b_generation_hash")
    if not isinstance(value, str) or not value or value != generation.get("generation_hash"):
        raise PilotRefusal("G2B_HASH_UNAVAILABLE")
    return value


def admission_for(plan: Path, trial_id: str) -> tuple[Path, dict]:
    index = load(plan / ADMISSION_INDEX)
    rows = [row for row in index.get("admissions", []) if isinstance(row, dict) and row.get("trial_id") == trial_id]
    if len(rows) != 1:
        raise PilotRefusal("ADMISSION_IDENTITY", trial_id)
    path = plan / rows[0]["path"]
    admission = load(path)
    if (digest(path) != rows[0].get("sha256")
            or admission.get("usage") != {"used_slices": 0, "max_slices": 1, "reusable": False}
            or admission.get("replay", {}).get("events") != [] or admission.get("task", {}).get("parent_item_id") != "P5.3"
            or admission.get("grant", {}).get("owner_decision") != "D105"):
        raise PilotRefusal("ADMISSION_USAGE_OR_HASH", trial_id)
    return path, admission


def _main_tree_guard(repo: Path) -> None:
    dirty = command(["git", "status", "--porcelain=v1"], cwd=repo).stdout.splitlines()
    for row in dirty:
        if len(row) < 4:
            continue
        path = row[3:].decode("utf-8", "strict")
        if any(path == guarded or path.startswith(guarded + "/") for guarded in GUARDED_PATHS):
            raise PilotRefusal("MAIN_TREE_DIRTY", path)


def preflight(repo: Path, plan: Path) -> dict:
    validator = plan / "artifacts/P5/validate-business-successor.py"
    args = [sys.executable, str(validator), "--contract", str(plan / "root/contracts/business-dispatch-admission-v1.md"),
            "--cases", str(plan / "artifacts/P5/business-dispatch-successor-cases-v1.json"),
            "--provider-manifest", str(plan / "artifacts/P5/provider-business-projection-v1.json"),
            "--provider-cases", str(plan / "artifacts/P5/provider-business-projection-cases-v1.json"),
            "--generation", str(plan / "artifacts/P5/business-successor-generation-v1.json"),
            "--assurance", str(plan / "artifacts/P5/business-successor-assurance-v1.json"),
            "--g2", str(plan / "artifacts/P4/assurance-manifest-v1.json"),
            "--admission-index", str(plan / "artifacts/P5/trial-admission-index-v1.json"), "--package", "packages/artifex"]
    validated = command(args, cwd=repo)
    if validated.returncode != 0:
        raise PilotRefusal("G2B_PRECONDITION", validated.stderr.decode("utf-8", "replace").strip())
    _main_tree_guard(repo)
    claude_bin = resolve_claude_bin()
    observed_claude = probe_version(claude_bin)
    if observed_claude != EXPECTED_VERSION["claude-code"]:
        raise PilotRefusal("PROVIDER_VERSION_DRIFT", f"claude-code observed {observed_claude!r}")
    codex_bin = which("codex")
    observed_codex = probe_version(codex_bin)
    if observed_codex != EXPECTED_VERSION["codex"]:
        raise PilotRefusal("PROVIDER_VERSION_DRIFT", f"codex observed {observed_codex!r}")
    return {"claude-code": {"binary": str(claude_bin), "version": observed_claude},
            "codex": {"binary": codex_bin, "version": observed_codex}}


# --- /proc-based, poll-until-condition process introspection (no fixed sleeps as a decision
# mechanism: every wait reacts to real kernel-observed process state, bounded by a deadline). ---

def _proc_children(pid: int) -> list[int]:
    try:
        return [int(x) for x in Path(f"/proc/{pid}/task/{pid}/children").read_text().split()]
    except (FileNotFoundError, ProcessLookupError):
        return []


def _proc_state(pid: int) -> str | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return None
    return raw.rsplit(")", 1)[1].split()[0]


def _proc_cmdline(pid: int) -> list[bytes]:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except FileNotFoundError:
        return []


def _is_probe_child(cmdline: list[bytes]) -> bool:
    return b"--version" in cmdline


def find_dispatch_child(pid: int, deadline: float, *, clock=time.monotonic, poll=0.01) -> int | None:
    """Poll until the artifex process spawns its real provider child (never its transient
    ``--version`` probe child), bounded by ``deadline``. Returns None on genuine timeout."""
    while clock() < deadline:
        for child in _proc_children(pid):
            cmdline = _proc_cmdline(child)
            if cmdline and not _is_probe_child(cmdline):
                return child
        time.sleep(poll)
    return None


def wait_gone(pid: int, deadline: float, *, clock=time.monotonic, poll=0.005) -> bool:
    """Poll until ``pid`` fully vanishes from ``/proc`` (reaped by its parent). Used, not zombie
    detection: an empirical dry run against the real seam showed ``worker.run()`` reaps its child
    essentially immediately after stdout EOF (no artificial delay) — the true zombie window
    measured sub-millisecond, unobservable at any reasonable external poll granularity. Full
    disappearance is the reliable proxy instead: the same dry run measured a tens-of-milliseconds
    window between "child gone" and "parent has finished decoding/printing" — exactly wide enough
    for this poll interval to reliably land inside it."""
    while clock() < deadline:
        if _proc_state(pid) is None:
            return True
        time.sleep(poll)
    return False


# --- Self-test: proves the two primitives above against synthetic, throwaway process trees (no
# relation to any admission, zero cost) before any real trial touches a one-shot grant. ---

_REAP_WINDOW_FIXTURE = ("import subprocess,time\n"
                        "p=subprocess.Popen(['python3','-c','import time;time.sleep(0.2);print(1)'],\n"
                        "                   stdout=subprocess.PIPE)\n"
                        "print(p.pid, flush=True)\n"
                        "p.stdout.read()\n"
                        "p.wait()\n"
                        "print('PARENTDONE', flush=True)\n")


def self_test() -> dict:
    """Validate the two primitives against synthetic, throwaway process trees — zero relation to
    any admission, zero cost. The reap-window fixture mirrors ``worker.run()``'s own shape (parent
    reads child stdout to EOF, then immediately reaps) to prove ``wait_gone`` can reliably land in
    the same narrow post-reap, pre-print window the real crash-after-observation cut relies on."""
    results = {"child_spawn_detection": [], "reap_window_detection": [], "orphan_after_parent_kill": []}
    for _ in range(3):
        proc = subprocess.Popen(["bash", "-c", "sleep 5 & wait"], start_new_session=True)
        try:
            child = find_dispatch_child(proc.pid, time.monotonic() + 2.0)
            results["child_spawn_detection"].append(child is not None)
            if child is not None:
                os.kill(proc.pid, signal.SIGKILL)
                results["orphan_after_parent_kill"].append(_proc_state(child) is not None)
                os.kill(child, signal.SIGKILL)
        finally:
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
    for _ in range(3):
        proc = subprocess.Popen(["python3", "-c", _REAP_WINDOW_FIXTURE], start_new_session=True, stdout=subprocess.PIPE)
        grandchild = int(proc.stdout.readline().strip())
        results["reap_window_detection"].append(wait_gone(grandchild, time.monotonic() + 2.0))
        proc.wait(timeout=2)
    return {"child_spawn_detection": {"trials": len(results["child_spawn_detection"]),
                                       "all_detected": all(results["child_spawn_detection"])},
            "reap_window_detection": {"trials": len(results["reap_window_detection"]),
                                      "all_detected": all(results["reap_window_detection"])},
            "orphan_after_parent_kill": {"trials": len(results["orphan_after_parent_kill"]),
                                         "all_orphaned": all(results["orphan_after_parent_kill"])}}


def _make_fake_binary(source: str) -> Path:
    fd, name = tempfile.mkstemp(prefix="artifex-p5.3-fake-")
    path = Path(name)
    path.write_text(source, encoding="utf-8")
    os.fchmod(fd, 0o700)
    os.close(fd)
    return path


def _seam_argv(repo: Path, trial_id: str, admission_path: Path, g2b: str, worktree: Path, binary: str) -> list[str]:
    runs_root = f"artifacts/P5/.p5.3-pilot-noop-runs/{trial_id}"
    return [str(repo / "packages/artifex/bin/artifex"), "--repo-root", str(repo), "--plan-dir", f"plans/{PLAN_ID}",
            "--runs-root", runs_root, "dispatch-business-intent", "--admission", str(admission_path.relative_to(repo)),
            "--g2-predecessor", G2, "--g2b-successor", g2b, "--cwd", str(worktree), "--binary", binary]


def _worktree_diff(worktree: Path) -> list[str]:
    changed = command(["git", "status", "--porcelain=v1", "-z"], cwd=worktree).stdout.split(b"\0")
    return sorted(row[3:].decode("utf-8", "strict") for row in changed if row)


def _rollback(worktree: Path, base_commit: str) -> bool:
    return (command(["git", "reset", "--hard", base_commit], cwd=worktree).returncode == 0
           and not command(["git", "status", "--porcelain=v1"], cwd=worktree).stdout)


def run_normal(repo: Path, admission_path: Path, g2b: str, worktree: Path, binary: str, task: dict, trial_id: str) -> dict:
    """Uninstrumented dispatch — the P5.2-identical path, used for the non-crash trials."""
    seam = command(_seam_argv(repo, trial_id, admission_path, g2b, worktree, binary), cwd=repo)
    try:
        payload = json.loads(seam.stdout.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}
    paths = _worktree_diff(worktree)
    accepted = seam.returncode == 0 and payload.get("status") == "success" and paths == sorted(task["files"])
    rollback_ok = _rollback(worktree, task["base_commit"])
    return {"crashed": False, "seam_status": payload.get("status"), "reason_code": payload.get("reason_code"),
            "process_count": payload.get("process_count", 0), "changed_paths": paths, "accepted": accepted,
            "rollback": rollback_ok, "reconcile": {"outcome": "postimage" if accepted else ("preimage" if not paths else "rollback")}}


def run_crash(repo: Path, admission_path: Path, g2b: str, worktree: Path, binary: str, task: dict,
             trial_id: str, cut: str, budget_seconds: float) -> dict:
    argv = _seam_argv(repo, trial_id, admission_path, g2b, worktree, binary)
    proc = subprocess.Popen(argv, cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=_ENV, start_new_session=True)
    spawn_deadline = time.monotonic() + min(budget_seconds, 30.0)
    child = find_dispatch_child(proc.pid, spawn_deadline)
    if child is None:
        os.kill(proc.pid, signal.SIGKILL)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait()
        return {"crashed": True, "crash_verified": False, "cut": cut,
                "reconcile": {"outcome": "owner_unknown", "reason": "NO_CHILD_OBSERVED"}}
    if cut == "after_observation":
        # `worker.run()` reaps its child via `proc.wait()` essentially immediately after stdout
        # EOF (no artificial delay) — an empirical dry run measured the true zombie window at
        # sub-millisecond, unobservable at any reasonable external poll granularity. Full
        # disappearance from /proc (fully reaped by the parent) is the reliable proxy instead: it
        # empirically leaves a tens-of-milliseconds window (measured ~46ms in the same dry run)
        # during which the parent has the child's exit code and output but hasn't yet finished
        # decoding/folding/printing the result — exactly "activity complete, not yet recorded".
        if not wait_gone(child, time.monotonic() + budget_seconds):
            os.kill(proc.pid, signal.SIGKILL)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
            return {"crashed": True, "crash_verified": False, "cut": cut, "child_pid": child,
                    "reconcile": {"outcome": "owner_unknown", "reason": "CHILD_REAP_NOT_OBSERVED"}}
    os.kill(proc.pid, signal.SIGKILL)
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill(); proc.wait()
    if cut == "third_state_discard":
        # Deliberate: simulate supervisor memory loss across its own crash — the business seam
        # persists no resume state, so a resuming supervisor with no surviving PID reference
        # cannot positively confirm orphan termination. A clean diff would be ambiguous (nothing
        # happened vs. not written yet); never used to decide. Zero further mutation: worktree
        # is intentionally NOT rolled back or removed by this trial.
        return {"crashed": True, "crash_verified": True, "cut": cut, "child_pid_discarded": True,
                "forensic_changed_paths": _worktree_diff(worktree),
                "reconcile": {"outcome": "owner_unknown", "reason": "PID_TRACKING_DISCARDED_BY_DESIGN"}}
    orphan_gone = wait_gone(child, time.monotonic() + budget_seconds)
    if not orphan_gone:
        return {"crashed": True, "crash_verified": True, "cut": cut, "child_pid": child,
                "reconcile": {"outcome": "owner_unknown", "reason": "ORPHAN_UNVERIFIED_TIMEOUT"}}
    paths = _worktree_diff(worktree)
    if paths == sorted(task["files"]):
        rollback_ok = _rollback(worktree, task["base_commit"])
        return {"crashed": True, "crash_verified": True, "cut": cut, "child_pid": child, "orphan_verified_dead": True,
                "changed_paths": paths, "accepted": True, "rollback": rollback_ok, "reconcile": {"outcome": "postimage"}}
    if not paths:
        return {"crashed": True, "crash_verified": True, "cut": cut, "child_pid": child, "orphan_verified_dead": True,
                "changed_paths": paths, "accepted": False, "rollback": True, "reconcile": {"outcome": "preimage"}}
    rollback_ok = _rollback(worktree, task["base_commit"])
    return {"crashed": True, "crash_verified": True, "cut": cut, "child_pid": child, "orphan_verified_dead": True,
            "changed_paths": paths, "accepted": False, "rollback": rollback_ok, "reconcile": {"outcome": "rollback"}}


def execute(repo: Path, plan: Path, trial_id: str, g2b: str, probe: dict, results_path: Path) -> dict:
    if trial_id not in ORDER:
        raise PilotRefusal("SLICE_NOT_CATALOGUED", trial_id)
    existing = load(results_path) if results_path.exists() else {"trials": []}
    previous_ids = [row.get("trial_id") for row in existing.get("trials", []) if isinstance(row, dict)]
    if trial_id in previous_ids:
        return {"trial_id": trial_id, "duplicate_refused": True, "reason": "SLICE_ALREADY_RUN",
                "process_spawned": False}
    admission_path, admission = admission_for(plan, trial_id)
    task = admission["task"]
    budget_seconds = task["budgets"]["timeout_ms"] / 1000.0
    mechanism = MECHANISM[trial_id]
    # The third-state-orphan trial must survive this process's own exit for owner inspection
    # (zero further mutation): a `tempfile.TemporaryDirectory` context manager would `rmtree` it
    # regardless of any in-process "keep" flag. `mkdtemp` (manual, non-auto-cleaning) is used
    # uniformly instead, kept OUTSIDE the repo tree (system temp, like P5.2's harness) so a
    # preserved worktree never shows up as foreign diff in the main tree's `git status`; only the
    # non-preserved cases explicitly remove it afterward.
    worktree_root = Path(tempfile.mkdtemp(prefix=f"p5-p53-{trial_id}-"))
    worktree = worktree_root / "root"
    if command(["git", "worktree", "add", "--detach", "--", str(worktree), task["base_commit"]], cwd=repo).returncode:
        raise PilotRefusal("WORKTREE_CREATE", trial_id)
    keep_worktree = False
    try:
        if mechanism == "real-crash-after-intent":
            binary = str(resolve_claude_bin()) if task["provider"] == "claude-code" else which("codex")
            row = run_crash(repo, admission_path, g2b, worktree, binary, task, trial_id, "after_intent", budget_seconds)
        elif mechanism == "real-crash-after-observation":
            binary = str(resolve_claude_bin()) if task["provider"] == "claude-code" else which("codex")
            row = run_crash(repo, admission_path, g2b, worktree, binary, task, trial_id, "after_observation", budget_seconds)
        elif mechanism == "real-third-state-orphan":
            binary = str(resolve_claude_bin()) if task["provider"] == "claude-code" else which("codex")
            row = run_crash(repo, admission_path, g2b, worktree, binary, task, trial_id, "third_state_discard", budget_seconds)
            keep_worktree = True
        elif mechanism == "real-duplicate-refusal":
            binary = str(resolve_claude_bin()) if task["provider"] == "claude-code" else which("codex")
            row = run_normal(repo, admission_path, g2b, worktree, binary, task, trial_id)
        elif mechanism == "fake-timeout":
            fake = _make_fake_binary(FAKE_CODEX)
            try:
                row = run_normal(repo, admission_path, g2b, worktree, str(fake), task, trial_id)
                row["fake_binary"] = True
            finally:
                fake.unlink(missing_ok=True)
        elif mechanism == "fake-schema-refusal":
            fake = _make_fake_binary(FAKE_CLAUDE)
            try:
                row = run_normal(repo, admission_path, g2b, worktree, str(fake), task, trial_id)
                row["fake_binary"] = True
            finally:
                fake.unlink(missing_ok=True)
        else:
            raise PilotRefusal("MECHANISM_UNKNOWN", mechanism)
        row.update({"trial_id": trial_id, "provider": task["provider"], "mechanism": mechanism,
                   "admission_hash": admission["admission_hash"], "base_commit": task["base_commit"],
                   "duplicate_refused": False})
        return row
    finally:
        if not keep_worktree:
            command(["git", "worktree", "remove", "--force", "--", str(worktree)], cwd=repo)
            try:
                worktree_root.rmdir()
            except OSError:
                pass
        else:
            row["preserved_worktree"] = str(worktree)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slice", choices=ORDER)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--results", required=True, type=Path)
    args = parser.parse_args()
    repo, plan = root(), root() / "plans" / PLAN_ID
    try:
        result = load(args.results) if args.results.exists() else None
        if args.self_test:
            report = self_test()
            base = result or {"schema_version": "artifex-recovery-pilot-results-v1", "g2_predecessor": G2,
                              "g2b_generation_hash": g2b_hash(plan), "self_test": None, "version_probe": None,
                              "main_tree_delta": False, "trials": []}
            base["self_test"] = report
            args.results.write_text(json.dumps(base, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ok = (report["child_spawn_detection"]["all_detected"] and report["reap_window_detection"]["all_detected"]
                 and report["orphan_after_parent_kill"]["all_orphaned"])
            print("P5.3 self-test:", "OK" if ok else "FAIL")
            return 0 if ok else 1
        if args.slice is None:
            raise PilotRefusal("SLICE_REQUIRED")
        probe = preflight(repo, plan)
        g2b = g2b_hash(plan)
        row = execute(repo, plan, args.slice, g2b, probe, args.results)
        if result is None:
            raise PilotRefusal("SELF_TEST_MISSING_FIRST")
        if (result.get("schema_version") != "artifex-recovery-pilot-results-v1" or result.get("g2_predecessor") != G2
                or result.get("g2b_generation_hash") != g2b or result.get("main_tree_delta") is not False
                or not isinstance(result.get("self_test"), dict) or not isinstance(result.get("trials"), list)):
            raise PilotRefusal("RESULTS_DRIFT")
        if result.get("version_probe") is None:
            result["version_probe"] = probe
        elif result["version_probe"] != probe:
            raise PilotRefusal("RESULTS_DRIFT")
        # Duplicate-refusal rows repeat an already-used trial_id and must not consume a new ORDER
        # slot: the prefix check tracks only the REAL (non-duplicate) rows.
        previous_real = [value.get("trial_id") for value in result["trials"]
                         if isinstance(value, dict) and not value.get("duplicate_refused")]
        if tuple(previous_real) != ORDER[:len(previous_real)]:
            raise PilotRefusal("SLICE_ORDER_OR_REUSE")
        if row.get("duplicate_refused"):
            if args.slice not in previous_real:
                raise PilotRefusal("SLICE_ORDER_OR_REUSE")
        elif args.slice != ORDER[len(previous_real)]:
            raise PilotRefusal("SLICE_ORDER_OR_REUSE")
        result["trials"].append(row)
        args.results.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"P5.3 pilot: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"P5.3 pilot: OK ({args.slice})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
