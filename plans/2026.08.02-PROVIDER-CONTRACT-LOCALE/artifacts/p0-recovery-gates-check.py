#!/usr/bin/env python3
"""Semantic fail-closed P0 recovery contract producer and verifier."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


PLAN_ID = "2026.08.02-PROVIDER-CONTRACT-LOCALE"
CONTRACT_VERSION = "v1.0.1"
REQUIRED_GATES = tuple(f"R{number:02d}" for number in range(1, 8))
REQUIRED_OBLIGATIONS = tuple(f"G{number:02d}" for number in range(1, 12))
PREDECESSOR_VERSIONS = {
    "provider-migration-gates.md": "v1.0.0",
    "provider-capability-contract.md": "v1.0.0",
    "provider-artifact-contract.md": "v1.3.0",
    "provider-config-contract.md": "v1.0.0",
    "provider-harness-contract.md": "v1.0.0",
    "provider-instruction-contract.md": "v1.0.0",
    "provider-command-routing-contract.md": "v1.0.0",
}
PIN_HEADERS = ("Predecessor", "Version", "SHA-256", "Preserved boundary")
MAPPING_HEADERS = (
    "Obligation", "Predecessor gate", "Source row SHA-256",
    "Successor enforcement", "Failure action",
)
RECOVERY_HEADERS = (
    "Gate", "Transition", "Producer", "Independent verifier", "Verifier phase",
    "Required evidence", "Owner", "Pass rule", "Failure action",
)
PREDECESSOR_GATE_HEADERS = (
    "Gate", "Transition", "Exact producer item / verifier", "Evidence path", "Owner",
    "Pass rule", "failure action",
)
SECRET_RE = re.compile(r"(?:sk-[A-Za-z0-9_-]{20,}|/(?:home|Users)/[^\s|`]+)")
SHA_RE = re.compile(r"sha256:[0-9a-f]{64}")


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def json_file(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"object required: {path}")
    return value


def metadata(text: str, field: str) -> str:
    match = re.search(rf"^\*\*{re.escape(field)}:\*\*\s*(.+)$", text, re.MULTILINE)
    if not match:
        raise ValueError(f"missing contract metadata: {field}")
    return match.group(1).strip()


def table(text: str, heading: str, headers: tuple[str, ...]) -> list[dict[str, str]]:
    marker = f"## {heading}"
    try:
        section = text.split(marker, 1)[1]
    except IndexError as exc:
        raise ValueError(f"missing section: {heading}") from exc
    section = section.split("\n## ", 1)[0]
    lines = [line for line in section.splitlines() if line.startswith("|")]
    if len(lines) < 3:
        raise ValueError(f"missing table: {heading}")
    observed_headers = tuple(cell.strip() for cell in lines[0].strip("|").split("|"))
    if observed_headers != headers:
        raise ValueError(f"table schema mismatch: {heading}")
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
        if len(cells) != len(headers):
            raise ValueError(f"table row width mismatch: {heading}")
        rows.append(dict(zip(headers, cells)))
    return rows


def row_sha(row: dict[str, str]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def decision_path(directory: Path, decision_id: str) -> Path:
    matches = [path for path in directory.glob(f"{decision_id}-*.md") if not path.name.startswith("_")]
    if len(matches) != 1:
        raise ValueError("exact immutable decision record required")
    return matches[0]


def require_freeze_decision(directory: Path, decision_id: str, contract: Path) -> Path:
    path = decision_path(directory, decision_id)
    text = path.read_text(encoding="utf-8")
    required = {
        "status: accepted",
        "type: contract_freeze_decision",
        f"contract_version: {CONTRACT_VERSION}",
        f"contract_sha256: {sha(contract)}",
    }
    if not required.issubset(set(text.splitlines())):
        raise ValueError("typed accepted exact-hash contract-freeze decision required")
    return path


def require_predecessors(contract_text: str, predecessor_dir: Path) -> dict[str, str]:
    rows = table(contract_text, "Predecessor source pins", PIN_HEADERS)
    names = [row["Predecessor"].strip("`") for row in rows]
    if names != list(PREDECESSOR_VERSIONS):
        raise ValueError("predecessor order or exact set mismatch")
    result: dict[str, str] = {}
    for row in rows:
        name = row["Predecessor"].strip("`")
        path = predecessor_dir / name
        if row["Version"] != PREDECESSOR_VERSIONS[name]:
            raise ValueError(f"predecessor version mismatch: {name}")
        actual = sha(path)
        if row["SHA-256"] != actual:
            raise ValueError(f"predecessor digest mismatch: {name}")
        if not row["Preserved boundary"]:
            raise ValueError(f"empty predecessor boundary: {name}")
        result[name] = actual
    return result


def require_obligation_mapping(contract_text: str, predecessor_dir: Path) -> dict[str, str]:
    predecessor_text = (predecessor_dir / "provider-migration-gates.md").read_text(encoding="utf-8")
    source_rows = table(predecessor_text, "Preconditions", PREDECESSOR_GATE_HEADERS)
    source_ids = [row["Gate"] for row in source_rows]
    if source_ids != list(REQUIRED_OBLIGATIONS):
        raise ValueError("predecessor G01–G11 order or exact set mismatch")
    source = {row["Gate"]: row_sha(row) for row in source_rows}
    rows = table(contract_text, "Exact G01–G11 obligation mapping", MAPPING_HEADERS)
    gates = [row["Predecessor gate"] for row in rows]
    obligations = [row["Obligation"] for row in rows]
    if gates != list(REQUIRED_OBLIGATIONS) or obligations != [f"O-{gate}" for gate in REQUIRED_OBLIGATIONS]:
        raise ValueError("G01–G11 mapping order, identity, or exact set mismatch")
    for row in rows:
        gate = row["Predecessor gate"]
        if row["Source row SHA-256"] != source[gate]:
            raise ValueError(f"predecessor obligation weakened or changed: {gate}")
        if not row["Successor enforcement"] or not row["Failure action"]:
            raise ValueError(f"incomplete obligation mapping: {gate}")
    return source


def require_recovery_topology(contract_text: str) -> list[dict[str, str]]:
    rows = table(contract_text, "Recovery transition matrix", RECOVERY_HEADERS)
    if [row["Gate"] for row in rows] != list(REQUIRED_GATES):
        raise ValueError("R01–R07 order or exact set mismatch")
    for index, row in enumerate(rows):
        empty = [name for name in RECOVERY_HEADERS if not row[name]]
        if empty:
            raise ValueError(f"empty recovery field {row['Gate']}: {empty[0]}")
        transition = re.fullmatch(r"P(\d+) → P(\d+)", row["Transition"])
        if not transition or tuple(map(int, transition.groups())) != (index, index + 1):
            raise ValueError(f"transition order mismatch: {row['Gate']}")
        phase = f"P{index}"
        if row["Verifier phase"] != phase:
            raise ValueError(f"future, self, or cyclic verifier phase: {row['Gate']}")
        expected = f"task:plan-audit {PLAN_ID} {phase}"
        if expected not in row["Independent verifier"] or "P7.4" in row["Independent verifier"]:
            raise ValueError(f"unavailable transition verifier: {row['Gate']}")
        if phase not in row["Producer"]:
            raise ValueError(f"producer phase mismatch: {row['Gate']}")
    final_rows = table(contract_text, "Final release audit", ("Role", "Verifier", "Scope", "Timing"))
    if len(final_rows) != 1 or final_rows[0]["Verifier"] != "`P7.4`" or "never used to open P1–P7" not in final_rows[0]["Timing"]:
        raise ValueError("P7.4 final-only topology mismatch")
    return rows


def require_matrix(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required = ("`action_set=[]`", "no-op baseline", CONTRACT_VERSION, "pending exact freeze decision")
    if any(value not in text for value in required):
        raise ValueError("action matrix does not reference the corrective no-op contract")
    if SECRET_RE.search(text):
        raise ValueError("matrix privacy leak")


def validate_contract(contract: Path, predecessor_dir: Path, *, status: str) -> dict:
    text = contract.read_text(encoding="utf-8")
    if metadata(text, "Version") != CONTRACT_VERSION or metadata(text, "Status") != status:
        raise ValueError(f"contract must be {CONTRACT_VERSION} {status}")
    pins = require_predecessors(text, predecessor_dir)
    obligations = require_obligation_mapping(text, predecessor_dir)
    rows = require_recovery_topology(text)
    return {
        "contract_sha256": sha(contract),
        "predecessor_sha256": pins,
        "obligation_row_sha256": obligations,
        "recovery_gates": [row["Gate"] for row in rows],
    }


def inputs(args: argparse.Namespace, *, require_decision: bool, status: str) -> dict:
    manifest = json_file(Path(args.manifest))
    classification = json_file(Path(args.classification))
    if manifest.get("bundle_id") != "P0.1-provider-fleet-baseline":
        raise ValueError("unexpected manifest")
    if classification.get("schema_version") != 1 or not classification.get("classifications"):
        raise ValueError("unexpected classification")
    contract = Path(args.contract)
    result = validate_contract(contract, Path(args.predecessor_dir), status=status)
    require_matrix(Path(args.action_matrix))
    result.update({
        "manifest_sha256": sha(Path(args.manifest)),
        "classification_sha256": sha(Path(args.classification)),
        "action_matrix_sha256": sha(Path(args.action_matrix)),
        "checker_sha256": sha(Path(__file__).resolve()),
    })
    if require_decision:
        decision = require_freeze_decision(
            Path(args.decision_dir), args.contract_freeze_decision, contract,
        )
        result.update({
            "contract_freeze_decision": args.contract_freeze_decision,
            "decision_sha256": sha(decision),
        })
    return result


def validate_draft(args: argparse.Namespace) -> int:
    inputs(args, require_decision=False, status="draft")
    print("allow")
    return 0


def evidence(args: argparse.Namespace) -> dict:
    result = inputs(args, require_decision=True, status="frozen")
    result.update({
        "schema_version": "p0-recovery-gates-check/v2",
        "branch": "admission",
        "action_set": [],
        "result": "pass",
    })
    return result


def write(args: argparse.Namespace) -> int:
    value = evidence(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    print("allow")
    return 0


def check(args: argparse.Namespace) -> int:
    actual = json_file(Path(args.evidence))
    decision_id = actual.get("contract_freeze_decision")
    if not isinstance(decision_id, str):
        raise ValueError("missing contract-freeze decision")
    args.contract_freeze_decision = decision_id
    if actual != evidence(args):
        raise ValueError("evidence digest drift")
    print("allow")
    return 0


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--manifest", required=True)
    common.add_argument("--classification", required=True)
    common.add_argument("--contract", required=True)
    common.add_argument("--action-matrix", required=True)
    common.add_argument("--predecessor-dir", required=True)
    common.add_argument("--decision-dir", required=True)
    main = argparse.ArgumentParser()
    commands = main.add_subparsers(dest="command", required=True)
    draft = commands.add_parser("validate-draft", parents=[common])
    draft.set_defaults(run=validate_draft)
    writer = commands.add_parser("write", parents=[common])
    writer.add_argument("--contract-freeze-decision", required=True)
    writer.add_argument("--output", required=True)
    writer.set_defaults(run=write)
    checker = commands.add_parser("check", parents=[common])
    checker.add_argument("--evidence", required=True)
    checker.set_defaults(run=check)
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
