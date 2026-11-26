"""Real relay and ledger contracts shared by the memory and PostgreSQL backends."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from contracts.knowledge.harness import KnowledgeSide, knowledge_side
from integration.artifacts.test_upload_flow import dispatch_new
from skm.application_bus.ports import ConsumerReceipts, EventReader, OutboxState, OutboxStore
from skm.application_bus.subscribers import DeliveryOutcome, DeliverySettings, deliver
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import EventId, HostId
from skm.kernel.ports_uow import Surface, UnitOfWork
from skm.modules.exports.domain.note import NoteKind, VaultNote, VaultNoteId, VaultNoteState, VaultNoteWrite
from skm.modules.exports.domain.plan_markdown import PlanExportView
from skm.modules.exports.ports import VaultNoteRepository
from skm.modules.exports.public import RequeueNote, RequeueNoteResult
from skm.modules.planning.public import ArchivePlan, CreatePlan, PlanView
from skm.modules.workspace.public import AttachRepository, BindCheckout, RegisterHost, RegisterRepository
from skm.platform.logging.logger import get_logger
from skm.platform.system_ids import Uuid7Generator
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "knowledge_side", "pg_session", "test_database"]

_CONSUMER = "exports.plan_archived_note"
_REMOTE = "https://github.com/example/exports-fixture"


def archive_and_queue(side: KnowledgeSide) -> VaultNote:
    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    plan_id = dispatch_new(client, CreatePlan(side.project, "A plan before publication")).plan_id
    note = materialize_archive(side, plan_id)
    assert "revision:" not in note.body
    return note


def deliver_note(side: KnowledgeSide, destination: str = _CONSUMER) -> tuple[DeliveryOutcome, EventId]:
    with side.uow() as uow:
        (item,) = uow.repo(OutboxStore).claim(
            destination=destination, relay_id="exports-test", now=side.clock.now(), limit=1
        )
        uow.commit()
    outcome = deliver(
        item,
        registry=side.app.bus._registry,
        uow_factory=side.app.uow_factory,
        config=side.app.config,
        delivery=DeliverySettings(),
        clock=side.clock,
        ids=Uuid7Generator(side.clock),
        gateways=side.app.gateways,
        log=get_logger("tests.exports"),
        relay_id="exports-test",
    )
    return outcome, item.event_id


def materialize_archive(side: KnowledgeSide, plan_id: UUID) -> VaultNote:
    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    dispatch_new(client, ArchivePlan(plan_id))
    side.clock.advance(timedelta(seconds=1))
    outcome, event_id = deliver_note(side)
    assert outcome == DeliveryOutcome.DELIVERED
    with side.uow(readonly=True) as uow:
        assert uow.repo(ConsumerReceipts).seen(_CONSUMER, event_id)
        note = uow.repo(VaultNoteRepository).by_event(event_id, NoteKind.PLAN_ARCHIVED)
        assert note is not None
        assert note.source_id == plan_id
        assert "classification: restricted" in note.body
        (queued,) = uow.repo(EventReader).after_workspace_seq(
            side.workspace,
            0,
            types=frozenset({"urn:skm:exports:event:vault-note-queued:v1"}),
            limit=20,
        )
        assert "body" not in queued.payload
        assert queued.stream_id == note.id
    return note


def bound_host(side: KnowledgeSide) -> HostId:
    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    host = HostId(
        dispatch_new(
            client,
            RegisterHost.from_json(
                {"name": "vault-host", "platform": {"os": "linux", "arch": "x86_64"}},
            ),
        ).host_id
    )
    repo_id = dispatch_new(
        client, RegisterRepository(side.workspace, "Projection source", _REMOTE, None)
    ).repository_id
    dispatch_new(client, AttachRepository(side.project, repo_id))
    dispatch_new(
        client,
        BindCheckout(
            repo_id,
            host,
            "/opt/test-checkout",
            "/opt/test-checkout",
            ("github.com/example/exports-fixture",),
            None,
            False,
            side.clock.now(),
        ),
    )
    return host


def test_subscriber_replay_preserves_bytes_and_does_not_render_again(
    knowledge_side: KnowledgeSide,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from skm.modules.exports.application import subscribers

    note = archive_and_queue(knowledge_side)

    def invalid_render(*_args: object, **_kwargs: object) -> None:
        pytest.fail("a duplicate event must be detected before rendering")

    monkeypatch.setattr(subscribers, "build_plan_view", invalid_render)
    with knowledge_side.uow() as uow:
        (event,) = uow.repo(EventReader).by_ids((note.event_id,))
        subscribers.plan_archived_note(event, None, uow)  # type: ignore[arg-type] -- no context read on replay
        repo = uow.repo(VaultNoteRepository)
        assert not repo.add(replace(note, id=VaultNoteId(uuid4()), body="changed candidate"))
        assert repo.by_event(note.event_id, note.kind) == note
        uow.commit()


@pytest.mark.parametrize("knowledge_side", [pytest.param("postgres", marks=pytest.mark.pg)], indirect=True)
def test_subscriber_reads_metadata_from_one_snapshot(
    knowledge_side: KnowledgeSide, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skm.modules.exports.application import subscribers
    from skm.modules.workspace.ports import ProjectRepository

    side = knowledge_side
    original = subscribers.build_plan_view
    observed: list[str] = []

    def rename() -> None:
        with side.uow() as writer:
            projects = writer.repo(ProjectRepository)
            project = projects.get(side.project)
            renamed = replace(project, title="Renamed concurrently", row_version=project.row_version + 1)
            projects.save(renamed, expected_version=project.row_version)
            writer.commit()

    def rename_after_plan_read(uow: UnitOfWork, plan: PlanView) -> PlanExportView:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(rename).result(timeout=5)
        view = original(uow, plan)
        observed.append(view.project)
        return view

    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    plan_id = dispatch_new(client, CreatePlan(side.project, "Plan with concurrent project metadata")).plan_id
    dispatch_new(client, ArchivePlan(plan_id))
    with monkeypatch.context() as patch:
        patch.setattr(subscribers, "build_plan_view", rename_after_plan_read)
        outcome, event_id = deliver_note(side)
    assert observed == ["Initial"]
    # The foreign-key check encounters the update and PostgreSQL rolls back the old snapshot.
    assert outcome == DeliveryOutcome.FAILED
    with side.uow(readonly=True) as uow:
        assert uow.repo(VaultNoteRepository).by_event(event_id, NoteKind.PLAN_ARCHIVED) is None
        assert not uow.repo(ConsumerReceipts).seen(_CONSUMER, event_id)
        retry = uow.repo(OutboxStore).list(
            destination_prefix=_CONSUMER,
            state=OutboxState.PENDING,
            workspace_id=side.workspace,
            after=None,
            limit=1,
        )
        assert retry.items[0].last_error == "Conflict: SERIALIZATION_FAILURE"
    side.clock.advance(timedelta(seconds=5))
    assert deliver_note(side) == (DeliveryOutcome.DELIVERED, event_id)
    with side.uow(readonly=True) as uow:
        note = uow.repo(VaultNoteRepository).by_event(event_id, NoteKind.PLAN_ARCHIVED)
        assert note is not None
        assert "Renamed concurrently" in note.body
        assert uow.repo(ConsumerReceipts).seen(_CONSUMER, event_id)


def test_receipt_expiry_requeue_and_retention_are_serialized(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    host = bound_host(side)
    note = archive_and_queue(side)
    vault_id = uuid4()
    write = VaultNoteWrite(
        note.id,
        vault_id,
        1,
        host,
        "Plans/note.md",
        "modified_existing",
        note.body_digest,
        "sha256:" + "0" * 64,
        side.clock.now(),
    )
    with side.uow() as uow:
        repo = uow.repo(VaultNoteRepository)
        assert repo.active_checkout(side.workspace, host, side.project)
        assert (
            len(
                repo.pending_for_host(
                    side.workspace,
                    host,
                    vault_id,
                    now=side.clock.now(),
                    ttl_days=30,
                    after=None,
                    scan_limit=500,
                ).items
            )
            == 1
        )
        assert repo.add_write(write, now=side.clock.now(), ttl_days=30)
        assert not repo.add_write(write, now=side.clock.now(), ttl_days=30)
        assert not repo.pending_for_host(
            side.workspace,
            host,
            vault_id,
            now=side.clock.now(),
            ttl_days=30,
            after=None,
            scan_limit=500,
        ).items
        uow.commit()
    side.clock.advance(timedelta(days=30))
    with side.uow() as uow:
        repo = uow.repo(VaultNoteRepository)
        with pytest.raises(SkmError) as err:
            repo.add_write(replace(write, vault_id=uuid4()), now=side.clock.now(), ttl_days=30)
        assert err.value.code == ErrorCode.INVALID_TRANSITION
        assert repo.expire_due(side.clock.now(), 30, limit=500) == 1
        assert repo.get(note.id).state == VaultNoteState.EXPIRED
        uow.commit()
    cmd = RequeueNote(side.project, note.id, 1)
    for _ in range(2):
        outcome = side.app.bus.dispatch(cmd, actor=side.owner, meta=side.meta("one-requeue"))
        assert outcome == RequeueNoteResult(2)
    with side.uow() as uow:
        repo = uow.repo(VaultNoteRepository)
        with pytest.raises(SkmError) as err:
            repo.add_write(write, now=side.clock.now(), ttl_days=30)
        assert err.value.code == ErrorCode.VERSION_CONFLICT
        assert repo.writes(note.id) == (write,)
        assert repo.delete_older_than(note.created_at + timedelta(days=1), limit=500) == 0
        assert repo.delete_older_than(side.clock.now(), limit=500) == 1
        assert repo.writes(note.id) == ()
        uow.commit()


def test_invalid_settings_candidate_is_rejected_before_commit(knowledge_side: KnowledgeSide) -> None:
    from skm.modules.settings.public import GetGeneration, SetValue

    side = knowledge_side
    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    prior = client.ask(GetGeneration())
    with pytest.raises(SkmError) as refused:
        dispatch_new(
            client,
            SetValue.from_json(
                {
                    "scope": {"level": "instance"},
                    "key": "exports.notes.pending_ttl_days",
                    "value": 365,
                }
            ),
        )
    assert refused.value.code == ErrorCode.SCHEMA_INVALID
    assert refused.value.details["validator"] == "exports.notes_ttl_order"
    assert client.ask(GetGeneration()) == prior
