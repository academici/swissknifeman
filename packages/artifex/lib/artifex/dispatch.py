"""Pure dispatch-admission projection; no provider is ever touched here."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


HEX64 = re.compile(r"[0-9a-f]{64}\Z")
TASK_KEYS = frozenset(("schema_version", "manifest_version", "task_id", "task_hash", "purpose",
                       "provider", "parent_plan_id", "parent_item_id", "parent_task_contract_hash",
                       "workspace", "permissions", "prompt", "response_schema", "outputs", "budgets",
                       "source_hashes"))
GRANT_KEYS = frozenset(("schema_version", "grant_version", "grant_id", "grant_hash", "owner_decision",
                        "purpose", "task_id", "task_hash", "provider", "route", "capabilities",
                        "workspace", "permissions", "budgets", "max_slices", "revoked"))
BUDGET_KEYS = frozenset(("max_slices", "timeout_ms", "max_envelope_bytes", "max_event_count",
                         "max_turns", "max_output_bytes", "token_limit", "cost_limit_microunits"))
SOURCE_KEYS = frozenset(("plan", "p3_phase", "provider_matrix", "worker_contract", "parity"))
SMOKE_GRANT_DECISION = "D74"
WORKSPACE = {"kind": "temporary-empty-git", "creation": "fresh-per-attempt",
             "preimage": "empty-git-tree", "postimage": "equals-preimage"}


class DispatchRefusal(ValueError):
    """Typed pre-intent refusal for an untrusted admission carrier."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


def canonical_hash(value: dict[str, Any], omitted: str) -> str:
    raw = json.dumps({key: item for key, item in value.items() if key != omitted}, ensure_ascii=False,
                     sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(value: Any, reason: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DispatchRefusal(reason)
    return value


def _hex(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise DispatchRefusal(reason)
    return value


def verify_task(value: Any) -> dict[str, Any]:
    task = _object(value, "UNKNOWN_SCHEMA_VERSION")
    if task.get("schema_version") in {"slice-manifest-v1", "task-contract/v1"}:
        raise DispatchRefusal("PARENT_ITEM_AS_TASK")
    if task.get("schema_version") != "dispatch-task-manifest-v1" or task.get("manifest_version") != "1.0.0":
        raise DispatchRefusal("UNKNOWN_SCHEMA_VERSION")
    if set(task) != TASK_KEYS:
        raise DispatchRefusal("UNKNOWN_FIELD")
    parent_plan = task.get("parent_plan_id")
    if not isinstance(parent_plan, str) or not parent_plan or task.get("parent_item_id") != "P3.4":
        raise DispatchRefusal("PARENT_ITEM_AS_TASK")
    if task.get("purpose") != "provider-readiness-smoke":
        raise DispatchRefusal("PURPOSE_MISMATCH")
    if not isinstance(task.get("task_id"), str) or not task["task_id"] or not isinstance(task.get("provider"), str) or not task["provider"]:
        raise DispatchRefusal("PROVIDER_MISMATCH")
    if task.get("workspace") != WORKSPACE:
        raise DispatchRefusal("WORKSPACE_NOT_TEMPORARY_EMPTY")
    permissions = task.get("permissions")
    if not isinstance(permissions, dict) or set(permissions) != {"reads", "writes", "tools"}:
        raise DispatchRefusal("UNKNOWN_FIELD")
    if any(permissions[key] != [] for key in ("reads", "writes", "tools")):
        raise DispatchRefusal("SCOPE_NOT_EMPTY")
    budgets = task.get("budgets")
    if (not isinstance(budgets, dict) or set(budgets) != BUDGET_KEYS or budgets.get("max_slices") != 1
            or any(isinstance(row, bool) or not isinstance(row, int) or row <= 0 for row in budgets.values())):
        raise DispatchRefusal("CAP_INVALID")
    sources = task.get("source_hashes")
    if (not isinstance(sources, dict) or set(sources) != SOURCE_KEYS
            or any(not isinstance(row, str) or not HEX64.fullmatch(row) for row in sources.values())):
        raise DispatchRefusal("SOURCE_HASH_MISMATCH")
    if task.get("task_hash") != canonical_hash(task, "task_hash"):
        raise DispatchRefusal("TASK_HASH_MISMATCH")
    return task


def verify_grant(value: Any, task: dict[str, Any]) -> dict[str, Any]:
    grant = _object(value, "UNKNOWN_SCHEMA_VERSION")
    if grant.get("schema_version") != "dispatch-grant-v1" or grant.get("grant_version") != "1.0.0":
        raise DispatchRefusal("UNKNOWN_SCHEMA_VERSION")
    if set(grant) != GRANT_KEYS:
        raise DispatchRefusal("UNKNOWN_FIELD")
    if grant.get("grant_hash") != canonical_hash(grant, "grant_hash"):
        raise DispatchRefusal("GRANT_HASH_MISMATCH")
    if grant.get("revoked") is not False:
        raise DispatchRefusal("GRANT_REVOKED")
    if grant.get("owner_decision") != SMOKE_GRANT_DECISION or grant.get("purpose") != task["purpose"]:
        raise DispatchRefusal("GRANT_SCOPE_MISMATCH")
    for key in ("task_id", "task_hash", "provider", "workspace", "permissions", "budgets"):
        if grant.get(key) != task.get(key):
            raise DispatchRefusal("GRANT_SCOPE_MISMATCH")
    if grant.get("max_slices") != 1 or grant.get("route") != {"model_class": "implementation", "effort": "high"}:
        raise DispatchRefusal("GRANT_SCOPE_MISMATCH")
    if not isinstance(grant.get("capabilities"), list) or not grant["capabilities"]:
        raise DispatchRefusal("GRANT_SCOPE_MISMATCH")
    return grant


def strict_replay(rows: Any, task: dict[str, Any], grant: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rows, list):
        raise DispatchRefusal("REPLAY_INVALID")
    used, seen = 0, set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"event", "grant_id", "task_id", "idempotency_key"}:
            raise DispatchRefusal("REPLAY_INVALID")
        if row.get("event") != "dispatch_intent":
            raise DispatchRefusal("REPLAY_INVALID")
        key = _hex(row.get("idempotency_key"), "REPLAY_INVALID")
        if key in seen:
            raise DispatchRefusal("REPLAY_INVALID")
        seen.add(key)
        if row.get("grant_id") == grant["grant_id"] and row.get("task_id") == task["task_id"]:
            used += 1
    key = _hex(identity.get("idempotency_key"), "IDENTITY_MISMATCH")
    if key in seen or used >= grant["max_slices"]:
        raise DispatchRefusal("USAGE_LIMIT_EXCEEDED")
    return {"schema_version": "dispatch-usage-v1", "used_slices": used,
            "replay_event_count": len(rows), "replay_identity_hash": hashlib.sha256(
                json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()}


def project(task_value: Any, grant_value: Any, replay_rows: Any, *, run_id: str, slice_id: str,
            attempt: int, idempotency_key: str) -> dict[str, Any]:
    task, grant = verify_task(task_value), verify_grant(grant_value, verify_task(task_value))
    if not all(isinstance(value, str) and value for value in (run_id, slice_id)) or not isinstance(attempt, int) or attempt < 1:
        raise DispatchRefusal("IDENTITY_MISMATCH")
    identity = {"run_id": run_id, "slice_id": slice_id, "attempt": attempt, "idempotency_key": idempotency_key}
    _hex(idempotency_key, "IDENTITY_MISMATCH")
    usage = strict_replay(replay_rows, task, grant, identity)
    dispatch = {"purpose": task["purpose"], "provider": task["provider"], "task_id": task["task_id"],
                "task_hash": task["task_hash"], "grant_id": grant["grant_id"], "grant_hash": grant["grant_hash"],
                **identity, "source_hashes": task["source_hashes"]}
    manifest = {"schema_version": "dispatch-runtime-manifest-v1", "manifest_version": "1.0.0",
                "manifest_hash": "", "task": task, "grant": grant, "dispatch": dispatch,
                "usage": usage}
    manifest["manifest_hash"] = canonical_hash(manifest, "manifest_hash")
    admission = {"schema_version": "dispatch-admission-v1", "admission_version": "1.0.0",
                 "admission_hash": "", "manifest_hash": manifest["manifest_hash"], "task": task,
                 "grant": grant, "dispatch": dispatch, "usage": usage}
    admission["admission_hash"] = canonical_hash(admission, "admission_hash")
    return {"manifest": manifest, "admission": admission}


def verify_admission(value: Any) -> dict[str, Any]:
    admission = _object(value, "UNKNOWN_SCHEMA_VERSION")
    required = {"schema_version", "admission_version", "admission_hash", "manifest_hash", "task", "grant", "dispatch", "usage"}
    if admission.get("schema_version") != "dispatch-admission-v1" or admission.get("admission_version") != "1.0.0":
        raise DispatchRefusal("UNKNOWN_SCHEMA_VERSION")
    if set(admission) != required:
        raise DispatchRefusal("UNKNOWN_FIELD")
    if admission.get("admission_hash") != canonical_hash(admission, "admission_hash"):
        raise DispatchRefusal("ADMISSION_HASH_MISMATCH")
    task = verify_task(admission["task"])
    grant = verify_grant(admission["grant"], task)
    dispatch = _object(admission["dispatch"], "UNKNOWN_FIELD")
    if set(dispatch) != {"purpose", "provider", "task_id", "task_hash", "grant_id", "grant_hash", "run_id", "slice_id", "attempt", "idempotency_key", "source_hashes"}:
        raise DispatchRefusal("UNKNOWN_FIELD")
    for key in ("purpose", "provider", "task_id", "task_hash"):
        if dispatch.get(key) != task.get(key):
            raise DispatchRefusal("IDENTITY_MISMATCH")
    if dispatch.get("grant_id") != grant["grant_id"] or dispatch.get("grant_hash") != grant["grant_hash"]:
        raise DispatchRefusal("GRANT_NOT_FOUND")
    if dispatch.get("source_hashes") != task["source_hashes"]:
        raise DispatchRefusal("SOURCE_HASH_MISMATCH")
    usage = _object(admission["usage"], "REPLAY_INVALID")
    if set(usage) != {"schema_version", "used_slices", "replay_event_count", "replay_identity_hash"} or usage.get("schema_version") != "dispatch-usage-v1":
        raise DispatchRefusal("REPLAY_INVALID")
    if usage.get("used_slices") != 0 or usage.get("replay_event_count") != 0 or not HEX64.fullmatch(str(usage.get("replay_identity_hash"))):
        raise DispatchRefusal("REPLAY_INVALID")
    expected = {"task": task, "grant": grant, "dispatch": dispatch, "usage": usage,
                "schema_version": "dispatch-runtime-manifest-v1", "manifest_version": "1.0.0", "manifest_hash": ""}
    expected["manifest_hash"] = canonical_hash(expected, "manifest_hash")
    if admission.get("manifest_hash") != expected["manifest_hash"]:
        raise DispatchRefusal("ADMISSION_HASH_MISMATCH")
    return admission


def load_indexed_admission(plan_dir: Path, admission_path: Path) -> dict[str, Any]:
    root = plan_dir.resolve()
    try:
        candidate = admission_path.resolve(strict=True)
        candidate.relative_to(root)
        if candidate.is_symlink() or not candidate.is_file():
            raise OSError("unsafe admission")
        index_path = root / "artifacts/P2/p3-smoke-admission-index-v1.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        admission = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise DispatchRefusal("ADMISSION_NOT_INDEXED") from exc
    if set(index) != {"schema_version", "index_version", "admissions"} or index.get("schema_version") != "p3-smoke-admission-index-v1" or index.get("index_version") != "1.0.0":
        raise DispatchRefusal("ADMISSION_NOT_INDEXED")
    verified = verify_admission(admission)
    relative = candidate.relative_to(root).as_posix()
    rows = index.get("admissions")
    if not isinstance(rows, list) or len(rows) != 2:
        raise DispatchRefusal("ADMISSION_NOT_INDEXED")
    matching = [row for row in rows if isinstance(row, dict) and row.get("path") == relative]
    if len(matching) != 1 or matching[0].get("task_id") != verified["task"]["task_id"] or matching[0].get("provider") != verified["task"]["provider"] or matching[0].get("sha256") != file_hash(candidate):
        raise DispatchRefusal("ADMISSION_NOT_INDEXED")
    return verified


def scheduler_slice(admission: dict[str, Any], authority_input: dict[str, Any]) -> dict[str, Any]:
    verified = verify_admission(admission)
    dispatch = verified["dispatch"]
    return {"slice_id": dispatch["slice_id"], "attempt": dispatch["attempt"],
            "idempotency_key": dispatch["idempotency_key"], "dependencies": [], "read_only": True,
            "worktree_isolated": True, "budget": {"attempts": 1, "tokens": verified["task"]["budgets"]["token_limit"],
            "cost": verified["task"]["budgets"]["cost_limit_microunits"], "duration": verified["task"]["budgets"]["timeout_ms"],
            "turns": verified["task"]["budgets"]["max_turns"]}, "used": {"attempts": 0, "tokens": 0, "cost": 0, "duration": 0, "turns": 0},
            "input_hashes": {"admission": verified["admission_hash"], "manifest": verified["manifest_hash"]},
            "authority_input": authority_input}
