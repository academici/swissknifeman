"""Contract of the transactional memory UoW and the core repositories (kernel §2.11, adapters §2.2).

``test_uow.py`` runs the shared rules on both backends; here they are proven for the memory backend, which is
the backend of every unit test.
"""

import threading
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from typing import ClassVar, override
from uuid import UUID, uuid4

import pytest

import skm
from fakes.app import Harness, build_harness, request_id
from fakes.demo_module import Echoed, Noted
from skm.application_bus.ports import (
    AuditLog,
    AuditRecord,
    ConsumerReceipts,
    EventReader,
    IdempotencyReceipt,
    IdempotencyStore,
    OutboxState,
    OutboxStore,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, ValidationFailed
from skm.kernel.events import DomainEvent, EventEnvelope
from skm.kernel.ids import EventId, PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry

NOTE_STREAM = UUID("01900000-0000-7000-8000-0000000000c1")


@pytest.fixture
def h() -> Harness:
    return build_harness()


def echoed(h: Harness, text: str = "hello") -> Echoed:
    return Echoed(workspace_id=h.seed.workspace_id, text=text)


def commit_echo(h: Harness, text: str = "hello") -> EventId:
    with h.uow_factory(h.meta()) as uow:
        uow.record(echoed(h, text))
        uow.commit()
    return h.events()[-1].id


# ---------------------------------------------------------------- rollback and commit lifecycle


def test_exit_without_commit_loses_nothing_committed_and_keeps_nothing_new(h: Harness) -> None:
    commit_echo(h, "kept")
    before = h.backend.committed
    with h.uow_factory(h.meta()) as uow:
        uow.record(echoed(h, "dropped"))
    assert h.backend.committed is before
    assert [e.payload["text"] for e in h.events()] == ["kept"]
    assert h.backend.committed.core.feed_seq[h.seed.workspace_id] == 1  # the dropped event consumed no number


def test_exception_inside_with_rolls_back_and_is_not_swallowed(h: Harness) -> None:
    def body() -> None:
        with h.uow_factory(h.meta()) as uow:
            uow.record(echoed(h))
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        body()
    assert h.events() == []
    assert h.backend.committed.core.outbox == {}


def test_failed_commit_publishes_nothing(h: Harness) -> None:
    commit_echo(h, "kept")

    def body() -> None:
        with h.uow_factory(h.meta()) as uow:
            uow.record(echoed(h, "second"))
            uow.outbox.enqueue(EventId(uuid4()), "hook:one")  # no such event: the whole commit fails
            uow.commit()

    with pytest.raises(InternalError):
        body()
    assert [e.payload["text"] for e in h.events()] == ["kept"]
    assert len(h.backend.committed.core.outbox) == 2  # only the rows of "kept"


def test_second_commit_and_commit_after_rollback_are_runtime_errors(h: Harness) -> None:
    with h.uow_factory(h.meta()) as uow:
        uow.commit()
        with pytest.raises(RuntimeError):
            uow.commit()
    with h.uow_factory(h.meta()) as uow:
        uow.rollback()
        uow.rollback()  # idempotent
        with pytest.raises(RuntimeError):
            uow.commit()


def test_a_unit_of_work_cannot_be_entered_twice(h: Harness) -> None:
    uow = h.uow_factory(h.meta())
    with uow:
        pass
    with pytest.raises(RuntimeError), uow:
        pass


def test_working_copy_is_invisible_until_commit(h: Harness) -> None:
    with h.uow_factory(h.meta()) as uow:
        uow.record(echoed(h))
        assert h.events() == []
        uow.commit()
        assert len(h.events()) == 1


# ---------------------------------------------------------------- readonly


def test_readonly_unit_of_work_refuses_every_write(h: Harness) -> None:
    before = h.backend.committed
    with h.uow_factory(h.meta(), readonly=True) as uow:
        assert uow.readonly
        with pytest.raises(RuntimeError):
            uow.record(echoed(h))
        with pytest.raises(RuntimeError):
            uow.outbox.enqueue(EventId(uuid4()), "hook:one")
        with pytest.raises(RuntimeError):
            uow.repo(AuditLog).append(_audit(h))
        with pytest.raises(RuntimeError):
            uow.repo(ConsumerReceipts).add("c", EventId(uuid4()), h.clock.now())
        uow.commit()  # nothing can have been written: committing is a no-op
    assert h.backend.committed is before


def test_unknown_port_is_internal_error_and_repos_are_cached(h: Harness) -> None:
    class Unknown:
        pass

    with h.uow_factory(h.meta()) as uow:
        assert uow.repo(AuditLog) is uow.repo(AuditLog)
        with pytest.raises(InternalError):
            uow.repo(Unknown)


def test_two_units_of_work_are_never_open_at_once_in_sequential_use(h: Harness) -> None:
    commit_echo(h)
    with h.uow_factory(h.meta(), readonly=True):
        pass
    assert h.backend.peak_active == 1
    commit_echo(h, "again")
    assert h.backend.peak_active == 1
    assert h.backend.active == 0


@pytest.mark.parametrize(("outer_readonly", "inner_readonly"), [(False, False), (False, True), (True, False)])
def test_nested_unit_of_work_is_refused_and_the_outer_one_loses_nothing(
    h: Harness, outer_readonly: bool, inner_readonly: bool
) -> None:
    """adapters §2.2: one unit of work at a time; the holder cannot open a second one (e.g. in a handler)."""

    def enter_nested() -> None:
        with h.uow_factory(h.meta(), readonly=inner_readonly):
            pytest.fail("the nested unit of work must not be entered")

    commit_echo(h, "kept")
    committed_before = [e.id for e in h.events()]
    outbox_before = dict(h.backend.committed.core.outbox)
    with h.uow_factory(h.meta(), readonly=outer_readonly) as outer:
        with pytest.raises(RuntimeError, match="only one unit of work"):
            enter_nested()
        assert h.backend.active == 1  # the refused entry changed nothing
        if not outer_readonly:
            outer.record(echoed(h, "outer"))
        outer.commit()
    assert h.backend.active == 0
    assert h.backend.peak_active == 1
    assert [e.id for e in h.events()][: len(committed_before)] == committed_before
    assert outbox_before.items() <= h.backend.committed.core.outbox.items()
    expected = ["kept"] if outer_readonly else ["kept", "outer"]
    assert [e.payload["text"] for e in h.events()] == expected
    commit_echo(h, "next")  # the lock was released exactly once: a later entry works
    assert h.backend.active == 0


def test_refused_nested_entry_releases_only_its_own_lock_acquisition(h: Harness) -> None:
    with h.uow_factory(h.meta()) as outer:
        with pytest.raises(RuntimeError, match="only one unit of work"):
            h.uow_factory(h.meta()).__enter__()
        outer.rollback()
    results: list[bool] = []

    def other_thread() -> None:
        acquired = h.backend.lock.acquire(timeout=1)
        results.append(acquired)
        if acquired:
            h.backend.lock.release()

    thread = threading.Thread(target=other_thread)
    thread.start()
    thread.join(timeout=5)
    assert results == [True]  # no leaked recursion level keeps the lock held


# ---------------------------------------------------------------- events, sequences, causal metadata


def test_commit_assigns_sequences_and_envelope_metadata(h: Harness) -> None:
    meta = h.meta(request=request_id(7), correlation_id=request_id(3), causation_id=request_id(5))
    with h.uow_factory(meta) as uow:
        uow.record(echoed(h, "one"))
        uow.record(echoed(h, "two"))
        uow.record(Noted(stream=NOTE_STREAM, text="instance"))
        uow.commit()
    one, two, noted = h.events()
    assert (one.stream_seq, two.stream_seq) == (1, 2)
    assert (one.workspace_seq, two.workspace_seq) == (1, 2)
    assert one.global_position is None
    assert (noted.workspace_id, noted.workspace_seq, noted.global_position, noted.stream_seq) == (
        None,
        None,
        1,
        1,
    )
    for envelope in (one, two, noted):
        assert envelope.request_id == request_id(7)
        assert envelope.causation_id == request_id(7)  # the command itself is the immediate cause
        assert envelope.parent_causation_id == request_id(5)  # meta.causation_id is the parent
        assert envelope.correlation_id == request_id(3)
        assert envelope.recorded_at == h.clock.now()
    assert len({e.id for e in h.events()}) == 3


def test_correlation_defaults_to_the_request_id_and_parent_to_none(h: Harness) -> None:
    with h.uow_factory(h.meta(request=request_id(9))) as uow:
        uow.record(echoed(h))
        uow.commit()
    (envelope,) = h.events()
    assert envelope.correlation_id == request_id(9)
    assert envelope.parent_causation_id is None


def test_numbers_continue_across_units_of_work(h: Harness) -> None:
    commit_echo(h, "a")
    commit_echo(h, "b")
    assert [(e.stream_seq, e.workspace_seq) for e in h.events()] == [(1, 1), (2, 2)]
    with h.uow_factory(h.meta(), readonly=True) as uow:
        reader = uow.repo(EventReader)
        assert reader.head_workspace_seq(h.seed.workspace_id) == 2
        assert reader.head_workspace_seq(h.seed.other_workspace_id) == 0
        after_one = reader.after_workspace_seq(h.seed.workspace_id, 1, types=None, limit=10)
        assert [e.workspace_seq for e in after_one] == [2]
        assert reader.after_workspace_seq(h.seed.workspace_id, 0, types=frozenset({"x"}), limit=10) == ()


def test_invalid_event_is_refused_at_record_as_internal_error(h: Harness) -> None:
    with h.uow_factory(h.meta()) as uow:
        with pytest.raises(InternalError) as raised:
            uow.record(echoed(h, ""))  # minLength 1
        assert "text" not in raised.value.details  # nothing of the payload is echoed back
        uow.commit()
    assert h.events() == []


def test_overlong_causal_id_fails_the_commit_and_stores_nothing(h: Harness) -> None:
    def body() -> None:
        with h.uow_factory(h.meta(causation_id="c" * 65)) as uow:
            uow.record(echoed(h))
            uow.commit()

    with pytest.raises(InternalError):
        body()
    assert h.events() == []


# ---------------------------------------------------------------- outbox rows


def rows(h: Harness) -> list[tuple[EventId, str]]:
    return sorted((r.event_id, r.destination) for r in h.backend.committed.core.outbox.values())


def test_workspace_event_gets_subscriber_row_and_exactly_one_sse_row(h: Harness) -> None:
    event_id = commit_echo(h)
    assert rows(h) == [(event_id, "demo.on_echoed"), (event_id, "sse")]
    assert all(
        r.state is OutboxState.PENDING and r.attempts == 0 for r in h.backend.committed.core.outbox.values()
    )
    assert {r.workspace_id for r in h.backend.committed.core.outbox.values()} == {h.seed.workspace_id}


def test_instance_event_gets_no_sse_row(h: Harness) -> None:
    with h.uow_factory(h.meta()) as uow:
        uow.record(Noted(stream=NOTE_STREAM, text="instance"))
        uow.commit()
    assert rows(h) == []  # no subscriber of this type, and the instance feed is read by global_position


def test_explicit_enqueue_is_deduplicated_and_validated(h: Harness) -> None:
    event_id = commit_echo(h)
    later = h.clock.now() + timedelta(minutes=5)
    with h.uow_factory(h.meta()) as uow:
        uow.outbox.enqueue(event_id, "hook:sub1", available_at=later)
        uow.outbox.enqueue(event_id, "hook:sub1")  # same pair: a no-op
        uow.commit()
    with h.uow_factory(h.meta()) as uow:
        uow.outbox.enqueue(event_id, "hook:sub1")  # already committed: still a no-op
        with pytest.raises(ValueError, match="external prefix"):
            uow.outbox.enqueue(event_id, "sse")  # not an external destination
        with pytest.raises(ValueError, match="external prefix"):
            uow.outbox.enqueue(event_id, "other:x")
        uow.commit()
    hook = [r for r in h.backend.committed.core.outbox.values() if r.destination == "hook:sub1"]
    assert len(hook) == 1
    assert hook[0].available_at == later  # the first enqueue won


def test_enqueue_is_buffered_until_commit_and_dropped_on_rollback(h: Harness) -> None:
    event_id = commit_echo(h)
    with h.uow_factory(h.meta()) as uow:
        uow.outbox.enqueue(event_id, "hook:sub1")
    assert all(r.destination != "hook:sub1" for r in h.backend.committed.core.outbox.values())


def test_claim_in_a_rolled_back_unit_of_work_leaves_the_committed_outbox_row_pending(h: Harness) -> None:
    commit_echo(h)
    now = h.clock.now()
    with h.uow_factory(h.meta()) as uow:
        (item,) = uow.repo(OutboxStore).claim(destination="sse", relay_id="r1", now=now, limit=5)
    (row,) = (r for r in h.backend.committed.core.outbox.values() if r.destination == "sse")
    assert row.id == item.id
    assert (row.state, row.attempts, row.claimed_by) == (OutboxState.PENDING, 0, None)


def test_working_copy_shares_immutable_rows_but_never_their_containers(h: Harness) -> None:
    commit_echo(h)
    committed = h.backend.committed.core
    working = deepcopy(committed)
    assert working.events == committed.events
    assert working.events is not committed.events
    assert working.events[0] is committed.events[0]  # a frozen envelope with a stored payload snapshot
    assert working.outbox_keys is not committed.outbox_keys
    for key, row in working.outbox.items():
        assert row == committed.outbox[key]
        assert row is not committed.outbox[key]  # outbox rows are mutable
    assert working.config_entries is not committed.config_entries
    assert working.clock is committed.clock


def test_outbox_store_claim_and_failure_flow(h: Harness) -> None:
    commit_echo(h)
    now = h.clock.now()
    with h.uow_factory(h.meta()) as uow:
        store = uow.repo(OutboxStore)
        due = store.due_destinations(
            consumer_ids=frozenset({"demo.on_echoed"}),
            prefixes=frozenset(),
            include_sse=True,
            now=now,
            after=None,
            limit=10,
        )
        assert due == ("demo.on_echoed", "sse")
        (item,) = store.claim(destination="sse", relay_id="r1", now=now, limit=5)
        assert item.attempts == 1
        assert store.claim(destination="sse", relay_id="r2", now=now, limit=5) == ()  # claimed
        assert not store.mark_failed(
            item.id, relay_id="r2", error="x", next_at=now, dead=False
        )  # stale claimant
        assert store.mark_failed(item.id, relay_id="r1", error="x", next_at=now, dead=True)
        assert store.retry_dead(outbox_id=item.id, event_id=None, destination=None, now=now) == 1
        with pytest.raises(ValueError, match="needs a filter"):
            store.retry_dead(outbox_id=None, event_id=None, destination=None, now=now)
        (again,) = store.claim(destination="sse", relay_id="r1", now=now, limit=5)
        assert (again.attempts, again.delivery_generation) == (1, 1)
        store.mark_delivered(again.id, at=now)
        uow.commit()
    assert {r.state for r in h.backend.committed.core.outbox.values()} == {
        OutboxState.PENDING,
        OutboxState.DELIVERED,
    }


# ---------------------------------------------------------------- idempotency, receipts, audit, scopes


def _receipt(
    h: Harness, key: str = "k", *, ttl: timedelta = timedelta(hours=1), result: str = "a"
) -> IdempotencyReceipt:
    now = h.clock.now()
    return IdempotencyReceipt(
        workspace_id=h.seed.workspace_id,
        principal_id=h.seed.principal_id,
        operation="demo.echo",
        key=key,
        request_digest="sha256:" + "a" * 64,
        result={"text": result},
        created_at=now,
        expires_at=now + ttl,
    )


def _audit(h: Harness) -> AuditRecord:
    return AuditRecord(
        id=uuid4(),
        workspace_id=h.seed.workspace_id,
        actor_id=PrincipalId(h.seed.principal_id),
        action="demo.echo",
        target={"scope": None, "permission": "demo.echo"},
        decision="allowed",
        reason_code=None,
        request_id=request_id(),
        recorded_at=h.clock.now(),
    )


def test_idempotency_store_expiry_and_live_conflict(h: Harness) -> None:
    ws, principal = h.seed.workspace_id, h.seed.principal_id
    with h.uow_factory(h.meta()) as uow:
        store = uow.repo(IdempotencyStore)
        store.put(_receipt(h))
        with pytest.raises(Conflict) as raised:
            store.put(_receipt(h, result="b"))  # a live row of the same key: the receipt race
        assert raised.value.code is ErrorCode.ALREADY_EXISTS
        got = store.get(ws, principal, "demo.echo", "k")
        assert got is not None
        assert got.result == {"text": "a"}
        got.result["text"] = "mutated"  # a copy: the stored row does not change
        assert store.get(ws, principal, "demo.echo", "k") == _receipt(h)
        assert store.get(None, principal, "demo.echo", "k") is None  # instance-level key space is separate
        uow.commit()
    h.clock.advance(timedelta(hours=2))
    with h.uow_factory(h.meta()) as uow:
        store = uow.repo(IdempotencyStore)
        assert store.get(ws, principal, "demo.echo", "k") is None  # never returns expired rows
        store.put(_receipt(h, result="c"))  # overwrites the expired row
        assert store.purge_expired(h.clock.now() + timedelta(hours=5), limit=10) == 1
        uow.commit()


def test_consumer_receipts_and_audit_are_written_on_commit_only(h: Harness) -> None:
    event_id = EventId(uuid4())
    with h.uow_factory(h.meta()) as uow:
        receipts = uow.repo(ConsumerReceipts)
        assert not receipts.seen("c", event_id)
        receipts.add("c", event_id, h.clock.now())
        receipts.add("c", event_id, h.clock.now() + timedelta(hours=1))  # no-op, the first time stays
        uow.repo(AuditLog).append(_audit(h))
        assert receipts.seen("c", event_id)
    assert h.audit() == []
    assert not h.backend.committed.core.consumer_receipts
    with h.uow_factory(h.meta()) as uow:
        uow.repo(ConsumerReceipts).add("c", event_id, h.clock.now())
        uow.repo(AuditLog).append(_audit(h))
        uow.commit()
    assert len(h.audit()) == 1
    with h.uow_factory(h.meta()) as uow:
        receipts = uow.repo(ConsumerReceipts)
        assert receipts.seen("c", event_id)
        assert receipts.purge(before=h.clock.now() + timedelta(seconds=1), limit=10) == 1
        assert not receipts.seen("c", event_id)


def test_scope_registry_enforces_parents_workspace_and_uniqueness(h: Harness) -> None:
    ws = h.seed.workspace_id
    project = ScopeId(uuid4())
    with h.uow_factory(h.meta()) as uow:
        scopes = uow.repo(ScopeRegistry)
        scopes.create(project, ScopeKind.PROJECT, parent=ScopeId(ws), workspace_id=ws)
        assert [r.kind for r in scopes.ancestors(project)] == [
            ScopeKind.INSTANCE,
            ScopeKind.WORKSPACE,
            ScopeKind.PROJECT,
        ]
        with pytest.raises(Conflict):
            scopes.create(project, ScopeKind.PROJECT, parent=ScopeId(ws), workspace_id=ws)
        with pytest.raises(ValidationFailed) as wrong_parent:
            scopes.create(ScopeId(uuid4()), ScopeKind.RUN, parent=ScopeId(ws), workspace_id=ws)
        assert wrong_parent.value.details["parent_kind"] == "workspace"
        with pytest.raises(ValidationFailed):
            scopes.create(
                ScopeId(uuid4()), ScopeKind.PROJECT, parent=ScopeId(ws), workspace_id=WorkspaceId(uuid4())
            )
        with pytest.raises(NotFound):
            scopes.get(ScopeId(uuid4()))
        with pytest.raises(Conflict):  # a second instance scope
            scopes.create(ScopeId(uuid4()), ScopeKind.INSTANCE, parent=None, workspace_id=None)
        assert scopes.instance().id == h.seed.instance_id


def test_stored_receipt_is_a_copy_of_the_callers_object(h: Harness) -> None:
    """Mutating the caller's result after ``put`` changes nothing in the stored row."""
    receipt = _receipt(h)
    with h.uow_factory(h.meta()) as uow:
        uow.repo(IdempotencyStore).put(receipt)
        receipt.result["text"] = "changed"
        uow.commit()
    stored = next(iter(h.backend.committed.core.idempotency.values()))
    assert stored == replace(receipt, result={"text": "a"})


# ---------------------------------------------------------------- commit-time validation (kernel §2.11)


@dataclass(frozen=True, slots=True)
class SharedEcho(DomainEvent):
    """A frozen event whose payload reads a mutable object that the caller still holds."""

    event_type: ClassVar[str] = Echoed.event_type
    stream_kind: ClassVar[str] = "workspace"

    workspace_id: WorkspaceId
    shared: dict[str, str]

    @override
    def stream_id(self) -> UUID:
        return self.workspace_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return {"workspace_id": str(self.workspace_id), "text": self.shared["text"]}


@dataclass(frozen=True, slots=True)
class AliasedEcho(SharedEcho):
    """``payload()`` hands out the very same dict every time."""

    @override
    def payload(self) -> JsonObject:
        return self.shared  # type: ignore[return-value]


def _write_everything_else(h: Harness, uow: UnitOfWork) -> None:
    uow.repo(IdempotencyStore).put(_receipt(h))
    uow.repo(ConsumerReceipts).add("c", EventId(uuid4()), h.clock.now())
    uow.repo(AuditLog).append(_audit(h))
    uow.repo(ScopeRegistry).create(
        ScopeId(uuid4()),
        ScopeKind.PROJECT,
        parent=ScopeId(h.seed.workspace_id),
        workspace_id=h.seed.workspace_id,
    )


def test_payload_changed_after_record_is_refused_at_commit_and_nothing_is_stored(h: Harness) -> None:
    commit_echo(h, "kept")
    before = deepcopy(h.backend.committed)
    shared = {"text": "valid"}

    def body() -> None:
        with h.uow_factory(h.meta()) as uow:
            uow.record(echoed(h, "first"))  # a valid event ahead of the broken one
            uow.record(SharedEcho(workspace_id=h.seed.workspace_id, shared=shared))
            uow.outbox.enqueue(EventId(uuid4()), "hook:one")
            _write_everything_else(h, uow)
            shared["text"] = ""  # minLength 1: schema-invalid since record()
            uow.commit()

    with pytest.raises(InternalError) as raised:
        body()
    assert raised.value.code is ErrorCode.INTERNAL_ERROR
    assert "valid" not in str(raised.value.details)
    assert h.backend.committed.core == before.core  # events, outbox, receipts, audit, scopes, sequences
    assert [e.payload["text"] for e in h.events()] == ["kept"]
    assert h.backend.active == 0
    commit_echo(h, "after")  # the backend still works and numbering continues without a gap
    assert [e.workspace_seq for e in h.events()] == [1, 2]


def test_second_event_invalid_after_a_valid_first_stores_neither(h: Harness) -> None:
    shared = {"text": "ok"}

    def body() -> None:
        with h.uow_factory(h.meta()) as uow:
            uow.record(SharedEcho(workspace_id=h.seed.workspace_id, shared={"text": "one"}))
            uow.record(SharedEcho(workspace_id=h.seed.workspace_id, shared=shared))
            shared["text"] = 5  # type: ignore[assignment]  # not even a string any more
            uow.commit()

    with pytest.raises(InternalError):
        body()
    assert h.events() == []
    assert h.backend.committed.core.outbox == {}
    assert h.backend.committed.core.feed_seq == {}


def test_committed_payload_is_the_validated_snapshot_not_a_live_reference(h: Harness) -> None:
    shared = {"workspace_id": str(h.seed.workspace_id), "text": "snapshot"}
    with h.uow_factory(h.meta()) as uow:
        uow.record(AliasedEcho(workspace_id=h.seed.workspace_id, shared=shared))
        uow.commit()
    shared["text"] = ""  # later change of the caller's object
    assert [e.payload["text"] for e in h.events()] == ["snapshot"]


def test_payload_that_is_not_json_object_fails_the_commit(h: Harness) -> None:
    shared = {"text": "ok"}

    def body() -> None:
        with h.uow_factory(h.meta()) as uow:
            uow.record(SharedEcho(workspace_id=h.seed.workspace_id, shared=shared))
            shared["extra"] = object()  # type: ignore[assignment]
            shared["text"] = float("nan")  # type: ignore[assignment]
            uow.commit()

    with pytest.raises(InternalError):
        body()
    assert h.events() == []


# ---------------------------------------------------------------- event reader returns copies (adapters §2.3)


def _read_workspace(h: Harness, uow: UnitOfWork) -> EventEnvelope:
    (envelope,) = uow.repo(EventReader).after_workspace_seq(h.seed.workspace_id, 0, types=None, limit=10)
    return envelope


def _read_global(h: Harness, uow: UnitOfWork) -> EventEnvelope:
    (envelope,) = uow.repo(EventReader).after_global_position(0, limit=10)
    return envelope


def _read_by_ids(h: Harness, uow: UnitOfWork) -> EventEnvelope:
    ids = [e.id for e in h.events()]
    (envelope,) = uow.repo(EventReader).by_ids(ids)
    return envelope


@pytest.mark.parametrize("read", [_read_workspace, _read_global, _read_by_ids])
@pytest.mark.parametrize("ending", ["commit", "rollback", "readonly"])
def test_event_reader_returns_copies_so_history_cannot_be_rewritten(
    h: Harness, read: Callable[[Harness, UnitOfWork], EventEnvelope], ending: str
) -> None:
    if read is _read_global:
        with h.uow_factory(h.meta()) as uow:
            uow.record(Noted(stream=NOTE_STREAM, text="original"))
            uow.commit()
    else:
        commit_echo(h, "original")
    stored = h.events()[0]
    snapshot = deepcopy(stored)
    with h.uow_factory(h.meta(), readonly=ending == "readonly") as uow:
        first = read(h, uow)
        first.payload["text"] = "rewritten"
        first.payload["injected"] = ["x"]
        again = read(h, uow)
        assert again.payload == snapshot.payload  # the same unit of work sees the original
        assert again is not first
        if ending == "commit":
            uow.commit()
    assert h.events() == [snapshot]
    assert h.events()[0].payload["text"] == "original"
    assert (h.events()[0].workspace_seq, h.events()[0].global_position) == (
        snapshot.workspace_seq,
        snapshot.global_position,
    )


def test_event_reader_copies_nested_payload_containers(h: Harness) -> None:
    commit_echo(h)
    core = h.backend.committed.core
    core.events[0] = replace(core.events[0], payload={"text": "t", "nested": {"list": [1, {"deep": "d"}]}})
    original = deepcopy(core.events[0].payload)
    with h.uow_factory(h.meta()) as uow:
        envelope = _read_by_ids(h, uow)
        nested = envelope.payload["nested"]
        assert isinstance(nested, dict)
        items = nested["list"]
        assert isinstance(items, list)
        inner = items[1]
        assert isinstance(inner, dict)
        inner["deep"] = "changed"
        items.append(2)
        assert _read_workspace(h, uow).payload == original
        uow.commit()
    assert core.events[0].payload == original


# ---------------------------------------------------------------- consumer receipt purge (adapters §2.3)


def _consumer_row(h: Harness, event_id: EventId, state: str) -> None:
    """Bring the ``demo.on_echoed`` outbox row of ``event_id`` into ``state``."""
    now = h.clock.now()
    with h.uow_factory(h.meta()) as uow:
        store = uow.repo(OutboxStore)
        if state != "pending":
            claimed = list(store.claim(destination="demo.on_echoed", relay_id="r1", now=now, limit=10))
            (item,) = [i for i in claimed if i.event_id == event_id]
            if state == "delivered":
                store.mark_delivered(item.id, at=now)
            else:
                assert store.mark_failed(item.id, relay_id="r1", error="x", next_at=now, dead=state == "dead")
        uow.commit()


@pytest.mark.parametrize(
    ("state", "survives"), [("pending", True), ("failed", True), ("dead", True), ("delivered", False)]
)
def test_receipt_of_an_undelivered_outbox_row_is_not_purged(h: Harness, state: str, survives: bool) -> None:
    event_id = commit_echo(h)
    with h.uow_factory(h.meta()) as uow:
        uow.repo(ConsumerReceipts).add("demo.on_echoed", event_id, h.clock.now())
        uow.commit()
    _consumer_row(h, event_id, state)
    later = h.clock.now() + timedelta(days=1)
    with h.uow_factory(h.meta()) as uow:
        receipts = uow.repo(ConsumerReceipts)
        removed = receipts.purge(before=later, limit=10)
        assert receipts.seen("demo.on_echoed", event_id) is survives
        assert removed == (0 if survives else 1)
        uow.commit()
    assert (("demo.on_echoed", event_id) in h.backend.committed.core.consumer_receipts) is survives


def test_receipt_purge_ignores_other_consumers_events_and_applies_before_and_limit(h: Harness) -> None:
    blocked = commit_echo(h, "blocked")  # its demo.on_echoed row stays pending
    other = EventId(uuid4())  # no outbox row at all
    now = h.clock.now()
    with h.uow_factory(h.meta()) as uow:
        receipts = uow.repo(ConsumerReceipts)
        receipts.add("demo.on_echoed", blocked, now - timedelta(hours=3))  # oldest, but protected
        receipts.add("demo.on_echoed", other, now - timedelta(hours=2))
        receipts.add("other-consumer", blocked, now - timedelta(hours=2))  # its pair has no outbox row
        receipts.add("demo.on_echoed", EventId(uuid4()), now)  # not older than the cutoff
        uow.commit()
    cutoff = now - timedelta(hours=1)
    with h.uow_factory(h.meta()) as uow:
        receipts = uow.repo(ConsumerReceipts)
        assert receipts.purge(before=cutoff, limit=1) == 1  # the limit counts purgeable pairs only
        assert receipts.seen("demo.on_echoed", blocked)
        assert receipts.purge(before=cutoff, limit=0) == 0
        assert receipts.purge(before=cutoff, limit=10) == 1
        assert receipts.seen("demo.on_echoed", blocked)
        assert not receipts.seen("demo.on_echoed", other)
        assert not receipts.seen("other-consumer", blocked)
        assert receipts.purge(before=cutoff, limit=10) == 0
        uow.commit()
    assert len(h.backend.committed.core.consumer_receipts) == 2


# ---------------------------------------------------------------- dead-notification claims (adapters §1.4)


def test_mark_failed_leaves_a_dead_notification_claim_unchanged(h: Harness) -> None:
    event_id = commit_echo(h)
    now = h.clock.now()
    with h.uow_factory(h.meta()) as uow:
        uow.outbox.enqueue(event_id, "hook:sub1")
        uow.commit()
    with h.uow_factory(h.meta()) as uow:
        store = uow.repo(OutboxStore)
        (item,) = store.claim(destination="hook:sub1", relay_id="r0", now=now, limit=1)
        assert store.mark_failed(item.id, relay_id="r0", error="boom", next_at=now, dead=True)
        (notice,) = store.claim_dead_notifications(
            prefixes=frozenset({"hook"}), relay_id="r1", now=now, limit=5
        )
        assert notice.id == item.id
        row = store._row(item.id)  # type: ignore[attr-defined]  # the working-copy row, not a read model
        before = deepcopy(row)
        assert before.state is OutboxState.DEAD
        assert before.claimed_by == "r1"
        for dead in (False, True):
            assert not store.mark_failed(item.id, relay_id="r1", error="x", next_at=now, dead=dead)
            assert row == before  # no field changed: state, claim, error, available_at
        assert store.mark_dead_notified(
            item.id,
            relay_id="r1",
            generation=notice.delivery_generation,
            claimed_at=notice.claimed_at,
            at=now,
        )
        assert row.dead_notified_at == now
        assert row.state is OutboxState.DEAD


def test_mark_failed_still_handles_pending_failed_and_stale_claims(h: Harness) -> None:
    commit_echo(h)
    now = h.clock.now()
    later = now + timedelta(minutes=1)
    with h.uow_factory(h.meta()) as uow:
        store = uow.repo(OutboxStore)
        (item,) = store.claim(destination="sse", relay_id="r1", now=now, limit=1)
        assert not store.mark_failed(item.id, relay_id="r2", error="x", next_at=later, dead=False)  # stale
        assert store.mark_failed(
            item.id, relay_id="r1", error="x", next_at=later, dead=False
        )  # pending→failed
        (again,) = store.claim(destination="sse", relay_id="r1", now=later, limit=1)
        assert again.attempts == 2
        assert store.mark_failed(again.id, relay_id="r1", error="y", next_at=later, dead=True)  # failed→dead
        assert not store.mark_failed(
            again.id, relay_id="r1", error="z", next_at=later, dead=False
        )  # unclaimed
        uow.commit()
    assert [r.state for r in h.backend.committed.core.outbox.values() if r.destination == "sse"] == [
        OutboxState.DEAD
    ]


# ---------------------------------------------------------------- production has no demo


def test_production_code_does_not_reference_the_demo_module() -> None:
    from skm.bootstrap.modules import MODULE_CATALOG

    assert "demo" not in {entry.id for entry in MODULE_CATALOG}
    root = Path(skm.__file__).parent
    assert not (root / "modules" / "demo").exists()
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if any(
            marker in path.read_text(encoding="utf-8")
            for marker in ("demo_module", "fakes.app", "fakes.authorizer")
        )
    ]
    assert offenders == []
