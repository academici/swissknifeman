#!/usr/bin/env python3
"""Probe indexed admissions through the live P3.5 activity entrypoint."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def inside(root: Path, value: Path) -> Path:
    resolved = value.resolve(strict=True)
    resolved.relative_to(root)
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--providers", required=True)
    parser.add_argument("--admission-index", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-wall-seconds", required=True, type=int)
    args = parser.parse_args(argv)
    root = args.project_root.resolve(strict=True)
    if not root.is_dir() or args.providers != "codex,claude-code" or args.max_wall_seconds < 1:
        raise ValueError("exact project root, provider set and positive wall cap required")
    index_path, output = inside(root, args.admission_index), inside(root, args.output_dir.parent) / args.output_dir.name
    output.mkdir(mode=0o700, exist_ok=True)
    plan = root / "plans/2026.08.03-ARTIFEX-SUPERVISOR"
    sys.path.insert(0, str(plan / "artifacts/supervisor"))
    from artifex import activity, dispatch  # imported only after explicit-root validation
    index = json.loads(index_path.read_text(encoding="utf-8"))
    rows = index.get("admissions") if isinstance(index, dict) else None
    if not isinstance(rows, list) or {row.get("provider") for row in rows if isinstance(row, dict)} != {"codex", "claude-code"}:
        raise ValueError("exact admission index required")
    matrix = json.loads((plan / "artifacts/P0/provider-matrix-v1.json").read_text(encoding="utf-8"))
    versions = {row["provider"]: row["version"] for row in matrix["providers"]}
    for row in sorted(rows, key=lambda value: value["provider"]):
        admission_path = inside(plan, plan / row["path"])
        admission = dispatch.load_indexed_admission(plan, admission_path)
        observation = activity.ProviderActivityPort(plan, admission)({"input_hashes": {"admission": admission["admission_hash"]}})
        reason = observation.get("reason_code", "PROVIDER_PROTOCOL_UNKNOWN")
        exit_class = "capability_unsupported" if reason == "CAPABILITY_UNSUPPORTED" else "provider_failure"
        value = {"schema_version": "p3-readiness-row-v1", "provider_id": row["provider"],
                 "task_id": row["task_id"], "admission_hash": admission["admission_hash"],
                 "evidence_class": "real", "provider_version": versions[row["provider"]],
                 "exit_class": exit_class, "reason_code": reason, "readiness": "green" if observation.get("kind") == "success" else "non-green",
                 "process_count": observation.get("process_count"), "project_delta": [], "schema_valid": False,
                 "duration_ms": observation.get("duration_ms", 0), "evidence_hash": sha(json.dumps(observation, sort_keys=True).encode())}
        (output / f"{row['provider']}.json").write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("probe-adapters: OK (2 real indexed activity observations)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"probe-adapters: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
