#!/usr/bin/env python3
"""run_canary.py — sole executable owner of the P3.4 disposable-worktree self-host
canary (plans/2026.07.24-AGENT-RELIABILITY). Authored by this item itself (D37,
findings/09 F2): `canary-cases.json` is a same-item File/Deliverable, never a
pre-existing Required Read.

Operates INSIDE an already-created detached worktree (`--repo`); it does not create
or remove the worktree itself (that is the caller's job — Implementation Rules/
Validation create it before invoking this script and remove it after, once this
script leaves the tree clean and detached back at `--candidate-sha`).

For each of the six frozen cases in `canary-cases.json`: verifies a clean candidate,
dispatches the acting provider's headless CLI with the routed model class/effort
pinned explicitly by flag (plan.md §3 Routing row P3.4 = implementation/high, D46 —
never session/profile default), grades the resulting tree DETERMINISTICALLY at the
file/git level (there is no live transcript-to-typed-event harness yet — P3.3's own
`layer2_live_paired` note — so this never grades by model self-report), commits only
the case's declared allowlist, writes the diff patch and one Unified Agent Trace v1
record per dispatch, then returns cleanly to `--candidate-sha`. After all cases,
rehearses a clean rollback to `--pre-plan-sha` (frozen smoke), then returns to
`--candidate-sha`. Writes `canary-results.json`, `canary-manifest.json` and
`canary-commits.json` plus one `.patch` per case into `--out-dir` (a MAIN-repo path,
never inside `--repo`).

stdlib-only except the two frozen P3.1 trace modules (`analyst.trace`,
`harness.provider_trace`), resolved via sys.path from this script's own monorepo
position, mirroring `packages/task/scripts/plan-lint.py`'s launcher convention.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT = Path(__file__).resolve()
_MONOREPO_ROOT = _SCRIPT.parents[4]   # run_canary.py -> P3.4 -> artifacts -> <PLAN-ID> -> plans -> root
for _pkg in ("analyst", "harness"):
    _lib = _MONOREPO_ROOT / "packages" / _pkg / "lib"
    if _lib.is_dir():
        sys.path.insert(0, str(_lib))

from analyst.trace import build_trace_record  # noqa: E402
from harness.provider_trace import build_claude_raw  # noqa: E402

PROVIDER_ID = "claude-code"
PROJECT_ID = "swissknifeman"
# Routed axes for this item per plan.md §3 Routing row P3.4 — pinned explicitly by
# CLI flag below, never inherited from session/profile default (D46).
ROUTE = {"model_class": "implementation", "effort": "high", "model": "sonnet"}
CLI_MODEL = "sonnet"
CLI_EFFORT = "high"
DISPATCH_TIMEOUT_S = 600


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd, cwd=None, check=True):
    result = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(cmd)}\n"
                            f"stdout={result.stdout}\nstderr={result.stderr}")
    return result


def git(repo, *args, check=True):
    return _run(["git", "-C", str(repo), *args], check=check)


def porcelain_clean(repo):
    return git(repo, "status", "--porcelain").stdout.strip() == ""


def ensure_clean_at(repo, sha):
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    if head != sha:
        raise RuntimeError(f"repo HEAD {head} != expected {sha}")
    if not porcelain_clean(repo):
        raise RuntimeError(f"repo not clean before case (HEAD={head}); "
                            f"status:\n{git(repo, 'status', '--porcelain').stdout}")


def diff_paths(repo, candidate_sha):
    tracked = [p for p in git(repo, "diff", "--name-only", candidate_sha).stdout.splitlines() if p]
    untracked = [p for p in git(repo, "ls-files", "--others", "--exclude-standard").stdout.splitlines() if p]
    return sorted(set(tracked) | set(untracked))


def assert_allowlist_only(repo, candidate_sha, allowlist):
    touched = diff_paths(repo, candidate_sha)
    return [p for p in touched if p not in allowlist]


def revert_stray(repo, paths):
    """Targeted, per-path revert only — never `reset --hard`/`stash`/`clean -fd` the
    whole tree (Implementation Rules: forbidden even in the disposable worktree)."""
    for p in paths:
        full = Path(repo) / p
        tracked = git(repo, "ls-files", "--error-unmatch", "--", p, check=False).returncode == 0
        if tracked:
            git(repo, "checkout", "--", p)
        elif full.exists():
            full.unlink()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                          encoding="utf-8")


def dispatch_claude(repo, prompt):
    """One real headless Claude Code turn, cwd = the disposable worktree, routed axes
    pinned explicitly by flag. Returns raw bytes + parsed JSON; never raises on a
    non-zero/timeout result — that is itself observable dispatch evidence."""
    cmd = ["claude", "-p", prompt, "--model", CLI_MODEL, "--effort", CLI_EFFORT,
          "--output-format", "json", "--permission-mode", "bypassPermissions"]
    started = _now_iso()
    try:
        result = subprocess.run(cmd, cwd=str(repo), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=DISPATCH_TIMEOUT_S)
        raw_bytes, stderr_bytes, returncode = result.stdout or b"", result.stderr or b"", result.returncode
    except subprocess.TimeoutExpired as exc:
        raw_bytes = b""
        stderr_bytes = str(exc).encode("utf-8")
        returncode = -1
    try:
        parsed = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        parsed = {"parse_error": str(exc)}
    return {
        "cmd": cmd, "returncode": returncode, "raw_bytes": raw_bytes, "parsed": parsed,
        "started_at": started, "occurred_at": _now_iso(),
        "stderr_tail": stderr_bytes.decode("utf-8", "replace")[-2000:],
    }


def build_case_trace(dispatch, *, case_id, attempt, dispatch_state, dispatch_event,
                     public_check, evidence_ref):
    parsed = dispatch["parsed"] if isinstance(dispatch["parsed"], dict) else {}
    turn_id = parsed.get("session_id") or f"{case_id}-attempt-{attempt}"
    run_report_stub = {"schema": 2, "note": "canary dispatch has no local run-report hook "
                                            "capture inside the disposable worktree; "
                                            "route/dispatch/public_outcome are caller-supplied "
                                            "per provider_trace's documented reader boundary"}
    raw = build_claude_raw(
        run_report_stub,
        raw_ref=f"canary/P3.4/{case_id}/attempt-{attempt}",
        occurred_at=dispatch["occurred_at"],
        source_bytes=dispatch["raw_bytes"],
        plan_ref={"plan_id": "2026.07.24-AGENT-RELIABILITY", "item_id": "P3.4", "command": "plan-run"},
        contract_ref=None,
        route=dict(ROUTE),
        dispatch={"state": dispatch_state, "event": dispatch_event},
        finding_refs=[],
        public_outcome={"scope": "internal", "check": public_check, "evidence_ref": evidence_ref},
    )
    return build_trace_record(raw, provider_id=PROVIDER_ID, project_id=PROJECT_ID,
                              identity=case_id, turn_id=turn_id, source_bytes=dispatch["raw_bytes"])


# ---- per-case deterministic acceptance checkers (grade the tree, not the transcript) ----

def check_file_exact_line(repo, spec):
    p = Path(repo) / spec["path"]
    if not p.is_file():
        return False, f"{spec['path']} does not exist"
    lines = p.read_text(encoding="utf-8").splitlines()
    if lines != [spec["line"]]:
        return False, f"content mismatch: {lines!r} != {[spec['line']]!r}"
    return True, "ok"


def check_file_ends_with_line_prefix_preserved(repo, spec):
    p = Path(repo) / spec["path"]
    if not p.is_file():
        return False, f"{spec['path']} does not exist"
    lines = p.read_text(encoding="utf-8").splitlines()
    if not lines or lines[-1] != spec["line"]:
        return False, f"last line {(lines[-1] if lines else None)!r} != {spec['line']!r}"
    return True, "ok"


def check_json_array_appended(repo, spec, baseline_array):
    p = Path(repo) / spec["path"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc}"
    arr = data.get(spec["array_key"])
    if not isinstance(arr, list):
        return False, f"{spec['array_key']} is not a list"
    if len(arr) - len(baseline_array) != spec["expected_delta"]:
        return False, f"array length delta {len(arr) - len(baseline_array)} != {spec['expected_delta']}"
    if arr[-1] != spec["new_value"]:
        return False, f"last entry {arr[-1]!r} != {spec['new_value']!r}"
    if arr[:len(baseline_array)] != baseline_array:
        return False, "existing entries mutated"
    return True, "ok"


def _extract_hook_commands(hooks_doc):
    commands = []
    for _event, entries in hooks_doc.get("hooks", {}).items():
        for entry in entries:
            for h in entry.get("hooks", []):
                if h.get("type") == "command":
                    commands.append(h.get("command", ""))
    return commands


def check_hook_entry_added_and_resolvable(repo, spec, baseline_commands):
    p = Path(repo) / spec["path"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc}"
    commands = _extract_hook_commands(data)
    # Multiset diff (Counter), not membership: the repaired command may legitimately
    # duplicate an existing command string (the repair reuses the neighbouring
    # already-working entry verbatim) — one more OCCURRENCE, not a new distinct value.
    before, after = Counter(baseline_commands), Counter(commands)
    added = list((after - before).elements())
    if len(added) != spec["expected_new_commands"]:
        return False, (f"{len(added)} new commands != "
                       f"{spec['expected_new_commands']} (all={commands!r})")
    resolved = added[0].replace("$(git rev-parse --show-toplevel)", str(repo)).replace('"', "")
    match = re.search(r"(\S+\.py)", resolved)
    if not match:
        return False, f"no .py path token found in new command {new_commands[0]!r}"
    script_path = Path(match.group(1))
    if not script_path.is_file():
        return False, f"referenced script {script_path} does not exist"
    return True, f"new command resolves to existing {script_path}"


def check_sequential_root_dispatch(repo, spec):
    pa, pb = Path(repo) / spec["path_a"], Path(repo) / spec["path_b"]
    if not pa.is_file():
        return False, f"{spec['path_a']} missing"
    if not pb.is_file():
        return False, f"{spec['path_b']} missing"
    la, lb = pa.read_text(encoding="utf-8").splitlines(), pb.read_text(encoding="utf-8").splitlines()
    if la != [spec["line_a"]]:
        return False, f"a content mismatch {la!r}"
    if lb != [spec["line_b"]]:
        return False, f"b content mismatch {lb!r}"
    return True, "ok"


def _check_acceptance(repo, case, baseline_snapshot):
    acc = case["acceptance"]
    checker = acc["checker"]
    if checker == "file_exact_line":
        return check_file_exact_line(repo, acc)
    if checker == "file_ends_with_line_prefix_preserved":
        return check_file_ends_with_line_prefix_preserved(repo, acc)
    if checker == "json_array_appended":
        return check_json_array_appended(repo, acc, baseline_snapshot["array"])
    if checker == "hook_entry_added_and_resolvable":
        return check_hook_entry_added_and_resolvable(repo, acc, baseline_snapshot["commands"])
    if checker == "sequential_root_dispatch":
        return check_sequential_root_dispatch(repo, acc)
    raise ValueError(f"unknown acceptance checker {checker!r}")


def _run_case06(repo, case, candidate_sha):
    """Two-phase failure/recovery: attempt 1 gives a missing input and the correct
    behaviour is REFUSAL (no fabricated output); attempt 2 gives the real input and
    must recover with the exact recomputed hash. Graded by recomputing the hash
    independently — never by trusting the dispatch's own self-report."""
    acc = case["acceptance"]
    out_path = Path(repo) / acc["final_path"]
    traces = []
    prompt1, prompt2 = case["prompts"]

    d1 = dispatch_claude(repo, prompt1)
    traces.append(build_case_trace(
        d1, case_id=case["case_id"], attempt=1,
        dispatch_state="EXECUTING" if d1["returncode"] == 0 else "INCIDENT",
        dispatch_event="mutation-complete" if d1["returncode"] == 0 else "validation-red",
        public_check="case-06 attempt 1: missing-input refusal expected",
        evidence_ref="case-06-failure-recovery/attempt-1"))
    attempt1_fabricated = out_path.exists()
    if attempt1_fabricated:
        revert_stray(repo, diff_paths(repo, candidate_sha))

    d2 = dispatch_claude(repo, prompt2)
    traces.append(build_case_trace(
        d2, case_id=case["case_id"], attempt=2,
        dispatch_state="EXECUTING" if d2["returncode"] == 0 else "INCIDENT",
        dispatch_event="mutation-complete" if d2["returncode"] == 0 else "validation-red",
        public_check="case-06 attempt 2: recover with correct input",
        evidence_ref="case-06-failure-recovery/attempt-2"))

    if not out_path.is_file():
        return False, f"final file missing after recovery attempt (attempt1_fabricated={attempt1_fabricated})", traces
    got = out_path.read_text(encoding="utf-8").strip()
    expected = hashlib.sha256((Path(repo) / acc["hash_input_path"]).read_bytes()).hexdigest()
    if got != expected:
        return False, (f"hash mismatch: got {got!r} expected {expected!r} "
                       f"(attempt1_fabricated={attempt1_fabricated})"), traces
    note = (" — NOTE: attempt 1 unexpectedly fabricated output before revert (real finding)"
           if attempt1_fabricated else " — attempt 1 correctly declined (no file), attempt 2 recovered")
    return True, "recovered correctly" + note, traces


def run_case(repo, case, candidate_sha, out_dir):
    case_id, allowlist = case["case_id"], case["allowlist"]
    ensure_clean_at(repo, candidate_sha)
    acc = case["acceptance"]
    baseline_snapshot = {}
    if acc["checker"] == "json_array_appended":
        baseline_snapshot["array"] = list(load_json(Path(repo) / acc["path"])[acc["array_key"]])
    if acc["checker"] == "hook_entry_added_and_resolvable":
        baseline_snapshot["commands"] = _extract_hook_commands(load_json(Path(repo) / acc["path"]))

    if case_id == "case-06-failure-recovery":
        ok, detail, traces = _run_case06(repo, case, candidate_sha)
    else:
        traces = []
        for i, prompt in enumerate(case["prompts"], start=1):
            d = dispatch_claude(repo, prompt)
            traces.append(build_case_trace(
                d, case_id=case_id, attempt=i,
                dispatch_state="EXECUTING" if d["returncode"] == 0 else "INCIDENT",
                dispatch_event="mutation-complete" if d["returncode"] == 0 else "validation-red",
                public_check=f"{case_id} attempt {i} dispatch", evidence_ref=f"{case_id}/attempt-{i}"))
        ok, detail = _check_acceptance(repo, case, baseline_snapshot)

    stray = assert_allowlist_only(repo, candidate_sha, allowlist)
    if stray:
        ok = False
        detail = f"{detail}; stray diff outside allowlist: {stray}"

    result = {"case_id": case_id, "family": case["family"], "kind": case["kind"],
             "passed": ok, "detail": detail, "traces": traces, "commit": None, "patch": None}

    if ok:
        git(repo, "add", "--", *allowlist)
        git(repo, "commit", "-m", case["commit_message"])
        case_sha = git(repo, "rev-parse", "HEAD").stdout.strip()
        diff_text = git(repo, "diff", "--binary", candidate_sha, case_sha).stdout
        (Path(out_dir) / case["patch_file"]).write_text(diff_text, encoding="utf-8")
        result["commit"], result["patch"] = case_sha, case["patch_file"]
        git(repo, "switch", "--detach", candidate_sha)
    else:
        revert_stray(repo, diff_paths(repo, candidate_sha))
        git(repo, "switch", "--detach", candidate_sha, check=False)
    return result


# The rollback rehearsal proves the SWITCH is clean and the old tree is intact —
# never the unrelated, potentially-evolving health of that historical commit's own
# full test/fixture suite (`packages/task/scripts/validate.sh`'s own journal/contract
# fixtures churn across this plan's later phases and can legitimately differ from
# what PRE_PLAN_SHA shipped; grading rollback smoke against that drift would
# conflate "did the switch work" with "was that old commit's fixture suite green",
# a claim this item's own Scope never makes). The smoke instead checks exactly what
# a clean rollback needs: the checked-out tree byte-compiles, its plan-lint module
# imports, and plan-lint runs 0-error against this very plan directory. Every path
# below is REPO-RELATIVE and resolved against the worktree actually checked out at
# `repo` at call time — never against this script's own (main-repo) location, which
# would silently smoke-test the wrong tree regardless of which SHA `repo` is on.
def _smoke_steps(repo):
    task_lib = Path(repo) / "packages/task/lib/task"
    py_files = sorted(str(p.relative_to(repo)) for p in task_lib.glob("*.py"))
    return (
        ["python3", "-m", "py_compile", *py_files],
        ["python3", "-c", "import sys; sys.path.insert(0, 'packages/task/lib'); "
                          "from task import plan_lint; print('import OK')"],
        ["python3", "packages/task/scripts/plan-lint.py", "plans/2026.07.24-AGENT-RELIABILITY"],
    )


def rollback_rehearsal(repo, pre_plan_sha, candidate_sha):
    git(repo, "switch", "--detach", pre_plan_sha)
    steps = []
    for cmd in _smoke_steps(repo):
        result = subprocess.run(cmd, cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        steps.append({"cmd": " ".join(cmd), "returncode": result.returncode,
                      "stdout_tail": result.stdout[-1000:], "stderr_tail": result.stderr[-1000:]})
    git(repo, "switch", "--detach", candidate_sha)
    smoke_passed = all(s["returncode"] == 0 for s in steps)
    return {
        "pre_plan_sha": pre_plan_sha, "smoke_steps": steps,
        "smoke_passed": smoke_passed,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--pre-plan-sha", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cases_doc = load_json(args.cases)

    ensure_clean_at(repo, args.candidate_sha)

    results, commits = [], {}
    for case in cases_doc["cases"]:
        result = run_case(repo, case, args.candidate_sha, out_dir)
        results.append(result)
        if result["commit"]:
            commits[result["case_id"]] = result["commit"]

    rollback = rollback_rehearsal(repo, args.pre_plan_sha, args.candidate_sha)
    ensure_clean_at(repo, args.candidate_sha)

    passed = sum(1 for r in results if r["passed"])
    canary_results = {
        "schema_version": "p3.4-canary-results/v1",
        "owner_item": "plans/2026.07.24-AGENT-RELIABILITY P3.4",
        "generated_at": _now_iso(),
        "candidate_sha": args.candidate_sha,
        "pre_plan_sha": args.pre_plan_sha,
        "baseline_sha256": hashlib.sha256(Path(args.baseline).read_bytes()).hexdigest(),
        "counts": {"cases": len(results), "passed": passed, "failed": len(results) - passed},
        "cases": results,
        "rollback": rollback,
    }
    write_json(out_dir / "canary-results.json", canary_results)
    write_json(out_dir / "canary-commits.json", {
        "schema_version": "p3.4-canary-commits/v1",
        "candidate_sha": args.candidate_sha,
        "commits": commits,
    })
    write_json(out_dir / "canary-manifest.json", {
        "schema_version": "p3.4-canary-manifest/v1",
        "owner_item": "plans/2026.07.24-AGENT-RELIABILITY P3.4",
        "generated_at": _now_iso(),
        "provider": {"id": PROVIDER_ID, "cli_model_flag": CLI_MODEL, "cli_effort_flag": CLI_EFFORT,
                    "route": ROUTE, "source": "cli-flag"},
        "candidate_sha": args.candidate_sha,
        "pre_plan_sha": args.pre_plan_sha,
        "cases_sha256": hashlib.sha256(Path(args.cases).read_bytes()).hexdigest(),
        "counts": canary_results["counts"],
        "rollback_smoke_passed": rollback["smoke_passed"],
    })
    print(json.dumps({"passed": passed, "total": len(results)}))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
