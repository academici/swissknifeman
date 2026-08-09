#!/usr/bin/env python3
"""Reproduce P4.6 acceptance without changing the historical corpus or baseline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "packages/task/lib"))

from task import plan_returns  # noqa: E402


def canonical_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def fail(message: str) -> None:
    raise SystemExit(f"acceptance failed: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-dir", required=True)
    parser.add_argument("--refresh-historical", action="store_true",
                        help="regenerate historical-detect.json from the read-only corpus")
    args = parser.parse_args()
    plan_dir = Path(args.plan_dir)
    artifact_dir = plan_dir / "artifacts/P4"
    historical_path = artifact_dir / "historical-detect.json"
    baseline_path = artifact_dir / "returns-baseline.json"

    first = plan_returns.measure_repository(ROOT)
    second = plan_returns.measure_repository(ROOT)
    if canonical_bytes(first) != canonical_bytes(second):
        fail("two historical measurements differ")
    if args.refresh_historical:
        historical_path.write_bytes(canonical_bytes(first))

    try:
        historical = json.loads(historical_path.read_text(encoding="utf-8"))
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"acceptance carrier unreadable: {exc}")
    if historical != first:
        fail("historical-detect.json is not the current deterministic measurement")
    for key in ("counts", "entries", "fingerprints", "journals", "return_events"):
        if baseline.get(key) != first.get(key):
            fail(f"baseline differs in {key}")
    for key, value in baseline["metrics"].items():
        if first["metrics"].get(key) != value:
            fail(f"baseline differs in metrics.{key}")
    expected_over_cap = sorted(digest for digest, count in baseline["counts"].items() if count > 2)
    if first["over_cap_subjects"] != expected_over_cap:
        fail("historical over-cap subjects do not derive from the unchanged baseline")

    fixture = ROOT / "packages/task/tests/data/plan-v2"
    gates = plan_returns.return_loop_gates(fixture)
    if len(gates) != 1:
        fail("classified fixture must yield one grouped gate")
    gate = gates[0]
    if (gate["namespace"], gate["action"], gate["occurrences"], gate["cap"]) != (
            "classified", "owner-gate", 3, 2):
        fail("classified fixture did not reach the expected owner gate")
    if gate["blocks"] is not True or gate["continue_allowed"] is not False or gate["stop_required"] is not True:
        fail("owner gate has contradictory continuation state")
    if gate.get("judgement", {}).get("return_event_id") != "journal.jsonl:7":
        fail("current-event judgement was not selected by return_event_id")
    packet_ids = [record["return_event_id"] for record in gate["owner_packet"]["judgements"]]
    if packet_ids != ["journal.jsonl:3", "journal.jsonl:5", "journal.jsonl:7"]:
        fail("owner packet is not complete and event ordered")
    if any(row["blocks"] and row["continue_allowed"] for row in gates):
        fail("gate matrix contains a blocking continuation")
    print("acceptance: historical byte-replay; baseline-derived 7 over-cap; classified event-scoped owner packet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
