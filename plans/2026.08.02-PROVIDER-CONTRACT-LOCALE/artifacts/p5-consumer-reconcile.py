#!/usr/bin/env python3
"""Compile and execute the frozen P5 fleet action manifest.

The runner owns exact-set admission, ordering, durable transaction evidence and
restart reconciliation. Provider meaning and rendering stay behind a supplied
P3 adapter. The default ``plan`` and ``check`` paths are strictly no-write for
consumer/provider targets.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


PLAN_ID = "2026.08.02-PROVIDER-CONTRACT-LOCALE"
MANIFEST_VERSION = "p5-fleet-action-manifest/v1"
EVENT_VERSION = "p5-fleet-transaction-event/v1"
RESULT_VERSION = "p5-fleet-results/v1"
ZERO_HASH = "0" * 64
ACTION_SETS = {
    "P5.2": frozenset({"preserve", "register-override"}),
    "P5.3": frozenset({"relink", "refresh-managed"}),
    "P5.4": frozenset({"quarantine-remove"}),
}
ALLOWED_ACTIONS = frozenset({"no-op-unresolved", *set().union(*ACTION_SETS.values())})
ALLOWED_EVENTS = frozenset({
    "before", "applied", "readback-passed", "readback-failed", "accepted",
    "rollback-started", "rolled-back",
})
TRANSITIONS = {
    None: {"before"},
    "before": {"applied", "rollback-started"},
    "applied": {"readback-passed", "readback-failed", "rollback-started"},
    "readback-passed": {"accepted", "rollback-started"},
    "readback-failed": {"rollback-started"},
    "rollback-started": {"rolled-back"},
    "accepted": set(),
    "rolled-back": set(),
}
SECRET = re.compile(r"(?:secret|token|password|api[_-]?key|credential|private[_-]?key)", re.I)
SECRET_VALUE = re.compile(
    r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,})"
)
ABSOLUTE = re.compile(r"(?:^|[\s\"'])(?:/home/|/Users/|[A-Za-z]:\\)")
SHA256 = re.compile(r"(?:sha256:)?([0-9a-f]{64})$")
GIT_OID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
CONTRACT_VERSION = re.compile(r"^\*\*Version:\*\*\s+(v?[0-9]+\.[0-9]+\.[0-9]+)", re.M)
CONTRACT_STATUS = re.compile(r"^\*\*Status:\*\*\s+(\S+)", re.M)
CONTRACT_APPROVAL = re.compile(r"^\*\*(?:Approval|Approval Owner):\*\*\s+(.+)$", re.M)


class Refusal(RuntimeError):
    """A fail-closed contract refusal."""


class InjectedCrash(RuntimeError):
    """A deterministic crash point used only by temporary-root tests."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def digest_value(value: Any) -> str:
    return digest_bytes(canonical_bytes(value))


def bare_digest(value: Any) -> str:
    return digest_value(value).removeprefix("sha256:")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refusal(f"P5_JSON_INVALID:{path.name}") from exc


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def initialize_empty(path: Path) -> None:
    if path.exists() and path.read_bytes() != b"":
        raise Refusal("P5_JOURNAL_NOT_EMPTY")
    atomic_write(path, b"")


def normalized_target(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise Refusal("P5_TARGET_INVALID")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise Refusal("P5_TARGET_INVALID")
    if ABSOLUTE.search(value):
        raise Refusal("P5_TARGET_PRIVACY")
    return path.as_posix()


def stable_project_id(root: Path, records: list[dict[str, Any]]) -> str:
    identity = "|".join(sorted(
        f"{record.get('provider', 'generic')}:{record.get('channel', '')}"
        for record in records
    ))
    return "project-" + hashlib.sha256((str(root) + "|" + identity).encode()).hexdigest()[:16]


def load_live_registry(registry: Path) -> dict[str, Path]:
    data = load_json(registry)
    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        raise Refusal("P5_REGISTRY_SCHEMA")
    grouped: dict[Path, list[dict[str, Any]]] = defaultdict(list)
    for record in data["projects"]:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise Refusal("P5_REGISTRY_RECORD")
        grouped[Path(record["path"])].append(record)
    resolved: dict[str, Path] = {}
    for root, records in grouped.items():
        project_id = stable_project_id(root, records)
        if project_id in resolved:
            raise Refusal("P5_DUPLICATE_PROJECT_ID")
        resolved[project_id] = root
    return resolved


def _config_shape(path: Path, raw: bytes) -> dict[str, Any]:
    if path.suffix == ".json":
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = None
        if data is not None:
            found: list[str] = []

            def walk(value: Any, prefix: str = "") -> None:
                if isinstance(value, dict):
                    for key, nested in value.items():
                        part = f"{prefix}.{key}" if prefix else key
                        found.append(part + ":" + type(nested).__name__)
                        walk(nested, part)
                elif isinstance(value, list):
                    found.append(prefix + ":list[" + str(len(value)) + "]")

            walk(data)
            return {
                "kind": "structural",
                "key_paths": sorted(found),
                "contains_secret_key": any(SECRET.search(item) for item in found),
            }
    return {
        "kind": "structural",
        "bytes": len(raw),
        "contains_secret_key": bool(SECRET.search(path.name)),
    }


def observe_node(path: Path, root: Path) -> dict[str, Any] | None:
    if not path.exists() and not path.is_symlink():
        return None
    stat = path.lstat()
    result: dict[str, Any] = {
        "path": path.relative_to(root).as_posix(),
        "mode": stat.st_mode,
        "managed": any(part in {".claude", ".codex", ".agents"} for part in path.parts),
    }
    if path.is_symlink():
        resolved = path.resolve(strict=False)
        result.update({
            "node": "symlink",
            "target_state": "broken" if not resolved.exists() else (
                "out-of-root" if root not in resolved.parents and resolved != root else "in-root"
            ),
        })
        return result
    if path.is_dir():
        result["node"] = "directory"
        return result
    result["node"] = "file"
    raw = path.read_bytes()
    result["content"] = (
        _config_shape(path, raw)
        if path.suffix in {".json", ".toml", ".yaml", ".yml", ".ini", ".env"}
        or SECRET.search(path.name)
        or SECRET_VALUE.search(raw.decode("utf-8", "ignore"))
        else {"kind": "sha256", "value": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    )
    return result


def repository_rebound(root: Path, sealed: dict[str, Any]) -> bool:
    head = sealed.get("head")
    if not root.is_dir() or not isinstance(head, str) or not GIT_OID.fullmatch(head):
        return False
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{head}^{{commit}}"],
        cwd=root, capture_output=True, check=False,
    )
    return result.returncode == 0


def contract_identity(path: Path, *, expected_status: str = "frozen") -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    version = CONTRACT_VERSION.search(text)
    status = CONTRACT_STATUS.search(text)
    approval = CONTRACT_APPROVAL.search(text)
    if not version or not status or status.group(1) != expected_status or not approval:
        raise Refusal(f"P5_CONTRACT_NOT_FROZEN:{path.name}")
    return {
        "path": path.as_posix(),
        "version": version.group(1),
        "approval": approval.group(1).strip(),
        "sha256": digest_file(path),
    }


def provider_target_guard(path: str, provider_ids: tuple[str, ...]) -> None:
    first = path.split("/", 1)[0]
    if "codex" in provider_ids and first in {".claude", ".claude-plugin", "CLAUDE.md"}:
        raise Refusal("P5_CROSS_PROVIDER_TARGET")
    if "claude-code" in provider_ids and first in {".agents", ".codex", ".codex-plugin", "AGENTS.md"}:
        raise Refusal("P5_CROSS_PROVIDER_TARGET")


def choose_action(row: dict[str, Any]) -> tuple[str, str]:
    classification = row.get("classification")
    owner = row.get("owner")
    proposed = row.get("action")
    if proposed == "no-op":
        return "no-op-unresolved", "classification carries no mutation authority"
    if classification == "local-override" and proposed in {"preserve", "register-override"}:
        return proposed, "sealed local-override disposition"
    if classification in {"canonical-equivalent", "broken-link"} and proposed == "relink" and owner != "unknown":
        return "relink", "sealed owner-qualified relink"
    if classification == "stale-managed-copy" and proposed in {"refresh-managed", "quarantine-remove"} and owner == "skm":
        return proposed, "sealed SKM ownership and rollback"
    raise Refusal("P5_CLASS_ACTION_CONTRADICTION")


def build_manifest(
    *, p0_manifest: Path, classification: Path, recovery_contract: Path,
    control_plane_contract: Path, repository_acceptance: Path, registry: Path,
) -> dict[str, Any]:
    p0 = load_json(p0_manifest)
    required = {"provider-fleet-inventory.json", "provider-source-snapshot.json"}
    if not isinstance(p0, dict) or not required.issubset(set(p0.get("files", []))):
        raise Refusal("P5_P0_MANIFEST_INCOMPLETE")
    inventory_path = p0_manifest.parent / "provider-fleet-inventory.json"
    snapshot_path = p0_manifest.parent / "provider-source-snapshot.json"
    inventory = load_json(inventory_path)
    snapshot = load_json(snapshot_path)
    classified = load_json(classification)
    acceptance = load_json(repository_acceptance)
    if inventory.get("schema_version") != 2 or snapshot.get("schema_version") != 2:
        raise Refusal("P5_P0_VERSION")
    if classified.get("schema_version") != 1 or not isinstance(classified.get("classifications"), list):
        raise Refusal("P5_CLASSIFICATION_VERSION")
    if acceptance.get("schema_version") != "p4-compact-field-acceptance/v1":
        raise Refusal("P5_REPOSITORY_ACCEPTANCE_VERSION")

    live = load_live_registry(registry)
    sealed_projects = {project["project_id"]: project for project in snapshot.get("projects", [])}
    if len(sealed_projects) != len(snapshot.get("projects", [])):
        raise Refusal("P5_DUPLICATE_SEALED_PROJECT")
    if set(live) != set(sealed_projects):
        raise Refusal("P5_PROJECT_SET_MISMATCH")

    sealed_nodes: dict[tuple[str, str], dict[str, Any]] = {}
    for project_id, project in sealed_projects.items():
        for node in project.get("provider_paths", []):
            key = (project_id, normalized_target(node.get("path")))
            if key in sealed_nodes:
                raise Refusal("P5_DUPLICATE_SEALED_ARTIFACT")
            sealed_nodes[key] = node

    source_rows = classified["classifications"]
    if len(source_rows) != len(sealed_nodes):
        raise Refusal("P5_ARTIFACT_COUNT_MISMATCH")
    source_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    rebind_counts: Counter[str] = Counter()
    repository_mismatch: set[str] = set()
    for source in source_rows:
        source_id = source.get("artifact_id")
        if not isinstance(source_id, str) or source_id in source_ids:
            raise Refusal("P5_DUPLICATE_CLASSIFICATION_ROW")
        source_ids.add(source_id)
        project_id = source.get("project_id")
        target = normalized_target(source.get("path"))
        sealed = sealed_nodes.get((project_id, target))
        if sealed is None:
            raise Refusal("P5_UNCLASSIFIED_OR_EXTRA_ROW")
        provider_ids = tuple(sorted(source.get("providers", [])))
        if not provider_ids or any(provider not in {"claude-code", "codex", "shared"} for provider in provider_ids):
            raise Refusal("P5_PROVIDER_SET_INVALID")
        provider_target_guard(target, provider_ids)
        action, action_reason = choose_action(source)
        root = live[project_id]
        rebound = repository_rebound(root, sealed_projects[project_id].get("repository", {}))
        if not rebound:
            repository_mismatch.add(project_id)
        current = observe_node(root / target, root)
        comparable = {key: value for key, value in sealed.items() if key not in {"artifact_id", "tracked"}}
        if current is None:
            rebind_status = "missing"
        elif current == comparable:
            rebind_status = "exact"
        else:
            rebind_status = "drifted"
        if not rebound:
            rebind_status = "repository-mismatch"
        rebind_counts[rebind_status] += 1
        if rebind_status != "exact" and action != "no-op-unresolved":
            raise Refusal("P5_MUTATION_PREIMAGE_DRIFT")
        evidence = source.get("evidence")
        if not isinstance(evidence, list) or not all(isinstance(item, str) and not ABSOLUTE.search(item) for item in evidence):
            raise Refusal("P5_EVIDENCE_INVALID")
        row_base = {
            "source_artifact_id": source_id,
            "sealed_artifact_id": sealed.get("artifact_id"),
            "project_id": project_id,
            "provider_ids": list(provider_ids),
            "relative_target": target,
            "classification": source.get("classification"),
            "owner": source.get("owner"),
            "evidence": sorted(evidence),
            "action": action,
            "action_reason": action_reason,
            "sealed_preimage_sha256": digest_value(comparable),
            "preimage_rebind": rebind_status,
            "backup": "not-required:no-write" if action == "no-op-unresolved" else "required:private-project-backup",
            "rollback": "not-required:no-write" if action == "no-op-unresolved" else source.get("rollback"),
            "expected_readback": "unresolved-no-write" if action == "no-op-unresolved" else "provider-qualified-clean",
            "destination_item": next((item for item, actions in ACTION_SETS.items() if action in actions), None),
        }
        row_base["action_id"] = "action-" + bare_digest(row_base)[:24]
        rows.append(row_base)

    if set(sealed_nodes) != {(row["project_id"], row["relative_target"]) for row in rows}:
        raise Refusal("P5_ARTIFACT_SET_MISMATCH")
    rows.sort(key=lambda row: (row["project_id"], row["relative_target"], row["action_id"]))
    action_sets = {}
    for item, actions in ACTION_SETS.items():
        action_ids = [row["action_id"] for row in rows if row["action"] in actions]
        action_sets[item] = {
            "action_ids": action_ids,
            "action_set_id": "action-set-" + bare_digest({"item": item, "action_ids": action_ids})[:24],
        }
    source_identities = {
        "p0_manifest": {"path": p0_manifest.as_posix(), "sha256": digest_file(p0_manifest)},
        "p0_inventory": {"path": inventory_path.as_posix(), "sha256": digest_file(inventory_path)},
        "p0_snapshot": {"path": snapshot_path.as_posix(), "sha256": digest_file(snapshot_path)},
        "classification": {"path": classification.as_posix(), "sha256": digest_file(classification)},
        "recovery_contract": contract_identity(recovery_contract),
        "control_plane_contract": contract_identity(control_plane_contract),
        "repository_acceptance": {"path": repository_acceptance.as_posix(), "sha256": digest_file(repository_acceptance)},
    }
    payload = {
        "schema_version": MANIFEST_VERSION,
        "plan_id": PLAN_ID,
        "source_identities": source_identities,
        "project_ids": sorted(sealed_projects),
        "protected_project_ids": sorted({row["project_id"] for row in rows if row["action"] == "no-op-unresolved"}),
        "repository_mismatch_project_ids": sorted(repository_mismatch),
        "action_sets": action_sets,
        "rows": rows,
        "summary": {
            "projects": len(sealed_projects),
            "rows": len(rows),
            "actions": dict(sorted(Counter(row["action"] for row in rows).items())),
            "preimage_rebind": dict(sorted(rebind_counts.items())),
            "consumer_writes": 0,
        },
    }
    payload["manifest_sha256"] = digest_value(payload)
    return payload


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != MANIFEST_VERSION:
        raise Refusal("P5_MANIFEST_VERSION")
    claimed = manifest.get("manifest_sha256")
    payload = dict(manifest)
    payload.pop("manifest_sha256", None)
    if claimed != digest_value(payload):
        raise Refusal("P5_MANIFEST_DIGEST")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or rows != sorted(rows, key=lambda row: (row["project_id"], row["relative_target"], row["action_id"])):
        raise Refusal("P5_MANIFEST_ROW_ORDER")
    if len({row.get("action_id") for row in rows}) != len(rows):
        raise Refusal("P5_ACTION_ID_DUPLICATE")
    for row in rows:
        if row.get("action") not in ALLOWED_ACTIONS:
            raise Refusal("P5_ACTION_UNKNOWN")
        normalized_target(row.get("relative_target"))
        provider_target_guard(row["relative_target"], tuple(row.get("provider_ids", [])))
        if row["action"] == "quarantine-remove" and (
            row.get("owner") != "skm" or not str(row.get("rollback", "")).strip()
        ):
            raise Refusal("P5_DESTRUCTIVE_OWNERSHIP")


def _event_hash(event: dict[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_sha256", None)
    return bare_digest(payload)


def validate_journal(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise Refusal("P5_JOURNAL_MISSING")
    events: list[dict[str, Any]] = []
    previous = ZERO_HASH
    transaction_state: dict[str, str | None] = {}
    for ordinal, raw in enumerate(path.read_bytes().splitlines()):
        try:
            event = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Refusal("P5_JOURNAL_TORN_OR_TRUNCATED") from exc
        if canonical_bytes(event) != raw:
            raise Refusal("P5_JOURNAL_NONCANONICAL")
        if event.get("schema_version") != EVENT_VERSION or event.get("ordinal") != ordinal:
            raise Refusal("P5_JOURNAL_ORDINAL")
        if event.get("prev_event_sha256") != previous:
            raise Refusal("P5_JOURNAL_PREVIOUS_HASH")
        if event.get("event_sha256") != _event_hash(event):
            raise Refusal("P5_JOURNAL_EVENT_HASH")
        event_name = event.get("event")
        if event_name not in ALLOWED_EVENTS:
            raise Refusal("P5_JOURNAL_EVENT_UNKNOWN")
        transaction_id = event.get("transaction_id")
        prior = transaction_state.get(transaction_id)
        if event_name not in TRANSITIONS[prior]:
            raise Refusal("P5_JOURNAL_TRANSITION")
        transaction_state[transaction_id] = event_name
        previous = event["event_sha256"]
        events.append(event)
    return events


def append_event(path: Path, event: dict[str, Any]) -> dict[str, Any]:
    events = validate_journal(path)
    complete = {
        "schema_version": EVENT_VERSION,
        "ordinal": len(events),
        "prev_event_sha256": events[-1]["event_sha256"] if events else ZERO_HASH,
        **event,
    }
    complete["event_sha256"] = _event_hash(complete)
    with path.open("ab") as handle:
        handle.write(canonical_bytes(complete) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)
    validate_journal(path)
    _checkpoint("append-" + complete["event"])
    return complete


def _checkpoint(name: str) -> None:
    if os.environ.get("P5_CRASH_AFTER") == name:
        raise InjectedCrash(name)


def parse_approval(path: Path, manifest: dict[str, Any]) -> str:
    text = path.read_text(encoding="utf-8")
    manifest_match = re.search(r"^Manifest SHA-256:\s+(sha256:[0-9a-f]{64})$", text, re.M)
    decision = re.search(r"^Owner decision:\s+(D[0-9]+)$", text, re.M)
    status = re.search(r"^Status:\s+frozen$", text, re.M)
    if not manifest_match or manifest_match.group(1) != manifest["manifest_sha256"]:
        raise Refusal("P5_APPROVAL_MANIFEST_MISMATCH")
    if not decision or not status:
        raise Refusal("P5_APPROVAL_REQUIRED")
    if re.search(r"^(?:Approver|Owner):\s+(?:executor|agent|model)$", text, re.M | re.I):
        raise Refusal("P5_SELF_APPROVAL")
    for item, value in manifest["action_sets"].items():
        if f"{item}: {value['action_set_id']}" not in text:
            raise Refusal("P5_APPROVAL_ACTION_SET_MISMATCH")
    return decision.group(1)


class JsonStateAdapter:
    """Temporary-root fake P3 adapter; unavailable unless explicitly enabled."""

    def __init__(self, path: Path):
        if os.environ.get("P5_ALLOW_FAKE_ADAPTER") != "1":
            raise Refusal("P5_FAKE_ADAPTER_FORBIDDEN")
        self.path = path

    def _load(self) -> dict[str, str]:
        value = load_json(self.path)
        if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            raise Refusal("P5_FAKE_ADAPTER_SCHEMA")
        return value

    def observe(self, project_id: str, actions: list[dict[str, Any]]) -> str:
        return self._load().get(project_id, "third-state")

    def apply(self, project_id: str, actions: list[dict[str, Any]]) -> None:
        state = self._load()
        state[project_id] = _project_image(actions, "planned_postimage_sha256")
        atomic_write(self.path, pretty_bytes(state))

    def readback(self, project_id: str, actions: list[dict[str, Any]]) -> dict[str, str]:
        observed = self.observe(project_id, actions)
        expected = _project_image(actions, "planned_postimage_sha256")
        status = "passed" if observed == expected else "failed"
        if os.environ.get("P5_FAKE_READBACK_FAIL") == "1":
            status = "failed"
        providers = {p for row in actions for p in row["provider_ids"] if p != "shared"}
        if any("shared" in row["provider_ids"] for row in actions):
            providers.update({"claude-code", "codex"})
        return {provider: status for provider in sorted(providers)}

    def rollback(self, project_id: str, actions: list[dict[str, Any]]) -> None:
        state = self._load()
        state[project_id] = _project_image(actions, "sealed_preimage_sha256")
        atomic_write(self.path, pretty_bytes(state))


def load_adapter(args: argparse.Namespace):
    if args.adapter_state:
        return JsonStateAdapter(Path(args.adapter_state))
    entrypoint = os.environ.get("P5_RECONCILE_ADAPTER")
    if not entrypoint or ":" not in entrypoint:
        raise Refusal("P5_PUBLIC_ADAPTER_UNAVAILABLE")
    module_name, factory_name = entrypoint.split(":", 1)
    factory = getattr(importlib.import_module(module_name), factory_name)
    return factory()


def transaction_id(manifest: dict[str, Any], item: str, project_id: str, actions: list[dict[str, Any]]) -> str:
    source_ids = {
        key: value["sha256"] for key, value in manifest["source_identities"].items()
    }
    payload = {
        "manifest_sha256": manifest["manifest_sha256"],
        "destination_item": item,
        "project_id": project_id,
        "action_ids": [row["action_id"] for row in actions],
        "source_identities": source_ids,
    }
    return "transaction-" + bare_digest(payload)[:24]


def _project_image(actions: list[dict[str, Any]], field: str) -> str:
    return digest_value({row["action_id"]: row[field] for row in actions})


def _base_event(manifest: dict[str, Any], item: str, project_id: str, actions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "transaction_id": transaction_id(manifest, item, project_id, actions),
        "manifest_sha256": manifest["manifest_sha256"],
        "action_set": item,
        "action_set_id": manifest["action_sets"][item]["action_set_id"],
        "project_id": project_id,
        "action_ids": [row["action_id"] for row in actions],
        "preimage_sha256": _project_image(actions, "sealed_preimage_sha256"),
        "postimage_sha256": _project_image(actions, "planned_postimage_sha256"),
        "backup_identities": {row["action_id"]: row.get("backup") for row in actions},
    }


def _latest_by_transaction(events: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for event in events:
        result[event["transaction_id"]] = event
    return result


def _append_rollback(manifest, item, project_id, actions, journal, adapter, *, started: bool = False) -> None:
    base = _base_event(manifest, item, project_id, actions)
    if not started:
        append_event(journal, {**base, "event": "rollback-started", "provider_readback": None})
    adapter.rollback(project_id, actions)
    _checkpoint("public-rollback")
    if adapter.observe(project_id, actions) != _project_image(actions, "sealed_preimage_sha256"):
        raise Refusal("P5_ROLLBACK_PREIMAGE_MISMATCH")
    append_event(journal, {**base, "event": "rolled-back", "provider_readback": None})


def _continue_transaction(manifest, item, project_id, actions, journal, adapter, *, start: bool) -> str:
    base = _base_event(manifest, item, project_id, actions)
    if start:
        append_event(journal, {**base, "event": "before", "provider_readback": None})
        adapter.apply(project_id, actions)
        _checkpoint("public-apply")
        append_event(journal, {**base, "event": "applied", "provider_readback": None})
    observed = adapter.observe(project_id, actions)
    preimage = _project_image(actions, "sealed_preimage_sha256")
    postimage = _project_image(actions, "planned_postimage_sha256")
    if observed == preimage:
        _append_rollback(manifest, item, project_id, actions, journal, adapter)
        return "rolled-back"
    if observed != postimage:
        raise Refusal("P5_RECONCILE_THIRD_STATE")
    readback = adapter.readback(project_id, actions)
    _checkpoint("public-readback")
    if readback and all(value == "passed" for value in readback.values()):
        append_event(journal, {**base, "event": "readback-passed", "provider_readback": readback})
        append_event(journal, {**base, "event": "accepted", "provider_readback": readback})
        return "accepted"
    append_event(journal, {**base, "event": "readback-failed", "provider_readback": readback})
    _append_rollback(manifest, item, project_id, actions, journal, adapter)
    return "rolled-back"


def _resume_transaction(manifest, item, project_id, actions, journal, adapter, state: str) -> str:
    base = _base_event(manifest, item, project_id, actions)
    if state == "readback-passed":
        if adapter.observe(project_id, actions) != _project_image(actions, "planned_postimage_sha256"):
            raise Refusal("P5_RECONCILE_THIRD_STATE")
        readback = adapter.readback(project_id, actions)
        _checkpoint("public-readback")
        if not readback or not all(value == "passed" for value in readback.values()):
            _append_rollback(manifest, item, project_id, actions, journal, adapter)
            return "rolled-back"
        append_event(journal, {**base, "event": "accepted", "provider_readback": readback})
        return "accepted"
    if state == "rollback-started":
        _append_rollback(manifest, item, project_id, actions, journal, adapter, started=True)
        return "rolled-back"
    if state in {"readback-failed"}:
        _append_rollback(manifest, item, project_id, actions, journal, adapter)
        return "rolled-back"
    if state == "before":
        observed = adapter.observe(project_id, actions)
        preimage = _project_image(actions, "sealed_preimage_sha256")
        postimage = _project_image(actions, "planned_postimage_sha256")
        if observed == preimage:
            _append_rollback(manifest, item, project_id, actions, journal, adapter)
            return "rolled-back"
        if observed != postimage:
            raise Refusal("P5_RECONCILE_THIRD_STATE")
        append_event(journal, {**base, "event": "applied", "provider_readback": None})
        return _continue_transaction(manifest, item, project_id, actions, journal, adapter, start=False)
    if state != "applied":
        raise Refusal("P5_RECONCILE_STATE_INVALID")
    return _continue_transaction(manifest, item, project_id, actions, journal, adapter, start=False)


def execute(args: argparse.Namespace, *, mode: str) -> int:
    manifest = load_json(Path(args.manifest))
    validate_manifest(manifest)
    parse_approval(Path(args.approval), manifest)
    contract_identity(Path(args.recovery_contract))
    item = args.action_set
    if item not in ACTION_SETS:
        raise Refusal("P5_ACTION_SET_UNKNOWN")
    journal = Path(args.journal)
    events = validate_journal(journal)
    wanted = set(manifest["action_sets"][item]["action_ids"])
    rows = [row for row in manifest["rows"] if row["action_id"] in wanted]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if "planned_postimage_sha256" not in row:
            raise Refusal("P5_POSTIMAGE_MISSING")
        groups[row["project_id"]].append(row)
    adapter = load_adapter(args) if groups else None
    latest = _latest_by_transaction(events)
    outcomes: dict[str, str] = {}
    for project_id in sorted(groups):
        actions = sorted(groups[project_id], key=lambda row: row["action_id"])
        txid = transaction_id(manifest, item, project_id, actions)
        current = latest.get(txid)
        state = current["event"] if current else None
        if state in {"accepted", "rolled-back"}:
            outcomes[project_id] = state
            continue
        if mode == "rollback":
            if state is None:
                continue
            _append_rollback(
                manifest, item, project_id, actions, journal, adapter,
                started=state == "rollback-started",
            )
            outcomes[project_id] = "rolled-back"
        elif state is None:
            outcomes[project_id] = _continue_transaction(
                manifest, item, project_id, actions, journal, adapter, start=True
            )
        else:
            outcomes[project_id] = _resume_transaction(
                manifest, item, project_id, actions, journal, adapter, state
            )
        latest = _latest_by_transaction(validate_journal(journal))
    result = {
        "schema_version": RESULT_VERSION,
        "manifest_sha256": manifest["manifest_sha256"],
        "action_set": item,
        "action_set_id": manifest["action_sets"][item]["action_set_id"],
        "project_outcomes": dict(sorted(outcomes.items())),
        "unresolved_action_ids": [row["action_id"] for row in manifest["rows"] if row["action"] == "no-op-unresolved"],
        "journal_events": len(validate_journal(journal)),
    }
    atomic_write(Path(args.results), pretty_bytes(result))
    return 0


def verify_results(args: argparse.Namespace) -> int:
    manifest = load_json(Path(args.manifest))
    validate_manifest(manifest)
    parse_approval(Path(args.approval), manifest)
    contract_identity(Path(args.recovery_contract))
    events = validate_journal(Path(args.journal))
    result = load_json(Path(args.results))
    if result.get("schema_version") != RESULT_VERSION or result.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise Refusal("P5_RESULTS_MISMATCH")
    latest = _latest_by_transaction(events)
    if any(event["event"] not in {"accepted", "rolled-back"} for event in latest.values()):
        raise Refusal("P5_RESULTS_NONTERMINAL")
    print(f"P5 results verified: {len(events)} durable events")
    return 0


def add_plan_arguments(parser: argparse.ArgumentParser, *, check: bool) -> None:
    parser.add_argument("--p0-manifest", required=True)
    parser.add_argument("--classification", required=True)
    parser.add_argument("--recovery-contract", required=True)
    parser.add_argument("--control-plane-contract", required=True)
    parser.add_argument("--repository-acceptance", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--registry", default=os.environ.get(
        "SWISSKNIFEMAN_PROJECT_REGISTRY",
        str(Path.home() / ".swissknifeman" / "projects.json"),
    ))


def add_transaction_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--approval", required=True)
    parser.add_argument("--recovery-contract", required=True)
    parser.add_argument("--action-set", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--adapter-state")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    add_plan_arguments(commands.add_parser("plan"), check=False)
    add_plan_arguments(commands.add_parser("check"), check=True)
    for name in ("apply", "resume", "rollback"):
        add_transaction_arguments(commands.add_parser(name))
    add_transaction_arguments(commands.add_parser("verify-results"))
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command in {"plan", "check"}:
            expected = build_manifest(
                p0_manifest=Path(args.p0_manifest),
                classification=Path(args.classification),
                recovery_contract=Path(args.recovery_contract),
                control_plane_contract=Path(args.control_plane_contract),
                repository_acceptance=Path(args.repository_acceptance),
                registry=Path(args.registry),
            )
            manifest_path = Path(args.manifest)
            journal_path = Path(args.journal)
            if args.command == "plan":
                atomic_write(manifest_path, pretty_bytes(expected))
                initialize_empty(journal_path)
                print(
                    f"P5 manifest frozen: {expected['summary']['rows']} rows; "
                    f"{expected['manifest_sha256']}"
                )
                return 0
            if manifest_path.read_bytes() != pretty_bytes(expected):
                raise Refusal("P5_MANIFEST_STALE")
            validate_journal(journal_path)
            print("P5 manifest check: allow")
            return 0
        if args.command in {"apply", "resume", "rollback"}:
            return execute(args, mode=args.command)
        return verify_results(args)
    except InjectedCrash as exc:
        print(f"P5_INJECTED_CRASH:{exc}", file=sys.stderr)
        return 75
    except (Refusal, OSError, KeyError, TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
