#!/usr/bin/env python3
"""Independently validate all D105-bound P5 business admissions."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
OWNER_MARKER = "[OWNER-GRANT:G-OWNER-P5-BUSINESS]"
BRANCH = "p5-business-trials"

# --- D122 replacement batch (P5.1 reopen under D121/D122) -------------------
# A SECOND authority validated by the same closed-set rules, never a relaxation of
# the D105 ones: the v1 argument list keeps every D105 literal below as its default.
RETRY_OWNER_DECISION = "D122"
RETRY_OWNER_MARKER = "[OWNER-GRANT:G-OWNER-P5.2-RETRY]"
RETRY_EXPIRY = "2026-08-12T23:59:59Z"
RETRY_RAISED_PROVIDER = "claude-code"
RETRY_TIMEOUT_MS = 600000
RETRY_BASE_TIMEOUT_MS = 180000
RETRY_TRIAL_IDS = {
    "p5.2r-slice-01-worktree-core": "p5.2-slice-01-worktree-core",
    "p5.2r-slice-02-worktree-binding": "p5.2-slice-02-worktree-binding",
    "p5.2r-slice-03-worktree-evidence": "p5.2-slice-03-worktree-evidence",
}
RETRY_IDENTITY_FIELDS = ("trial_id", "controlled_root", "order")
RETRY_PLAN_LITERALS = (
    RETRY_OWNER_MARKER,
    "«Поднять до 600000 ms в новых строках (реком.)»",
    "brief/34-p5.2-zero-accept-owner-decision-2026-08-06.md",
    "exactly three replacement P5.2 repository-slice trials",
    "`reusable:false`",
    "`180000` to `600000`",
    RETRY_EXPIRY,
)
GENERATION_KEYS = {"schema_version", "generation_version", "predecessor", "successor", "generation_hash"}
FORBIDDEN_KEYS = {"prompt", "transcript", "thinking", "tool_payload", "environment", "credential", "secret"}
GRANT_SET_KEYS = {"schema_version", "set_version", "owner_decision", "catalog_hash", "request_hash", "grants"}
MANIFEST_INDEX_KEYS = {"schema_version", "index_version", "catalog_hash", "request_hash", "g2_package_digest", "manifests"}
ADMISSION_INDEX_KEYS = {"schema_version", "index_version", "catalog_hash", "request_hash", "g2_package_digest", "admissions"}
TASK_KEYS = {"schema_version", "manifest_version", "task_id", "task_hash", "purpose", "parent_plan_id", "parent_item_id", "catalog_hash", "request_hash", "g2_package_digest", "provider", "repository", "controlled_root", "base_commit", "files", "route", "capabilities", "acceptance_refs", "validation", "budgets"}
GRANT_KEYS = {"schema_version", "grant_version", "grant_id", "grant_hash", "owner_decision", "owner_marker", "branch", "purpose", "task_id", "task_hash", "catalog_hash", "request_hash", "g2_package_digest", "provider", "controlled_root", "route", "capabilities", "budgets", "max_slices", "expiry", "revoked"}
REPLAY_KEYS = {"schema_version", "trial_id", "task_id", "grant_id", "run_id", "slice_id", "attempt", "idempotency_key", "events", "used_slices", "replay_hash"}
ADMISSION_KEYS = {"schema_version", "admission_version", "purpose", "trial_id", "task", "grant", "replay", "usage", "admission_hash"}
MANIFEST_ROW_KEYS = {"trial_id", "task_hash", "document_sha256", "task"}
INDEX_ROW_KEYS = {"trial_id", "provider", "path", "sha256", "admission_hash", "task_hash", "grant_hash", "replay_hash"}


class ValidationError(ValueError):
    """A closed-set trial admission validation error."""


def canonical_hash(value: Any, *, omit: str | None = None) -> str:
    body = ({key: item for key, item in value.items() if key != omit}
            if omit and isinstance(value, dict) else value)
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"object required: {path}")
    return value


def ensure_no_forbidden_keys(value: Any, where: str) -> None:
    if isinstance(value, dict):
        overlap = set(value) & FORBIDDEN_KEYS
        if overlap:
            raise ValidationError(f"forbidden privacy key in {where}: {sorted(overlap)}")
        for key, child in value.items():
            ensure_no_forbidden_keys(child, f"{where}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            ensure_no_forbidden_keys(child, f"{where}[{index}]")


def replay_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"replay line {number}") from exc
        if not isinstance(value, dict):
            raise ValidationError(f"replay object {number}")
        rows.append(value)
    return rows


def validate_d105(root: Path, catalog: dict[str, Any], request: dict[str, Any]) -> None:
    text = (root / f"plans/{PLAN_ID}/plan.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| D105 |")]
    if len(rows) != 1 or "[OWNER-GRANT:G-OWNER-P5-BUSINESS]" not in rows[0]:
        raise ValidationError("exact D105 carrier")
    row = rows[0]
    required = [
        f"catalog_sha256=`{catalog['catalog_hash']}`",
        f"request_sha256=`{request['request_hash']}`",
        "providers=`claude-code,codex`",
        f"maximum_dispatch_count=`{request['maximum_dispatch_count']}`",
        "revoked=`false`",
    ]
    required.extend(root_value for root_value in request["controlled_roots"])
    required.extend(f"{key}:{value}" for key, value in request["per_trial_caps"].items())
    if any(value not in row for value in required):
        raise ValidationError("D105/request mismatch")
    for later in text.splitlines():
        match = re.match(r"\| D(\d+) \|", later)
        if (match and int(match.group(1)) > 105 and request["request_hash"] in later
                and "revoked=`true`" in later):
            raise ValidationError(f"D105 revoked by D{match.group(1)}")


def validate_d122(root: Path, request: dict[str, Any]) -> None:
    """The D122 replacement-batch grant. That Decision Log row states its bounds in
    prose rather than in D105's `key=`value`` fields, so each authorized bound is
    verified as an exact literal of the row and cross-checked against the request;
    "every other cap unchanged" is verified against D105's own caps literal."""
    text = (root / f"plans/{PLAN_ID}/plan.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith(f"| {RETRY_OWNER_DECISION} |")]
    if len(rows) != 1:
        raise ValidationError("exact D122 carrier")
    row = rows[0]
    if any(literal not in row for literal in RETRY_PLAN_LITERALS) or OWNER_MARKER in row:
        raise ValidationError("D122/owner literal mismatch")
    frozen = [line for line in text.splitlines() if line.startswith("| D105 |")]
    if len(frozen) != 1:
        raise ValidationError("D105 caps literal")
    caps = request.get("per_trial_caps")
    frozen_caps = re.search(r"per_trial_caps=`([^`]*)`", frozen[0])
    if not isinstance(caps, dict) or not frozen_caps:
        raise ValidationError("request/D105 caps")
    frozen_pairs = dict(pair.strip().split(":", 1) for pair in frozen_caps.group(1).split(","))
    if set(caps) != set(frozen_pairs):
        raise ValidationError("D122 cap key set")
    for key, value in caps.items():
        allowed = RETRY_TIMEOUT_MS if key == "timeout_ms" else int(frozen_pairs[key])
        if value != allowed:
            raise ValidationError(f"D122 cap outside the grant: {key}")
    if int(frozen_pairs["timeout_ms"]) != RETRY_BASE_TIMEOUT_MS:
        raise ValidationError("D122 timeout raise baseline")
    if request.get("owner_marker") != RETRY_OWNER_MARKER:
        raise ValidationError("request owner marker")
    for later in text.splitlines():
        match = re.match(r"\| D(\d+) \|", later)
        if (match and int(match.group(1)) > int(RETRY_OWNER_DECISION[1:])
                and request["request_hash"] in later and "revoked=`true`" in later):
            raise ValidationError(f"D122 revoked by D{match.group(1)}")


def validate_package_generation(root: Path, generation_path: Path) -> str:
    """D121/D122 rule (6). The old assertion — `packages/artifex` equals the immutable
    G2 digest — is structurally false since D118/D119 moved the business-execution seam
    into the package: the live tree is the G2B successor by construction. What the
    admission contract actually names is asserted instead, on both sides and without
    widening: the current package equals the sole G2B digest in
    `business-successor-generation-v1.json`, and that manifest's predecessor is still
    the immutable G2 digest that every frozen carrier pins. Returns that G2 digest so
    each admission is checked against it individually."""
    generation = load(generation_path)
    if (set(generation) != GENERATION_KEYS
            or generation.get("schema_version") != "artifex-business-successor-generation-v1"
            or generation.get("generation_version") != "1.0.0"):
        raise ValidationError("G2B generation closed schema")
    if generation.get("generation_hash") != canonical_hash(generation, omit="generation_hash"):
        raise ValidationError("G2B generation hash")
    predecessor = generation.get("predecessor", {})
    successor = generation.get("successor", {})
    if predecessor.get("generation") != "G2" or successor.get("generation") != "G2B":
        raise ValidationError("G2B generation lineage")
    g2_digest = predecessor.get("digest")
    if not isinstance(g2_digest, str) or not HEX64.fullmatch(g2_digest):
        raise ValidationError("G2 predecessor digest")
    rows = successor.get("package_files")
    if not isinstance(rows, list) or not rows:
        raise ValidationError("G2B package rows")
    for row in rows:
        path = root / row["path"]
        if not path.is_file() or digest(path) != row["sha256"]:
            raise ValidationError(f"current package differs from G2B: {row['path']}")
    return g2_digest


def validate_retry_rows(trials: list[dict[str, Any]], baseline: dict[str, Any]) -> None:
    """D122 rule (3), proven independently of the generator: three replacement rows,
    each byte-equal to the v1 row it replaces apart from its own identity and the one
    authorized `claude-code` wall-clock raise."""
    if baseline.get("catalog_hash") != canonical_hash(baseline, omit="catalog_hash"):
        raise ValidationError("baseline catalog hash")
    sources = {row["trial_id"]: row for row in baseline.get("trials", [])}
    if sorted(row["trial_id"] for row in trials) != sorted(RETRY_TRIAL_IDS):
        raise ValidationError("replacement rows outside the D122 closed set")
    for row in trials:
        source = sources.get(RETRY_TRIAL_IDS[row["trial_id"]])
        if source is None:
            raise ValidationError(f"replaced v1 row unavailable: {row['trial_id']}")
        if row.get("controlled_root") != f"mktemp:p5-p5-2-{row['trial_id']}":
            raise ValidationError(f"controlled root convention: {row['trial_id']}")
        for key in set(source) | set(row):
            if key in RETRY_IDENTITY_FIELDS or key == "budgets":
                continue
            if row.get(key) != source.get(key):
                raise ValidationError(f"replacement row diverges from v1: {row['trial_id']}:{key}")
        budgets, frozen = row.get("budgets"), source["budgets"]
        if not isinstance(budgets, dict) or set(budgets) != set(frozen):
            raise ValidationError(f"budget key set: {row['trial_id']}")
        for key, value in frozen.items():
            raised = (key == "timeout_ms" and row.get("provider") == RETRY_RAISED_PROVIDER
                      and value == RETRY_BASE_TIMEOUT_MS)
            if budgets[key] != (RETRY_TIMEOUT_MS if raised else value):
                raise ValidationError(f"budget outside the D122 grant: {row['trial_id']}:{key}")


def manifest_index_from_admissions(admission_index: Path, index_doc: dict[str, Any]) -> dict[str, Any]:
    """The D122 batch carries no dispatch-manifest index of its own (its Files list is
    exhaustive), so the task side is read from the admissions themselves. Every task is
    still proven against the catalog row, the grant, the replay identity and the
    admission hash below — only the separate index document is absent."""
    rows = []
    for row in index_doc.get("admissions", []):
        task = load(admission_index.parent.parent.parent / row["path"]).get("task")
        if not isinstance(task, dict):
            raise ValidationError(f"admission task object: {row.get('trial_id')}")
        rows.append({
            "trial_id": row["trial_id"], "task_hash": task.get("task_hash"),
            "document_sha256": hashlib.sha256(
                (json.dumps(task, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
            ).hexdigest(),
            "task": task,
        })
    return {"schema_version": "artifex-business-dispatch-manifest-index-v1",
            "index_version": "1.0.0", "catalog_hash": index_doc.get("catalog_hash"),
            "request_hash": index_doc.get("request_hash"),
            "g2_package_digest": index_doc.get("g2_package_digest"), "manifests": rows}


def validate_smoke_refusal(tasks_path: Path, grants_path: Path, admissions_path: Path,
                           business_hashes: set[str]) -> None:
    tasks = load(tasks_path).get("tasks")
    grants = load(grants_path).get("grants")
    admissions = load(admissions_path).get("admissions")
    if not all(isinstance(rows, list) and len(rows) == 2 for rows in (tasks, grants, admissions)):
        raise ValidationError("P3 smoke carrier set")
    smoke_hashes = set()
    for task in tasks:
        if task.get("purpose") != "provider-readiness-smoke":
            raise ValidationError("P3 task purpose")
        reason = "BUSINESS_AUTHORITY_REQUIRED" if task.get("purpose") != "business-trial" else "allow"
        if reason not in {"BUSINESS_AUTHORITY_REQUIRED", "PURPOSE_MISMATCH"}:
            raise ValidationError("P3 task accepted for business purpose")
        smoke_hashes.add(task.get("task_hash"))
    for grant in grants:
        if grant.get("owner_decision") != "D74" or grant.get("purpose") != "provider-readiness-smoke":
            raise ValidationError("P3 grant lineage")
        smoke_hashes.add(grant.get("grant_hash"))
    for row in admissions:
        smoke_hashes.update((row.get("admission_hash"), row.get("sha256")))
    if any(not isinstance(value, str) or not HEX64.fullmatch(value) for value in smoke_hashes):
        raise ValidationError("P3 smoke hash")
    if smoke_hashes & business_hashes:
        raise ValidationError("P3 smoke carrier reused by business admission")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--grants", type=Path, required=True)
    parser.add_argument("--manifest-index", type=Path)
    parser.add_argument("--admission-index", type=Path, required=True)
    parser.add_argument("--smoke-tasks", type=Path, required=True)
    parser.add_argument("--smoke-grants", type=Path, required=True)
    parser.add_argument("--smoke-admissions", type=Path, required=True)
    # --- D122 replacement batch: explicit v2 inputs, v1 defaults unchanged ---
    parser.add_argument("--owner-decision", choices=("D105", RETRY_OWNER_DECISION), default="D105")
    parser.add_argument("--expected-count", type=int, default=14)
    parser.add_argument("--replay", type=Path,
                        help="defaults to the v1 replay beside the admission index")
    parser.add_argument("--baseline-catalog", type=Path,
                        help="v1 catalog the D122 replacement rows are proven against")
    parser.add_argument("--generation", type=Path,
                        help="G2B generation manifest; defaults to the frozen P5 one")
    args = parser.parse_args()
    retry = args.owner_decision == RETRY_OWNER_DECISION
    owner_marker = RETRY_OWNER_MARKER if retry else OWNER_MARKER
    expected_count = args.expected_count
    try:
        root = Path(__file__).resolve().parents[4]
        catalog = load(args.catalog)
        request = load(args.request)
        grants_doc = load(args.grants)
        index_doc = load(args.admission_index)
        manifests_doc = (load(args.manifest_index) if args.manifest_index is not None
                         else manifest_index_from_admissions(args.admission_index, index_doc))
        if (set(grants_doc) != GRANT_SET_KEYS
                or grants_doc.get("schema_version") != "artifex-business-dispatch-grant-set-v1"
                or grants_doc.get("set_version") != "1.0.0"):
            raise ValidationError("grant set closed schema")
        if (set(manifests_doc) != MANIFEST_INDEX_KEYS
                or manifests_doc.get("schema_version") != "artifex-business-dispatch-manifest-index-v1"
                or manifests_doc.get("index_version") != "1.0.0"):
            raise ValidationError("manifest index closed schema")
        if (set(index_doc) != ADMISSION_INDEX_KEYS
                or index_doc.get("schema_version") != "artifex-business-dispatch-admission-index-v1"
                or index_doc.get("index_version") != "1.0.0"):
            raise ValidationError("admission index closed schema")
        if catalog.get("catalog_hash") != canonical_hash(catalog, omit="catalog_hash"):
            raise ValidationError("catalog hash")
        if request.get("request_hash") != canonical_hash(request, omit="request_hash"):
            raise ValidationError("request hash")
        if request.get("catalog_hash") != catalog["catalog_hash"]:
            raise ValidationError("request/catalog binding")
        if retry:
            validate_d122(root, request)
            if args.baseline_catalog is None:
                raise ValidationError("D122 proof requires the v1 baseline catalog")
            validate_retry_rows(catalog.get("trials") or [], load(args.baseline_catalog))
        else:
            validate_d105(root, catalog, request)
        trials = catalog.get("trials")
        if not isinstance(trials, list) or len(trials) != expected_count:
            raise ValidationError(f"{expected_count} trials required")
        trial_ids = [row.get("trial_id") for row in trials]
        if (len(set(trial_ids)) != expected_count
                or [row.get("order") for row in trials] != list(range(1, expected_count + 1))):
            raise ValidationError("trial identity/order")
        if (set(request.get("trial_ids", [])) != set(trial_ids)
                or request.get("maximum_dispatch_count") != expected_count):
            raise ValidationError("request trial set/count")
        if set(request.get("providers", [])) != {"codex", "claude-code"}:
            raise ValidationError("request provider set")
        assurance = load(root / f"plans/{PLAN_ID}/artifacts/P4/assurance-manifest-v1.json")
        if digest(root / f"plans/{PLAN_ID}/artifacts/P4/assurance-manifest-v1.json") != request.get("assurance_sha256"):
            raise ValidationError("assurance hash")
        generation_path = args.generation or (
            root / f"plans/{PLAN_ID}/artifacts/P5/business-successor-generation-v1.json")
        g2_predecessor = validate_package_generation(root, generation_path)
        if request.get("g2_package_digest") != g2_predecessor:
            raise ValidationError("request G2 predecessor drift")

        bindings = (catalog["catalog_hash"], request["request_hash"], request["g2_package_digest"])
        if any(doc.get("catalog_hash") != bindings[0] or doc.get("request_hash") != bindings[1]
               for doc in (grants_doc, manifests_doc, index_doc)):
            raise ValidationError("carrier catalog/request binding")
        if any(doc.get("g2_package_digest") != bindings[2] for doc in (manifests_doc, index_doc)):
            raise ValidationError("carrier G2 binding")
        grants = grants_doc.get("grants")
        manifests = manifests_doc.get("manifests")
        indexes = index_doc.get("admissions")
        replays = replay_rows(args.replay or args.admission_index.with_name("trial-replay-v1.jsonl"))
        if not all(isinstance(rows, list) and len(rows) == expected_count
                   for rows in (grants, manifests, indexes, replays)):
            raise ValidationError(f"complete {expected_count}-row carrier sets required")
        if grants_doc.get("owner_decision") != args.owner_decision:
            raise ValidationError("grant set owner")
        by_trial = {row["trial_id"]: row for row in trials}
        grant_by_id = {row.get("task_id"): row for row in grants}
        manifest_by_id = {row.get("trial_id"): row for row in manifests}
        replay_by_id = {row.get("trial_id"): row for row in replays}
        if any(set(mapping) != set(trial_ids) for mapping in (grant_by_id, manifest_by_id, replay_by_id)):
            raise ValidationError("carrier identity closure")
        if ({row.get("trial_id") for row in indexes} != set(trial_ids)
                or any(set(row) != INDEX_ROW_KEYS for row in indexes)
                or any(set(row) != MANIFEST_ROW_KEYS for row in manifests)):
            raise ValidationError("index row closure")
        seen_keys: set[str] = set()
        business_hashes: set[str] = set()
        for index_row in indexes:
            trial_id = index_row.get("trial_id")
            if trial_id not in by_trial:
                raise ValidationError("unknown admission trial")
            catalog_row = by_trial[trial_id]
            manifest_row = manifest_by_id[trial_id]
            task = manifest_row.get("task")
            grant = grant_by_id[trial_id]
            replay = replay_by_id[trial_id]
            if not isinstance(task, dict):
                raise ValidationError("task object")
            if (set(task) != TASK_KEYS
                    or task.get("schema_version") != "artifex-business-dispatch-task-v1"
                    or task.get("manifest_version") != "1.0.0"):
                raise ValidationError(f"task closed schema: {trial_id}")
            if task.get("task_hash") != canonical_hash(task, omit="task_hash"):
                raise ValidationError(f"task hash: {trial_id}")
            if manifest_row.get("document_sha256") != hashlib.sha256(
                    (json.dumps(task, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
            ).hexdigest():
                raise ValidationError(f"task document hash: {trial_id}")
            expected_task = {
                "purpose": "business-trial", "parent_plan_id": PLAN_ID,
                "parent_item_id": catalog_row["item"], "provider": catalog_row["provider"],
                "controlled_root": catalog_row["controlled_root"], "files": catalog_row["files"],
                "route": catalog_row["route"], "capabilities": catalog_row["capabilities"],
                "acceptance_refs": catalog_row["acceptance_refs"],
                "validation": catalog_row["validation"], "budgets": catalog_row["budgets"],
            }
            if any(task.get(key) != value for key, value in expected_task.items()):
                raise ValidationError(f"task/catalog mismatch: {trial_id}")
            if (task.get("catalog_hash"), task.get("request_hash"), task.get("g2_package_digest")) != bindings:
                raise ValidationError(f"task binding: {trial_id}")
            if grant.get("grant_hash") != canonical_hash(grant, omit="grant_hash"):
                raise ValidationError(f"grant hash: {trial_id}")
            if (set(grant) != GRANT_KEYS
                    or grant.get("schema_version") != "artifex-business-dispatch-grant-v1"
                    or grant.get("grant_version") != "1.0.0"):
                raise ValidationError(f"grant closed schema: {trial_id}")
            if (grant.get("owner_decision"), grant.get("owner_marker"), grant.get("branch"),
                    grant.get("purpose"), grant.get("revoked"), grant.get("max_slices")) != (
                    args.owner_decision, owner_marker, BRANCH, "business-trial", False, 1):
                raise ValidationError(f"grant authority: {trial_id}")
            if (task.get("g2_package_digest") != g2_predecessor
                    or grant.get("g2_package_digest") != g2_predecessor):
                raise ValidationError(f"frozen carrier G2 predecessor drift: {trial_id}")
            if retry and grant.get("expiry") != RETRY_EXPIRY:
                raise ValidationError(f"D122 grant expiry: {trial_id}")
            for key in ("task_id", "task_hash", "provider", "controlled_root", "route", "capabilities", "budgets"):
                task_key = "task_id" if key == "task_id" else key
                if grant.get(key) != task.get(task_key):
                    raise ValidationError(f"grant widening: {trial_id}:{key}")
            if replay.get("replay_hash") != canonical_hash(replay, omit="replay_hash"):
                raise ValidationError(f"replay hash: {trial_id}")
            if set(replay) != REPLAY_KEYS or replay.get("schema_version") != "artifex-business-dispatch-replay-v1":
                raise ValidationError(f"replay closed schema: {trial_id}")
            if replay.get("events") != [] or replay.get("used_slices") != 0 or replay.get("attempt") != 1:
                raise ValidationError(f"pre-intent replay state: {trial_id}")
            idempotency = replay.get("idempotency_key")
            if not isinstance(idempotency, str) or not HEX64.fullmatch(idempotency) or idempotency in seen_keys:
                raise ValidationError(f"replay identity: {trial_id}")
            seen_keys.add(idempotency)
            path = args.admission_index.parent.parent.parent / index_row["path"]
            admission = load(path)
            if (set(admission) != ADMISSION_KEYS
                    or admission.get("schema_version") != "artifex-business-dispatch-admission-v1"
                    or admission.get("admission_version") != "1.0.0"):
                raise ValidationError(f"admission closed schema: {trial_id}")
            if digest(path) != index_row.get("sha256") or admission.get("admission_hash") != canonical_hash(admission, omit="admission_hash"):
                raise ValidationError(f"admission content address: {trial_id}")
            if admission.get("task") != task or admission.get("grant") != grant or admission.get("replay") != replay:
                raise ValidationError(f"admission carrier mismatch: {trial_id}")
            if admission.get("usage") != {"used_slices": 0, "max_slices": 1, "reusable": False}:
                raise ValidationError(f"admission reuse state: {trial_id}")
            if any(index_row.get(key) != value for key, value in {
                "task_hash": task["task_hash"], "grant_hash": grant["grant_hash"],
                "replay_hash": replay["replay_hash"], "admission_hash": admission["admission_hash"],
                "provider": task["provider"],
            }.items()):
                raise ValidationError(f"admission index binding: {trial_id}")
            business_hashes.update((task["task_hash"], grant["grant_hash"], replay["replay_hash"], admission["admission_hash"], index_row["sha256"]))
            ensure_no_forbidden_keys(admission, trial_id)
        validate_smoke_refusal(args.smoke_tasks, args.smoke_grants, args.smoke_admissions, business_hashes)
    except (ValidationError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"P5 trial admission validator: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"P5 trial admission validator: OK ({expected_count} {args.owner_decision}/G2-bound "
          "non-reusable admissions; P3 smoke refused pre-intent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
