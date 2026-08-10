#!/usr/bin/env python3
"""Fail-closed pre-mutation authority probe for P4.8."""
from __future__ import annotations

import argparse
from pathlib import Path

from task import route_evidence, task_contract


GATE_ID = "G-OWNER-P4.8-G2-REQUALIFICATION"
BRANCH = "p4.8-g2-authority-requalification"
SCOPE = (
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/authority-policy-v1.md · "
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/supervisor-run-v1.md · "
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P1/authority-policy-cases-v1.json · "
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P1/supervisor-run-cases-v1.json · "
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P1/contract-manifest-v1.json · "
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P1/validate-authority-policy.py · "
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/validate-hook-integrity.py · "
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/attention-cases-v1.json · "
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/authority-requalification-v1.json · "
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/assurance-manifest-v1.json · "
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/validate-authority-requalification.py · "
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/validate-assurance.py · "
    "packages/artifex/lib/artifex/authority.py · "
    "packages/artifex/lib/artifex/scheduler.py · "
    "packages/artifex/lib/artifex/telemetry.py · "
    "packages/artifex/lib/artifex/cli.py · "
    "packages/artifex/README.md · "
    "packages/artifex/tests/test_authority.py · "
    "packages/artifex/tests/test_scheduler.py · "
    "packages/artifex/tests/test_attention_telemetry.py"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-dir", type=Path, required=True)
    args = parser.parse_args()
    actual = route_evidence.capture_actual(
        "implementation", "high", source="self-attested",
        ts="2026-08-05T00:00:00Z", model="p4.8-authority-preflight",
    )
    contract = task_contract.build(
        args.plan_dir.resolve(),
        "P4.8",
        actual_route=actual,
        protected_transition={"gate_id": GATE_ID, "branch": BRANCH, "scope": SCOPE},
    )
    result = task_contract.evaluate(contract)
    authority = contract["authority"]
    expected = {
        "class": "owner-gate",
        "granted": True,
        "pre_mutation": "allow",
        "pre_final": "allow",
    }
    observed = {
        "class": authority["class"],
        "granted": authority["granted"],
        "pre_mutation": result["pre_mutation"],
        "pre_final": result["pre_final"],
    }
    if observed != expected:
        raise SystemExit(f"P4.8 authority preflight: FAIL: {observed!r}")
    granted_by = authority["granted_by"]
    if not granted_by.startswith("plan.md:D104:") or f"[OWNER-GRANT:{GATE_ID}]" not in granted_by:
        raise SystemExit(f"P4.8 authority preflight: FAIL: provenance={granted_by!r}")
    print(
        "P4.8 authority preflight: OK · authority.class=owner-gate · granted=true · "
        "pre_mutation=allow · pre_final=allow · provenance=D104"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
