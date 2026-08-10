#!/usr/bin/env python3
"""Independent P4.7 reconciliation validation from Git and current plan carriers."""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path


EXPECTED = {
    "P4.1": ("abdd888a", "🟢 Done", 8, False,
             {"fault_cuts": 16, "artifex_tests": 62}),
    "P4.2": ("bde07fb0", "🟠 Done with deviations", 1, True,
             {"artifex_tests": 66, "recovery_cuts": 16}),
    "P4.3": ("e3c932aa", "🟢 Done", 8, True,
             {"artifex_tests": 70, "worktree_cases": 7}),
    "P4.4": ("7607b0c0", "🟠 Done with deviations", 7, True,
             {"artifex_tests": 73}),
    "P4.5": ("23f71d34", "🟠 Done with deviations", 18, True,
             {"artifex_tests": 77}),
    "P4.6": ("10422237", "🟠 Done with deviations", 5, True,
             {"hook_actions": 0, "hook_clean_rows": 2}),
}

TERMINAL_RESULTS = {"closed-green", "closed-deviations"}


def git(root: Path, *args: str) -> str:
    run = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True)
    if run.returncode:
        raise ValueError(run.stderr.strip() or "git failed")
    return run.stdout


def current_statuses(phase: str) -> dict[str, str]:
    rows = {}
    for line in phase.splitlines():
        if line.startswith("| P4."):
            cells = [value.strip() for value in line.strip("|").split("|")]
            if len(cells) >= 3:
                rows[cells[0]] = cells[2]
    return rows


def journal_rows(text: str) -> list[dict]:
    rows = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"journal row {line_number}")
        rows.append(row)
    return rows


def validate(value: dict, *, root: Path, phase: str, journal: str) -> None:
    if value.get("schema_version") != "artifex-p4-provenance-reconciliation-v1":
        raise ValueError("schema")
    rows = value.get("items")
    if not isinstance(rows, list) or [row.get("id") for row in rows] != list(EXPECTED):
        raise ValueError("item identity")
    statuses = current_statuses(phase)
    events = journal_rows(journal)
    by_id = {row["id"]: row for row in rows}
    for item_id, (commit, status, count, has_close, anchors) in EXPECTED.items():
        row = by_id[item_id]
        if set(row) != {"id", "commit", "status", "file_count", "journal_close",
                        "limitation", "anchors"}:
            raise ValueError(f"item shape: {item_id}")
        if (row.get("commit"), row.get("status"), row.get("file_count"),
                row.get("journal_close"), row.get("anchors")) != (
                    commit, status, count, has_close, anchors):
            raise ValueError(f"declared reconciliation: {item_id}")
        if statuses.get(item_id) != status:
            raise ValueError(f"current status: {item_id}")
        resolved = git(root, "rev-parse", "--verify", f"{commit}^{{commit}}").strip()
        if not resolved.startswith(commit):
            raise ValueError(f"git commit: {item_id}")
        files = [line for line in git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines() if line]
        if len(files) != count:
            raise ValueError(f"git file count: {item_id}")
        closes = [event for event in events
                  if event.get("item_id") == item_id
                  and event.get("result") in TERMINAL_RESULTS]
        if bool(closes) != has_close:
            raise ValueError(f"journal close presence: {item_id}")
        if has_close and not any(commit in str(event.get("note", "")) for event in closes):
            close_commit = value.get("historical_corrections", {}).get(
                item_id, {}).get("close_commit")
            if not close_commit or not any(
                    close_commit in str(event.get("note", "")) for event in closes):
                raise ValueError(f"journal commit carrier: {item_id}")
    corrections = value.get("historical_corrections", {})
    if set(corrections) != {"P4.2", "P4.4", "P4.6"}:
        raise ValueError("historical corrections shape")
    if corrections.get("P4.2", {}).get("extra_path") != "packages/artifex/tests/test_scheduler.py":
        raise ValueError("P4.2 correction")
    if corrections.get("P4.4", {}).get("extra_path") not in git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "7607b0c0"):
        raise ValueError("P4.4 activity proof")
    if corrections.get("P4.6", {}).get("hook_status") != "green":
        raise ValueError("P4.6 hook status")


def self_test(value: dict, *, root: Path, phase: str, journal: str) -> None:
    probes = []
    bad_anchor = copy.deepcopy(value)
    bad_anchor["items"][0]["anchors"]["fault_cuts"] += 1
    probes.append(("anchor", bad_anchor, journal))
    bad_close = "\n".join(
        line for line in journal.splitlines()
        if not ('"item_id": "P4.3"' in line and '"result": "closed-green"' in line))
    probes.append(("journal close", value, bad_close))
    fake_close = journal + "\n" + json.dumps({"item_id": "P4.1", "result": "closed-green",
                                                "note": "abdd888a"})
    probes.append(("journal absence", value, fake_close))
    for name, candidate, candidate_journal in probes:
        try:
            validate(candidate, root=root, phase=phase, journal=candidate_journal)
        except ValueError:
            continue
        raise ValueError(f"tamper probe accepted: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    root = args.plan_dir.resolve().parents[1]
    value = json.loads(args.record.read_text(encoding="utf-8"))
    phase = (args.plan_dir / "phases/P4.md").read_text(encoding="utf-8")
    journal = (args.plan_dir / "journal.jsonl").read_text(encoding="utf-8")
    validate(value, root=root, phase=phase, journal=journal)
    if args.self_test:
        self_test(value, root=root, phase=phase, journal=journal)
    print("provenance reconciliation validator: OK (P4.1–P4.6 Git/status/journal map)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"provenance reconciliation validator: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
