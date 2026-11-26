"""Memory adapters of the extensions repository ports (extensions §6, §11).

Immutability is the contract of the ports: there is no method that changes a stored row except the state of a
pack version and the release of a quarantine row.
"""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import replace
from datetime import datetime

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.extensions.mapping import MemoryExtensionsState, QuarantineRow, extensions_state
from skm.adapters.memory.extensions.queries import pack_summary, resource_summary
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed
from skm.kernel.ids import PrincipalId, ResourceVersionId
from skm.modules.extensions.domain.keys import PackId, PackSlug, PackVersionId, ResourceKey, SemVer
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.pack import Pack, PackState, PackTrust, PackVersion, PackVersionSummary
from skm.modules.extensions.domain.quarantine import QuarantineEntry
from skm.modules.extensions.domain.resource import (
    Resource,
    ResourceVersion,
    ResourceVersionSummary,
    ResourceVersionWithBodies,
    check_file_bodies,
    quarantine_row,
)

__all__ = [
    "MemoryPackRepository",
    "MemoryQuarantineRepository",
    "MemoryResourceRepository",
]


def _not_found(kind: str, ref: object) -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, f"{kind} not found", details={"kind": kind, "ref": str(ref)})


def _exists(constraint: str) -> Conflict:
    return Conflict(
        ErrorCode.ALREADY_EXISTS, "unique constraint violated", details={"constraint": constraint}
    )


class _Tables:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state

    @property
    def _tables(self) -> MemoryExtensionsState:
        return extensions_state(self._state)

    def _writable(self) -> MemoryExtensionsState:
        self._state.core.require_writable()
        return self._tables


class MemoryPackRepository(_Tables):
    def lock_registry(self) -> None:
        self._writable()  # a memory unit of work runs alone: only the write rule of the port is left

    def get(self, pack_id: PackId) -> Pack:
        found = self._tables.packs.get(pack_id)
        if found is None:
            raise _not_found("pack", pack_id)
        return found

    def find_by_slug(self, slug: PackSlug) -> Pack | None:
        return next((pack for pack in self._tables.packs.values() if pack.slug == slug), None)

    def add(self, pack: Pack) -> None:
        tables = self._writable()
        if pack.id in tables.packs:
            raise _exists("packs_pkey")
        if self.find_by_slug(pack.slug) is not None:
            raise _exists("uq_packs__slug")
        tables.packs[pack.id] = pack

    def get_version(self, version_id: PackVersionId) -> PackVersion:
        found = self._tables.pack_versions.get(version_id)
        if found is None:
            raise _not_found("pack_version", version_id)
        return deepcopy(found)

    def find_version(self, pack_id: PackId, version: SemVer) -> PackVersion | None:
        for row in self._tables.pack_versions.values():
            if row.pack_id == pack_id and row.version == version:
                return deepcopy(row)
        return None

    def list_versions(
        self, pack_id: PackId | None = None, *, state: PackState | None = None
    ) -> tuple[PackVersionSummary, ...]:
        tables = self._tables
        rows = [
            pack_summary(tables, row)
            for row in tables.pack_versions.values()
            if (pack_id is None or row.pack_id == pack_id) and (state is None or row.state is state)
        ]
        return tuple(sorted(rows, key=lambda row: (row.slug, str(row.version_id))))

    def add_version(self, version: PackVersion) -> None:
        tables = self._writable()
        if version.pack_id not in tables.packs:
            raise Conflict(
                ErrorCode.INVALID_REFERENCE, "unknown pack", details={"constraint": "fk_pack_versions__packs"}
            )
        if version.id in tables.pack_versions:
            raise _exists("pack_versions_pkey")
        if self.find_version(version.pack_id, version.version) is not None:
            raise _exists("uq_pack_versions__pack_id_version")
        tables.pack_versions[version.id] = deepcopy(version)

    def set_version_state(self, version_id: PackVersionId, state: PackState) -> None:
        tables = self._writable()
        row = tables.pack_versions.get(version_id)
        if row is None:
            raise _not_found("pack_version", version_id)
        if row.state is state:
            return
        if not (row.state is PackState.ACTIVE and state is PackState.RETIRED):
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                "a pack version only retires",
                details={"from": row.state.value, "to": state.value},
            )
        tables.pack_versions[version_id] = replace(row, state=state)


class MemoryResourceRepository(_Tables):
    def find(self, kind: ResourceKind, key: ResourceKey) -> Resource | None:
        return next(
            (row for row in self._tables.resources.values() if row.kind is kind and row.key == key), None
        )

    def add(self, resource: Resource) -> None:
        tables = self._writable()
        if resource.id in tables.resources:
            raise _exists("resources_pkey")
        if self.find(resource.kind, resource.key) is not None:
            raise _exists("uq_resources__kind_key")
        tables.resources[resource.id] = resource

    def add_version(self, version: ResourceVersion, file_bodies: Mapping[str, bytes]) -> None:
        tables = self._writable()
        check_file_bodies(version.files, file_bodies)
        if version.id in tables.versions:
            raise _exists("resource_versions_pkey")
        if any(
            row.resource_id == version.resource_id and row.pack_version_id == version.pack_version_id
            for row in tables.versions.values()
        ):
            raise _exists("uq_resource_versions__resource_id_pack_version_id")
        tables.versions[version.id] = deepcopy(version)
        tables.bodies[version.id] = dict(file_bodies)

    def get_version(
        self, version_id: ResourceVersionId, *, include_bodies: bool = False
    ) -> ResourceVersionWithBodies:
        tables = self._tables
        row = tables.versions.get(version_id)
        if row is None:
            raise _not_found("resource_version", version_id)
        bodies = tables.bodies.get(version_id, {}) if include_bodies else None
        return ResourceVersionWithBodies(deepcopy(row), None if bodies is None else dict(bodies))

    def versions_of(
        self, kind: ResourceKind, key: ResourceKey, pack_version_ids: Sequence[PackVersionId]
    ) -> tuple[ResourceVersionSummary, ...]:
        wanted = set(pack_version_ids)
        return tuple(
            resource_summary(row)
            for row in self._tables.versions.values()
            if row.kind is kind and row.key == key and row.pack_version_id in wanted
        )

    def list_in_pack_versions(
        self, pack_version_ids: Sequence[PackVersionId], *, kind: ResourceKind | None
    ) -> tuple[ResourceVersionSummary, ...]:
        wanted = set(pack_version_ids)
        rows = [
            resource_summary(row)
            for row in self._tables.versions.values()
            if row.pack_version_id in wanted and (kind is None or row.kind is kind)
        ]
        return tuple(sorted(rows, key=lambda row: (row.kind.value, row.key, str(row.id))))

    def owner_trust(self, kind: ResourceKind, key: ResourceKey) -> PackTrust | None:
        tables = self._tables
        resource = self.find(kind, key)
        return None if resource is None else tables.packs[resource.first_pack_id].trust


class MemoryQuarantineRepository(_Tables):
    def quarantined_ids(self, version_ids: Sequence[ResourceVersionId]) -> frozenset[ResourceVersionId]:
        wanted = set(version_ids)
        return frozenset(
            row.resource_version_id
            for row in self._tables.quarantine
            if row.released_at is None and row.resource_version_id in wanted
        )

    def add(self, entry: QuarantineEntry) -> None:
        tables = self._writable()
        if entry.version_id in self.quarantined_ids([entry.version_id]):
            raise _exists("uq_resource_quarantine__resource_version_id_active")
        reason_kind, reasons, report = quarantine_row(entry)
        tables.quarantine.append(
            QuarantineRow(entry.version_id, reason_kind, reasons, report, entry.created_by, entry.created_at)
        )

    def release(self, version_id: ResourceVersionId, *, by: PrincipalId, reason: str, at: datetime) -> None:
        tables = self._writable()
        for row in tables.quarantine:
            if row.resource_version_id == version_id and row.released_at is None:
                row.released_by, row.released_at, row.release_reason = by, at, reason
                return
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "the resource version is not in quarantine",
            details={"resource_version_id": str(version_id)},
        )
