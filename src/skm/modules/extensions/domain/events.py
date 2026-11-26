"""Domain events of the extensions module (extensions §9): stream ``pack``, instance feed (no workspace)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, override
from uuid import UUID

from skm.kernel.events import DomainEvent
from skm.kernel.ids import WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.extensions.generated import events as generated

__all__ = [
    "EVENT_TYPES",
    "PackInstalled",
    "PackVersionUninstalled",
    "ResourceQuarantined",
    "ResourceReleased",
    "ResourceVersionAdded",
]

EVENT_TYPES = (
    "urn:skm:extensions:event:pack-installed:v1",
    "urn:skm:extensions:event:pack-version-uninstalled:v1",
    "urn:skm:extensions:event:resource-quarantined:v1",
    "urn:skm:extensions:event:resource-released:v1",
    "urn:skm:extensions:event:resource-version-added:v1",
)


@dataclass(frozen=True, slots=True)
class _PackEvent(DomainEvent):
    stream_kind: ClassVar[str] = "pack"

    pack_id: UUID

    @override
    def stream_id(self) -> UUID:
        return self.pack_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return None


@dataclass(frozen=True, slots=True)
class PackInstalled(_PackEvent):
    event_type: ClassVar[str] = EVENT_TYPES[0]

    pack_version_id: UUID
    slug: str
    version: str
    digest: str
    trust: str
    resource_count: int
    quarantined_count: int

    @override
    def payload(self) -> JsonObject:
        return generated.PackInstalled(
            pack_id=self.pack_id,
            pack_version_id=self.pack_version_id,
            slug=self.slug,
            version=self.version,
            digest=self.digest,
            trust=generated.PackTrust(self.trust),
            resource_count=self.resource_count,
            quarantined_count=self.quarantined_count,
        ).to_json()


@dataclass(frozen=True, slots=True)
class PackVersionUninstalled(_PackEvent):
    event_type: ClassVar[str] = EVENT_TYPES[1]

    pack_version_id: UUID
    slug: str
    version: str

    @override
    def payload(self) -> JsonObject:
        return generated.PackVersionUninstalled(
            pack_id=self.pack_id, pack_version_id=self.pack_version_id, slug=self.slug, version=self.version
        ).to_json()


@dataclass(frozen=True, slots=True)
class ResourceQuarantined(_PackEvent):
    event_type: ClassVar[str] = EVENT_TYPES[2]

    resource_version_id: UUID
    kind: str
    key: str
    reason_kind: str
    reasons: tuple[str, ...]

    @override
    def payload(self) -> JsonObject:
        reason_kind = "compat" if self.reason_kind == "compat" else "manual"
        return generated.ResourceQuarantined(
            resource_version_id=self.resource_version_id,
            kind=generated.ResourceKind(self.kind),
            key=self.key,
            reason_kind=reason_kind,
            reasons=self.reasons,
        ).to_json()


@dataclass(frozen=True, slots=True)
class ResourceReleased(_PackEvent):
    event_type: ClassVar[str] = EVENT_TYPES[3]

    resource_version_id: UUID
    kind: str
    key: str
    released_by: UUID
    reason: str

    @override
    def payload(self) -> JsonObject:
        return generated.ResourceReleased(
            resource_version_id=self.resource_version_id,
            kind=generated.ResourceKind(self.kind),
            key=self.key,
            released_by=self.released_by,
            reason=self.reason,
        ).to_json()


@dataclass(frozen=True, slots=True)
class ResourceVersionAdded(_PackEvent):
    event_type: ClassVar[str] = EVENT_TYPES[4]

    resource_version_id: UUID
    resource_id: UUID
    kind: str
    key: str
    version: str
    digest: str
    pack_version_id: UUID

    @override
    def payload(self) -> JsonObject:
        return generated.ResourceVersionAdded(
            resource_version_id=self.resource_version_id,
            resource_id=self.resource_id,
            kind=generated.ResourceKind(self.kind),
            key=self.key,
            version=self.version,
            digest=self.digest,
            pack_version_id=self.pack_version_id,
        ).to_json()
