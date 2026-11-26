"""``OutboxStore`` over the memory outbox table (``skm_core.outbox``).

The unit of work inserts the rows on commit (``uow.py``); this repository is the relay side. A claim expires
after ``CLAIM_TTL`` so that a crashed relay does not hold a row forever. ``list`` and ``list_dead`` page by
row id; the cursor is the id of the last row of the page.
"""

from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState, OutboxRecord
from skm.application_bus.ports import OutboxEntry, OutboxItem, OutboxState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import EventId, WorkspaceId
from skm.kernel.pagination import Cursor, Page

__all__ = ["CLAIM_TTL", "MemoryOutboxStore"]

CLAIM_TTL: Final = timedelta(seconds=60)
_DELIVERABLE: Final = (OutboxState.PENDING, OutboxState.FAILED)


def _free(row: OutboxRecord, now: datetime) -> bool:
    return row.claimed_by is None or row.claimed_at is None or row.claimed_at + CLAIM_TTL <= now


def _due(row: OutboxRecord, now: datetime) -> bool:
    return row.state in _DELIVERABLE and row.available_at <= now and _free(row, now)


def _item(row: OutboxRecord) -> OutboxItem:
    return OutboxItem(
        id=row.id,
        event_id=row.event_id,
        destination=row.destination,
        attempts=row.attempts,
        delivery_generation=row.delivery_generation,
        claimed_at=row.claimed_at or row.created_at,
    )


def _entry(row: OutboxRecord) -> OutboxEntry:
    return OutboxEntry(
        id=row.id,
        event_id=row.event_id,
        destination=row.destination,
        state=row.state,
        attempts=row.attempts,
        last_error=row.last_error,
        created_at=row.created_at,
        available_at=row.available_at,
    )


def _listing(rows: list[OutboxRecord], after: str | None, limit: int) -> Page[OutboxEntry]:
    ordered = sorted((r for r in rows if after is None or str(r.id) > after), key=lambda r: str(r.id))
    page = ordered[: max(limit, 0)]
    more = len(ordered) > len(page) and bool(page)
    return Page(tuple(_entry(r) for r in page), Cursor(str(page[-1].id)) if more else None)


def _prefix(destination: str) -> str | None:
    prefix, separator, _ = destination.partition(":")
    return prefix if separator else None


class MemoryOutboxStore:
    def __init__(self, state: MemoryBackendState) -> None:
        self._core = state.core

    def _row(self, item_id: UUID) -> OutboxRecord:
        row = self._core.outbox.get(item_id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "outbox row not found", details={"kind": "outbox"})
        return row

    @staticmethod
    def _release(row: OutboxRecord) -> None:
        row.claimed_by = None
        row.claimed_at = None

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
        found: set[str] = set()
        for row in self._core.outbox.values():
            destination = row.destination
            routable = (
                (include_sse and destination == "sse")
                or destination in consumer_ids
                or _prefix(destination) in prefixes
            )
            if routable and _due(row, now):
                found.add(destination)
        ordered = sorted(d for d in found if after is None or d > after)
        return tuple(ordered[: max(limit, 0)])

    def claim(self, *, destination: str, relay_id: str, now: datetime, limit: int) -> tuple[OutboxItem, ...]:
        self._core.require_writable()
        due = [row for row in self._core.outbox.values() if row.destination == destination and _due(row, now)]
        claimed: list[OutboxItem] = []
        for row in due[: max(limit, 0)]:
            row.claimed_by = relay_id
            row.claimed_at = now
            row.attempts += 1
            claimed.append(_item(row))
        return tuple(claimed)

    def mark_delivered(self, item_id: UUID, *, at: datetime, relay_id: str | None = None) -> bool:
        self._core.require_writable()
        row = self._row(item_id)
        if relay_id is not None and (row.claimed_by != relay_id or row.state not in _DELIVERABLE):
            return False  # a stale claimant (or a dead-notification claim) marks nothing
        row.state = OutboxState.DELIVERED
        row.delivered_at = at
        row.last_error = None
        self._release(row)
        return True

    def mark_failed(
        self,
        item_id: UUID,
        *,
        relay_id: str,
        error: str,
        next_at: datetime,
        dead: bool,
    ) -> bool:
        self._core.require_writable()
        row = self._row(item_id)
        if row.claimed_by != relay_id or row.state not in _DELIVERABLE:  # a dead-notification claim stays
            return False
        row.state = OutboxState.DEAD if dead else OutboxState.FAILED
        row.available_at = next_at
        row.last_error = error
        self._release(row)
        return True

    def claim_dead_notifications(
        self,
        *,
        prefixes: frozenset[str],
        relay_id: str,
        now: datetime,
        limit: int,
    ) -> tuple[OutboxItem, ...]:
        self._core.require_writable()
        due = [
            row
            for row in self._core.outbox.values()
            if row.state is OutboxState.DEAD
            and row.dead_notified_at is None
            and _prefix(row.destination) in prefixes
            and row.available_at <= now
            and _free(row, now)
        ]
        claimed: list[OutboxItem] = []
        for row in due[: max(limit, 0)]:
            row.claimed_by = relay_id
            row.claimed_at = now
            claimed.append(_item(row))
        return tuple(claimed)

    def _owned_dead(
        self, item_id: UUID, relay_id: str, generation: int, claimed_at: datetime
    ) -> OutboxRecord | None:
        row = self._row(item_id)
        owned = (
            row.state is OutboxState.DEAD
            and row.dead_notified_at is None
            and row.claimed_by == relay_id
            and row.delivery_generation == generation
            and row.claimed_at == claimed_at
        )
        return row if owned else None

    def mark_dead_notified(
        self,
        item_id: UUID,
        *,
        relay_id: str,
        generation: int,
        claimed_at: datetime,
        at: datetime,
    ) -> bool:
        self._core.require_writable()
        row = self._owned_dead(item_id, relay_id, generation, claimed_at)
        if row is None:
            return False
        row.dead_notified_at = at
        self._release(row)
        return True

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
        self._core.require_writable()
        row = self._owned_dead(item_id, relay_id, generation, claimed_at)
        if row is None:
            return False
        row.available_at = next_at
        row.last_error = error
        self._release(row)
        return True

    def retry_dead(
        self,
        *,
        outbox_id: UUID | None,
        event_id: EventId | None,
        destination: str | None,
        now: datetime,
    ) -> int:
        self._core.require_writable()
        if outbox_id is None and event_id is None and destination is None:
            raise ValueError("retry_dead needs a filter")
        count = 0
        for row in self._core.outbox.values():
            matches = (
                row.state is OutboxState.DEAD
                and (outbox_id is None or row.id == outbox_id)
                and (event_id is None or row.event_id == event_id)
                and (destination is None or row.destination == destination)
            )
            if matches:
                row.state = OutboxState.PENDING
                row.attempts = 0
                row.delivery_generation += 1
                row.available_at = now
                row.dead_notified_at = None
                self._release(row)
                count += 1
        return count

    def list_dead(self, *, after: str | None, limit: int) -> Page[OutboxEntry]:
        rows = [r for r in self._core.outbox.values() if r.state is OutboxState.DEAD]
        return _listing(rows, after, limit)

    def list(
        self,
        *,
        destination_prefix: str,
        state: OutboxState | None,
        workspace_id: WorkspaceId | None,
        after: str | None,
        limit: int,
    ) -> Page[OutboxEntry]:
        rows = [
            r
            for r in self._core.outbox.values()
            if r.destination.startswith(destination_prefix)
            and (
                state is None
                or r.state is state
                or (state is OutboxState.PENDING and r.state is OutboxState.FAILED)
            )
            and (workspace_id is None or r.workspace_id == workspace_id)
        ]
        return _listing(rows, after, limit)

    def purge_delivered(self, *, before: datetime, limit: int) -> int:
        self._core.require_writable()
        old = [
            r
            for r in self._core.outbox.values()
            if r.state is OutboxState.DELIVERED and (r.delivered_at or before) < before
        ]
        removed = old[: max(limit, 0)]
        for row in removed:
            del self._core.outbox[row.id]
            self._core.outbox_keys.discard((row.event_id, row.destination))
        return len(removed)
