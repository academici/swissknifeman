"""A known artifact identifier does not authorize opening the stored bytes (S18)."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from contracts.execution.harness import ExecSide
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.test_step_notes import owned_agent
from integration.api.test_artifacts_routes import client as client
from integration.api.test_artifacts_routes import put_blob
from integration.api.test_worker_protocol import bearer, worker_api
from integration.api.test_worker_protocol import worker_side as worker_side
from integration.api.test_workspace_routes import created, workspace
from integration.api.test_workspace_routes import world as world
from security.api.harness import BASE, TestClient, World
from skm.adapters.memory.uow import InMemoryBackend, InMemoryUowFactory
from skm.bootstrap.composition import App
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import FileVersionId
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.domain.access_grant import GrantReason
from skm.modules.artifacts.ports import AccessGrantRepository, BlobRepository, FileVersionRepository
from support.pg import TestDatabase, table_counts
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database


def files_under(root: Path) -> dict[Path, object]:
    snapshot: dict[Path, object] = {}
    for path in root.rglob("*"):
        key = path.relative_to(root)
        if path.is_symlink():
            snapshot[key] = path.readlink()
        elif path.is_file():
            info = path.stat()
            snapshot[key] = (path.read_bytes(), info.st_mode, info.st_mtime_ns)
        elif path.is_dir():
            snapshot[key] = path.stat().st_mode
    return snapshot


def assert_private_output(output: object, *private: str) -> None:
    rendered = str(output)
    for value in private:
        if value in rendered:
            pytest.fail("private fixture data reached the response or diagnostics", pytrace=False)


def audit_snapshot(dsn: str | None, backend: InMemoryBackend | None) -> dict[UUID, tuple[str, str, object]]:
    if dsn is None:
        assert backend is not None
        return {row.id: (row.action, row.decision, row) for row in backend.committed.core.audit}
    with psycopg.connect(dsn) as conn:
        return {
            audit_id: (action, decision, row)
            for audit_id, action, decision, row in conn.execute(
                "SELECT id, action, decision, to_jsonb(t) FROM skm_core.audit_records AS t"
            )
        }


def assert_denied_audit(
    before: dict[UUID, tuple[str, str, object]],
    after: dict[UUID, tuple[str, str, object]],
    expected: tuple[str, ...],
    *private: str,
) -> None:
    added = [after[key] for key in after.keys() - before.keys()]
    assert_private_output(added, *private)
    assert {key: after[key] for key in after.keys() & before.keys()} == before
    assert sorted((action, decision) for action, decision, _ in added) == sorted(
        (action, "denied") for action in expected
    )


class _NoBlobOpen:
    def __init__(self, store: artifacts.BlobStore) -> None:
        self.store = store
        self.opened = 0

    def open(self, *_args: object, **_kwargs: object) -> None:
        self.opened += 1
        pytest.fail("a denied request reached BlobStore.open", pytrace=False)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.store, name)


def _memory_tables(backend: InMemoryBackend) -> dict[str, Any]:
    committed = backend.committed
    tables: dict[str, Any] = {}
    for module, state in (("core", committed.core), *committed.modules.items()):
        if is_dataclass(state) and not isinstance(state, type):
            for field in fields(state):
                if field.name not in {"readonly", "clock"} and (module, field.name) != ("core", "audit"):
                    tables[f"{module}.{field.name}"] = getattr(state, field.name)
    return tables


def _memory_counts(tables: dict[str, Any]) -> dict[str, int]:
    return {
        name: len(rows)
        for name, rows in tables.items()
        if isinstance(rows, (dict, list, tuple, set, frozenset))
    }


def _pg_state(dsn: str, schemas: tuple[str, ...]) -> dict[tuple[str, str], tuple[int, str]]:
    snapshot: dict[tuple[str, str], tuple[int, str]] = {}
    with psycopg.connect(dsn) as conn:
        for name in ("core", *schemas):
            schema = f"skm_{name}"
            for table, count in table_counts(conn, schema).items():
                if table == "audit_records":
                    # RBAC denials append audit evidence checked separately.
                    continue
                query = sql.SQL(
                    "SELECT md5(COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t))::text, '[]')) "
                    "FROM {} AS t"
                ).format(sql.Identifier(schema, table))
                row = conn.execute(query).fetchone()
                assert row is not None
                snapshot[schema, table] = (count, str(row[0]))
    return snapshot


@contextmanager
def denial_checks(
    app: App,
    root: Path,
    *,
    dsn: str | None,
    schemas: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
    private: tuple[str, ...],
    audit: tuple[str, ...] = (),
) -> Iterator[Callable[[object], None]]:
    before_fs = files_under(root)
    factory = app.uow_factory
    if dsn is None:
        assert isinstance(factory, InMemoryUowFactory)
        before_state = _memory_tables(factory._backend)
        before_counts = _memory_counts(before_state)
    else:
        before_pg = _pg_state(dsn, schemas)
    backend = factory._backend if isinstance(factory, InMemoryUowFactory) else None
    before_audit = audit_snapshot(dsn, backend)

    gateways = app.gateways
    assert isinstance(gateways, GatewayTable)
    entries = cast("dict[type[object], object]", gateways.entries)
    store = gateways.get(artifacts.BlobStore)
    probe = _NoBlobOpen(store)
    entries[artifacts.BlobStore] = probe
    capsys.readouterr()
    try:
        yield lambda output: assert_private_output(output, *private)
    finally:
        entries[artifacts.BlobStore] = store

    assert_private_output(capsys.readouterr(), *private)
    assert_denied_audit(before_audit, audit_snapshot(dsn, backend), audit, *private)
    assert probe.opened == 0
    assert files_under(root) == before_fs
    if dsn is None:
        assert isinstance(factory, InMemoryUowFactory)
        after_state = _memory_tables(factory._backend)
        assert _memory_counts(after_state) == before_counts
        assert after_state == before_state
    else:
        assert _pg_state(dsn, schemas) == before_pg


@pytest.mark.parametrize("credential", ["foreign", "without-file-read", "revoked"])
def test_known_blob_identifiers_cannot_open_bytes(
    client: TestClient,
    world: World,
    request: pytest.FixtureRequest,
    tmp_path: Path,
    credential: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    own, foreign = workspace(client, "reader"), workspace(client, "private")
    private = "private-blob-bytes-5122"
    staged = created(put_blob(client, foreign, private.encode(), "text/plain", "private-blob"))
    file = created(
        client.post(
            f"/api/v1/workspaces/{foreign}/files",
            json={
                "title": "private-file-title-6947",
                "blob": staged,
                "origin": "upload",
                "original_filename": "private-file.txt",
                "source": {"kind": "upload"},
                "declared_media_type": "text/plain",
            },
        )
    )
    version = file["file_version_id"]
    path = f"/api/v1/file-versions/{version}/content"
    allowed = client.get(path)
    assert (allowed.status_code, allowed.text) == (200, private)
    with world.core.uow_factory(world.meta(), readonly=True) as uow:
        row = uow.repo(FileVersionRepository).get(FileVersionId(UUID(version)))
        blob = uow.repo(BlobRepository).get(row.blob_id)
        (location,) = uow.repo(BlobRepository).locations(blob.id)

    token = created(
        client.post(
            "/api/v1/tokens",
            json={
                "name": f"blob-{credential}",
                "scope_id": own if credential == "foreign" else foreign,
                "permissions": ["file.read"] if credential != "without-file-read" else ["project.read"],
            },
        )
    )
    if credential == "revoked":
        revoked = client.post(f"/api/v1/tokens/{token['token_id']}/revoke", json={})
        assert revoked.is_success, revoked.text
    dsn = (
        None
        if world.backend is not None
        else cast("TestDatabase", request.getfixturevalue("clean_test_database")).dsn
    )
    headers = {"Authorization": f"Bearer {token['secret']}"}
    probes = [
        (path, {}),
        (path, {"blob_id": str(blob.id), "sha256": blob.digest.value, "storage_key": location.storage_key}),
        (f"/api/v1/file-versions/{blob.id}/content", {}),
        (f"/api/v1/file-versions/{uuid4()}/content", {"sha256": blob.digest.value}),
    ]
    markers = (private, "private-file-title-6947", location.storage_key, token["secret"], world.secret)
    problems = []
    for target, params in probes:
        with denial_checks(
            world.core,
            tmp_path,
            dsn=dsn,
            schemas=("access", "artifacts", "workspace"),
            capsys=capsys,
            private=markers,
            audit=() if credential == "revoked" else ("artifacts.open_file_version_content",),
        ) as check:
            response = client.get(target, params=params, headers=headers)
            check((response.text, response.headers))
        assert response.status_code in ({401} if credential == "revoked" else {403, 404})
        assert response.json()["code"] in (
            {"UNAUTHENTICATED"} if credential == "revoked" else {"FORBIDDEN", "NOT_FOUND"}
        )
        problem = response.json()
        problems.append((response.status_code, problem["code"], problem["details"]))
        assert "ETag" not in response.headers
        assert "Content-Disposition" not in response.headers
    assert problems == [problems[0]] * len(probes)


def test_assignment_cannot_open_known_version_after_grant_revocation(
    worker_side: tuple[ExecSide, dict[str, str], dict[str, str]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    side, worker, owner = worker_side
    _, _, _, claim, _, _, runtime, _, secret = owned_agent(side)
    ref, other_ref = str(claim["assignment_id"]), str(side.new_id())
    principal_id = runtime._actor.principal_id
    version_id = side.fv2
    path = f"/api/v1/file-versions/{version_id}/content"

    with side.uow() as uow:
        for assignment_ref in (ref, other_ref):
            assert (
                artifacts.grant_access(
                    uow,
                    principal_id=principal_id,
                    version_ids=(version_id,),
                    reason=GrantReason.ASSIGNMENT,
                    ref=assignment_ref,
                    expires_at=side.clock.now() + timedelta(seconds=30),
                    now=side.clock.now(),
                    ids=side.ids,
                )
                == 1
            )
        row = uow.repo(FileVersionRepository).get(version_id)
        blob = uow.repo(BlobRepository).get(row.blob_id)
        (location,) = uow.repo(BlobRepository).locations(blob.id)
        uow.commit()

    with TestClient(worker_api(side), base_url=BASE) as api:
        allowed = api.get(path, headers=bearer(secret))
        assert (allowed.status_code, allowed.content) == (200, b"Artifact 2\n")
        with side.uow() as uow:
            now = side.clock.now()
            assert artifacts.revoke_grants(uow, reason=GrantReason.ASSIGNMENT, ref=ref, now=now) >= 1
            grants = uow.repo(AccessGrantRepository)
            assert grants.active_for(principal_id, version_id, now, ref=ref) is None
            assert grants.active_for(principal_id, version_id, now, ref=other_ref) is not None
            uow.commit()
        markers = (
            "Artifact 2",
            location.storage_key,
            blob.digest.value,
            secret,
            worker["Authorization"][7:],
            owner["Authorization"][7:],
        )
        for extra in ({}, {"If-None-Match": allowed.headers["ETag"]}):
            with denial_checks(
                side.app,
                tmp_path,
                dsn=side.dsn,
                schemas=("access", "artifacts", "execution"),
                capsys=capsys,
                private=markers,
                audit=("artifacts.open_file_version_content",),
            ) as check:
                response = api.get(path, headers={**bearer(secret), **extra})
                check((response.text, response.headers))
            assert (response.status_code, response.json()["code"]) == (403, "FORBIDDEN")
            assert "ETag" not in response.headers
            assert "Content-Disposition" not in response.headers
