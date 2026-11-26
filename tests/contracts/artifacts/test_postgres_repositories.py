"""Artifacts repositories: memory ∥ PostgreSQL parity, DDL constraints and concurrency (artifacts §6, §11).

Covers:
1. Repository parity (memory ∥ PostgreSQL): ``StagedBlobRepository``, ``BlobRepository``, ``FileRepository``,
   ``FileVersionRepository``, ``AccessGrantRepository`` and ``BlobContentReader``.
2. Bus & facade parity (memory ∥ PostgreSQL): worker negative cases (``add_file``, ``add_file_version``,
   ``trash_file``, ``restore_file`` → ``FORBIDDEN``) and ``grant_access`` / ``extend_grants`` /
   ``revoke_grants`` maintaining a single grant row per pinned ``(principal, version, reason, ref)`` claim.
3. PostgreSQL-only invariants: ``tg_file_versions__immutable`` trigger, composite deferred FK
   ``fk_files__current_version``, cross-workspace composite FKs, filter-bound pagination cursors, full
   transaction rollback leaving zero partial metadata, ``staged_blobs`` ``FOR UPDATE`` / ``SKIP LOCKED`` row
   locks, parallel version appends producing distinct consecutive ``version_no``s under the ``files`` row
   lock, and concurrent ``trash_file`` ∥ ``add_file_version`` (testing §11.1 №7).
"""

import itertools
import threading
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, cast, override
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import errors as pgerr

from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from skm.adapters.memory.blob_store import MemoryBlobStore
from skm.adapters.postgres.access.repositories import PostgresPrincipalRepository, PostgresTokenRepository
from skm.adapters.postgres.artifacts.repositories import PostgresBlobContentReader, PostgresFileRepository
from skm.adapters.postgres.config_store import PostgresConfigStore
from skm.adapters.postgres.core.audit import PostgresAuditLog
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.core.idempotency import PostgresIdempotencyStore
from skm.adapters.postgres.uow import PostgresUnitOfWork, PostgresUowFactory
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import AuditLog, Authorizer, IdempotencyStore
from skm.application_bus.registry import BusRegistry
from skm.bootstrap.adapters import postgres_repository_table
from skm.kernel import errors as kerr
from skm.kernel.error_codes import ErrorCode
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import FileVersionId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access.module import MODULE as ACCESS
from skm.modules.access.ports import PrincipalRepository, TokenPepperSource, TokenRepository
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.artifacts import ports as art_ports
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.application.staging import StagedBlobView
from skm.modules.artifacts.application.versions import VersionDraft, append_version
from skm.modules.artifacts.domain import blob as blob_dom
from skm.modules.artifacts.domain import file as file_rules
from skm.modules.artifacts.domain.access_grant import AccessGrant, AccessGrantId, GrantReason
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import SafetyFinding, SafetyLevel, SafetyReport
from skm.modules.artifacts.domain.file import FileId, FileOrigin, FileState, new_file
from skm.modules.artifacts.domain.file_version import FileVersion, VersionSource, new_version
from skm.modules.artifacts.domain.staged_blob import StagedBlob, StagedBlobId
from skm.modules.artifacts.generated import commands as wire
from skm.modules.artifacts.module import MODULE as ARTIFACTS
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource
from support.backend import LockedIds, PostgresTestBackend
from support.pg import TestDatabase, clean_test_database, pg_session, test_database
from support.seed import SEED
from unit.artifacts.application.test_commands import (
    EVERYTHING,
    NOW,
    FixedPepper,
    Packs,
    World,
    build_world,
    schemas,
    settings_registry,
)  # fmt: skip

__all__ = ["clean_test_database", "pg_session", "test_database"]


class PgWorld(World):
    """``World`` backed by PostgreSQL ``PostgresUowFactory`` and an autocommit observer connection."""

    pg: PostgresTestBackend
    uow_factory: PostgresUowFactory
    raw_uow_factory: PostgresUowFactory
    _seq: Iterator[int]

    @override
    def meta(self, key: str | None = None) -> RequestMeta:
        return RequestMeta(f"req_{next(self._seq):0>26}", Surface.TEST, key, self.clock.now())

    @override
    def uow(self, *, readonly: bool = False) -> Any:
        return self.uow_factory(self.meta(), readonly=readonly)

    def sql(self, statement: str, params: object = None) -> list[tuple[Any, ...]]:
        return self.pg.execute(statement, params)

    @override
    def snapshot(self) -> tuple[object, ...]:
        counts = dict(self.pg.table_counts("skm_artifacts"))
        unconsumed = self.sql(
            "SELECT id, consumed_at, consumed_request_id FROM skm_artifacts.staged_blobs ORDER BY id"
        )
        files = self.sql(
            "SELECT id, state, row_version, current_version_id FROM skm_artifacts.files ORDER BY id"
        )
        events = int(self.sql("SELECT count(*) FROM skm_core.domain_events")[0][0])
        return (counts, unconsumed, files, events)

    def close(self) -> None:
        self.pg.close()


def build_pg_world(database: TestDatabase) -> PgWorld:
    registry = BusRegistry.build(
        (ACCESS, WORKSPACE, ARTIFACTS),
        schemas=schemas(),
        permission_catalog=EVERYTHING,
        disabled_modules=frozenset(),
    )
    clock, ids, entropy = FrozenClock(NOW), LockedIds(), DeterministicEntropy()
    packs, authorizer = Packs(), RbacAuthorizer(clock)
    pg = PostgresTestBackend(database, pool_max_size=10)
    try:
        blobs = MemoryBlobStore(clock, max_bytes=1 << 20)
        table = cast(
            "Mapping[type, Callable[[psycopg.Connection], object]]",
            postgres_repository_table(("access", "workspace", "artifacts")),
        )
        writer = PostgresEventWriter(schemas=schemas(), subscriptions=registry.subscription_index(), ids=ids)
        raw_uow_factory = PostgresUowFactory(pg.pool, table, writer, clock)
        factories: dict[type, Callable[[psycopg.Connection], object]] = {
            **table,
            PrincipalRepository: lambda conn: PostgresPrincipalRepository(conn, clock=clock),
            TokenRepository: lambda conn: PostgresTokenRepository(conn, clock=clock),
            art_ports.FileRepository: lambda conn: PostgresFileRepository(conn, clock=clock),
            art_ports.BlobContentReader: lambda conn: PostgresBlobContentReader(conn, store=blobs),
            IdempotencyStore: lambda conn: PostgresIdempotencyStore(conn, ids),
            AuditLog: PostgresAuditLog,
            ConfigStore: PostgresConfigStore,
            PackConfigSource: lambda _conn: packs,
            Authorizer: lambda _conn: authorizer,
        }
        uow_factory = PostgresUowFactory(pg.pool, factories, writer, clock)
        bus = Bus(
            registry=registry, schemas=schemas(), uow_factory=uow_factory, authorizer=authorizer,
            scopes=FakeScopeChain(), config=ConfigLoader(settings_registry(), packs), clock=clock,
            ids=ids, entropy=entropy,
            gateways=GatewayTable(
                {TokenPepperSource: FixedPepper(), art_ports.BlobStore: cast("art_ports.BlobStore", blobs)},
                "control_plane_gateway",
            ),
            retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
            idempotency_ttl=timedelta(hours=1),
        )  # fmt: skip
        world = PgWorld(cast("Any", None), bus, clock, ids, blobs, SEED.instance_id)
        world.pg = pg
        world.uow_factory = uow_factory
        world.raw_uow_factory = raw_uow_factory
        world._seq = itertools.count(1)
        world.person("owner", {SEED.instance_id: Role.OWNER})
    except BaseException:
        pg.close()
        raise
    else:
        return world


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def side(request: pytest.FixtureRequest) -> Iterator[World]:
    if request.param == "memory":
        yield build_world()
        return
    made = build_pg_world(request.getfixturevalue("clean_test_database"))
    try:
        yield made
    finally:
        made.close()


@pytest.fixture
def pg_world(clean_test_database: TestDatabase) -> Iterator[PgWorld]:
    made = build_pg_world(clean_test_database)
    try:
        yield made
    finally:
        made.close()


# ------------------------------------------------------------------ 1. Repository & bus parity (memory ∥ pg)


def test_staged_and_blob_repositories_parity(side: World) -> None:
    ws, other_ws = side.workspace("alpha"), side.workspace("beta")
    owner_id = side.people["owner"].principal_id
    digest = blob_dom.ContentDigest("sha256:" + "a" * 64)
    staged = StagedBlob(
        StagedBlobId(side.ids.new_id()), ws, digest, 12, "text/plain", "text/plain",
        "local-primary", f"{ws}/objects/aa/{'a' * 64}", owner_id, NOW, NOW + timedelta(hours=1), None, None,
    )  # fmt: skip
    expired_row = replace(
        staged, id=StagedBlobId(side.ids.new_id()), storage_key=f"{ws}/objects/bb/{'b' * 64}",
        expires_at=NOW + timedelta(minutes=5),
    )  # fmt: skip

    with side.uow() as uow:
        repo = uow.repo(art_ports.StagedBlobRepository)
        repo.add(staged)
        repo.add(expired_row)
        with pytest.raises(kerr.Conflict) as dup:
            repo.add(staged)
        assert (dup.value.code, dup.value.details) == (
            ErrorCode.ALREADY_EXISTS, {"kind": "staged_blob", "ref": str(staged.id)},
        )  # fmt: skip
        assert repo.get_for_update(staged.id) == staged  # UoW stays usable after conflict
        assert repo.key_referenced("local-primary", staged.storage_key) is True
        uow.commit()

    with side.uow() as uow:
        repo = uow.repo(art_ports.StagedBlobRepository)
        with pytest.raises(kerr.NotFound) as missing:
            repo.get_for_update(StagedBlobId(side.ids.new_id()))
        assert missing.value.details["kind"] == "staged_blob"
        assert [row.id for row in repo.expired(NOW + timedelta(minutes=10), limit=10)] == [expired_row.id]
        assert repo.expired(NOW + timedelta(minutes=10), limit=0) == ()
        repo.delete(expired_row.id)
        assert repo.key_referenced("local-primary", expired_row.storage_key) is False
        consumed = replace(staged, consumed_at=NOW + timedelta(seconds=1), consumed_request_id="req_1")
        repo.save(consumed)
        assert repo.key_referenced("local-primary", staged.storage_key) is False
        with pytest.raises(kerr.InternalError) as twice:
            repo.save(replace(consumed, consumed_at=NOW + timedelta(seconds=2)))
        assert twice.value.details["reason"] == "consumed_twice"
        uow.commit()

    blob = blob_dom.Blob(
        blob_dom.BlobId(side.ids.new_id()), ws, digest, 12, "text/plain",
        blob_dom.BlobAvailability.AVAILABLE, NOW, None,
    )  # fmt: skip
    loc = blob_dom.BlobLocation(
        blob.id, "local-primary", staged.storage_key, None, blob_dom.LocationState.PRESENT, None
    )
    with side.uow() as uow:
        blobs = uow.repo(art_ports.BlobRepository)
        with pytest.raises(kerr.InternalError) as bad_loc:
            blobs.add(blob, replace(loc, blob_id=blob_dom.BlobId(side.ids.new_id())))
        assert bad_loc.value.details == {"reason": "foreign_location"}
        blobs.add(blob, loc)
        dup_blob = replace(blob, id=blob_dom.BlobId(side.ids.new_id()))
        dup_loc = blob_dom.BlobLocation(
            dup_blob.id, "local-primary", "other-key", None, blob_dom.LocationState.PRESENT, None
        )
        with pytest.raises(kerr.Conflict) as taken:
            blobs.add(dup_blob, dup_loc)
        assert (taken.value.code, taken.value.details) == (
            ErrorCode.ALREADY_EXISTS, {"kind": "blob", "digest": digest.value},
        )  # fmt: skip
        assert blobs.find(ws, digest, 12) == blob
        other_blob = replace(blob, id=blob_dom.BlobId(side.ids.new_id()), workspace_id=other_ws)
        other_loc = blob_dom.BlobLocation(
            other_blob.id, "local-primary", f"{other_ws}/objects/aa/{'a' * 64}", None,
            blob_dom.LocationState.PRESENT, None,
        )  # fmt: skip
        blobs.add(other_blob, other_loc)
        assert uow.repo(art_ports.StagedBlobRepository).key_referenced("local-primary", staged.storage_key)
        blobs.mark_location(
            blob.id, "local-primary", blob_dom.LocationState.MISSING, NOW + timedelta(minutes=1)
        )
        assert blobs.locations(blob.id)[0].state is blob_dom.LocationState.MISSING
        assert blobs.all_keys(ws, "local-primary") == frozenset({staged.storage_key})
        with pytest.raises(kerr.NotFound):
            blobs.mark_location(blob.id, "s3-missing", blob_dom.LocationState.PRESENT, NOW)
        uow.commit()


def test_file_and_version_repositories_jsonb_and_pagination_parity(side: World) -> None:
    ws = side.workspace("alpha")
    proj = side.project(ws, "skm")
    owner_id = side.people["owner"].principal_id
    digest = blob_dom.ContentDigest("sha256:" + "c" * 64)
    blob = blob_dom.Blob(
        blob_dom.BlobId(side.ids.new_id()), ws, digest, 5, "text/plain",
        blob_dom.BlobAvailability.AVAILABLE, NOW, None,
    )  # fmt: skip
    loc = blob_dom.BlobLocation(
        blob.id, "local-primary", f"{ws}/objects/cc/{'c' * 64}", None, blob_dom.LocationState.PRESENT, None
    )
    f1 = new_file(
        file_id=FileId(side.ids.new_id()), workspace_id=ws, project_id=proj, title="Spec A",
        origin=FileOrigin.UPLOAD, classification=Classification.CONFIDENTIAL, created_by=owner_id, now=NOW,
    )  # fmt: skip
    f2 = new_file(
        file_id=FileId(side.ids.new_id()), workspace_id=ws, project_id=None, title="Evidence B",
        origin=FileOrigin.EVIDENCE, classification=Classification.INTERNAL, created_by=owner_id,
        now=NOW + timedelta(seconds=10),
    )  # fmt: skip
    f3 = new_file(
        file_id=FileId(side.ids.new_id()), workspace_id=ws, project_id=proj, title="Spec C",
        origin=FileOrigin.UPLOAD, classification=Classification.PUBLIC, created_by=owner_id,
        now=NOW + timedelta(seconds=20),
    )  # fmt: skip
    report = SafetyReport(
        (SafetyFinding("CS-HOME-PATH", SafetyLevel.WARN, "1 home path", 3, None),), ("CS-SECRET-NAME",), False
    )

    with side.uow() as uow:
        uow.repo(art_ports.BlobRepository).add(blob, loc)
        files, versions = uow.repo(art_ports.FileRepository), uow.repo(art_ports.FileVersionRepository)
        for item in (f1, f2, f3):
            files.add(item)
        with pytest.raises(kerr.Conflict):
            files.add(f1)
        assert versions.last_no(f1.id) == 0
        v1 = new_version(
            version_id=FileVersionId(side.ids.new_id()), file=f1, previous_no=versions.last_no(f1.id),
            blob=blob, original_filename="spec.md", declared_media_type="text/markdown",
            description="initial", source=VersionSource("capture", "session-1", NOW), safety=report,
            created_by=owner_id, now=NOW,
        )  # fmt: skip
        versions.add(v1)
        f1_cur = file_rules.set_current(f1, v1)
        files.save(f1_cur, expected_version=1)
        v2 = new_version(
            version_id=FileVersionId(side.ids.new_id()), file=f1_cur, previous_no=versions.last_no(f1.id),
            blob=blob, original_filename="spec-v2.md", declared_media_type=None, description="second",
            source=VersionSource("upload", None, None), safety=SafetyReport((), (), True),
            created_by=owner_id, now=NOW + timedelta(seconds=5),
        )  # fmt: skip
        versions.add(v2)
        with pytest.raises(kerr.Conflict) as dup_ver:
            versions.add(replace(v2, id=FileVersionId(side.ids.new_id())))
        assert dup_ver.value.code is ErrorCode.ALREADY_EXISTS
        files.save(file_rules.set_current(f1_cur, v2), expected_version=2)
        with pytest.raises(kerr.Conflict) as stale:
            files.save(file_rules.trash(f1_cur), expected_version=1)
        assert (stale.value.code, stale.value.details) == (
            ErrorCode.VERSION_CONFLICT, {"kind": "file", "expected": 1, "actual": 3},
        )  # fmt: skip
        files.save(file_rules.trash(f2), expected_version=1)
        uow.commit()

    with side.uow(readonly=True) as uow:
        files, versions = uow.repo(art_ports.FileRepository), uow.repo(art_ports.FileVersionRepository)
        assert versions.get(v1.id) == v1
        unknown = FileVersionId(side.ids.new_id())
        assert [v.id for v in versions.many([v2.id, unknown, v1.id, v2.id])] == [v2.id, v1.id]
        v_p1 = versions.list(f1.id, after=None, limit=1)
        v_p2 = versions.list(f1.id, after=v_p1.next, limit=1)
        assert ([v.version_no for v in v_p1.items], [v.version_no for v in v_p2.items], v_p2.next) == (
            [2], [1], None,
        )  # fmt: skip
        p1 = files.list(ws, project_id=None, state=None, origin=None, after=None, limit=2)
        p2 = files.list(ws, project_id=None, state=None, origin=None, after=p1.next, limit=2)
        assert ([f.id for f in (*p1.items, *p2.items)], p2.next) == ([f3.id, f2.id, f1.id], None)
        active_proj = files.list(
            ws, project_id=proj, state=FileState.ACTIVE, origin=FileOrigin.UPLOAD, after=None, limit=10
        )
        assert [f.id for f in active_proj.items] == [f3.id, f1.id]
        with pytest.raises(kerr.ValidationFailed) as bad_cur:
            files.list(ws, project_id=None, state=None, origin=None, after="bm90LWEtY3Vyc29y", limit=2)
        assert (bad_cur.value.code, bad_cur.value.details["field"]) == (ErrorCode.SCHEMA_INVALID, "after")


def test_worker_negative_mutations_and_grant_lifecycle_parity(side: World) -> None:
    ws = side.workspace("alpha")
    proj = side.project(ws, "skm")
    worker = side.worker("worker-1", ws)
    run_scope = side.run_scope(ws, proj)
    assignment_id = UUID("01900000-0000-7000-8000-000000000777")
    worker_tok = side.token_actor(
        worker, permissions=frozenset({"file.read", "file.write"}), scope=run_scope, assignment=assignment_id
    )

    staged_a = side.stage(ws, b"pinned content\n")
    side.refused(ErrorCode.FORBIDDEN, lambda: side.add_file(ws, staged_a, project_id=proj, actor=worker_tok))
    added = side.add_file(ws, staged_a, project_id=proj, title="Runbook")
    file_id, v1_id = added.file_id, FileVersionId(added.file_version_id)
    twin = side.add_file(ws, side.stage(ws, b"pinned content\n"), project_id=proj, title="Twin")
    twin_v_id = FileVersionId(twin.file_version_id)
    staged_v2 = side.stage(ws, b"v2 content\n")

    side.refused(
        ErrorCode.FORBIDDEN, lambda: side.add_version(file_id, staged_v2, version=2, actor=worker_tok)
    )
    side.refused(
        ErrorCode.FORBIDDEN,
        lambda: side.run(
            artifacts.TrashFile(file_id=file_id, expected_row_version=2, reason="no"), actor=worker_tok
        ),
    )
    side.run(artifacts.TrashFile(file_id=file_id, expected_row_version=2, reason="temp"))
    side.refused(
        ErrorCode.FORBIDDEN,
        lambda: side.run(artifacts.RestoreFile(file_id=file_id, expected_row_version=3), actor=worker_tok),
    )
    side.run(artifacts.RestoreFile(file_id=file_id, expected_row_version=3))

    ref = str(assignment_id)
    exp1, exp2 = NOW + timedelta(hours=1), NOW + timedelta(hours=3)
    with side.uow() as uow:
        added_n = artifacts.grant_access(
            uow, principal_id=worker.principal_id, version_ids=[v1_id, v1_id], reason=GrantReason.ASSIGNMENT,
            ref=ref, expires_at=exp1, ids=side.ids, now=NOW,
        )  # fmt: skip
        other_n = artifacts.grant_access(
            uow, principal_id=worker.principal_id, version_ids=[v1_id], reason=GrantReason.SHARE,
            ref="share-later", expires_at=NOW + timedelta(hours=10), ids=side.ids, now=NOW,
        )  # fmt: skip
        repeat_n = artifacts.grant_access(
            uow, principal_id=worker.principal_id, version_ids=[v1_id], reason=GrantReason.ASSIGNMENT,
            ref=ref, expires_at=exp2, ids=side.ids, now=NOW,
        )  # fmt: skip
        assert (added_n, other_n, repeat_n) == (1, 1, 0)
        exact = uow.repo(art_ports.AccessGrantRepository).active_for(
            worker.principal_id, v1_id, NOW, reason=GrantReason.ASSIGNMENT, ref=ref
        )
        assert exact is not None
        assert exact.expires_at == exp1
        assert artifacts.extend_grants(uow, reason=GrantReason.ASSIGNMENT, ref=ref, expires_at=exp2, now=NOW)
        assert artifacts.extend_grants(uow, reason=GrantReason.ASSIGNMENT, ref=ref, expires_at=exp1, now=NOW)
        renewed = uow.repo(art_ports.AccessGrantRepository).active_for(
            worker.principal_id, v1_id, NOW, reason=GrantReason.ASSIGNMENT, ref=ref
        )
        assert renewed is not None
        assert (renewed.id, renewed.expires_at) == (exact.id, exp2)
        assert artifacts.read_text_content(uow, v1_id, max_bytes=1024) == "pinned content\n"
        uow.commit()

    assert side.ask(artifacts.GetFileVersion(file_version_id=v1_id), actor=worker_tok).version_no == 1
    assert (
        side.ask(artifacts.OpenFileVersionContent(file_version_id=v1_id), actor=worker_tok).size_bytes == 15
    )
    with pytest.raises(kerr.SkmError) as denied_twin:
        side.ask(artifacts.GetFileVersion(file_version_id=twin_v_id), actor=worker_tok)
    assert denied_twin.value.code is ErrorCode.FORBIDDEN

    with side.uow() as uow:
        assert artifacts.revoke_grants(uow, reason=GrantReason.ASSIGNMENT, ref=ref, now=NOW) == 1
        assert (
            artifacts.extend_grants(uow, reason=GrantReason.ASSIGNMENT, ref=ref, expires_at=exp2, now=NOW)
            == 0
        )
        uow.commit()
    with pytest.raises(kerr.SkmError) as after_revoke:
        side.ask(artifacts.OpenFileVersionContent(file_version_id=v1_id), actor=worker_tok)
    assert after_revoke.value.code is ErrorCode.FORBIDDEN


def test_held_claims_and_a_batch_grant_see_only_the_exact_active_claim(side: World) -> None:
    ws = side.workspace("alpha")
    proj = side.project(ws, "skm")
    worker = side.worker("worker-1", ws)
    v1, v2, v3 = (
        FileVersionId(side.add_file(ws, side.stage(ws, body), project_id=proj, title=title).file_version_id)
        for body, title in ((b"one\n", "One"), (b"two\n", "Two"), (b"three\n", "Three"))
    )
    ref, exp = "assignment-1", NOW + timedelta(hours=1)

    def grant(versions: list[FileVersionId], reason: GrantReason, claim: str) -> int:
        with side.uow() as uow:
            added = artifacts.grant_access(
                uow, principal_id=worker.principal_id, version_ids=versions, reason=reason, ref=claim,
                expires_at=exp, ids=side.ids, now=NOW,
            )  # fmt: skip
            uow.commit()
        return added

    def held(reason: GrantReason, claim: str, at: datetime = NOW) -> frozenset[FileVersionId]:
        with side.uow() as uow:
            return uow.repo(art_ports.AccessGrantRepository).held_claims(
                worker.principal_id, [v1, v2, v3], at, reason=reason, ref=claim
            )

    assert grant([v1], GrantReason.ASSIGNMENT, ref) == 1
    assert grant([v2], GrantReason.SHARE, ref) == 1
    assert held(GrantReason.ASSIGNMENT, ref) == {v1}
    assert grant([v3, v1, v2, v3], GrantReason.ASSIGNMENT, ref) == 2  # v1's claim is held; v2's is another
    assert held(GrantReason.ASSIGNMENT, ref) == {v1, v2, v3}
    assert held(GrantReason.ASSIGNMENT, "other") == frozenset()
    assert held(GrantReason.ASSIGNMENT, ref, at=exp) == frozenset()
    with side.uow() as uow, pytest.raises(kerr.NotFound):
        artifacts.grant_access(
            uow, principal_id=worker.principal_id, version_ids=[v1, FileVersionId(uuid4())],
            reason=GrantReason.ASSIGNMENT, ref="fresh", expires_at=exp, ids=side.ids, now=NOW,
        )  # fmt: skip


# ------------------------------------------------------------------ 2. PostgreSQL-only constraints & locks


def _corrupt_current_version_and_commit(world: PgWorld, file_id: UUID, foreign_version_id: UUID) -> None:
    with world.uow() as uow:
        conn = cast("PostgresUnitOfWork", uow).connection
        conn.execute(
            "UPDATE skm_artifacts.files SET current_version_id = %s WHERE id = %s",
            (foreign_version_id, file_id),
        )
        uow.commit()


@pytest.mark.pg
def test_pg_immutability_trigger_deferred_fk_and_single_grant_row(pg_world: PgWorld) -> None:
    ws = pg_world.workspace("ws-one")
    a1 = pg_world.add_file(ws, pg_world.stage(ws, b"file one\n"), title="One")
    a2 = pg_world.add_file(ws, pg_world.stage(ws, b"file two\n"), title="Two")
    owner_id = pg_world.people["owner"].principal_id
    v1_id = FileVersionId(a1.file_version_id)

    with pg_world.uow() as uow:
        for hours in (1, 2):
            artifacts.grant_access(
                uow, principal_id=owner_id, version_ids=[v1_id], reason=GrantReason.SHARE,
                ref="claim-1", expires_at=NOW + timedelta(hours=hours), ids=pg_world.ids, now=NOW,
            )  # fmt: skip
        artifacts.extend_grants(
            uow, reason=GrantReason.SHARE, ref="claim-1", expires_at=NOW + timedelta(hours=4), now=NOW
        )
        clash = AccessGrant(
            AccessGrantId(pg_world.ids.new_id()), ws, owner_id, v1_id, GrantReason.SHARE, "claim-1",
            NOW + timedelta(hours=5), NOW, None,
        )  # fmt: skip
        with pytest.raises(kerr.Conflict) as grant_clash:
            uow.repo(art_ports.AccessGrantRepository).add_many([clash])
        assert grant_clash.value.code is ErrorCode.ALREADY_EXISTS
        uow.commit()
    assert pg_world.sql("SELECT count(*) FROM skm_artifacts.access_grants WHERE ref = 'claim-1'")[0][0] == 1

    with pytest.raises(pgerr.RestrictViolation):
        pg_world.sql("UPDATE skm_artifacts.file_versions SET description = 'mutated' WHERE id = %s", (v1_id,))
    with pytest.raises(pgerr.RestrictViolation):
        pg_world.sql("DELETE FROM skm_artifacts.file_versions WHERE id = %s", (v1_id,))

    with pytest.raises(kerr.ValidationFailed) as bad_cur:
        _corrupt_current_version_and_commit(pg_world, a1.file_id, a2.file_version_id)
    assert (bad_cur.value.code, bad_cur.value.details.get("constraint")) == (
        ErrorCode.INVALID_REFERENCE, "fk_files__current_version",
    )  # fmt: skip
    assert (
        pg_world.ask(artifacts.GetFile(file_id=a1.file_id)).current_version.file_version_id
        == a1.file_version_id
    )


@pytest.mark.pg
def test_pg_cross_workspace_composite_fks_cursors_and_unbound_reader(pg_world: PgWorld) -> None:
    ws1, ws2 = pg_world.workspace("ws-one"), pg_world.workspace("ws-two")
    proj2 = pg_world.project(ws2, "foreign-proj")
    a1 = pg_world.add_file(ws1, pg_world.stage(ws1, b"file one\n"), title="One")
    pg_world.add_file(ws1, pg_world.stage(ws1, b"file two\n"), title="Two")
    a_ws2 = pg_world.add_file(ws2, pg_world.stage(ws2, b"ws two\n"), title="OtherWs")
    owner_id = pg_world.people["owner"].principal_id
    v1_id = FileVersionId(a1.file_version_id)

    with pg_world.uow() as uow:
        cross_proj = new_file(
            file_id=FileId(pg_world.ids.new_id()), workspace_id=ws1, project_id=proj2, title="Cross",
            origin=FileOrigin.UPLOAD, classification=Classification.INTERNAL,
            created_by=owner_id, now=NOW,
        )  # fmt: skip
        with pytest.raises(kerr.ValidationFailed) as fk_proj:
            uow.repo(art_ports.FileRepository).add(cross_proj)
        assert fk_proj.value.code is ErrorCode.INVALID_REFERENCE

        v_ws2 = uow.repo(art_ports.FileVersionRepository).get(FileVersionId(a_ws2.file_version_id))
        cross_ver = FileVersion(
            FileVersionId(pg_world.ids.new_id()), ws2, FileId(a1.file_id), 9, v_ws2.blob_id, "cross.txt",
            None, "", VersionSource("upload", None, None), SafetyReport((), (), False), owner_id, NOW,
        )  # fmt: skip
        with pytest.raises(kerr.ValidationFailed) as fk_ver:
            uow.repo(art_ports.FileVersionRepository).add(cross_ver)
        assert fk_ver.value.code is ErrorCode.INVALID_REFERENCE

        cross_grant = AccessGrant(
            AccessGrantId(pg_world.ids.new_id()), ws2, owner_id, v1_id, GrantReason.SHARE, "cross-ws",
            NOW + timedelta(hours=1), NOW, None,
        )  # fmt: skip
        with pytest.raises(kerr.ValidationFailed) as fk_grant:
            uow.repo(art_ports.AccessGrantRepository).add_many([cross_grant])
        assert fk_grant.value.code is ErrorCode.INVALID_REFERENCE

        p1 = uow.repo(art_ports.FileRepository).list(
            ws1, project_id=None, state=None, origin=None, after=None, limit=1
        )
        assert p1.next is not None
        with pytest.raises(kerr.ValidationFailed) as cross_cursor:
            uow.repo(art_ports.FileRepository).list(
                ws2, project_id=None, state=None, origin=None, after=p1.next, limit=1
            )
        assert cross_cursor.value.details["field"] == "after"

    with (
        pg_world.raw_uow_factory(pg_world.meta(), readonly=True) as raw_uow,
        pytest.raises(kerr.CapabilityUnavailable) as no_store,
    ):
        artifacts.read_text_content(raw_uow, v1_id, max_bytes=64)
    assert no_store.value.code is ErrorCode.CAPABILITY_UNAVAILABLE


def _abort_mid_uow(pg_world: PgWorld, ws: Any, staged_boom: Any) -> None:
    with pg_world.uow() as uow:
        artifacts.consume_staged_blob(
            uow, ref=staged_boom.ref().to_json(), workspace_id=ws, request_id="req_boom", now=NOW
        )
        f = new_file(
            file_id=FileId(pg_world.ids.new_id()), workspace_id=ws, project_id=None, title="Boom",
            origin=FileOrigin.UPLOAD, classification=Classification.INTERNAL,
            created_by=pg_world.people["owner"].principal_id, now=NOW,
        )  # fmt: skip
        uow.repo(art_ports.FileRepository).add(f)
        raise RuntimeError("abort before commit")


@pytest.mark.pg
def test_pg_rollback_leaves_no_partial_metadata_and_staged_locks_serialize(pg_world: PgWorld) -> None:
    ws = pg_world.workspace("alpha")
    secret_staged = pg_world.stage(ws, b"api_key = 'sk-LiveSecretKey1234567890ABCDEF'\n")
    pg_world.refused(ErrorCode.CONTENT_UNSAFE, lambda: pg_world.add_file(ws, secret_staged, filename=".env"))
    admitted = pg_world.add_file(
        ws, secret_staged, filename=".env", classification=wire.Classification.CONFIDENTIAL,
        acknowledge=("CS-SECRET-NAME", "CS-SECRET-CONTENT"),
    )  # fmt: skip
    assert admitted.version_no == 1

    staged_boom = pg_world.stage(ws, b"rollback me\n")
    before = pg_world.snapshot()
    with pytest.raises(RuntimeError, match="abort before commit"):
        _abort_mid_uow(pg_world, ws, staged_boom)
    assert pg_world.snapshot() == before

    exp_locked = pg_world.stage(ws, b"locked expired\n", ttl=timedelta(minutes=5))
    exp_free = pg_world.stage(ws, b"free expired\n", ttl=timedelta(minutes=5))
    with pg_world.uow() as uow1, pg_world.uow() as uow2:
        uow1.repo(art_ports.StagedBlobRepository).get_for_update(exp_locked.id)
        found = uow2.repo(art_ports.StagedBlobRepository).expired(NOW + timedelta(minutes=10), limit=10)
        assert [row.id for row in found] == [exp_free.id]

    shared_staged = pg_world.stage(ws, b"race once\n")
    barrier = threading.Barrier(2)

    def race_consume(idx: int) -> str:
        barrier.wait(timeout=5)
        try:
            pg_world.add_file(ws, shared_staged, title=f"Race {idx}")
        except kerr.SkmError as exc:
            return str(exc.code)
        else:
            return "ok"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(race_consume, (1, 2)))
    assert outcomes == [str(ErrorCode.STAGED_BLOB_CONSUMED), "ok"]


@pytest.mark.pg
def test_pg_parallel_add_file_version_produces_consecutive_numbers(pg_world: PgWorld) -> None:
    ws = pg_world.workspace("alpha")
    owner_id = pg_world.people["owner"].principal_id
    created = pg_world.add_file(ws, pg_world.stage(ws, b"v1\n"), title="Concurrent")
    file_id = FileId(created.file_id)

    staged_parallel = [pg_world.stage(ws, f"parallel-{i}\n".encode()) for i in range(3)]
    start_versions = threading.Barrier(3)

    def append_under_lock(idx: int) -> int:
        st = staged_parallel[idx]
        start_versions.wait(timeout=5)
        for _ in range(5):
            current_view = pg_world.ask(artifacts.GetFile(file_id=file_id))
            try:
                res = pg_world.add_version(file_id, st, version=current_view.row_version)
            except kerr.Conflict as exc:
                if exc.code is not ErrorCode.VERSION_CONFLICT:
                    raise
            else:
                return res.version_no
        raise AssertionError("parallel AddFileVersion did not converge")

    with ThreadPoolExecutor(max_workers=3) as pool:
        nos = sorted(pool.map(append_under_lock, range(3)))
    assert nos == [2, 3, 4]
    after_parallel = pg_world.ask(artifacts.GetFile(file_id=file_id))
    assert (after_parallel.current_version.version_no, after_parallel.row_version) == (4, 5)

    # Direct UoW-level lock serialization (last_no FOR UPDATE before reading file row)
    staged_uow = [pg_world.stage(ws, f"uow-{i}\n".encode()) for i in range(2)]
    uow_barrier = threading.Barrier(2)

    def uow_append(idx: int) -> int:
        st = staged_uow[idx]
        uow_barrier.wait(timeout=5)
        with pg_world.uow() as uow:
            uow.repo(art_ports.FileVersionRepository).last_no(file_id)
            file = uow.repo(art_ports.FileRepository).get(file_id)
            view: StagedBlobView = artifacts.consume_staged_blob(
                uow, ref=st.ref().to_json(), workspace_id=ws, request_id=f"req_uow_{idx}", now=NOW
            )
            draft = VersionDraft(
                staged=view, original_filename=f"uow-{idx}.txt", declared_media_type="text/plain",
                description="", source=VersionSource("upload", None, None),
                safety=SafetyReport((), (), False), created_by=owner_id,
            )  # fmt: skip
            _, ver = append_version(
                uow, file, classification=file.classification, draft=draft, ids=pg_world.ids, now=NOW
            )
            uow.commit()
            return ver.version_no

    with ThreadPoolExecutor(max_workers=2) as pool:
        uow_nos = sorted(pool.map(uow_append, range(2)))
    assert uow_nos == [5, 6]


@pytest.mark.pg
def test_pg_concurrent_trash_and_add_file_version_race(pg_world: PgWorld) -> None:
    """testing §11.1 №7: concurrent trash_file ∥ add_file_version yields one consistent outcome."""
    ws = pg_world.workspace("alpha")
    race_target = pg_world.add_file(ws, pg_world.stage(ws, b"race-base\n"), title="TrashRace")
    race_id = FileId(race_target.file_id)
    race_staged = pg_world.stage(ws, b"race-v2\n")
    race_barrier = threading.Barrier(2)

    def do_trash() -> tuple[str, Any]:
        race_barrier.wait(timeout=5)
        try:
            res = pg_world.run(artifacts.TrashFile(file_id=race_id, expected_row_version=2, reason="retire"))
        except kerr.SkmError as exc:
            return ("err", exc.code)
        else:
            return ("ok", res.row_version)

    def do_version() -> tuple[str, Any]:
        race_barrier.wait(timeout=5)
        try:
            res = pg_world.add_version(race_id, race_staged, version=2)
        except kerr.SkmError as exc:
            return ("err", exc.code)
        else:
            return ("ok", res.version_no)

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_trash = pool.submit(do_trash)
        fut_ver = pool.submit(do_version)
        trash_out, ver_out = fut_trash.result(), fut_ver.result()

    final_file = pg_world.ask(artifacts.GetFile(file_id=race_id))
    if trash_out[0] == "ok":
        assert ver_out == ("err", ErrorCode.VERSION_CONFLICT)
        assert (final_file.state, final_file.current_version.version_no, final_file.row_version) == (
            "trashed", 1, 3,
        )  # fmt: skip
        with pytest.raises(kerr.PreconditionFailed) as trashed_err:
            pg_world.add_version(race_id, race_staged, version=3)
        assert trashed_err.value.code is ErrorCode.FILE_TRASHED
    else:
        assert ver_out == ("ok", 2)
        assert trash_out == ("err", ErrorCode.VERSION_CONFLICT)
        assert (final_file.state, final_file.current_version.version_no, final_file.row_version) == (
            "active", 2, 3,
        )  # fmt: skip
