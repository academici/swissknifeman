"""Standalone HTTP implementation of the host-side client protocol."""

from __future__ import annotations

import errno
import hashlib
import io
import os
import re
import ssl
import stat
import time
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from contextlib import closing, contextmanager, suppress
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast, override
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx

from skm.application_bus.client import QueryMeta, SkmClient, StagedBlobRef
from skm.entrypoints.api.etag import encode_etag
from skm.entrypoints.api.routing import Route, RouteTable, encode_scope
from skm.kernel.clock import Monotonic
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, InternalError, SkmError, ValidationFailed
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import FileVersionId, ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.artifacts.generated.commands import AddFileDefsStagedBlobRef
from skm.modules.settings.generated.views import explain_report_from_json
from skm.platform.config.secrets import SecretValue
from skm.platform.fs.storage_budget import StorageBudget
from skm.platform.logging.logger import get_logger
from skm.platform.process.identity import ProcessIdentity, identity_of, is_same_process
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import SchemaValidator
from skm.platform.system_clock import SystemClock, SystemMonotonic
from skm.platform.system_ids import Uuid7Generator

from .auth import BearerHeaders
from .events import read_events
from .retry import TRANSPORT_FAILURES, idempotency_key, send_before_deadline, send_with_retry, transport_error
from .spool import BoundedLocalSpool, HistoricalObservation

__all__ = ["HttpSkmClient"]

_BLOCK_BYTES = 1 << 16
_OCTETS = "application/octet-stream"
_CREATE_ONLY = {"settings.set_value", "settings.unset_value"}
_SPOOL = re.compile(r"upload-([0-9a-f-]{36})-([1-9][0-9]*)-([0-9]+)-[0-9a-f]{32}\.tmp")
_LOG = get_logger("adapters.http_client")


def _heartbeat_payload(operation: str, fields: Mapping[str, Any], host_id: UUID | None) -> JsonObject | None:
    if operation == "workspace.record_worker_heartbeat":
        claim = fields
    elif operation == "execution.renew_lease":
        claim = fields["claim"]
    else:
        return None
    # The claim's fence belongs to one assignment. The spool fence covers the local queue.
    return {
        "operation": operation,
        "host_id": str(host_id) if host_id is not None else None,
        "worker_id": claim.get("worker_id"),
        "attempt_id": claim.get("attempt_id"),
    }


def _record_heartbeat_observation(observation: HistoricalObservation) -> None:
    operation = observation.payload.get("operation", "workspace.record_worker_heartbeat")
    observed_at = observation.observed_at.astimezone(UTC).isoformat(timespec="microseconds")
    _LOG.info(
        "worker.heartbeat.observed",
        observed_at=observed_at.replace("+00:00", "Z"),
        operation=operation,
        host_id=observation.payload.get("host_id"),
        worker_id=observation.payload.get("worker_id"),
        attempt_id=observation.payload.get("attempt_id"),
    )


@cache
def _blob_schema() -> SchemaValidator:
    return SchemaValidator(
        {"$ref": "urn:skm:artifacts:defs:v1#/$defs/staged_blob_ref"},
        SchemaRegistry.load_default().dialect_free_registry(),
        dialect_free_inputs=True,
    )


def _member(fields: Mapping[str, Any], name: str) -> Any:
    value: Any = fields
    for part in name.split("."):
        value = cast("Mapping[str, Any]", value).get(part) if isinstance(value, Mapping) else None
    return value


def _pop_member(fields: dict[str, Any], name: str) -> Any:
    root, _, nested = name.partition(".")
    if not nested:
        return fields.pop(root, None)
    child = dict(fields[root])
    fields[root] = child
    return _pop_member(child, nested)


def _wire_value(value: Any, field: str) -> str:
    if field == "scope" and isinstance(value, dict):
        return encode_scope(cast("dict[str, Any]", value))
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) in (str, int, float):
        return str(value)
    raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Unsupported HTTP parameter")


def _query_parameters(route: Route, fields: Mapping[str, Any]) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = []
    mapped: set[str] = set()
    for name, target in route.query_params.items():
        if target in mapped:
            continue
        mapped.add(target)
        value = _member(fields, target)
        if value is None:
            continue
        if name == "include" and target == "include_tree":
            if value:
                params.append((name, "tree"))
            continue
        if isinstance(value, list):
            encoded = [_wire_value(item, target) for item in cast("list[Any]", value)]
            if route.bus_name == "settings.explain_config":
                if name == "key" and len(encoded) != 1:
                    raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Expected one configuration key")
                if encoded:
                    params.append((name, ",".join(encoded)))
            elif target == "edge_types" and not encoded:
                params.append((name, ""))
            else:
                params.extend((name, item) for item in encoded)
        else:
            params.append((name, _wire_value(value, target)))
    return params


def _matches_body(route: Route, fields: Mapping[str, Any]) -> bool:
    if route.bus_name == "planning.save_draft":
        body_field = {"PUT": "document", "PATCH": "merge_patch", "POST": "changes"}[route.method]
        return fields.get(body_field) is not None
    if route.bus_name == "artifacts.add_file":
        return ("project_id" in route.path_params) == (fields.get("project_id") is not None)
    if route.bus_name == "integrations.record_projection_applied":
        create = route.operation_id == "integrations_create_projection"
        return create == (fields.get("base_row_version") is None)
    if route.bus_name == "settings.explain_config":
        return (route.operation_id == "settings_explain_config") == (fields.get("detail") == "full")
    return True


def _select_route(routes: tuple[Route, ...], fields: Mapping[str, Any]) -> Route:
    # Otherwise equivalent aliases use RouteTable's declaration order.
    for route in routes:
        if _matches_body(route, fields) and all(
            _member(fields, field) is not None for field in route.path_params.values()
        ):
            return route
    raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "DTO has no matching HTTP route")


def _receipt_deadline(headers: httpx.Headers) -> datetime | None:
    try:
        (stamp,) = headers.get_list("SKM-Server-Time")
        (retention,) = headers.get_list("SKM-Idempotency-Retention-Seconds")
        if not re.fullmatch(r"[1-9][0-9]{0,8}", retention):
            return None
        observed_at = datetime.fromisoformat(stamp)
        if observed_at.tzinfo is None:
            return None
        return observed_at.astimezone(UTC) + timedelta(seconds=int(retention))
    except (ValueError, OverflowError):
        return None


def _decode_result(route: Route, response: httpx.Response) -> object:
    if route.path.endswith(".md"):
        try:
            markdown = response.content.decode("utf-8")
        except UnicodeError:
            raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid HTTP Markdown") from None
        if not response.headers.get("content-type", "").startswith("text/markdown"):
            raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid HTTP Markdown response type")
        return {
            "markdown": markdown,
            "digest": "sha256:" + hashlib.sha256(response.content).hexdigest(),
        }
    try:
        raw = response.json()
        if route.bus_name == "settings.explain_config":
            # The report's bus wrapper exposes to_json only.
            return route.result_type(report=explain_report_from_json(raw))
        return route.result_type.from_json(raw)
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid HTTP result")


def _private_spool_root(root: Path, budget: StorageBudget) -> ProcessIdentity:
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "Upload spool directory must be private")
    owner = identity_of(os.getpid())
    if owner is None or owner.boot_id is None or owner.start_ticks is None:
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "Upload spool owner identity unavailable")
    for path in root.glob("upload-*.tmp"):
        match = _SPOOL.fullmatch(path.name)
        if match is None:
            continue
        previous = ProcessIdentity(int(match[2]), int(match[3]), match[1])
        try:
            still_alive = previous.boot_id == owner.boot_id and is_same_process(previous)
        except (OSError, ValueError):
            continue  # Unknown process ownership is not evidence of a crash.
        if not still_alive:
            with suppress(FileNotFoundError):
                item = path.lstat()
                if stat.S_ISREG(item.st_mode) and item.st_uid == os.geteuid() and not item.st_mode & 0o077:
                    path.unlink()
    budget.reconcile(root)
    return owner


class _ContentStream(io.RawIOBase):
    def __init__(self, response: httpx.Response) -> None:
        super().__init__()
        self._response = response
        self._chunks = response.iter_bytes()
        self._pending = memoryview(b"")

    @override
    def readable(self) -> bool:
        return True

    @override
    def readinto(self, buffer: Any) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed content")
        target = memoryview(buffer).cast("B")
        if not target:
            return 0
        interrupted = False
        if not self._pending:
            try:
                self._pending = memoryview(next(self._chunks, b""))
            except TRANSPORT_FAILURES:
                interrupted = True
        if interrupted:
            self.close()
            raise transport_error(retryable=False)
        size = min(len(target), len(self._pending))
        target[:size] = self._pending[:size]
        self._pending = self._pending[size:]
        return size

    @override
    def close(self) -> None:
        if not self.closed:
            try:
                self._response.close()
            finally:
                super().close()


class _Sleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


class HttpSkmClient(SkmClient):
    """A synchronous client over the shared wire declarations."""

    def __init__(  # noqa: PLR0913 -- explicit transport and local storage policy
        self,
        base_url: str,
        token: SecretValue,
        routes: RouteTable | Callable[[type[object]], RouteTable],
        *,
        spool_root: Path,
        storage_budget: StorageBudget,
        min_free_bytes: int,
        timeout_seconds: float = 30.0,
        max_attempts: int = 4,
        clock: Monotonic | None = None,
        sleeper: _Sleeper | Callable[[float], None] = time.sleep,
        http: httpx.Client | None = None,
        max_upload_bytes: int = 104857600,
        run_scope_id: UUID | None = None,
        verify: ssl.SSLContext | bool = True,
        deadline: Callable[[], float] | None = None,
        host_id: UUID | None = None,
        local_spool: BoundedLocalSpool | None = None,
        expected_instance_id: UUID | None = None,
    ) -> None:
        if max_attempts < 1 or timeout_seconds <= 0 or min_free_bytes < 0 or max_upload_bytes < 0:
            raise ValueError("Invalid HTTP client limits")
        endpoint = httpx.URL(base_url)
        if (
            endpoint.scheme not in {"http", "https"}
            or not endpoint.host
            or endpoint.userinfo
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("Invalid HTTP API endpoint")
        self._url = str(endpoint).rstrip("/").removesuffix("/api/v1")
        self._auth = BearerHeaders(token)
        self._routes = routes
        self._spool_root = spool_root
        self._storage_budget = storage_budget
        self._min_free_bytes = min_free_bytes
        self._max_upload_bytes = max_upload_bytes
        self._attempts = max_attempts
        self._timeout = timeout_seconds
        self._deadline = deadline
        self._clock = clock if clock is not None else SystemMonotonic()
        self._sleeper = sleeper if callable(sleeper) else sleeper.sleep
        self._run_scope_id = run_scope_id
        self._host_id = host_id
        self._expected_instance_id = expected_instance_id
        self._receipt_deadline: datetime | None = None
        self._local_spool = local_spool
        self._ids = Uuid7Generator(SystemClock())
        self._owns_http = http is None
        self._http = http if http is not None else httpx.Client(trust_env=False, verify=verify)

    @property
    def local_spool(self) -> BoundedLocalSpool | None:
        return self._local_spool

    def bind_host(self, host_id: UUID) -> None:
        self._host_id = host_id

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    @override
    def new_idempotency_key(self) -> str:
        return "idem_" + self._ids.new_id().hex

    def _request(  # noqa: PLR0913 -- keep request construction uniform for JSON, SSE, and byte streams
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        *,
        params: list[tuple[str, str]] | None = None,
        body: Mapping[str, Any] | None = None,
        content: Callable[[], Iterable[bytes]] | None = None,
        timeout: float | None = None,
        retry: bool = True,
        stream: bool = False,
    ) -> httpx.Response:
        expected = self._expected_instance_id
        if expected is not None:
            headers = {**headers, "SKM-Instance-Id": str(expected)}

        def send() -> httpx.Response:
            request_timeout = self._timeout if timeout is None else timeout
            if self._deadline is not None:
                request_timeout = min(request_timeout, self._deadline() - self._clock.monotonic())
                if request_timeout <= 0:
                    raise transport_error(retryable=False)
            request = self._http.build_request(
                method,
                self._url + path,
                headers=headers,
                params=httpx.QueryParams(tuple(params)) if params is not None else None,
                json=body,
                content=content() if content is not None else None,
                timeout=request_timeout,
            )
            if "Idempotency-Key" not in headers:
                request.headers.pop("Idempotency-Key", None)
            response = self._http.send(request, stream=True, auth=None, follow_redirects=False)
            if expected is not None:
                values = response.headers.get_list("SKM-Instance-Id")
                if values != [str(expected)]:
                    response.close()
                    raise ValidationFailed(
                        ErrorCode.CONFIG_INVALID,
                        "Backend response did not confirm the expected instance_id",
                        details={"expected": str(expected)},
                    )
            return response

        def exchange() -> httpx.Response:
            return send_with_retry(
                send,
                attempts=self._attempts if retry else 1,
                sleeper=self._sleeper,
                redactor=self._auth.redactor,
                stream=stream,
            )

        if self._deadline is not None and not stream:
            return send_before_deadline(exchange, self._deadline() - self._clock.monotonic())
        return exchange()

    def _resolve_dto(
        self, dto: object, *, command: bool, key: str | None
    ) -> tuple[Route, dict[str, Any], str | None]:
        routes = self._routes(type(dto)) if callable(self._routes) else self._routes
        aliases = tuple(entry for entry in routes.describe() if (entry.command or entry.query) is type(dto))
        route = aliases[0] if aliases else routes[type(dto)]
        if command != (route.command is not None):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "DTO does not match the client operation")
        fields = None
        if len(aliases) > 1:
            fields = dict[str, Any](cast("Any", dto).to_json())
            route = _select_route(aliases, fields)
        key = idempotency_key(
            route.idempotency, key, retry=self._attempts > 1, generate=self.new_idempotency_key
        )
        if fields is None:
            fields = dict[str, Any](cast("Any", dto).to_json())
        return route, fields, key

    def _json_request(
        self, dto: object, *, command: bool, key: str | None = None, safe_until: datetime | None = None
    ) -> tuple[object, httpx.Headers]:
        route, fields, key = self._resolve_dto(dto, command=command, key=key)
        with self._spool_heartbeats(route.bus_name, fields):
            return self._send_json(route, fields, command=command, key=key, safe_until=safe_until)

    @contextmanager
    def _spool_heartbeats(self, operation: str, fields: Mapping[str, Any]) -> Generator[None]:
        spool = self._local_spool
        if spool is None:
            yield
            return
        observation = _heartbeat_payload(operation, fields, self._host_id)
        observed_at, fence = SystemClock().now(), spool.current_fence
        try:
            yield
        except BackendUnavailable as error:
            if error.retryable and observation is not None:
                try:
                    spool.enqueue_heartbeat(observation, fence_token=fence, observed_at=observed_at)
                except (OSError, SkmError) as spool_error:
                    _LOG.error("worker.spool.enqueue_failed", exc=spool_error)
            raise
        try:
            spool.replay(active_fence=spool.current_fence, record_observation=_record_heartbeat_observation)
        except OSError as error:
            _LOG.error("worker.spool.replay_failed", exc=error)

    def _send_json(
        self,
        route: Route,
        fields: dict[str, Any],
        *,
        command: bool,
        key: str | None,
        safe_until: datetime | None,
    ) -> tuple[object, httpx.Headers]:
        path = route.path
        for param, field in route.path_params.items():
            value = _pop_member(fields, field)
            path = path.replace("{" + param + "}", quote(_wire_value(value, field), safe=""))
        for param in route.path_guards:
            if self._run_scope_id is None:
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID, "An explicit run scope is required for this route"
                )
            path = path.replace("{" + param + "}", str(self._run_scope_id))
        headers = self._auth.new("application/json")
        if route.host_metadata is not None and self._host_id is not None:
            headers["SKM-Host-Id"] = str(self._host_id)
        if key is not None:
            headers["Idempotency-Key"] = key
        if safe_until is not None:
            headers["SKM-Idempotency-Deadline"] = safe_until.astimezone(UTC).isoformat()
        if route.if_match_to is not None:
            value = fields.pop(route.if_match_to, None)
            if value is not None:
                if type(value) is int and value == 0 and route.bus_name in _CREATE_ONLY:
                    headers["If-None-Match"] = "*"
                else:
                    headers["If-Match"] = encode_etag(value)
            elif route.requires_if_match(SchemaRegistry.load_default()):
                # Keep explicit nulls for the server's DTO validation.
                fields[route.if_match_to] = value
        if route.body == "merge_patch":
            headers["Content-Type"] = "application/merge-patch+json"
        elif route.body == "none" and route.method in {"POST", "PUT", "DELETE"}:
            headers["Content-Type"] = "application/json"
        response = self._request(
            route.method,
            path,
            headers,
            params=_query_parameters(route, fields),
            body=fields if route.body != "none" else None,
            retry=(not command and route.method == "GET") or key is not None,
        )
        result = _decode_result(route, response)
        if self._expected_instance_id is not None:
            self._receipt_deadline = _receipt_deadline(response.headers)
        return result, response.headers

    @override
    def dispatch(self, command: object, *, idempotency_key: str | None = None) -> object:
        return self._json_request(command, command=True, key=idempotency_key)[0]

    def safe_retry_deadline(self) -> datetime:
        """Read the safe limit observed on the last successful pinned project request."""
        if self._receipt_deadline is None:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Project API did not report retry retention")
        return self._receipt_deadline

    def dispatch_before(self, command: object, *, idempotency_key: str, safe_until: datetime) -> object:
        if self._expected_instance_id is None or safe_until.tzinfo is None:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Safe retries require a pinned API and UTC deadline"
            )
        return self._json_request(command, command=True, key=idempotency_key, safe_until=safe_until)[0]

    @override
    def ask(self, query: object) -> object:
        return self._json_request(query, command=False)[0]

    @override
    def ask_with_meta(self, query: object) -> tuple[object, QueryMeta]:
        result, headers = self._json_request(query, command=False)
        cursor = headers.get("SKM-Events-Cursor")
        if cursor is None:
            return result, QueryMeta(events_cursor=None)
        if not re.fullmatch(r"[0-9]{1,19}", cursor) or int(cursor) > 2**63 - 1:
            raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid HTTP events cursor")
        return result, QueryMeta(events_cursor=int(cursor))

    @override
    def events(
        self,
        *,
        workspace_id: WorkspaceId,
        after: int,
        types: frozenset[str] | None = None,
        wait_seconds: float = 0.0,
    ) -> Iterator[EventEnvelope]:
        params = [("workspace_id", str(workspace_id)), ("after", str(after))]
        params.extend(("types", name) for name in sorted(types or ()))

        @contextmanager
        def connection(resume: int | None, timeout: float) -> Generator[httpx.Response]:
            headers = self._auth.new("text/event-stream")
            headers["Connection"] = "close"
            if resume is not None:
                headers["Last-Event-ID"] = str(resume)
            response = self._request(
                "GET", "/api/v1/events", headers, params=params, timeout=timeout, stream=True, retry=False
            )
            with closing(response):
                if response.headers.get("content-type", "").partition(";")[0] != "text/event-stream":
                    raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid event stream media type")
                yield response

        return read_events(
            connection,
            workspace_id=workspace_id,
            after=after,
            wait_seconds=wait_seconds,
            timeout_seconds=self._timeout,
            clock=self._clock,
            sleeper=self._sleeper,
        )

    def project_events(
        self,
        *,
        project_id: ProjectId,
        workspace_id: WorkspaceId,
        after: int,
        types: frozenset[str] | None = None,
        wait_seconds: float = 0.0,
    ) -> Iterator[EventEnvelope]:
        """Stream project-scoped durable events from ``GET /api/v1/projects/{project_id}/events/stream``."""
        params = [("after", str(after))]
        if wait_seconds <= 0:
            params.append(("snapshot", "true"))
        params.extend(("types", name) for name in sorted(types or ()))
        path = f"/api/v1/projects/{project_id}/events/stream"

        @contextmanager
        def connection(resume: int | None, timeout: float) -> Generator[httpx.Response]:
            headers = self._auth.new("text/event-stream")
            headers["Connection"] = "close"
            if resume is not None:
                headers["Last-Event-ID"] = str(resume)
            response = self._request(
                "GET", path, headers, params=params, timeout=timeout, stream=True, retry=False
            )
            with closing(response):
                if response.headers.get("content-type", "").partition(";")[0] != "text/event-stream":
                    raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid event stream media type")
                yield response

        return read_events(
            connection,
            workspace_id=workspace_id,
            after=after,
            wait_seconds=wait_seconds,
            timeout_seconds=self._timeout,
            clock=self._clock,
            sleeper=self._sleeper,
            finite_snapshot=wait_seconds <= 0,
        )

    @contextmanager
    def _freeze(
        self,
        stream: Iterable[bytes],
        size: int,
        expected_digest: str | None,
    ) -> Generator[tuple[BinaryIO, str]]:
        root = self._spool_root
        owner = _private_spool_root(root, self._storage_budget)
        path = root.resolve() / f"upload-{owner.boot_id}-{owner.pid}-{owner.start_ticks}-{uuid4().hex}.tmp"
        with self._storage_budget.reserve(
            root,
            owner_id=path.name,
            max_bytes=size,
            min_free_bytes=self._min_free_bytes,
        ) as reservation:
            cleanup = True
            try:
                try:
                    spool = reservation.open_file(path)
                except FileExistsError:
                    cleanup = False  # Exclusive create refused an existing file.
                    raise
                digest = hashlib.sha256()
                length = 0
                for chunk in stream:
                    if not isinstance(chunk, bytes):  # pyright: ignore[reportUnnecessaryIsInstance]
                        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Upload chunks must be bytes")
                    length += len(chunk)
                    if length > size:
                        raise ValidationFailed(ErrorCode.BLOB_DIGEST_MISMATCH, "Upload exceeds declared size")
                    spool.write(chunk)
                    digest.update(chunk)
                actual = "sha256:" + digest.hexdigest()
                if length != size or (expected_digest is not None and actual != expected_digest):
                    raise ValidationFailed(ErrorCode.BLOB_DIGEST_MISMATCH, "Upload size or digest mismatch")
                spool.close()
                with path.open("rb") as frozen:
                    yield frozen, actual
            finally:
                if cleanup:
                    path.unlink(missing_ok=True)

    @override
    def upload_blob(
        self,
        workspace_id: WorkspaceId,
        stream: Iterable[bytes],
        *,
        size: int,
        expected_digest: str | None = None,
        media_type: str | None = None,
    ) -> StagedBlobRef:
        if type(size) is not int or size < 0:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Upload size must be a nonnegative integer")
        if size > self._max_upload_bytes:
            raise ValidationFailed(ErrorCode.BLOB_TOO_LARGE, "Upload exceeds the local size limit")
        try:
            with self._freeze(stream, size, expected_digest) as (frozen, digest):
                return self._upload_frozen(workspace_id, frozen, size, digest, media_type)
        except OSError as error:
            if error.errno != errno.ENOSPC:
                raise
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE, "Insufficient space for upload", details={"reason": "disk_low"}
        )

    def _upload_frozen(
        self, workspace_id: WorkspaceId, frozen: BinaryIO, size: int, digest: str, media_type: str | None
    ) -> StagedBlobRef:
        def rewind() -> Iterable[bytes]:
            frozen.seek(0)
            return iter(lambda: frozen.read(_BLOCK_BYTES), b"")

        headers = self._auth.new("application/json")
        headers.update(
            {
                "Content-Type": _OCTETS,
                "Content-Length": str(size),
                "SKM-Expected-Digest": digest,
                "Idempotency-Key": self.new_idempotency_key(),
            }
        )
        response = self._request(
            "POST",
            f"/api/v1/workspaces/{workspace_id}/blobs",
            headers,
            params=[("media_type", media_type)] if media_type is not None else None,
            content=rewind,
        )
        invalid = InternalError(ErrorCode.INTERNAL_ERROR, "Invalid staged blob response")
        try:
            data: object = response.json()
            if response.status_code != 201 or _blob_schema().issues(data):
                raise invalid
            ref = AddFileDefsStagedBlobRef.from_json(cast("dict[str, Any]", data))
        except (ValueError, TypeError, KeyError):
            raise invalid from None
        if ref.workspace_id != workspace_id:
            raise InternalError(ErrorCode.INTERNAL_ERROR, "Staged blob workspace mismatch")
        if ref.size != size or ref.digest != digest:
            raise ValidationFailed(ErrorCode.BLOB_DIGEST_MISMATCH, "Staged blob size or digest mismatch")
        return StagedBlobRef(
            ref.staged_blob_id, WorkspaceId(ref.workspace_id), ref.digest, ref.size, ref.media_type
        )

    @override
    def open_file_version_content(self, file_version_id: FileVersionId) -> BinaryIO:
        headers = self._auth.new(_OCTETS)
        response = self._request(
            "GET", f"/api/v1/file-versions/{file_version_id}/content", headers, stream=True
        )
        return cast("BinaryIO", io.BufferedReader(_ContentStream(response)))
