"""Event ordering contract on both backends: gapless feeds and streams, readers by cursor (ADR 0017).

Each workspace feed (``workspace_seq``), the instance feed (``global_position``) and every aggregate stream
(``stream_seq``) count 1, 2, 3 … in commit order. A unit of work that does not commit, or whose commit
fails, takes no number. Concurrent writers to one workspace never let a cursor reader skip an event: the
memory backend serialises its units of work, PostgreSQL holds the feed counter row until COMMIT.
"""

import threading
from dataclasses import dataclass
from typing import ClassVar, override
from uuid import UUID

import pytest

from fakes.demo_module import Echoed, Noted
from skm.application_bus.ports import EventReader
from skm.kernel.errors import InternalError
from skm.kernel.events import DomainEvent, EventEnvelope
from skm.kernel.ids import EventId, WorkspaceId
from skm.kernel.json_types import JsonObject
from support.backend import TestBackend

NOTE_STREAM = UUID("01900000-0000-7000-8000-0000000000c4")
PROJECT_A = UUID("01900000-0000-7000-8000-0000000000d1")
PROJECT_B = UUID("01900000-0000-7000-8000-0000000000d2")
WRITERS = 3  # with the reader, the four connections of the PostgreSQL test pool
EVENTS_PER_WRITER = 8


@dataclass(frozen=True, slots=True)
class ProjectEchoed(DomainEvent):
    """A workspace event on its own aggregate stream (``project``), checked by the demo ``echoed`` schema."""

    event_type: ClassVar[str] = Echoed.event_type
    stream_kind: ClassVar[str] = "project"

    workspace_id: WorkspaceId
    project: UUID
    text: str

    @override
    def stream_id(self) -> UUID:
        return self.project

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return {"workspace_id": str(self.workspace_id), "text": self.text}


def commit(backend: TestBackend, *events: DomainEvent) -> None:
    with backend.uow() as uow:
        for event in events:
            uow.record(event)
        uow.commit()


def on(backend: TestBackend, project: UUID, text: str, *, other: bool = False) -> ProjectEchoed:
    workspace = backend.seed.other_workspace_id if other else backend.seed.workspace_id
    return ProjectEchoed(workspace_id=workspace, project=project, text=text)


def numbers(events: list[EventEnvelope]) -> list[tuple[str, int | None, int | None, int]]:
    return [(str(e.payload["text"]), e.workspace_seq, e.global_position, e.stream_seq) for e in events]


def test_feeds_and_streams_count_without_gaps_in_commit_order(backend: TestBackend) -> None:
    commit(backend, on(backend, PROJECT_A, "a1"))
    commit(backend, on(backend, PROJECT_B, "b1", other=True))
    commit(backend, on(backend, PROJECT_A, "a2"), on(backend, PROJECT_B, "b2"), on(backend, PROJECT_A, "a3"))
    commit(backend, Noted(stream=NOTE_STREAM, text="n1"))
    commit(backend, on(backend, PROJECT_A, "a4"), Noted(stream=NOTE_STREAM, text="n2"))
    assert numbers(backend.envelopes(workspace_id=backend.seed.workspace_id)) == [
        ("a1", 1, None, 1),
        ("a2", 2, None, 2),
        ("b2", 3, None, 2),  # project B's stream continues across workspaces
        ("a3", 4, None, 3),
        ("a4", 5, None, 4),
    ]
    assert numbers(backend.envelopes(workspace_id=backend.seed.other_workspace_id)) == [("b1", 1, None, 1)]
    instance = [e for e in backend.envelopes() if e.workspace_id is None]
    assert numbers(instance) == [("n1", None, 1, 1), ("n2", None, 2, 2)]


def test_units_of_work_that_do_not_commit_take_no_number(backend: TestBackend) -> None:
    commit(backend, on(backend, PROJECT_A, "first"))
    with backend.uow() as uow:  # left without commit
        uow.record(on(backend, PROJECT_A, "dropped"))
        uow.record(Noted(stream=NOTE_STREAM, text="dropped"))

    def failing() -> None:
        with backend.uow() as uow:
            uow.record(on(backend, PROJECT_A, "failed"))
            uow.record(Noted(stream=NOTE_STREAM, text="failed"))
            uow.outbox.enqueue(EventId(backend.ids.new_id()), "hook:lost")  # commit fails after allocation
            uow.commit()

    with pytest.raises(InternalError):
        failing()
    commit(backend, on(backend, PROJECT_A, "second"), Noted(stream=NOTE_STREAM, text="note"))
    assert numbers(backend.envelopes()) == [
        ("first", 1, None, 1),
        ("second", 2, None, 2),
        ("note", None, 1, 1),
    ]


def test_a_cursor_reader_sees_every_event_once_and_in_order(backend: TestBackend) -> None:
    for n in range(7):
        commit(backend, Echoed(workspace_id=backend.seed.workspace_id, text=f"e{n}"))
    seen: list[int] = []
    cursor = 0
    while True:
        with backend.uow(readonly=True) as uow:
            page = uow.repo(EventReader).after_workspace_seq(
                backend.seed.workspace_id, cursor, types=None, limit=3
            )
        if not page:
            break
        seen.extend(e.workspace_seq or 0 for e in page)
        cursor = page[-1].workspace_seq or 0
    assert seen == list(range(1, 8))


def test_concurrent_writers_never_let_a_cursor_reader_skip_an_event(backend: TestBackend) -> None:
    workspace = backend.seed.workspace_id
    total = WRITERS * EVENTS_PER_WRITER
    start = threading.Barrier(WRITERS + 1)
    errors: list[BaseException] = []

    def write(writer: int) -> None:
        try:
            start.wait(timeout=10)
            for n in range(EVENTS_PER_WRITER):
                commit(backend, Echoed(workspace_id=workspace, text=f"w{writer}-{n}"))
        except BaseException as exc:  # noqa: BLE001 - reported by the main thread
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(writer,)) for writer in range(WRITERS)]
    for thread in threads:
        thread.start()
    start.wait(timeout=10)
    observed: list[int] = []
    cursor = 0
    for _ in range(10_000):  # bounded polling; every round reads one committed snapshot
        with backend.uow(readonly=True) as uow:
            page = uow.repo(EventReader).after_workspace_seq(workspace, cursor, types=None, limit=5)
        # a page always continues exactly at the cursor: nothing committed later has a smaller number
        assert [e.workspace_seq for e in page] == list(range(cursor + 1, cursor + 1 + len(page)))
        observed.extend(e.workspace_seq or 0 for e in page)
        cursor = observed[-1] if observed else 0
        if cursor == total or (errors and not any(t.is_alive() for t in threads)):
            break
    for thread in threads:
        thread.join(timeout=30)
    assert not errors, errors
    assert not any(thread.is_alive() for thread in threads)
    assert observed == list(range(1, total + 1))
    texts = sorted(str(e.payload["text"]) for e in backend.envelopes(workspace_id=workspace))
    assert texts == sorted(f"w{w}-{n}" for w in range(WRITERS) for n in range(EVENTS_PER_WRITER))
