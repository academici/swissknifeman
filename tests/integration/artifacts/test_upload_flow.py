"""End-to-end ``SkmClient.upload_blob``, consume, and content streaming (artifacts §5-§8, §15)."""

import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from fakes.clock import FrozenClock
from skm.application_bus.client import SkmClient, StagedBlobRef
from skm.application_bus.ports import AuditLog
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import FileVersionId, PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.generated import commands as wire
from skm.modules.artifacts.ports import BlobStore
from skm.modules.settings.generated import commands as settings_cmds
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from skm.platform.config.bootstrap import load_bootstrap
from support.pg import TestDatabase, clean_test_database, pg_session, test_database
from support.seed import SEED

__all__ = [
    "NOW",
    "OWNER_ID",
    "Harness",
    "add_file_dto",
    "audit_rows",
    "clean_test_database",
    "dispatch_new",
    "open_test_app",
    "pg_session",
    "seed_principals",
    "test_database",
]

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
OWNER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d1"))


@dataclass
class Harness:
    app: App
    clock: FrozenClock
    owner: Actor
    client: SkmClient
    ws: WorkspaceId
    proj: ProjectId
    blobs_root: Path
    dsn: str | None


def dispatch_new(client: SkmClient, cmd: object) -> Any:
    return client.dispatch(cmd, idempotency_key=client.new_idempotency_key())


def audit_rows(app: App, dsn: str | None) -> list[tuple[str, str, UUID, str]]:
    if dsn is not None:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
            rows = conn.execute(
                "SELECT action, decision, actor_id, target::text FROM skm_core.audit_records"
            ).fetchall()
            return [
                (str(r[0]), str(r[1]), r[2] if isinstance(r[2], UUID) else UUID(str(r[2])), str(r[3]))
                for r in rows
            ]
    with app.uow_factory(RequestMeta("req_" + "a" * 26, Surface.CLI, None, NOW), readonly=True) as uow:
        mem_log: Any = uow.repo(AuditLog)
        out = [
            (r.action, r.decision, UUID(int=r.actor_id.int), json.dumps(r.target))
            for r in mem_log._core.audit
        ]
        uow.rollback()
        return out


def open_test_app(
    backend: str, tmp_path: Path, dsn: str | None = None, *, max_uow: int = 2
) -> tuple[App, FrozenClock, Path]:
    clock = FrozenClock(NOW)
    env = {"SKM_DATABASE_URL": dsn} if dsn else {}
    bs_env = {"SKM_DATABASE_URL": dsn or "postgresql://127.0.0.1:5432/mem"}
    bs = replace(
        load_bootstrap(None, bs_env, tmp_path),
        instance_id=SEED.instance_id,
        database_application_name="skm-artifacts-int",
        database_pool_min_size=0,
        database_pool_max_size=max_uow,
        database_pool_timeout_seconds=2,
    )
    ov = CompositionOverrides(
        authorizer=RbacAuthorizer(clock), scopes=StoredScopeChain(), clock=clock, instance_id=SEED.instance_id
    )
    inv: JsonObject = {}
    be = "postgres" if backend == "postgres" else None
    return (
        build_app(bs, surface=Surface.CLI, environ=env, invocation=inv, backend=be, overrides=ov),
        clock,
        bs.blobs_root,
    )


def seed_principals(
    app: App,
    backend: str,
    people: Sequence[tuple[PrincipalId, PrincipalKind, str]] = ((OWNER_ID, PrincipalKind.HUMAN, "owner"),),
    roles: Sequence[tuple[ScopeId, PrincipalId, Role]] = ((SEED.instance_id, OWNER_ID, Role.OWNER),),
) -> Actor:
    with app.uow_factory(RequestMeta("req_" + "1" * 26, Surface.CLI, None, NOW)) as uow:
        if backend == "memory":
            uow.repo(ScopeRegistry).create(
                SEED.instance_id, ScopeKind.INSTANCE, parent=None, workspace_id=None
            )
        for pid, kind, name in people:
            uow.repo(PrincipalRepository).add(
                new_principal(principal_id=pid, kind=kind, display_name=name, created_by=None, now=NOW)
            )
        for scope_id, pid, role in roles:
            uow.repo(MembershipRepository).upsert(Membership(scope_id, pid, role, None, NOW))
        uow.commit()
    return Actor(OWNER_ID, PrincipalKind.HUMAN, "owner")


def _make_harness(backend: str, tmp_path: Path, dsn: str | None = None) -> Iterator[Harness]:
    app, clock, blobs_root = open_test_app(backend, tmp_path, dsn)
    try:
        actor = seed_principals(app, backend)
        client = app.client(actor=actor, surface=Surface.CLI)
        ws = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        yield Harness(app, clock, actor, client, ws, proj, blobs_root, dsn)
    finally:
        app.close()


@pytest.fixture
def mem_harness(tmp_path: Path) -> Iterator[Harness]:
    yield from _make_harness("memory", tmp_path)


@pytest.fixture
def pg_harness(clean_test_database: TestDatabase, tmp_path: Path) -> Iterator[Harness]:
    yield from _make_harness("postgres", tmp_path, clean_test_database.dsn)


def add_file_dto(ws: WorkspaceId, proj: ProjectId, ref: StagedBlobRef, **overrides: Any) -> artifacts.AddFile:
    fields: dict[str, Any] = {
        "staged_blob_id": ref.staged_blob_id,
        "workspace_id": ref.workspace_id,
        "digest": ref.digest,
        "size": ref.size,
        "media_type": ref.media_type,
        **overrides,
    }
    return artifacts.AddFile(
        workspace_id=ws,
        project_id=proj,
        title="Audit note",
        origin=wire.FileOrigin.UPLOAD,
        blob=wire.AddFileDefsStagedBlobRef(**fields),
        original_filename="audit.txt",
        source=wire.AddFileDefsVersionSource(kind="upload"),
    )


def _exercise_e2e_upload_consume_and_read(h: Harness) -> None:
    v1_bytes = b"SECRET-BYTE-PAYLOAD-V1\nsecond line\n"
    v2_bytes = b"SECRET-BYTE-PAYLOAD-V2\nupdated\n"
    v1_digest = "sha256:" + hashlib.sha256(v1_bytes).hexdigest()

    ref1 = h.client.upload_blob(
        h.ws,
        [v1_bytes[:10], v1_bytes[10:]],
        size=len(v1_bytes),
        expected_digest=v1_digest,
        media_type="text/plain",
    )
    assert ref1.digest == v1_digest
    assert ref1.size == len(v1_bytes)
    assert ref1.media_type == "text/plain"

    idem = h.client.new_idempotency_key()
    added: Any = h.client.dispatch(add_file_dto(h.ws, h.proj, ref1), idempotency_key=idem)
    assert added.version_no == 1
    assert h.client.dispatch(add_file_dto(h.ws, h.proj, ref1), idempotency_key=idem) == added

    with pytest.raises(SkmError) as consumed_err:
        dispatch_new(h.client, add_file_dto(h.ws, h.proj, ref1))
    assert consumed_err.value.code is ErrorCode.STAGED_BLOB_CONSUMED

    ref2 = h.client.upload_blob(h.ws, [v2_bytes], size=len(v2_bytes))
    ver_ref = wire.AddFileVersionDefsStagedBlobRef(
        ref2.staged_blob_id, ref2.workspace_id, ref2.digest, ref2.size, ref2.media_type
    )
    ver2 = dispatch_new(
        h.client,
        artifacts.AddFileVersion(
            file_id=added.file_id,
            expected_row_version=2,
            blob=ver_ref,
            original_filename="audit-v2.txt",
            declared_media_type=None,
            source=wire.AddFileVersionDefsVersionSource(kind="upload"),
        ),
    )
    assert ver2.version_no == 2

    with h.client.open_file_version_content(FileVersionId(added.file_version_id)) as s1:
        assert s1.read() == v1_bytes
    with h.client.open_file_version_content(FileVersionId(ver2.file_version_id)) as s2:
        assert s2.read() == v2_bytes

    with h.app.uow_factory(
        RequestMeta("req_" + "9" * 26, Surface.CLI, None, h.clock.now()), readonly=True
    ) as uow:
        text = artifacts.read_text_content(uow, FileVersionId(added.file_version_id), max_bytes=1024)
        uow.rollback()
    assert text == v1_bytes.decode()

    events = list(h.client.events(workspace_id=h.ws, after=0))
    assert events
    for ev in events:
        assert "SECRET-BYTE-PAYLOAD" not in json.dumps(ev.payload)
    for _, _, _, target_json in audit_rows(h.app, h.dsn):
        assert "SECRET-BYTE-PAYLOAD" not in target_json


def test_memory_upload_consume_stream_and_validation(mem_harness: Harness) -> None:
    _exercise_e2e_upload_consume_and_read(mem_harness)

    for declared_size in (4, 6):
        with pytest.raises(SkmError) as exc:
            mem_harness.client.upload_blob(mem_harness.ws, [b"hello"], size=declared_size)
        assert exc.value.code is ErrorCode.BLOB_DIGEST_MISMATCH
        assert exc.value.details.get("reason") == "size"

    with pytest.raises(SkmError) as dig_exc:
        mem_harness.client.upload_blob(
            mem_harness.ws, [b"hello"], size=5, expected_digest="sha256:" + "0" * 64
        )
    assert dig_exc.value.code is ErrorCode.BLOB_DIGEST_MISMATCH
    assert dig_exc.value.details.get("reason") == "digest"

    def broken() -> Iterator[bytes]:
        yield b"part1"
        raise RuntimeError("broken pipe")

    with pytest.raises(RuntimeError, match="broken pipe"):
        mem_harness.client.upload_blob(mem_harness.ws, broken(), size=10)


@pytest.mark.pg
def test_pg_upload_limits_crash_orphan_reuse_and_e2e(pg_harness: Harness) -> None:
    _exercise_e2e_upload_consume_and_read(pg_harness)

    proj_scope = settings_cmds.SetValueDefsScopeRef(level="project", scope_id=pg_harness.proj)
    with pytest.raises(SkmError) as proj_cfg_err:
        dispatch_new(
            pg_harness.client,
            settings_cmds.SetValue(
                scope=proj_scope,
                key="artifacts.upload.max_bytes",
                value=2048,
                reason="disallowed project level",
            ),
        )
    assert proj_cfg_err.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED

    ws_scope = settings_cmds.SetValueDefsScopeRef(level="workspace", scope_id=pg_harness.ws)
    dispatch_new(
        pg_harness.client,
        settings_cmds.SetValue(
            scope=ws_scope, key="artifacts.upload.max_bytes", value=1024, reason="narrow ceiling"
        ),
    )
    with pytest.raises(SkmError) as decl_large:
        pg_harness.client.upload_blob(pg_harness.ws, [b"x" * 1025], size=1025)
    assert decl_large.value.code is ErrorCode.BLOB_TOO_LARGE

    with pytest.raises(SkmError) as stream_large:
        pg_harness.client.upload_blob(pg_harness.ws, [b"x" * 600, b"y" * 500], size=1000)
    assert stream_large.value.code is ErrorCode.BLOB_TOO_LARGE
    staging_dir = pg_harness.blobs_root / "staging"
    assert not staging_dir.exists() or list(staging_dir.rglob("*.part")) == []

    store = pg_harness.app.gateways.get(BlobStore)
    orphan_bytes = b"orphan-ok\n"
    assert store.exists(store.promote(store.stage(pg_harness.ws, [orphan_bytes])))
    recovered = pg_harness.client.upload_blob(pg_harness.ws, [orphan_bytes], size=len(orphan_bytes))
    assert recovered.digest == "sha256:" + hashlib.sha256(orphan_bytes).hexdigest()
