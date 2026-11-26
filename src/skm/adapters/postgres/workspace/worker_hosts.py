"""PostgreSQL ``access.WorkerHostLookup`` (access §4.4, §6; workspace §3, §18 K17).

The port belongs to ``access``; the workspace adapters implement it because the workers live in
``skm_workspace``. It reads host and workspace scopes of non-retired workers in the caller's statement
snapshot, so a retirement committed before authorization is visible.
"""

from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.workspace.mapping import run
from skm.kernel.clock import Clock
from skm.kernel.ids import PrincipalId, ScopeId

__all__ = ["PostgresWorkerHostLookup"]

_HOSTS: Final = (
    "SELECT DISTINCT host_id FROM skm_workspace.workers WHERE principal_id = %s AND state <> 'retired'"
)
_WORKSPACE: Final = (
    "SELECT workspace_id FROM skm_workspace.workers WHERE principal_id = %s AND state <> 'retired'"
)


class PostgresWorkerHostLookup:
    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        del clock  # the uniform factory signature of the workspace adapters; no time is read here
        self._conn = conn

    def host_ids(self, principal_id: PrincipalId) -> frozenset[ScopeId]:
        rows = run(lambda: self._conn.execute(_HOSTS, (principal_id,)).fetchall())
        return frozenset(ScopeId(cast("UUID", row[0])) for row in rows)

    def workspace_scope_id(self, principal_id: PrincipalId) -> ScopeId | None:
        row = run(lambda: self._conn.execute(_WORKSPACE, (principal_id,)).fetchone())
        return None if row is None else ScopeId(cast("UUID", row[0]))
