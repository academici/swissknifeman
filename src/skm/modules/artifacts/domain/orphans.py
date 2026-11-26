"""Orphan report domain model, deterministic digest and manual-prune G22 guards (artifacts §7, §8)."""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from skm.kernel.ids import WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.artifacts.domain.blob import BlobId, ContentDigest

__all__ = [
    "MissingObject",
    "OrphanObject",
    "OrphanReport",
    "build_orphan_report",
    "orphan_report_digest",
    "parse_object_storage_key",
    "prunable",
]


def _require_aware(value: datetime, field: str) -> datetime:
    if value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _format_timestamp(value: datetime) -> str:
    """UTC ISO-8601 with six fractional digits and ``Z`` (identical to ``platform.jsonc.canonical``)."""
    return (
        _require_aware(value, "timestamp")
        .astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _require_text(text: str) -> str:
    if not text.isascii():
        text.encode("utf-8")
    return text


@dataclass(frozen=True, slots=True)
class OrphanObject:
    """Physical object in ``BlobStore`` with no ``blob_locations`` row."""

    storage_key: str
    size_bytes: int
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.storage_key:
            raise ValueError("storage_key must be non-empty")
        _require_text(self.storage_key)
        if isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ValueError("size_bytes must be >= 0")
        _require_aware(self.created_at, "created_at")

    def to_json(self) -> JsonObject:
        return {
            "storage_key": self.storage_key,
            "size_bytes": self.size_bytes,
            "created_at": _format_timestamp(self.created_at),
        }


@dataclass(frozen=True, slots=True)
class MissingObject:
    """``blob_locations`` row whose physical object is absent from ``BlobStore``."""

    blob_id: BlobId
    storage_key: str

    def __post_init__(self) -> None:
        if not self.storage_key:
            raise ValueError("storage_key must be non-empty")
        _require_text(self.storage_key)

    def to_json(self) -> JsonObject:
        return {
            "blob_id": str(self.blob_id),
            "storage_key": self.storage_key,
        }


@dataclass(frozen=True, slots=True)
class OrphanReport:
    """Sorted, immutable orphan/missing report with deterministic ``report_digest``."""

    orphan_objects: tuple[OrphanObject, ...]
    missing_objects: tuple[MissingObject, ...]
    report_digest: str

    def to_json(self) -> JsonObject:
        return {
            "orphan_objects": [item.to_json() for item in self.orphan_objects],
            "missing_objects": [item.to_json() for item in self.missing_objects],
            "report_digest": self.report_digest,
        }


def orphan_report_digest(orphans: Iterable[OrphanObject]) -> str:
    """Canonical SHA-256 digest of the ``storage_key``-sorted ``orphan_objects`` list (artifacts §8)."""
    sorted_orphans = sorted(orphans, key=lambda item: item.storage_key)
    canonical_items = [
        {
            "created_at": _format_timestamp(item.created_at),
            "size_bytes": item.size_bytes,
            "storage_key": item.storage_key,
        }
        for item in sorted_orphans
    ]
    payload = json.dumps(canonical_items, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def build_orphan_report(
    orphan_objects: Iterable[OrphanObject],
    missing_objects: Iterable[MissingObject],
) -> OrphanReport:
    """Sort orphan and missing lists deterministically and compute ``report_digest``."""
    sorted_orphans = tuple(sorted(orphan_objects, key=lambda item: item.storage_key))
    sorted_missing = tuple(sorted(missing_objects, key=lambda item: (item.storage_key, str(item.blob_id))))
    return OrphanReport(
        orphan_objects=sorted_orphans,
        missing_objects=sorted_missing,
        report_digest=orphan_report_digest(sorted_orphans),
    )


def prunable(report: OrphanReport, *, now: datetime, min_age: timedelta) -> tuple[OrphanObject, ...]:
    """Filter orphans eligible for manual prune under G22 (age >= ``min_age``, positive ``min_age``)."""
    _require_aware(now, "now")
    if min_age <= timedelta(0):
        raise ValueError("min_age must be positive to protect in-flight uploads")
    cutoff = now - min_age
    return tuple(item for item in report.orphan_objects if item.created_at <= cutoff)


def parse_object_storage_key(storage_key: str) -> tuple[WorkspaceId, ContentDigest]:
    """Parse ``<workspace_uuid>/objects/<aa>/<64hex>`` and reject staging or malformed keys (G22)."""
    parts = storage_key.split("/")
    if len(parts) != 4 or parts[1] != "objects":
        raise ValueError("storage_key is not a final workspace object key")
    ws_raw, _, prefix, hex_digest = parts
    workspace_id = WorkspaceId(UUID(ws_raw))
    digest = ContentDigest(f"sha256:{hex_digest}")
    if len(prefix) != 2 or hex_digest[:2] != prefix:
        raise ValueError("storage_key shard prefix does not match digest")
    if storage_key != f"{workspace_id}/objects/{prefix}/{hex_digest}":
        raise ValueError("storage_key is not in canonical form")
    return workspace_id, digest
