"""Configuration editor: ``/v1/config*`` (contracts ``config-view/v1`` and ``config-mutation/v1``).

The service blocks on files and on the layer lock, so every call runs in a worker thread. A layer that the GUI may
not write is refused before the body is read; the body of a preview or a commit is checked by its contract.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .. import contracts
from ..core.config import WRITABLE_LAYERS
from ..errors import GuiError
from .errors import endpoint, json_response, read_json

MUTATION = "config-mutation"
_MODULE = re.compile(r"^[a-z][a-z0-9-]*$")


def _state(request: Request):
    return request.app.state.backend


def _module(request: Request) -> str:
    module = request.path_params["module"]
    if not _MODULE.match(module):
        raise GuiError("NOT_FOUND", f"no module {module!r} with a configuration schema")
    return module


def _project(request: Request, *, required: bool = False) -> Tuple[Optional[str], Optional[str]]:
    """``(project_id, real root)`` of the ``project_id`` query parameter; ``NOT_FOUND`` for an unknown project."""
    project_id = request.query_params.get("project_id")
    if project_id is None:
        if required:
            raise GuiError("INPUT_INVALID", "the project layer needs project_id",
                           issues=[{"pointer": "/project_id", "code": "required", "message": "pass ?project_id="}])
        return None, None
    state = _state(request)
    with state.db_lock:
        return project_id, str(state.registry.resolve(project_id))


def _body(document: Dict[str, Any], kind: str) -> Dict[str, Any]:
    problems = contracts.validate(document, MUTATION)
    if problems or document.get("kind") != kind:
        raise GuiError("INPUT_INVALID", f"the body is not a {MUTATION}/v1 {kind}",
                       issues=[{"pointer": issue.path, "code": issue.code, "message": issue.message}
                               for issue in problems[:50]]
                       or [{"pointer": "/kind", "code": "const", "message": kind}])
    return document


@endpoint
async def modules(request: Request) -> Response:
    return json_response(await run_in_threadpool(_state(request).config.modules))


@endpoint
async def effective(request: Request) -> Response:
    state = _state(request)
    module = _module(request)
    project_id, root = _project(request)
    return json_response(await run_in_threadpool(state.config.view, module, root, project_id))


@endpoint
async def preview(request: Request) -> Response:
    state = _state(request)
    module = _module(request)
    body = _body(await read_json(request), "preview_request")
    project_id, root = _project(request, required=body.get("layer") == "project")
    return json_response(await run_in_threadpool(state.config.preview, module, root, project_id, body))


@endpoint
async def commit(request: Request) -> Response:
    state = _state(request)
    module = _module(request)
    layer = request.path_params["layer"]
    if layer not in WRITABLE_LAYERS:
        raise GuiError("CONFIG_LAYER_FORBIDDEN", f"layer {layer!r} cannot be written from the GUI; "
                                                 f"use {' or '.join(WRITABLE_LAYERS)}")
    body = _body(await read_json(request), "commit_request")
    project_id, root = _project(request, required=layer == "project")
    return json_response(await run_in_threadpool(state.config.commit, module, layer, root, project_id, body))


ROUTES = [
    Route("/v1/config", modules, methods=["GET"]),
    Route("/v1/config/{module}/effective", effective, methods=["GET"]),
    Route("/v1/config/{module}/preview", preview, methods=["POST"]),
    Route("/v1/config/{module}/layers/{layer}", commit, methods=["PATCH"]),
]
