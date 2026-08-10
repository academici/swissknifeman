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
PRIVATE_MATERIAL_RE = re.compile(
    r"(?:"
    r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"[A-Za-z]:\\Users\\[^\s|`]+"
    r")"
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"\b(?:account[_ -]?(?:id|identifier)|user[_ -]?id|api[_ -]?key|"
    r"access[_ -]?token|refresh[_ -]?token|secret|credential)\s*[:=]\s*"
    r"[`\"']?[A-Za-z0-9_./+@:-]{6,}",
    re.IGNORECASE,
)
SHA_RE = re.compile(r"sha256:[0-9a-f]{64}")
EXPECTED_MAPPING_ROW_SHA = {
    "G01": "sha256:8f99b703c1dd070efafba570103508cd44be57ce335af06657479c92de260fd1",
    "G02": "sha256:775751b358b2c6cb0c54a78c12d14707fbd6ed9ebda33c5a14f340cdf5ed9b6f",
    "G03": "sha256:7b66d86eb386c64b33e761bccd3a7c42e3097ff9935aed9eb9418ecb89242ab0",
    "G04": "sha256:b4f2cf5b74105071e64290ae41add5c37e477a8d89fc250ffc6486da9b674240",
    "G05": "sha256:e94a360e77c379cdae330b619451256ca2f7f96df618849f4fc5f918b98524e9",
    "G06": "sha256:2dcbc04f7f928c356a82b1d456feb06e61a6c2c477c628857a4b4ed31f89bf34",
    "G07": "sha256:d969f274803d6423b596ee306c652e9081d4efd4d1fb5670ef8a4bfb15c5675a",
    "G08": "sha256:68457bf4180df917cfa3cbb0e2a55447ec2c7cd433d26297f5442ea7bd1fe186",
    "G09": "sha256:350ed2d168756919fed4c54bc3e78b4e5fabaf666106c25c26e5b09c5ee5eded",
    "G10": "sha256:4ea1019bc833c39bb876e64448f48bba93e1a45a1cb8d8d41ad53aac10a3826c",
    "G11": "sha256:dd6451320202b5e515e4412074b1f99a9a8ebc31c9d75858d2a08a4965fe6d63",
}
EXPECTED_RECOVERY_ROW_SHA = {
    "R01": "sha256:55b165f0859e1d8e7aeabeaa6fae83b43fcb5762aff057185da6c5533d2bed81",
    "R02": "sha256:070ec305e3db2085b1ec15b4d4679fd81e5d31868e195f2979c1cf9b1241e545",
    "R03": "sha256:4dd8198cef552480ee4bae09457a34a39d92e2a7af9d741f0f961e9d7d4f2e12",
    "R04": "sha256:929cd4992de46fb3d7de7aa6107c834c0ec2c6e6b907dc986e257206c0d762e9",
    "R05": "sha256:e1941583c70e9ddf88f799c2b386321af28b21af7eec248355fdfecd537249cc",
    "R06": "sha256:8af05e7968a1fccbeb2df03009c78f8d079f8547c53349211c8144d455e3e595",
    "R07": "sha256:466b24f187387df4b585ef3359afbc15a2b991690d5dc1062ba71b450e2243d0",
}
EXPECTED_FINAL_AUDIT_ROW_SHA = (
    "sha256:3e6d952f8c8f230a007ad697eb984d9de1e8243fe8bffd91aa28242154387b6d"
)


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


def frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("decision frontmatter required")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("unterminated decision frontmatter") from exc
    result: dict[str, str] = {}
    for line in lines[1:end]:
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError("malformed decision frontmatter")
        key, value = (part.strip() for part in line.split(":", 1))
        if not key or not value or key in result:
            raise ValueError("malformed or duplicate decision frontmatter field")
        result[key] = value
    return result


def require_freeze_decision(directory: Path, decision_id: str, contract: Path) -> Path:
    path = decision_path(directory, decision_id)
    fields = frontmatter(path.read_text(encoding="utf-8"))
    required = {
        "id": decision_id,
        "status": "accepted",
        "type": "contract_freeze_decision",
        "item": "P0.6",
        "contract_version": CONTRACT_VERSION,
        "contract_sha256": sha(contract),
    }
    if any(fields.get(key) != value for key, value in required.items()):
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
        if row_sha(row) != EXPECTED_MAPPING_ROW_SHA[gate]:
            raise ValueError(f"successor obligation semantics drift: {gate}")
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
        if row_sha(row) != EXPECTED_RECOVERY_ROW_SHA[row["Gate"]]:
            raise ValueError(f"recovery row semantics drift: {row['Gate']}")
    final_rows = table(contract_text, "Final release audit", ("Role", "Verifier", "Scope", "Timing"))
    if len(final_rows) != 1 or row_sha(final_rows[0]) != EXPECTED_FINAL_AUDIT_ROW_SHA:
        raise ValueError("P7.4 final-only topology mismatch")
    return rows


def require_matrix(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required = ("`action_set=[]`", "no-op baseline", CONTRACT_VERSION, "pending exact freeze decision")
    if any(value not in text for value in required):
        raise ValueError("action matrix does not reference the corrective no-op contract")
    if SECRET_RE.search(text) or PRIVATE_MATERIAL_RE.search(text) or SENSITIVE_ASSIGNMENT_RE.search(text):
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
