"""Explicit machine routes served only by the installation's private Unix socket."""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Generator
from contextlib import contextmanager, suppress
from functools import partial
from pathlib import Path
from socket import AF_UNIX, SOCK_STREAM, socket
from types import FrameType
from typing import cast, override
from uuid import UUID

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from uvicorn import Config, Server

from skm.bootstrap.instance_secrets import ensure_private_dir
from skm.bootstrap.machine_access import (
    MachineAuthority,
    MachineOperation,
    MachineOperationHandler,
    require_user_setting,
    validate_user_setting,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.fs.file_lock import FileLock
from skm.platform.logging.redaction import Redactor

from .errors import problem_response
from .request_context import RequestContext

__all__ = ["create_machine_api", "serve_machine_api"]

_PREFIX = "/api/v1/machine"
_HOST = "skm-machine"
_HANDLE = re.compile(r"[A-Za-z0-9_-]{43}")
_PROFILE = re.compile(r"[a-z][a-z0-9-]{0,31}")
_NAME = re.compile(r"[a-zA-Z0-9_.-]{1,128}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_MAX_BODY = 32768
_OPERATIONS: tuple[tuple[str, MachineOperation], ...] = (
    ("/repo/bind", "repo.bind"),
    ("/repo/verify", "repo.verify"),
    ("/integrations/plan", "integrations.plan"),
    ("/integrations/apply", "integrations.apply"),
    ("/integrations/doctor", "integrations.doctor"),
    ("/integrations/list", "integrations.list"),
    ("/workspace/sync-projections", "workspace.sync-projections"),
)


def _admit(request: Request) -> None:
    if request.scope.get("client") is not None:
        raise error_for(ErrorCode.FORBIDDEN, "Machine API requires a local Unix socket")
    if request.headers.getlist("host") != [_HOST]:
        raise error_for(ErrorCode.HOST_REJECTED, "Invalid machine API Host")
    if request.headers.getlist("origin"):
        raise error_for(ErrorCode.ORIGIN_REJECTED, "Browser origins are forbidden on the machine API")


def _profile(request: Request, default: str) -> str:
    values = request.headers.getlist("skm-instance-profile")
    if not values:
        return default
    if len(values) != 1 or _PROFILE.fullmatch(values[0]) is None:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid machine profile header")
    return values[0]


def _token(request: Request, *, required: bool = True) -> str | None:
    fields = request.headers.getlist("authorization")
    if not fields and not required:
        return None
    if len(fields) == 1:
        parts = fields[0].split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    raise error_for(ErrorCode.UNAUTHENTICATED, "An explicit project bearer token is required")


def _handle(request: Request, *, required: bool = True) -> str | None:
    values = request.headers.getlist("skm-machine-session")
    if not values and not required:
        return None
    if len(values) == 1 and _HANDLE.fullmatch(values[0]):
        return values[0]
    raise error_for(ErrorCode.UNAUTHENTICATED, "An active machine session handle is required")


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


def _reject_constants(_: str) -> JsonValue:
    raise ValueError("Invalid JSON number")


async def _body(request: Request) -> JsonObject:
    types = request.headers.getlist("content-type")
    if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
        raise error_for(ErrorCode.UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_BODY:
            raise error_for(ErrorCode.PAYLOAD_TOO_LARGE, "Machine request body exceeds the limit")
        body.extend(chunk)
    try:
        value: object = json.loads(body, object_pairs_hook=_unique_object, parse_constant=_reject_constants)
    except (ValueError, RecursionError):
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid machine request JSON") from None
    if not isinstance(value, dict):
        raise error_for(ErrorCode.SCHEMA_INVALID, "Machine request must be a JSON object")
    return cast("JsonObject", value)


def _uuid(value: JsonValue) -> UUID:
    try:
        if isinstance(value, str):
            return UUID(value)
    except ValueError:
        pass
    raise error_for(ErrorCode.SCHEMA_INVALID, "Expected a UUID in the machine request")


def _operation_payload(operation: MachineOperation, body: JsonObject) -> JsonObject:
    field_types: dict[str, type]
    if operation == "repo.bind":
        field_types = {
            "path": str,
            "workspace_id": UUID,
            "project_id": UUID,
            "repository_id": UUID,
            "mount_name": str,
            "role": str,
            "title": str,
            "assume_yes": bool,
            "register_missing": bool,
            "write_marker": bool,
        }
        required = {"path", "workspace_id"}
    elif operation == "repo.verify":
        field_types = {"project_id": UUID, "repository_id": UUID, "mount_name": str, "binding_id": UUID}
        required = {"project_id"}
    elif operation == "workspace.sync-projections":
        field_types = {"scope": str, "scope_id": UUID}
        required = {"scope", "scope_id"}
    elif operation == "integrations.list":
        field_types = {"project_id": UUID, "after": str, "limit": int}
        required = {"project_id"}
    else:
        field_types = {"project_id": UUID, "mount": str, "targets": list}
        required = {"project_id"}
        if operation in ("integrations.plan", "integrations.apply"):
            field_types["force_conflicts"] = bool
        if operation == "integrations.apply":
            field_types.update(restore_pre_image=bool, plan_digests=list)
            required.add("plan_digests")
    if set(body) - field_types.keys() or required - body.keys():
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid fields for the machine operation")
    validated: JsonObject = {}
    for name, value in body.items():
        kind = field_types[name]
        if kind is UUID:
            validated[name] = str(_uuid(value))
        elif type(value) is not kind:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid field type for the machine operation")
        else:
            validated[name] = value
    _validate_operation_values(operation, validated)
    return validated


def _validate_operation_values(operation: MachineOperation, body: JsonObject) -> None:
    for key in ("mount", "mount_name", "role"):
        if key in body and _NAME.fullmatch(cast("str", body[key])) is None:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid mount or role")
    if "path" in body:
        path = cast("str", body["path"])
        if len(path) > 4096 or "\x00" in path or not Path(path).is_absolute():
            raise error_for(ErrorCode.SCHEMA_INVALID, "Checkout path must be a local absolute path")
    if operation == "workspace.sync-projections" and body["scope"] not in ("project", "workspace"):
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid projection scope")
    if "targets" in body:
        values = cast("list[JsonValue]", body["targets"])
        if (
            not values
            or len(values) > 16
            or any(not isinstance(value, str) or _NAME.fullmatch(value) is None for value in values)
        ):
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid projection targets")
    if "plan_digests" in body:
        digests = cast("list[JsonValue]", body["plan_digests"])
        if len(digests) > 16 or any(
            not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None for digest in digests
        ):
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid projection plan digests")


def _request_id(request: Request, operation: MachineOperation) -> UUID | None:
    values = request.headers.getlist("idempotency-key")
    if not values and operation not in ("repo.bind", "repo.verify"):
        return None
    if len(values) != 1:
        raise error_for(ErrorCode.PRECONDITION_REQUIRED, "A UUID Idempotency-Key is required")
    return _uuid(values[0])


def _instance_status(authority: MachineAuthority, name: str, token: str | None) -> JsonObject:
    pin = authority.profile(name)
    if token is None:
        return {"profile": name, "instance_id": str(pin.instance_id), "connection": "unchecked"}
    try:
        with authority.caller(name, token) as (caller, _expires):
            return {"profile": name, "instance_id": str(caller.scope.instance_id), "connection": "ready"}
    except SkmError as error:
        if error.code is not ErrorCode.BACKEND_UNAVAILABLE:
            raise
        return {"profile": name, "instance_id": str(pin.instance_id), "connection": "unavailable"}


def create_machine_api(
    authority: MachineAuthority,
    *,
    default_profile: str,
    run_operation: MachineOperationHandler,
    redactor: Redactor | None = None,
) -> Starlette:
    """Mount machine primitives and the fixed operation allowlist."""

    def profile(request: Request) -> str:
        return _profile(request, default_profile)

    async def local_status(request: Request) -> JSONResponse:
        _admit(request)
        installation = await run_in_threadpool(authority.store.get_installation_id)
        if installation != authority.installation_id:
            raise error_for(ErrorCode.CONFIG_INVALID, "Machine database identity changed")
        return JSONResponse({"status": "ready", "installation_id": str(installation)})

    async def instance_status(request: Request) -> JSONResponse:
        _admit(request)
        name, token = profile(request), _token(request, required=False)

        return JSONResponse(await run_in_threadpool(_instance_status, authority, name, token))

    async def login(request: Request) -> JSONResponse:
        _admit(request)
        token, old = cast("str", _token(request)), _handle(request, required=False)
        result = await run_in_threadpool(authority.login, profile(request), token, old)
        return JSONResponse(result, status_code=201)

    async def logout(request: Request) -> Response:
        _admit(request)
        await run_in_threadpool(authority.logout, cast("str", _handle(request)))
        return Response(status_code=204)

    async def settings(request: Request) -> JSONResponse:
        _admit(request)
        key = cast("str", request.path_params["key"])
        require_user_setting(key)
        handle = cast("str", _handle(request))
        scope = await run_in_threadpool(authority.scope, handle)
        if request.method in ("GET", "HEAD"):
            value = await run_in_threadpool(authority.store.get_user_setting, scope, key)
            return JSONResponse({"key": key, "value": value})
        token = cast("str", _token(request))
        name = profile(request)
        body = await _body(request)
        if set(body) != {"value"}:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Machine setting requires a value")

        def save() -> JsonValue:
            try:
                with authority.caller(name, token) as (caller, _expires):
                    if caller.scope != scope:
                        raise error_for(ErrorCode.FORBIDDEN, "Machine session is outside the caller's scope")
                    value = validate_user_setting(key, body["value"], caller.client)
                    if authority.scope(handle) != scope:
                        raise error_for(ErrorCode.UNAUTHENTICATED, "Machine session has been invalidated")
                    authority.store.set_user_setting(scope, key, value)
                    return value
            except SkmError as error:
                if error.code is ErrorCode.UNAUTHENTICATED:
                    authority.logout(handle)
                raise

        return JSONResponse({"key": key, "value": await run_in_threadpool(save)})

    async def composed(request: Request, operation: MachineOperation) -> JSONResponse:
        _admit(request)
        token = cast("str", _token(request))
        name, request_id = profile(request), _request_id(request, operation)
        payload = _operation_payload(operation, await _body(request))

        def run() -> JsonValue:
            with authority.caller(name, token) as (caller, _expires):
                _ = caller.host_id
                return run_operation(operation, caller, payload, request_id)

        return JSONResponse(await run_in_threadpool(run))

    async def missing(request: Request, error: Exception) -> JSONResponse:
        reply = problem_response(request, error_for(ErrorCode.NOT_FOUND, "Machine route not found"))
        reply.status_code = cast("HTTPException", error).status_code
        return reply

    api = Starlette(
        routes=[
            Route(_PREFIX + "/local/status", local_status),
            Route(_PREFIX + "/instance/status", instance_status),
            Route(_PREFIX + "/session", login, methods=["POST"]),
            Route(_PREFIX + "/session", logout, methods=["DELETE"]),
            Route(_PREFIX + "/settings/{key}", settings, methods=["GET", "PUT"]),
            *[
                Route(_PREFIX + path, partial(composed, operation=operation), methods=["POST"])
                for path, operation in _OPERATIONS
            ],
        ],
        exception_handlers={HTTPException: missing},
        middleware=[Middleware(RequestContext, settings={}, redactor=redactor or Redactor())],
    )
    api.router.redirect_slashes = False
    return api


def _is_private_socket(info: os.stat_result) -> bool:
    return stat.S_ISSOCK(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600


def _remove_stale_socket(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if not _is_private_socket(info):
        raise error_for(ErrorCode.SECRET_PERMISSIONS, "The machine socket path is not a private socket")
    with socket(AF_UNIX, SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        try:
            probe.connect(str(path))
        except ConnectionRefusedError:
            if os.path.samestat(info, path.lstat()):
                path.unlink()
            return
    raise error_for(ErrorCode.ALREADY_EXISTS, "A machine API already serves this installation")


@contextmanager
def _listen(path: Path) -> Generator[socket]:
    ensure_private_dir(path.parent)
    if stat.S_IMODE(path.parent.lstat().st_mode) != 0o700:
        raise error_for(ErrorCode.SECRET_PERMISSIONS, "Machine socket directory must have mode 0700")
    lock = FileLock(path.with_suffix(".lock"))
    if not lock.acquire():
        raise error_for(ErrorCode.ALREADY_EXISTS, "A machine API already serves this installation")
    try:
        _remove_stale_socket(path)
        with socket(AF_UNIX, SOCK_STREAM) as listener:
            listener.bind(str(path))
            info = path.lstat()
            try:
                path.chmod(0o600)
                if not _is_private_socket(path.lstat()):
                    raise error_for(ErrorCode.SECRET_PERMISSIONS, "Machine socket must have mode 0600")
                listener.listen()
                yield listener
            finally:
                with suppress(FileNotFoundError):
                    if os.path.samestat(info, path.lstat()):
                        path.unlink()
    finally:
        lock.release()


class _MachineServer(Server):
    @override
    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        del sig, frame
        self.force_exit = self.should_exit
        self.should_exit = True


def serve_machine_api(api: Starlette, path: Path) -> None:
    with _listen(path) as listener:
        config = Config(api, proxy_headers=False, access_log=False, ws="none", timeout_graceful_shutdown=5)
        _MachineServer(config).run(sockets=[listener])
