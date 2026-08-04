"""Data-only provider-parity mapping and exact provider registry helpers."""
from __future__ import annotations

import json
from pathlib import Path

from .common import AdapterRefusal


PROVIDERS = ("claude-code", "codex")
SUPPORT = frozenset({"equivalent", "degraded", "unsupported", "unknown"})
SOURCE_KEYS = frozenset({
    "worker_contract_sha256", "provider_matrix_sha256", "routing_sha256",
    "provider_capabilities_sha256", "profile_catalog_sha256",
})


def _exact(value: object, keys: set[str] | frozenset[str]) -> bool:
    return isinstance(value, dict) and set(value) == set(keys)


def _mapping_row(value: object) -> bool:
    if not _exact(value, {"status", "reason", "evidence"}):
        return False
    return (value["status"] in SUPPORT and isinstance(value["reason"], str)
            and value["reason"] and isinstance(value["evidence"], str) and value["evidence"])


def _mapping_rows(rows: object) -> bool:
    if not isinstance(rows, list) or not rows:
        return False
    ids: set[str] = set()
    for row in rows:
        if not _exact(row, {"id", "providers"}) or not isinstance(row["id"], str) or not row["id"]:
            return False
        if row["id"] in ids or not _exact(row["providers"], set(PROVIDERS)):
            return False
        ids.add(row["id"])
        if not all(_mapping_row(value) for value in row["providers"].values()):
            return False
    return len(ids) == len(rows)


def build_registry(rows: object) -> dict[str, str]:
    """Return exact provider→adapter registry or a closed mapping refusal."""
    if not isinstance(rows, list):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    registry: dict[str, str] = {}
    for row in rows:
        if not _exact(row, {"provider", "adapter"}):
            raise AdapterRefusal("MAPPING_UNKNOWN")
        provider, adapter = row["provider"], row["adapter"]
        if provider not in PROVIDERS or not isinstance(adapter, str) or not adapter or provider in registry:
            raise AdapterRefusal("MAPPING_UNKNOWN")
        registry[provider] = adapter
    if set(registry) != set(PROVIDERS):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    return registry


def lookup_provider(registry: dict[str, str], provider_id: str) -> str:
    """Resolve only an exact provider ID; no fallback or normalization exists."""
    if not isinstance(provider_id, str) or provider_id not in registry:
        raise AdapterRefusal("MAPPING_UNKNOWN")
    return registry[provider_id]


def load_mapping(path: str | Path) -> dict:
    """Load one supplied mapping without discovery or provider-to-provider translation."""
    try:
        mapping = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AdapterRefusal("MAPPING_UNKNOWN") from error
    if not _exact(mapping, {
        "schema_version", "contract_version", "sources", "registry", "fields", "capabilities", "exits",
    }):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if mapping["schema_version"] != "provider-parity-v1" or mapping["contract_version"] != "1.0.0":
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if not _exact(mapping["sources"], SOURCE_KEYS) or not all(
            isinstance(value, str) and len(value) == 64 for value in mapping["sources"].values()):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if not all(_mapping_rows(mapping[key]) for key in ("fields", "capabilities", "exits")):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    build_registry(mapping["registry"])
    return mapping
