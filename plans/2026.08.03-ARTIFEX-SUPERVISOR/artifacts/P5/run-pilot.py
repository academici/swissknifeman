#!/usr/bin/env python3
"""Thin stateless P5.2 pilot harness.

Owns only Git worktree lifecycle (create at the frozen base commit, measure
delta, roll back) around the package's D118 business-execution seam
(``bin/artifex dispatch-business-intent``). It never reimplements argv
construction, provider execution or result folding — those stay in
``packages/artifex/lib/artifex/activity.py``/``providers/*``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
G2 = "ef08406d7ca630d46e9e9e8bca0d10ea73b141d984615bded75f19d7eea13f09"
G2B = "7c1187f0a3f8addda07a27ea36cda836ffd64f91281cf56ac95a7fcb04da7a30"
ORDER = ("p5.2-slice-01-worktree-core", "p5.2-slice-02-worktree-binding", "p5.2-slice-03-worktree-evidence")
EXPECTED_VERSION = {"codex": "codex-cli 0.146.0", "claude-code": "2.1.222 (Claude Code)"}
_ENV = {"PATH": os.defpath, "LC_ALL": "C", "LANG": "C", "TZ": "UTC"}


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
    found = command(["which", binary], cwd=root()).stdout.decode("utf-8", "replace").strip()
    if not found:
        raise PilotRefusal("PROVIDER_UNAVAILABLE", binary)
    return found


def admission_for(plan: Path, trial_id: str) -> tuple[Path, dict]:
    index = load(plan / "artifacts/P5/trial-admission-index-v1.json")
    rows = [row for row in index.get("admissions", []) if isinstance(row, dict) and row.get("trial_id") == trial_id]
    if len(rows) != 1:
        raise PilotRefusal("ADMISSION_IDENTITY", trial_id)
    path = plan / rows[0]["path"]
    admission = load(path)
    if (digest(path) != rows[0].get("sha256")
            or admission.get("usage") != {"used_slices": 0, "max_slices": 1, "reusable": False}
            or admission.get("replay", {}).get("events") != [] or admission.get("task", {}).get("parent_item_id") != "P5.2"):
        raise PilotRefusal("ADMISSION_USAGE_OR_HASH", trial_id)
    return path, admission


def preflight(repo: Path, plan: Path) -> None:
    """Whole-batch precondition: rerun the P5.5 validator, then require every
    P5.2 provider's LIVE installed version to equal its frozen R2 pin. A single
    admission is never spent while a later slice in the same batch cannot run."""
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
    allowed = {
        f"plans/{PLAN_ID}/artifacts/P5/repository-pilot-results-v1.json",
        f"plans/{PLAN_ID}/findings/P5-repository-pilot.md",
    }
    dirty = command(["git", "status", "--porcelain=v1"], cwd=repo).stdout.splitlines()
    if any(len(row) < 4 or row[3:].decode("utf-8", "strict") not in allowed for row in dirty):
        raise PilotRefusal("MAIN_TREE_DIRTY")
    drift = []
    for provider, expected in EXPECTED_VERSION.items():
        binary = which("codex" if provider == "codex" else "claude")
        observed = subprocess.run([binary, "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  check=False, env={"PATH": os.defpath}).stdout.decode("utf-8", "replace").strip()
        if observed != expected:
            drift.append(f"{provider}: expected {expected!r}, installed {observed!r}")
    if drift:
        raise PilotRefusal("PROVIDER_VERSION_DRIFT", "; ".join(drift))


def execute(repo: Path, plan: Path, trial_id: str) -> dict:
    if trial_id not in ORDER:
        raise PilotRefusal("SLICE_NOT_CATALOGUED", trial_id)
    admission_path, admission = admission_for(plan, trial_id)
    task = admission["task"]
    binary = which("codex" if task["provider"] == "codex" else "claude")
    with tempfile.TemporaryDirectory(prefix="p5-p52-") as temporary:
        worktree = Path(temporary) / "root"
        if command(["git", "worktree", "add", "--detach", "--", str(worktree), task["base_commit"]], cwd=repo).returncode:
            raise PilotRefusal("WORKTREE_CREATE", trial_id)
        try:
            seam = command([str(repo / "packages/artifex/bin/artifex"), "--repo-root", str(repo),
                            "--plan-dir", f"plans/{PLAN_ID}", "--runs-root", str(Path(temporary) / "runs"),
                            "dispatch-business-intent", "--admission", str(admission_path.relative_to(repo)),
                            "--g2-predecessor", G2, "--g2b-successor", G2B, "--cwd", str(worktree), "--binary", binary],
                           cwd=repo)
            try:
                payload = json.loads(seam.stdout.decode("utf-8"))
            except json.JSONDecodeError:
                raise PilotRefusal("SEAM_OUTPUT_INVALID", seam.stdout.decode("utf-8", "replace"))
            changed = command(["git", "status", "--porcelain=v1", "-z"], cwd=worktree).stdout.split(b"\0")
            paths = sorted(row[3:].decode("utf-8", "strict") for row in changed if row)
            accepted = seam.returncode == 0 and payload.get("status") == "success" and paths == sorted(task["files"])
            rollback_ok = (command(["git", "reset", "--hard", task["base_commit"]], cwd=worktree).returncode == 0
                          and not command(["git", "status", "--porcelain=v1"], cwd=worktree).stdout)
            return {"trial_id": trial_id, "provider": task["provider"], "admission_hash": payload.get("admission_hash"),
                    "dispatch_business": {"intent_written": bool(payload.get("intent_written", False)), "usage": 0},
                    "observation": {"kind": payload.get("status"), "reason_code": payload.get("reason_code"),
                                    "process_count": payload.get("process_count", 0)},
                    "changed_paths": paths, "accepted": accepted, "rollback": rollback_ok,
                    "base_commit": task["base_commit"], "fresh_process": payload.get("process_count") == 1}
        finally:
            command(["git", "worktree", "remove", "--force", "--", str(worktree)], cwd=repo)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slice", required=True, choices=ORDER)
    parser.add_argument("--results", required=True, type=Path)
    args = parser.parse_args()
    repo, plan = root(), root() / "plans" / PLAN_ID
    try:
        preflight(repo, plan)
        row = execute(repo, plan, args.slice)
        if args.results.exists():
            result = load(args.results)
            if (result.get("schema_version") != "artifex-repository-pilot-results-v1" or result.get("g2_predecessor") != G2
                    or result.get("g2b_generation_hash") != G2B or result.get("main_tree_delta") is not False
                    or not isinstance(result.get("slices"), list)):
                raise PilotRefusal("RESULTS_DRIFT")
        else:
            result = {"schema_version": "artifex-repository-pilot-results-v1", "g2_predecessor": G2,
                      "g2b_generation_hash": G2B, "slices": [], "main_tree_delta": False}
        previous = [value.get("trial_id") for value in result["slices"] if isinstance(value, dict)]
        if tuple(previous) != ORDER[:len(previous)] or args.slice != ORDER[len(previous)]:
            raise PilotRefusal("SLICE_ORDER_OR_REUSE")
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
