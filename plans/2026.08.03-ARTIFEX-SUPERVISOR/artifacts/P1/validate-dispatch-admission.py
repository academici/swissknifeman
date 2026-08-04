#!/usr/bin/env python3
"""Validate dispatch-admission-v1 and the two D74 P3 smoke carriers."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


TASK_KEYS = {
    "schema_version", "manifest_version", "task_id", "task_hash", "purpose",
    "provider", "parent_plan_id", "parent_item_id", "parent_task_contract_hash",
    "workspace", "permissions", "prompt", "response_schema", "outputs", "budgets",
    "source_hashes",
}
GRANT_KEYS = {
    "schema_version", "grant_version", "grant_id", "grant_hash", "owner_decision",
    "purpose", "task_id", "task_hash", "provider", "route", "capabilities",
    "workspace", "permissions", "budgets", "max_slices", "revoked",
}
DISPATCH_KEYS = {
    "purpose", "provider", "task_id", "task_hash", "grant_id", "grant_hash",
    "run_id", "slice_id", "attempt", "idempotency_key", "source_hashes",
}
BUDGET_KEYS = {
    "max_slices", "timeout_ms", "max_envelope_bytes", "max_event_count", "max_turns",
    "max_output_bytes", "token_limit", "cost_limit_microunits",
}
SOURCE_KEYS = {"plan", "p3_phase", "provider_matrix", "worker_contract", "parity"}
OUTPUTS = [
    "provider_id", "binary_version_hash", "exit_class", "reason_code", "schema_valid",
    "project_delta", "duration_ms",
]
WORKSPACE = {
    "kind": "temporary-empty-git", "creation": "fresh-per-attempt",
    "preimage": "empty-git-tree", "postimage": "equals-preimage",
}
PROVIDER_TASKS = {
    "codex": "p3-smoke-codex-v1",
    "claude-code": "p3-smoke-claude-code-v1",
}
CAPABILITIES = {
    "codex": ["structured_output", "machine_events", "permission_boundary", "ephemeral_session"],
    "claude-code": ["structured_output", "machine_events", "permission_boundary"],
}
PROMPT = {
    "id": "artifex-provider-readiness-smoke-v1",
    "content_hash": "2868254fddba1e36e830631ae1e944ee18872a7ad3a3dfd2e8fc687b27f390fd",
}
RESPONSE_SCHEMA = {
    "id": "artifex-readiness-result-v1",
    "content_hash": "990901a4d25beb01bf84ae951e5ee5bb7431a5e8d8172f967cb2801c3f35fe5d",
}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
DECLARED_RE = re.compile(
    r"<!-- declared-set: (?P<name>[a-z_]+) -->\s*```text\n(?P<body>.*?)\n```",
    re.DOTALL,
)


class AdmissionError(ValueError):
    pass


def canonical_hash(value: dict[str, Any], omitted: str) -> str:
    body = {key: item for key, item in value.items() if key != omitted}
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdmissionError(f"{label}: invalid JSON") from exc
    if not isinstance(value, dict):
        raise AdmissionError(f"{label}: object required")
    return value


def declared_sets(text: str) -> dict[str, tuple[str, ...]]:
    return {
        match["name"]: tuple(line.strip() for line in match["body"].splitlines() if line.strip())
        for match in DECLARED_RE.finditer(text)
    }


def task_reason(task: Any, parent_contract_hash: str) -> str:
    if not isinstance(task, dict):
        return "UNKNOWN_SCHEMA_VERSION"
    if task.get("schema_version") in {"slice-manifest-v1", "task-contract/v1"}:
        return "PARENT_ITEM_AS_TASK"
    if task.get("schema_version") != "dispatch-task-manifest-v1" or task.get("manifest_version") != "1.0.0":
        return "UNKNOWN_SCHEMA_VERSION"
    if set(task) != TASK_KEYS:
        return "UNKNOWN_FIELD"
    if task.get("parent_plan_id") != "2026.08.03-ARTIFEX-SUPERVISOR" or task.get("parent_item_id") != "P3.4":
        return "PARENT_ITEM_AS_TASK"
    if task.get("parent_task_contract_hash") != parent_contract_hash or task.get("task_hash") == parent_contract_hash:
        return "PARENT_ITEM_AS_TASK"
    if task.get("purpose") != "provider-readiness-smoke":
        return "PURPOSE_MISMATCH"
    provider = task.get("provider")
    if provider not in PROVIDER_TASKS or task.get("task_id") != PROVIDER_TASKS[provider]:
        return "PROVIDER_MISMATCH"
    if task.get("workspace") != WORKSPACE:
        return "WORKSPACE_NOT_TEMPORARY_EMPTY"
    permissions = task.get("permissions")
    if not isinstance(permissions, dict) or set(permissions) != {"reads", "writes", "tools"}:
        return "UNKNOWN_FIELD"
    if any(permissions[key] != [] for key in ("reads", "writes", "tools")):
        return "SCOPE_NOT_EMPTY"
    if task.get("prompt") != PROMPT:
        return "PROMPT_MISMATCH"
    if task.get("response_schema") != RESPONSE_SCHEMA:
        return "SCHEMA_MISMATCH"
    if task.get("outputs") != OUTPUTS:
        return "OUTPUTS_MISMATCH"
    budgets = task.get("budgets")
    if (not isinstance(budgets, dict) or set(budgets) != BUDGET_KEYS
            or budgets.get("max_slices") != 1
            or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in budgets.values())):
        return "CAP_INVALID"
    sources = task.get("source_hashes")
    if (not isinstance(sources, dict) or set(sources) != SOURCE_KEYS
            or any(not isinstance(value, str) or not HEX64.fullmatch(value) for value in sources.values())):
        return "SOURCE_HASH_MISMATCH"
    if task.get("task_hash") != canonical_hash(task, "task_hash"):
        return "TASK_HASH_MISMATCH"
    return "allow"


def grant_reason(grant: Any, task: dict[str, Any]) -> str:
    if not isinstance(grant, dict) or grant.get("schema_version") != "dispatch-grant-v1" or grant.get("grant_version") != "1.0.0":
        return "UNKNOWN_SCHEMA_VERSION"
    if set(grant) != GRANT_KEYS:
        return "UNKNOWN_FIELD"
    if grant.get("grant_hash") != canonical_hash(grant, "grant_hash"):
        return "GRANT_HASH_MISMATCH"
    if grant.get("revoked") is not False:
        return "GRANT_REVOKED"
    if grant.get("owner_decision") != "D74":
        return "GRANT_SCOPE_MISMATCH"
    if grant.get("purpose") != "provider-readiness-smoke":
        return "PURPOSE_MISMATCH"
    provider = task["provider"]
    if grant.get("provider") != provider:
        return "PROVIDER_MISMATCH"
    if grant.get("task_id") != task["task_id"] or grant.get("task_hash") != task["task_hash"]:
        return "GRANT_SCOPE_MISMATCH"
    if grant.get("route") != {"model_class": "implementation", "effort": "high"}:
        return "GRANT_SCOPE_MISMATCH"
    if grant.get("capabilities") != CAPABILITIES[provider]:
        return "GRANT_SCOPE_MISMATCH"
    if (grant.get("workspace") != task["workspace"] or grant.get("permissions") != task["permissions"]
            or grant.get("budgets") != task["budgets"] or grant.get("max_slices") != 1):
        return "GRANT_SCOPE_MISMATCH"
    return "allow"


def evaluate(value: Any, parent_contract_hash: str) -> str:
    if not isinstance(value, dict) or value.get("schema_version") != "dispatch-admission-input-v1":
        return "UNKNOWN_SCHEMA_VERSION"
    if "usage" in value:
        return "USAGE_CALLER_SUPPLIED"
    if set(value) != {"schema_version", "task", "grant", "dispatch", "replay"}:
        return "UNKNOWN_FIELD"
    task = value["task"]
    reason = task_reason(task, parent_contract_hash)
    if reason != "allow":
        return reason
    grant = value["grant"]
    reason = grant_reason(grant, task)
    if reason != "allow":
        return reason
    dispatch = value["dispatch"]
    if not isinstance(dispatch, dict) or set(dispatch) != DISPATCH_KEYS:
        return "UNKNOWN_FIELD"
    if dispatch.get("purpose") == "business-trial":
        return "BUSINESS_AUTHORITY_REQUIRED"
    if dispatch.get("purpose") != task["purpose"]:
        return "PURPOSE_MISMATCH"
    if dispatch.get("task_hash") == parent_contract_hash:
        return "PARENT_ITEM_AS_TASK"
    if dispatch.get("provider") != task["provider"]:
        return "PROVIDER_MISMATCH"
    if dispatch.get("task_id") != task["task_id"] or dispatch.get("task_hash") != task["task_hash"]:
        return "IDENTITY_MISMATCH"
    if dispatch.get("grant_id") != grant["grant_id"] or dispatch.get("grant_hash") != grant["grant_hash"]:
        return "GRANT_NOT_FOUND"
    if dispatch.get("source_hashes") != task["source_hashes"]:
        return "SOURCE_HASH_MISMATCH"
    if (not isinstance(dispatch.get("run_id"), str) or not dispatch["run_id"]
            or not isinstance(dispatch.get("slice_id"), str) or not dispatch["slice_id"]
            or isinstance(dispatch.get("attempt"), bool) or not isinstance(dispatch.get("attempt"), int)
            or dispatch["attempt"] < 1 or not isinstance(dispatch.get("idempotency_key"), str)
            or not HEX64.fullmatch(dispatch["idempotency_key"])):
        return "IDENTITY_MISMATCH"
    replay = value["replay"]
    if not isinstance(replay, dict) or set(replay) != {"schema_version", "events"} or replay.get("schema_version") != "dispatch-replay-v1" or not isinstance(replay.get("events"), list):
        return "REPLAY_INVALID"
    used = 0
    seen: set[str] = set()
    for event in replay["events"]:
        if (not isinstance(event, dict) or set(event) != {"event", "grant_id", "task_id", "idempotency_key"}
                or event.get("event") != "dispatch_intent" or not isinstance(event.get("idempotency_key"), str)
                or not HEX64.fullmatch(event["idempotency_key"]) or event["idempotency_key"] in seen):
            return "REPLAY_INVALID"
        seen.add(event["idempotency_key"])
        if event["grant_id"] == grant["grant_id"] and event["task_id"] == task["task_id"]:
            used += 1
    if dispatch["idempotency_key"] in seen or used >= grant["max_slices"]:
        return "USAGE_LIMIT_EXCEEDED"
    return "allow"


def mutate(base: dict[str, Any], mutations: list[dict[str, Any]]) -> dict[str, Any]:
    value = copy.deepcopy(base)
    for mutation in mutations:
        parts = [part for part in mutation.get("path", "").split("/") if part]
        if not parts:
            raise AdmissionError("case mutation path is empty")
        target: Any = value
        for part in parts[:-1]:
            target = target[int(part)] if isinstance(target, list) else target[part]
        final: Any = int(parts[-1]) if isinstance(target, list) else parts[-1]
        operation = mutation.get("op")
        if operation in {"set", "add"}:
            if isinstance(target, list) and operation == "add":
                target.insert(final, copy.deepcopy(mutation.get("value")))
            else:
                target[final] = copy.deepcopy(mutation.get("value"))
        elif operation == "remove":
            target.pop(final)
        else:
            raise AdmissionError(f"unsupported mutation operation: {operation}")
    return value


def built_p34_hash(p3_phase: Path) -> str:
    plan_dir = p3_phase.parent.parent
    root = plan_dir.parent.parent
    task_lib = root / "packages/task/lib"
    if not task_lib.is_dir():
        raise AdmissionError("task contract compiler unavailable")
    sys.path.insert(0, str(task_lib))
    from task import task_contract  # pylint: disable=import-outside-toplevel
    contract = task_contract.build(str(plan_dir), "P3.4")
    value = contract.get("version", {}).get("content_hash")
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise AdmissionError("P3.4 Task Contract hash unavailable")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--smoke-tasks", required=True, type=Path)
    parser.add_argument("--smoke-grants", required=True, type=Path)
    parser.add_argument("--p3-phase", required=True, type=Path)
    args = parser.parse_args()
    try:
        contract_text = args.contract.read_text(encoding="utf-8")
        sets = declared_sets(contract_text)
        if set(sets.get("task_keys", ())) != TASK_KEYS or len(sets.get("task_keys", ())) != len(TASK_KEYS):
            raise AdmissionError("contract task key declaration drift")
        if set(sets.get("grant_keys", ())) != GRANT_KEYS or len(sets.get("grant_keys", ())) != len(GRANT_KEYS):
            raise AdmissionError("contract grant key declaration drift")
        required_refusals = {
            "TASK_HASH_MISMATCH", "PARENT_ITEM_AS_TASK", "PURPOSE_MISMATCH",
            "PROVIDER_MISMATCH", "WORKSPACE_NOT_TEMPORARY_EMPTY", "SCOPE_NOT_EMPTY",
            "SCHEMA_MISMATCH", "OUTPUTS_MISMATCH", "CAP_INVALID", "GRANT_NOT_FOUND",
            "GRANT_HASH_MISMATCH", "REPLAY_INVALID", "USAGE_CALLER_SUPPLIED",
            "USAGE_LIMIT_EXCEEDED", "BUSINESS_AUTHORITY_REQUIRED",
        }
        if not required_refusals.issubset(set(sets.get("refusal_reasons", ()))):
            raise AdmissionError("contract refusal declaration incomplete")

        parent_hash = built_p34_hash(args.p3_phase)
        tasks_doc = load_json(args.smoke_tasks, "smoke tasks")
        grants_doc = load_json(args.smoke_grants, "smoke grants")
        if set(tasks_doc) != {"schema_version", "set_version", "tasks"} or tasks_doc.get("schema_version") != "dispatch-task-set-v1" or tasks_doc.get("set_version") != "1.0.0":
            raise AdmissionError("task set shape/version")
        if set(grants_doc) != {"schema_version", "set_version", "grants"} or grants_doc.get("schema_version") != "dispatch-grant-set-v1" or grants_doc.get("set_version") != "1.0.0":
            raise AdmissionError("grant set shape/version")
        tasks = tasks_doc.get("tasks")
        grants = grants_doc.get("grants")
        if not isinstance(tasks, list) or len(tasks) != 2 or not isinstance(grants, list) or len(grants) != 2:
            raise AdmissionError("exactly two tasks and grants required")
        by_provider: dict[str, dict[str, Any]] = {}
        for task in tasks:
            reason = task_reason(task, parent_hash)
            if reason != "allow":
                raise AdmissionError(f"task {task.get('task_id')}: {reason}")
            if task["provider"] in by_provider:
                raise AdmissionError("duplicate task provider")
            by_provider[task["provider"]] = task
        if set(by_provider) != set(PROVIDER_TASKS):
            raise AdmissionError("task provider set mismatch")
        grant_providers: set[str] = set()
        for grant in grants:
            provider = grant.get("provider")
            if provider not in by_provider:
                raise AdmissionError("grant provider unknown")
            reason = grant_reason(grant, by_provider[provider])
            if reason != "allow":
                raise AdmissionError(f"grant {grant.get('grant_id')}: {reason}")
            grant_providers.add(provider)
        if grant_providers != set(PROVIDER_TASKS):
            raise AdmissionError("grant provider set mismatch")

        cases_doc = load_json(args.cases, "cases")
        if cases_doc.get("schema_version") != "dispatch-admission-cases-v1" or cases_doc.get("contract_version") != "1.0.0":
            raise AdmissionError("case bank identity/version")
        cases = cases_doc.get("cases")
        if not isinstance(cases, list) or not cases:
            raise AdmissionError("case bank empty")
        seen_ids: set[str] = set()
        for case in cases:
            if not isinstance(case, dict) or set(case) != {"id", "mutations", "expected"}:
                raise AdmissionError("case shape")
            if case["id"] in seen_ids:
                raise AdmissionError("duplicate case ID")
            seen_ids.add(case["id"])
            actual = evaluate(mutate(cases_doc["base_input"], case["mutations"]), parent_hash)
            if actual != case["expected"]:
                raise AdmissionError(f"{case['id']}: expected {case['expected']}, got {actual}")
        base_task = cases_doc["base_input"]["task"]
        base_grant = cases_doc["base_input"]["grant"]
        if base_task != by_provider["codex"]:
            raise AdmissionError("case base task drift")
        codex_grant = next(row for row in grants if row["provider"] == "codex")
        if base_grant != codex_grant:
            raise AdmissionError("case base grant drift")
    except (AdmissionError, OSError, UnicodeDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"dispatch-admission: FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "dispatch-admission: OK "
        f"({len(tasks)} tasks; {len(grants)} grants; {len(cases)} independent cases; "
        "P3.4 Task Contract rejected as task carrier)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
