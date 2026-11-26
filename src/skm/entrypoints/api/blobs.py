"""ASGI byte routes. The host supplies its bound embedded uploader at composition time."""

import asyncio
import re
from collections.abc import Iterator
from typing import Any, BinaryIO, cast, override
from urllib.parse import quote
from uuid import UUID

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from skm.application_bus.client import BlobUploader, StagedBlobRef
from skm.bootstrap.composition import App
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, error_for
from skm.kernel.ids import WorkspaceId, parse_uuid
from skm.modules.artifacts import public as artifacts

from .app import call_bus
from .auth import request_auth_basis
from .etag import encode_etag, parse_if_none_match
from .middleware import BodyPolicy, HTTPBoundary
from .request_context import request_meta

__all__ = ["mount_blobs"]

_UPLOAD = "/api/v1/workspaces/{workspace_id}/blobs"
_CONTENT = "/api/v1/file-versions/{file_version_id}/content"
_OCTETS = "application/octet-stream"
_POLICY = BodyPolicy("POST", _UPLOAD, "artifacts.upload.max_bytes", _OCTETS, length_required=True)
_CHUNK = 64 * 1024


def _path_id(request: Request, name: str) -> UUID:
    try:
        return parse_uuid(request.path_params[name])
    except ValueError:
        raise error_for(ErrorCode.SCHEMA_INVALID, f"Invalid {name}") from None


def _length(request: Request) -> int:
    lengths = request.headers.getlist("content-length")
    if not lengths:
        raise error_for(ErrorCode.LENGTH_REQUIRED, "Content-Length is required")
    if len(lengths) != 1 or not re.fullmatch(r"[0-9]+", lengths[0]):
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid Content-Length")
    digits = lengths[0].lstrip("0") or "0"
    if len(digits) > 19:
        raise error_for(ErrorCode.BLOB_TOO_LARGE, "Upload exceeds maximum blob size")
    return int(digits)


class _BlobBoundary(HTTPBoundary):
    @override
    async def _body(self, request: Request, receive: Receive, policy: BodyPolicy) -> bytes:
        if policy != _POLICY:
            return await super()._body(request, receive, policy)
        # Keep the transport stream for stage(). The ordinary boundary still runs its
        # media type, version, health, bearer and idempotency checks before dispatch.
        request.state.upload_size = _length(request)
        request.state.upload_receive = receive
        return b""


class _UploadStream:
    """The store pulls frames from the ASGI loop, with at most one outstanding receive."""

    def __init__(self, receive: Receive, size: int) -> None:
        self.receive = receive
        self.size = size
        self.loop = asyncio.get_running_loop()
        self.pending: asyncio.Task[Message] | None = None
        self.closed = False

    async def _read(self) -> Message:
        if self.closed:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Upload interrupted")
        self.pending = asyncio.current_task()
        try:
            return await self.receive()
        finally:
            self.pending = None

    def close(self) -> None:
        # Only the event loop accesses pending/closed, including late reads after cancellation.
        self.closed = True
        if self.pending is not None:
            self.pending.cancel()

    def __iter__(self) -> Iterator[bytes]:
        received = 0
        while True:
            message = asyncio.run_coroutine_threadsafe(self._read(), self.loop).result()
            if message["type"] == "http.disconnect":
                raise error_for(ErrorCode.SCHEMA_INVALID, "Upload interrupted")
            data: bytes = message.get("body", b"")
            received += len(data)
            more = message.get("more_body", False)
            if received > self.size or (not more and received != self.size):
                raise error_for(ErrorCode.BLOB_DIGEST_MISMATCH, "Content-Length does not match upload size")
            if data:
                yield data
            if not more:
                return


async def _upload(request: Request) -> JSONResponse:
    meta = request_meta(request)
    if meta.idempotency_key is None:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Idempotency-Key is required")
    digests = request.headers.getlist("skm-expected-digest")
    if len(digests) > 1:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Multiple SKM-Expected-Digest headers")
    uploader: BlobUploader = request.app.state.blob_uploader
    size: int = request.state.upload_size
    workspace_id = WorkspaceId(_path_id(request, "workspace_id"))
    basis = request_auth_basis(request)
    stream = _UploadStream(request.state.upload_receive, size)
    worker = asyncio.create_task(
        run_in_threadpool(
            uploader,
            actor=basis.actor,
            meta=meta,
            workspace_id=workspace_id,
            stream=stream,
            size=size,
            expected_digest=digests[0] if digests else None,
            media_type=request.query_params.get("media_type", _OCTETS),
            auth_basis=basis,
        )
    )
    try:
        staged = await asyncio.shield(worker)
    except asyncio.CancelledError:
        stream.close()
        # Let stage discard its partial file before releasing the request.
        await asyncio.gather(worker, return_exceptions=True)
        raise
    ref = StagedBlobRef(
        staged.staged_blob_id, WorkspaceId(staged.workspace_id), staged.digest, staged.size, staged.media_type
    )
    return JSONResponse(ref.to_json(), status_code=201)


class _Download(StreamingResponse):
    def __init__(self, file: BinaryIO, headers: dict[str, str]) -> None:
        self.file = file
        super().__init__(iter(lambda: file.read(_CHUNK), b""), headers=headers)

    @override
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.file.close()


async def _content(request: Request) -> Response:
    version_id = _path_id(request, "file_version_id")
    query = artifacts.OpenFileVersionContent(file_version_id=version_id)
    view = cast("artifacts.OpenFileVersionContentView", await call_bus(request, query))
    tag = encode_etag(view.digest)
    conditions = request.headers.getlist("if-none-match")
    if len(conditions) > 1:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Multiple If-None-Match headers")
    condition = conditions[0] if conditions else None
    # If-None-Match uses weak comparison even for our strong content digest.
    if condition is not None and condition.startswith('W/"'):
        condition = condition.removeprefix("W/")
    conditional = parse_if_none_match(condition)
    request.state.blob_download = True
    headers = {
        "ETag": tag,
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(view.filename, safe=""),
        "Content-Security-Policy": "sandbox",
        "X-Content-Type-Options": "nosniff",
    }
    if conditional in {"*", tag}:
        return Response(status_code=304, headers=headers)
    core: App = request.app.state.core
    store = core.gateways.get(artifacts.BlobStore)
    try:
        file = await run_in_threadpool(store.open, view.location)
    except NotFound:
        raise error_for(ErrorCode.FILE_VERSION_NOT_READY, "File version content is unavailable") from None
    mime = view.media_type.split(";", 1)[0].strip().lower()
    headers["Content-Type"] = (
        _OCTETS if mime in {"text/html", "application/xhtml+xml", "image/svg+xml"} else view.media_type
    )
    headers["Content-Length"] = str(view.size_bytes)
    return _Download(file, headers)


class _ContentSandbox:
    """Apply the download CSP after the shared RequestContext sets the site's default CSP."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def with_sandbox(message: Message) -> None:
            if message["type"] == "http.response.start" and scope["state"].get("blob_download"):
                MutableHeaders(scope=message)["Content-Security-Policy"] = "sandbox"
            await send(message)

        await self.app(scope, receive, with_sandbox)


def mount_blobs(api: Starlette, upload: BlobUploader) -> None:
    """Install on create_app's API before startup when artifacts is enabled."""
    if api.middleware_stack is not None:
        raise RuntimeError("Mount blob routes before ASGI startup")
    if api.state.health.schema_error is not None:
        return
    for index, middleware in enumerate(api.user_middleware):
        if middleware.cls is HTTPBoundary:
            options = dict(cast("dict[str, Any]", middleware.kwargs))
            options["policies"] = (_POLICY, *options["policies"])
            api.user_middleware[index] = Middleware(_BlobBoundary, **options)
            break
    else:
        raise ValueError("Blob routes require the shared HTTP admission boundary")
    api.add_middleware(_ContentSandbox)
    api.state.blob_uploader = upload
    api.router.routes.extend(
        (
            Route(_UPLOAD, _upload, methods=["POST"], name="artifacts_upload_blob"),
            Route(_CONTENT, _content, methods=["GET"], name="artifacts_open_file_version_content"),
        )
    )
