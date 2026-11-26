"""Staging and content authorization over the complete ASGI middleware stack."""

import asyncio
import hashlib
import json
from uuid import UUID

import psycopg
import pytest

from integration.api.test_workspace_routes import application, created, workspace
from integration.api.test_workspace_routes import world as world
from security.api.harness import BASE, TestClient
from skm.adapters.memory.artifacts.state import artifacts_state
from skm.entrypoints.api.blobs import mount_blobs
from skm.kernel.ids import WorkspaceId
from skm.kernel.ports_uow import Surface
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.application.upload import bind_embedded_upload
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

OCTETS = "application/octet-stream"


@pytest.fixture
def client(world):
    core = world.core
    bus = core.bus
    upload, _ = bind_embedded_upload(
        core.uow_factory,
        bus._authorizer,
        bus._scopes,
        core.config,
        core.gateways,
        bus._clock,
        bus._ids,
        bus.dispatch,
        bus.ask,
    )
    api = application(world)
    mount_blobs(api, upload)
    with TestClient(api, base_url=BASE, headers=world.headers) as client:
        yield client


def upload_path(ws):
    return f"/api/v1/workspaces/{ws}/blobs"


def put_blob(client, ws, data, mime, key):
    return client.post(
        upload_path(ws),
        params={"media_type": mime},
        content=data,
        headers={
            "Content-Type": OCTETS,
            "Idempotency-Key": key,
            "X-Request-Id": "upload-correlation",
            "SKM-Expected-Digest": "sha256:" + hashlib.sha256(data).hexdigest(),
        },
    )


@pytest.mark.parametrize(
    ("mime", "content"), [("text/html", b"<p>document</p>"), ("image/svg+xml", b"<svg/>")]
)
def test_file_lifecycle_and_conditional_download(client, world, monkeypatch, mime, content):
    ws = workspace(client)
    seen = []
    upload = client.app.state.blob_uploader

    def observed_upload(**kwargs):
        seen.append(kwargs["meta"])
        return upload(**kwargs)

    monkeypatch.setattr(client.app.state, "blob_uploader", observed_upload)
    ref = created(put_blob(client, ws, content, mime, "upload-file"))
    assert created(put_blob(client, ws, content, mime, "upload-file")) == ref
    assert len(seen) == 2
    assert all(
        (m.surface, m.request_id, m.idempotency_key) == (Surface.API, "upload-correlation", "upload-file")
        for m in seen
    )
    assert set(ref) == {"staged_blob_id", "workspace_id", "digest", "size", "media_type"}
    assert ref["size"] == len(content)
    filename = "отчёт #1"
    body = {
        "title": "Document",
        "blob": ref,
        "origin": "upload",
        "original_filename": filename,
        "source": {"kind": "upload"},
        "declared_media_type": mime,
    }
    files = f"/api/v1/workspaces/{ws}/files"
    assert client.post(files, json={**body, "project_id": ws}).status_code == 422
    file = created(client.post(files, json=body))
    file_id, version_id = file["file_id"], file["file_version_id"]
    path = f"/api/v1/file-versions/{version_id}/content"
    response = client.get(path)
    assert (response.status_code, response.content) == (200, content)
    assert (
        response.headers["Content-Disposition"]
        == "attachment; filename*=UTF-8''%D0%BE%D1%82%D1%87%D1%91%D1%82%20%231"
    )
    assert response.headers["Content-Security-Policy"] == "sandbox"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Type"] == OCTETS
    assert response.headers["ETag"] == '"' + ref["digest"] + '"'
    obj = client.get(f"/api/v1/files/{file_id}").json()
    assert obj["current_version"]["file_version_id"] == version_id
    store = world.core.gateways.get(artifacts.BlobStore)

    def unexpected_open(location):
        pytest.fail("BlobStore.open ran on a conditional or unauthorized download")

    monkeypatch.setattr(store, "open", unexpected_open)
    cond = {"If-None-Match": response.headers["ETag"]}
    cached = client.get(path, headers=cond)
    assert (cached.status_code, cached.content) == (304, b"")
    assert client.get(path, headers={"If-None-Match": "W/" + response.headers["ETag"]}).status_code == 304
    other = workspace(client, "other")
    secret = created(client.post("/api/v1/tokens", json={"name": "other-workspace", "scope_id": other}))[
        "secret"
    ]
    denied = client.get(path, headers={**cond, "Authorization": "Bearer " + secret})
    assert denied.status_code == 403, denied.text


def upload_scope(path, headers):
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "state": {},
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        "server": ("127.0.0.1", 8765),
        "client": ("127.0.0.1", 10001),
    }


async def raw_post(app, path, headers, frames, observe):
    messages = iter(frames)
    sent = []

    async def receive():
        observe()
        frame = next(messages)
        if frame is None:
            return {"type": "http.disconnect"}
        body, more = frame
        return {"type": "http.request", "body": body, "more_body": more}

    async def send(message):
        sent.append(message)

    await app(upload_scope(path, headers), receive, send)
    return sent[0]["status"], json.loads(b"".join(m["body"] for m in sent[1:]))["code"]


def test_staging_stream_aborts_without_metadata_or_objects(client, world, request, tmp_path):
    ws = workspace(client)
    policy = client.put(
        f"/api/v1/config/entries/workspace:{ws}/artifacts.upload.max_bytes", json={"value": 1024}
    )
    assert policy.is_success, policy.text
    headers = {"Host": "127.0.0.1:8765", **world.headers, "Content-Type": OCTETS, "Idempotency-Key": "abort"}
    pg = world.backend is None
    store = world.core.gateways.get(artifacts.BlobStore)

    # Every receive in a valid request happens while the local adapter owns its .part.
    # A buffered boundary would consume all frames before this file exists.
    def observe():
        if pg:
            assert list(tmp_path.rglob("*.part"))

    cases = [
        ({}, [], 411, "LENGTH_REQUIRED"),
        ({"Content-Length": "1025"}, [], 413, "BLOB_TOO_LARGE"),
        ({"Content-Length": "3"}, [(b"a", True), (b"b", False)], 422, "BLOB_DIGEST_MISMATCH"),
        ({"Content-Length": "1"}, [(b"a", True), (b"b", False)], 422, "BLOB_DIGEST_MISMATCH"),
        ({"Content-Length": "3"}, [None], 422, "SCHEMA_INVALID"),
        ({"Content-Length": "3"}, [(b"a", True), None], 422, "SCHEMA_INVALID"),
        ({"Content-Length": "3"}, [(b"a", True), (b"b", True), None], 422, "SCHEMA_INVALID"),
        (
            {"Content-Length": "1", "SKM-Expected-Digest": "sha256:" + "0" * 64},
            [(b"a", False)],
            422,
            "BLOB_DIGEST_MISMATCH",
        ),
    ]
    for extra, frames, status, code in cases:
        assert client.portal.call(
            raw_post, client.app, upload_path(ws), {**headers, **extra}, frames, observe
        ) == (status, code)
        assert not list(tmp_path.rglob("*.part"))
        assert not list(store.iter_objects(WorkspaceId(UUID(ws))))

    async def cancel_during_upload():
        waiting = asyncio.Event()

        async def receive():
            observe()
            waiting.set()
            await asyncio.Future()

        async def send(message):
            pytest.fail(f"Unexpected response during cancellation: {message['type']}")

        task = asyncio.create_task(
            client.app(upload_scope(upload_path(ws), {**headers, "Content-Length": "100"}), receive, send)
        )
        await asyncio.wait_for(waiting.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)

    client.portal.call(cancel_during_upload)
    assert not list(tmp_path.rglob("*.part"))
    assert not list(store.iter_objects(WorkspaceId(UUID(ws))))
    if pg:
        with psycopg.connect(request.getfixturevalue("clean_test_database").dsn) as conn:
            assert conn.execute("SELECT count(*) FROM skm_artifacts.staged_blobs").fetchone() == (0,)
    else:
        assert not artifacts_state(world.backend.committed).staged
    no_key = client.post(upload_path(ws), content=b"a", headers={"Content-Type": OCTETS})
    assert (no_key.status_code, no_key.json()["code"]) == (422, "SCHEMA_INVALID")
    wrong_type = client.post(upload_path(ws), json={"data": "a"}, headers={"Idempotency-Key": "wrong-type"})
    assert wrong_type.status_code == 415


def test_project_file_version_cas_and_trash_restore(client):
    ws = workspace(client)
    project_path = f"/api/v1/workspaces/{ws}/projects"
    project = created(client.post(project_path, json={"slug": "archive", "title": "Archive"}))
    ref = created(put_blob(client, ws, b"one", "text/plain", "first-version"))
    file = created(
        client.post(
            f"/api/v1/projects/{project['project_id']}/files",
            json={
                "workspace_id": ws,
                "blob": ref,
                "origin": "upload",
                "source": {"kind": "upload"},
                "original_filename": "one.txt",
                "title": "Notes",
            },
        )
    )
    path = f"/api/v1/files/{file['file_id']}"
    versions = path + "/versions"
    second = created(put_blob(client, ws, b"two", "text/plain", "second-version"))
    version = {
        "blob": second,
        "source": {"kind": "upload"},
        "original_filename": "two.txt",
        "declared_media_type": "text/plain",
    }
    assert client.post(versions, json=version).status_code == 428
    tag = client.get(path).headers["ETag"]
    assert created(client.post(versions, json=version, headers={"If-Match": tag}))["version_no"] == 2
    assert [v["version_no"] for v in client.get(versions).json()["items"]] == [2, 1]
    tag = client.get(path).headers["ETag"]
    trashed = client.post(path + "/trash", json={"reason": "cleanup"}, headers={"If-Match": tag})
    assert trashed.status_code == 200, trashed.text
    restored = client.post(path + "/restore", json={}, headers={"If-Match": trashed.headers["ETag"]})
    assert restored.status_code == 200, restored.text
    assert restored.json()["state"] == "active"
