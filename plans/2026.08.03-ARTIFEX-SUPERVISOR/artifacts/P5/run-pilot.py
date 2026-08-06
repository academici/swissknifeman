#!/usr/bin/env python3
"""Thin stateless P5.2 pilot harness.

Owns only Git worktree lifecycle (create at the frozen base commit, measure
delta, roll back) around the package's D118 business-execution seam
(``bin/artifex dispatch-business-intent``). It never reimplements argv
construction, provider execution or result folding — those stay in
``packages/artifex/lib/artifex/activity.py``/``providers/*``.

D119/D120 discipline (owner decision, 2026-08-06):
  * G2B is P5.5's output, never this item's. The generation/assurance hash is
    re-derived from the live, re-frozen manifests on every invocation instead
    of a hardcoded literal, so it can never silently drift again.
  * The Claude Code binary is resolved *only* through the explicit
    ``SKM_CLAUDE_BIN`` override (the frozen ``2.1.222`` pin) — never through
    PATH. The live ``--version`` re-probe happens once, immediately before the
    first dispatch of the whole three-slice batch (not per slice); it is
    recorded into the results file and reused, never re-derived, by the later
    slice invocations of the same batch.

D121/D122 re-run (2026-08-06): repointed at the three replacement identities
and the v2 admission index P5.1 minted under D122; ``repository-pilot-
results-v1.json`` stays untouched, read-only historical evidence — this
harness now writes only ``repository-pilot-results-v2.json``.
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
ORDER = ("p5.2r-slice-01-worktree-core", "p5.2r-slice-02-worktree-binding", "p5.2r-slice-03-worktree-evidence")
ADMISSION_INDEX = "artifacts/P5/trial-admission-index-v2-p5.2-retry.json"
EXPECTED_VERSION = {"codex": "codex-cli 0.146.0", "claude-code": "2.1.222 (Claude Code)"}
# D119: the only bytes this item may never move are packages/artifex/** and the
# two G2B manifests P5.5 owns. Unrelated pre-existing repository drift outside
# that surface is not this item's authority to police or refuse on.
GUARDED_PATHS = (
    "packages/artifex",
    f"plans/{PLAN_ID}/artifacts/P5/business-successor-generation-v1.json",
    f"plans/{PLAN_ID}/artifacts/P5/business-successor-assurance-v1.json",
)
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
    """Locate a provider CLI on the real ambient PATH.

    Deliberately not routed through ``command()``/``_ENV``: this host's codex
    install lives under a user PATH entry outside the reproducible
    ``os.defpath`` (``/bin:/usr/bin``) used for the actual dispatch/git
    subprocesses. Only binary *discovery* inherits the ambient PATH; the
    frozen version literal is still independently re-probed (never assumed),
    and the resolved absolute path is what actually gets executed.
    """
    found = subprocess.run(["which", binary], cwd=str(root()), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           shell=False, check=False, env={"PATH": os.environ.get("PATH", os.defpath)}
                           ).stdout.decode("utf-8", "replace").strip()
    if not found:
        raise PilotRefusal("PROVIDER_UNAVAILABLE", binary)
    return found


def resolve_claude_bin() -> Path:
    """D120: the Claude binary is the explicit ``SKM_CLAUDE_BIN`` override only.

    Never falls back to PATH (currently ``2.1.223``, forbidden). Refuses before
    intent if the override is absent, relative, missing or not executable.
    """
    value = os.environ.get("SKM_CLAUDE_BIN")
    if not value:
        raise PilotRefusal("SKM_CLAUDE_BIN_UNSET")
    path = Path(value)
    if not path.is_absolute():
        raise PilotRefusal("SKM_CLAUDE_BIN_NOT_ABSOLUTE", value)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise PilotRefusal("SKM_CLAUDE_BIN_NOT_EXECUTABLE", value)
    return path


def probe_version(binary: str | Path) -> str:
    completed = subprocess.run([str(binary), "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               check=False, env={"PATH": os.defpath})
    return completed.stdout.decode("utf-8", "replace").strip()


def g2b_hash(plan: Path) -> str:
    """D119: G2B is re-derived from the live, P5.5-owned manifests at every call
    instead of a hardcoded literal, so a P5.5 re-freeze can never silently drift
    this pilot's pin again."""
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
            or admission.get("replay", {}).get("events") != [] or admission.get("task", {}).get("parent_item_id") != "P5.2"
            or admission.get("grant", {}).get("owner_decision") != "D122"):
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


def _existing_probe(results: Path) -> dict | None:
    """Only trust a recorded probe once at least one slice already ran under it."""
    if not results.exists():
        return None
    value = load(results)
    slices, probe = value.get("slices"), value.get("version_probe")
    if isinstance(slices, list) and slices and isinstance(probe, dict):
        return probe
    return None


def preflight(repo: Path, plan: Path, results: Path) -> dict:
    """Whole-batch precondition: rerun the P5.5 validator, guard the two D119
    surfaces, and — only immediately before the FIRST dispatch of the whole
    three-slice batch, never per slice — require every provider's LIVE
    installed version to equal its frozen pin (D120: Claude via
    ``SKM_CLAUDE_BIN`` only, codex via PATH ``which``). A single admission is
    never spent while a later slice in the same batch cannot run."""
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
    existing = _existing_probe(results)
    if existing is not None:
        return existing
    claude_bin = resolve_claude_bin()
    observed_claude = probe_version(claude_bin)
    if observed_claude != EXPECTED_VERSION["claude-code"]:
        raise PilotRefusal("PROVIDER_VERSION_DRIFT",
                           f"claude-code: expected {EXPECTED_VERSION['claude-code']!r}, observed {observed_claude!r} ({claude_bin})")
    codex_bin = which("codex")
    observed_codex = probe_version(codex_bin)
    if observed_codex != EXPECTED_VERSION["codex"]:
        raise PilotRefusal("PROVIDER_VERSION_DRIFT",
                           f"codex: expected {EXPECTED_VERSION['codex']!r}, observed {observed_codex!r} ({codex_bin})")
    return {"claude-code": {"binary": str(claude_bin), "version": observed_claude},
            "codex": {"binary": codex_bin, "version": observed_codex}}


def execute(repo: Path, plan: Path, trial_id: str, g2b: str) -> dict:
    if trial_id not in ORDER:
        raise PilotRefusal("SLICE_NOT_CATALOGUED", trial_id)
    admission_path, admission = admission_for(plan, trial_id)
    task = admission["task"]
    binary = str(resolve_claude_bin()) if task["provider"] == "claude-code" else which("codex")
    with tempfile.TemporaryDirectory(prefix="p5-p52-") as temporary:
        worktree = Path(temporary) / "root"
        if command(["git", "worktree", "add", "--detach", "--", str(worktree), task["base_commit"]], cwd=repo).returncode:
            raise PilotRefusal("WORKTREE_CREATE", trial_id)
        try:
            # `--runs-root` must resolve *inside* `--repo-root`: cli.py's generic
            # `_roots()` path-safety gate (`_inside`) runs for every subcommand,
            # including `dispatch-business-intent`, even though that handler's own
            # `_runs` parameter is unused. An absolute temp path here would be
            # rejected as PATH_EXTERNAL (pathlib's `/` discards the left operand
            # when the right one is absolute). This literal is never created —
            # `_roots()` only materializes `runs` for the `start` subcommand — so a
            # notional, never-touched, repo-relative path is exactly what's needed.
            runs_root = f"artifacts/P5/.p5.2-pilot-noop-runs/{trial_id}"
            seam = command([str(repo / "packages/artifex/bin/artifex"), "--repo-root", str(repo),
                            "--plan-dir", f"plans/{PLAN_ID}", "--runs-root", runs_root,
                            "dispatch-business-intent", "--admission", str(admission_path.relative_to(repo)),
                            "--g2-predecessor", G2, "--g2b-successor", g2b, "--cwd", str(worktree), "--binary", binary],
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
        probe = preflight(repo, plan, args.results)
        g2b = g2b_hash(plan)
        row = execute(repo, plan, args.slice, g2b)
        if args.results.exists():
            result = load(args.results)
            if (result.get("schema_version") != "artifex-repository-pilot-results-v1" or result.get("g2_predecessor") != G2
                    or result.get("g2b_generation_hash") != g2b or result.get("main_tree_delta") is not False
                    or not isinstance(result.get("slices"), list) or result.get("version_probe") != probe):
                raise PilotRefusal("RESULTS_DRIFT")
        else:
            result = {"schema_version": "artifex-repository-pilot-results-v1", "g2_predecessor": G2,
                      "g2b_generation_hash": g2b, "slices": [], "main_tree_delta": False, "version_probe": probe}
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
