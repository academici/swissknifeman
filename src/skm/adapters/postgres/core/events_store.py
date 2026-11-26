"""Event allocation and reads over ``skm_core`` (adapters §1.4, §1.6; kernel-platform §2.9, §2.11; ADR 0017).

``PostgresEventWriter.write`` is the last step of a unit of work before COMMIT. It takes every counter row the
transaction needs in one global order: the instance feed (``event_streams('instance_feed', <instance
scope>)``), then the workspace feeds of ``workspace_event_counters`` by workspace id, then the aggregate
streams of ``event_streams`` by ``(stream_kind, stream_id)``. Each row is locked once and advanced by the
number of buffered events it serves; the numbers go to the events in buffer order. The row locks are held
until COMMIT, so a second transaction writing to the same feed waits and receives its numbers only after the
first commits: feed positions are fixed in commit order and a reader of ``workspace_seq > cursor`` (or
``global_position > cursor``) cannot skip an event that commits later with a smaller number. One order for
all writers also rules out deadlocks between multi-event transactions.

The writer stores ``correlation_id``, ``causation_id`` and ``parent_causation_id`` from ``RequestMeta``
verbatim. They are diagnostic context: no value is resolved against stored events, and a client-supplied id
never becomes a verified causal edge or an authority. Driver errors propagate; the unit of work translates.
"""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.application_bus.registry import SSE_DESTINATION
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, SkmError
from skm.kernel.events import DomainEvent, EventEnvelope
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import EventId, PrincipalId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta
from skm.platform.schema.registry import SchemaRegistry

__all__ = ["PostgresEventReader", "PostgresEventWriter"]

# stream_kind of the instance feed counter row; never a DomainEvent.stream_kind (conventions §4.0.1).
INSTANCE_FEED_KIND: Final = "instance_feed"

type ExplicitOutboxRow = tuple[EventId, str, datetime | None]

_INSTANCE_SCOPE: Final = "SELECT id FROM skm_core.scopes WHERE kind = 'instance'"
_WORKSPACE_FEED: Final = (
    "INSERT INTO skm_core.workspace_event_counters AS c (workspace_id, last_seq) VALUES (%s, %s) "
    "ON CONFLICT (workspace_id) DO UPDATE SET last_seq = c.last_seq + EXCLUDED.last_seq "
    "RETURNING last_seq"
)
_STREAM: Final = (
    "INSERT INTO skm_core.event_streams AS s (stream_kind, stream_id, last_seq) VALUES (%s, %s, %s) "
    "ON CONFLICT (stream_kind, stream_id) DO UPDATE SET last_seq = s.last_seq + EXCLUDED.last_seq "
    "RETURNING last_seq"
)
_INSERT_EVENT: Final = """
INSERT INTO skm_core.domain_events
  (id, workspace_id, stream_kind, stream_id, stream_seq, workspace_seq, global_position, event_type,
   schema_version, actor_id, request_id, correlation_id, causation_id, parent_causation_id, payload,
   occurred_at, recorded_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
RETURNING recorded_at
"""
_INSERT_ROW: Final = (
    "INSERT INTO skm_core.outbox (id, event_id, destination, state, available_at, attempts) "
    "VALUES (%s, %s, %s, 'pending', now(), 0)"
)
_INSERT_EXPLICIT: Final = (
    "INSERT INTO skm_core.outbox (id, event_id, destination, state, available_at, attempts) "
    "VALUES (%s, %s, %s, 'pending', coalesce(%s, now()), 0) "
    "ON CONFLICT ON CONSTRAINT uq_outbox__event_id_destination DO NOTHING"
)
_KNOWN_EVENTS: Final = "SELECT id FROM skm_core.domain_events WHERE id = ANY(%s)"

_SELECT: Final = (
    "SELECT id, event_type, schema_version, workspace_id, stream_kind, stream_id, stream_seq, workspace_seq, "
    "global_position, actor_id, request_id, correlation_id, causation_id, parent_causation_id, payload, "
    "occurred_at, recorded_at FROM skm_core.domain_events "
)
_AFTER_GLOBAL: Final = (
    _SELECT + "WHERE workspace_id IS NULL AND global_position > %s ORDER BY global_position LIMIT %s"
)
_AFTER_WORKSPACE: Final = (
    _SELECT + "WHERE workspace_id = %s AND workspace_seq > %s "
    "AND (%s::text[] IS NULL OR event_type = ANY(%s::text[])) ORDER BY workspace_seq LIMIT %s"
)
_BY_IDS: Final = _SELECT + "WHERE id = ANY(%s)"
_HEAD: Final = "SELECT coalesce(max(workspace_seq), 0) FROM skm_core.domain_events WHERE workspace_id = %s"


def _invalid(message: str, event: object, exc: BaseException) -> InternalError:
    error = InternalError(ErrorCode.INTERNAL_ERROR, message, details={"event": type(event).__name__})
    error.__cause__ = exc
    return error


def _returned(row: tuple[object, ...] | None) -> object:
    """The single value of an ``INSERT … RETURNING`` row, which PostgreSQL always returns here."""
    if row is None:
        raise InternalError(ErrorCode.INTERNAL_ERROR, "insert returned no row")
    return row[0]


@dataclass(frozen=True, slots=True)
class _Prepared:
    event: DomainEvent
    workspace_id: WorkspaceId | None
    stream: tuple[str, UUID]
    payload: JsonObject


class PostgresEventWriter:
    """Validates buffered events and writes them, numbered and fanned out, into the open transaction.

    ``subscriptions`` is the immutable ``SubscriptionIndex`` (``{event_type: (consumer_id, ...)}``) of the
    enabled modules. The writer never commits, rolls back or closes the connection.
    """

    def __init__(
        self,
        *,
        schemas: SchemaRegistry,
        subscriptions: Mapping[str, tuple[str, ...]],
        ids: IdGenerator,
    ) -> None:
        self._schemas = schemas
        self._subscriptions = subscriptions
        self._ids = ids

    def validate(self, event: DomainEvent) -> None:
        """Record-time check (adapters §1.3 step 3): an invalid event is a defect, ``InternalError``."""
        try:
            event.validate(self._schemas)
        except (ValueError, TypeError, SkmError) as exc:
            raise _invalid("domain event is invalid", event, exc) from exc

    def write(
        self,
        conn: psycopg.Connection,
        events: Sequence[DomainEvent],
        meta: RequestMeta,
        *,
        occurred_at: datetime,
        explicit: Sequence[ExplicitOutboxRow] = (),
    ) -> tuple[EventEnvelope, ...]:
        """Allocate, insert and fan out ``events``; then the explicit rows of ``uow.outbox.enqueue``."""
        require_aware(occurred_at)
        prepared = tuple(self._prepare(event) for event in events)
        feeds, streams = self._allocate(conn, prepared)
        correlation_id = meta.correlation_id if meta.correlation_id is not None else meta.request_id
        envelopes: list[EventEnvelope] = []
        for item in prepared:
            workspace_id = item.workspace_id
            feed = feeds[workspace_id]
            feeds[workspace_id] = feed + 1
            stream_seq = streams[item.stream]
            streams[item.stream] = stream_seq + 1
            try:
                envelope = EventEnvelope(
                    id=EventId(self._ids.new_id()),
                    type=item.event.event_type,
                    schema_version=item.event.schema_version,
                    workspace_id=workspace_id,
                    stream_kind=item.stream[0],
                    stream_id=item.stream[1],
                    stream_seq=stream_seq,
                    workspace_seq=None if workspace_id is None else feed,
                    global_position=feed if workspace_id is None else None,
                    actor_id=None,  # RequestMeta carries no principal; the audit record names the actor
                    request_id=meta.request_id,
                    correlation_id=correlation_id,
                    causation_id=meta.request_id,  # the immediate cause is this request
                    parent_causation_id=meta.causation_id,  # the request's own cause, kept with the event
                    occurred_at=occurred_at,
                    recorded_at=occurred_at,  # replaced by the database now() on insert
                    payload=item.payload,
                )
            except ValueError as exc:
                raise _invalid("event envelope is invalid", item.event, exc) from exc
            envelopes.append(self._insert(conn, envelope))
        rows = [
            (self._ids.new_id(), envelope.id, destination)
            for envelope in envelopes
            for destination in self._destinations(envelope)
        ]
        if rows:
            with conn.cursor() as cursor:
                cursor.executemany(_INSERT_ROW, rows)
        self._write_explicit(conn, envelopes, explicit)
        return tuple(envelopes)

    # ------------------------------------------------------------------ steps
    def _prepare(self, event: DomainEvent) -> _Prepared:
        """Commit-time validation (kernel §2.11 rule 2) of an independent payload snapshot, the stored one."""
        try:
            event.validate_registration(self._schemas)
            stream_id = event.stream_id()
            workspace_id = event.scope_workspace_id()
            if not isinstance(stream_id, UUID) or not isinstance(workspace_id, UUID | None):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise ValueError("stream_id and workspace_id must be UUIDs")
            payload = deepcopy(event.payload())
            self._schemas.require_valid(event.event_type, payload)
        except (ValueError, TypeError, SkmError) as exc:
            raise _invalid("domain event is invalid at commit", event, exc) from exc
        return _Prepared(event, workspace_id, (event.stream_kind, stream_id), payload)

    def _allocate(
        self, conn: psycopg.Connection, prepared: Sequence[_Prepared]
    ) -> tuple[dict[WorkspaceId | None, int], dict[tuple[str, UUID], int]]:
        """First number of every feed and stream; counter rows are locked in the global order above."""
        feed_counts = Counter(item.workspace_id for item in prepared)
        stream_counts = Counter(item.stream for item in prepared)
        feeds: dict[WorkspaceId | None, int] = {}
        instance_count = feed_counts.pop(None, 0)
        if instance_count:
            row = conn.execute(_INSTANCE_SCOPE).fetchone()
            if row is None:
                raise InternalError(
                    ErrorCode.INTERNAL_ERROR,
                    "instance scope is missing",
                    details={"reason": "no_instance_scope"},
                )
            locked = conn.execute(_STREAM, (INSTANCE_FEED_KIND, row[0], instance_count)).fetchone()
            feeds[None] = _first(locked, instance_count)
        for workspace_id in sorted(feed_counts, key=lambda value: cast("UUID", value)):
            count = feed_counts[workspace_id]
            feeds[workspace_id] = _first(
                conn.execute(_WORKSPACE_FEED, (workspace_id, count)).fetchone(), count
            )
        streams: dict[tuple[str, UUID], int] = {}
        for (kind, stream_id), count in sorted(stream_counts.items()):
            streams[kind, stream_id] = _first(
                conn.execute(_STREAM, (kind, stream_id, count)).fetchone(), count
            )
        return feeds, streams

    def _insert(self, conn: psycopg.Connection, envelope: EventEnvelope) -> EventEnvelope:
        row = conn.execute(
            _INSERT_EVENT,
            (
                envelope.id,
                envelope.workspace_id,
                envelope.stream_kind,
                envelope.stream_id,
                envelope.stream_seq,
                envelope.workspace_seq,
                envelope.global_position,
                envelope.type,
                envelope.schema_version,
                envelope.actor_id,
                envelope.request_id,
                envelope.correlation_id,
                envelope.causation_id,
                envelope.parent_causation_id,
                to_jsonb(envelope.payload),
                envelope.occurred_at,
            ),
        ).fetchone()
        recorded_at = cast("datetime", _returned(row))
        return replace(envelope, recorded_at=recorded_at.astimezone(UTC))

    def _destinations(self, envelope: EventEnvelope) -> tuple[str, ...]:
        """Consumers of the type, then exactly one ``sse`` row per workspace event (none per instance one)."""
        consumers = self._subscriptions.get(envelope.type, ())
        return consumers if envelope.workspace_id is None else (*consumers, SSE_DESTINATION)

    def _write_explicit(
        self,
        conn: psycopg.Connection,
        envelopes: Sequence[EventEnvelope],
        explicit: Sequence[ExplicitOutboxRow],
    ) -> None:
        """Rows for this unit of work's events or for events committed earlier; any other id is a defect."""
        if not explicit:
            return
        own = {envelope.id for envelope in envelopes}
        foreign = sorted({event_id for event_id, _, _ in explicit if event_id not in own})
        if foreign:
            known = {cast("UUID", row[0]) for row in conn.execute(_KNOWN_EVENTS, (foreign,)).fetchall()}
            for event_id, destination, _ in explicit:
                if event_id not in own and event_id not in known:
                    raise InternalError(
                        ErrorCode.INTERNAL_ERROR,
                        "outbox row for an unknown event",
                        details={"destination": destination},
                    )
        rows = [
            (self._ids.new_id(), event_id, destination, None if at is None else require_aware(at))
            for event_id, destination, at in explicit
        ]
        with conn.cursor() as cursor:
            cursor.executemany(_INSERT_EXPLICIT, rows)


def _first(row: tuple[object, ...] | None, count: int) -> int:
    """First number of the block of ``count`` that the counter's ``RETURNING last_seq`` row ends."""
    return cast("int", _returned(row)) - count + 1


# ---------------------------------------------------------------------- reader


def _envelope(row: tuple[object, ...]) -> EventEnvelope:
    (
        event_id,
        event_type,
        schema_version,
        workspace_id,
        stream_kind,
        stream_id,
        stream_seq,
        workspace_seq,
        global_position,
        actor_id,
        request_id,
        correlation_id,
        causation_id,
        parent_causation_id,
        payload,
        occurred_at,
        recorded_at,
    ) = row
    try:
        return EventEnvelope(
            id=EventId(cast("UUID", event_id)),
            type=cast("str", event_type),
            schema_version=cast("int", schema_version),
            workspace_id=None if workspace_id is None else WorkspaceId(cast("UUID", workspace_id)),
            stream_kind=cast("str", stream_kind),
            stream_id=cast("UUID", stream_id),
            stream_seq=cast("int", stream_seq),
            workspace_seq=cast("int | None", workspace_seq),
            global_position=cast("int | None", global_position),
            actor_id=None if actor_id is None else PrincipalId(cast("UUID", actor_id)),
            request_id=cast("str | None", request_id),
            correlation_id=cast("str", correlation_id),
            causation_id=cast("str | None", causation_id),
            # rows written before 0025 have no parent and stay unknown: None, never inferred
            parent_causation_id=cast("str | None", parent_causation_id),
            occurred_at=cast("datetime", occurred_at).astimezone(UTC),
            recorded_at=cast("datetime", recorded_at).astimezone(UTC),
            payload=cast("JsonObject", payload),
        )
    except ValueError as exc:
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "stored event is malformed", details={"event_id": str(event_id)}
        ) from exc


class PostgresEventReader:
    """``EventReader`` over the committed rows in the unit-of-work snapshot; never commits or closes."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    @staticmethod
    def _envelopes(fetch: Callable[[], list[tuple[object, ...]]]) -> tuple[EventEnvelope, ...]:
        try:
            rows = fetch()
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc
        return tuple(_envelope(row) for row in rows)

    def after_global_position(self, after: int, *, limit: int) -> tuple[EventEnvelope, ...]:
        params = (after, max(limit, 0))
        return self._envelopes(lambda: self._conn.execute(_AFTER_GLOBAL, params).fetchall())

    def after_workspace_seq(
        self,
        workspace_id: WorkspaceId,
        after: int,
        *,
        types: frozenset[str] | None,
        limit: int,
    ) -> tuple[EventEnvelope, ...]:
        names = None if types is None else sorted(types)
        params = (workspace_id, after, names, names, max(limit, 0))
        return self._envelopes(lambda: self._conn.execute(_AFTER_WORKSPACE, params).fetchall())

    def by_ids(self, ids: Sequence[EventId]) -> tuple[EventEnvelope, ...]:
        """Envelopes in the order of ``ids``; unknown ids are left out."""
        rows = self._envelopes(lambda: self._conn.execute(_BY_IDS, (list(ids),)).fetchall())
        found = {envelope.id: envelope for envelope in rows}
        return tuple(found[event_id] for event_id in ids if event_id in found)

    def head_workspace_seq(self, workspace_id: WorkspaceId) -> int:
        try:
            row = self._conn.execute(_HEAD, (workspace_id,)).fetchone()
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc
        return 0 if row is None else cast("int", row[0])
