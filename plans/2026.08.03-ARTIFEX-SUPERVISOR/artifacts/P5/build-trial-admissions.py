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

# --- D122 replacement batch (P5.1 reopen under D121/D122) -------------------
# Additive only: every literal below is a SECOND authority, never a replacement of
# the D105 literals above. The v1 code path keeps its own defaults byte-for-byte.
RETRY_OWNER_MARKER = "[OWNER-GRANT:G-OWNER-P5.2-RETRY]"
RETRY_OWNER_DECISION = "D122"
# D122 forbids extending D105's expiry, so the replacement batch inherits it verbatim.
RETRY_EXPIRY = "2026-08-12T23:59:59Z"
RETRY_RAISED_PROVIDER = "claude-code"
RETRY_TIMEOUT_MS = 600000
RETRY_BASE_TIMEOUT_MS = 180000
# The exhaustive closed set D122 authorizes: three replacement rows, each bound to the
# spent v1 row it replaces. A fourth row or a reused v1 identity has no authority.
RETRY_TRIAL_IDS = {
    "p5.2r-slice-01-worktree-core": "p5.2-slice-01-worktree-core",
    "p5.2r-slice-02-worktree-binding": "p5.2-slice-02-worktree-binding",
    "p5.2r-slice-03-worktree-evidence": "p5.2-slice-03-worktree-evidence",
}
# Row fields whose identity legitimately changes with the new trial_id; everything
# else must be byte-equal to the v1 counterpart (D122: same scenarios, file scopes,
# base and providers).
RETRY_IDENTITY_FIELDS = ("trial_id", "controlled_root", "order")
# The exact literals of the `| D122 |` Decision Log row. That row states its grant in
# prose rather than in D105's `key=`value`` fields, so the authorized bounds are
# verified as exact literals of the row itself and cross-checked against the request.
RETRY_PLAN_LITERALS = (
    RETRY_OWNER_MARKER,
    "«Поднять до 600000 ms в новых строках (реком.)»",
    "brief/34-p5.2-zero-accept-owner-decision-2026-08-06.md",
    "exactly three replacement P5.2 repository-slice trials",
    "`reusable:false`",
    "`180000` to `600000`",
    RETRY_EXPIRY,
)


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


def owner_grant_retry(plan: Path, request: dict[str, Any]) -> dict[str, Any]:
    """D122 `[OWNER-GRANT:G-OWNER-P5.2-RETRY]` — the replacement-batch authority.

    Verified against the exact literal of the `| D122 |` row (`RETRY_PLAN_LITERALS`)
    and against D105's own `per_trial_caps` literal for "every other cap unchanged".
    Nothing is defaulted locally: an absent literal refuses before any write.
    """
    text = plan.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.startswith(f"| {RETRY_OWNER_DECISION} |")]
    if len(lines) != 1:
        raise BuildError("exact D122 owner grant row unavailable")
    line = lines[0]
    for literal in RETRY_PLAN_LITERALS:
        if literal not in line:
            raise BuildError(f"D122 literal unavailable: {literal}")
    if OWNER_MARKER in line:
        raise BuildError("D122 must not carry the D105 owner marker")
    for later in text.splitlines():
        match = re.match(r"\| D(\d+) \|", later)
        if (match and int(match.group(1)) > int(RETRY_OWNER_DECISION[1:])
                and request["request_hash"] in later and "revoked=`true`" in later):
            raise BuildError(f"D122 revoked by D{match.group(1)}")
    expiry = datetime.fromisoformat(RETRY_EXPIRY.replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expiry:
        raise BuildError("D122 replacement grant expired")
    d105 = [row for row in text.splitlines() if row.startswith(f"| {OWNER_DECISION} |")]
    if len(d105) != 1:
        raise BuildError("D105 caps literal unavailable")
    frozen_caps = parse_caps(capture(d105[0], "per_trial_caps", "expiry"))
    caps = request.get("per_trial_caps")
    if not isinstance(caps, dict) or set(caps) != set(frozen_caps):
        raise BuildError("D122 cap key set differs from the frozen caps")
    for key, value in frozen_caps.items():
        allowed = RETRY_TIMEOUT_MS if key == "timeout_ms" else value
        if caps[key] != allowed:
            raise BuildError(f"D122 cap outside the grant: {key}")
    if request.get("owner_marker") != RETRY_OWNER_MARKER:
        raise BuildError("request owner marker is not the D122 grant")
    if (request.get("maximum_dispatch_count") != len(RETRY_TRIAL_IDS)
            or sorted(request.get("trial_ids", [])) != sorted(RETRY_TRIAL_IDS)):
        raise BuildError("D122 authorizes exactly the three replacement trial ids")
    if sorted(request.get("providers", [])) != sorted(("claude-code", "codex")):
        raise BuildError("D122 keeps the two frozen providers")
    return {
        "owner_decision": RETRY_OWNER_DECISION,
        "owner_marker": RETRY_OWNER_MARKER,
        "branch": BRANCH,
        "catalog_hash": request["catalog_hash"],
        "request_hash": request["request_hash"],
        "providers": request["providers"],
        "controlled_roots": request["controlled_roots"],
        "maximum_dispatch_count": request["maximum_dispatch_count"],
        "per_trial_caps": caps,
        "expiry": RETRY_EXPIRY,
        "revoked": False,
    }


def validate_retry_rows(catalog: dict[str, Any], baseline: dict[str, Any]) -> None:
    """D122 rule (3) — the three replacement rows copy their v1 counterparts verbatim,
    with exactly one authorized change (`claude-code` `timeout_ms` 180000 → 600000).
    A fourth row, a reused v1 identity, a changed scope/base/provider or a second
    changed budget key refuses BEFORE any write."""
    if baseline.get("catalog_hash") != canonical_hash(baseline, omit="catalog_hash"):
        raise BuildError("baseline catalog content hash mismatch")
    v1_rows = {row["trial_id"]: row for row in baseline["trials"]}
    rows = catalog["trials"]
    if sorted(row["trial_id"] for row in rows) != sorted(RETRY_TRIAL_IDS):
        raise BuildError("replacement rows outside the D122 closed set")
    for row in rows:
        source = v1_rows.get(RETRY_TRIAL_IDS[row["trial_id"]])
        if source is None:
            raise BuildError(f"replaced v1 row unavailable: {row['trial_id']}")
        if row["controlled_root"] != f"mktemp:p5-p5-2-{row['trial_id']}":
            raise BuildError(f"controlled root outside the v1 convention: {row['trial_id']}")
        for key in set(source) | set(row):
            if key in RETRY_IDENTITY_FIELDS or key == "budgets":
                continue
            if row.get(key) != source.get(key):
                raise BuildError(f"replacement row diverges from v1: {row['trial_id']}:{key}")
        budgets, frozen = row["budgets"], source["budgets"]
        if set(budgets) != set(frozen):
            raise BuildError(f"budget key set changed: {row['trial_id']}")
        for key, value in frozen.items():
            raised = (key == "timeout_ms" and row["provider"] == RETRY_RAISED_PROVIDER
                      and value == RETRY_BASE_TIMEOUT_MS)
            if budgets[key] != (RETRY_TIMEOUT_MS if raised else value):
                raise BuildError(f"budget outside the D122 grant: {row['trial_id']}:{key}")


def package_digest(rows: list[dict[str, str]]) -> str:
    return canonical_hash(sorted(rows, key=lambda row: row["path"]))


def validate_package_generation(root: Path, g2_digest: str) -> None:
    """D121/D122 rule (6) — the live tree is NOT the immutable G2 package any more:
    D118/D119 deliberately moved the business-execution seam into `packages/artifex`,
    so `packages/artifex` is now the G2B successor. The equality that still holds, and
    the one the admission contract actually names, is two-sided: the current package
    equals the sole G2B digest of `business-successor-generation-v1.json`, and that
    manifest's own predecessor stays the immutable G2 digest every frozen carrier pins.
    """
    path = root / f"plans/{PLAN_ID}/artifacts/P5/business-successor-generation-v1.json"
    generation = load(path)
    if generation.get("schema_version") != "artifex-business-successor-generation-v1":
        raise BuildError("G2B generation manifest schema")
    if generation.get("generation_hash") != canonical_hash(generation, omit="generation_hash"):
        raise BuildError("G2B generation manifest hash")
    predecessor = generation.get("predecessor", {})
    successor = generation.get("successor", {})
    if predecessor.get("generation") != "G2" or successor.get("generation") != "G2B":
        raise BuildError("G2B generation lineage")
    if predecessor.get("digest") != g2_digest:
        raise BuildError("G2B predecessor is not the frozen G2 digest")
    rows = successor.get("package_files")
    if not isinstance(rows, list) or not rows:
        raise BuildError("G2B package rows unavailable")
    for row in rows:
        file = root / row["path"]
        if not file.is_file() or digest(file) != row["sha256"]:
            raise BuildError(f"current package differs from G2B: {row.get('path')}")


def validate_inputs(root: Path, catalog: dict[str, Any], request: dict[str, Any],
                    plan: Path, *, expected_trials: int = 14,
                    owner_decision: str = OWNER_DECISION,
                    baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    if catalog.get("catalog_hash") != canonical_hash(catalog, omit="catalog_hash"):
        raise BuildError("catalog content hash mismatch")
    if request.get("request_hash") != canonical_hash(request, omit="request_hash"):
        raise BuildError("request content hash mismatch")
    if request.get("catalog_hash") != catalog["catalog_hash"]:
        raise BuildError("request/catalog binding mismatch")
    trials = catalog.get("trials")
    if not isinstance(trials, list) or len(trials) != expected_trials:
        raise BuildError(f"exactly {expected_trials} frozen trials required")
    if [row.get("order") for row in trials] != list(range(1, expected_trials + 1)):
        raise BuildError("trial order mismatch")
    ids = [row.get("trial_id") for row in trials]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != expected_trials:
        raise BuildError("trial identity mismatch")
    if owner_decision == OWNER_DECISION:
        grant = owner_grant(plan, request["request_hash"])
    else:
        if baseline is None:
            raise BuildError("D122 mint requires the v1 baseline catalog")
        validate_retry_rows(catalog, baseline)
        grant = owner_grant_retry(plan, request)
    expected = {
        "catalog_hash": catalog["catalog_hash"],
        "request_hash": request["request_hash"],
        "providers": request["providers"],
        "controlled_roots": request["controlled_roots"],
        "maximum_dispatch_count": request["maximum_dispatch_count"],
        "per_trial_caps": request["per_trial_caps"],
    }
    if any(grant[key] != value for key, value in expected.items()):
        raise BuildError(f"{owner_decision} does not exactly match the frozen request")
    assurance_path = root / f"plans/{PLAN_ID}/artifacts/P4/assurance-manifest-v1.json"
    assurance = load(assurance_path)
    if digest(assurance_path) != request.get("assurance_sha256") or assurance.get("readiness") != "green":
        raise BuildError("current G2 assurance binding mismatch")
    package_rows = assurance.get("g2", {}).get("package_files")
    if not isinstance(package_rows, list):
        raise BuildError("G2 package rows unavailable")
    if package_digest(package_rows) != request.get("g2_package_digest"):
        raise BuildError("G2 package digest mismatch")
    validate_package_generation(root, request["g2_package_digest"])
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


def dispatch_grant(task: dict[str, Any], owner: dict[str, Any], *,
                   decision: str = OWNER_DECISION, marker: str = OWNER_MARKER,
                   branch: str = BRANCH) -> dict[str, Any]:
    value = {
        "schema_version": "artifex-business-dispatch-grant-v1",
        "grant_version": "1.0.0",
        "grant_id": f"{decision}:{task['task_id']}",
        "owner_decision": decision,
        "owner_marker": marker,
        "branch": branch,
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
    baseline = load(args.baseline_catalog) if args.baseline_catalog else None
    owner = validate_inputs(root, catalog, request, args.plan,
                            expected_trials=args.expected_trials,
                            owner_decision=args.owner_decision, baseline=baseline)
    tasks: list[dict[str, Any]] = []
    grants: list[dict[str, Any]] = []
    replays: list[dict[str, Any]] = []
    admissions: list[tuple[str, dict[str, Any]]] = []
    for row in catalog["trials"]:
        task = task_manifest(row, catalog, request)
        grant = dispatch_grant(task, owner, decision=owner["owner_decision"],
                               marker=owner["owner_marker"], branch=owner["branch"])
        replay = replay_identity(task, grant)
        tasks.append(task)
        grants.append(grant)
        replays.append(replay)
        admissions.append((row["trial_id"], admission(task, grant, replay)))

    write_json(args.grants, {
        "schema_version": "artifex-business-dispatch-grant-set-v1",
        "set_version": "1.0.0",
        "owner_decision": owner["owner_decision"],
        "catalog_hash": catalog["catalog_hash"],
        "request_hash": request["request_hash"],
        "grants": grants,
    })
    if args.manifest_index is not None:
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
            "path": f"{args.admissions_relpath}/{trial_id}.json",
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
    print(f"P5 business carriers: written ({len(index_rows)} {owner['owner_decision']}-bound "
          "admissions; 0 dispatch intents)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--grants", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--manifest-index", type=Path)
    parser.add_argument("--admission-index", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    # --- D122 replacement batch: explicit v2 inputs/outputs, v1 defaults unchanged ---
    parser.add_argument("--owner-decision", choices=(OWNER_DECISION, RETRY_OWNER_DECISION),
                        default=OWNER_DECISION)
    parser.add_argument("--expected-trials", type=int, default=14)
    parser.add_argument("--baseline-catalog", type=Path,
                        help="v1 catalog the D122 replacement rows are checked against")
    parser.add_argument("--admissions-relpath", default="artifacts/P5/trial-admissions")
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
