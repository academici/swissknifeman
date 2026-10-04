#!/usr/bin/env python3
"""Read-only verification of legacy phase-close evidence; new writes are retired."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PKG / "lib"))
sys.path.insert(0, str(_PKG.parent.parent))

from task import phase_findings, plan_closure, plan_decisions, plan_gates, plan_status  # noqa: E402


def close(plan_dir, phase_id, *, actor, note, check=False, session_id=None):
    if not check:
        raise ValueError("PLAN_CLOSE_WHOLE_PLAN_ONLY: phase-close writes are retired; verify phase acceptance inside plan-run")
    root = Path(plan_dir)
    candidate = plan_gates.phase_candidate_fingerprint(root, phase_id)
    gate = plan_gates.phase_close_gate(root, phase_id,
        candidate_fingerprint=candidate["fingerprint"], candidate_snapshot=candidate["snapshot"])
    if not gate["allow"]:
        raise ValueError(f"{gate['code']}: {gate}")
    proof = gate.get("audit_policy", {}).get("findings_resolution")
    if proof and not phase_findings.closed_green(root, phase_id):
        raise ValueError("PHASE_FINDINGS_CLOSE_MISSING: legacy phase-close proof is absent")
    plan_decisions.build_views(root, check=True)
    plan_status.build_status(root, check=True)
    plan_closure.build_closure(root, phase_id, check=True)
    return {"phase_id": phase_id, "gate": gate, "fingerprint": candidate["fingerprint"], "checked": check}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", required=True, type=Path)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--actor", default="task:plan-close")
    parser.add_argument("--session-id", help="actual invoking provider session ID; required for a new close")
    parser.add_argument("--note", default="Phase GREEN; current acceptance verified.\nwrite-site: pre_mutation: allow · pre_final: allow")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(close(args.plan_dir, args.phase, actor=args.actor, note=args.note,
                               check=args.check, session_id=args.session_id), ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
