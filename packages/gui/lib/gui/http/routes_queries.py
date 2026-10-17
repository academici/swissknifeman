"""``POST /v1/queries/{id}``: run a read-only query of an accepted contribution through its handler (D7).

The handler is an aicore command plugin called at ``gui:query`` with ``{id, context, params}`` by ``invoke_one`` in
a worker thread. Its output passes, in order: the size limit (``query.max_output_bytes``), ``view-data/v1``, the
view the query declares, then redaction of secret values — only then does it reach the client (I6).
"""
from __future__ import annotations

import dataclasses
import re
import time
from typing import Any, Dict, Optional, Tuple

import anyio
from aicore.ext import settings as ext_settings
from aicore.ext.errors import ExtError
from aicore.ext.plugins import Registration, load_manifest, registered_plugins
from aicore.config import ConfigError
from aicore.util.digest import canonical_json_bytes
from aicore.util.redact import redact_document
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .. import contracts
from ..core import inputs
from ..errors import GuiError
from .errors import endpoint, json_response, read_json

POINT = "gui:query"
TIMEOUT_CODES = frozenset({"PROCESS_TIMEOUT", "PLUGIN_TIMEOUT"})
CONTEXT_KEYS = ("project_id", "plan_id", "item_id", "run_id")
_RUN_ID = re.compile(r"^run-[0-9a-f]{32}$")
_limiter: Optional[anyio.CapacityLimiter] = None


def limiter() -> anyio.CapacityLimiter:
    global _limiter
    if _limiter is None:
        _limiter = anyio.CapacityLimiter(8)
    return _limiter


def check_context(state, scope: str, context: Any) -> Tuple[Dict[str, str], Optional[str]]:
    """The validated context and the real project root (or ``None``) of a query or command of ``scope``."""
    if context is None:
        context = {}
    if not isinstance(context, dict):
        raise GuiError("INPUT_INVALID", "context must be an object",
                       issues=[{"pointer": "/context", "code": "type", "message": "expected an object"}])
    issues = [{"pointer": f"/context/{name}", "code": "additional", "message": "unknown context field"}
              for name in sorted(set(context) - set(CONTEXT_KEYS))]
    checks = {"plan_id": inputs.REF_PATTERNS["plan-ref"], "item_id": inputs.REF_PATTERNS["item-ref"],
              "run_id": _RUN_ID}
    for name in CONTEXT_KEYS:
        value = context.get(name)
        if value is None:
            continue
        if not isinstance(value, str) or (name in checks and not checks[name].match(value)):
            issues.append({"pointer": f"/context/{name}", "code": "pattern", "message": f"invalid {name}"})
    needed = {"project": ("project_id",), "plan": ("project_id", "plan_id"),
              "item": ("project_id", "plan_id", "item_id"), "run": ("run_id",)}.get(scope, ())
    for name in needed:
        if context.get(name) is None:
            issues.append({"pointer": f"/context/{name}", "code": "required",
                           "message": f"a {scope} query needs {name}"})
    if issues:
        raise GuiError("INPUT_INVALID", "invalid context", issues=issues)
    root = None
    if context.get("project_id") is not None:
        with state.db_lock:
            root = str(state.registry.resolve(context["project_id"]))
    return {name: context[name] for name in CONTEXT_KEYS if context.get(name) is not None}, root


def registration(state, owner: str, timeout_s: int, project_root: Optional[str]) -> Registration:
    """The plugin registration of the owner's handler: a hub unit is trusted by its place in the hub; an
    extension comes from ``[aicore.plugins]`` as configured (enabled, trusted, usable)."""
    entry = state.catalog.owners.get(owner)
    if entry is None or entry.handler is None:
        raise GuiError("PLUGIN_UNAVAILABLE", f"{owner} has no handler")
    try:
        manifest = load_manifest(entry.handler)
    except ExtError as error:
        raise GuiError("PLUGIN_UNAVAILABLE", f"the handler of {owner} is not usable: {error.code}") from None
    if entry.source.kind == "unit":
        return Registration(id=manifest.id, manifest_path=str(entry.handler), trusted=True,
                            timeout_seconds=timeout_s, enabled=True, manifest=manifest, problem=None)
    try:
        found, _problems = registered_plugins(ext_settings.load(project_root, env=dict(state.env)),
                                              env=dict(state.env))
    except (ExtError, ConfigError, OSError):
        raise GuiError("PLUGIN_UNAVAILABLE", "the plugin configuration cannot be read") from None
    for candidate in found:
        if candidate.id == manifest.id and candidate.usable:
            return dataclasses.replace(candidate, timeout_seconds=timeout_s)
    raise GuiError("PLUGIN_UNAVAILABLE", f"extension {manifest.id} is not enabled or not usable")


def check_output(state, output: Any, returns: str) -> Any:
    if len(canonical_json_bytes(output)) > state.settings.query.max_output_bytes:
        raise GuiError("OUTPUT_INVALID", f"the answer is larger than {state.settings.query.max_output_bytes} bytes")
    issues = contracts.validate(output, "view-data")
    if issues:
        raise GuiError("OUTPUT_INVALID", "the answer is not view-data/v1",
                       details={"issue": f"{issues[0].path}: {issues[0].code}"})
    if output.get("view") != returns:
        raise GuiError("OUTPUT_INVALID", f"the answer is a {output.get('view')} view, the query returns {returns}")
    return redact_document(output, secrets=state.secrets())


@endpoint
async def run_query(request: Request) -> Response:
    state = request.app.state.backend
    query_id = request.path_params["query_id"]
    found = state.catalog.queries.get(query_id)
    if found is None:
        raise GuiError("NOT_FOUND", f"no query {query_id!r} in the catalog")
    owner, query = found
    body = await read_json(request, allowed={"context", "params"})
    context, root = check_context(state, query["scope"], body.get("context"))
    params = inputs.validate(query.get("params", ()), body.get("params"), root, pointer="/params")
    cache_s = int(query.get("cache_s", 0))
    key = (owner, query_id, canonical_json_bytes(context).decode(), canonical_json_bytes(params).decode())
    if cache_s > 0:
        cached = state.query_cache.get(key)
        if cached is not None and cached[0] > time.monotonic() and state.plugins.visible(owner):
            return json_response(cached[1])
    ticket = state.plugins.admit(owner, "query", ["read"], context.get("project_id"))
    code, judged = None, False  # judged: the outcome says something about the plugin (a failure or a success)
    try:
        plugin = registration(state, owner, int(query.get("timeout_s", 30)), root)
        payload = {"id": query_id, "context": context, "params": params}
        result = await anyio.to_thread.run_sync(
            lambda: ticket.invoke(plugin, POINT, payload, env=state.env, project=root), limiter=limiter())
        if result.status != "ok":
            code, judged = result.code or result.status, True
            if code in TIMEOUT_CODES:
                raise GuiError("HANDLER_TIMEOUT", f"the handler of {owner} did not answer in {plugin.timeout_seconds} s")
            raise GuiError("HANDLER_FAILED", f"the handler of {owner} failed", details={"plugin_code": str(code)[:64]})
        try:
            output = check_output(state, result.output, query["returns"])
        except GuiError:
            code, judged = "OUTPUT_INVALID", True
            raise
        judged = True
    finally:
        ticket.finish(code, cancelled=not judged)
    if cache_s > 0:
        state.query_cache[key] = (time.monotonic() + cache_s, output)
    return json_response(output)


ROUTES = [Route("/v1/queries/{query_id}", run_query, methods=["POST"])]
