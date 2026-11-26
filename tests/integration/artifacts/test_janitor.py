"""Integration tests for janitor staged expiry, orphan detection, and manual prune (artifacts §6-§8, G22)."""

import hashlib
import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from fakes.clock import FrozenClock
from skm.application_bus.client import SkmClient, StagedBlobRef
from skm.application_bus.ports import AuditLog
from skm.background.janitor import ExpireStagedBlobsTask, JanitorService
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, PreconditionFailed
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import FileVersionId, PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.domain.access_grant import GrantReason
from skm.modules.artifacts.domain.file_version import VersionSource
from skm.modules.artifacts.domain.staged_blob import StagedBlobId
from skm.modules.artifacts.generated import commands as wire
from skm.modules.artifacts.generated.commands import ExpireStagedBlobs, PruneOrphanObjects
from skm.modules.artifacts.generated.queries import FindOrphanBlobs
from skm.modules.artifacts.generated.results import ExpireStagedBlobsResult, PruneOrphanObjectsResult
from skm.modules.artifacts.generated.views import FindOrphanBlobsView
from skm.modules.artifacts.ports import BlobLocationRef, BlobStore, StagedBlobRepository
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.fs import storage_budget
from skm.platform.jsonc.digest import digest as canonical_digest
from skm.platform.logging.logger import get_logger
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator
from support.pg import TestDatabase, clean_test_database, pg_session, test_database
from support.seed import SEED

__all__ = ["clean_test_database", "pg_session", "test_database"]

NOW = SystemClock().now()
OWNER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d7"))
WORKER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d8"))
SERVICE_ACTOR = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")


@dataclass
class Harness:
    app: App
    clock: FrozenClock
    ids: IdGenerator
    owner: Actor
    client: SkmClient
    ws: WorkspaceId
    proj: ProjectId
    store: BlobStore
    dsn: str | None


def _dispatch(client: SkmClient, cmd: object) -> Any:
    return client.dispatch(cmd, idempotency_key=client.new_idempotency_key())


def _dispatch_expire(h: Harness, *, limit: int = 100) -> ExpireStagedBlobsResult:
    token = (
        h.ids.new_id()
        .hex[:26]
        .upper()
        .replace("0", "A")
        .replace("1", "B")
        .replace("8", "C")
        .replace("9", "D")
    )
    meta = RequestMeta(
        request_id="req_" + token,
        surface=Surface.BACKGROUND,
        idempotency_key=None,
        received_at=h.clock.now(),
    )
    res = h.app.bus.dispatch(ExpireStagedBlobs(limit=limit), actor=SERVICE_ACTOR, meta=meta)
    assert isinstance(res, ExpireStagedBlobsResult)
    return res


def _add_file_dto(
    ws: WorkspaceId, proj: ProjectId, ref: StagedBlobRef, title: str = "Doc"
) -> artifacts.AddFile:
    return artifacts.AddFile(
        workspace_id=ws,
        project_id=proj,
        title=title,
        origin=wire.FileOrigin.UPLOAD,
        blob=wire.AddFileDefsStagedBlobRef(
            staged_blob_id=ref.staged_blob_id,
            workspace_id=ref.workspace_id,
            digest=ref.digest,
            size=ref.size,
            media_type=ref.media_type,
        ),
        original_filename="doc.txt",
        source=wire.AddFileDefsVersionSource(kind="upload"),
    )


def _object_loc(ws: WorkspaceId, data: bytes, backend_id: str = "local-primary") -> BlobLocationRef:
    hex_digest = hashlib.sha256(data).hexdigest()
    return {
        "backend_id": backend_id,
        "storage_key": f"{ws}/objects/{hex_digest[:2]}/{hex_digest}",
        "storage_version": None,
    }


def _audit_actions(h: Harness) -> list[tuple[str, str]]:
    if h.dsn is not None:
        with psycopg.connect(h.dsn, autocommit=True, connect_timeout=5) as conn:
            rows = conn.execute("SELECT action, decision FROM skm_core.audit_records").fetchall()
            return [(str(r[0]), str(r[1])) for r in rows]
    with h.app.uow_factory(
        RequestMeta("req_" + "a" * 26, Surface.CLI, None, h.clock.now()), readonly=True
    ) as uow:
        mem_log: Any = uow.repo(AuditLog)
        out = [(r.action, r.decision) for r in mem_log._core.audit]
        uow.rollback()
        return out


def _make_harness(
    backend: str,
    tmp_path: Path,
    dsn: str | None = None,
    *,
    max_uow: int = 6,
    start_at: datetime | None = None,
) -> Iterator[Harness]:
    t0 = NOW if start_at is None else start_at
    clock = FrozenClock(t0)
    ids = Uuid7Generator(clock)
    env = {"SKM_DATABASE_URL": dsn} if dsn else {}
    bs_env = {"SKM_DATABASE_URL": dsn or "postgresql://127.0.0.1:5432/mem"}
    bs = replace(
        load_bootstrap(None, bs_env, tmp_path),
        instance_id=SEED.instance_id,
        database_application_name="skm-janitor-int",
        database_pool_min_size=0,
        database_pool_max_size=max_uow,
        database_pool_timeout_seconds=5,
    )
    ov = CompositionOverrides(
        authorizer=RbacAuthorizer(clock),
        scopes=StoredScopeChain(),
        clock=clock,
        ids=ids,
        instance_id=SEED.instance_id,
    )
    be = "postgres" if backend == "postgres" else None
    app = build_app(bs, surface=Surface.CLI, environ=env, invocation={}, backend=be, overrides=ov)
    try:
        with app.uow_factory(RequestMeta("req_" + "1" * 26, Surface.CLI, None, t0)) as uow:
            if backend == "memory":
                uow.repo(ScopeRegistry).create(
                    SEED.instance_id, ScopeKind.INSTANCE, parent=None, workspace_id=None
                )
            for pid, kind, name in (
                (SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system"),
                (OWNER_ID, PrincipalKind.HUMAN, "owner"),
                (WORKER_ID, PrincipalKind.WORKER, "worker-1"),
            ):
                uow.repo(PrincipalRepository).add(
                    new_principal(principal_id=pid, kind=kind, display_name=name, created_by=None, now=t0)
                )
            uow.repo(MembershipRepository).upsert(
                Membership(SEED.instance_id, SYSTEM_PRINCIPAL_ID, Role.OWNER, None, t0)
            )
            uow.repo(MembershipRepository).upsert(
                Membership(SEED.instance_id, OWNER_ID, Role.OWNER, None, t0)
            )
            uow.commit()
        owner = Actor(OWNER_ID, PrincipalKind.HUMAN, "owner")
        client = app.client(actor=owner, surface=Surface.CLI)
        ws = WorkspaceId(_dispatch(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        proj = ProjectId(
            _dispatch(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        with app.uow_factory(RequestMeta("req_" + "2" * 26, Surface.CLI, None, t0)) as uow:
            uow.repo(MembershipRepository).upsert(
                Membership(ScopeId(ws), WORKER_ID, Role.WORKER, OWNER_ID, t0)
            )
            uow.commit()
        store = app.gateways.get(BlobStore)
        yield Harness(app, clock, ids, owner, client, ws, proj, store, dsn)
    finally:
        app.close()


@pytest.fixture
def mem_harness(tmp_path: Path) -> Iterator[Harness]:
    yield from _make_harness("memory", tmp_path)


@pytest.fixture
def pg_harness(clean_test_database: TestDatabase, tmp_path: Path) -> Iterator[Harness]:
    yield from _make_harness("postgres", tmp_path, clean_test_database.dsn)


def _stamp_staging_handle(h: Harness, staging_id: str) -> None:
    """Advance a ``LocalBlobStore`` staging file mtime to ``FrozenClock.now()`` when clock moved ahead."""
    own: Path | None = getattr(h.store, "_own", None)
    if own is not None:
        part = own / f"{staging_id}.part"
        if part.is_file():
            ts = h.clock.now().timestamp()
            os.utime(part, (ts, ts))


def _check_expires_unconsumed(h: Harness) -> None:
    stale_data = b"expired-unconsumed-payload\n"
    fresh_data = b"fresh-unconsumed-payload\n"
    stale_ref = h.client.upload_blob(h.ws, [stale_data], size=len(stale_data), media_type="text/plain")
    stale_stage = h.store.stage(h.ws, [b"abandoned-upload-1"])

    h.clock.advance(timedelta(hours=25))
    fresh_ref = h.client.upload_blob(h.ws, [fresh_data], size=len(fresh_data), media_type="text/plain")
    fresh_stage = h.store.stage(h.ws, [b"in-flight-upload-2"])
    _stamp_staging_handle(h, fresh_stage.staging_id)

    with pytest.raises(Forbidden) as denied:
        _dispatch(h.client, ExpireStagedBlobs(limit=10))
    assert denied.value.code is ErrorCode.FORBIDDEN

    task = ExpireStagedBlobsTask(
        h.app.bus,
        lambda limit: ExpireStagedBlobs(limit=limit),
        h.ids,
        h.clock,
        batch_size=10,
    )
    tick = JanitorService((task,), log=get_logger("test.janitor")).tick()
    assert tick.processed == 1
    assert not h.store.exists(_object_loc(h.ws, stale_data))
    assert h.store.exists(_object_loc(h.ws, fresh_data))

    with pytest.raises(NotFound):
        _dispatch(h.client, _add_file_dto(h.ws, h.proj, stale_ref))

    added = _dispatch(h.client, _add_file_dto(h.ws, h.proj, fresh_ref))
    with h.client.open_file_version_content(FileVersionId(added.file_version_id)) as stream:
        assert stream.read() == fresh_data

    with pytest.raises(NotFound):
        h.store.promote(stale_stage)
    promoted_fresh = h.store.promote(fresh_stage)
    assert h.store.exists(promoted_fresh)


def test_janitor_expires_unconsumed_staged_blobs(mem_harness: Harness) -> None:
    _check_expires_unconsumed(mem_harness)


@pytest.mark.pg
def test_pg_janitor_expires_unconsumed_staged_blobs(pg_harness: Harness) -> None:
    _check_expires_unconsumed(pg_harness)


def _check_preserves_consumed(h: Harness) -> None:
    payload = b"consumed-shared-payload\n"
    ref_consumed = h.client.upload_blob(h.ws, [payload], size=len(payload), media_type="text/plain")
    created = _dispatch(h.client, _add_file_dto(h.ws, h.proj, ref_consumed))
    ver_id = FileVersionId(created.file_version_id)

    h.client.upload_blob(h.ws, [payload], size=len(payload), media_type="text/plain")
    h.clock.advance(timedelta(hours=25))

    res_25h = _dispatch_expire(h)
    assert res_25h.expired == 1
    assert res_25h.objects_deleted == 0
    assert h.store.exists(_object_loc(h.ws, payload))

    h.clock.advance(timedelta(days=8))
    res_8d = _dispatch_expire(h)
    assert res_8d.expired == 0
    assert res_8d.objects_deleted == 0
    with h.app.uow_factory(RequestMeta("req_" + "c" * 26, Surface.CLI, None, h.clock.now())) as uow:
        with pytest.raises(NotFound):
            uow.repo(StagedBlobRepository).get_for_update(StagedBlobId(ref_consumed.staged_blob_id))
        uow.rollback()

    with h.client.open_file_version_content(ver_id) as stream:
        assert stream.read() == payload


def test_janitor_preserves_consumed_staged_blobs(mem_harness: Harness) -> None:
    _check_preserves_consumed(mem_harness)


@pytest.mark.pg
def test_pg_janitor_preserves_consumed_staged_blobs(pg_harness: Harness) -> None:
    _check_preserves_consumed(pg_harness)


def test_concurrent_upload_consume_safe(mem_harness: Harness) -> None:
    h = mem_harness
    shared = b"shared-digest-across-cycles\n"
    expired_ref = h.client.upload_blob(h.ws, [shared], size=len(shared), media_type="text/plain")
    assert expired_ref.size == len(shared)
    h.clock.advance(timedelta(hours=25))

    re_uploaded = h.client.upload_blob(h.ws, [shared], size=len(shared), media_type="text/plain")
    res = _dispatch_expire(h)
    assert res.expired == 1
    assert res.objects_deleted == 0
    added = _dispatch(h.client, _add_file_dto(h.ws, h.proj, re_uploaded))
    with h.client.open_file_version_content(FileVersionId(added.file_version_id)) as stream:
        assert stream.read() == shared


@contextmanager
def _open_harness(
    backend: str,
    tmp_path: Path,
    dsn: str | None = None,
    *,
    max_uow: int = 6,
    start_at: datetime | None = None,
) -> Iterator[Harness]:
    yield from _make_harness(backend, tmp_path, dsn, max_uow=max_uow, start_at=start_at)


@pytest.mark.pg
def test_pg_concurrent_upload_consume_safe(
    clean_test_database: TestDatabase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exercise the real ledger and digest locks under a parallel PG run even when durable ledger
    # writes take longer than the admission deadline. The storage budget tests cover that deadline.
    monkeypatch.setattr(storage_budget, "_LOCK_TIMEOUT_SECONDS", 10.0)
    # Start simulated clock 26h behind wall-clock so advancing +25h lands at wall-clock - 1h;
    # that way concurrent LocalBlobStore.stage() files (stamped by the OS at wall-clock) are never
    # falsely older than stale_before = clock.now() - 24h.
    with _open_harness(
        "postgres",
        tmp_path,
        clean_test_database.dsn,
        max_uow=8,
        start_at=SystemClock().now() - timedelta(hours=26),
    ) as h:
        shared = b"pg-concurrent-shared-bytes\n"
        for _ in range(3):
            h.client.upload_blob(h.ws, [shared], size=len(shared), media_type="text/plain")
        for idx in range(4):
            raw = f"pg-expired-only-{idx}\n".encode()
            h.client.upload_blob(h.ws, [raw], size=len(raw), media_type="text/plain")
        h.clock.advance(timedelta(hours=25))

        def upload_and_consume(idx: int) -> tuple[FileVersionId, bytes]:
            client = h.app.client(actor=h.owner, surface=Surface.CLI)
            body = shared if idx % 2 == 0 else f"pg-live-worker-{idx}\n".encode()
            ref = client.upload_blob(h.ws, [body], size=len(body), media_type="text/plain")
            out = _dispatch(client, _add_file_dto(h.ws, h.proj, ref, title=f"Doc-{idx}"))
            return FileVersionId(out.file_version_id), body

        def janitor_sweep() -> int:
            total = 0
            for _ in range(3):
                total += _dispatch_expire(h, limit=2).expired
            return total

        with ThreadPoolExecutor(max_workers=5) as pool:
            janitor_fut = pool.submit(janitor_sweep)
            upload_futs = [pool.submit(upload_and_consume, i) for i in range(6)]
            assert janitor_fut.result() >= 4
            created = [fut.result() for fut in upload_futs]

        for ver_id, expected in created:
            with h.client.open_file_version_content(ver_id) as stream:
                assert stream.read() == expected
        report = h.client.ask(FindOrphanBlobs(workspace_id=h.ws))
        assert isinstance(report, FindOrphanBlobsView)
        assert report.missing_objects == ()


def _promote_orphan(h: Harness, data: bytes) -> BlobLocationRef:
    handle = h.store.stage(h.ws, [data])
    loc = h.store.promote(handle)
    root: Path | None = getattr(h.store, "_root", None)
    if root is not None:
        path = root / str(loc["storage_key"])
        ts = h.clock.now().timestamp()
        os.utime(path, (ts, ts))
    return loc


def _check_orphan_report_and_stale_guard(h: Harness) -> None:
    orphan_loc = _promote_orphan(h, b"old-orphan-bytes\n")
    live_data = b"committed-file-with-missing-object\n"
    ref = h.client.upload_blob(h.ws, [live_data], size=len(live_data), media_type="text/plain")
    _dispatch(h.client, _add_file_dto(h.ws, h.proj, ref))
    missing_loc = _object_loc(h.ws, live_data)
    if h.dsn is None:
        h.store._objects.pop(str(missing_loc["storage_key"]))  # type: ignore[attr-defined]
    else:
        (h.app.gateways.get(BlobStore)._root / str(missing_loc["storage_key"])).unlink()  # type: ignore[attr-defined]

    h.clock.advance(timedelta(hours=25))
    view_1 = h.client.ask(FindOrphanBlobs(workspace_id=h.ws))
    view_2 = h.client.ask(FindOrphanBlobs(workspace_id=h.ws))
    assert isinstance(view_1, FindOrphanBlobsView)
    assert isinstance(view_2, FindOrphanBlobsView)
    assert view_1.report_digest == view_2.report_digest
    assert [o.storage_key for o in view_1.orphan_objects] == [orphan_loc["storage_key"]]
    assert [m.storage_key for m in view_1.missing_objects] == [missing_loc["storage_key"]]
    assert view_1.report_digest == canonical_digest(
        json.loads(json.dumps(view_1.to_json()["orphan_objects"]))
    )

    extra_loc = _promote_orphan(h, b"second-orphan-after-report\n")
    with pytest.raises(PreconditionFailed) as exc_info:
        _dispatch(
            h.client,
            PruneOrphanObjects(
                workspace_id=h.ws,
                report_digest=view_1.report_digest,
                confirm=True,
            ),
        )
    assert exc_info.value.code is ErrorCode.INVALID_TRANSITION
    assert exc_info.value.details == {"reason": "report_changed"}
    assert h.store.exists(orphan_loc)
    assert h.store.exists(extra_loc)


def test_prune_orphans_stale_report_rejected(mem_harness: Harness) -> None:
    _check_orphan_report_and_stale_guard(mem_harness)


@pytest.mark.pg
def test_pg_prune_orphans_stale_report_rejected(pg_harness: Harness) -> None:
    _check_orphan_report_and_stale_guard(pg_harness)


def _check_skips_young_and_audits(h: Harness) -> None:
    old_loc = _promote_orphan(h, b"orphan-older-than-ttl\n")
    h.clock.advance(timedelta(hours=25))
    young_loc = _promote_orphan(h, b"orphan-younger-than-ttl\n")

    report = h.client.ask(FindOrphanBlobs(workspace_id=h.ws))
    assert isinstance(report, FindOrphanBlobsView)
    assert len(report.orphan_objects) == 2

    pruned = _dispatch(
        h.client,
        PruneOrphanObjects(workspace_id=h.ws, report_digest=report.report_digest, confirm=True),
    )
    assert isinstance(pruned, PruneOrphanObjectsResult)
    assert pruned.deleted == 1
    assert pruned.skipped_referenced == 0
    assert not h.store.exists(old_loc)
    assert h.store.exists(young_loc)
    assert ("artifacts.prune_orphan_objects", "allowed") in _audit_actions(h)


def test_prune_orphans_skips_young_objects(mem_harness: Harness) -> None:
    _check_skips_young_and_audits(mem_harness)


@pytest.mark.pg
def test_pg_prune_orphans_skips_young_objects(pg_harness: Harness) -> None:
    _check_skips_young_and_audits(pg_harness)


def _check_skips_newly_referenced(h: Harness) -> None:
    reused_bytes = b"orphan-that-gains-staged-ref\n"
    reused_loc = _promote_orphan(h, reused_bytes)
    h.clock.advance(timedelta(hours=25))

    report = h.client.ask(FindOrphanBlobs(workspace_id=h.ws))
    assert isinstance(report, FindOrphanBlobsView)
    assert [o.storage_key for o in report.orphan_objects] == [reused_loc["storage_key"]]

    staged_ref = h.client.upload_blob(h.ws, [reused_bytes], size=len(reused_bytes), media_type="text/plain")

    pruned = _dispatch(
        h.client,
        PruneOrphanObjects(workspace_id=h.ws, report_digest=report.report_digest, confirm=True),
    )
    assert isinstance(pruned, PruneOrphanObjectsResult)
    assert pruned.deleted == 0
    assert pruned.skipped_referenced == 1
    assert h.store.exists(reused_loc)

    added = _dispatch(h.client, _add_file_dto(h.ws, h.proj, staged_ref))
    with h.client.open_file_version_content(FileVersionId(added.file_version_id)) as stream:
        assert stream.read() == reused_bytes


def test_prune_orphans_skips_newly_referenced(mem_harness: Harness) -> None:
    _check_skips_newly_referenced(mem_harness)


@pytest.mark.pg
def test_pg_prune_orphans_skips_newly_referenced(pg_harness: Harness) -> None:
    _check_skips_newly_referenced(pg_harness)


def _check_trash_and_grants_preserve_bytes(h: Harness) -> None:
    shared_bytes = b"shared-evidence-and-upload-bytes\n"
    ref_1 = h.client.upload_blob(h.ws, [shared_bytes], size=len(shared_bytes), media_type="text/plain")
    file_1 = _dispatch(h.client, _add_file_dto(h.ws, h.proj, ref_1, title="Primary"))

    ref_2 = h.client.upload_blob(h.ws, [shared_bytes], size=len(shared_bytes), media_type="text/plain")
    with h.app.uow_factory(RequestMeta("req_" + "e" * 26, Surface.CLI, None, h.clock.now())) as uow:
        consumed = artifacts.consume_staged_blob(
            uow,
            ref=ref_2.to_json(),
            workspace_id=h.ws,
            request_id="req_" + "e" * 26,
            now=h.clock.now(),
        )
        ev_ver = artifacts.register_file_version(
            uow,
            workspace_id=h.ws,
            project_id=h.proj,
            title="Evidence",
            origin=artifacts.FileOrigin.EVIDENCE,
            staged=consumed,
            original_filename="evidence.log",
            media_type="text/plain",
            source=VersionSource(kind="evidence", ref="step:1", captured_at=h.clock.now()),
            classification=artifacts.Classification.INTERNAL,
            safety=artifacts.SafetyReport((), (), False),
            created_by=WORKER_ID,
            ids=h.ids,
            now=h.clock.now(),
        )
        ev_ver_id = FileVersionId(UUID(str(ev_ver["file_version_id"])))
        artifacts.grant_access(
            uow,
            principal_id=WORKER_ID,
            version_ids=(ev_ver_id,),
            reason=GrantReason.ASSIGNMENT,
            ref="assign:1",
            expires_at=h.clock.now() + timedelta(hours=1),
            ids=h.ids,
            now=h.clock.now(),
        )
        uow.commit()

    trashed = _dispatch(
        h.client,
        artifacts.TrashFile(file_id=file_1.file_id, expected_row_version=2, reason="superseded"),
    )
    with h.app.uow_factory(RequestMeta("req_" + "r" * 26, Surface.CLI, None, h.clock.now())) as uow:
        assert (
            artifacts.revoke_grants(uow, reason=GrantReason.ASSIGNMENT, ref="assign:1", now=h.clock.now())
            == 1
        )
        uow.commit()

    h.clock.advance(timedelta(days=10))
    exp = _dispatch_expire(h)
    assert exp.objects_deleted == 0

    report = h.client.ask(FindOrphanBlobs(workspace_id=h.ws))
    assert isinstance(report, FindOrphanBlobsView)
    assert report.orphan_objects == ()
    assert report.missing_objects == ()

    with h.client.open_file_version_content(ev_ver_id) as stream:
        assert stream.read() == shared_bytes

    _dispatch(
        h.client,
        artifacts.RestoreFile(file_id=file_1.file_id, expected_row_version=trashed.row_version),
    )
    with h.client.open_file_version_content(FileVersionId(file_1.file_version_id)) as stream:
        assert stream.read() == shared_bytes


def test_trash_and_grant_revocation_preserve_shared_and_evidence_blobs(mem_harness: Harness) -> None:
    _check_trash_and_grants_preserve_bytes(mem_harness)


@pytest.mark.pg
def test_pg_trash_and_grant_revocation_preserve_shared_and_evidence_blobs(pg_harness: Harness) -> None:
    _check_trash_and_grants_preserve_bytes(pg_harness)
