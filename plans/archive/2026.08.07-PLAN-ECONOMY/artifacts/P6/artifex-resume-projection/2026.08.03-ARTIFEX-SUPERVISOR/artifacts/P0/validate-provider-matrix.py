#!/usr/bin/env python3
"""Independent structural and retention validator for P0.3 observations."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys


PROVIDERS = ("codex", "claude-code")
STATES = {"supported", "degraded", "unsupported", "unknown"}
OUTCOMES = {"exited", "nonzero", "timeout", "unavailable"}
FORBIDDEN = re.compile(r"prompt|thinking|api[_-]?key|authorization|cookie", re.I)


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: {error}") from error


def check_record(record: object, expected: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return [f"{expected}: record is not an object"]
    if record.get("schema_version") != "provider-probe-v1" or record.get("provider") != expected:
        errors.append(f"{expected}: identity mismatch")
    if record.get("availability") not in {"available", "unavailable"}:
        errors.append(f"{expected}: bad availability")
    capabilities = record.get("capabilities")
    if not isinstance(capabilities, dict) or set(capabilities) != {"structured_output", "machine_events", "permission_boundary", "ephemeral_session", "child_agent_control"}:
        errors.append(f"{expected}: closed capability shape missing")
    elif not all(value in STATES for value in capabilities.values()):
        errors.append(f"{expected}: unsupported capability state")
    runs = record.get("runs")
    if not isinstance(runs, list) or (record.get("availability") == "available" and len(runs) != 2):
        errors.append(f"{expected}: expected two bounded runs")
    else:
        names = set()
        for run in runs:
            if not isinstance(run, dict):
                errors.append(f"{expected}: run is not an object"); continue
            names.add(run.get("name"))
            if run.get("outcome") not in OUTCOMES:
                errors.append(f"{expected}: invalid run outcome")
            argv = run.get("argv")
            if not isinstance(argv, list) or "<input-not-retained>" not in argv:
                errors.append(f"{expected}: invocation shape is not redacted")
            if "raw_stdout" in run or "raw_stderr" in run:
                errors.append(f"{expected}: raw output retained")
        if record.get("availability") == "available" and names != {"bounded_success", "schema_boundary"}:
            errors.append(f"{expected}: missing required run classes")
    if record.get("project_delta") != []:
        errors.append(f"{expected}: project delta is not empty")
    raw = json.dumps(record, ensure_ascii=False)
    if FORBIDDEN.search(raw):
        errors.append(f"{expected}: forbidden retained content")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: validate-provider-matrix.py MATRIX CODEX CLAUDE", file=sys.stderr)
        return 2
    matrix_path, codex_path, claude_path = map(Path, argv[1:])
    try:
        matrix, records = load(matrix_path), [load(codex_path), load(claude_path)]
    except ValueError as error:
        print(error, file=sys.stderr); return 1
    errors: list[str] = []
    if not isinstance(matrix, dict) or matrix.get("schema_version") != "provider-matrix-v1":
        errors.append("matrix: identity mismatch")
    rows = matrix.get("providers") if isinstance(matrix, dict) else None
    if not isinstance(rows, list) or [row.get("provider") for row in rows if isinstance(row, dict)] != list(PROVIDERS):
        errors.append("matrix: provider ordering/coverage mismatch")
    else:
        for row, record, expected in zip(rows, records, PROVIDERS):
            if row.get("record") != f"provider-probes/{expected}.json":
                errors.append(f"matrix: bad record link for {expected}")
            if row.get("capabilities") != record.get("capabilities"):
                errors.append(f"matrix: capability mismatch for {expected}")
    for record, expected in zip(records, PROVIDERS):
        errors.extend(check_record(record, expected))
    raw_matrix = json.dumps(matrix, ensure_ascii=False)
    if FORBIDDEN.search(raw_matrix):
        errors.append("matrix: forbidden retained content")
    if errors:
        print("\n".join(errors), file=sys.stderr); return 1
    print("provider matrix: valid (2 provider records, 4 bounded run records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
