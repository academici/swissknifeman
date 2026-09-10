#!/usr/bin/env python3
"""Produce integrity-only P0 observations and one-shot live admission receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "p0-security-trust-evidence/v3"
RECEIPT_SCHEMA = "p0-live-admission/v1"
DETECTOR_VERSION = "allowlist-v1"
COMMAND_TIMEOUT_SECONDS = 60
SECRET = re.compile(r"(?:sk-[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
UNSAFE = re.compile(r"(?:/(?:home|tmp|private|var)/|[A-Za-z]:\\Users\\|(?:account|user)[_-]?id\s*[:=])", re.I)
COMMANDS = (
    ("harness-provider-audit", ["bash", "packages/harness/bin/harness", "doctor", "--provider-audit", "--json"]),
    ("maind-strict-health", ["bash", "packages/maind/bin/maind", "health", "--cwd", "--strict"]),
    ("codex-doctor", ["codex", "doctor", "--json"]),
)


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def json_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"object required: {path.name}")
    return value


def plan_paths(plan_dir: Path, manifest: Path) -> dict[str, Path]:
    artifacts = plan_dir / "artifacts"
    return {
        "manifest": manifest,
        "classification": artifacts / "P0-provider-fleet-classification.json",
        "contract": plan_dir / "root/contracts/provider-recovery-gates-v1.md",
        "recovery_checker": artifacts / "p0-recovery-gates-check.py",
        "recovery_evidence": artifacts / "P0.3/recovery-gates-check.json",
        "freeze_decision": plan_dir / "decisions/D67-p0-recovery-gates-v1.0.1-freeze.md",
    }


def command(command_id: str, argv: list[str], *, cwd: Path) -> dict:
    try:
        result = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=COMMAND_TIMEOUT_SECONDS, check=False)
        exit_code = result.returncode
    except (OSError, subprocess.TimeoutExpired):
        exit_code = None
    return {"id": command_id, "argv": argv, "exit": exit_code,
            "class": "green" if exit_code == 0 else "unavailable" if exit_code is None else "red"}


def observations(plan_dir: Path, fixture: Path | None = None) -> list[dict]:
    if fixture is not None:
        rows = json_object(fixture).get("commands")
        if not isinstance(rows, list):
            raise ValueError("fixture commands required")
        by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
        if set(by_id) != {command_id for command_id, _argv in COMMANDS}:
            raise ValueError("fixture command identifiers required")
        return [{"id": command_id, "argv": argv, "exit": by_id[command_id].get("exit"),
                 "class": by_id[command_id].get("class")} for command_id, argv in COMMANDS]
    root = plan_dir.parents[1]
    return [command(command_id, argv, cwd=root) for command_id, argv in COMMANDS]


def detector(manifest: Path) -> dict:
    document = json_object(manifest)
    names = document.get("files")
    if not isinstance(names, list) or not all(isinstance(name, str) and "/" not in name for name in names):
        raise ValueError("sealed manifest allowlist required")
    findings = []
    for name in names:
        path = manifest.parent / name
        if not path.is_file() or path.resolve().parent != manifest.parent.resolve():
            raise ValueError("unreadable or out-of-root detector node")
        if SECRET.search(path.read_text(encoding="utf-8")):
            findings.append("secret-pattern")
    return {"version": DETECTOR_VERSION, "sha256": sha(Path(__file__)), "findings": sorted(set(findings)), "count": len(set(findings))}


def capture(args: argparse.Namespace) -> dict:
    plan_dir, manifest = Path(args.plan_dir), Path(args.manifest)
    paths = plan_paths(plan_dir, manifest)
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("required pinned input missing")
    rows = observations(plan_dir, Path(args.fixture) if args.fixture else None)
    if [(row.get("id"), row.get("argv")) for row in rows] != list(COMMANDS):
        raise ValueError("exact command observations required")
    if any(row.get("class") not in {"green", "red", "unavailable"} for row in rows):
        raise ValueError("malformed command observation")
    detector_result = detector(manifest)
    pins = {name: sha(path) for name, path in paths.items()}
    protected = {name: pins[name] for name in ("manifest", "classification", "contract", "recovery_checker", "recovery_evidence", "freeze_decision")}
    all_green = all(row["class"] == "green" for row in rows)
    return {
        "schema_version": SCHEMA, "observation_kind": "recorded-integrity-only", "observed_at": now(),
        "producer_sha256": sha(Path(__file__)), "commands": rows, "detector": detector_result,
        "inputs": pins, "protected_inventory_before": protected, "protected_inventory_after": protected,
        "protected_target_delta": 0, "plaintext_secret_findings": detector_result["count"],
        "provider_trust": {"claude-code": "green" if rows[0]["class"] == rows[1]["class"] == "green" else "red",
                           "codex": "green" if rows[1]["class"] == rows[2]["class"] == "green" else "red"},
        "action_set": [] if all_green and detector_result["count"] == 0 else ["containment-review"],
    }


def predicate(value: dict, *, plan_dir: Path, manifest: Path) -> None:
    if value.get("schema_version") != SCHEMA or value.get("observation_kind") != "recorded-integrity-only":
        raise ValueError("stored observation schema mismatch")
    if value.get("producer_sha256") != sha(Path(__file__)):
        raise ValueError("producer provenance drift")
    expected_inputs = {name: sha(path) for name, path in plan_paths(plan_dir, manifest).items()}
    if value.get("inputs") != expected_inputs:
        raise ValueError("pinned input drift")
    protected = {name: expected_inputs[name] for name in ("manifest", "classification", "contract", "recovery_checker", "recovery_evidence", "freeze_decision")}
    if value.get("protected_inventory_before") != protected or value.get("protected_inventory_after") != protected or value.get("protected_target_delta") != 0:
        raise ValueError("protected inventory drift")
    if [(row.get("id"), row.get("argv")) for row in value.get("commands", [])] != list(COMMANDS):
        raise ValueError("command identity drift")
    if any(row.get("class") != "green" for row in value["commands"]):
        raise ValueError("command observation not green")
    current_detector = detector(manifest)
    if value.get("detector") != current_detector or current_detector["count"] != 0:
        raise ValueError("detector provenance or finding drift")
    if value.get("provider_trust") != {"claude-code": "green", "codex": "green"} or value.get("action_set") != [] or value.get("plaintext_secret_findings") != 0:
        raise ValueError("no-op predicate rejected")


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def integrity_verdict(args: argparse.Namespace) -> dict:
    evidence = json_object(Path(args.evidence))
    predicate(evidence, plan_dir=Path(args.plan_dir), manifest=Path(args.manifest))
    return {"schema_version": "p0-branch-verdict/v3", "branch": "no-op", "result": "integrity-only",
            "admission_authority": False, "action_set": [], "plaintext_secret_findings": 0,
            "protected_target_delta": 0, "recorded_evidence_sha256": sha(Path(args.evidence)),
            "producer_sha256": sha(Path(__file__)), "authority_reference": None}


def admit(args: argparse.Namespace) -> dict:
    observation = capture(args)
    predicate(observation, plan_dir=Path(args.plan_dir), manifest=Path(args.manifest))
    receipt = {"schema_version": RECEIPT_SCHEMA, "result": "allow", "observed_at": observation["observed_at"],
               "command_ids": [row["id"] for row in observation["commands"]], "inputs": observation["inputs"],
               "detector": {"version": observation["detector"]["version"], "count": 0},
               "protected_target_delta": 0, "action_set": []}
    text = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
    if SECRET.search(text) or UNSAFE.search(text):
        raise ValueError("admission receipt privacy rejection")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("capture", "check", "admit"):
        sub = commands.add_parser(name)
        sub.add_argument("--plan-dir", required=True)
        sub.add_argument("--manifest", required=True)
        if name == "capture":
            sub.add_argument("--output", required=True); sub.add_argument("--fixture")
        elif name == "check":
            sub.add_argument("--evidence", required=True); sub.add_argument("--branch-output", required=True)
        else:
            sub.add_argument("--stdout", action="store_true", required=True); sub.add_argument("--fixture")
    args = parser.parse_args()
    try:
        if args.command == "capture":
            value = capture(args); write(Path(args.output), value)
            if value["action_set"]:
                raise ValueError("capture no-op predicate rejected")
        elif args.command == "check":
            write(Path(args.branch_output), integrity_verdict(args))
        else:
            print(json.dumps(admit(args), ensure_ascii=False, sort_keys=True))
        print("allow", file=sys.stderr)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
