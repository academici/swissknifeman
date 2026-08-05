#!/usr/bin/env python3
"""Independent P4.4 evidence validator; it trusts neither candidate results nor exit code alone."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


EXPECTED = {
    "indexed-admission": "allow", "grant-as-admission": "UNKNOWN_SCHEMA_VERSION",
    "cross-provider": "ADMISSION_WIDENING", "permission-widening": "PERMISSION_WIDENING",
    "child-widening": "CAPABILITY_WIDENING", "foreign-path": "ADMISSION_NOT_INDEXED",
    "secret-canary": "FORBIDDEN_CONTENT", "raw-transcript": "OBSERVATION_SCHEMA",
    "environment-widening": "ENVIRONMENT_WIDENING", "hook-green": "green",
}


def fail(message: str) -> None:
    raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(cases: Path, results: Path, hooks: Path, root: Path) -> None:
    case_value, result_value, hook_value = (json.loads(path.read_text(encoding="utf-8")) for path in (cases, results, hooks))
    rows = case_value.get("cases") if isinstance(case_value, dict) else None
    actual = {row.get("id"): row.get("expected") for row in rows if isinstance(row, dict)} if isinstance(rows, list) else {}
    if case_value.get("schema_version") != "p4-security-cases-v1" or actual != EXPECTED:
        fail("case matrix")
    if not isinstance(result_value, dict) or result_value.get("schema_version") != "p4-security-results-v1" or result_value.get("result") != "green":
        fail("result schema")
    if result_value.get("cases_sha256") != digest(cases):
        fail("case hash")
    if result_value.get("hook") != {"provider": "codex", "status": "green", "actions": 0}:
        fail("hook result")
    if result_value.get("persistence") != {"raw_content": False, "environment_values": False, "canary_sha256_only": True}:
        fail("persistence policy")
    if hook_value.get("post_repair", {}).get("status") != "green" or hook_value.get("post_repair", {}).get("actions") != []:
        fail("terminal hook evidence")
    command = [sys.executable, "-m", "unittest", "packages.artifex.tests.test_security_boundaries"]
    ran = subprocess.run(command, cwd=root, env={"PYTHONPATH": str(root / "packages/artifex/lib")}, capture_output=True, text=True)
    if ran.returncode:
        fail("security unit tests")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--cases", type=Path, required=True); parser.add_argument("--results", type=Path, required=True); parser.add_argument("--hook-results", type=Path, required=True)
    args, _unknown = parser.parse_known_args(argv)
    root = Path(__file__).resolve().parents[4]
    validate(args.cases, args.results, args.hook_results, root)
    print("security validator: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"security validator: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
