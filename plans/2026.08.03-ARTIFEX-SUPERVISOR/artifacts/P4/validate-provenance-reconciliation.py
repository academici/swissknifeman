#!/usr/bin/env python3
"""Independent P4.7 reconciliation validation from Git and current plan carriers."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


EXPECTED = {
    "P4.1": ("abdd888a", "🟢 Done", 8, False),
    "P4.2": ("bde07fb0", "🟠 Done with deviations", 1, True),
    "P4.3": ("e3c932aa", "🟢 Done", 8, True),
    "P4.4": ("7607b0c0", "🟠 Done with deviations", 7, True),
    "P4.5": ("23f71d34", "🟠 Done with deviations", 18, True),
    "P4.6": ("10422237", "🟠 Done with deviations", 5, True),
}


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.plan_dir.resolve().parents[1]
    value = json.loads(args.record.read_text(encoding="utf-8"))
    if value.get("schema_version") != "artifex-p4-provenance-reconciliation-v1":
        raise ValueError("schema")
    rows = value.get("items")
    if not isinstance(rows, list) or [row.get("id") for row in rows] != list(EXPECTED):
        raise ValueError("item identity")
    statuses = current_statuses((args.plan_dir / "phases/P4.md").read_text(encoding="utf-8"))
    journal = (args.plan_dir / "journal.jsonl").read_text(encoding="utf-8")
    by_id = {row["id"]: row for row in rows}
    for item_id, (commit, status, count, has_close) in EXPECTED.items():
        row = by_id[item_id]
        if (row.get("commit"), row.get("status"), row.get("file_count"), row.get("journal_close")) != (commit, status, count, has_close):
            raise ValueError(f"declared reconciliation: {item_id}")
        if statuses.get(item_id) != status:
            raise ValueError(f"current status: {item_id}")
        files = [line for line in git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines() if line]
        if len(files) != count:
            raise ValueError(f"git file count: {item_id}")
        if has_close and f'"item_id": "{item_id}"' not in journal:
            raise ValueError(f"journal carrier: {item_id}")
    corrections = value.get("historical_corrections", {})
    if corrections.get("P4.2", {}).get("extra_path") != "packages/artifex/tests/test_scheduler.py":
        raise ValueError("P4.2 correction")
    if corrections.get("P4.4", {}).get("extra_path") not in git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "7607b0c0"):
        raise ValueError("P4.4 activity proof")
    if corrections.get("P4.6", {}).get("hook_status") != "green":
        raise ValueError("P4.6 hook status")
    print("provenance reconciliation validator: OK (P4.1–P4.6 Git/status/journal map)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"provenance reconciliation validator: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
