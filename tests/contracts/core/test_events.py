"""Event and outbox contract on both backends (kernel-platform §2.9/§2.11, adapters §1.4/§2.2, ADR 0017).

The envelope a commit stores, the outbox rows it fans out and what ``EventReader`` returns are the same on
memory and PostgreSQL. Only ``recorded_at`` differs by design (memory: the backend clock, PostgreSQL: the
database ``now()``), and ids are compared within one backend, never across them.
"""

from uuid import UUID

import pytest

from fakes.app import request_id
from fakes.demo_module import Echoed, Noted
from skm.application_bus.ports import EventReader
from skm.kernel.errors import InternalError
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import EventId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta
from support.backend import OutboxRow, TestBackend

NOTE_STREAM = UUID("01900000-0000-7000-8000-0000000000c3")
TEXTS = ("plain", 'quote " and \\ backslash', "кириллица и 漢字", "line\nbreak\ttab", "emoji 🙂", " ")


def echoed(backend: TestBackend, text: str = "hello", *, workspace: WorkspaceId | None = None) -> Echoed:
    return Echoed(workspace_id=workspace or backend.seed.workspace_id, text=text)


def commit(backend: TestBackend, *events: Echoed | Noted, meta: RequestMeta | None = None) -> RequestMeta:
    meta = meta or backend.meta()
    with backend.uow_factory(meta) as uow:
        for event in events:
            uow.record(event)
        uow.commit()
    return meta


def rows_of(backend: TestBackend, event: EventEnvelope) -> list[tuple[str, str, int]]:
    rows: list[OutboxRow] = [row for row in backend.outbox_rows() if row.event_id == event.id]
    return sorted((row.destination, row.state, row.attempts) for row in rows)


# ------------------------------------------------------------------------------------- envelopes


def test_a_workspace_event_stores_its_numbers_request_and_causes(backend: TestBackend) -> None:
    parent = "01900000-0000-7000-8000-0000000000e1"
    meta = commit(
        backend, echoed(backend), meta=backend.meta(correlation_id=request_id(900), causation_id=parent)
    )
    (event,) = backend.envelopes()
    assert (event.type, event.schema_version, event.workspace_id) == (
        Echoed.event_type,
        1,
        backend.seed.workspace_id,
    )
    assert (event.stream_kind, event.stream_id, event.stream_seq) == (
        "workspace",
        backend.seed.workspace_id,
        1,
    )
    assert (event.workspace_seq, event.global_position, event.actor_id) == (1, None, None)
    assert (event.request_id, event.correlation_id, event.causation_id, event.parent_causation_id) == (
        meta.request_id,
        request_id(900),
        meta.request_id,  # the immediate cause is this request
        parent,  # and its own cause is kept with the event
    )
    assert event.payload == {"workspace_id": str(backend.seed.workspace_id), "text": "hello"}
    assert event.occurred_at == backend.clock.now()
    assert event.recorded_at.tzinfo is not None


def test_correlation_defaults_to_the_request_and_the_parent_to_none(backend: TestBackend) -> None:
    meta = commit(backend, echoed(backend))
    (event,) = backend.envelopes()
    assert (event.correlation_id, event.causation_id, event.parent_causation_id) == (
        meta.request_id,
        meta.request_id,
        None,
    )


def test_an_instance_event_has_a_global_position_and_no_workspace_numbers(backend: TestBackend) -> None:
    commit(backend, Noted(stream=NOTE_STREAM, text="one"), Noted(stream=NOTE_STREAM, text="two"))
    first, second = backend.envelopes()
    assert [(e.workspace_id, e.workspace_seq, e.global_position, e.stream_seq) for e in (first, second)] == [
        (None, None, 1, 1),
        (None, None, 2, 2),
    ]
    assert (first.stream_kind, first.stream_id) == ("config", NOTE_STREAM)
    assert backend.envelopes(workspace_id=backend.seed.workspace_id) == []


@pytest.mark.parametrize("text", TEXTS)
def test_a_payload_round_trips_exactly(backend: TestBackend, text: str) -> None:
    commit(backend, echoed(backend, text))
    (event,) = backend.envelopes()
    assert event.payload == {"workspace_id": str(backend.seed.workspace_id), "text": text}


def test_an_invalid_event_is_refused_at_record_and_nothing_is_stored(backend: TestBackend) -> None:
    with backend.uow() as uow, pytest.raises(InternalError):
        uow.record(Echoed(workspace_id=backend.seed.workspace_id, text=7))  # type: ignore[arg-type]
    assert backend.envelopes() == []
    assert backend.outbox_rows() == []


# ------------------------------------------------------------------------------------- outbox fan-out


def test_a_workspace_event_gets_its_subscribers_and_exactly_one_sse_row(backend: TestBackend) -> None:
    commit(backend, echoed(backend, "a"), echoed(backend, "b"))
    first, second = backend.envelopes()
    for event in (first, second):
        assert rows_of(backend, event) == [("demo.on_echoed", "pending", 0), ("sse", "pending", 0)]


def test_an_instance_event_without_subscribers_gets_no_row(backend: TestBackend) -> None:
    commit(backend, Noted(stream=NOTE_STREAM, text="quiet"))
    assert backend.outbox_rows() == []


def test_an_explicit_row_for_an_earlier_event_is_written_once(backend: TestBackend) -> None:
    commit(backend, echoed(backend))
    (event,) = backend.envelopes()
    for _ in range(2):  # a duplicate in the same and in a later unit of work is a no-op
        with backend.uow() as uow:
            uow.outbox.enqueue(event.id, "hook:audit")
            uow.outbox.enqueue(event.id, "hook:audit")
            uow.commit()
    assert rows_of(backend, event) == [
        ("demo.on_echoed", "pending", 0),
        ("hook:audit", "pending", 0),
        ("sse", "pending", 0),
    ]


def test_an_explicit_row_is_buffered_until_commit_and_dropped_on_rollback(backend: TestBackend) -> None:
    commit(backend, echoed(backend))
    (event,) = backend.envelopes()
    with backend.uow() as uow:
        uow.outbox.enqueue(event.id, "hook:later")
        assert len(backend.outbox_rows()) == 2
    assert [row.destination for row in backend.outbox_rows()].count("hook:later") == 0


def test_an_explicit_row_for_an_unknown_event_fails_the_commit(backend: TestBackend) -> None:
    def body() -> None:
        with backend.uow() as uow:
            uow.record(echoed(backend))
            uow.outbox.enqueue(EventId(backend.ids.new_id()), "hook:lost")
            uow.commit()

    with pytest.raises(InternalError):
        body()
    assert backend.envelopes() == []
    assert backend.outbox_rows() == []


@pytest.mark.parametrize("destination", ["one", "nope:x", "hook:", "sse", "demo.on_echoed"])
def test_an_explicit_row_needs_an_external_prefix(backend: TestBackend, destination: str) -> None:
    commit(backend, echoed(backend))
    (event,) = backend.envelopes()
    with backend.uow() as uow, pytest.raises(ValueError, match="external prefix"):
        uow.outbox.enqueue(event.id, destination)


# ------------------------------------------------------------------------------------- reader


def test_the_reader_returns_requested_ids_in_order_and_skips_unknown_ones(backend: TestBackend) -> None:
    commit(backend, echoed(backend, "a"), echoed(backend, "b"), echoed(backend, "c"))
    a, b, c = backend.envelopes()
    unknown = EventId(backend.ids.new_id())
    with backend.uow(readonly=True) as uow:
        found = uow.repo(EventReader).by_ids([c.id, unknown, a.id])
    assert [event.payload["text"] for event in found] == ["c", "a"]
    assert b.id not in {event.id for event in found}


def test_the_reader_pages_a_workspace_feed_by_cursor_types_and_limit(backend: TestBackend) -> None:
    other = backend.seed.other_workspace_id
    commit(backend, echoed(backend, "1"), echoed(backend, "x", workspace=other), echoed(backend, "2"))
    commit(backend, echoed(backend, "3"), Noted(stream=NOTE_STREAM, text="instance"))
    workspace = backend.seed.workspace_id
    with backend.uow(readonly=True) as uow:
        reader = uow.repo(EventReader)
        page = reader.after_workspace_seq(workspace, 1, types=None, limit=1)
        rest = reader.after_workspace_seq(workspace, 2, types=frozenset({Echoed.event_type}), limit=10)
        none = reader.after_workspace_seq(
            workspace, 0, types=frozenset({"urn:skm:demo:event:other:v1"}), limit=10
        )
        empty = reader.after_workspace_seq(workspace, 0, types=None, limit=0)
        heads = (reader.head_workspace_seq(workspace), reader.head_workspace_seq(other))
        unknown_head = reader.head_workspace_seq(WorkspaceId(backend.ids.new_id()))
        instance = reader.after_global_position(0, limit=10)
    assert [(e.workspace_seq, e.payload["text"]) for e in page] == [(2, "2")]
    assert [(e.workspace_seq, e.payload["text"]) for e in rest] == [(3, "3")]
    assert (none, empty) == ((), ())
    assert (heads, unknown_head) == ((3, 1), 0)
    assert [(e.global_position, e.payload["text"]) for e in instance] == [(1, "instance")]


def test_the_reader_does_not_see_rolled_back_events(backend: TestBackend) -> None:
    commit(backend, echoed(backend, "kept"))
    with backend.uow() as uow:
        uow.record(echoed(backend, "dropped"))
        uow.rollback()
    with backend.uow(readonly=True) as uow:
        seen = uow.repo(EventReader).after_workspace_seq(backend.seed.workspace_id, 0, types=None, limit=10)
    assert [event.payload["text"] for event in seen] == ["kept"]


def test_changing_a_returned_payload_does_not_rewrite_history(backend: TestBackend) -> None:
    commit(backend, echoed(backend, "original"))
    with backend.uow(readonly=True) as uow:
        (event,) = uow.repo(EventReader).after_workspace_seq(
            backend.seed.workspace_id, 0, types=None, limit=1
        )
        event.payload["text"] = "rewritten"
        (again,) = uow.repo(EventReader).by_ids([event.id])
    assert again.payload["text"] == "original"
    assert backend.envelopes()[0].payload["text"] == "original"
