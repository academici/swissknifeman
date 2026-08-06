#!/usr/bin/env python3
"""D116 one-shot P5.2 bridge; durable evidence is minimized JSON only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
G2 = "ef08406d7ca630d46e9e9e8bca0d10ea73b141d984615bded75f19d7eea13f09"
G2B = "7c1187f0a3f8addda07a27ea36cda836ffd64f91281cf56ac95a7fcb04da7a30"
ORDER = ("p5.2-slice-01-worktree-core", "p5.2-slice-02-worktree-binding", "p5.2-slice-03-worktree-evidence")


def fail(reason: str) -> None:
    raise ValueError(reason)


def root() -> Path:
    return Path(__file__).resolve().parents[4]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("JSON_OBJECT_REQUIRED")
    return value


def command(argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          shell=False, check=False, env={"PATH": os.defpath, "LC_ALL": "C", "LANG": "C", "TZ": "UTC"})


def admission_for(plan: Path, trial_id: str) -> tuple[Path, dict]:
    index = load(plan / "artifacts/P5/trial-admission-index-v1.json")
    rows = [row for row in index.get("admissions", []) if isinstance(row, dict) and row.get("trial_id") == trial_id]
    if len(rows) != 1:
        fail("ADMISSION_IDENTITY")
    path = plan / rows[0]["path"]
    admission = load(path)
    if (digest(path) != rows[0].get("sha256") or admission.get("usage") != {"used_slices": 0, "max_slices": 1, "reusable": False}
            or admission.get("replay", {}).get("events") != [] or admission.get("task", {}).get("parent_item_id") != "P5.2"):
        fail("ADMISSION_USAGE_OR_HASH")
    return path, admission


def preflight(repo: Path, plan: Path) -> None:
    validator = plan / "artifacts/P5/validate-business-successor.py"
    args = [sys.executable, str(validator), "--contract", str(plan / "root/contracts/business-dispatch-admission-v1.md"),
            "--cases", str(plan / "artifacts/P5/business-dispatch-successor-cases-v1.json"),
            "--provider-manifest", str(plan / "artifacts/P5/provider-business-projection-v1.json"),
            "--provider-cases", str(plan / "artifacts/P5/provider-business-projection-cases-v1.json"),
            "--generation", str(plan / "artifacts/P5/business-successor-generation-v1.json"),
            "--assurance", str(plan / "artifacts/P5/business-successor-assurance-v1.json"),
            "--g2", str(plan / "artifacts/P4/assurance-manifest-v1.json"),
            "--admission-index", str(plan / "artifacts/P5/trial-admission-index-v1.json"), "--package", "packages/artifex"]
    if command(args, cwd=repo).returncode != 0:
        fail("G2B_PRECONDITION")
    allowed = {
        f"plans/{PLAN_ID}/artifacts/P5/run-pilot.py",
        f"plans/{PLAN_ID}/artifacts/P5/repository-pilot-results-v1.json",
        f"plans/{PLAN_ID}/artifacts/P5/validate-repository-pilot.py",
        f"plans/{PLAN_ID}/findings/P5-repository-pilot.md",
    }
    dirty = command(["git", "status", "--porcelain=v1"], cwd=repo).stdout.splitlines()
    if any(len(row) < 4 or row[3:].decode("utf-8", "strict") not in allowed for row in dirty):
        fail("MAIN_TREE_DIRTY")


def _prompt(files: list[str]) -> str:
    return ("Work only in these admission-declared files: " + ", ".join(files)
            + ". Implement the bounded repository slice, modify no other path, create no commit, "
              "then return only a JSON object satisfying the supplied schema.")


def execute(repo: Path, plan: Path, trial_id: str) -> dict:
    if trial_id not in ORDER:
        fail("SLICE_NOT_CATALOGUED")
    preflight(repo, plan)
    admission_path, admission = admission_for(plan, trial_id)
    task, grant = admission["task"], admission["grant"]
    provider = task["provider"]
    expected_version = {"codex": "codex-cli 0.146.0", "claude-code": "2.1.222 (Claude Code)"}[provider]
    binary = shutil.which("codex" if provider == "codex" else "claude")
    if not binary:
        fail("PROVIDER_UNAVAILABLE")
    version = subprocess.run([binary, "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             check=False, env={"PATH": os.defpath}).stdout.decode("utf-8", "replace").strip()
    if version != expected_version:
        fail("PROVIDER_VERSION_DRIFT")
    admission_check = command([str(repo / "packages/artifex/bin/artifex"), "--repo-root", str(repo), "--plan-dir", f"plans/{PLAN_ID}",
                               "--runs-root", ".p52-preflight", "dispatch-business", "--admission", str(admission_path.relative_to(repo)),
                               "--g2-predecessor", G2, "--g2b-successor", G2B], cwd=repo)
    if admission_check.returncode != 0 or b'"intent_written":false' not in admission_check.stdout:
        fail("DISPATCH_BUSINESS_REFUSED")
    sys.path.insert(0, str(repo / "packages/artifex/lib"))
    from artifex import business_dispatch, security, worker
    from artifex.providers import claude_code, codex
    with tempfile.TemporaryDirectory(prefix="p5-p52-") as temporary:
        temporary_root = Path(temporary)
        worktree = temporary_root / "root"
        if command(["git", "worktree", "add", "--detach", "--", str(worktree), task["base_commit"]], cwd=repo).returncode:
            fail("WORKTREE_CREATE")
        try:
            current = security.indexed_business_admission(plan, admission_path, g2_digest=G2, g2b_digest=G2B)
            request = business_dispatch.request(current, provider_version=version, cwd=worktree)
            schema = plan / "artifacts/P5/business-worker-output-schema-v1.json"
            if provider == "codex":
                argv = codex.build_business_argv(request, schema_path=schema, cwd=worktree, binary=binary)
                stdin = _prompt(task["files"]).encode("utf-8")
                fold = lambda rows, code: codex.fold_records(rows, request, exit_code=code)
            else:
                mcp = temporary_root / "mcp.json"; mcp.write_text('{"mcpServers":{}}', encoding="utf-8")
                argv = claude_code.build_business_argv(request, schema_path=schema, cwd=worktree, mcp_config_path=mcp, binary=binary)
                argv[-1] = _prompt(task["files"])
                stdin = b""
                fold = lambda rows, code: claude_code.fold_business_records(rows, request, exit_code=code)
            observation = security.observation(worker.run(argv, cwd=worktree,
                env=security.environment({"PATH": os.defpath, "LC_ALL": "C", "LANG": "C", "TZ": "UTC"}), stdin=stdin,
                timeout_ms=task["budgets"]["timeout_ms"], max_output_bytes=task["budgets"]["max_output_bytes"],
                max_event_count=task["budgets"]["max_event_count"], normalizer=fold))
            changed = command(["git", "status", "--porcelain=v1", "-z"], cwd=worktree).stdout.split(b"\0")
            paths = sorted(row[3:].decode("utf-8", "strict") for row in changed if row)
            accepted = observation.get("kind") == "success" and paths == sorted(task["files"])
            rollback = command(["git", "reset", "--hard", task["base_commit"]], cwd=worktree).returncode == 0 and not command(["git", "status", "--porcelain=v1"], cwd=worktree).stdout
            return {"trial_id": trial_id, "provider": provider, "admission_hash": current["admission_hash"],
                    "dispatch_business": {"intent_written": False, "usage": 0}, "observation": observation,
                    "changed_paths": paths, "accepted": accepted, "rollback": rollback,
                    "base_commit": task["base_commit"], "fresh_process": observation.get("process_count") == 1}
        finally:
            command(["git", "worktree", "remove", "--force", "--", str(worktree)], cwd=repo)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slice", required=True, choices=ORDER)
    parser.add_argument("--results", required=True, type=Path)
    args = parser.parse_args()
    repo, plan = root(), root() / "plans" / PLAN_ID
    try:
        row = execute(repo, plan, args.slice)
        if args.results.exists():
            result = load(args.results)
            if (result.get("schema_version") != "artifex-repository-pilot-results-v1" or result.get("g2_predecessor") != G2
                    or result.get("g2b_generation_hash") != G2B or result.get("main_tree_delta") is not False
                    or not isinstance(result.get("slices"), list)):
                fail("RESULTS_DRIFT")
        else:
            result = {"schema_version": "artifex-repository-pilot-results-v1", "g2_predecessor": G2,
                      "g2b_generation_hash": G2B, "slices": [], "main_tree_delta": False}
        previous = [value.get("trial_id") for value in result["slices"] if isinstance(value, dict)]
        if tuple(previous) != ORDER[:len(previous)] or args.slice != ORDER[len(previous)]:
            fail("SLICE_ORDER_OR_REUSE")
        result["slices"].append(row)
        args.results.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"P5.2 pilot: FAIL: {exc}", file=sys.stderr)
        return 1
    if not row["accepted"] or not row["rollback"]:
        print("P5.2 pilot: FAIL: non-terminal slice", file=sys.stderr)
        return 1
    print("P5.2 pilot: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
