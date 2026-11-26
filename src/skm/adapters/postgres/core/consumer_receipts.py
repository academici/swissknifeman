"""``ConsumerReceipts`` over ``skm_core.consumer_receipts`` (adapters §1.4, kernel-platform §4.5).

The relay adds the receipt in the subscriber's own unit of work, together with the subscriber's effects and
the ``delivered`` mark, so a redelivery finds it and runs no effect twice. Receipts are never updated
(``tg_consumer_receipts__no_update``); ``purge`` deletes old ones only once no undelivered outbox row of the
same (consumer, event) pair is left, because such a receipt still guards against a redelivery.
"""

from datetime import datetime
from typing import Final

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.jsonb import require_aware
from skm.kernel.ids import EventId

__all__ = ["PostgresConsumerReceipts"]

_SEEN: Final = "SELECT 1 FROM skm_core.consumer_receipts WHERE consumer_id = %s AND event_id = %s"
_ADD: Final = (
    "INSERT INTO skm_core.consumer_receipts (consumer_id, event_id, processed_at) VALUES (%s, %s, %s) "
    "ON CONFLICT ON CONSTRAINT pk_consumer_receipts DO NOTHING"
)
_PURGE: Final = """
DELETE FROM skm_core.consumer_receipts AS d USING (
  SELECT r.consumer_id, r.event_id FROM skm_core.consumer_receipts r
   WHERE r.processed_at < %s
     AND NOT EXISTS (SELECT 1 FROM skm_core.outbox o
                      WHERE o.destination = r.consumer_id AND o.event_id = r.event_id
                        AND o.state <> 'delivered')
   ORDER BY r.processed_at, r.consumer_id, r.event_id LIMIT %s FOR UPDATE OF r SKIP LOCKED) AS old
 WHERE d.consumer_id = old.consumer_id AND d.event_id = old.event_id
"""


class PostgresConsumerReceipts:
    """Constructed per unit of work over its connection; never commits or closes it."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def seen(self, consumer_id: str, event_id: EventId) -> bool:
        try:
            return self._conn.execute(_SEEN, (consumer_id, event_id)).fetchone() is not None
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc

    def add(self, consumer_id: str, event_id: EventId, at: datetime) -> None:
        """A second receipt of the same pair keeps the first (``ON CONFLICT DO NOTHING``)."""
        require_aware(at)
        try:
            self._conn.execute(_ADD, (consumer_id, event_id, at))
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc

    def purge(self, *, before: datetime, limit: int) -> int:
        if limit <= 0:
            return 0
        require_aware(before)
        try:
            return self._conn.execute(_PURGE, (before, limit)).rowcount
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc
