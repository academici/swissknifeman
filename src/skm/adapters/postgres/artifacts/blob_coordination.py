"""PostgreSQL ``BlobCoordination`` and transaction digest lock (artifacts §6.1, adapters §1.2)."""

import hashlib
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from typing import Any, Final
from uuid import UUID

import psycopg
import psycopg_pool

from skm.adapters.postgres.artifacts.repositories import PostgresBlobContentReader
from skm.adapters.postgres.connection import PgSettings
from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.pool import PoolHandle, create_pool
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import WorkspaceId
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.staged_blob import StagedBlobId
from skm.modules.artifacts.ports import BlobContentReader, BlobCoordination, BlobStore

__all__ = [
    "PostgresBlobCoordination",
    "PostgresBlobDigestLock",
    "bind_postgres_artifacts",
    "create_coordination_pool",
    "digest_lock_key",
]

_LOCK_SESSION: Final = "SELECT pg_advisory_lock(%s)"
_UNLOCK_SESSION: Final = "SELECT pg_advisory_unlock(%s)"
_LOCK_XACT: Final = "SELECT pg_advisory_xact_lock(%s)"
_STAGED_DIGEST: Final = (
    "SELECT workspace_id, content_digest, backend_id FROM skm_artifacts.staged_blobs WHERE id = %s"
)


def digest_lock_key(workspace_id: WorkspaceId, digest: ContentDigest, backend_id: str) -> int:
    """Signed 64-bit PostgreSQL advisory lock key for ``(backend_id, workspace_id, digest)`` (§6.1)."""
    payload = (
        b"skm-blob-v1\0"
        + backend_id.encode("utf-8")
        + b"\0"
        + str(workspace_id).encode("utf-8")
        + b"\0"
        + digest.value.encode("utf-8")
    )
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=True)


def create_coordination_pool(
    dsn: str, *, application_name: str, uow_max_size: int, timeout_seconds: int
) -> PoolHandle:
    """Dedicated bounded pool for session-scoped ``BlobCoordination.hold`` (never shared with UoW)."""
    return create_pool(
        PgSettings(
            dsn=dsn,
            application_name=application_name,
            pool_min_size=0,
            pool_max_size=max(2, min(uow_max_size, 8)),
            pool_timeout_seconds=timeout_seconds,
        )
    )


class PostgresBlobCoordination:
    """Session-scoped ``pg_advisory_lock`` over a dedicated bounded ``PoolHandle`` (artifacts §6.1)."""

    def __init__(self, pool: PoolHandle) -> None:
        self._pool = pool

    @contextmanager
    def hold(self, workspace_id: WorkspaceId, digest: ContentDigest, backend_id: str) -> Generator[None]:
        key = digest_lock_key(workspace_id, digest, backend_id)
        try:
            conn = self._pool.getconn()
        except psycopg_pool.PoolClosed as exc:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                "coordination connection pool is closed",
                details={"reason": "pool_closed"},
            ) from exc
        try:
            conn.execute(_LOCK_SESSION, (key,))
            conn.commit()
        except psycopg.Error as exc:
            with suppress(Exception):
                conn.close()
            self._pool.putconn(conn)
            raise translate_pg_error(exc) from exc
        except BaseException:
            with suppress(Exception):
                conn.close()
            self._pool.putconn(conn)
            raise
        try:
            yield
        finally:
            try:
                row = conn.execute(_UNLOCK_SESSION, (key,)).fetchone()
                conn.commit()
                if row is None or not bool(row[0]):
                    conn.close()
            except BaseException:  # noqa: BLE001 - dropping the session frees its advisory locks
                with suppress(Exception):
                    conn.close()
            finally:
                self._pool.putconn(conn)


class PostgresBlobDigestLock:
    """Transaction-scoped ``pg_advisory_xact_lock`` acquired before metadata row locks (artifacts §6.1)."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def lock_digest(self, workspace_id: WorkspaceId, digest: ContentDigest, backend_id: str) -> None:
        key = digest_lock_key(workspace_id, digest, backend_id)
        try:
            self._conn.execute(_LOCK_XACT, (key,))
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc

    def lock_staged(self, workspace_id: WorkspaceId, staged_blob_id: StagedBlobId) -> None:
        try:
            row = self._conn.execute(_STAGED_DIGEST, (staged_blob_id,)).fetchone()
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc
        if row is None:
            return
        row_workspace = WorkspaceId(row[0] if isinstance(row[0], UUID) else UUID(str(row[0])))
        if row_workspace == workspace_id:
            raw = str(row[1])
            digest = ContentDigest(raw if raw.startswith("sha256:") else f"sha256:{raw}")
            self.lock_digest(workspace_id, digest, str(row[2]))


def bind_postgres_artifacts(
    dsn: str,
    application_name: str,
    uow_max_size: int,
    timeout_seconds: int,
    supplied: GatewayTable | None,
    default_store: Callable[[], BlobStore],
) -> tuple[dict[type[object], object], dict[type, Callable[[Any], object]], PoolHandle | None]:
    store = supplied.get(BlobStore) if supplied is not None and supplied.has(BlobStore) else default_store()
    coord_pool: PoolHandle | None = None
    if supplied is not None and supplied.has(BlobCoordination):
        coord = supplied.get(BlobCoordination)
    else:
        coord_pool = create_coordination_pool(
            dsn, application_name=application_name, uow_max_size=uow_max_size, timeout_seconds=timeout_seconds
        )
        coord = PostgresBlobCoordination(coord_pool)
    repos: dict[type, Callable[[Any], object]] = {
        BlobContentReader: lambda conn, s=store: PostgresBlobContentReader(conn, store=s)
    }
    return {BlobStore: store, BlobCoordination: coord}, repos, coord_pool
