"""Closed D108 business-admission projection; it never mutates D105 carriers.

The business format is deliberately separate from :mod:`artifex.dispatch`: the
former is a read-only projection of the owner-frozen D105 evidence, while the
latter remains the immutable P3 smoke boundary.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
HEX64 = frozenset("0123456789abcdef")
INDEX_KEYS = frozenset(("schema_version", "index_version", "catalog_hash", "request_hash", "g2_package_digest", "admissions"))
INDEX_ROW_KEYS = frozenset(("trial_id", "provider", "path", "sha256", "admission_hash", "task_hash", "grant_hash", "replay_hash"))
ADMISSION_KEYS = frozenset(("schema_version", "admission_version", "purpose", "trial_id", "task", "grant", "replay", "usage", "admission_hash"))
TASK_KEYS = frozenset(("schema_version", "manifest_version", "task_id", "task_hash", "purpose", "parent_plan_id", "parent_item_id", "catalog_hash", "request_hash", "g2_package_digest", "provider", "repository", "controlled_root", "base_commit", "files", "route", "capabilities", "acceptance_refs", "validation", "budgets"))
GRANT_KEYS = frozenset(("schema_version", "grant_version", "grant_id", "grant_hash", "owner_decision", "owner_marker", "branch", "purpose", "task_id", "task_hash", "catalog_hash", "request_hash", "g2_package_digest", "provider", "controlled_root", "route", "capabilities", "budgets", "max_slices", "expiry", "revoked"))
REPLAY_KEYS = frozenset(("schema_version", "trial_id", "task_id", "grant_id", "run_id", "slice_id", "attempt", "idempotency_key", "events", "used_slices", "replay_hash"))


class BusinessRefusal(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _hash(value: Any, omitted: str) -> str:
    return hashlib.sha256(json.dumps({k: v for k, v in value.items() if k != omitted}, ensure_ascii=False,
                                     sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def _same_path(root: Path, candidate: Path) -> str:
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise BusinessRefusal("ADMISSION_PATH_EXTERNAL") from exc
    if resolved.is_symlink() or not resolved.is_file():
        raise BusinessRefusal("ADMISSION_NOT_INDEXED")
    return relative.as_posix()


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BusinessRefusal("ADMISSION_NOT_INDEXED") from exc


def load_indexed(plan_dir: Path, admission_path: Path, *, g2_digest: str, g2b_digest: str) -> dict[str, Any]:
    """Recompute the index/hash link and accept an unused D105 admission only."""
    root = plan_dir.resolve()
    relative = _same_path(root, admission_path)
    candidate = root / relative
    value = _load(candidate)
    index = _load(root / "artifacts/P5/trial-admission-index-v1.json")
    if (not isinstance(index, dict) or set(index) != INDEX_KEYS
            or index.get("schema_version") != "artifex-business-dispatch-admission-index-v1"
            or index.get("index_version") != "1.0.0" or not isinstance(index.get("admissions"), list)
            or len(index["admissions"]) != 14):
        raise BusinessRefusal("ADMISSION_NOT_INDEXED")
    if (not isinstance(value, dict) or set(value) != ADMISSION_KEYS
            or value.get("schema_version") != "artifex-business-dispatch-admission-v1"
            or value.get("admission_version") != "1.0.0" or value.get("admission_hash") != _hash(value, "admission_hash")):
        raise BusinessRefusal("UNKNOWN_SCHEMA_VERSION")
    rows = [r for r in index["admissions"] if isinstance(r, dict) and set(r) == INDEX_ROW_KEYS and r.get("path") == relative]
    if len(rows) != 1 or rows[0].get("sha256") != hashlib.sha256(candidate.read_bytes()).hexdigest():
        raise BusinessRefusal("ADMISSION_NOT_INDEXED")
    task, grant, replay, usage = (value.get(k) for k in ("task", "grant", "replay", "usage"))
    if (not all(isinstance(v, dict) for v in (task, grant, replay, usage)) or value.get("purpose") != "business-trial"
            or set(task) != TASK_KEYS or set(grant) != GRANT_KEYS or set(replay) != REPLAY_KEYS
            or task.get("schema_version") != "artifex-business-dispatch-task-v1" or task.get("manifest_version") != "1.0.0"
            or grant.get("schema_version") != "artifex-business-dispatch-grant-v1" or grant.get("grant_version") != "1.0.0"
            or replay.get("schema_version") != "artifex-business-dispatch-replay-v1"):
        raise BusinessRefusal("ADMISSION_INVALID")
    if (task.get("task_hash") != _hash(task, "task_hash") or grant.get("grant_hash") != _hash(grant, "grant_hash")
            or replay.get("replay_hash") != _hash(replay, "replay_hash") or not all(_hex(row) for row in (
                task.get("task_hash"), grant.get("grant_hash"), replay.get("replay_hash"), value.get("admission_hash")))):
        raise BusinessRefusal("ADMISSION_HASH_MISMATCH")
    if (task.get("parent_plan_id") != PLAN_ID or task.get("parent_item_id") not in {"P5.2", "P5.3", "P5.4"}
            or task.get("purpose") != "business-trial" or task.get("g2_package_digest") != g2_digest
            or grant.get("g2_package_digest") != g2_digest or index.get("g2_package_digest") != g2_digest
            or g2b_digest == g2_digest or not _hex(g2_digest) or not _hex(g2b_digest)):
        raise BusinessRefusal("G2_PREDECESSOR_MISMATCH")
    if (task.get("task_id") != grant.get("task_id") or task.get("task_hash") != grant.get("task_hash")
            or task.get("provider") != grant.get("provider") or task.get("provider") != rows[0].get("provider")
            or any(rows[0].get(key) != source.get(key) for key, source in (("task_hash", task), ("grant_hash", grant), ("replay_hash", replay)))
            or rows[0].get("admission_hash") != value.get("admission_hash")):
        raise BusinessRefusal("ADMISSION_INVALID")
    if (grant.get("owner_decision") != "D105" or grant.get("owner_marker") != "[OWNER-GRANT:G-OWNER-P5-BUSINESS]"
            or grant.get("branch") != "p5-business-trials" or grant.get("revoked") is not False
            or grant.get("max_slices") != 1 or value.get("usage") != {"used_slices": 0, "max_slices": 1, "reusable": False}
            or replay.get("used_slices") != 0 or replay.get("events") != [] or replay.get("attempt") != 1):
        raise BusinessRefusal("USAGE_LIMIT_EXCEEDED")
    if task.get("provider") != grant.get("provider") or task.get("provider") not in {"codex", "claude-code"}:
        raise BusinessRefusal("PROVIDER_MISMATCH")
    try:
        if datetime.fromisoformat(grant["expiry"].replace("Z", "+00:00")) <= datetime.now(UTC):
            raise BusinessRefusal("GRANT_EXPIRED")
    except (KeyError, TypeError, ValueError) as exc:
        raise BusinessRefusal("GRANT_EXPIRED") from exc
    return value


_CATALOG_CROSS_CHECK_FIELDS = ("files", "base_commit", "provider", "route", "capabilities",
                               "acceptance_refs", "validation")


def resolve_task_description(catalog_path: Path, admission: dict[str, Any]) -> dict[str, Any]:
    """D121 — hash-verified catalog row resolution.

    The catalog is a SECOND source, never a substitute authority: the admission's own
    ``task.catalog_hash``/``task.task_id`` are the only things that decide which row is
    trusted, and every dispatch-governing field on that row must match the admission
    field-for-field before its ``scenario``/``kind`` may enter a prompt. Any absent
    catalog, hash mismatch, missing/duplicate row or cross-check divergence refuses
    before intent rather than degrading to a file-list-only prompt.
    """
    task = admission["task"]
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BusinessRefusal("CATALOG_UNAVAILABLE") from exc
    if not isinstance(catalog, dict) or not isinstance(catalog.get("trials"), list):
        raise BusinessRefusal("CATALOG_UNAVAILABLE")
    if _hash(catalog, "catalog_hash") != task.get("catalog_hash"):
        raise BusinessRefusal("CATALOG_HASH_MISMATCH")
    matches = [row for row in catalog["trials"]
               if isinstance(row, dict) and row.get("trial_id") == task.get("task_id")]
    if len(matches) != 1:
        raise BusinessRefusal("CATALOG_ROW_MISSING")
    row = matches[0]
    if (not isinstance(row.get("scenario"), str) or not row["scenario"]
            or not isinstance(row.get("kind"), str) or not row["kind"]):
        raise BusinessRefusal("CATALOG_ROW_DIVERGENT")
    if any(row.get(key) != task.get(key) for key in _CATALOG_CROSS_CHECK_FIELDS):
        raise BusinessRefusal("CATALOG_ROW_DIVERGENT")
    row_budgets, task_budgets = row.get("budgets"), task.get("budgets")
    if (not isinstance(row_budgets, dict) or not isinstance(task_budgets, dict)
            or set(row_budgets) != set(task_budgets)
            or any(row_budgets[key] != task_budgets[key] for key in row_budgets)):
        raise BusinessRefusal("CATALOG_ROW_DIVERGENT")
    return row


def request(admission: dict[str, Any], *, provider_version: str, cwd: Path) -> dict[str, Any]:
    task, grant = admission["task"], admission["grant"]
    if (not cwd.is_dir() or cwd.is_symlink() or not isinstance(task.get("controlled_root"), str)
            or not task["controlled_root"].startswith("mktemp:")):
        raise BusinessRefusal("WORKSPACE_NOT_DISPOSABLE")
    return {"provider": {"id": task["provider"], "cli_version": provider_version}, "route": grant["route"],
            "permissions": {"approval_mode": "never", "sandbox_mode": "workspace_write", "network_mode": "disabled", "cwd": str(cwd)},
            "budgets": grant["budgets"], "bundle": {"content_refs": []},
            "child_policy": {"mode": "forbidden", "max_children": 0, "allowed_capabilities": []}}
