#!/usr/bin/env python3
"""Materialize the exact D105-bound P5 business dispatch carriers."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
OWNER_MARKER = "[OWNER-GRANT:G-OWNER-P5-BUSINESS]"
OWNER_DECISION = "D105"
BRANCH = "p5-business-trials"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class BuildError(ValueError):
    """A fail-closed business-carrier generation error."""


def canonical_bytes(value: Any, *, omit: str | None = None) -> bytes:
    body = ({key: item for key, item in value.items() if key != omit}
            if omit and isinstance(value, dict) else value)
    return json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_hash(value: Any, *, omit: str | None = None) -> str:
    return hashlib.sha256(canonical_bytes(value, omit=omit)).hexdigest()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BuildError(f"JSON object required: {path}")
    return value


def render_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_json(value))


def parse_caps(raw: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for pair in raw.split(","):
        key, separator, value = pair.strip().partition(":")
        if not separator or not value.isdigit():
            raise BuildError("D105 per_trial_caps syntax")
        result[key] = int(value)
    return result


def capture(line: str, name: str, following: str) -> str:
    match = re.search(rf"{re.escape(name)}=`([^`]*)`; {re.escape(following)}=", line)
    if not match:
        raise BuildError(f"D105 field unavailable: {name}")
    return match.group(1)


def owner_grant(plan: Path, request_hash: str) -> dict[str, Any]:
    text = plan.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.startswith("| D105 |")]
    if len(lines) != 1 or OWNER_MARKER not in lines[0]:
        raise BuildError("exact D105 owner marker unavailable")
    line = lines[0]
    if "owner-message=`brief/22-p5-last-pass-fast-track.md`" not in line:
        raise BuildError("D105 owner-message provenance")
    grant = {
        "owner_decision": OWNER_DECISION,
        "owner_marker": OWNER_MARKER,
        "branch": capture(line, "branch", "catalog_sha256"),
        "catalog_hash": capture(line, "catalog_sha256", "request_sha256"),
        "request_hash": capture(line, "request_sha256", "providers"),
        "providers": capture(line, "providers", "controlled_roots").split(","),
        "controlled_roots": capture(line, "controlled_roots", "maximum_dispatch_count").split(" · "),
        "maximum_dispatch_count": int(capture(line, "maximum_dispatch_count", "per_trial_caps")),
        "per_trial_caps": parse_caps(capture(line, "per_trial_caps", "expiry")),
        "expiry": capture(line, "expiry", "revoked"),
        "revoked": capture(line, "revoked", "owner-message") == "true",
    }
    if grant["branch"] != BRANCH or grant["revoked"]:
        raise BuildError("D105 branch is unavailable or revoked")
    try:
        expiry = datetime.fromisoformat(grant["expiry"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise BuildError("D105 expiry syntax") from exc
    if datetime.now(timezone.utc) > expiry:
        raise BuildError("D105 owner grant expired")
    for later in text.splitlines():
        match = re.match(r"\| D(\d+) \|", later)
        if match and int(match.group(1)) > 105 and request_hash in later and "revoked=`true`" in later:
            raise BuildError(f"D105 revoked by D{match.group(1)}")
    return grant


def package_digest(rows: list[dict[str, str]]) -> str:
    return canonical_hash(sorted(rows, key=lambda row: row["path"]))


def validate_inputs(root: Path, catalog: dict[str, Any], request: dict[str, Any],
                    plan: Path) -> dict[str, Any]:
    if catalog.get("catalog_hash") != canonical_hash(catalog, omit="catalog_hash"):
        raise BuildError("catalog content hash mismatch")
    if request.get("request_hash") != canonical_hash(request, omit="request_hash"):
        raise BuildError("request content hash mismatch")
    if request.get("catalog_hash") != catalog["catalog_hash"]:
        raise BuildError("request/catalog binding mismatch")
    trials = catalog.get("trials")
    if not isinstance(trials, list) or len(trials) != 14:
        raise BuildError("exactly 14 frozen trials required")
    if [row.get("order") for row in trials] != list(range(1, 15)):
        raise BuildError("trial order mismatch")
    ids = [row.get("trial_id") for row in trials]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != 14:
        raise BuildError("trial identity mismatch")
    grant = owner_grant(plan, request["request_hash"])
    expected = {
        "catalog_hash": catalog["catalog_hash"],
        "request_hash": request["request_hash"],
        "providers": request["providers"],
        "controlled_roots": request["controlled_roots"],
        "maximum_dispatch_count": request["maximum_dispatch_count"],
        "per_trial_caps": request["per_trial_caps"],
    }
    if any(grant[key] != value for key, value in expected.items()):
        raise BuildError("D105 does not exactly match the frozen request")
    assurance_path = root / f"plans/{PLAN_ID}/artifacts/P4/assurance-manifest-v1.json"
    assurance = load(assurance_path)
    if digest(assurance_path) != request.get("assurance_sha256") or assurance.get("readiness") != "green":
        raise BuildError("current G2 assurance binding mismatch")
    package_rows = assurance.get("g2", {}).get("package_files")
    if not isinstance(package_rows, list):
        raise BuildError("G2 package rows unavailable")
    for row in package_rows:
        path = root / row["path"]
        if not path.is_file() or digest(path) != row["sha256"]:
            raise BuildError(f"current G2 package drift: {row.get('path')}")
    if package_digest(package_rows) != request.get("g2_package_digest"):
        raise BuildError("G2 package digest mismatch")
    return grant


def task_manifest(row: dict[str, Any], catalog: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    value = {
        "schema_version": "artifex-business-dispatch-task-v1",
        "manifest_version": "1.0.0",
        "task_id": row["trial_id"],
        "purpose": "business-trial",
        "parent_plan_id": PLAN_ID,
        "parent_item_id": row["item"],
        "catalog_hash": catalog["catalog_hash"],
        "request_hash": request["request_hash"],
        "g2_package_digest": request["g2_package_digest"],
        "provider": row["provider"],
        "repository": row["repository"],
        "controlled_root": row["controlled_root"],
        "base_commit": row["base_commit"],
        "files": row["files"],
        "route": row["route"],
        "capabilities": row["capabilities"],
        "acceptance_refs": row["acceptance_refs"],
        "validation": row["validation"],
        "budgets": row["budgets"],
    }
    value["task_hash"] = canonical_hash(value, omit="task_hash")
    return value


def dispatch_grant(task: dict[str, Any], owner: dict[str, Any]) -> dict[str, Any]:
    value = {
        "schema_version": "artifex-business-dispatch-grant-v1",
        "grant_version": "1.0.0",
        "grant_id": f"D105:{task['task_id']}",
        "owner_decision": OWNER_DECISION,
        "owner_marker": OWNER_MARKER,
        "branch": BRANCH,
        "purpose": "business-trial",
        "task_id": task["task_id"],
        "task_hash": task["task_hash"],
        "catalog_hash": task["catalog_hash"],
        "request_hash": task["request_hash"],
        "g2_package_digest": task["g2_package_digest"],
        "provider": task["provider"],
        "controlled_root": task["controlled_root"],
        "route": task["route"],
        "capabilities": task["capabilities"],
        "budgets": task["budgets"],
        "max_slices": 1,
        "expiry": owner["expiry"],
        "revoked": False,
    }
    value["grant_hash"] = canonical_hash(value, omit="grant_hash")
    return value


def replay_identity(task: dict[str, Any], grant: dict[str, Any]) -> dict[str, Any]:
    trial_id = task["task_id"]
    value = {
        "schema_version": "artifex-business-dispatch-replay-v1",
        "trial_id": trial_id,
        "task_id": trial_id,
        "grant_id": grant["grant_id"],
        "run_id": f"p5-business:{trial_id}",
        "slice_id": f"{trial_id}:1",
        "attempt": 1,
        "idempotency_key": hashlib.sha256(f"{PLAN_ID}|{trial_id}|1".encode()).hexdigest(),
        "events": [],
        "used_slices": 0,
    }
    value["replay_hash"] = canonical_hash(value, omit="replay_hash")
    return value


def admission(task: dict[str, Any], grant: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    value = {
        "schema_version": "artifex-business-dispatch-admission-v1",
        "admission_version": "1.0.0",
        "purpose": "business-trial",
        "trial_id": task["task_id"],
        "task": task,
        "grant": grant,
        "replay": replay,
        "usage": {"used_slices": 0, "max_slices": 1, "reusable": False},
    }
    value["admission_hash"] = canonical_hash(value, omit="admission_hash")
    return value


def build(root: Path, args: argparse.Namespace) -> None:
    catalog = load(args.catalog)
    request = load(args.request)
    owner = validate_inputs(root, catalog, request, args.plan)
    tasks: list[dict[str, Any]] = []
    grants: list[dict[str, Any]] = []
    replays: list[dict[str, Any]] = []
    admissions: list[tuple[str, dict[str, Any]]] = []
    for row in catalog["trials"]:
        task = task_manifest(row, catalog, request)
        grant = dispatch_grant(task, owner)
        replay = replay_identity(task, grant)
        tasks.append(task)
        grants.append(grant)
        replays.append(replay)
        admissions.append((row["trial_id"], admission(task, grant, replay)))

    write_json(args.grants, {
        "schema_version": "artifex-business-dispatch-grant-set-v1",
        "set_version": "1.0.0",
        "owner_decision": OWNER_DECISION,
        "catalog_hash": catalog["catalog_hash"],
        "request_hash": request["request_hash"],
        "grants": grants,
    })
    write_json(args.manifest_index, {
        "schema_version": "artifex-business-dispatch-manifest-index-v1",
        "index_version": "1.0.0",
        "catalog_hash": catalog["catalog_hash"],
        "request_hash": request["request_hash"],
        "g2_package_digest": request["g2_package_digest"],
        "manifests": [
            {"trial_id": task["task_id"], "task_hash": task["task_hash"],
             "document_sha256": hashlib.sha256(render_json(task)).hexdigest(), "task": task}
            for task in tasks
        ],
    })
    args.replay.parent.mkdir(parents=True, exist_ok=True)
    args.replay.write_bytes(b"".join(canonical_bytes(row) + b"\n" for row in replays))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    index_rows = []
    for trial_id, value in admissions:
        path = args.output_dir / f"{trial_id}.json"
        write_json(path, value)
        index_rows.append({
            "trial_id": trial_id,
            "provider": value["task"]["provider"],
            "path": f"artifacts/P5/trial-admissions/{trial_id}.json",
            "sha256": digest(path),
            "admission_hash": value["admission_hash"],
            "task_hash": value["task"]["task_hash"],
            "grant_hash": value["grant"]["grant_hash"],
            "replay_hash": value["replay"]["replay_hash"],
        })
    write_json(args.admission_index, {
        "schema_version": "artifex-business-dispatch-admission-index-v1",
        "index_version": "1.0.0",
        "catalog_hash": catalog["catalog_hash"],
        "request_hash": request["request_hash"],
        "g2_package_digest": request["g2_package_digest"],
        "admissions": index_rows,
    })
    print("P5 business carriers: written (14 D105-bound admissions; 0 dispatch intents)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--grants", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--manifest-index", type=Path, required=True)
    parser.add_argument("--admission-index", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    try:
        build(root, args)
    except (BuildError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"P5 business carrier builder: FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
