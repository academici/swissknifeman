#!/usr/bin/env python3
"""Validate frozen, data-only Artifex provider parity evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


PROVIDERS = {"codex", "claude-code"}
STATES = {"equivalent", "degraded", "unsupported", "unknown"}
CAPABILITIES = {"structured_output", "machine_events", "permission_boundary", "ephemeral_session", "child_agent_control"}
EXITS = {"success", "schema_failure", "permission_denied", "timeout", "quota_exhausted", "budget_exhausted", "capability_unsupported", "provider_failure", "internal_failure", "orphaned"}
FIELDS = {
    "bundle.authority_policy_hash", "bundle.content_refs", "bundle.output_schema_hash", "bundle.slice_manifest_hash", "bundle.task_contract_hash", "bundle.validation_hash",
    "budgets.cost_limit_microunits", "budgets.cost_limit_unknown_reason", "budgets.max_envelope_bytes", "budgets.max_event_count", "budgets.max_output_bytes", "budgets.max_turns", "budgets.timeout_ms", "budgets.token_limit", "budgets.token_limit_unknown_reason",
    "child_policy.allowed_capabilities", "child_policy.max_children", "child_policy.mode", "event.acceptance_state", "event.diagnostic", "event.identity", "event.provider_event_type", "event.sequence", "event.turn_index", "event.usage", "event.worker_event_type",
    "permissions.approval_mode", "permissions.authority_profile", "permissions.filesystem_scope_hash", "permissions.network_mode", "permissions.sandbox_mode", "permissions.source",
    "provider.cli_version", "provider.degraded_route_grant_hash", "provider.id", "provider.mapping_id", "provider.mapping_state", "provider.mapping_version", "redaction_policy_hash",
    "request.attempt", "request.created_at", "request.idempotency_key", "request.request_id", "request.run_id", "request.schema_version", "request.slice_id", "request.trace_id",
    "result.acceptance_state", "result.diagnostic_codes", "result.duration_ms", "result.event_count", "result.exit_class", "result.output", "result.reason_code", "result.redaction", "result.turn_count", "result.usage", "result.worker_succeeded", "route.capabilities", "route.effort", "route.model", "route.model_class",
}


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ids(rows: object, expected: set[str], label: str) -> None:
    if not isinstance(rows, list) or {row.get("id") for row in rows if isinstance(row, dict)} != expected:
        raise ValueError(f"{label}: coverage is not exact")
    for row in rows:
        providers = row.get("providers")
        if not isinstance(providers, dict) or set(providers) != PROVIDERS:
            raise ValueError(f"{label}/{row['id']}: each provider needs one exact mapping")
        for mapping in providers.values():
            if not isinstance(mapping, dict) or set(mapping) != {"status", "reason", "evidence"}:
                raise ValueError(f"{label}/{row['id']}: mapping shape is open")
            if mapping["status"] not in STATES or not all(isinstance(mapping[key], str) and mapping[key] for key in ("reason", "evidence")):
                raise ValueError(f"{label}/{row['id']}: invalid status or provenance")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--worker-contract", type=Path, required=True)
    parser.add_argument("--providers", type=Path, required=True)
    args = parser.parse_args()
    try:
        matrix, cases, provider_matrix = load(args.matrix), load(args.cases), load(args.providers)
        if set(matrix) != {"schema_version", "contract_version", "sources", "registry", "fields", "capabilities", "exits"}:
            raise ValueError("matrix shape is open")
        if matrix["schema_version"] != "provider-parity-v1" or matrix["contract_version"] != "1.0.0":
            raise ValueError("matrix version mismatch")
        repo = Path(__file__).resolve().parents[4]
        expected_hashes = {
            "worker_contract_sha256": digest(args.worker_contract),
            "provider_matrix_sha256": digest(args.providers),
            "routing_sha256": digest(repo / "packages/task/configs/command-routing.json"),
            "provider_capabilities_sha256": digest(repo / "configs/provider-capabilities.json"),
            "profile_catalog_sha256": digest(repo / "packages/harness/configs/common/profile-catalog.json"),
        }
        if not isinstance(matrix["sources"], dict) or any(matrix["sources"].get(key) != value for key, value in expected_hashes.items()):
            raise ValueError("matrix source hash mismatch")
        registry = matrix["registry"]
        if not isinstance(registry, list) or {(row.get("provider"), row.get("adapter")) for row in registry if isinstance(row, dict)} != {("codex", "artifex.providers.codex"), ("claude-code", "artifex.providers.claude_code")}:
            raise ValueError("registry is not exact")
        ids(matrix["fields"], FIELDS, "fields")
        ids(matrix["capabilities"], CAPABILITIES, "capabilities")
        ids(matrix["exits"], EXITS, "exits")
        declared = re.search(r"<!-- declared-set: exit_classes -->\s*```text\n(.*?)\n```", args.worker_contract.read_text(encoding="utf-8"), re.DOTALL)
        if not declared or set(declared.group(1).split()) != EXITS:
            raise ValueError("worker contract exit set diverges")
        if {row.get("provider") for row in provider_matrix.get("providers", []) if isinstance(row, dict)} != PROVIDERS:
            raise ValueError("provider matrix does not contain exactly both providers")
        if set(cases) != {"schema_version", "contract_version", "cases"} or cases["schema_version"] != "provider-parity-cases-v1":
            raise ValueError("case bank version or shape mismatch")
        case_rows = cases["cases"]
        if not isinstance(case_rows, list) or {row.get("provider") for row in case_rows if isinstance(row, dict)} != PROVIDERS:
            raise ValueError("case bank needs independently authored rows for both providers")
        if any(not isinstance(row.get("expected", {}).get("reason_code"), str) for row in case_rows):
            raise ValueError("case bank lacks closed expected reasons")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"provider-parity: RED — {error}", file=sys.stderr)
        return 1
    print(f"provider-parity: OK — {len(FIELDS)} fields, {len(CAPABILITIES)} capabilities, {len(EXITS)} exits; exact two-provider mappings and source hashes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
