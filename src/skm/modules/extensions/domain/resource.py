"""Resources and their immutable versions (extensions §4.4, §13).

A version never changes: files, digest and compat report are written once. ``check_file_bodies`` makes a
stored ``ResourceFile`` provably describe its bytes, in every backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.modules.extensions.domain.compat import (
    CompatCheck,
    CompatCheckId,
    CompatReport,
    CompatStatus,
    CompatVerdict,
)
from skm.modules.extensions.domain.digest_rules import file_digest, resource_digest

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from skm.kernel.ids import ResourceVersionId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.extensions.domain.keys import PackId, PackVersionId, ResourceId, ResourceKey, SemVer
    from skm.modules.extensions.domain.kinds import ResourceKind
    from skm.modules.extensions.domain.quarantine import QuarantineEntry

__all__ = [
    "Digest",
    "Resource",
    "ResourceFile",
    "ResourceRef",
    "ResourceVersion",
    "ResourceVersionSummary",
    "ResourceVersionWithBodies",
    "RuntimeCatalogEntry",
    "RuntimeCatalogView",
    "check_file_bodies",
    "compat_report_from_json",
    "compat_report_to_json",
    "proven_bodies",
    "quarantine_row",
]

type Digest = str


@dataclass(frozen=True, slots=True)
class Resource:
    id: ResourceId
    kind: ResourceKind
    key: ResourceKey
    first_pack_id: PackId
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ResourceFile:
    path: str
    size_bytes: int
    digest: Digest
    media_type: str


@dataclass(frozen=True, slots=True)
class ResourceVersion:
    id: ResourceVersionId
    resource_id: ResourceId
    kind: ResourceKind
    key: ResourceKey
    pack_version_id: PackVersionId
    version: SemVer
    digest: Digest
    manifest: Mapping[str, JsonValue]
    files: tuple[ResourceFile, ...]
    tokens_estimate: int
    compat: CompatReport
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ResourceRef:
    kind: ResourceKind
    key: ResourceKey
    version_id: ResourceVersionId
    digest: Digest


@dataclass(frozen=True, slots=True)
class ResourceVersionSummary:
    """A version without manifest and bodies: what resolution compares."""

    id: ResourceVersionId
    kind: ResourceKind
    key: ResourceKey
    pack_version_id: PackVersionId
    version: SemVer
    digest: Digest
    verdict: CompatVerdict


@dataclass(frozen=True, slots=True)
class ResourceVersionWithBodies:
    version: ResourceVersion
    bodies: Mapping[str, bytes] | None


@dataclass(frozen=True, slots=True)
class RuntimeCatalogEntry:
    resource_version_id: ResourceVersionId
    key: ResourceKey
    digest: Digest
    manifest: Mapping[str, JsonValue]
    body: str
    is_operator_snapshot: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeCatalogView:
    entries: tuple[RuntimeCatalogEntry, ...]  # by key; the merge and its conflicts belong to runtimes
    digest: Digest


def _describes(files: tuple[ResourceFile, ...], bodies: Mapping[str, bytes]) -> bool:
    known = {item.path: item for item in files}
    return set(known) == set(bodies) and all(
        len(bodies[path]) == item.size_bytes and file_digest(bodies[path]) == item.digest
        for path, item in known.items()
    )


def check_file_bodies(files: tuple[ResourceFile, ...], bodies: Mapping[str, bytes]) -> None:
    """A defect of the writer, never of the client: the metadata must describe exactly these bytes."""
    if not _describes(files, bodies):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            "resource file metadata does not match its bytes",
            details={"paths": [*sorted(item.path for item in files)]},
        )


def proven_bodies(stored: ResourceVersionWithBodies) -> Mapping[str, bytes] | None:
    """The files of a stored version, if its rows still prove them; ``None``: nothing can be compared with
    them. A resource has at least one file, and files that lost a row no longer hash to the stored digest."""
    version, bodies = stored.version, stored.bodies
    if not bodies or not _describes(version.files, bodies):
        return None
    return bodies if resource_digest(bodies) == version.digest else None


def compat_report_to_json(report: CompatReport) -> JsonObject:
    return {
        "verdict": report.verdict.value,
        "checks": [
            {"id": check.id.value, "status": check.status.value, "detail": check.detail}
            for check in report.checks
        ],
    }


def compat_report_from_json(document: Mapping[str, object]) -> CompatReport:
    checks = cast("list[Mapping[str, str]]", document["checks"])
    return CompatReport(
        checks=tuple(
            CompatCheck(CompatCheckId(item["id"]), CompatStatus(item["status"]), item["detail"])
            for item in checks
        ),
        verdict=CompatVerdict(cast("str", document["verdict"])),
    )


def quarantine_row(entry: QuarantineEntry) -> tuple[str, list[str], JsonObject | None]:
    """``(reason_kind, reasons, report)`` of ``resource_quarantine``: ``reason = "compat"`` carries a report
    with its reasons (§7.1 step 15), every other value is the text of a manual decision (§7.3)."""
    if entry.reason != "compat":
        return "manual", [entry.reason], entry.report or None
    reasons = entry.report.get("reasons")
    listed = [str(item) for item in cast("list[object]", reasons)] if isinstance(reasons, list) else []
    return "compat", listed or ["compat"], entry.report
