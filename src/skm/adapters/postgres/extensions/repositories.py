"""PostgreSQL adapters of the extensions repository ports (extensions §6, §11; DDL ``0018``).

The triggers of ``0018`` keep packs, resources, versions and files immutable; the only updates here are the
state of a pack version and the release of a quarantine row. Bodies are read only on ``include_bodies=True``.
``lock_registry`` is a transaction advisory lock: a pack that does not exist yet has no row to lock.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.extensions import queries as sql
from skm.adapters.postgres.extensions.mapping import (
    not_found,
    pack_from_row,
    pack_summary_from_row,
    pack_version_from_row,
    resource_from_row,
    resource_summary_from_row,
    resource_version_from_row,
    run,
)
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.ids import PrincipalId, ResourceVersionId
from skm.modules.extensions.domain.keys import PackId, PackSlug, PackVersionId, ResourceKey, SemVer
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.pack import (
    Pack,
    PackState,
    PackTrust,
    PackVersion,
    PackVersionSummary,
    manifest_to_json,
)
from skm.modules.extensions.domain.quarantine import QuarantineEntry
from skm.modules.extensions.domain.resource import (
    Resource,
    ResourceVersion,
    ResourceVersionSummary,
    ResourceVersionWithBodies,
    check_file_bodies,
    compat_report_to_json,
    quarantine_row,
)

__all__ = [
    "PostgresPackRepository",
    "PostgresQuarantineRepository",
    "PostgresResourceRepository",
]


class PostgresPackRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def lock_registry(self) -> None:
        run(lambda: sql.lock_registry(self._conn))

    def get(self, pack_id: PackId) -> Pack:
        row = run(lambda: sql.get_pack(self._conn, (pack_id,)))
        if row is None:
            raise not_found("pack", pack_id)
        return pack_from_row(row)

    def find_by_slug(self, slug: PackSlug) -> Pack | None:
        row = run(lambda: sql.find_pack_by_slug(self._conn, (slug,)))
        return None if row is None else pack_from_row(row)

    def add(self, pack: Pack) -> None:
        params = (
            pack.id,
            pack.slug,
            pack.title,
            pack.publisher,
            pack.trust.value,
            require_aware(pack.created_at),
        )
        run(lambda: sql.add_pack(self._conn, params))

    def get_version(self, version_id: PackVersionId) -> PackVersion:
        row = run(lambda: sql.get_pack_version(self._conn, (version_id,)))
        if row is None:
            raise not_found("pack_version", version_id)
        return pack_version_from_row(row)

    def find_version(self, pack_id: PackId, version: SemVer) -> PackVersion | None:
        row = run(lambda: sql.find_pack_version(self._conn, (pack_id, str(version))))
        return None if row is None else pack_version_from_row(row)

    def list_versions(
        self, pack_id: PackId | None = None, *, state: PackState | None = None
    ) -> tuple[PackVersionSummary, ...]:
        params = {"pack_id": pack_id, "state": None if state is None else state.value}
        rows = run(lambda: sql.summaries(self._conn, params))
        return tuple(pack_summary_from_row(row) for row in rows)

    def add_version(self, version: PackVersion) -> None:
        semver = version.version
        params = (
            version.id,
            version.pack_id,
            str(semver),
            semver.major,
            semver.minor,
            semver.patch,
            semver.prerelease,
            version.digest,
            to_jsonb(manifest_to_json(version.manifest)),
            version.manifest.priority,
            version.state.value,
            version.origin,
            require_aware(version.installed_at),
            version.installed_by,
        )
        run(lambda: sql.add_pack_version(self._conn, params))

    def set_version_state(self, version_id: PackVersionId, state: PackState) -> None:
        current = run(lambda: sql.pack_version_state(self._conn, (version_id,)))
        if current is None:
            raise not_found("pack_version", version_id)
        if current[0] == state.value:
            return
        if state is not PackState.RETIRED or (
            run(lambda: sql.retire_pack_version(self._conn, (version_id,))) is None
        ):
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                "a pack version only retires",
                details={"from": str(current[0]), "to": state.value},
            )


class PostgresResourceRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def find(self, kind: ResourceKind, key: ResourceKey) -> Resource | None:
        row = run(lambda: sql.find_resource(self._conn, (kind.value, key)))
        return None if row is None else resource_from_row(row)

    def add(self, resource: Resource) -> None:
        params = (
            resource.id,
            resource.kind.value,
            resource.key,
            resource.first_pack_id,
            require_aware(resource.created_at),
        )
        run(lambda: sql.add_resource(self._conn, params))

    def add_version(self, version: ResourceVersion, file_bodies: Mapping[str, bytes]) -> None:
        check_file_bodies(version.files, file_bodies)
        params = (
            version.id,
            version.resource_id,
            version.pack_version_id,
            str(version.version),
            version.digest,
            to_jsonb(dict(version.manifest)),
            version.tokens_estimate,
            version.compat.verdict.value,
            to_jsonb(compat_report_to_json(version.compat)),
            require_aware(version.created_at),
        )
        run(lambda: sql.add_resource_version(self._conn, params))
        rows = [
            (version.id, item.path, item.size_bytes, item.digest, item.media_type, file_bodies[item.path])
            for item in version.files
        ]
        if rows:
            run(lambda: sql.add_resource_files(self._conn, rows))

    def get_version(
        self, version_id: ResourceVersionId, *, include_bodies: bool = False
    ) -> ResourceVersionWithBodies:
        row = run(lambda: sql.get_resource_version(self._conn, (version_id,)))
        if row is None:
            raise not_found("resource_version", version_id)
        files = tuple(run(lambda: sql.resource_files(self._conn, (version_id,))))
        bodies: dict[str, bytes] | None = None
        if include_bodies:
            stored = run(lambda: sql.resource_bodies(self._conn, (version_id,)))
            bodies = {cast("str", item[0]): bytes(cast("bytes", item[1])) for item in stored}
        return ResourceVersionWithBodies(resource_version_from_row(row, files), bodies)

    def versions_of(
        self, kind: ResourceKind, key: ResourceKey, pack_version_ids: Sequence[PackVersionId]
    ) -> tuple[ResourceVersionSummary, ...]:
        params = (kind.value, key, _ids(pack_version_ids))
        rows = run(lambda: sql.versions_of(self._conn, params))
        return tuple(resource_summary_from_row(row) for row in rows)

    def list_in_pack_versions(
        self, pack_version_ids: Sequence[PackVersionId], *, kind: ResourceKind | None
    ) -> tuple[ResourceVersionSummary, ...]:
        ids = _ids(pack_version_ids)
        if kind is None:
            rows = run(lambda: sql.in_pack_versions(self._conn, (ids,)))
        else:
            rows = run(lambda: sql.in_pack_versions_of_kind(self._conn, (ids, kind.value)))
        return tuple(resource_summary_from_row(row) for row in rows)

    def owner_trust(self, kind: ResourceKind, key: ResourceKey) -> PackTrust | None:
        row = run(lambda: sql.owner_trust(self._conn, (kind.value, key)))
        return None if row is None else PackTrust(cast("str", row[0]))


class PostgresQuarantineRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def quarantined_ids(self, version_ids: Sequence[ResourceVersionId]) -> frozenset[ResourceVersionId]:
        rows = run(lambda: sql.quarantined(self._conn, (_ids(version_ids),)))
        return frozenset(ResourceVersionId(cast("UUID", row[0])) for row in rows)

    def add(self, entry: QuarantineEntry) -> None:
        reason_kind, reasons, report = quarantine_row(entry)
        params = (
            entry.version_id,
            reason_kind,
            to_jsonb(reasons),
            None if report is None else to_jsonb(report),
            entry.created_by,
            require_aware(entry.created_at),
        )
        run(lambda: sql.add_quarantine(self._conn, params))

    def release(self, version_id: ResourceVersionId, *, by: PrincipalId, reason: str, at: datetime) -> None:
        params = (by, require_aware(at), reason, version_id)
        if run(lambda: sql.release_quarantine(self._conn, params)) is None:
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                "the resource version is not in quarantine",
                details={"resource_version_id": str(version_id)},
            )


def _ids(values: Sequence[UUID]) -> list[UUID]:
    return list(values)
