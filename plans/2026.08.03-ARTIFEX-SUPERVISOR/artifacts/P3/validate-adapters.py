#!/usr/bin/env python3
"""Independent aggregate gate for the bounded P3.4 readiness evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED = {"schema_version", "provider_id", "task_id", "admission_hash", "exit_class", "reason_code",
            "readiness", "process_count", "project_delta", "schema_valid", "duration_ms", "evidence_hash"}
FORBIDDEN = {"stdout", "stderr", "prompt", "transcript", "environment", "api_key", "tools"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-dir", required=True, type=Path)
    parser.add_argument("--admission-index", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args, _ = parser.parse_known_args()
    index = json.loads(args.admission_index.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if (manifest.get("schema_version") != "artifex-adapter-manifest-v1"
            or manifest.get("providers") != ["claude-code", "codex"]
            or manifest.get("readiness") != "non-green-measured"):
        raise ValueError("adapter manifest shape")
    admissions = {row["provider"]: row for row in index.get("admissions", [])}
    if set(admissions) != {"codex", "claude-code"}:
        raise ValueError("exactly two indexed providers required")
    expected = {"codex": "CAPABILITY_UNSUPPORTED", "claude-code": "MAPPING_UNKNOWN"}
    for provider, reason in expected.items():
        value = json.loads((args.smoke_dir / f"{provider}.json").read_text(encoding="utf-8"))
        if set(value) != REQUIRED or set(value) & FORBIDDEN:
            raise ValueError(f"{provider}: schema/privacy")
        if (value["provider_id"] != provider or value["task_id"] != admissions[provider]["task_id"]
                or value["admission_hash"] != admissions[provider]["admission_hash"] or value["reason_code"] != reason
                or value["readiness"] != "non-green" or value["process_count"] != 0 or value["project_delta"] != []):
            raise ValueError(f"{provider}: admission/readiness mismatch")
    print("adapter validator: OK (two exact non-green zero-activity rows)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"adapter validator: FAIL: {exc}")
        raise SystemExit(1)
