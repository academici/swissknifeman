"""``OutboxStore`` over ``skm_core.outbox`` (adapters §1.4, kernel-platform §4.5).

The unit of work inserts the rows with the events (``events_store.py``); this repository is the relay side and
the operator's (``platform.list_dead_outbox``/``retry_outbox``). There is no delivering state: a claim is
``claimed_at``/``claimed_by`` and expires after the visibility timeout, so a crashed relay never holds a row.
Claims take ``FOR UPDATE SKIP LOCKED``, so two relays never claim one row at the same time.

Admission and expiry use fresh database time, ``greatest(<caller now>, clock_timestamp())`` evaluated when
the statement runs, never the transaction's ``now()``. A caller clock that lags (a unit of work opened long
ago, a stale sample) therefore cannot keep a row hidden or a dead claim alive; it can only move the decision
forward, which is what a test clock that was advanced on purpose does. ``claimed_at`` is written after the row
is locked and is returned, so the notification CAS compares the exact stored value. The absolute times a
caller decided (``next_at`` of a backoff, ``at`` of a delivery) are stored as given.

``mark_delivered`` of an ``sse`` row sends ``NOTIFY skm_events, '<workspace_id>:<workspace_seq>'`` in the
same transaction (adapters §1.6): listeners see it only after the commit, and the event log stays the source
of replay. Every ``mark_*`` is a compare-and-set on the claimant; a stale claim returns ``False``.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.jsonb import require_aware
from skm.application_bus.ports import OutboxEntry, OutboxItem, OutboxState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import EventId, WorkspaceId
from skm.kernel.pagination import Cursor, Page

__all__ = ["VISIBILITY_TIMEOUT", "PostgresOutboxStore"]

# events.delivery.visibility_timeout_seconds (default 300); a claim older than this counts as abandoned.
VISIBILITY_TIMEOUT: Final = timedelta(seconds=300)
_ERROR_LIMIT: Final = 2000  # last_error is stored redacted and cut to this length (adapters §1.4)

# Every "greatest(%(now)s::timestamptz, clock_timestamp())" below is the fresh time described above.
_DUE_DESTINATIONS: Final = """
SELECT DISTINCT destination COLLATE "C" AS destination FROM skm_core.outbox
 WHERE state IN ('pending', 'failed')
   AND available_at <= greatest(%(now)s::timestamptz, clock_timestamp())
   AND (claimed_at IS NULL
        OR claimed_at <= greatest(%(now)s::timestamptz, clock_timestamp()) - %(visibility)s)
   AND (destination = ANY(%(consumers)s::text[])
        OR split_part(destination, ':', 1) = ANY(%(prefixes)s::text[])
        OR (%(sse)s AND destination = 'sse'))
   AND (%(after)s::text IS NULL OR destination COLLATE "C" > %(after)s::text COLLATE "C")
 ORDER BY 1 LIMIT %(limit)s
"""
_CLAIM: Final = """
WITH picked AS (
  SELECT id, available_at FROM skm_core.outbox
   WHERE destination = %(destination)s AND state IN ('pending', 'failed')
     AND available_at <= greatest(%(now)s::timestamptz, clock_timestamp())
     AND (claimed_at IS NULL
          OR claimed_at <= greatest(%(now)s::timestamptz, clock_timestamp()) - %(visibility)s)
   ORDER BY available_at, id LIMIT %(limit)s FOR UPDATE SKIP LOCKED)
UPDATE skm_core.outbox o
   SET attempts = o.attempts + 1, claimed_at = greatest(%(now)s::timestamptz, clock_timestamp()),
       claimed_by = %(relay_id)s
  FROM picked WHERE o.id = picked.id
RETURNING o.id, o.event_id, o.destination, o.attempts, o.delivery_generation, o.claimed_at,
          picked.available_at
"""
_DELIVERED: Final = """
UPDATE skm_core.outbox
   SET state = 'delivered', delivered_at = %(at)s, last_error = NULL, claimed_at = NULL, claimed_by = NULL
 WHERE id = %(id)s
   AND (%(relay_id)s::text IS NULL OR (claimed_by = %(relay_id)s AND state IN ('pending', 'failed')))
RETURNING event_id, destination
"""
_NOTIFY: Final = (
    "SELECT pg_notify('skm_events', e.workspace_id::text || ':' || e.workspace_seq::text) "
    "FROM skm_core.domain_events e WHERE e.id = %s AND e.workspace_id IS NOT NULL"
)
_FAILED: Final = """
UPDATE skm_core.outbox
   SET state = CASE WHEN %(dead)s THEN 'dead' ELSE 'failed' END, available_at = %(next_at)s,
       last_error = left(%(error)s, %(error_limit)s), claimed_at = NULL, claimed_by = NULL
 WHERE id = %(id)s AND claimed_by = %(relay_id)s AND state IN ('pending', 'failed')
RETURNING id
"""
_CLAIM_DEAD: Final = """
WITH picked AS (
  SELECT id, available_at FROM skm_core.outbox
   WHERE state = 'dead' AND dead_notified_at IS NULL
     AND available_at <= greatest(%(now)s::timestamptz, clock_timestamp())
     AND split_part(destination, ':', 1) = ANY(%(prefixes)s::text[])
     AND (claimed_at IS NULL
          OR claimed_at <= greatest(%(now)s::timestamptz, clock_timestamp()) - %(visibility)s)
   ORDER BY available_at, id LIMIT %(limit)s FOR UPDATE SKIP LOCKED)
UPDATE skm_core.outbox o
   SET claimed_at = greatest(%(now)s::timestamptz, clock_timestamp()), claimed_by = %(relay_id)s
  FROM picked WHERE o.id = picked.id
RETURNING o.id, o.event_id, o.destination, o.attempts, o.delivery_generation, o.claimed_at,
          picked.available_at
"""
_DEAD_NOTIFIED: Final = """
UPDATE skm_core.outbox SET dead_notified_at = %(at)s, claimed_at = NULL, claimed_by = NULL
 WHERE id = %(id)s AND state = 'dead' AND dead_notified_at IS NULL AND delivery_generation = %(generation)s
   AND claimed_by = %(relay_id)s AND claimed_at = %(claimed_at)s
RETURNING id
"""
_DEFER_DEAD: Final = """
UPDATE skm_core.outbox
   SET available_at = %(next_at)s, last_error = left(%(error)s, %(error_limit)s),
       claimed_at = NULL, claimed_by = NULL
 WHERE id = %(id)s AND state = 'dead' AND dead_notified_at IS NULL AND delivery_generation = %(generation)s
   AND claimed_by = %(relay_id)s AND claimed_at = %(claimed_at)s
RETURNING id
"""
_RETRY_DEAD: Final = """
UPDATE skm_core.outbox
   SET state = 'pending', available_at = greatest(%(now)s::timestamptz, clock_timestamp()), attempts = 0,
       delivery_generation = delivery_generation + 1, claimed_at = NULL, claimed_by = NULL,
       dead_notified_at = NULL
 WHERE state = 'dead' AND (%(outbox_id)s::uuid IS NULL OR id = %(outbox_id)s)
   AND (%(event_id)s::uuid IS NULL OR event_id = %(event_id)s)
   AND (%(destination)s::text IS NULL OR destination = %(destination)s)
"""
# Keyset by the text of the id, the cursor the memory adapter issues too; one extra row tells of a next page.
_LIST_DEAD: Final = """
SELECT o.id, o.event_id, o.destination, o.state, o.attempts, o.last_error, o.created_at, o.available_at
  FROM skm_core.outbox o
 WHERE o.state = 'dead' AND (%(after)s::text IS NULL OR o.id::text > %(after)s)
 ORDER BY o.id::text LIMIT %(limit)s + 1
"""
_LIST: Final = """
SELECT o.id, o.event_id, o.destination, o.state, o.attempts, o.last_error, o.created_at, o.available_at
  FROM skm_core.outbox o
 WHERE left(o.destination, length(%(prefix)s)) = %(prefix)s
   AND (%(state)s::text IS NULL OR o.state = %(state)s
        OR (%(state)s::text = 'pending' AND o.state = 'failed'))
   AND (%(workspace_id)s::uuid IS NULL OR EXISTS (
        SELECT 1 FROM skm_core.domain_events e
         WHERE e.id = o.event_id AND e.workspace_id = %(workspace_id)s))
   AND (%(after)s::text IS NULL OR o.id::text > %(after)s)
 ORDER BY o.id::text LIMIT %(limit)s + 1
"""
_PURGE: Final = (
    "DELETE FROM skm_core.outbox WHERE id IN ("
    "SELECT id FROM skm_core.outbox WHERE state = 'delivered' AND delivered_at < %s "
    "ORDER BY delivered_at, id LIMIT %s FOR UPDATE SKIP LOCKED)"
)
_EXISTS: Final = "SELECT 1 FROM skm_core.outbox WHERE id = %s"

type _ClaimRow = tuple[UUID, UUID, str, int, int, datetime, datetime]
type _EntryRow = tuple[UUID, UUID, str, str, int, str | None, datetime, datetime]


def _items(rows: list[tuple[Any, ...]]) -> tuple[OutboxItem, ...]:
    """Claimed rows in claim order (``available_at``, ``id``); ``RETURNING`` keeps no order of its own."""
    claimed = sorted(cast("list[_ClaimRow]", rows), key=lambda row: (row[6], row[0]))
    return tuple(
        OutboxItem(
            id=row_id,
            event_id=EventId(event_id),
            destination=destination,
            attempts=attempts,
            delivery_generation=generation,
            claimed_at=claimed_at,
        )
        for row_id, event_id, destination, attempts, generation, claimed_at, _ in claimed
    )


def _page(rows: list[tuple[Any, ...]], limit: int) -> Page[OutboxEntry]:
    entries = [
        OutboxEntry(
            id=row_id,
            event_id=EventId(event_id),
            destination=destination,
            state=OutboxState(state),
            attempts=attempts,
            last_error=last_error,
            created_at=created_at,
            available_at=available_at,
        )
        for row_id, event_id, destination, state, attempts, last_error, created_at, available_at in cast(
            "list[_EntryRow]", rows
        )
    ]
    page = entries[:limit]
    more = len(entries) > limit and bool(page)
    return Page(tuple(page), Cursor(str(page[-1].id)) if more else None)


def _translated[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """Driver errors of ``method`` become ``SkmError`` (adapters §1.7)."""

    @wraps(method)
    def call(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return method(*args, **kwargs)
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc

    return call


class PostgresOutboxStore:
    """Constructed per unit of work over its connection; never commits or closes it."""

    def __init__(self, conn: psycopg.Connection, *, visibility: timedelta = VISIBILITY_TIMEOUT) -> None:
        self._conn = conn
        self._visibility = visibility

    @_translated
    def _missing_or_stale(self, item_id: UUID) -> bool:
        """``False`` for a row that exists (a stale claim); a row that does not is ``NotFound``."""
        if self._conn.execute(_EXISTS, (item_id,)).fetchone() is None:
            raise NotFound(ErrorCode.NOT_FOUND, "outbox row not found", details={"kind": "outbox"})
        return False

    @_translated
    def due_destinations(
        self,
        *,
        consumer_ids: frozenset[str],
        prefixes: frozenset[str],
        include_sse: bool,
        now: datetime,
        after: str | None,
        limit: int,
    ) -> tuple[str, ...]:
        if limit <= 0:
            return ()
        require_aware(now)
        params = {
            "now": now,
            "visibility": self._visibility,
            "consumers": sorted(consumer_ids),
            "prefixes": sorted(prefixes),
            "sse": include_sse,
            "after": after,
            "limit": limit,
        }
        return tuple(cast("str", row[0]) for row in self._conn.execute(_DUE_DESTINATIONS, params).fetchall())

    @_translated
    def claim(self, *, destination: str, relay_id: str, now: datetime, limit: int) -> tuple[OutboxItem, ...]:
        if limit <= 0:
            return ()
        require_aware(now)
        params = {
            "destination": destination,
            "relay_id": relay_id,
            "now": now,
            "visibility": self._visibility,
            "limit": limit,
        }
        return _items(self._conn.execute(_CLAIM, params).fetchall())

    @_translated
    def mark_delivered(self, item_id: UUID, *, at: datetime, relay_id: str | None = None) -> bool:
        require_aware(at)
        row = self._conn.execute(_DELIVERED, {"id": item_id, "at": at, "relay_id": relay_id}).fetchone()
        if row is None:
            return self._missing_or_stale(item_id)
        event_id, destination = cast("tuple[UUID, str]", row)
        if destination == "sse":
            self._conn.execute(_NOTIFY, (event_id,))
        return True

    @_translated
    def mark_failed(
        self,
        item_id: UUID,
        *,
        relay_id: str,
        error: str,
        next_at: datetime,
        dead: bool,
    ) -> bool:
        require_aware(next_at)
        params = {
            "id": item_id,
            "relay_id": relay_id,
            "error": error,
            "error_limit": _ERROR_LIMIT,
            "next_at": next_at,
            "dead": dead,
        }
        if self._conn.execute(_FAILED, params).fetchone() is None:
            return self._missing_or_stale(item_id)
        return True

    @_translated
    def claim_dead_notifications(
        self,
        *,
        prefixes: frozenset[str],
        relay_id: str,
        now: datetime,
        limit: int,
    ) -> tuple[OutboxItem, ...]:
        if limit <= 0 or not prefixes:
            return ()
        require_aware(now)
        params = {
            "prefixes": sorted(prefixes),
            "relay_id": relay_id,
            "now": now,
            "visibility": self._visibility,
            "limit": limit,
        }
        return _items(self._conn.execute(_CLAIM_DEAD, params).fetchall())

    @_translated
    def mark_dead_notified(
        self,
        item_id: UUID,
        *,
        relay_id: str,
        generation: int,
        claimed_at: datetime,
        at: datetime,
    ) -> bool:
        require_aware(at)
        params = {
            "id": item_id,
            "relay_id": relay_id,
            "generation": generation,
            "claimed_at": claimed_at,
            "at": at,
        }
        if self._conn.execute(_DEAD_NOTIFIED, params).fetchone() is None:
            return self._missing_or_stale(item_id)
        return True

    @_translated
    def defer_dead_notification(
        self,
        item_id: UUID,
        *,
        relay_id: str,
        generation: int,
        claimed_at: datetime,
        next_at: datetime,
        error: str,
    ) -> bool:
        require_aware(next_at)
        params = {
            "id": item_id,
            "relay_id": relay_id,
            "generation": generation,
            "claimed_at": claimed_at,
            "next_at": next_at,
            "error": error,
            "error_limit": _ERROR_LIMIT,
        }
        if self._conn.execute(_DEFER_DEAD, params).fetchone() is None:
            return self._missing_or_stale(item_id)
        return True

    @_translated
    def retry_dead(
        self,
        *,
        outbox_id: UUID | None,
        event_id: EventId | None,
        destination: str | None,
        now: datetime,
    ) -> int:
        if outbox_id is None and event_id is None and destination is None:
            raise ValueError("retry_dead needs a filter")
        require_aware(now)
        params = {"outbox_id": outbox_id, "event_id": event_id, "destination": destination, "now": now}
        return self._conn.execute(_RETRY_DEAD, params).rowcount

    @_translated
    def list_dead(self, *, after: str | None, limit: int) -> Page[OutboxEntry]:
        if limit <= 0:
            return Page(())
        return _page(self._conn.execute(_LIST_DEAD, {"after": after, "limit": limit}).fetchall(), limit)

    @_translated
    def list(
        self,
        *,
        destination_prefix: str,
        state: OutboxState | None,
        workspace_id: WorkspaceId | None,
        after: str | None,
        limit: int,
    ) -> Page[OutboxEntry]:
        if limit <= 0:
            return Page(())
        params = {
            "prefix": destination_prefix,
            "state": None if state is None else state.value,
            "workspace_id": workspace_id,
            "after": after,
            "limit": limit,
        }
        return _page(self._conn.execute(_LIST, params).fetchall(), limit)

    @_translated
    def purge_delivered(self, *, before: datetime, limit: int) -> int:
        if limit <= 0:
            return 0
        require_aware(before)
        return self._conn.execute(_PURGE, (before, limit)).rowcount
