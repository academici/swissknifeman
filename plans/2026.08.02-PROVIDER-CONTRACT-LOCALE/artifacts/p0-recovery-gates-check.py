#!/usr/bin/env python3
"""Fail-closed P0 recovery-gate evidence producer and verifier."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


REQUIRED_GATES = {f"R{number:02d}" for number in range(1, 8)}
REQUIRED_PREDECESSORS = {"provider-migration-gates.md", "provider-capability-contract.md", "provider-artifact-contract.md", "provider-config-contract.md", "provider-harness-contract.md", "provider-instruction-contract.md", "provider-command-routing-contract.md"}
SECRET_RE = re.compile(r"sk-[A-Za-z0-9_-]{20,}")


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def json_file(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"object required: {path}")
    return value


def decision_path(directory: Path, decision_id: str) -> Path:
    matches = list(directory.glob(f"{decision_id}-*.md"))
    if len(matches) != 1 or matches[0].name.startswith("_"):
        raise ValueError("exact immutable decision record required")
    return matches[0]


def require_freeze_decision(directory: Path, decision_id: str) -> Path:
    path = decision_path(directory, decision_id)
    text = path.read_text(encoding="utf-8")
    if "status: accepted" not in text or "type: contract_freeze_decision" not in text:
        raise ValueError("typed accepted contract-freeze decision required")
    return path


def require_contract(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "**Version:** v1.0.0" not in text or "**Status:** frozen" not in text:
        raise ValueError("unfrozen recovery contract")
    gates = set(re.findall(r"\| (R\d\d) \|", text))
    if gates != REQUIRED_GATES:
        raise ValueError("recovery gate coverage mismatch")
    if not REQUIRED_PREDECESSORS.issubset(set(re.findall(r"`([^`]+)`", text))):
        raise ValueError("predecessor coverage mismatch")


def require_matrix(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "`action_set=[]`" not in text or "no-op baseline" not in text:
        raise ValueError("action matrix is not frozen no-op")
    if "/home/" in text or SECRET_RE.search(text):
        raise ValueError("matrix privacy leak")


def inputs(args: argparse.Namespace, *, require_decision: bool) -> dict:
    manifest, classification = json_file(Path(args.manifest)), json_file(Path(args.classification))
    if manifest.get("bundle_id") != "P0.1-provider-fleet-baseline":
        raise ValueError("unexpected manifest")
    if classification.get("schema_version") != 1 or not classification.get("classifications"):
        raise ValueError("unexpected classification")
    contract, matrix = Path(args.contract), Path(args.action_matrix)
    require_contract(contract)
    require_matrix(matrix)
    result = {"manifest_sha256": sha(Path(args.manifest)), "classification_sha256": sha(Path(args.classification)), "contract_sha256": sha(contract), "action_matrix_sha256": sha(matrix), "checker_sha256": sha(Path(__file__).resolve())}
    if require_decision:
        decision = require_freeze_decision(Path(args.decision_dir), args.contract_freeze_decision)
        result.update({"contract_freeze_decision": args.contract_freeze_decision, "decision_sha256": sha(decision)})
    return result


def evidence(args: argparse.Namespace, *, require_decision: bool) -> dict:
    result = inputs(args, require_decision=require_decision)
    if require_decision:
        result.update({"schema_version": "p0-recovery-gates-check/v1", "branch": "admission", "action_set": [], "result": "pass"})
    return result


def write(args: argparse.Namespace) -> int:
    value = evidence(args, require_decision=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("allow")
    return 0


def check(args: argparse.Namespace) -> int:
    actual = json_file(Path(args.evidence))
    decision_id = actual.get("contract_freeze_decision")
    if not isinstance(decision_id, str):
        raise ValueError("missing contract-freeze decision")
    args.contract_freeze_decision = decision_id
    expected = evidence(args, require_decision=True)
    if actual != expected:
        raise ValueError("evidence digest drift")
    print("allow")
    return 0


def verify_branch(args: argparse.Namespace) -> int:
    if args.branch != "no-op":
        raise ValueError("mutation branch requires separate containment authority")
    check_args = argparse.Namespace(**vars(args))
    check_args.evidence = args.p0_check_evidence
    check(check_args)
    fresh = json_file(Path(args.fresh_evidence))
    expected = {"schema_version": "p0-fresh-security-trust-evidence/v1", "action_set": [], "plaintext_secret_findings": 0, "protected_target_delta": 0, "provider_trust": {"claude-code": "green", "codex": "green"}}
    if fresh != expected:
        raise ValueError("fresh no-op predicate failed")
    result = {"schema_version": "p0-branch-verdict/v1", "branch": "no-op", "action_set": [], "plaintext_secret_findings": 0, "protected_target_delta": 0, "authority_reference": None, "result": "pass", "fresh_evidence_sha256": sha(Path(args.fresh_evidence)), "p0_check_evidence_sha256": sha(Path(args.p0_check_evidence))}
    if "/home/" in json.dumps(result) or SECRET_RE.search(json.dumps(result)):
        raise ValueError("verdict privacy leak")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("allow")
    return 0


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--manifest", required=True)
    common.add_argument("--classification", required=True)
    common.add_argument("--contract", required=True)
    common.add_argument("--action-matrix", required=True)
    common.add_argument("--decision-dir", required=True)
    main = argparse.ArgumentParser()
    commands = main.add_subparsers(dest="command", required=True)
    write_parser = commands.add_parser("write", parents=[common]); write_parser.add_argument("--contract-freeze-decision", required=True); write_parser.add_argument("--output", required=True); write_parser.set_defaults(run=write)
    check_parser = commands.add_parser("check", parents=[common]); check_parser.add_argument("--evidence", required=True); check_parser.set_defaults(run=check)
    branch_parser = commands.add_parser("verify-branch", parents=[common]); branch_parser.add_argument("--branch", required=True, choices=["no-op", "mutation"]); branch_parser.add_argument("--p0-check-evidence", required=True); branch_parser.add_argument("--fresh-evidence", required=True); branch_parser.add_argument("--output", required=True); branch_parser.set_defaults(run=verify_branch)
    return main


def main() -> int:
    args = parser().parse_args()
    try:
        return args.run(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
