"""PostgreSQL ``CheckoutBindingRepository`` (workspace §4.3, §6, §11; DDL ``0007``).

A binding names a repository of its workspace (composite FK ``(workspace_id, repository_id)``) on a host; at
most one binding per ``(host, repository)`` is not ``removed`` (partial unique index). ``add`` runs ``ON
CONFLICT DO NOTHING``: a taken pair is ``ALREADY_EXISTS`` naming the live binding.

The binding identity ``(id, workspace, host, repository, local_locator)`` is fixed at creation: ``save`` locks
the row, compares ``row_version`` and writes the state and the observations only; a value that changes the
identity is refused (``ValueError``). A verification never moves a locator: a moved checkout is a
``mismatched`` observation, a new place is a new binding after the old one is removed. ``local_locator`` is a
column of this table only; nothing here hands it to an event.
"""

from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.workspace.mapping import (
    Row,
    damaged,
    ensure_kept,
    not_found,
    run,
    version_conflict,
)
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.ids import HostId, RepositoryId, WorkspaceId
from skm.modules.workspace.domain.checkout_binding import BindingState, CheckoutBinding, CheckoutBindingId
from skm.modules.workspace.domain.remote_url import NormalizedRemote
from skm.platform.system_clock import SystemClock

__all__ = ["PostgresCheckoutBindingRepository"]

_COLUMNS: Final = (
    "SELECT id, workspace_id, host_id, repository_id, local_locator, state, observed_remotes, observed_head, "
    "last_verified_at, row_version, created_at FROM skm_workspace.checkout_bindings "
)
_GET: Final = _COLUMNS + "WHERE id = %s"
_LOCKED: Final = _GET + " FOR UPDATE"
_LIVE: Final = _COLUMNS + "WHERE host_id = %s AND repository_id = %s AND state <> 'removed'"
_INSERT: Final = """
INSERT INTO skm_workspace.checkout_bindings
    (id, workspace_id, host_id, repository_id, local_locator, state, observed_remotes, observed_head,
     last_verified_at, row_version, created_at, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING RETURNING id
"""
_UPDATE: Final = """
UPDATE skm_workspace.checkout_bindings
   SET state = %s, observed_remotes = %s, observed_head = %s, last_verified_at = %s, row_version = %s,
       updated_at = greatest(updated_at, %s)
 WHERE id = %s AND row_version = %s
"""
_IDENTITY: Final = ("workspace_id", "host_id", "repository_id", "local_locator", "created_at")


def _binding(row: Row) -> CheckoutBinding:
    try:
        return CheckoutBinding(
            id=CheckoutBindingId(cast("UUID", row[0])),
            workspace_id=WorkspaceId(cast("UUID", row[1])),
            host_id=HostId(cast("UUID", row[2])),
            repository_id=RepositoryId(cast("UUID", row[3])),
            local_locator=cast("str", row[4]),
            state=BindingState(cast("str", row[5])),
            observed_remotes=tuple(NormalizedRemote(item) for item in cast("list[str]", row[6])),
            observed_head=cast("str | None", row[7]),
            last_verified_at=cast("datetime", row[8]),
            row_version=cast("int", row[9]),
            created_at=cast("datetime", row[10]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise damaged("checkout_bindings", row[0], exc) from exc


class PostgresCheckoutBindingRepository:
    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def get(self, binding_id: CheckoutBindingId) -> CheckoutBinding:
        row = run(lambda: self._conn.execute(_GET, (binding_id,)).fetchone())
        if row is None:
            raise not_found("binding", binding_id)
        return _binding(row)

    def find(self, host_id: HostId, repository_id: RepositoryId) -> CheckoutBinding | None:
        row = run(lambda: self._conn.execute(_LIVE, (host_id, repository_id)).fetchone())
        return None if row is None else _binding(row)

    def add(self, binding: CheckoutBinding) -> None:
        params = (
            binding.id,
            binding.workspace_id,
            binding.host_id,
            binding.repository_id,
            binding.local_locator,
            BindingState(binding.state).value,
            [item.value for item in binding.observed_remotes],
            binding.observed_head,
            binding.last_verified_at,
            binding.row_version,
            binding.created_at,
            binding.created_at,
        )
        if run(lambda: self._conn.execute(_INSERT, params).fetchone()) is None:
            live = self.find(binding.host_id, binding.repository_id)
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "the repository is already bound on this host",
                details={"kind": "binding", "binding_id": str(binding.id if live is None else live.id)},
            )

    def save(self, binding: CheckoutBinding, *, expected_version: int) -> None:
        """State and observations only; the identity ``(workspace, host, repository, locator)`` is kept."""
        row = run(lambda: self._conn.execute(_LOCKED, (binding.id,)).fetchone())
        if row is None:
            raise not_found("binding", binding.id)
        current = _binding(row)
        if current.row_version != expected_version:
            raise version_conflict("binding", expected_version, current.row_version)
        ensure_kept("binding", current, binding, _IDENTITY)
        params = (
            BindingState(binding.state).value,
            [item.value for item in binding.observed_remotes],
            binding.observed_head,
            binding.last_verified_at,
            binding.row_version,
            self._clock.now(),
            binding.id,
            expected_version,
        )
        run(lambda: self._conn.execute(_UPDATE, params))
