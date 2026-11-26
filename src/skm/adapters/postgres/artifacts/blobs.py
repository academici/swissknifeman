"""PostgreSQL blobs repositories with local parameterized SQL (artifacts §6, §11).

Connections belong to the surrounding UoW; checked row decoding lives in mapping.py.
"""

from datetime import datetime
from typing import BinaryIO, Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.artifacts import mapping
from skm.adapters.postgres.jsonb import require_aware
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, InternalError
from skm.kernel.ids import WorkspaceId
from skm.modules.artifacts.domain.blob import (
    Blob,
    BlobAvailability,
    BlobId,
    BlobLocation,
    ContentDigest,
    LocationState,
)
from skm.modules.artifacts.domain.staged_blob import StagedBlob, StagedBlobId
from skm.modules.artifacts.ports import BlobLocationRef, BlobStore

__all__ = ["PostgresBlobContentReader", "PostgresBlobRepository", "PostgresStagedBlobRepository"]

_STAGED_COLS: Final = (
    "SELECT id, workspace_id, content_digest, size_bytes, media_type, detected_media_type, "
    "backend_id, storage_key, created_by, created_at, expires_at, consumed_at, consumed_request_id "
    "FROM skm_artifacts.staged_blobs "
)

_STAGED_FOR_UPDATE: Final = _STAGED_COLS + "WHERE id = %s FOR UPDATE"

_STAGED_INSERT: Final = (
    "INSERT INTO skm_artifacts.staged_blobs (id, workspace_id, content_digest, size_bytes, media_type, "
    "detected_media_type, backend_id, storage_key, created_by, created_at, expires_at, consumed_at, "
    "consumed_request_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (id) DO NOTHING RETURNING id"
)

_STAGED_UPDATE: Final = (
    "UPDATE skm_artifacts.staged_blobs SET media_type = %s, detected_media_type = %s, expires_at = %s, "
    "consumed_at = %s, consumed_request_id = %s WHERE id = %s"
)

_STAGED_EXPIRED_DIGESTS: Final = (
    "SELECT workspace_id, content_digest, backend_id FROM skm_artifacts.staged_blobs "
    "WHERE consumed_at IS NULL AND expires_at <= %s ORDER BY expires_at, id LIMIT %s"
)

_STAGED_EXPIRED: Final = (
    _STAGED_COLS
    + "WHERE consumed_at IS NULL AND expires_at <= %s ORDER BY expires_at, id LIMIT %s FOR UPDATE SKIP LOCKED"
)

_STAGED_PURGE_CONSUMED: Final = (
    "DELETE FROM skm_artifacts.staged_blobs WHERE id IN ("
    "SELECT id FROM skm_artifacts.staged_blobs "
    "WHERE consumed_at IS NOT NULL AND consumed_at <= %s "
    "ORDER BY consumed_at, id LIMIT %s FOR UPDATE SKIP LOCKED"
    ") RETURNING id"
)

_STAGED_DELETE: Final = "DELETE FROM skm_artifacts.staged_blobs WHERE id = %s"

_KEY_REFERENCED: Final = (
    "SELECT EXISTS (SELECT 1 FROM skm_artifacts.blob_locations WHERE backend_id = %s AND storage_key = %s) "
    "OR EXISTS (SELECT 1 FROM skm_artifacts.staged_blobs "
    "WHERE consumed_at IS NULL AND backend_id = %s AND storage_key = %s)"
)

_BLOB_COLS: Final = (
    "SELECT id, workspace_id, content_digest, size_bytes, detected_media_type, availability, created_at, "
    "verified_at FROM skm_artifacts.blobs "
)

_BLOB_GET: Final = _BLOB_COLS + "WHERE id = %s"

_BLOB_FIND: Final = (
    _BLOB_COLS
    + "WHERE workspace_id = %s AND hash_algorithm = 'sha256' AND content_digest = %s AND size_bytes = %s"
)

_BLOB_INSERT: Final = (
    "INSERT INTO skm_artifacts.blobs (id, workspace_id, hash_algorithm, content_digest, size_bytes, "
    "detected_media_type, availability, created_at, verified_at) "
    "VALUES (%s, %s, 'sha256', %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id"
)

_LOCATION_INSERT: Final = (
    "INSERT INTO skm_artifacts.blob_locations (workspace_id, blob_id, backend_id, storage_key, "
    "storage_version, state, verified_at) VALUES (%s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT DO NOTHING RETURNING blob_id"
)

_LOCATIONS_FOR_BLOB: Final = (
    "SELECT blob_id, backend_id, storage_key, storage_version, state, verified_at "
    'FROM skm_artifacts.blob_locations WHERE blob_id = %s ORDER BY backend_id COLLATE "C"'
)

_LOCATION_MARK: Final = (
    "UPDATE skm_artifacts.blob_locations SET state = %s, verified_at = %s "
    "WHERE blob_id = %s AND backend_id = %s RETURNING blob_id"
)

_ALL_KEYS: Final = (
    "SELECT storage_key FROM skm_artifacts.blob_locations WHERE workspace_id = %s AND backend_id = %s"
)

_ENTRIES_IN_BACKEND: Final = (
    "SELECT blob_id, storage_key FROM skm_artifacts.blob_locations "
    'WHERE workspace_id = %s AND backend_id = %s ORDER BY storage_key COLLATE "C", blob_id'
)


class PostgresBlobContentReader:
    """``BlobContentReader`` over a host-bound ``BlobStore``; unbound until composition supplies a store."""

    def __init__(self, conn: psycopg.Connection, *, store: BlobStore | None = None) -> None:
        self._conn, self._store = conn, store

    def open(self, location: BlobLocationRef) -> BinaryIO:
        if self._store is None:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "no blob store is bound to this backend",
                details={"capability": "blob_content"},
            )
        return self._store.open(location)


class PostgresStagedBlobRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, staged: StagedBlob) -> None:
        s = staged
        params = (
            s.id, s.workspace_id, mapping.hex_of(s.digest), s.size_bytes, s.media_type, s.detected_media_type,
            s.backend_id, s.storage_key, s.created_by, require_aware(s.created_at),
            require_aware(s.expires_at), mapping.opt_aware(s.consumed_at), s.consumed_request_id,
        )  # fmt: skip
        row = mapping.in_savepoint(
            self._conn, lambda: mapping.run(lambda: self._conn.execute(_STAGED_INSERT, params).fetchone())
        )
        if row is None:
            raise mapping.exists("staged_blob", ref=str(staged.id))

    def get_for_update(self, staged_blob_id: StagedBlobId) -> StagedBlob:
        row = mapping.run(lambda: self._conn.execute(_STAGED_FOR_UPDATE, (staged_blob_id,)).fetchone())
        if row is None:
            raise mapping.not_found("staged_blob", staged_blob_id)
        return mapping.staged_blob_from_row(row)

    def save(self, staged: StagedBlob) -> None:
        row = mapping.run(lambda: self._conn.execute(_STAGED_FOR_UPDATE, (staged.id,)).fetchone())
        if row is None:
            raise mapping.not_found("staged_blob", staged.id)
        stored = mapping.staged_blob_from_row(row)
        if stored.consumed_at is not None and staged.consumed_at != stored.consumed_at:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "staged blob is already consumed",
                details={"reason": "consumed_twice", "staged_blob_id": str(staged.id)},
            )
        kept = (
            "workspace_id",
            "digest",
            "size_bytes",
            "backend_id",
            "storage_key",
            "created_by",
            "created_at",
        )
        mapping.ensure_kept("staged_blob", stored, staged, kept)
        params = (
            staged.media_type, staged.detected_media_type, require_aware(staged.expires_at),
            mapping.opt_aware(staged.consumed_at), staged.consumed_request_id, staged.id,
        )  # fmt: skip
        mapping.in_savepoint(
            self._conn, lambda: mapping.run(lambda: self._conn.execute(_STAGED_UPDATE, params))
        )

    def expired_digests(
        self, now: datetime, *, limit: int
    ) -> tuple[tuple[WorkspaceId, ContentDigest, str], ...]:
        require_aware(now)
        if limit <= 0:
            return ()
        rows = mapping.run(lambda: self._conn.execute(_STAGED_EXPIRED_DIGESTS, (now, limit)).fetchall())
        seen: dict[tuple[str, str, str], tuple[WorkspaceId, ContentDigest, str]] = {}
        for row in rows:
            ws_id = WorkspaceId(cast("UUID", row[0]))
            digest = ContentDigest(f"sha256:{cast('str', row[1])}")
            backend_id = cast("str", row[2])
            seen[(backend_id, str(ws_id), digest.value)] = (ws_id, digest, backend_id)
        return tuple(seen[key] for key in sorted(seen))

    def expired(self, now: datetime, *, limit: int) -> tuple[StagedBlob, ...]:
        require_aware(now)
        if limit <= 0:
            return ()
        rows = mapping.run(lambda: self._conn.execute(_STAGED_EXPIRED, (now, limit)).fetchall())
        return tuple(mapping.staged_blob_from_row(row) for row in rows)

    def purge_consumed(self, before: datetime, *, limit: int) -> int:
        require_aware(before)
        if limit <= 0:
            return 0
        rows = mapping.run(lambda: self._conn.execute(_STAGED_PURGE_CONSUMED, (before, limit)).fetchall())
        return len(rows)

    def delete(self, staged_blob_id: StagedBlobId) -> None:
        mapping.run(lambda: self._conn.execute(_STAGED_DELETE, (staged_blob_id,)))

    def key_referenced(self, backend_id: str, storage_key: str) -> bool:
        params = (backend_id, storage_key, backend_id, storage_key)
        row = mapping.run(lambda: self._conn.execute(_KEY_REFERENCED, params).fetchone())
        return bool(row and row[0])


class PostgresBlobRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def find(self, workspace_id: WorkspaceId, digest: ContentDigest, size_bytes: int) -> Blob | None:
        row = mapping.run(
            lambda: self._conn.execute(
                _BLOB_FIND, (workspace_id, mapping.hex_of(digest), size_bytes)
            ).fetchone()
        )
        return None if row is None else mapping.blob_from_row(row)

    def get(self, blob_id: BlobId) -> Blob:
        row = mapping.run(lambda: self._conn.execute(_BLOB_GET, (blob_id,)).fetchone())
        if row is None:
            raise mapping.not_found("blob", blob_id)
        return mapping.blob_from_row(row)

    def add(self, blob: Blob, location: BlobLocation) -> None:
        if location.blob_id != blob.id:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "blob location names another blob",
                details={"reason": "foreign_location"},
            )
        b, loc = blob, location
        blob_params = (
            b.id, b.workspace_id, mapping.hex_of(b.digest), b.size_bytes, b.detected_media_type,
            BlobAvailability(b.availability).value, require_aware(b.created_at),
            mapping.opt_aware(b.verified_at),
        )  # fmt: skip
        loc_params = (
            b.workspace_id, b.id, loc.backend_id, loc.storage_key, loc.storage_version,
            LocationState(loc.state).value, mapping.opt_aware(loc.verified_at),
        )  # fmt: skip

        def write() -> None:
            if mapping.run(lambda: self._conn.execute(_BLOB_INSERT, blob_params).fetchone()) is None:
                raise mapping.exists("blob", digest=blob.digest.value)
            if mapping.run(lambda: self._conn.execute(_LOCATION_INSERT, loc_params).fetchone()) is None:
                raise mapping.exists("blob", digest=blob.digest.value)

        mapping.in_savepoint(self._conn, write)

    def locations(self, blob_id: BlobId) -> tuple[BlobLocation, ...]:
        rows = mapping.run(lambda: self._conn.execute(_LOCATIONS_FOR_BLOB, (blob_id,)).fetchall())
        return tuple(mapping.blob_location_from_row(row) for row in rows)

    def mark_location(self, blob_id: BlobId, backend_id: str, state: LocationState, at: datetime) -> None:
        params = (LocationState(state).value, require_aware(at), blob_id, backend_id)
        if mapping.run(lambda: self._conn.execute(_LOCATION_MARK, params).fetchone()) is None:
            raise mapping.not_found("blob_location", f"{blob_id}/{backend_id}")

    def all_keys(self, workspace_id: WorkspaceId, backend_id: str) -> frozenset[str]:
        rows = mapping.run(lambda: self._conn.execute(_ALL_KEYS, (workspace_id, backend_id)).fetchall())
        return frozenset(cast("str", row[0]) for row in rows)

    def entries_in_backend(
        self, workspace_id: WorkspaceId, backend_id: str
    ) -> tuple[tuple[BlobId, str], ...]:
        rows = mapping.run(
            lambda: self._conn.execute(_ENTRIES_IN_BACKEND, (workspace_id, backend_id)).fetchall()
        )
        return tuple((BlobId(cast("UUID", row[0])), cast("str", row[1])) for row in rows)
