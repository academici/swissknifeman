"""Byte streaming, staged-blob consumption and authorization through each client."""

from collections.abc import Iterator
from hashlib import sha256
from typing import Any

import httpx
import pytest

from integration.artifacts.test_upload_flow import add_file_dto
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import FileVersionId
from skm.modules.artifacts import public as artifacts
from support.backend import ClientBackend, client_backend
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "client_backend", "pg_session", "test_database"]


def test_byte_stream_validation_content_read_and_keyed_consumption(client_backend: ClientBackend) -> None:
    side = client_backend
    owner = side.client()
    ws, project = side.seed.workspace_id, side.seed.project_id
    chunks = (b"contract\n", bytes(range(256)) * 512, b"\x00\xfftail")
    payload = b"".join(chunks)
    digest = "sha256:" + sha256(payload).hexdigest()
    for size, expected_digest in ((len(payload) - 1, digest), (len(payload), "sha256:" + "0" * 64)):
        with pytest.raises(SkmError) as mismatch:
            owner.upload_blob(ws, iter(chunks), size=size, expected_digest=expected_digest)
        assert mismatch.value.code is ErrorCode.BLOB_DIGEST_MISMATCH

    with pytest.raises(SkmError) as denied:
        side.client("viewer").upload_blob(ws, iter(chunks), size=len(payload))
    assert denied.value.code is ErrorCode.FORBIDDEN

    upload_replies: list[tuple[str, str]] = []
    yielded: list[bytes] = []

    def lose_first_upload_reply(response: httpx.Response) -> None:
        if response.request.method == "POST" and response.request.url.path.endswith("/blobs"):
            assert response.status_code == 201
            response.read()
            upload_replies.append(
                (response.request.headers["Idempotency-Key"], response.json()["staged_blob_id"])
            )
            if len(upload_replies) == 1:
                raise httpx.ReadTimeout("Simulated lost upload response", request=response.request)

    def one_shot_chunks() -> Iterator[bytes]:
        for chunk in chunks:
            yielded.append(chunk)
            yield chunk

    uploader = side.client(on_response=lose_first_upload_reply) if side.kind == "http-pg" else owner
    staged = uploader.upload_blob(
        ws,
        one_shot_chunks(),
        size=len(payload),
        expected_digest=digest,
        media_type="application/octet-stream",
    )
    assert yielded == list(chunks)
    assert (staged.workspace_id, staged.digest, staged.size, staged.media_type) == (
        ws,
        digest,
        len(payload),
        "application/octet-stream",
    )
    if side.kind == "http-pg":
        assert len(upload_replies) == 2
        assert upload_replies[0] == upload_replies[1]
        assert upload_replies[1][1] == str(staged.staged_blob_id)

    command = add_file_dto(ws, project, staged)
    key = "consume-upload"
    with side.lose_response(owner) as interrupted:
        interrupted.dispatch(command, idempotency_key=key)
    added: Any = owner.dispatch(command, idempotency_key=key)
    assert added.version_no == 1
    assert owner.dispatch(command, idempotency_key=key) == added
    with pytest.raises(SkmError) as consumed:
        owner.dispatch(command, idempotency_key="consume-again")
    assert consumed.value.code is ErrorCode.STAGED_BLOB_CONSUMED
    version = FileVersionId(added.file_version_id)
    viewer = side.client("viewer")
    view: Any = viewer.ask(artifacts.GetFileVersion(version))
    assert (view.digest, view.size_bytes) == (digest, len(payload))
    actual = sha256()
    with viewer.open_file_version_content(version) as stream:
        while chunk := stream.read(4096):
            actual.update(chunk)
    assert stream.closed
    assert "sha256:" + actual.hexdigest() == digest
    with pytest.raises(SkmError) as foreign:
        side.client("foreign").open_file_version_content(version)
    assert foreign.value.code is ErrorCode.FORBIDDEN
    assert [row.decision for row in side.audit_records("artifacts.add_file")] == ["allowed"]
