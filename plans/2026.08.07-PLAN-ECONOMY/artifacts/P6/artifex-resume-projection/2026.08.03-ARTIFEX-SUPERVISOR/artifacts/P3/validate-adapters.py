#!/usr/bin/env python3
"""Strict immutable-P2 and current-P3 generation validator."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value


def git_blob(root: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=root, capture_output=True, check=False)
    if result.returncode:
        raise ValueError("missing historical anchor/blob")
    return result.stdout


CURRENT_FILES = (
    "artifacts/supervisor/artifex/activity.py", "artifacts/supervisor/artifex/cli.py",
    "artifacts/supervisor/artifex/worker.py", "artifacts/supervisor/artifex/scheduler.py",
    "artifacts/supervisor/artifex/providers/codex.py", "artifacts/supervisor/artifex/providers/claude_code.py",
    "artifacts/supervisor/tests/test_cli.py", "artifacts/supervisor/tests/test_provider_activity.py",
    "artifacts/supervisor/tests/test_adapter_evidence.py", "artifacts/P3/probe-adapters.py",
    "artifacts/P3/validate-adapters.py", "artifacts/P3/provider-parity-v1.json",
    "artifacts/P3/provider-smoke/codex.json", "artifacts/P3/provider-smoke/claude-code.json",
)


def expected_manifest(plan: Path) -> dict:
    prototype = plan / "artifacts/P2/prototype-manifest-v1.json"
    historical = load(prototype)
    return {"schema_version": "artifex-adapter-manifest-v1", "manifest_version": "1.0.0",
            "base_prototype": {"path": "artifacts/P2/prototype-manifest-v1.json", "sha256": digest(prototype.read_bytes()),
                               "git_commit": "6c2c2ef3", "files": historical["files"]},
            "current_files": [{"path": path, "sha256": digest((plan / path).read_bytes())} for path in CURRENT_FILES],
            "readiness": "observed-current-tree"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    for name in ("root", "manifest", "prototype", "contracts", "admission-index", "grant-index", "tasks", "parity", "smoke-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve(strict=True); plan = root.parents[1]
    if args.write:
        args.manifest.write_text(json.dumps(expected_manifest(plan), sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print("adapter manifest: written")
        return 0
    manifest = load(args.manifest)
    if set(manifest) != {"schema_version", "manifest_version", "base_prototype", "current_files", "readiness"} or manifest.get("schema_version") != "artifex-adapter-manifest-v1":
        raise ValueError("manifest shape")
    base = manifest["base_prototype"]
    if set(base) != {"path", "sha256", "git_commit", "files"} or base["git_commit"] != "6c2c2ef3":
        raise ValueError("baseline shape")
    prototype = load(args.prototype)
    if digest(args.prototype.read_bytes()) != base["sha256"] or prototype.get("files") != base["files"]:
        raise ValueError("baseline manifest mismatch")
    repo = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=plan, text=True, capture_output=True, check=True).stdout.strip())
    prefix = plan.relative_to(repo).as_posix() + "/artifacts/supervisor/"
    for row in base["files"]:
        if set(row) != {"path", "sha256"} or digest(git_blob(repo, base["git_commit"], prefix + row["path"])) != row["sha256"]:
            raise ValueError("historical file mismatch")
    current = manifest["current_files"]
    if not isinstance(current, list) or not current or len({row.get("path") for row in current if isinstance(row, dict)}) != len(current):
        raise ValueError("current file rows")
    for row in current:
        if set(row) != {"path", "sha256"} or "/../" in "/" + row["path"] or digest((plan / row["path"]).resolve(strict=True).read_bytes()) != row["sha256"]:
            raise ValueError("current file mismatch")
    index = load(args.admission_index); admissions = {row["provider"]: row for row in index.get("admissions", [])}
    if set(admissions) != {"codex", "claude-code"}:
        raise ValueError("admission index")
    required = {"schema_version", "provider_id", "task_id", "admission_hash", "evidence_class", "provider_version", "exit_class", "reason_code", "readiness", "process_count", "project_delta", "schema_valid", "duration_ms", "evidence_hash"}
    for provider, row in admissions.items():
        evidence = load(args.smoke_dir / f"{provider}.json")
        if set(evidence) != required or evidence["evidence_class"] != "real" or evidence["provider_id"] != provider or evidence["task_id"] != row["task_id"] or evidence["admission_hash"] != row["admission_hash"] or evidence["project_delta"] != [] or not isinstance(evidence["process_count"], int):
            raise ValueError("readiness row")
    for path in (args.contracts, args.grant_index, args.tasks, args.parity):
        load(path)
    print("adapter validator: OK (immutable P2 and current P3 generations)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"adapter validator: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
