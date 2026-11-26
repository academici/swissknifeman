"""``ScopeRegistry`` and ``ScopeTree`` over ``skm_core.scopes`` (adapters §1.1, kernel-platform §2.10).

The database is the authority for the scope lineage: ``ck_scopes__*``, ``tg_scopes__parent_kind`` and the
partial unique index of the instance row reject a wrong parent kind, a foreign workspace and a second instance
even when this adapter is bypassed. ``create`` repeats the checks of the memory adapter first so that both
backends raise the same errors (``ValidationFailed`` for lineage, ``NotFound`` for a missing parent); a writer
that slips past them meets the constraint and the SQLSTATE translation of ``errors.py``.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.pagination import validate_page_limit
from skm.kernel.scopes import (
    ScopeKind,
    ScopeRecord,
    check_scope_parent,
    check_scope_workspace,
    scope_not_found,
)
from skm.platform.config.scope_tree import RegistryScopeTree

__all__ = ["PostgresScopeRegistry", "PostgresScopeTree"]

type _Row = tuple[UUID, str, UUID | None, UUID | None, datetime]

_INSERT: Final = "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) VALUES (%s, %s, %s, %s)"
_GET: Final = "SELECT id, kind, parent_id, workspace_id, created_at FROM skm_core.scopes WHERE id = %s"
_LIST: Final = (
    "SELECT id, kind, parent_id, workspace_id, created_at FROM skm_core.scopes "
    "WHERE (%s::uuid IS NULL OR id > %s::uuid) ORDER BY id LIMIT %s"
)
_INSTANCE: Final = (
    "SELECT id, kind, parent_id, workspace_id, created_at FROM skm_core.scopes WHERE kind = 'instance'"
)
# Ancestors by parent_id, instance first. The tree is five levels deep at most; the bound only stops a cycle.
_ANCESTORS: Final = """
WITH RECURSIVE chain AS (
    SELECT id, kind, parent_id, workspace_id, created_at, 1 AS depth FROM skm_core.scopes WHERE id = %s
    UNION ALL
    SELECT s.id, s.kind, s.parent_id, s.workspace_id, s.created_at, c.depth + 1
      FROM skm_core.scopes s JOIN chain c ON s.id = c.parent_id WHERE c.depth < 16
)
SELECT id, kind, parent_id, workspace_id, created_at FROM chain ORDER BY depth DESC
"""


def _record(row: tuple[object, ...]) -> ScopeRecord:
    scope_id, kind, parent_id, workspace_id, created_at = cast("_Row", row)
    return ScopeRecord(
        id=ScopeId(scope_id),
        kind=ScopeKind(kind),
        parent_id=None if parent_id is None else ScopeId(parent_id),
        workspace_id=None if workspace_id is None else WorkspaceId(workspace_id),
        created_at=created_at,
    )


def _run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


class PostgresScopeRegistry:
    """Constructed per unit of work over its connection; never commits or closes it."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def create(
        self,
        scope_id: ScopeId,
        kind: ScopeKind,
        *,
        parent: ScopeId | None,
        workspace_id: WorkspaceId | None,
    ) -> None:
        if _run(lambda: self._conn.execute(_GET, (scope_id,)).fetchone()) is not None:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "scope already exists", details={"kind": "scope"})
        parent_record = None if parent is None else self.get(parent)
        check_scope_parent(kind, parent_record)
        check_scope_workspace(scope_id, kind, parent_record, workspace_id)
        # A concurrent duplicate id or a second instance row surfaces as unique_violation -> ALREADY_EXISTS.
        _run(lambda: self._conn.execute(_INSERT, (scope_id, kind.value, parent, workspace_id)))

    def get(self, scope_id: ScopeId) -> ScopeRecord:
        row = _run(lambda: self._conn.execute(_GET, (scope_id,)).fetchone())
        if row is None:
            raise scope_not_found()
        return _record(row)

    def list_scopes(self, *, after: ScopeId | None = None, limit: int = 100) -> tuple[ScopeRecord, ...]:
        limit = validate_page_limit(limit)
        if after is not None and not isinstance(after, UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("scope inventory after must be UUID or None")
        rows = _run(lambda: self._conn.execute(_LIST, (after, after, limit)).fetchall())
        return tuple(_record(row) for row in rows)

    def ancestors(self, scope_id: ScopeId) -> tuple[ScopeRecord, ...]:
        rows = _run(lambda: self._conn.execute(_ANCESTORS, (scope_id,)).fetchall())
        if not rows:
            raise scope_not_found()
        return tuple(_record(row) for row in rows)

    def instance(self) -> ScopeRecord:
        row = _run(lambda: self._conn.execute(_INSTANCE).fetchone())
        if row is None:
            raise scope_not_found()
        return _record(row)


class PostgresScopeTree(RegistryScopeTree):
    """The config scope tree over ``skm_core.scopes`` on the connection of the unit of work."""

    def __init__(self, conn: psycopg.Connection) -> None:
        super().__init__(PostgresScopeRegistry(conn))
