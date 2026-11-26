"""PostgreSQL ``WorkerRepository`` (workspace §6, §11, §13; DDL ``0007``): workers and their capabilities.

A worker belongs to one workspace, one host and one worker principal (``uq_workers__principal_id``).
``capabilities`` holds the ``urn:skm:workspace:worker-capabilities:v1`` document (labels, isolation profiles,
runtimes, platform, concurrency, version); the domain value re-checks it when read. ``add`` runs ``ON CONFLICT
DO NOTHING``; ``save`` locks the row, compares ``row_version`` and keeps workspace, host, principal and the
registration time (``ValueError``). ``heartbeat`` has no version check: the row lock orders concurrent
heartbeats and the last one wins. ``mark_offline_older_than`` is the sweeper transition ``online|draining ->
offline`` in one statement. Pages ascend by ``(registered_at, id)`` per workspace and state; ``online`` orders
by ``(host_id, id)``.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.jsonb import to_jsonb
from skm.adapters.postgres.pagination import page_of, query_digest
from skm.adapters.postgres.workspace.mapping import (
    Row,
    damaged,
    ensure_kept,
    keyset,
    not_found,
    run,
    time_key,
    version_conflict,
)
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.ids import HostId, PrincipalId, WorkerId, WorkspaceId
from skm.kernel.pagination import Page, validate_page_limit
from skm.modules.workspace.domain import worker as worker_rules
from skm.modules.workspace.domain.host import HostArch, HostOs, HostPlatform
from skm.modules.workspace.domain.worker import Worker, WorkerCapabilities, WorkerState
from skm.platform.system_clock import SystemClock

__all__ = ["PostgresWorkerRepository"]

_COLUMNS: Final = (
    "SELECT id, workspace_id, host_id, principal_id, display_name, capabilities, state, last_heartbeat_at, "
    "registered_at, row_version FROM skm_workspace.workers "
)
_GET: Final = _COLUMNS + "WHERE id = %s"
_LOCKED: Final = _GET + " FOR UPDATE"
_OF_PRINCIPAL: Final = _COLUMNS + "WHERE principal_id = %s"
_INSERT: Final = """
INSERT INTO skm_workspace.workers
    (id, workspace_id, host_id, principal_id, display_name, capabilities, state, last_heartbeat_at,
     registered_at, row_version)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING RETURNING id
"""
_UPDATE: Final = """
UPDATE skm_workspace.workers
   SET display_name = %s, capabilities = %s, state = %s, last_heartbeat_at = %s, row_version = %s
 WHERE id = %s
"""
_LIST: Final = (
    _COLUMNS
    + """
 WHERE workspace_id = %(workspace)s
   AND (%(state)s::text IS NULL OR state = %(state)s::text)
   AND (%(at)s::timestamptz IS NULL OR (registered_at, id) > (%(at)s::timestamptz, %(id)s::uuid))
 ORDER BY registered_at, id
 LIMIT %(limit)s
"""
)
_ONLINE: Final = _COLUMNS + "WHERE workspace_id = ANY(%s) AND state = 'online' ORDER BY host_id, id"
_OVERDUE: Final = (
    _COLUMNS
    + "WHERE state IN ('online', 'draining') AND coalesce(last_heartbeat_at, registered_at) < %s ORDER BY id"
)
_MARK_OFFLINE: Final = """
UPDATE skm_workspace.workers SET state = 'offline', row_version = row_version + 1
 WHERE state IN ('online', 'draining') AND coalesce(last_heartbeat_at, registered_at) < %s
RETURNING id
"""
_IDENTITY: Final = ("workspace_id", "host_id", "principal_id", "registered_at")


def _document(capabilities: WorkerCapabilities) -> dict[str, object]:
    """The ``urn:skm:workspace:worker-capabilities:v1`` document stored in ``workers.capabilities``."""
    return {
        "runtimes": list(capabilities.runtimes),
        "isolation_profiles": list(capabilities.isolation_profiles),
        "max_concurrency": capabilities.max_concurrency,
        "labels": list(capabilities.labels),
        "platform": {"os": capabilities.platform.os.value, "arch": capabilities.platform.arch.value},
        "skm_version": capabilities.skm_version,
    }


def _capabilities(value: object) -> WorkerCapabilities:
    document = cast("dict[str, object]", value)
    platform = cast("dict[str, str]", document["platform"])
    return WorkerCapabilities(
        runtimes=tuple(cast("list[str]", document["runtimes"])),
        isolation_profiles=tuple(cast("list[str]", document["isolation_profiles"])),
        max_concurrency=cast("int", document["max_concurrency"]),
        labels=tuple(cast("list[str]", document["labels"])),
        platform=HostPlatform(os=HostOs(platform["os"]), arch=HostArch(platform["arch"])),
        skm_version=cast("str", document["skm_version"]),
    )


def _worker(row: Row) -> Worker:
    try:
        return Worker(
            id=WorkerId(cast("UUID", row[0])),
            workspace_id=WorkspaceId(cast("UUID", row[1])),
            host_id=HostId(cast("UUID", row[2])),
            principal_id=PrincipalId(cast("UUID", row[3])),
            display_name=cast("str", row[4]),
            capabilities=_capabilities(row[5]),
            state=WorkerState(cast("str", row[6])),
            last_heartbeat_at=cast("datetime | None", row[7]),
            registered_at=cast("datetime", row[8]),
            row_version=cast("int", row[9]),
        )
    except (TypeError, ValueError, KeyError, ValidationFailed) as exc:
        raise damaged("workers", row[0], exc) from exc


class PostgresWorkerRepository:
    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def _locked(self, worker_id: WorkerId) -> Worker:
        row = run(lambda: self._conn.execute(_LOCKED, (worker_id,)).fetchone())
        if row is None:
            raise not_found("worker", worker_id)
        return _worker(row)

    def _write(self, current: Worker, worker: Worker) -> None:
        ensure_kept("worker", current, worker, _IDENTITY)
        params = (
            worker.display_name,
            to_jsonb(_document(worker.capabilities)),
            WorkerState(worker.state).value,
            worker.last_heartbeat_at,
            worker.row_version,
            worker.id,
        )
        run(lambda: self._conn.execute(_UPDATE, params))

    def get(self, worker_id: WorkerId) -> Worker:
        row = run(lambda: self._conn.execute(_GET, (worker_id,)).fetchone())
        if row is None:
            raise not_found("worker", worker_id)
        return _worker(row)

    def add(self, worker: Worker) -> None:
        params = (
            worker.id,
            worker.workspace_id,
            worker.host_id,
            worker.principal_id,
            worker.display_name,
            to_jsonb(_document(worker.capabilities)),
            WorkerState(worker.state).value,
            worker.last_heartbeat_at,
            worker.registered_at,
            worker.row_version,
        )
        if run(lambda: self._conn.execute(_INSERT, params).fetchone()) is None:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "worker already exists", details={"kind": "worker"})

    def save(self, worker: Worker, *, expected_version: int) -> None:
        current = self._locked(worker.id)
        if current.row_version != expected_version:
            raise version_conflict("worker", expected_version, current.row_version)
        self._write(current, worker)

    def heartbeat(self, worker_id: WorkerId, at: datetime, capabilities: WorkerCapabilities | None) -> Worker:
        """Last writer wins: no version check; a retired worker is refused by the domain rule."""
        current = self._locked(worker_id)
        beaten = worker_rules.heartbeat(current, capabilities, at)
        self._write(current, beaten)
        return beaten

    def list(
        self, workspace_id: WorkspaceId, *, state: WorkerState | None, after: str | None, limit: int
    ) -> Page[Worker]:
        limit = validate_page_limit(limit)
        state_value = None if state is None else WorkerState(state).value
        digest = query_digest(
            {"kind": "workspace_workers", "workspace_id": str(workspace_id), "state": state_value}
        )
        at, start = keyset(after, digest, time_key)
        params = {"workspace": workspace_id, "state": state_value, "at": at, "id": start, "limit": limit + 1}
        rows = run(lambda: self._conn.execute(_LIST, params).fetchall())
        return page_of(
            [_worker(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda item: (item.registered_at.isoformat(), str(item.id)),
        )

    def for_principal(self, principal_id: PrincipalId) -> Worker | None:
        row = run(lambda: self._conn.execute(_OF_PRINCIPAL, (principal_id,)).fetchone())
        return None if row is None else _worker(row)

    def online(self, workspace_ids: Sequence[WorkspaceId]) -> tuple[Worker, ...]:
        wanted = list(dict.fromkeys(workspace_ids))
        if not wanted:
            return ()
        rows = run(lambda: self._conn.execute(_ONLINE, (wanted,)).fetchall())
        return tuple(_worker(row) for row in rows)

    def overdue(self, cutoff: datetime) -> tuple[Worker, ...]:
        """Live workers (online or draining) whose last heartbeat, or registration, is before ``cutoff``."""
        rows = run(lambda: self._conn.execute(_OVERDUE, (cutoff,)).fetchall())
        return tuple(_worker(row) for row in rows)

    def mark_offline_older_than(self, cutoff: datetime) -> tuple[WorkerId, ...]:
        rows = run(lambda: self._conn.execute(_MARK_OFFLINE, (cutoff,)).fetchall())
        return tuple(sorted((WorkerId(cast("UUID", row[0])) for row in rows), key=str))
