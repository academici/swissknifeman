"""Security boundaries of ``upload_blob``, ``StagedBlobRef`` and content streaming (§4, §7, §8)."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from fakes.clock import FrozenClock
from integration.artifacts.test_upload_flow import (
    OWNER_ID,
    add_file_dto,
    audit_rows,
    clean_test_database,
    dispatch_new,
    open_test_app,
    pg_session,
    seed_principals,
    test_database,
)
from skm.application_bus.client import SkmClient
from skm.bootstrap.composition import App
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import FileVersionId, PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access.domain.membership import Membership
from skm.modules.access.ports import MembershipRepository
from skm.modules.access.public import Role
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.domain.access_grant import GrantReason
from skm.modules.artifacts.ports import BlobStore
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from skm.platform.system_ids import Uuid7Generator
from support.pg import TestDatabase

__all__ = ["clean_test_database", "pg_session", "test_database"]

VIEWER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000e2"))
OUTSIDER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000e3"))
WORKER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000e4"))


@dataclass
class SecWorld:
    app: App
    clock: FrozenClock
    owner: SkmClient
    viewer: SkmClient
    outsider: SkmClient
    worker: SkmClient
    ws_a: WorkspaceId
    ws_b: WorkspaceId
    proj_a: ProjectId
    dsn: str | None


def _meta(tag: str, now: datetime) -> RequestMeta:
    return RequestMeta(f"req_{tag * 26}"[:30], Surface.CLI, None, now)


def _make_sec_world(backend: str, tmp_path: Path, dsn: str | None = None) -> Iterator[SecWorld]:
    app, clock, _ = open_test_app(backend, tmp_path, dsn)
    try:
        owner_actor = seed_principals(
            app,
            backend,
            people=(
                (OWNER_ID, PrincipalKind.HUMAN, "owner"),
                (VIEWER_ID, PrincipalKind.HUMAN, "viewer"),
                (OUTSIDER_ID, PrincipalKind.HUMAN, "outsider"),
                (WORKER_ID, PrincipalKind.WORKER, "worker"),
            ),
        )
        owner = app.client(actor=owner_actor, surface=Surface.CLI)
        ws_a = WorkspaceId(dispatch_new(owner, CreateWorkspace(slug="ws-a", title="WS A")).workspace_id)
        ws_b = WorkspaceId(dispatch_new(owner, CreateWorkspace(slug="ws-b", title="WS B")).workspace_id)
        proj_a = ProjectId(
            dispatch_new(owner, CreateProject(workspace_id=ws_a, slug="pa", title="PA")).project_id
        )
        with app.uow_factory(_meta("2", clock.now())) as uow:
            uow.repo(MembershipRepository).upsert(
                Membership(ScopeId(ws_a), VIEWER_ID, Role.VIEWER, None, clock.now())
            )
            uow.repo(MembershipRepository).upsert(
                Membership(ScopeId(ws_b), OUTSIDER_ID, Role.MEMBER, None, clock.now())
            )
            uow.repo(MembershipRepository).upsert(
                Membership(ScopeId(ws_a), WORKER_ID, Role.WORKER, None, clock.now())
            )
            uow.commit()
        yield SecWorld(
            app=app,
            clock=clock,
            owner=owner,
            viewer=app.client(actor=Actor(VIEWER_ID, PrincipalKind.HUMAN, "viewer"), surface=Surface.CLI),
            outsider=app.client(
                actor=Actor(OUTSIDER_ID, PrincipalKind.HUMAN, "outsider"), surface=Surface.CLI
            ),
            worker=app.client(actor=Actor(WORKER_ID, PrincipalKind.WORKER, "worker"), surface=Surface.WORKER),
            ws_a=ws_a,
            ws_b=ws_b,
            proj_a=proj_a,
            dsn=dsn,
        )
    finally:
        app.close()


def _check_security_invariants(w: SecWorld) -> None:
    called = False

    def forbidden_stream() -> Iterator[bytes]:
        nonlocal called
        called = True
        yield b"untrusted"

    with pytest.raises(SkmError) as viewer_err:
        w.viewer.upload_blob(w.ws_a, forbidden_stream(), size=9)
    assert viewer_err.value.code is ErrorCode.FORBIDDEN
    assert not called
    assert list(w.app.gateways.get(BlobStore).iter_objects(w.ws_a)) == []

    unknown_ws = WorkspaceId(UUID("01900000-0000-7000-8000-000000009999"))
    with pytest.raises(SkmError) as probe_err:
        w.outsider.upload_blob(unknown_ws, forbidden_stream(), size=9)
    assert probe_err.value.code is ErrorCode.FORBIDDEN
    assert probe_err.value.details.get("scope") is None

    denied = [r for r in audit_rows(w.app, w.dsn) if r[1] == "denied"]
    assert any(action == "artifacts.upload_blob" and actor == VIEWER_ID for action, _, actor, _ in denied)

    ref_a = w.owner.upload_blob(w.ws_a, [b"confidential alpha\n"], size=19)
    ref_b = w.outsider.upload_blob(w.ws_b, [b"foreign beta\n"], size=13)

    with pytest.raises(SkmError) as missing_err:
        dispatch_new(
            w.owner,
            add_file_dto(
                w.ws_a, w.proj_a, ref_a, staged_blob_id=UUID("01900000-0000-7000-8000-000000008888")
            ),
        )
    assert missing_err.value.code is ErrorCode.NOT_FOUND

    for tamper in ({"size": 20}, {"digest": "sha256:" + "f" * 64}):
        with pytest.raises(SkmError) as tamp_err:
            dispatch_new(w.owner, add_file_dto(w.ws_a, w.proj_a, ref_a, **tamper))
        assert tamp_err.value.code is ErrorCode.BLOB_DIGEST_MISMATCH

    with pytest.raises(SkmError) as cross_err:
        dispatch_new(w.owner, add_file_dto(w.ws_a, w.proj_a, ref_b, workspace_id=w.ws_a))
    assert cross_err.value.code is ErrorCode.FORBIDDEN

    added = dispatch_new(w.owner, add_file_dto(w.ws_a, w.proj_a, ref_a))
    fvid = FileVersionId(added.file_version_id)

    for unauthorized in (w.outsider, w.worker):
        with pytest.raises(SkmError) as unauth_err:
            unauthorized.open_file_version_content(fvid)
        assert unauth_err.value.code is ErrorCode.FORBIDDEN

    with w.app.uow_factory(_meta("4", w.clock.now())) as uow:
        artifacts.grant_access(
            uow,
            principal_id=WORKER_ID,
            version_ids=(fvid,),
            reason=GrantReason.ASSIGNMENT,
            ref="attempt-1",
            expires_at=w.clock.now() + timedelta(minutes=10),
            ids=Uuid7Generator(w.clock),
            now=w.clock.now(),
        )
        uow.commit()

    stream = w.worker.open_file_version_content(fvid)
    try:
        assert stream.read(12) == b"confidential"
        with w.app.uow_factory(_meta("5", w.clock.now())) as uow:
            revoked = artifacts.revoke_grants(
                uow, reason=GrantReason.ASSIGNMENT, ref="attempt-1", now=w.clock.now()
            )
            uow.commit()
        assert revoked == 1
        with pytest.raises(SkmError) as revoked_open:
            w.worker.open_file_version_content(fvid)
        assert revoked_open.value.code is ErrorCode.FORBIDDEN
        assert stream.read() == b" alpha\n"
    finally:
        stream.close()


def test_staged_blob_refs_and_content_authz_memory(tmp_path: Path) -> None:
    for world in _make_sec_world("memory", tmp_path):
        _check_security_invariants(world)


@pytest.mark.pg
def test_staged_blob_refs_and_content_authz_postgres(
    clean_test_database: TestDatabase, tmp_path: Path
) -> None:
    for world in _make_sec_world("postgres", tmp_path, clean_test_database.dsn):
        _check_security_invariants(world)
