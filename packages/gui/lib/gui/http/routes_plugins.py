"""Plugin trust: ``/v1/plugins*`` (contract ``plugin-api/v1``, decision D25).

The routes only translate: every decision, every transaction and every event belongs to the ``PluginHost`` of the
backend state. A grant and a Disable that has runs to wait for are confirmed first (``428`` with ``details.confirm``,
purposes ``plugin.grant`` and ``plugin.disable``); the token is bound to the plugin and the parameters, and a grant
token also to the manifest digest the operator saw, so a manifest that changed in between asks again.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .. import contracts
from ..errors import GuiError
from . import confirm
from .errors import endpoint, json_response, read_json

CONTRACT = "urn:swissknifeman:gui:plugin-api:v1"
KIND = "plugin-api"
_PLUGIN = re.compile(r"^[a-z][a-z0-9-]*$")
_GRANT = re.compile(r"^grant-[0-9a-f]{32}$")
HISTORY_MAX = 200


def _state(request: Request):
    return request.app.state.backend


def _plugin_id(request: Request) -> str:
    plugin = request.path_params["plugin_id"]
    if not _PLUGIN.match(plugin):
        raise GuiError("NOT_FOUND", f"no plugin {plugin!r}")
    return plugin


def _project(request: Request) -> Optional[str]:
    """The ``project_id`` query parameter; ``NOT_FOUND`` for an unknown project."""
    project_id = request.query_params.get("project_id")
    if project_id is not None:
        state = _state(request)
        with state.db_lock:
            state.registry.get(project_id)
    return project_id


def _body(document: Dict[str, Any], kind: str) -> Dict[str, Any]:
    problems = contracts.validate(document, KIND)
    if problems or document.get("kind") != kind:
        raise GuiError("INPUT_INVALID", f"the body is not a {KIND}/v1 {kind}",
                       issues=[{"pointer": issue.path, "code": issue.code, "message": issue.message}
                               for issue in problems[:50]] or [{"pointer": "/kind", "code": "const", "message": kind}])
    return document


async def _action_body(request: Request) -> Dict[str, Any]:
    """An ``action_request``; an empty body means one without ``confirm``."""
    document = await read_json(request)
    return _body(document or {"$schema": CONTRACT, "kind": "action_request"}, "action_request")


def _result(state, plugin: str, drained: int = 0, cancelled: int = 0, project_id: Optional[str] = None) -> Dict[str, Any]:
    return {"$schema": CONTRACT, "kind": "action_result", "plugin": state.plugins.view(plugin, project_id),
            "drained": drained, "cancelled": cancelled}


@endpoint
async def plugin_list(request: Request) -> Response:
    state = _state(request)
    return json_response({"$schema": CONTRACT, "kind": "plugin_list", "plugins": state.plugins.views(_project(request))})


@endpoint
async def plugin(request: Request) -> Response:
    return json_response(_state(request).plugins.view(_plugin_id(request), _project(request)))


@endpoint
async def history(request: Request) -> Response:
    state = _state(request)
    plugin_id = _plugin_id(request)
    try:
        limit = int(request.query_params.get("limit", "50"))
    except ValueError:
        raise GuiError("INPUT_INVALID", "limit must be an integer") from None
    if not 1 <= limit <= HISTORY_MAX:
        raise GuiError("INPUT_INVALID", f"limit must be 1..{HISTORY_MAX}",
                       issues=[{"pointer": "/limit", "code": "range", "message": f"1..{HISTORY_MAX}"}])
    return json_response({"$schema": CONTRACT, "kind": "plugin_history", "plugin": plugin_id,
                          "entries": state.plugins.history(plugin_id, limit)})


@endpoint
async def enable(request: Request) -> Response:
    state = _state(request)
    plugin_id = _plugin_id(request)
    await _action_body(request)
    await state.plugins.enable(plugin_id)
    return json_response(_result(state, plugin_id))


@endpoint
async def disable(request: Request) -> Response:
    state = _state(request)
    plugin_id = _plugin_id(request)
    body = await _action_body(request)
    state.plugins.view(plugin_id)  # NOT_FOUND before anything else
    active = state.plugins.active_runs(plugin_id)
    if active:
        timeout = state.settings.plugins.drain_timeout_s
        confirm.require(state, "plugin.disable", {"plugin": plugin_id}, body.get("confirm"), risk="medium",
                        summary=f"Disable {plugin_id}: {len(active)} active run(s) are waited for up to {timeout} s, "
                                "then cancelled.")
    outcome = await state.plugins.disable(plugin_id)
    return json_response(_result(state, plugin_id, outcome["drained"], outcome["cancelled"]))


@endpoint
async def release(request: Request) -> Response:
    state = _state(request)
    plugin_id = _plugin_id(request)
    await _action_body(request)
    state.plugins.release(plugin_id)
    return json_response(_result(state, plugin_id))


@endpoint
async def grant(request: Request) -> Response:
    state = _state(request)
    plugin_id = _plugin_id(request)
    body = _body(await read_json(request), "grant_request")
    project_id = body["project_id"]
    if project_id is not None:
        with state.db_lock:
            try:
                state.registry.get(project_id)
            except GuiError:
                raise GuiError("INPUT_INVALID", f"no registered project {project_id!r}",
                               issues=[{"pointer": "/project_id", "code": "unknown", "message": "not a project"}]) \
                    from None
    current = state.plugins.view(plugin_id)
    declared = {entry["effect"] for entry in current["permissions"] if entry["declared"]}
    if current["source"] != "extension" or body["capability"] in ("read", "terminal") \
            or body["capability"] not in declared:
        raise GuiError("INPUT_INVALID", f"{body['capability']!r} is not a grantable effect of {plugin_id!r}",
                       issues=[{"pointer": "/capability", "code": "enum", "message": "not a grantable effect"}])
    digest = current["manifest_digest"]
    where = "every project" if project_id is None else f"project {project_id}"
    expires = body["expires_at"] or "never"
    confirm.require(state, "plugin.grant", {"plugin": plugin_id, "capability": body["capability"],
                                            "project_id": project_id, "expires_at": body["expires_at"],
                                            "manifest_digest": digest},
                    body.get("confirm"), risk="high" if project_id is None else "medium",
                    summary=f"Let {plugin_id} use {body['capability']} in {where} until {expires} "
                            f"(manifest {digest[:19]}).")
    granted_by = "browser" if request.scope["state"]["auth"] == "cookie" else "cli"
    made = state.plugins.grant(plugin_id, body["capability"], project_id, body["expires_at"], granted_by=granted_by,
                               digest=digest)
    return json_response({"$schema": CONTRACT, "kind": "grant_result", "plugin": state.plugins.view(plugin_id, project_id),
                          "grant": made}, 201)


@endpoint
async def revoke(request: Request) -> Response:
    state = _state(request)
    plugin_id = _plugin_id(request)
    grant_id = request.path_params["grant_id"]
    if not _GRANT.match(grant_id):
        raise GuiError("NOT_FOUND", f"no grant {grant_id!r}")
    await _action_body(request)
    state.plugins.revoke(plugin_id, grant_id)
    return json_response(_result(state, plugin_id))


# The action routes come first: ``{plugin_id}`` would otherwise swallow ``x:enable`` of the detail route.
ROUTES = [
    Route("/v1/plugins/{plugin_id}:enable", enable, methods=["POST"]),
    Route("/v1/plugins/{plugin_id}:disable", disable, methods=["POST"]),
    Route("/v1/plugins/{plugin_id}:release", release, methods=["POST"]),
    Route("/v1/plugins/{plugin_id}/grants/{grant_id}:revoke", revoke, methods=["POST"]),
    Route("/v1/plugins/{plugin_id}/grants", grant, methods=["POST"]),
    Route("/v1/plugins/{plugin_id}/history", history, methods=["GET"]),
    Route("/v1/plugins/{plugin_id}", plugin, methods=["GET"]),
    Route("/v1/plugins", plugin_list, methods=["GET"]),
]
