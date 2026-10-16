"""Core endpoints: handshake, catalog, schemas, projects and the browser session (token → cookie)."""
from __future__ import annotations

import json
import os
from urllib.parse import parse_qs

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .. import contracts
from ..backend import COOKIE
from ..core.projects import list_document
from ..errors import GuiError
from . import confirm
from .errors import endpoint, json_response, read_json


def _state(request: Request):
    return request.app.state.backend


@endpoint
async def bootstrap(request: Request) -> Response:
    return json_response(_state(request).bootstrap())


@endpoint
async def contributions(request: Request) -> Response:
    state = _state(request)
    if request.query_params.get("refresh") == "1":
        await run_in_threadpool(state.refresh_catalog)
    return json_response(state.catalog.document)


@endpoint
async def schema(request: Request) -> Response:
    """The JSON Schema of a contract of ``unit.json`` only; nothing from the request reaches the path otherwise."""
    name, version = request.path_params["contract"], request.path_params["version"]
    listed = {(entry["id"].rpartition(":")[2], entry["version"]) for entry in _unit_contracts()}
    if (name, version) not in listed:
        raise GuiError("NOT_FOUND", f"no contract {name}/{version}")
    path = contracts.SCHEMAS / name / version / f"{name}.schema.json"
    return json_response(json.loads(path.read_text(encoding="utf-8")))


def _unit_contracts():
    unit = json.loads((contracts.SCHEMAS.parent / "unit.json").read_text(encoding="utf-8"))
    return unit["provides"]["contracts"]


@endpoint
async def projects(request: Request) -> Response:
    state = _state(request)
    with state.db_lock:
        return json_response(list_document(state.registry.list()))


@endpoint
async def project(request: Request) -> Response:
    state = _state(request)
    with state.db_lock:
        return json_response(state.registry.get(request.path_params["project_id"]).document())


@endpoint
async def add_project(request: Request) -> Response:
    """``{path}``: a bearer client (the CLI) adds at once; a browser session confirms first (it grants trust)."""
    state = _state(request)
    body = await read_json(request, allowed={"path", "confirm_token"})
    path = body.get("path")
    if not isinstance(path, str) or not path or "\x00" in path or not os.path.isabs(path):
        raise GuiError("INPUT_INVALID", "path must be an absolute folder path",
                       issues=[{"pointer": "/path", "code": "type", "message": "expected an absolute path"}])
    auth = request.scope["state"]["auth"]
    if auth == "cookie":
        target = os.path.realpath(path)
        confirm.require(state, "project.add", {"path": target}, body.get("confirm_token"), risk="medium",
                        summary=f"Trust the project at {target}: commands of the catalog may run inside it.")
    with state.db_lock:
        added = state.registry.add(path, source="open" if auth == "bearer" else "user")
    return json_response(added.document(), 201)


@endpoint
async def session_token(request: Request) -> Response:
    """A new one-time browser URL; only for the bearer of the session secret (the CLI, the desktop shell)."""
    if request.scope["state"]["auth"] != "bearer":
        raise GuiError("PERMISSION_DENIED", "only the session secret may issue browser tokens")
    await read_json(request, allowed=set())
    state = _state(request)
    return json_response({"url": state.url(state.sessions.new_token())}, 201)


async def exchange(request: Request) -> Response:
    """``GET /?t=<token>``: redeem a one-time token for the session cookie and go to ``/`` (303)."""
    state = _state(request)
    tokens = parse_qs(request.url.query).get("t", [])
    cookie = state.sessions.redeem(tokens[0]) if len(tokens) == 1 else None
    if cookie is None:
        from .security import UNAUTHENTICATED_PAGE
        return Response(UNAUTHENTICATED_PAGE, status_code=401, media_type="text/html")
    response = Response(status_code=303, headers={"location": "/"})
    response.headers.append("set-cookie", f"{COOKIE}={cookie}; HttpOnly; SameSite=Strict; Path=/")
    return response


ROUTES = [
    Route("/v1/bootstrap", bootstrap, methods=["GET"]),
    Route("/v1/ui/contributions", contributions, methods=["GET"]),
    Route("/v1/schemas/{contract}/{version}", schema, methods=["GET"]),
    Route("/v1/projects", projects, methods=["GET"]),
    Route("/v1/projects", add_project, methods=["POST"]),
    Route("/v1/projects/{project_id}", project, methods=["GET"]),
    Route("/v1/session/tokens", session_token, methods=["POST"]),
]
