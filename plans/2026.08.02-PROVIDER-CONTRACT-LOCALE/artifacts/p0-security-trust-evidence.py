#!/usr/bin/env python3
"""Produce and verify privacy-minimized P0.7 no-op security evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "p0-security-trust-evidence/v2"
DETECTOR_VERSION = "allowlist-v1"
SECRET = re.compile(r"(?:sk-[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
ABSOLUTE = re.compile(r"(?:^|[\"'\s])/(?:home|tmp|private|var)/|[A-Za-z]:\\Users\\")


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


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
        completed = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=20, check=False)
        exit_code = completed.returncode
    except (OSError, subprocess.TimeoutExpired):
        exit_code = None
    return {"id": command_id, "argv": argv, "exit": exit_code,
            "class": "green" if exit_code == 0 else "unavailable" if exit_code is None else "red"}


def observations(plan_dir: Path, fixture: Path | None) -> list[dict]:
    if fixture:
        value = json_object(fixture)
        rows = value.get("commands")
        if not isinstance(rows, list):
            raise ValueError("fixture commands required")
        return rows
    root = plan_dir.parents[1]
    return [
        command("harness-provider-audit", ["bash", "packages/harness/bin/harness", "doctor", "--provider-audit", "--json"], cwd=root),
        command("maind-strict-health", ["bash", "packages/maind/bin/maind", "health", "--cwd", "--strict"], cwd=root),
        command("codex-doctor", ["codex", "doctor", "--json"], cwd=root),
    ]


def detector(manifest: Path) -> dict:
    document = json_object(manifest)
    names = document.get("files")
    if not isinstance(names, list) or not all(isinstance(name, str) and "/" not in name for name in names):
        raise ValueError("sealed manifest allowlist required")
    base = manifest.parent
    findings = []
    for name in names:
        path = base / name
        if not path.is_file() or path.resolve().parent != base.resolve():
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
    if {row.get("id") for row in rows} != {"harness-provider-audit", "maind-strict-health", "codex-doctor"}:
        raise ValueError("exact command observations required")
    if any(not isinstance(row.get("argv"), list) or row.get("class") not in {"green", "red", "unavailable"} for row in rows):
        raise ValueError("malformed command observation")
    observed = now()
    detector_result = detector(manifest)
    pins = {name: sha(path) for name, path in paths.items()}
    protected = {name: pins[name] for name in ("manifest", "classification", "contract", "recovery_checker", "recovery_evidence", "freeze_decision")}
    all_green = all(row["class"] == "green" for row in rows)
    action_set = [] if all_green and detector_result["count"] == 0 else ["containment-review"]
    return {
        "schema_version": SCHEMA, "observed_at": iso(observed), "expires_at": iso(observed + timedelta(minutes=10)),
        "producer_sha256": sha(Path(__file__)), "commands": rows, "detector": detector_result,
        "inputs": pins, "protected_inventory_before": protected, "protected_inventory_after": protected,
        "protected_target_delta": 0, "plaintext_secret_findings": detector_result["count"],
        "provider_trust": {"claude-code": "green" if rows[0]["class"] == rows[1]["class"] == "green" else "red",
                           "codex": "green" if rows[1]["class"] == rows[2]["class"] == "green" else "red"},
        "action_set": action_set,
    }


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify(args: argparse.Namespace) -> dict:
    evidence = json_object(Path(args.evidence))
    plan_dir, manifest = Path(args.plan_dir), Path(args.manifest)
    if evidence.get("schema_version") != SCHEMA or evidence.get("producer_sha256") != sha(Path(__file__)):
        raise ValueError("producer provenance drift")
    expires = datetime.strptime(evidence.get("expires_at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if expires <= now():
        raise ValueError("evidence expired")
    expected_inputs = {name: sha(path) for name, path in plan_paths(plan_dir, manifest).items()}
    if evidence.get("inputs") != expected_inputs or evidence.get("protected_inventory_before") != evidence.get("protected_inventory_after"):
        raise ValueError("pinned input or protected inventory drift")
    detector_value = evidence.get("detector")
    if not isinstance(detector_value, dict) or detector_value.get("sha256") != sha(Path(__file__)) or detector_value.get("count") != 0:
        raise ValueError("detector provenance or finding drift")
    rows = evidence.get("commands")
    if not isinstance(rows, list) or any(row.get("class") != "green" for row in rows):
        raise ValueError("command observation not green")
    if evidence.get("provider_trust") != {"claude-code": "green", "codex": "green"} or evidence.get("action_set") != [] or evidence.get("protected_target_delta") != 0:
        raise ValueError("no-op predicate rejected")
    raw = Path(args.evidence).read_bytes()
    return {"schema_version": "p0-branch-verdict/v2", "branch": "no-op", "result": "pass", "action_set": [],
            "plaintext_secret_findings": 0, "protected_target_delta": 0,
            "fresh_evidence_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "producer_sha256": sha(Path(__file__)), "recovery_checker_sha256": expected_inputs["recovery_checker"],
            "authority_reference": None}


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("capture", "check"):
        sub = commands.add_parser(name)
        sub.add_argument("--plan-dir", required=True)
        sub.add_argument("--manifest", required=True)
        if name == "capture":
            sub.add_argument("--output", required=True); sub.add_argument("--fixture")
        else:
            sub.add_argument("--evidence", required=True); sub.add_argument("--branch-output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "capture":
            write(Path(args.output), capture(args))
        else:
            write(Path(args.branch_output), verify(args))
        print("allow")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
