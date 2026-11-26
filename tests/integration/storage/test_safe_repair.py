"""Safe repair expiry, durable requeue, and the immutable evidence boundary."""

import io
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest

from integration.artifacts.test_janitor import (
    WORKER_ID,
    Harness,
    _add_file_dto,
    _audit_actions,
    _dispatch,
    _make_harness,
    _object_loc,
)
from integration.storage.test_verify import storage_side as storage_side
from integration.storage.test_verify import verify
from skm.application_bus.ports import IdempotencyStore, OutboxStore
from skm.bootstrap.composition_resources import LazyBlobStore
from skm.bootstrap.platform_module import _RepairOwnerCommands
from skm.entrypoints.cli.main import main
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.errors import Conflict, Forbidden, InternalError, ValidationFailed
from skm.kernel.ids import FileVersionId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.artifacts.domain.staged_blob import StagedBlob
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.generated.commands import RepairStorageSafe
from skm.platform.generated.queries import VerifyStorage
from skm.platform.generated.results import RepairStorageSafeResult
from support.pg import TestDatabase
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database


def test_repair_owner_actions_and_idempotency(storage_side: Harness) -> None:
    h = storage_side
    retained = b"accepted file bytes\n"
    expired = b"expired staging only\n"
    staged = h.client.upload_blob(h.ws, [retained], size=len(retained), media_type="text/plain")
    version = _dispatch(h.client, _add_file_dto(h.ws, h.proj, staged)).file_version_id
    duplicate = h.client.upload_blob(h.ws, [retained], size=len(retained), media_type="text/plain")
    stale = h.client.upload_blob(h.ws, [expired], size=len(expired), media_type="text/plain")
    h.clock.advance(timedelta(hours=25))
    now = h.clock.now()
    delivery = _mark_dead(h)

    query = VerifyStorage(levels=("files", "recovery"))
    before = verify(h, query)
    assert {item.target.id for item in before.findings} == {str(stale.staged_blob_id), str(delivery)}
    assert all(item.target.id != str(duplicate.staged_blob_id) for item in before.findings)

    def repair(*, key: str, dry_run: bool = False) -> RepairStorageSafeResult:
        result = h.client.dispatch(RepairStorageSafe(dry_run=dry_run), idempotency_key=key)
        assert isinstance(result, RepairStorageSafeResult)
        return result

    audit_before = _audit_actions(h)
    dry_run = repair(key="dry-run", dry_run=True)
    assert dry_run.repaired == ()
    assert {row.reason for row in dry_run.skipped} == {"dry_run"}
    assert verify(h, query) == before
    assert h.store.exists(_object_loc(h.ws, expired))
    assert _audit_actions(h) == audit_before
    with h.app.uow_factory(RequestMeta("storage-preview", Surface.TEST, None, now), readonly=True) as uow:
        assert (
            uow.repo(IdempotencyStore).get(
                None,
                h.owner.principal_id,
                "platform.repair_storage_safe",
                "dry-run",
            )
            is None
        )

    result = repair(key="safe-repair")
    assert {row.code: row.action for row in result.repaired} == {
        "STAGED_EXPIRED": "artifacts.expire_staged_blobs",
        "OUTBOX_DEAD": "platform.retry_outbox",
    }
    assert repair(key="safe-repair") == result
    assert verify(h, query).findings == ()
    assert not h.store.exists(_object_loc(h.ws, expired))
    with h.client.open_file_version_content(FileVersionId(version)) as stream:
        assert stream.read() == retained


def test_repair_scope_and_cli_safety(storage_side: Harness) -> None:
    h = storage_side
    worker = h.app.client(actor=Actor(WORKER_ID, PrincipalKind.WORKER, "worker"), surface=Surface.CLI)
    with pytest.raises(Forbidden):
        worker.ask(VerifyStorage())
    with pytest.raises(Forbidden):
        worker.dispatch(RepairStorageSafe(), idempotency_key="forbidden")
    with pytest.raises(ValidationFailed):
        h.client.dispatch(RepairStorageSafe())
    with pytest.raises(ValidationFailed):
        h.client.dispatch(RepairStorageSafe(codes=("NEW_CODE",)), idempotency_key="unknown")
    assert main(["storage", "repair"], environ={}, stdout=io.StringIO(), stderr=io.StringIO()) == 2


@pytest.mark.pg
@pytest.mark.parametrize("dry_run", [False, True], ids=["verify", "dry-run"])
def test_cold_storage_inspection_creates_no_files(
    clean_test_database: TestDatabase, tmp_path: Path, dry_run: bool
) -> None:
    env = {"SKM_DATABASE_URL": clean_test_database.dsn}
    config = load_bootstrap(None, env, tmp_path)
    for h in _make_harness("postgres", tmp_path, clean_test_database.dsn, max_uow=2):
        assert isinstance(h.store, LazyBlobStore)
        assert h.store._store is None
        assert not config.blobs_root.exists()
        assert not (config.state_dir / "locks").exists()
        before = tuple(sorted(tmp_path.rglob("*")))
        if dry_run:
            assert h.client.dispatch(
                RepairStorageSafe(dry_run=True), idempotency_key="cold-preview"
            ) == RepairStorageSafeResult(repaired=(), skipped=())
        else:
            assert verify(h).findings == ()
        assert tuple(sorted(tmp_path.rglob("*"))) == before
        assert h.store._store is None


def _mark_dead(h: Harness, delivery_id: UUID | None = None) -> UUID:
    now = h.clock.now()
    with h.app.uow_factory(RequestMeta("storage-dead", Surface.TEST, None, now)) as uow:
        outbox = uow.repo(OutboxStore)
        rows = outbox.claim(destination="sse", relay_id="storage-test", now=now, limit=100)
        delivery = next(row for row in rows if delivery_id is None or row.id == delivery_id)
        assert outbox.mark_failed(
            delivery.id, relay_id="storage-test", error="failed", next_at=now, dead=True
        )
        uow.commit()
        return delivery.id


def test_owner_transactions_survive_parent_failure_and_replay(
    storage_side: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = storage_side
    data = b"staging metadata commits in its owner transaction"
    stale = h.client.upload_blob(h.ws, [data], size=len(data), media_type="text/plain")
    h.clock.advance(timedelta(hours=25))
    delivery = _mark_dead(h)
    query = VerifyStorage(levels=("files", "recovery"))
    assert {row.target.id for row in verify(h, query).findings} == {str(stale.staged_blob_id), str(delivery)}
    cmd = RepairStorageSafe(codes=("STAGED_EXPIRED", "OUTBOX_DEAD"))

    def fail_result(*_args: object) -> None:
        raise RuntimeError("simulated failure before committing the result")

    with monkeypatch.context() as patch:
        patch.setattr(h.app.bus, "_valid_result", fail_result)
        with pytest.raises(InternalError):
            h.client.dispatch(cmd, idempotency_key="abort")

    assert verify(h, query).findings == ()
    assert not h.store.exists(_object_loc(h.ws, data))
    with pytest.raises(Conflict):
        h.client.dispatch(RepairStorageSafe(codes=("OUTBOX_DEAD",)), idempotency_key="abort")
    with pytest.raises(Conflict):
        h.client.dispatch(RepairStorageSafe(dry_run=True), idempotency_key="abort")

    _mark_dead(h, delivery)
    replayed = h.client.dispatch(cmd, idempotency_key="abort")
    assert isinstance(replayed, RepairStorageSafeResult)
    assert {row.target.id for row in replayed.repaired} == {str(stale.staged_blob_id), str(delivery)}
    assert h.client.dispatch(cmd, idempotency_key="abort") == replayed
    assert [row.target.id for row in verify(h, query).findings] == [str(delivery)]


def test_later_owner_failure_keeps_earlier_commit(
    storage_side: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = storage_side
    data = b"expired before a later outbox failure"
    expired = h.client.upload_blob(h.ws, [data], size=len(data), media_type="text/plain")
    h.clock.advance(timedelta(hours=25))
    delivery = _mark_dead(h)

    def fail_outbox(*_args: object) -> bool:
        raise RuntimeError("outbox action failed")

    command = RepairStorageSafe(codes=("STAGED_EXPIRED", "OUTBOX_DEAD"))
    with monkeypatch.context() as patch:
        patch.setattr(_RepairOwnerCommands, "retry_outbox", fail_outbox)
        with pytest.raises(InternalError):
            h.client.dispatch(command, idempotency_key="later-failure")

    assert not h.store.exists(_object_loc(h.ws, data))
    query = VerifyStorage(levels=("files", "recovery"))
    assert [row.target.id for row in verify(h, query).findings] == [str(delivery)]
    result = h.client.dispatch(command, idempotency_key="later-failure")
    assert isinstance(result, RepairStorageSafeResult)
    assert {row.target.id for row in result.repaired} == {str(expired.staged_blob_id), str(delivery)}
    assert verify(h, query).findings == ()


def test_repair_rechecks_new_references_before_deleting_bytes(
    storage_side: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = storage_side
    data = b"the same object becomes referenced before cleanup"
    stale = h.client.upload_blob(h.ws, [data], size=len(data), media_type="text/plain")
    h.clock.advance(timedelta(hours=25))
    cleanup = _RepairOwnerCommands._delete_unreferenced
    versions: list[FileVersionId] = []

    def reference_then_cleanup(owner: _RepairOwnerCommands, rows: tuple[StagedBlob, ...]) -> None:
        staged = h.client.upload_blob(h.ws, [data], size=len(data), media_type="text/plain")
        added = _dispatch(h.client, _add_file_dto(h.ws, h.proj, staged))
        versions.append(FileVersionId(added.file_version_id))
        cleanup(owner, rows)

    monkeypatch.setattr(_RepairOwnerCommands, "_delete_unreferenced", reference_then_cleanup)
    result = h.client.dispatch(RepairStorageSafe(codes=("STAGED_EXPIRED",)), idempotency_key="new-ref")
    assert isinstance(result, RepairStorageSafeResult)
    assert [row.target.id for row in result.repaired] == [str(stale.staged_blob_id)]
    [version] = versions
    with h.client.open_file_version_content(version) as stream:
        assert stream.read() == data
