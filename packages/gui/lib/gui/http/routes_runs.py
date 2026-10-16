"""Commands and runs: ``/v1/commands``, ``/v1/commands/{id}/runs``, ``/v1/runs*`` (contract ``run-api/v1``).

The client sends only typed input (I2): the command is looked up in the accepted catalog, the context and input are
checked, a risky run is confirmed first (``428`` with ``details.confirm``), and the broker builds the argv from the
descriptor.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, Optional

from aicore.config import ConfigError
from aicore.ext import settings as ext_settings
from aicore.ext.errors import ExtError
from aicore.ext.plugins import invoke_one, registered_plugins
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .. import contracts
from ..core import inputs, run_states
from ..core.runs import read_log
from ..errors import GuiError
from . import confirm
from .errors import endpoint, json_response, read_json
from .routes_queries import check_context, registration

CONTRACT = "urn:swissknifeman:gui:run-api:v1"
_RUN_ID = re.compile(r"^run-[0-9a-f]{32}$")
_ID = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$")


def _state(request: Request):
    return request.app.state.backend


def _issues(problems) -> list:
    return [{"pointer": issue.path, "code": issue.code, "message": issue.message} for issue in problems[:50]]


def command_entry(owner: str, command: Dict[str, Any]) -> Dict[str, Any]:
    entry = {"owner": owner, "exec_kind": command["exec"]["kind"]}
    for name in ("id", "title", "description", "scope", "input", "effects", "risk", "confirmation", "supports",
                 "timeout_s"):
        if name in command:
            entry[name] = command[name]
    return entry


@endpoint
async def commands(request: Request) -> Response:
    state = _state(request)
    scope = request.query_params.get("scope")
    project_id = request.query_params.get("project_id")
    if project_id is not None:
        with state.db_lock:
            state.registry.get(project_id)
    listed = [command_entry(owner, command) for _id, (owner, command) in sorted(state.catalog.commands.items())
              if scope is None or command["scope"] == scope]
    listed.sort(key=lambda entry: (entry["owner"], entry["id"]))
    return json_response({"$schema": CONTRACT, "kind": "command_list", "commands": listed})


def _trusted(state, owner: str, root: Optional[str]) -> bool:
    """A hub unit is trusted by its place in the hub; an extension only when ``[aicore.plugins]`` trusts it."""
    entry = state.catalog.owners[owner]
    if entry.source.kind == "unit":
        return True
    try:
        found, _problems = registered_plugins(ext_settings.load(root, env=dict(state.env)), env=dict(state.env))
    except (ExtError, ConfigError, OSError):
        return False
    return any(candidate.id == owner and candidate.usable and candidate.trusted for candidate in found)


def needs_confirmation(command: Dict[str, Any], dry_run: bool) -> bool:
    mode = command["confirmation"]
    return mode == "always" or (mode == "risk-based" and command["risk"] in ("medium", "high") and not dry_run)


@endpoint
async def start_run(request: Request) -> Response:
    state = _state(request)
    command_id = request.path_params["command_id"]
    found = state.catalog.commands.get(command_id)
    if found is None:
        raise GuiError("NOT_FOUND", f"no command {command_id!r} in the catalog")
    owner, command = found
    body = await read_json(request)
    problems = contracts.validate(body, "run-api")
    if problems or body.get("kind") != "run_request":
        raise GuiError("INPUT_INVALID", "the body is not a run-api/v1 run_request",
                       issues=_issues(problems) or [{"pointer": "/kind", "code": "const", "message": "run_request"}])
    context, root = check_context(state, command["scope"], body["context"])
    dry_run = bool(body["dry_run"])
    if dry_run and "dry-run" not in command.get("supports", ()):
        raise GuiError("INPUT_INVALID", f"command {command_id} has no dry run",
                       issues=[{"pointer": "/dry_run", "code": "unsupported", "message": "no dry run"}])
    values = inputs.validate(command.get("input", ()), body["input"], root, pointer="/input")
    confirmed = needs_confirmation(command, dry_run)
    if confirmed:
        confirm.require(state, "command.run", {"command": command_id, "context": context, "input": values,
                                               "dry_run": dry_run}, body.get("confirm"), risk=command["risk"],
                        summary=f"Run {command['title']} ({command_id}) of {owner} with risk {command['risk']}"
                                + (f" in project {context['project_id']}" if "project_id" in context else ""))
    entry = state.catalog.owners[owner]
    invoke = None
    if command["exec"]["kind"] == "invoke":
        plugin = registration(state, owner, int(command["timeout_s"]), root)
        payload = {"id": command_id, "context": context, "input": values}
        env = dict(state.env)

        def invoke():
            return invoke_one(plugin, "gui:command", payload, env=env, project=root)

    actor = {"kind": "user", "id": "browser" if request.scope["state"]["auth"] == "cookie" else "cli"}
    run = await state.broker.submit(owner=owner, owner_root=entry.source.root, trusted=_trusted(state, owner, root),
                                    command=command, context=context, project_root=root, values=values,
                                    dry_run=dry_run, confirmed=confirmed, correlation_id=uuid.uuid4().hex,
                                    actor=actor, invoke=invoke)
    return json_response(run, 202)


def _run_id(request: Request) -> str:
    run_id = request.path_params["run_id"]
    if not _RUN_ID.match(run_id):
        raise GuiError("NOT_FOUND", f"no run {run_id!r}")
    return run_id


@endpoint
async def runs(request: Request) -> Response:
    state = _state(request)
    params = request.query_params
    run_state = params.get("state")
    if run_state is not None and run_state not in run_states.STATES:
        raise GuiError("INPUT_INVALID", f"unknown state {run_state!r}",
                       issues=[{"pointer": "/state", "code": "enum", "message": "not a run state"}])
    try:
        limit = min(max(int(params.get("limit", "50")), 1), 200)
    except ValueError:
        raise GuiError("INPUT_INVALID", "limit must be an integer") from None
    page = state.store.list(project_id=params.get("project_id"), state=run_state, limit=limit,
                            before=params.get("cursor"))
    document: Dict[str, Any] = {"$schema": CONTRACT, "kind": "run_list", "runs": page}
    if len(page) == limit:
        document["next_cursor"] = f"{page[-1]['created_at']}|{page[-1]['run_id']}"
    return json_response(document)


@endpoint
async def run(request: Request) -> Response:
    run_id = _run_id(request)
    try:
        return json_response(_state(request).store.get(run_id))
    except KeyError:
        raise GuiError("NOT_FOUND", f"no run {run_id}") from None


@endpoint
async def cancel(request: Request) -> Response:
    run_id = _run_id(request)
    await read_json(request, allowed=set())
    return json_response(await _state(request).broker.cancel(run_id))


@endpoint
async def run_log(request: Request) -> Response:
    state = _state(request)
    run_id = _run_id(request)
    try:
        current = state.store.get(run_id)
    except KeyError:
        raise GuiError("NOT_FOUND", f"no run {run_id}") from None
    params = request.query_params
    stream = params.get("stream", "stdout")
    if stream not in ("stdout", "stderr"):
        raise GuiError("INPUT_INVALID", "stream is stdout or stderr",
                       issues=[{"pointer": "/stream", "code": "enum", "message": "stdout or stderr"}])
    try:
        cursor = max(int(params.get("cursor", "0")), 0)
        limit = min(max(int(params.get("limit", "200")), 1), 1000)
    except ValueError:
        raise GuiError("INPUT_INVALID", "cursor and limit must be integers") from None
    chunks = read_log(state.runs_dir, run_id, stream, cursor, limit)
    following = chunks[-1]["chunk"] + 1 if chunks else cursor
    finished = run_states.is_terminal(current["state"]) and len(chunks) < limit
    return json_response({"$schema": CONTRACT, "kind": "log_page", "run_id": run_id, "stream": stream,
                          "chunks": chunks, "next_cursor": None if finished else following})


ROUTES = [
    Route("/v1/commands", commands, methods=["GET"]),
    Route("/v1/commands/{command_id}/runs", start_run, methods=["POST"]),
    Route("/v1/runs", runs, methods=["GET"]),
    Route("/v1/runs/{run_id}:cancel", cancel, methods=["POST"]),
    Route("/v1/runs/{run_id}/log", run_log, methods=["GET"]),
    Route("/v1/runs/{run_id}", run, methods=["GET"]),
]
