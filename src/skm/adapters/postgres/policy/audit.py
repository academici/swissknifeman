"""PostgreSQL ``DecisionAuditRepository`` (policy §6, §11; DDL ``0012``): the append-only decision audit.

High volume: ``add_many`` is one ``executemany``. The table has constraints for the vocabulary of codes and
operations; a record that breaks one fails the whole batch (the handler validates first).
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.policy.mapping import Row, damaged, run
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.modules.policy.domain.tool_intent import DecisionSource, ToolDecisionRecord

__all__ = ["PostgresDecisionAuditRepository"]

_INSERT: Final = """
INSERT INTO skm_policy.decision_audit
    (id, workspace_id, scope_id, principal_id, source, at, tool, call_summary, outcome, code, rule,
     operation, recorded_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
_FOR_SCOPE: Final = """
SELECT id, workspace_id, scope_id, principal_id, source, at, tool, call_summary, outcome, code, rule,
       operation, recorded_at
  FROM skm_policy.decision_audit
 WHERE scope_id = %s AND (%s::text IS NULL OR operation = %s::text)
 ORDER BY at, id
 LIMIT %s
"""


def _record(row: Row) -> ToolDecisionRecord:
    try:
        return ToolDecisionRecord(
            id=cast("UUID", row[0]),
            workspace_id=None if row[1] is None else WorkspaceId(cast("UUID", row[1])),
            scope_id=ScopeId(cast("UUID", row[2])),
            principal_id=PrincipalId(cast("UUID", row[3])),
            source=DecisionSource(cast("str", row[4])),
            at=cast("datetime", row[5]),
            tool=cast("str", row[6]),
            call_summary=cast("str", row[7]),
            outcome=cast("str", row[8]),
            code=cast("str | None", row[9]),
            rule=cast("str | None", row[10]),
            operation=cast("str | None", row[11]),
            recorded_at=cast("datetime", row[12]),
        )
    except (TypeError, ValueError) as exc:
        raise damaged("decision_audit", row[0], exc) from exc


class PostgresDecisionAuditRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add_many(self, records: Sequence[ToolDecisionRecord]) -> None:
        rows = [
            (
                item.id,
                item.workspace_id,
                item.scope_id,
                item.principal_id,
                DecisionSource(item.source).value,
                item.at,
                item.tool,
                item.call_summary,
                item.outcome,
                item.code,
                item.rule,
                item.operation,
                item.recorded_at,
            )
            for item in records
        ]
        if not rows:
            return

        def write() -> None:
            with self._conn.cursor() as cursor:
                cursor.executemany(_INSERT, rows)

        run(write)

    def for_scope(
        self, scope_id: ScopeId, *, operation: str | None = None, limit: int = 200
    ) -> tuple[ToolDecisionRecord, ...]:
        rows = run(lambda: self._conn.execute(_FOR_SCOPE, (scope_id, operation, operation, limit)).fetchall())
        return tuple(_record(row) for row in rows)
