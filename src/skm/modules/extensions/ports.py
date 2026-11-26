"""Ports of the extensions module (extensions §6).

``ResourceRepository`` reads bodies only on ``include_bodies=True``. Versions are immutable: there is no
update method, the only state change of a pack version is ``set_version_state`` (``active -> retired``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from skm.kernel.gateways import control_plane_gateway, host_gateway
from skm.kernel.ports_uow import repository_port

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from skm.kernel.ids import PrincipalId, ResourceVersionId
    from skm.kernel.json_types import JsonValue
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.extensions.domain.keys import PackId, PackSlug, PackVersionId, ResourceKey, SemVer
    from skm.modules.extensions.domain.kinds import ResourceKind
    from skm.modules.extensions.domain.pack import Pack, PackState, PackTrust, PackVersion, PackVersionSummary
    from skm.modules.extensions.domain.payload import PackPayload
    from skm.modules.extensions.domain.quarantine import QuarantineEntry
    from skm.modules.extensions.domain.resource import (
        Resource,
        ResourceVersion,
        ResourceVersionSummary,
        ResourceVersionWithBodies,
    )


@host_gateway
class PackReader(Protocol):
    def read_dir(self, root: str) -> PackPayload: ...
    def read_archive(self, path: str) -> PackPayload: ...


@control_plane_gateway
class BuiltinPacks(Protocol):
    def payloads(
        self,
    ) -> tuple[PackPayload, ...]: ...


@control_plane_gateway
class RuntimeCatalogSeeder(Protocol):
    """Project the installed core catalog within the builtin pack sync transaction."""

    def __call__(
        self, uow: UnitOfWork, resource_version_id: ResourceVersionId, manifest: Mapping[str, JsonValue]
    ) -> None: ...


@host_gateway
class UpstreamFetcher(Protocol):
    def fetch(self, url: str, *, max_bytes: int, timeout_seconds: int) -> bytes: ...


@repository_port
class PackRepository(Protocol):
    def lock_registry(self) -> None:
        """Serialize registry writers until the unit of work ends; later reads see what they committed."""
        ...

    def get(self, pack_id: PackId) -> Pack: ...
    def find_by_slug(self, slug: PackSlug) -> Pack | None: ...
    def add(self, pack: Pack) -> None: ...
    def get_version(self, version_id: PackVersionId) -> PackVersion: ...
    def find_version(self, pack_id: PackId, version: SemVer) -> PackVersion | None: ...
    def list_versions(
        self, pack_id: PackId | None = None, *, state: PackState | None = None
    ) -> tuple[PackVersionSummary, ...]: ...
    def add_version(self, version: PackVersion) -> None: ...
    def set_version_state(self, version_id: PackVersionId, state: PackState) -> None: ...


@repository_port
class ResourceRepository(Protocol):
    def find(self, kind: ResourceKind, key: ResourceKey) -> Resource | None: ...
    def add(self, resource: Resource) -> None: ...
    def add_version(self, version: ResourceVersion, file_bodies: Mapping[str, bytes]) -> None: ...
    def get_version(
        self, version_id: ResourceVersionId, *, include_bodies: bool = False
    ) -> ResourceVersionWithBodies: ...
    def versions_of(
        self, kind: ResourceKind, key: ResourceKey, pack_version_ids: Sequence[PackVersionId]
    ) -> tuple[ResourceVersionSummary, ...]: ...
    def list_in_pack_versions(
        self, pack_version_ids: Sequence[PackVersionId], *, kind: ResourceKind | None
    ) -> tuple[ResourceVersionSummary, ...]: ...
    def owner_trust(self, kind: ResourceKind, key: ResourceKey) -> PackTrust | None: ...


@repository_port
class QuarantineRepository(Protocol):
    def quarantined_ids(self, version_ids: Sequence[ResourceVersionId]) -> frozenset[ResourceVersionId]: ...
    def add(self, entry: QuarantineEntry) -> None: ...
    def release(
        self, version_id: ResourceVersionId, *, by: PrincipalId, reason: str, at: datetime
    ) -> None: ...
