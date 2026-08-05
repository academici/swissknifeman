#!/usr/bin/env python3
"""Independent closed-set validation of Artifex P4.3 worktree evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value


parser = argparse.ArgumentParser()
for name in ("cases", "results", "recovery", "slice-contract"):
    parser.add_argument("--" + name, required=True)
args = parser.parse_args()

try:
    cases, results, recovery = load(args.cases), load(args.results), load(args.recovery)
    if not Path(args.slice_contract).is_file():
        raise ValueError("slice contract missing")
    expected = ["W4-001", "W4-002", "W4-003", "W4-004", "W4-005", "W4-006", "W4-007"]
    if cases.get("schema_version") != "artifex-worktree-cases-v1" or [row.get("id") for row in cases.get("cases", [])] != expected:
        raise ValueError("case identity")
    if results.get("schema_version") != "artifex-worktree-results-v1" or results.get("cases_schema") != cases["schema_version"]:
        raise ValueError("result schema")
    rows = results.get("results", [])
    if [row.get("id") for row in rows] != expected or any(set(row) != {"id", "outcome", "serialized", "residue"} for row in rows):
        raise ValueError("result identity")
    expected_outcomes = {row["id"]: row["expected"] for row in cases["cases"]}
    if any(row["outcome"] != expected_outcomes[row["id"]] or row["residue"] is not False for row in rows):
        raise ValueError("outcome or residue")
    if [row["id"] for row in rows if row["serialized"]] != ["W4-001", "W4-006"]:
        raise ValueError("serialized lane")
    if recovery.get("schema_version") != "artifex-recovery-results-v1" or len(recovery.get("results", [])) != 16:
        raise ValueError("P4.2 recovery input")
    print("worktree validator: OK (7 cases; serialized integration; zero residue)")
except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
    print("worktree validator: FAIL: " + str(exc), file=sys.stderr)
    raise SystemExit(1)
