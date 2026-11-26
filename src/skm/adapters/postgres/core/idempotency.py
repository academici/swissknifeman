"""``IdempotencyStore`` over ``skm_core.idempotency_receipts`` (adapters §1.5, kernel-platform §4.4).

The receipt is written on the connection of the command's unit of work and commits with the command's state,
events and outbox rows. The bus computes ``request_digest`` (``application_bus.middleware.request_digest``);
this adapter stores it, the secret-free result and never a request body.

Time is the database's. ``created_at``/``expires_at`` of a new or replaced receipt are ``clock_timestamp()``
and ``clock_timestamp() + ttl``, where ``ttl`` is the length of ``expires_at - created_at`` of the receipt the
bus built. ``INSERT … ON CONFLICT … DO UPDATE`` may wait for the row lock of a concurrent transaction; the
``WHERE`` predicate and the replacement times are evaluated after that wait, so an expired row that was locked
meanwhile is still replaced and its new TTL starts when the replacement happens, not at the start of the
transaction (``now()``) and not from ``EXCLUDED``. ``get`` and ``purge_expired`` do not depend on the age of
the unit of work either. A live row makes ``put`` raise ``Conflict`` (the receipt race the bus resolves by
re-reading the receipt in a new unit of work).
"""

from datetime import datetime, timedelta
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.application_bus.ports import IdempotencyReceipt
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import PrincipalId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

__all__ = ["PostgresIdempotencyStore"]

_NIL_UUID: Final = UUID(int=0)  # ``scope_key`` of an instance-level command (no workspace)

_GET: Final = (
    "SELECT request_digest, result, created_at, expires_at FROM skm_core.idempotency_receipts "
    "WHERE scope_key = %s AND principal_id = %s AND operation = %s AND key = %s "
    "AND expires_at > clock_timestamp()"
)
_PUT: Final = """
INSERT INTO skm_core.idempotency_receipts AS r
  (id, workspace_id, principal_id, operation, key, request_digest, result_type, result,
   created_at, expires_at)
SELECT %(id)s, %(workspace_id)s, %(principal_id)s, %(operation)s, %(key)s, %(digest)s, %(result_type)s,
       %(result)s, n.t, n.t + %(ttl)s
  FROM (SELECT clock_timestamp() AS t) AS n
 WHERE true
ON CONFLICT (scope_key, principal_id, operation, key) DO UPDATE
   SET id = EXCLUDED.id, request_digest = EXCLUDED.request_digest, result_type = EXCLUDED.result_type,
       result = EXCLUDED.result,
       (created_at, expires_at) = (SELECT u.t, u.t + %(ttl)s FROM (SELECT clock_timestamp() AS t) AS u)
 WHERE r.expires_at <= clock_timestamp()
RETURNING r.id
"""
_PURGE: Final = (
    "DELETE FROM skm_core.idempotency_receipts WHERE id IN ("
    "SELECT id FROM skm_core.idempotency_receipts WHERE expires_at <= %s "
    "ORDER BY expires_at, id LIMIT %s FOR UPDATE SKIP LOCKED)"
)

# Receipt ids are never shown to a caller, so a process-wide generator is enough for adapters built from a
# bare connection; a composition root that needs its own source passes ``ids``.
_DEFAULT_IDS: Final[IdGenerator] = Uuid7Generator(SystemClock())


def _result_type(operation: str) -> str:
    """URN of the result schema by the rule ``<module>.<name>`` -> ``urn:skm:<module>:result:<name>:v1``.

    ``IdempotencyReceipt`` does not carry the URN of the result schema (the bus decodes with its own spec), so
    the column, which is informational and has no reader, follows the convention of the schema URNs.
    """
    module, _, name = operation.partition(".")
    return f"urn:skm:{module}:result:{name.replace('_', '-')}:v1"


class PostgresIdempotencyStore:
    """Constructed per unit of work over its connection; never commits or closes it."""

    def __init__(self, conn: psycopg.Connection, ids: IdGenerator | None = None) -> None:
        self._conn = conn
        self._ids = _DEFAULT_IDS if ids is None else ids

    def get(
        self,
        workspace_id: WorkspaceId | None,
        principal_id: PrincipalId,
        operation: str,
        key: str,
    ) -> IdempotencyReceipt | None:
        """The live receipt; an expired row the janitor has not purged yet is not returned."""
        scope_key = _NIL_UUID if workspace_id is None else workspace_id
        try:
            row = self._conn.execute(_GET, (scope_key, principal_id, operation, key)).fetchone()
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc
        if row is None:
            return None
        digest, result, created_at, expires_at = cast("tuple[str, JsonObject, datetime, datetime]", row)
        return IdempotencyReceipt(
            workspace_id=workspace_id,
            principal_id=principal_id,
            operation=operation,
            key=key,
            request_digest=digest,
            result=result,
            created_at=created_at,
            expires_at=expires_at,
        )

    def put(self, receipt: IdempotencyReceipt) -> None:
        """Insert, or overwrite an expired row of the same key; a live row is ``Conflict``."""
        ttl = receipt.expires_at - receipt.created_at
        if ttl <= timedelta(0):
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "idempotency receipt must expire after it is created",
                details={"operation": receipt.operation},
            )
        params = {
            "id": self._ids.new_id(),
            "workspace_id": receipt.workspace_id,
            "principal_id": receipt.principal_id,
            "operation": receipt.operation,
            "key": receipt.key,
            "digest": receipt.request_digest,
            "result_type": _result_type(receipt.operation),
            "result": to_jsonb(receipt.result),
            "ttl": ttl,
        }
        try:
            row = self._conn.execute(_PUT, params).fetchone()
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc
        if row is None:  # a live receipt of another request holds the key: the receipt race
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "idempotency receipt already exists",
                details={"kind": "idempotency_receipt"},
            )

    def purge_expired(self, now: datetime, *, limit: int) -> int:
        """Delete up to ``limit`` rows expired by ``now``; rows locked by others wait for the next run."""
        if limit <= 0:
            return 0
        require_aware(now)
        try:
            return self._conn.execute(_PURGE, (now, limit)).rowcount
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc
