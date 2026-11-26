"""PostgreSQL ``HostRepository`` (workspace §6, §11; DDL ``0007``): hosts of the instance.

A host has no workspace (its scope's parent is the instance) and never carries a locator. ``add`` runs
``ON CONFLICT DO NOTHING`` (a taken id or name is ``ALREADY_EXISTS``); ``save`` locks the row, compares
``row_version`` and keeps the name and the registration time (``ValueError``). ``touch`` is liveness only: it
moves ``last_seen_at`` forward and keeps ``row_version``. Pages ascend by ``(name, id)``, filtered by state.
"""

from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.pagination import page_of, query_digest
from skm.adapters.postgres.workspace.mapping import (
    Row,
    damaged,
    ensure_kept,
    keyset,
    not_found,
    run,
    text_key,
    version_conflict,
)
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import HostId
from skm.kernel.pagination import Page, validate_page_limit
from skm.modules.workspace.domain.host import Host, HostArch, HostOs, HostPlatform, HostState
from skm.platform.system_clock import SystemClock

__all__ = ["PostgresHostRepository"]

_COLUMNS: Final = (
    "SELECT id, name, os, arch, state, registered_at, last_seen_at, row_version FROM skm_workspace.hosts "
)
_GET: Final = _COLUMNS + "WHERE id = %s"
_LOCKED: Final = _GET + " FOR UPDATE"
_BY_NAME: Final = _COLUMNS + "WHERE name = %s"
_EXISTS: Final = "SELECT 1 FROM skm_workspace.hosts WHERE id = %s"
_INSERT: Final = """
INSERT INTO skm_workspace.hosts (id, name, os, arch, state, row_version, registered_at, last_seen_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING RETURNING id
"""
_UPDATE: Final = """
UPDATE skm_workspace.hosts SET os = %s, arch = %s, state = %s, last_seen_at = %s, row_version = %s
 WHERE id = %s AND row_version = %s
"""
_TOUCH: Final = """
UPDATE skm_workspace.hosts SET last_seen_at = %(at)s
 WHERE id = %(id)s AND (last_seen_at IS NULL OR last_seen_at < %(at)s)
RETURNING id
"""
_LIST: Final = (
    _COLUMNS
    + """
 WHERE (%(state)s::text IS NULL OR state = %(state)s::text)
   AND (%(at)s::text IS NULL OR (name COLLATE "C", id) > (%(at)s::text COLLATE "C", %(id)s::uuid))
 ORDER BY name COLLATE "C", id
 LIMIT %(limit)s
"""
)


def _host(row: Row) -> Host:
    try:
        return Host(
            id=HostId(cast("UUID", row[0])),
            name=cast("str", row[1]),
            platform=HostPlatform(os=HostOs(cast("str", row[2])), arch=HostArch(cast("str", row[3]))),
            state=HostState(cast("str", row[4])),
            registered_at=cast("datetime", row[5]),
            last_seen_at=cast("datetime | None", row[6]),
            row_version=cast("int", row[7]),
        )
    except (TypeError, ValueError) as exc:
        raise damaged("hosts", row[0], exc) from exc


class PostgresHostRepository:
    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def get(self, host_id: HostId) -> Host:
        row = run(lambda: self._conn.execute(_GET, (host_id,)).fetchone())
        if row is None:
            raise not_found("host", host_id)
        return _host(row)

    def find_by_name(self, name: str) -> Host | None:
        row = run(lambda: self._conn.execute(_BY_NAME, (name,)).fetchone())
        return None if row is None else _host(row)

    def add(self, host: Host) -> None:
        params = (
            host.id,
            host.name,
            HostOs(host.platform.os).value,
            HostArch(host.platform.arch).value,
            HostState(host.state).value,
            host.row_version,
            host.registered_at,
            host.last_seen_at,
        )
        if run(lambda: self._conn.execute(_INSERT, params).fetchone()) is None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS, "host already exists", details={"kind": "host", "name": host.name}
            )

    def save(self, host: Host, *, expected_version: int) -> None:
        row = run(lambda: self._conn.execute(_LOCKED, (host.id,)).fetchone())
        if row is None:
            raise not_found("host", host.id)
        current = _host(row)
        if current.row_version != expected_version:
            raise version_conflict("host", expected_version, current.row_version)
        ensure_kept("host", current, host, ("name", "registered_at"))
        params = (
            HostOs(host.platform.os).value,
            HostArch(host.platform.arch).value,
            HostState(host.state).value,
            host.last_seen_at,
            host.row_version,
            host.id,
            expected_version,
        )
        run(lambda: self._conn.execute(_UPDATE, params))

    def touch(self, host_id: HostId, at: datetime) -> None:
        """Liveness only: ``last_seen_at`` moves forward, ``row_version`` stays."""
        if run(lambda: self._conn.execute(_TOUCH, {"id": host_id, "at": at}).fetchone()) is not None:
            return
        if run(lambda: self._conn.execute(_EXISTS, (host_id,)).fetchone()) is None:
            raise not_found("host", host_id)

    def list(self, *, state: HostState | None, after: str | None, limit: int) -> Page[Host]:
        limit = validate_page_limit(limit)
        state_value = None if state is None else HostState(state).value
        digest = query_digest({"kind": "workspace_hosts", "state": state_value})
        at, start = keyset(after, digest, text_key)
        params = {"state": state_value, "at": at, "id": start, "limit": limit + 1}
        rows = run(lambda: self._conn.execute(_LIST, params).fetchall())
        return page_of(
            [_host(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda item: (item.name, str(item.id)),
        )
