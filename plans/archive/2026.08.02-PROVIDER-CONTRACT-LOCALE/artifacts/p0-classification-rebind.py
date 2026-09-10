#!/usr/bin/env python3
"""Prove and record P0.2's digest-only forward rebind."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path


PLAN = Path(__file__).resolve().parent.parent
REPO = PLAN.parents[1]
HISTORICAL_COMMIT = "1e552dd4"
CLASSIFICATION = PLAN / "artifacts/P0-provider-fleet-classification.json"
DEFAULT_OUTPUT = PLAN / "artifacts/P0.9/classification-rebind-v1.json"
RECORD_FIELDS = (
    "artifact_id", "project_id", "path", "providers", "node", "managed", "tracked",
    "target_state", "classification", "owner", "action", "rollback", "destination",
)
TOP_LEVEL_FIELDS = {"schema_version", "source", "policy", "classifications", "known_cases", "summary"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RebindError(ValueError):
    pass


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def document(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != TOP_LEVEL_FIELDS:
        raise RebindError("classification schema changed")
    if not isinstance(value["classifications"], list) or not isinstance(value["known_cases"], list):
        raise RebindError("classification rows or known cases are invalid")
    return value


def historical_bytes(commit: str) -> bytes:
    relative = CLASSIFICATION.relative_to(REPO).as_posix()
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise RebindError(f"historical classification unavailable: {completed.stderr.decode().strip()}")
    return completed.stdout


def projection(value: dict) -> dict:
    records = []
    for row in value["classifications"]:
        if not isinstance(row, dict) or set(row) != set(RECORD_FIELDS) | {"evidence"}:
            raise RebindError("classification row schema changed")
        records.append({field: row[field] for field in RECORD_FIELDS})
    source = value["source"]
    if not isinstance(source, dict) or set(source) != {"snapshot", "inventory", "row_count"}:
        raise RebindError("classification source schema changed")
    return {
        "schema_version": value["schema_version"],
        "source": {"row_count": source["row_count"]},
        "policy": value["policy"],
        "classifications": records,
        "known_cases": value["known_cases"],
        "summary": value["summary"],
    }


def consumer_pins() -> dict[str, str]:
    research = (PLAN / "research/12-p0.8-validation-recovery-design.md").read_text(encoding="utf-8")
    research_match = re.search(r"\| Source SHA-256 \| `([0-9a-f]{64})` \|", research)
    provenance = (PLAN / "artifacts/p0-execution-provenance.py").read_text(encoding="utf-8")
    provenance_match = re.search(r'"source_sha256": "([0-9a-f]{64})"', provenance)
    recovery = json.loads((PLAN / "artifacts/P0.3/recovery-gates-check.json").read_text(encoding="utf-8"))
    recovery_pin = recovery.get("classification_sha256", "").removeprefix("sha256:")
    pins = {
        "research/12-p0.8-validation-recovery-design.md": research_match.group(1) if research_match else "",
        "artifacts/p0-execution-provenance.py": provenance_match.group(1) if provenance_match else "",
        "artifacts/P0.3/recovery-gates-check.json": recovery_pin,
    }
    if any(not SHA256.fullmatch(value) for value in pins.values()):
        raise RebindError("consumer pin is missing or malformed")
    return pins


def build(*, historical_commit: str) -> dict:
    old_bytes = historical_bytes(historical_commit)
    old = json.loads(old_bytes)
    current_bytes = CLASSIFICATION.read_bytes()
    current = document(CLASSIFICATION)
    old_projection = projection(old)
    current_projection = projection(current)
    if old_projection != current_projection:
        raise RebindError("semantic classification delta")
    current_hash = sha256(current_bytes)
    pins = consumer_pins()
    if set(pins.values()) != {current_hash}:
        raise RebindError("consumer pin coverage is incomplete or stale")
    return {
        "schema_version": "p0-classification-rebind/v1",
        "historical_commit": historical_commit,
        "classification": {
            "old_sha256": sha256(old_bytes),
            "new_sha256": current_hash,
            "old_bytes": len(old_bytes),
            "new_bytes": len(current_bytes),
            "semantic_projection_sha256": sha256(canonical(current_projection)),
            "semantic_rows": len(current_projection["classifications"]),
            "summary": current_projection["summary"],
            "policy": current_projection["policy"],
        },
        "consumer_pins": pins,
    }


def write(path: Path, *, historical_commit: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(build(historical_commit=historical_commit)))


def check(path: Path, *, historical_commit: str) -> None:
    if not path.is_file():
        raise RebindError("classification rebind carrier is missing")
    validate_carrier(json.loads(path.read_text(encoding="utf-8")), historical_commit=historical_commit)


def validate_carrier(candidate: dict, *, historical_commit: str) -> None:
    if candidate != build(historical_commit=historical_commit):
        raise RebindError("classification rebind carrier is stale")


def self_test() -> None:
    baseline = document(CLASSIFICATION)
    reference = projection(baseline)
    mutations = []
    reordered = copy.deepcopy(baseline); reordered["classifications"].reverse(); mutations.append(reordered)
    for field in RECORD_FIELDS:
        changed = copy.deepcopy(baseline)
        changed["classifications"][0][field] = "mutated" if field != "providers" else ["mutated"]
        mutations.append(changed)
    changed = copy.deepcopy(baseline); changed["known_cases"][0]["case"] = "mutated"; mutations.append(changed)
    changed = copy.deepcopy(baseline); changed["summary"]["ambiguous"] -= 1; mutations.append(changed)
    if any(projection(candidate) == reference for candidate in mutations):
        raise RebindError("semantic mutation was accepted")
    carrier = build(historical_commit=HISTORICAL_COMMIT)
    for mutator in (
        lambda value: value["classification"].__setitem__("old_sha256", "0" * 64),
        lambda value: value["classification"].__setitem__("new_sha256", "0" * 64),
        lambda value: value["consumer_pins"].pop("artifacts/P0.3/recovery-gates-check.json"),
    ):
        changed = copy.deepcopy(carrier)
        mutator(changed)
        try:
            validate_carrier(changed, historical_commit=HISTORICAL_COMMIT)
        except RebindError:
            continue
        raise RebindError("digest or consumer-pin mutation was accepted")
    result = subprocess.run([sys.executable, str(PLAN / "artifacts/p0-provider-fleet-classify.py"), "--check"], check=False)
    if result.returncode:
        raise RebindError("production classification check failed")


def main() -> int:
    parser = argparse.ArgumentParser(description="P0 digest-only classification rebind")
    parser.add_argument("action", choices=("write", "check", "self-test"))
    parser.add_argument("--plan-dir", type=Path, default=PLAN)
    parser.add_argument("--historical-commit", default=HISTORICAL_COMMIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.plan_dir.resolve() != PLAN:
        raise SystemExit("rejected: unexpected plan directory")
    try:
        if args.action == "write":
            write(args.output, historical_commit=args.historical_commit)
        elif args.action == "check":
            check(args.output, historical_commit=args.historical_commit)
        else:
            self_test()
    except (OSError, ValueError, json.JSONDecodeError, RebindError) as exc:
        print(f"rejected: {exc}", file=sys.stderr)
        return 1
    print("allow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
