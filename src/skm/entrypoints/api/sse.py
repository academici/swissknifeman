"""Durable workspace and project SSE with request-time and continuous access checks."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol, cast, override
from uuid import UUID

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import Message, Receive, Scope, Send

from skm.application_bus.context import AuthBasis
from skm.application_bus.ports import EventReader
from skm.bootstrap.composition import App
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, SkmError, error_for
from skm.kernel.events import STREAM_KINDS, EventEnvelope
from skm.kernel.ids import ProjectId, ScopeId, ToolIntentId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Isolation, RequestMeta, UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRegistry
from skm.modules.access.public import RbacAuthorizer, effective_permissions
from skm.modules.artifacts.public import FileId, FileRepository
from skm.modules.integrations.public import ProjectionId, ProjectionRepository
from skm.modules.policy.public import intent_scope_id
from skm.platform.logging.redaction import Redactor

from .auth import request_auth_basis
from .request_context import request_meta

__all__ = ["EventWakeups", "WorkspaceEvents"]

_PERMISSIONS = {
    "workspace": "workspace.read",
    "project": "project.read",
    "plan": "plan.read",
    "run": "run.read",
    "config": "config.read",
    "file": "file.read",
    "intent": "policy.read",
    "projection": "integration.read",
    "hook_delivery": "integration.read",
    "memory": "memory.read",
    "lesson": "lesson.read",
    "candidate": "lesson.read",
    "vault_note": "plan.read",
}
_DIRECT_SCOPES = {
    kind.value: kind for kind in (ScopeKind.WORKSPACE, ScopeKind.PROJECT, ScopeKind.PLAN, ScopeKind.RUN)
}
_EVENT_TYPE = re.compile(r"urn:skm:[a-z][a-z0-9-]*:event:[a-z][a-z0-9-]*:v[1-9][0-9]*|[A-Z][A-Za-z0-9]*")
_RETRY = "retry: 3000\n\n"
_MAX_CURSOR = 2**63 - 1
_MAX_REVOCATION_RECHECK_SECONDS = 5.0
_RUN_PAUSED = "urn:skm:execution:event:run-paused:v1"
_RUN_CANCELLED = "urn:skm:execution:event:run-cancelled:v1"
_RUN_CODES = frozenset({"RUN_PAUSED", "RUN_CANCELLED", "ITEM_BLOCKED", *(code.value for code in ErrorCode)})
_CONTROL_TRIGGERS = frozenset({"cancel", "subscription", "wait_changed", "stage_outcome"})
_REFERENCE_KINDS = frozenset(
    {
        "run",
        "task",
        "attempt",
        "stage",
        "step",
        "output",
        "check",
        "review",
        "decision_request",
        "decision",
        "effect",
        "recovery",
        "fix_brief",
        "finding",
        "reconfiguration",
    }
)


class EventWakeups(Protocol):
    def start(self, wake: Callable[[WorkspaceId], None]) -> None: ...

    def stop(self) -> None: ...


def _feed_filters(
    request: Request,
) -> tuple[int | None, frozenset[tuple[str, UUID]], frozenset[str]]:
    params = request.query_params
    last = request.headers.getlist("last-event-id")
    after = _cursor_input(last if last else params.getlist("after"))
    streams: set[tuple[str, UUID]] = set()
    for item in params.getlist("stream"):
        kind, _, stream_id = item.partition(":")
        if kind not in STREAM_KINDS:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid stream kind")
        streams.add((kind, _uuid(stream_id, "stream")))
    types = frozenset(part.strip() for value in params.getlist("types") for part in value.split(","))
    if any(_EVENT_TYPE.fullmatch(event_type) is None for event_type in types):
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid event type")
    return after, frozenset(streams), types


@dataclass(frozen=True, slots=True)
class _Feed:
    workspace: WorkspaceId
    after: int | None
    streams: frozenset[tuple[str, UUID]]
    types: frozenset[str]
    project: ProjectId | None = None
    snapshot_end: int | None = None

    @classmethod
    def from_request(cls, request: Request) -> _Feed:
        workspace = _uuid(request.query_params.get("workspace_id"), "workspace_id")
        after, streams, types = _feed_filters(request)
        return cls(WorkspaceId(workspace), after, streams, types)

    def matches(self, event: EventEnvelope, name: str) -> bool:
        return (
            event.workspace_id == self.workspace
            and (not self.streams or (event.stream_kind, event.stream_id) in self.streams)
            and (not self.types or name in self.types or event.type in self.types)
        )


def _uuid(value: str | None, field: str) -> UUID:
    try:
        return UUID(value or "")
    except ValueError:
        raise error_for(ErrorCode.SCHEMA_INVALID, f"Invalid {field}") from None


def _cursor_input(values: list[str]) -> int | None:
    if not values:
        return None
    digits = values[0].lstrip("0") or "0"
    if len(values) != 1 or re.fullmatch(r"[0-9]+", values[0]) is None or len(digits) > 19:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid event cursor")
    cursor = int(digits)
    if cursor > _MAX_CURSOR:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid event cursor")
    return cursor


def _short_name(event: EventEnvelope) -> str:
    return "".join(part.title() for part in event.type.split(":")[-2].split("-"))


def _cursor(seq: int) -> str:
    return f"id: {seq}\nevent: cursor\ndata: {{}}\n\n"


def _run_code(value: JsonValue) -> str | None:
    return value if isinstance(value, str) and value in _RUN_CODES else None


def _uuid_field(value: JsonValue) -> str | None:
    if isinstance(value, str):
        with suppress(ValueError):
            return str(UUID(value))
    return None


def _control_cause(raw: JsonValue, event: EventEnvelope) -> JsonObject | None:
    if not isinstance(raw, dict):
        return None
    trigger = raw.get("trigger_kind")
    if not isinstance(trigger, str) or trigger not in _CONTROL_TRIGGERS:
        return None
    codes, rule = raw.get("reason_codes"), raw.get("advance_rule")
    items = raw.get("refs")
    refs: list[JsonValue] = (
        [
            {"kind": kind, "id": ref}
            for item in items
            if isinstance(item, dict)
            and isinstance(kind := item.get("kind"), str)
            and kind in _REFERENCE_KINDS
            and (ref := _uuid_field(item.get("id"))) is not None
        ]
        if isinstance(items, list)
        else []
    )
    cause: JsonObject = {
        "trigger_kind": trigger,
        "advance_rule": rule if rule in ("R6", "R10") else None,
        "reason_codes": [code for value in codes if (code := _run_code(value)) is not None]
        if isinstance(codes, list)
        else [],
        "refs": refs,
    }
    if (source_event := _uuid_field(raw.get("source_event_id"))) is not None:
        cause["source_event_id"] = source_event
    if isinstance(command := raw.get("command_id"), str) and command in (
        event.request_id,
        event.causation_id,
        event.parent_causation_id,
    ):
        cause["command_id"] = command
    return cause


def _stream_document(event: EventEnvelope) -> JsonObject:
    document = event.to_json()
    if event.type not in (_RUN_PAUSED, _RUN_CANCELLED):
        return document
    raw = event.payload
    safe: JsonObject = {
        key: value
        for key in ("workspace_id", "project_id", "run_id", "by")
        if (value := _uuid_field(raw.get(key))) is not None
    }
    if event.type == _RUN_PAUSED:
        stop = _run_code(raw.get("stop_code"))
        safe["reason"] = _run_code(raw.get("reason")) or stop or "RUN_PAUSED"
        safe["stop_code"] = stop
        if (source := raw.get("pause_source")) in ("owner", "system"):
            safe["pause_source"] = source
    else:
        safe["reason"] = "RUN_CANCELLED"
        safe["previous_stop_code"] = _run_code(raw.get("previous_stop_code"))
    if (cause := _control_cause(raw.get("cause"), event)) is not None:
        safe["cause"] = cause
    document["payload"] = safe
    return document


def _payload_scope(event: EventEnvelope, key: str, kind: ScopeKind) -> tuple[ScopeId, ScopeKind] | None:
    value = event.payload.get(key)
    if isinstance(value, str):
        try:
            return ScopeId(UUID(value)), kind
        except ValueError:
            pass
    return None


def _target(uow: UnitOfWork, event: EventEnvelope) -> ScopeRecord | None:
    """Resolve the stream's scope through stored ownership. Missing or foreign scopes hide the event."""
    kind, stream_id = event.stream_kind, event.stream_id
    if kind in _DIRECT_SCOPES:
        target = ScopeId(stream_id), _DIRECT_SCOPES[kind]
    elif kind in {"config", "memory"}:
        # These streams may name a scope directly. Namespace hashes do not resolve as scopes.
        target = ScopeId(stream_id), None
    elif kind == "file":
        file = uow.repo(FileRepository).get(FileId(stream_id))
        if file.workspace_id != event.workspace_id:
            return None
        target = (
            (ScopeId(file.workspace_id), ScopeKind.WORKSPACE)
            if file.project_id is None
            else (ScopeId(file.project_id), ScopeKind.PROJECT)
        )
    elif kind == "projection":
        project = uow.repo(ProjectionRepository).get(ProjectionId(stream_id)).project_id
        target = ScopeId(project), ScopeKind.PROJECT
    elif kind == "intent":
        intent_scope = intent_scope_id(uow, ToolIntentId(stream_id))
        if intent_scope is None:
            return None
        target = intent_scope, None
    elif kind == "hook_delivery":
        target = _hook_scope(event)
    elif kind in {"lesson", "candidate", "vault_note"} and event.workspace_id is not None:
        target = (
            _payload_scope(event, "project_id", ScopeKind.PROJECT)
            if "project_id" in event.payload
            else (ScopeId(event.workspace_id), ScopeKind.WORKSPACE)
        )
    else:
        return None
    if target is None:
        return None
    scope = uow.repo(ScopeRegistry).get(target[0])
    if (target[1] is not None and scope.kind is not target[1]) or scope.workspace_id != event.workspace_id:
        return None
    return scope


def _hook_scope(event: EventEnvelope) -> tuple[ScopeId, ScopeKind] | None:
    if event.type not in {
        "urn:skm:integrations:event:hook-delivery-failed:v1",
        "urn:skm:integrations:event:hook-test-requested:v1",
    }:
        return None
    if event.payload.get("run_id") is not None:
        return _payload_scope(event, "run_id", ScopeKind.RUN)
    if event.payload.get("project_id") is not None:
        return _payload_scope(event, "project_id", ScopeKind.PROJECT)
    return None if event.workspace_id is None else (ScopeId(event.workspace_id), ScopeKind.WORKSPACE)


class _Subscription:
    def __init__(self, queue_size: int, release: Callable[[], None]) -> None:
        self.pending: asyncio.Queue[None] = asyncio.Queue(maxsize=queue_size)
        self.recheck: asyncio.Event = asyncio.Event()
        self.closed: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._release = release

    def close(self) -> None:
        if not self.closed.done():
            self.recheck.set()
            self.closed.set_result(None)
            self._release()

    def notify(self) -> None:
        try:
            self.pending.put_nowait(None)
        except asyncio.QueueFull:
            self.close()

    def wake_check(self) -> None:
        """Wake waiting streams and blocked-send watchers to re-check credentials without backpressure."""
        if self.closed.done():
            return
        self.recheck.set()
        if self.pending.empty():
            with suppress(asyncio.QueueFull):
                self.pending.put_nowait(None)

    def drain(self) -> None:
        while not self.pending.empty():
            self.pending.get_nowait()

    async def wait(self, seconds: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self.pending.get(), timeout=max(0.0, seconds))


class _Response(StreamingResponse):
    def __init__(
        self,
        body: AsyncGenerator[str],
        subscription: _Subscription,
        *,
        heartbeat: int | None = None,
        check: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(body, media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})
        self._body = body
        self._subscription = subscription
        self._heartbeat = heartbeat
        self._check = check

    @override
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        sending = False

        async def write(message: Message) -> None:
            nonlocal sending
            sending = True
            try:
                await send(message)
            finally:
                sending = False

        heartbeat, check = self._heartbeat, self._check
        has_watcher = heartbeat is not None and check is not None

        async def watch() -> None:
            assert heartbeat is not None  # noqa: S101 -- guarded by has_watcher
            assert check is not None  # noqa: S101 -- guarded by has_watcher
            interval = min(float(heartbeat), _MAX_REVOCATION_RECHECK_SECONDS)
            while not self._subscription.closed.done():
                self._subscription.recheck.clear()
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._subscription.recheck.wait(), timeout=interval)
                if self._subscription.closed.done():
                    return
                if sending:
                    try:
                        await run_in_threadpool(check)
                    except SkmError:
                        self._subscription.close()
                        return

        # Listen for disconnect even on ASGI 2.4, when Starlette normally waits for the next send.
        tasks: list[asyncio.Task[None]] = [
            asyncio.create_task(self.stream_response(write if has_watcher else send)),
            asyncio.create_task(self.listen_for_disconnect(receive)),
        ]
        watcher = asyncio.create_task(watch()) if has_watcher else None
        try:
            done, _ = await asyncio.wait(
                (*tasks, self._subscription.closed), return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                with suppress(OSError):  # The transport may close before http.disconnect arrives.
                    task.result()
        finally:
            self._subscription.close()
            if watcher is not None:
                watcher.cancel()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, *((watcher,) if watcher is not None else ()), return_exceptions=True)
            await self._body.aclose()


class WorkspaceEvents:
    def __init__(self, app: App, settings: Mapping[str, JsonValue], authorizer: RbacAuthorizer) -> None:
        self._app = app
        self._auth = authorizer
        self._max_streams = self._setting(settings, "max_streams_per_token", 8)
        self._queue_size = self._setting(settings, "queue_size", 1000)
        self._batch_size = min(self._queue_size, self._setting(settings, "batch_size", 200))
        self._heartbeat = self._setting(settings, "heartbeat_seconds", 15)
        self._poll = self._setting(settings, "poll_ms", 2000) / 1000
        self._counts: dict[tuple[str, UUID], int] = {}
        self._feeds: dict[WorkspaceId, set[_Subscription]] = {}

    @staticmethod
    def _setting(settings: Mapping[str, JsonValue], name: str, default: int) -> int:
        return max(1, cast("int", settings.get(f"api.sse.{name}", default)))

    def notify(self, workspace: WorkspaceId) -> None:
        for subscription in tuple(self._feeds.get(workspace, ())):
            subscription.notify()

    def notify_access_changed(self) -> None:
        """Wake active streams to immediately re-check credentials and memberships."""
        for subscriptions in tuple(self._feeds.values()):
            for subscription in tuple(subscriptions):
                subscription.wake_check()

    async def endpoint(self, request: Request) -> Response:
        feed = _Feed.from_request(request)
        basis = request_auth_basis(request)
        meta = request_meta(request)
        after = await run_in_threadpool(self._admit, basis, meta, feed)
        return self._open_stream(request, basis, meta, feed, after)

    async def project_endpoint(self, request: Request) -> Response:
        project_id = ProjectId(_uuid(request.path_params.get("project_id"), "project_id"))
        after_param, streams, types = _feed_filters(request)
        snapshot = request.query_params.getlist("snapshot")
        if snapshot not in ([], ["false"], ["true"]):
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid snapshot parameter")
        basis = request_auth_basis(request)
        meta = request_meta(request)
        workspace, after, end = await run_in_threadpool(
            self._admit_project, basis, meta, project_id, after_param, snapshot=snapshot == ["true"]
        )
        feed = _Feed(workspace, after_param, streams, types, project=project_id, snapshot_end=end)
        return self._open_stream(request, basis, meta, feed, after)

    def _open_stream(
        self, request: Request, basis: AuthBasis, meta: RequestMeta, feed: _Feed, after: int
    ) -> Response:
        if request.method == "HEAD":
            return Response(media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})
        quota_key = basis.stream_quota_key
        count = self._counts.get(quota_key, 0)
        if count >= self._max_streams:
            raise error_for(ErrorCode.TOO_MANY_STREAMS, "Too many active event streams")

        def release() -> None:
            self._feeds[feed.workspace].remove(subscription)
            if not self._feeds[feed.workspace]:
                del self._feeds[feed.workspace]
            self._counts[quota_key] -= 1
            if not self._counts[quota_key]:
                del self._counts[quota_key]

        subscription = _Subscription(self._queue_size, release)
        self._counts[quota_key] = count + 1
        self._feeds.setdefault(feed.workspace, set()).add(subscription)
        redactor = cast("Redactor | None", getattr(self._app, "redactor", None)) or cast(
            "Redactor", request.state.redactor
        )
        return _Response(
            self._stream(basis, meta, feed, after, subscription, redactor),
            subscription,
            heartbeat=self._heartbeat,
            check=lambda: self._heartbeat_check(basis, meta, feed),
        )

    def _require_workspace(self, uow: UnitOfWork, basis: AuthBasis, workspace: WorkspaceId) -> None:
        self._auth.admit_basis(uow, basis)
        scope = uow.repo(ScopeRegistry).get(ScopeId(workspace))
        if scope.kind is not ScopeKind.WORKSPACE or scope.workspace_id != workspace:
            raise error_for(ErrorCode.NOT_FOUND, "Workspace not found")
        if "workspace.read" not in effective_permissions(uow, basis.actor, scope.id):
            raise error_for(ErrorCode.FORBIDDEN, "This operation requires workspace.read")

    def _require_project(
        self,
        uow: UnitOfWork,
        basis: AuthBasis,
        project: ProjectId,
        *,
        expected_workspace: WorkspaceId | None = None,
    ) -> WorkspaceId:
        self._auth.admit_basis(uow, basis)
        try:
            scope = uow.repo(ScopeRegistry).get(ScopeId(project))
        except NotFound:
            raise error_for(ErrorCode.NOT_FOUND, "Project not found") from None
        if (
            scope.kind is not ScopeKind.PROJECT
            or scope.workspace_id is None
            or (expected_workspace is not None and scope.workspace_id != expected_workspace)
        ):
            raise error_for(ErrorCode.NOT_FOUND, "Project not found")
        if "project.read" not in effective_permissions(uow, basis.actor, scope.id):
            raise error_for(ErrorCode.FORBIDDEN, "This operation requires project.read")
        return scope.workspace_id

    def _require_access(self, uow: UnitOfWork, basis: AuthBasis, feed: _Feed) -> None:
        if feed.project is not None:
            self._require_project(uow, basis, feed.project, expected_workspace=feed.workspace)
            return
        self._require_workspace(uow, basis, feed.workspace)

    def _admit(self, basis: AuthBasis, meta: RequestMeta, feed: _Feed) -> int:
        with self._app.uow_factory(meta, readonly=True, isolation=Isolation.REPEATABLE_READ) as uow:
            self._require_access(uow, basis, feed)
            if feed.after is not None:
                return feed.after
            return uow.repo(EventReader).head_workspace_seq(feed.workspace)

    def _admit_project(
        self, basis: AuthBasis, meta: RequestMeta, project: ProjectId, after: int | None, *, snapshot: bool
    ) -> tuple[WorkspaceId, int, int | None]:
        with self._app.uow_factory(meta, readonly=True, isolation=Isolation.REPEATABLE_READ) as uow:
            workspace = self._require_project(uow, basis, project)
            head = uow.repo(EventReader).head_workspace_seq(workspace) if snapshot or after is None else 0
            return workspace, after if after is not None else head, head if snapshot else None

    def _heartbeat_check(self, basis: AuthBasis, meta: RequestMeta, feed: _Feed) -> None:
        with self._app.uow_factory(meta, readonly=True, isolation=Isolation.REPEATABLE_READ) as uow:
            self._require_access(uow, basis, feed)

    def _batch(
        self, basis: AuthBasis, meta: RequestMeta, feed: _Feed, after: int, redactor: Redactor
    ) -> tuple[int, str, bool]:
        with self._app.uow_factory(meta, readonly=True, isolation=Isolation.REPEATABLE_READ) as uow:
            self._require_access(uow, basis, feed)
            # Scan the whole workspace range so filtering never strands the client's cursor.
            events = uow.repo(EventReader).after_workspace_seq(
                feed.workspace, after, types=None, limit=self._batch_size
            )
            if feed.snapshot_end is not None:
                bound = feed.snapshot_end
                events = tuple(event for event in events if (event.workspace_seq or after) <= bound)
            selected = tuple(
                (event, name) for event in events if feed.matches(event, name := _short_name(event))
            )
            return self._frames(uow, basis, feed, after, events, selected, redactor)

    def _frames(
        self,
        uow: UnitOfWork,
        basis: AuthBasis,
        feed: _Feed,
        after: int,
        events: tuple[EventEnvelope, ...],
        selected: tuple[tuple[EventEnvelope, str], ...],
        redactor: Redactor,
    ) -> tuple[int, str, bool]:
        advanced = (events[-1].workspace_seq or after) if events else after
        visible_through = after
        permissions: dict[ScopeId, frozenset[str]] = {}
        ancestors_cache: dict[ScopeId, tuple[ScopeRecord, ...]] = {}
        scopes = uow.repo(ScopeRegistry)
        frames: list[str] = []
        for event, name in selected:
            permission = _PERMISSIONS.get(event.stream_kind)
            if permission is None or event.workspace_seq is None:
                continue
            try:
                target = _target(uow, event)
                if target is None or target.workspace_id != feed.workspace:
                    continue
                chain = ancestors_cache.get(target.id)
                if chain is None:
                    chain = scopes.ancestors(target.id)
                    ancestors_cache[target.id] = chain
                if not any(
                    record.id == ScopeId(feed.workspace) and record.kind is ScopeKind.WORKSPACE
                    for record in chain
                ):
                    continue
                if feed.project is not None and not any(
                    record.id == ScopeId(feed.project) and record.kind is ScopeKind.PROJECT
                    for record in chain
                ):
                    continue
                if target.id not in permissions:
                    permissions[target.id] = effective_permissions(uow, basis.actor, target.id)
            except NotFound:
                continue
            if permission in permissions[target.id]:
                visible_through = event.workspace_seq
                data = json.dumps(redactor.document(_stream_document(event)), separators=(",", ":"))
                frames.append(f"id: {visible_through}\nevent: {name}\ndata: {data}\n\n")
        if feed.project is None and advanced > visible_through:
            frames.append(_cursor(advanced))
        more = len(events) == self._batch_size and (feed.snapshot_end is None or advanced < feed.snapshot_end)
        return advanced, "".join(frames), more

    async def _stream(
        self,
        basis: AuthBasis,
        meta: RequestMeta,
        feed: _Feed,
        after: int,
        subscription: _Subscription,
        redactor: Redactor,
    ) -> AsyncGenerator[str]:
        loop = asyncio.get_running_loop()
        heartbeat_at = loop.time() + self._heartbeat
        yield _RETRY + (_cursor(after) if feed.after is None and feed.project is None else "")
        try:
            while not subscription.closed.done():
                if loop.time() >= heartbeat_at:
                    await run_in_threadpool(self._heartbeat_check, basis, meta, feed)
                    heartbeat_at = loop.time() + self._heartbeat
                    yield f": ping {time.time_ns() // 1_000_000}\n\n"
                subscription.drain()
                after, frames, more = await run_in_threadpool(self._batch, basis, meta, feed, after, redactor)
                if subscription.closed.done():
                    return
                if frames:
                    yield frames
                if feed.snapshot_end is not None and not more:
                    return
                if not more and not subscription.closed.done():
                    await subscription.wait(
                        min(self._poll, _MAX_REVOCATION_RECHECK_SECONDS, max(0.0, heartbeat_at - loop.time()))
                    )
        except SkmError:
            # Headers have already been sent. End the feed; reconnect goes through normal HTTP admission.
            return
