"""``BlobCoordination`` and ``BlobDigestLock`` contracts on memory and PostgreSQL (artifacts §6.1)."""

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from integration.artifacts.test_upload_flow import (
    NOW,
    OWNER_ID,
    add_file_dto,
    clean_test_database,
    dispatch_new,
    open_test_app,
    pg_session,
    seed_principals,
    test_database,
)
from skm.adapters.memory.artifacts.blob_coordination import MemoryBlobCoordination
from skm.adapters.memory.artifacts.blob_coordination import digest_lock_key as memory_digest_lock_key
from skm.adapters.postgres.artifacts.blob_coordination import digest_lock_key as pg_digest_lock_key
from skm.bootstrap.composition import App
from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import SafetyReport
from skm.modules.artifacts.domain.file import FileOrigin
from skm.modules.artifacts.domain.file_version import VersionSource
from skm.modules.artifacts.ports import BlobCoordination, StagedBlobRepository
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from skm.platform.system_ids import Uuid7Generator
from support.pg import TestDatabase
from support.seed import SEED

__all__ = ["clean_test_database", "pg_session", "test_database"]


def _meta(tag: str = "0") -> RequestMeta:
    return RequestMeta(f"req_{tag * 26}"[:30], Surface.CLI, None, NOW)


def _seed_owner_ws(app: App) -> tuple[Actor, WorkspaceId]:
    actor = seed_principals(app, "postgres")
    ws = dispatch_new(
        app.client(actor=actor, surface=Surface.CLI), CreateWorkspace(slug="coord", title="Coord")
    )
    return actor, WorkspaceId(ws.workspace_id)


def test_digest_lock_key_vector_and_domain_separation() -> None:
    ws, other_ws = SEED.workspace_id, SEED.other_workspace_id
    digest = ContentDigest("sha256:" + "a" * 64)
    raw = b"skm-blob-v1\0local-primary\0" + str(ws).encode("utf-8") + b"\0" + digest.value.encode("utf-8")
    expected = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big", signed=True)

    assert memory_digest_lock_key(ws, digest, "local-primary") == expected
    assert pg_digest_lock_key(ws, digest, "local-primary") == expected
    assert -(2**63) <= expected < 2**63
    assert pg_digest_lock_key(ws, digest, "secondary") != expected
    assert pg_digest_lock_key(other_ws, digest, "local-primary") != expected
    assert pg_digest_lock_key(ws, ContentDigest("sha256:" + "b" * 64), "local-primary") != expected
    neg = next(
        pg_digest_lock_key(ws, ContentDigest(f"sha256:{i:064x}"), "local-primary")
        for i in range(64)
        if pg_digest_lock_key(ws, ContentDigest(f"sha256:{i:064x}"), "local-primary") < 0
    )
    assert -(2**63) <= neg < 0


def test_memory_blob_coordination_mutual_exclusion_reentrancy_and_distinct_keys() -> None:
    coord = MemoryBlobCoordination()
    ws, other_ws = SEED.workspace_id, SEED.other_workspace_id
    digest = ContentDigest("sha256:" + "1" * 64)
    entered, release, contender_in, distinct_in = (threading.Event() for _ in range(4))

    def holder() -> None:
        with coord.hold(ws, digest, "local-primary"), coord.hold(ws, digest, "local-primary"):
            entered.set()
            assert release.wait(2.0)

    def waiter(target_ws: WorkspaceId, out: threading.Event) -> None:
        assert entered.wait(2.0)
        with coord.hold(target_ws, digest, "local-primary"):
            out.set()

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_hold = pool.submit(holder)
        f_same = pool.submit(waiter, ws, contender_in)
        f_other = pool.submit(waiter, other_ws, distinct_in)
        assert distinct_in.wait(2.0)
        assert not contender_in.wait(0.1)
        release.set()
        assert contender_in.wait(2.0)
        f_hold.result()
        f_same.result()
        f_other.result()


def _enter_hold(
    coord: BlobCoordination, ws: WorkspaceId, digest: ContentDigest, flag: threading.Event
) -> None:
    with coord.hold(ws, digest, "local-primary"):
        flag.set()


@pytest.mark.pg
def test_pg_coordination_dedicated_pool_isolation_and_close(
    clean_test_database: TestDatabase, tmp_path: Path
) -> None:
    app, _, _ = open_test_app("postgres", tmp_path, clean_test_database.dsn, max_uow=2)
    try:
        _, ws = _seed_owner_ws(app)
        coord = app.gateways.get(BlobCoordination)
        digest, other = ContentDigest("sha256:" + "2" * 64), ContentDigest("sha256:" + "3" * 64)
        same_entered, other_entered = threading.Event(), threading.Event()

        with ThreadPoolExecutor(max_workers=2) as pool:
            with coord.hold(ws, digest, "local-primary"):
                # Holding a coordination lock never consumes a connection from the 2-connection UoW pool.
                with (
                    app.uow_factory(_meta("2"), readonly=True) as uow1,
                    app.uow_factory(_meta("3"), readonly=True) as uow2,
                ):
                    uow2.rollback()
                    uow1.rollback()
                f_other = pool.submit(_enter_hold, coord, ws, other, other_entered)
                f_same = pool.submit(_enter_hold, coord, ws, digest, same_entered)
                assert other_entered.wait(2.0)
                assert not same_entered.wait(0.15)
            assert same_entered.wait(2.0)
            f_other.result()
            f_same.result()
    finally:
        app.close()

    closed_coord = app.gateways.get(BlobCoordination)
    with (
        pytest.raises(BackendUnavailable) as caught,
        closed_coord.hold(SEED.workspace_id, digest, "local-primary"),
    ):
        pass
    assert caught.value.code is ErrorCode.BACKEND_UNAVAILABLE


@pytest.mark.pg
def test_pg_digest_lock_orders_cleanup_against_commit(
    clean_test_database: TestDatabase, tmp_path: Path
) -> None:
    app, clock, _ = open_test_app("postgres", tmp_path, clean_test_database.dsn, max_uow=3)
    try:
        actor, ws = _seed_owner_ws(app)
        client = app.client(actor=actor, surface=Surface.CLI)
        coord = app.gateways.get(BlobCoordination)
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )

        ref1 = client.upload_blob(ws, [b"alpha\n"], size=6)
        add_done = threading.Event()

        def run_add() -> int:
            res = dispatch_new(client, add_file_dto(ws, proj, ref1))
            add_done.set()
            return int(res.version_no)

        with ThreadPoolExecutor(max_workers=1) as pool:
            with coord.hold(ws, ContentDigest(ref1.digest), "local-primary"):
                fut = pool.submit(run_add)
                assert not add_done.wait(0.15)
            assert fut.result() == 1

        ref2 = client.upload_blob(ws, [b"beta\n"], size=5)
        cleanup_entered = threading.Event()
        seen_referenced: list[bool] = []

        def run_cleanup(storage_key: str) -> None:
            with coord.hold(ws, ContentDigest(ref2.digest), "local-primary"):
                cleanup_entered.set()
                with app.uow_factory(_meta("8"), readonly=True) as check_uow:
                    seen_referenced.append(
                        check_uow.repo(StagedBlobRepository).key_referenced("local-primary", storage_key)
                    )
                    check_uow.rollback()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with app.uow_factory(_meta("7")) as uow:
                staged = artifacts.consume_staged_blob(
                    uow, ref=ref2.to_json(), workspace_id=ws, request_id="req_" + "7" * 26, now=clock.now()
                )
                artifacts.register_file_version(
                    uow,
                    workspace_id=ws,
                    project_id=proj,
                    title="Beta",
                    origin=FileOrigin.EVIDENCE,
                    staged=staged,
                    original_filename="beta.txt",
                    media_type="text/plain",
                    source=VersionSource(kind="evidence", ref=None, captured_at=None),
                    classification=Classification.INTERNAL,
                    safety=SafetyReport(findings=(), acknowledged=(), binary=False),
                    created_by=OWNER_ID,
                    ids=Uuid7Generator(clock),
                    now=clock.now(),
                )
                fut_clean = pool.submit(run_cleanup, staged.storage_key)
                assert not cleanup_entered.wait(0.15)
                uow.commit()
            fut_clean.result()
        assert seen_referenced == [True]
    finally:
        app.close()
