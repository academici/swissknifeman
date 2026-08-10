#!/usr/bin/env python3
"""Independent, closed-set validator for P4 no-rerun recovery evidence."""
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
for name in ("matrix", "cases", "results", "run-contract", "dispatch-contract", "grant-index", "admission-index"):
    parser.add_argument("--" + name, required=True)
args = parser.parse_args()

try:
    matrix, cases, results = load(args.matrix), load(args.cases), load(args.results)
    for path in (args.grant_index, args.admission_index):
        load(path)
    for path in (args.run_contract, args.dispatch_contract):
        if not Path(path).is_file():
            raise ValueError("contract missing")
    rows, result_rows = matrix["rows"], results["results"]
    if matrix.get("schema_version") != "artifex-fault-matrix-v1" or cases.get("schema_version") != "artifex-fault-cases-v1":
        raise ValueError("fault evidence schema")
    if results.get("schema_version") != "artifex-recovery-results-v1" or results.get("matrix_schema") != matrix["schema_version"]:
        raise ValueError("recovery schema")
    expected = [(row["id"], row["cut_id"]) for row in rows]
    actual = [(row.get("id"), row.get("cut_id")) for row in result_rows]
    if actual != expected or len(result_rows) != 16:
        raise ValueError("row identity")
    required = {"id", "cut_id", "fresh_process", "external_call_count", "observed", "decision", "reason", "retry", "unknown_rerun"}
    accepted = {("preimage", "ROLLED_BACK", "exact_no_effect", True),
                ("postimage", "ACCEPTED", "validate_without_rerun", False),
                ("partial", "ROLLED_BACK", "whole_slice_rollback", True),
                ("third", "INCIDENT", "BACKUP_MISSING", False),
                ("third", "INCIDENT", "ORPHAN_IDENTITY_AMBIGUOUS", False)}
    for row in result_rows:
        if set(row) != required or row["fresh_process"] is not True or row["unknown_rerun"] is not False:
            raise ValueError("fresh process/no-rerun")
        if row["external_call_count"] not in (0, 1):
            raise ValueError("external call count")
        if (row["observed"], row["decision"], row["reason"], row["retry"]) not in accepted:
            raise ValueError("recovery decision")
    if {row["observed"] for row in result_rows} != {"preimage", "postimage", "partial", "third"}:
        raise ValueError("decision coverage")
    print("recovery validator: OK (16 fresh-process cuts; call-count ≤1; no unknown rerun)")
except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
    print("recovery validator: FAIL: " + str(exc), file=sys.stderr)
    raise SystemExit(1)
