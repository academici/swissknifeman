"""``AuditLog`` over ``skm_core.audit_records`` (adapters §1.5, kernel-platform §4.4).

An allowed decision is appended on the connection of the command's unit of work and commits with it; a denied
one is appended by the bus in its own short unit of work after the command's has been left, so this adapter
never opens a connection or a transaction and never commits. The table is append-only
(``tg_audit_records__append_only``): there is no update or delete here.
"""

from typing import Final

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.jsonb import to_jsonb
from skm.application_bus.ports import AuditRecord

__all__ = ["PostgresAuditLog"]

# ``recorded_at`` is the database's ``now()`` (adapters §1.5), not ``AuditRecord.recorded_at`` of the clock.
_INSERT: Final = (
    "INSERT INTO skm_core.audit_records "
    "(id, workspace_id, actor_id, action, target, decision, reason_code, request_id, recorded_at) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())"
)


class PostgresAuditLog:
    """Constructed per unit of work over its connection."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def append(self, record: AuditRecord) -> None:
        try:
            self._conn.execute(
                _INSERT,
                (
                    record.id,
                    record.workspace_id,
                    record.actor_id,
                    record.action,
                    to_jsonb(record.target),
                    record.decision,
                    record.reason_code,
                    record.request_id,
                ),
            )
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc
