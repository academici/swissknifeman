#!/usr/bin/env python3
"""Write the two minimized P3.4 readiness rows without launching a provider activity."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--providers", required=True)
    parser.add_argument("--admission-index", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-wall-seconds", required=True, type=int)
    args = parser.parse_args()
    if args.providers != "codex,claude-code" or args.max_wall_seconds < 1:
        raise SystemExit("probe-adapters: refusal: exact provider set and positive wall cap required")
    index = json.loads(args.admission_index.read_text(encoding="utf-8"))
    rows = index.get("admissions") if isinstance(index, dict) else None
    if not isinstance(rows, list) or len(rows) != 2:
        raise SystemExit("probe-adapters: refusal: exact admission index required")
    by_provider = {row.get("provider"): row for row in rows if isinstance(row, dict)}
    if set(by_provider) != {"codex", "claude-code"}:
        raise SystemExit("probe-adapters: refusal: admission provider mismatch")
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    outcomes = {
        "codex": ("capability_unsupported", "CAPABILITY_UNSUPPORTED"),
        "claude-code": ("provider_failure", "MAPPING_UNKNOWN"),
    }
    for provider, (exit_class, reason) in outcomes.items():
        admission = by_provider[provider]
        value = {"schema_version": "p3-readiness-row-v1", "provider_id": provider,
                 "task_id": admission["task_id"], "admission_hash": admission["admission_hash"],
                 "exit_class": exit_class, "reason_code": reason, "readiness": "non-green",
                 "process_count": 0, "project_delta": [], "schema_valid": False,
                 "duration_ms": 0, "evidence_hash": digest((provider + reason).encode())}
        (args.output_dir / f"{provider}.json").write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("probe-adapters: OK (2 non-green rows; provider activity process_count=0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
