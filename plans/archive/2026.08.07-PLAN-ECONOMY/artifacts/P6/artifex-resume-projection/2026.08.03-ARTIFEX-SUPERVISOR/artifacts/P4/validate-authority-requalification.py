#!/usr/bin/env python3
"""Independent closed-set validation of P4.8 authority requalification."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

EXPECTED_PATHS = {
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/authority-policy-v1.md",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/supervisor-run-v1.md",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P1/authority-policy-cases-v1.json",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P1/contract-manifest-v1.json",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P1/supervisor-run-cases-v1.json",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P1/validate-authority-policy.py",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/assurance-manifest-v1.json",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/attention-cases-v1.json",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/validate-assurance.py",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/validate-hook-integrity.py",
    "packages/artifex/README.md", "packages/artifex/lib/artifex/authority.py",
    "packages/artifex/lib/artifex/cli.py", "packages/artifex/lib/artifex/scheduler.py",
    "packages/artifex/lib/artifex/telemetry.py", "packages/artifex/tests/test_attention_telemetry.py",
    "packages/artifex/tests/test_authority.py", "packages/artifex/tests/test_scheduler.py"}
KEYS = ("blast_radius", "rollback", "affected_slices", "no_decision_consequence", "blocking_dependencies", "authority_attention", "resolved", "withdrawn")

def git(root, *args):
    run = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True)
    if run.returncode: raise ValueError(run.stderr.strip())
    return run.stdout

def main():
    p = argparse.ArgumentParser(); p.add_argument("--record", type=Path, required=True); p.add_argument("--plan-dir", type=Path, required=True); p.add_argument("--before", required=True); p.add_argument("--historical-item", required=True); a = p.parse_args()
    root = a.plan_dir.resolve().parents[1]; value = json.loads(a.record.read_text())
    if value.get("schema_version") != "artifex-p4-authority-requalification-v1": raise ValueError("schema")
    if value.get("owner_gate") != "G-OWNER-P4.8-G2-REQUALIFICATION" or value.get("grant") != "plan.md:D104": raise ValueError("owner gate")
    if value.get("historical_diff") != {"before": a.before, "item": a.historical_item, "file_count": 18}: raise ValueError("historical metadata")
    actual = set(git(root, "diff", "--name-only", f"{a.before}..{a.historical_item}").splitlines())
    if actual != EXPECTED_PATHS: raise ValueError("historical protected path set")
    if tuple(value.get("semantic_keys", ())) != KEYS: raise ValueError("semantic key set")
    text = "\n".join((root / path).read_text() for path in ("plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/authority-policy-v1.md", "plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/supervisor-run-v1.md", "packages/artifex/lib/artifex/authority.py", "packages/artifex/lib/artifex/scheduler.py", "packages/artifex/lib/artifex/telemetry.py"))
    if any(key not in text for key in KEYS): raise ValueError("current semantic carrier")
    phase = (a.plan_dir / "phases/P4.md").read_text()
    if "| P4.7 | Repair committed-tree Harness validation and provenance | 🟢 Done |" not in phase: raise ValueError("stale P4.7")
    if value.get("predecessors") != {"p4_7_item": "138b2424", "g1_item": "367e477a"}: raise ValueError("predecessor map")
    print("authority requalification validator: OK (D104, 18 paths, closed semantics, P4.7/G1)")
if __name__ == "__main__":
    try: main()
    except (OSError, ValueError, json.JSONDecodeError) as e: print(f"authority requalification validator: FAIL: {e}", file=sys.stderr); raise SystemExit(1)
