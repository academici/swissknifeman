"""Content replay through loopback and bounded private spool failures."""

from __future__ import annotations

import errno
import hashlib
import io
import os
import stat
import subprocess
import sys
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path
from threading import Event
from typing import Any, override
from uuid import uuid4

import httpx
import pytest

from contracts.execution.harness import exec_side as exec_side
from integration.api.test_worker_protocol import worker_api, worker_side
from skm.adapters.http_client.client import HttpSkmClient
from skm.bootstrap.host_services import build_host_storage
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import RouteTable, build_route_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, SkmError
from skm.kernel.ids import FileVersionId, WorkspaceId
from skm.platform.config.secrets import SecretRef, SecretValue
from skm.platform.fs.storage_budget import StorageBudget, StorageOwnerIdentity
from support.http_server import loopback_server
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "exec_side", "pg_session", "test_database", "worker_side"]

_WS = WorkspaceId(uuid4())
_BYTES = b"first line\n" * 8192
_DIGEST = "sha256:" + hashlib.sha256(_BYTES).hexdigest()


@cache
def _routes() -> RouteTable:
    return build_route_table(MODULE_IDS)


def _token(revealed: str = "upload-private-token") -> SecretValue:
    return SecretValue(SecretRef.parse("secret://env/SKM_API_TOKEN"), revealed)


def _reference(workspace: WorkspaceId = _WS) -> dict[str, str | int]:
    return {
        "staged_blob_id": str(uuid4()),
        "workspace_id": str(workspace),
        "digest": _DIGEST,
        "size": len(_BYTES),
        "media_type": "text/plain",
    }


class _Rupture(httpx.SyncByteStream):
    def __init__(self, stream: Iterable[bytes]) -> None:
        self.stream = stream

    @override
    def __iter__(self) -> Iterator[bytes]:
        yield next(iter(self.stream))
        raise httpx.WriteError("connection lost during upload")


class _FaultOnce(httpx.BaseTransport):
    def __init__(self, phase: str, mutate: Callable[[], None]) -> None:
        self.backend = httpx.HTTPTransport()
        self.phase, self.mutate = phase, mutate
        self.requests: list[httpx.Headers] = []
        self.committed: dict[str, Any] | None = None
        self.sent: bytes | None = None

    @override
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.headers)
        if len(self.requests) != 1:
            self.sent = request.read()
            return self.backend.handle_request(request)
        self.mutate()
        if self.phase == "before":
            raise httpx.ConnectError("connection lost before upload")
        if self.phase == "middle":
            assert isinstance(request.stream, httpx.SyncByteStream)
            request.stream = _Rupture(request.stream)
            return self.backend.handle_request(request)
        response = self.backend.handle_request(request)
        try:
            response.read()
            assert response.status_code == 201, response.text
            self.committed = response.json()
        finally:
            response.close()
        raise httpx.ReadError("connection lost after server commit")

    @override
    def close(self) -> None:
        self.backend.close()


@pytest.mark.parametrize("exec_side", [pytest.param("postgres", marks=pytest.mark.pg)], indirect=True)
@pytest.mark.parametrize("phase", ["before", "middle", "committed"])
@pytest.mark.parametrize("source", ["generator", "seekable"])
def test_loopback_upload_replays_exact_frozen_bytes(
    worker_side: Any,
    tmp_path: Path,
    phase: str,
    source: str,
) -> None:
    side, _, operator = worker_side
    root = tmp_path / "spool"
    upstream = io.BytesIO(_BYTES)
    consumed = False

    def generate() -> Iterator[bytes]:
        nonlocal consumed
        assert not consumed
        consumed = True
        yield _BYTES[:800]
        yield _BYTES[800:]

    def mutate() -> None:
        (spool,) = root.iterdir()
        assert stat.S_IMODE(spool.stat().st_mode) == 0o600
        assert spool.read_bytes() == _BYTES
        upstream.seek(0)
        upstream.write(b"x" * len(_BYTES))
        upstream.seek(0)

    fault = _FaultOnce(phase, mutate)
    with (
        loopback_server(
            lambda address: worker_api(
                side,
                settings={"api.bind": address},
            )
        ) as endpoint,
        httpx.Client(transport=fault) as http,
    ):
        client = HttpSkmClient(
            endpoint,
            _token(operator["Authorization"].removeprefix("Bearer ")),
            _routes(),
            spool_root=root,
            storage_budget=build_host_storage(tmp_path),
            min_free_bytes=0,
            http=http,
            sleeper=lambda _: None,
        )
        ref = client.upload_blob(
            side.ws,
            generate() if source == "generator" else upstream,
            size=len(_BYTES),
            media_type="text/plain",
        )
        assert fault.sent == _BYTES
        assert ref.size == len(_BYTES)
        assert ref.digest == _DIGEST
        assert ref.workspace_id == side.ws
        assert ref.media_type == "text/plain"
        if phase == "committed":
            assert ref.to_json() == fault.committed
        assert len(fault.requests) == 2
        first, second = fault.requests
        for name in ("Content-Length", "Idempotency-Key", "SKM-Expected-Digest"):
            assert first[name] == second[name]
        assert first["SKM-Expected-Digest"] == _DIGEST
        assert first["Content-Length"] == str(len(_BYTES))
        assert "Transfer-Encoding" not in first
        assert "Transfer-Encoding" not in second
    assert not list(root.iterdir())


def _budget(path: Path, free: int) -> StorageBudget:
    return StorageBudget(
        path / "locks",
        free_bytes=lambda _: free,
        identity=lambda: StorageOwnerIdentity("test-boot", os.getpid(), "test-start"),
        owner_alive=lambda _: True,
    )


def _client(
    root: Path,
    budget: StorageBudget,
    http: httpx.Client,
    *,
    min_free_bytes: int = 0,
) -> HttpSkmClient:
    return HttpSkmClient(
        "http://127.0.0.1",
        _token(),
        _routes(),
        spool_root=root,
        storage_budget=budget,
        min_free_bytes=min_free_bytes,
        http=http,
    )


def _no_network(request: httpx.Request) -> httpx.Response:
    pytest.fail(f"Unexpected HTTP request to {request.url.path}")


@pytest.mark.parametrize(
    ("size", "expected_digest", "code"),
    [
        (-1, None, ErrorCode.SCHEMA_INVALID),
        (104857601, None, ErrorCode.BLOB_TOO_LARGE),
        (len(_BYTES) + 1, None, ErrorCode.BLOB_DIGEST_MISMATCH),
        (len(_BYTES) - 1, None, ErrorCode.BLOB_DIGEST_MISMATCH),
        (len(_BYTES), "sha256:" + "0" * 64, ErrorCode.BLOB_DIGEST_MISMATCH),
    ],
)
def test_invalid_upload_never_reaches_http(
    tmp_path: Path,
    size: int,
    expected_digest: str | None,
    code: ErrorCode,
) -> None:
    root = tmp_path / "spool"
    with httpx.Client(transport=httpx.MockTransport(_no_network)) as http:
        budget = _budget(tmp_path, 1 << 20)
        with pytest.raises(SkmError) as caught:
            _client(root, budget, http).upload_blob(_WS, [_BYTES], size=size, expected_digest=expected_digest)
        assert caught.value.code == code
        assert not list(root.glob("*"))
        assert budget.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == 0


def test_failed_spool_inode_registration_releases_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    budget = _budget(tmp_path, 1 << 20)
    root = tmp_path / "spool"
    save = budget._save
    failed = False

    def fail_inode_write(entries: list[Any]) -> None:
        nonlocal failed
        if not failed and any(path.ino is not None for entry in entries for path in entry.paths):
            assert len(list(root.glob("*.tmp"))) == 1
            failed = True
            raise OSError(errno.ENOSPC, "no space for inode registration")
        save(entries)

    monkeypatch.setattr(budget, "_save", fail_inode_write)
    with (
        httpx.Client(transport=httpx.MockTransport(_no_network)) as http,
        pytest.raises(BackendUnavailable) as caught,
    ):
        _client(root, budget, http).upload_blob(_WS, [_BYTES], size=len(_BYTES))
    assert failed
    assert caught.value.details == {"reason": "disk_low"}
    assert not list(root.iterdir())
    assert budget.snapshot(root, min_free_bytes=0).reserved_bytes > len(_BYTES)
    reconciler = StorageBudget(
        tmp_path / "locks",
        free_bytes=lambda _: 1 << 20,
        identity=lambda: StorageOwnerIdentity("test-boot", os.getpid(), "test-start"),
        owner_alive=lambda _: False,
    )
    assert reconciler.reconcile(root).reserved_bytes == 0


def test_producer_failure_cleans_spool_before_network(tmp_path: Path) -> None:
    root = tmp_path / "spool"
    budget = _budget(tmp_path, 1 << 20)

    def fail() -> Iterator[bytes]:
        yield _BYTES[:3]
        raise RuntimeError("producer failed")

    with (
        httpx.Client(transport=httpx.MockTransport(_no_network)) as http,
        pytest.raises(RuntimeError, match="producer failed"),
    ):
        _client(root, budget, http).upload_blob(_WS, fail(), size=len(_BYTES))
    assert not list(root.iterdir())
    assert budget.snapshot(root, min_free_bytes=0).reserved_bytes == 0


@pytest.mark.parametrize(
    ("patch", "code"),
    [
        ({"digest": "sha256:" + "0" * 64}, ErrorCode.BLOB_DIGEST_MISMATCH),
        ({"size": 1}, ErrorCode.BLOB_DIGEST_MISMATCH),
        ({"workspace_id": str(uuid4())}, ErrorCode.INTERNAL_ERROR),
        ({"media_type": None}, ErrorCode.INTERNAL_ERROR),
        ({"media_type": ""}, ErrorCode.INTERNAL_ERROR),
        ({"size": True}, ErrorCode.INTERNAL_ERROR),
        ({"unexpected": 1}, ErrorCode.INTERNAL_ERROR),
    ],
)
def test_upload_validates_complete_ref_and_cleans_spool(
    tmp_path: Path,
    patch: dict[str, Any],
    code: ErrorCode,
) -> None:
    payload = {**_reference(), **patch}
    if patch == {"media_type": None}:
        del payload["media_type"]
    root = tmp_path / "spool"
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(201, json=payload))) as http,
        pytest.raises(SkmError) as caught,
    ):
        _client(root, _budget(tmp_path, 1 << 20), http).upload_blob(_WS, [_BYTES], size=len(_BYTES))
    assert caught.value.code == code
    assert not list(root.iterdir())


def test_concurrent_spools_share_reservations_and_floor(tmp_path: Path) -> None:
    entered, release = Event(), Event()
    spool = tmp_path / "spool"
    free = 2 * len(_BYTES)
    floor = len(_BYTES) // 2

    def produce() -> Iterator[bytes]:
        entered.set()
        assert release.wait(6)
        yield _BYTES

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.read() == _BYTES
        return httpx.Response(201, json=_reference())

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as first_http,
        httpx.Client(transport=httpx.MockTransport(_no_network)) as second_http,
        ThreadPoolExecutor(1) as pool,
    ):
        first = _client(spool, _budget(tmp_path, free), first_http, min_free_bytes=floor)
        second = _client(spool, _budget(tmp_path, free), second_http)
        pending = pool.submit(first.upload_blob, _WS, produce(), size=len(_BYTES))
        try:
            assert entered.wait(6)
            with pytest.raises(BackendUnavailable) as caught:
                second.upload_blob(_WS, [_BYTES], size=len(_BYTES))
            assert caught.value.details == {"reason": "disk_low"}
        finally:
            release.set()
        assert pending.result(timeout=6).digest == _DIGEST
        assert not list(spool.iterdir())
        assert _budget(tmp_path, free).snapshot(spool, min_free_bytes=0).reserved_bytes == 0


def test_empty_upload_sends_explicit_zero_length(tmp_path: Path) -> None:
    digest = "sha256:" + hashlib.sha256(b"").hexdigest()

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["Content-Length"] == "0"
        assert request.headers["SKM-Expected-Digest"] == digest
        assert request.read() == b""
        return httpx.Response(201, json={**_reference(), "size": 0, "digest": digest})

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = _client(tmp_path / "spool", _budget(tmp_path, 1 << 20), http)
        assert client.upload_blob(_WS, [], size=0).digest == digest


def test_upload_recovers_spool_of_dead_process(tmp_path: Path) -> None:
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os
import sys
from pathlib import Path
from uuid import uuid4

from skm.adapters.http_client.client import HttpSkmClient
from skm.bootstrap.host_services import build_host_storage
from skm.entrypoints.api.routing import build_route_table
from skm.platform.config.secrets import SecretRef, SecretValue

root = Path(sys.argv[1])
client = HttpSkmClient("http://127.0.0.1", SecretValue(SecretRef.parse("secret://env/TOKEN"), "test-secret"),
                       build_route_table(()), spool_root=root / "spool",
                       storage_budget=build_host_storage(root), min_free_bytes=0)
def producer():
    yield b"partial"
    os._exit(27)
client.upload_blob(uuid4(), producer(), size=100)
""",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        timeout=15,
    )
    assert child.returncode == 27, child.stderr
    spool = tmp_path / "spool"
    (abandoned,) = spool.iterdir()
    assert abandoned.read_bytes() == b"partial"

    def handle(_: httpx.Request) -> httpx.Response:
        assert not abandoned.exists()
        return httpx.Response(201, json=_reference())

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        budget = build_host_storage(tmp_path)
        assert _client(spool, budget, http).upload_blob(_WS, [_BYTES], size=len(_BYTES)).digest == _DIGEST
        assert budget.snapshot(spool, min_free_bytes=0).reserved_bytes == 0
    assert not list(spool.iterdir())


def test_download_reads_lazily_and_close_releases_response(tmp_path: Path) -> None:
    file_version_id = FileVersionId(uuid4())
    parts: list[bytes] = []
    closed = False

    class Body(httpx.SyncByteStream):
        @override
        def __iter__(self) -> Iterator[bytes]:
            for data in (b"abc", b"def"):
                parts.append(data)
                yield data

        @override
        def close(self) -> None:
            nonlocal closed
            closed = True

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/api/v1/file-versions/{file_version_id}/content"
        return httpx.Response(200, stream=Body())

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = _client(tmp_path / "spool", _budget(tmp_path, 1 << 20), http)
        with client.open_file_version_content(file_version_id) as stream:
            assert parts == []
            assert stream.read(2) == b"ab"
            assert parts == [b"abc"]
            assert not closed
        assert closed
        assert parts == [b"abc"]
