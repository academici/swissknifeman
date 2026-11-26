"""Synchronous MCP request dispatch over stdio NDJSON."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, TextIO
from uuid import UUID

from skm import __version__
from skm.application_bus.client import SkmClient
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, SkmError
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.access.public import WhoAmIView
from skm.platform.logging.logger import get_logger
from skm.platform.schema.registry import SchemaRegistry

from . import protocol, registry
from .registry import ToolSpec
from .session import McpSession
from .truncation import AUTHORING_READS, AuthoringReceipts

if TYPE_CHECKING:
    from skm.bootstrap.composition import App

__all__ = ["serve", "serve_stage"]

_LOG = get_logger("entrypoints.mcp")
_FETCH = "skm_fetch"
_FETCH_INPUT = "urn:skm:mcp:tool-input:fetch:v1"
_FETCH_OUTPUT = "urn:skm:mcp:tool-output:fetch:v1"


def _tool_result(payload: JsonValue, *, is_error: bool = False) -> JsonObject:
    body = protocol.json_text(payload)
    body.encode("utf-8")
    return {"content": [{"type": "text", "text": body}], "isError": is_error}


def _invalid_params(name: str, issues: list[JsonValue]) -> protocol.RpcError:
    return protocol.RpcError(protocol.INVALID_PARAMS, f"invalid params for {name}", data={"issues": issues})


class _Server:
    def __init__(self, session: McpSession, schemas: SchemaRegistry) -> None:
        self.session = session
        self.schemas = schemas
        self.receipts = AuthoringReceipts()

    def _arguments(self, name: str, schema: str, value: JsonValue) -> JsonObject:
        issues = self.schemas.validate(schema, value)
        if issues:
            raise _invalid_params(name, [issue.to_json() for issue in issues])
        if not isinstance(value, dict):
            raise ValueError("MCP tool input schemas must require an object")
        return value

    def _run(self, tool: ToolSpec, arguments: JsonObject) -> JsonValue:
        payload = tool.handler(self.session, arguments)
        self._validate_output(tool.output_schema_urn, payload)
        return payload

    def _validate_output(self, schema: str, payload: JsonValue) -> None:
        if self.schemas.validate(schema, payload):
            raise ValueError("MCP handler returned a result outside its output schema")

    def _fetch(self, tools: tuple[ToolSpec, ...], identity: WhoAmIView, arguments: JsonValue) -> JsonValue:
        if not self.session.allows_tool(_FETCH):
            raise Forbidden(ErrorCode.FORBIDDEN, f"Access denied for {_FETCH}")
        args = self._arguments(_FETCH, _FETCH_INPUT, arguments)
        if not any(tool.permitted(self.session, identity) for tool in tools):
            raise Forbidden(ErrorCode.FORBIDDEN, "An authoring read permission is required")
        token = args["receipt"]
        if not isinstance(token, str):
            raise ValueError("MCP receipt schema must require a string")
        receipt = self.receipts.get(token)
        tool = registry.lookup_tool(tools, receipt.tool)
        if tool is None:
            raise protocol.RpcError(protocol.METHOD_NOT_FOUND, "unknown tool")
        if not tool.permitted(self.session, identity):
            raise Forbidden(ErrorCode.FORBIDDEN, f"Access denied for {tool.name}")
        bound = self._arguments(tool.name, tool.input_schema_urn, receipt.arguments)
        limit = self.session.max_response_tokens
        payload = self._run(tool, bound)
        rendered = self.receipts.render(tool.name, bound, payload, limit, resume=receipt)
        self._validate_output(_FETCH_OUTPUT, rendered)
        return rendered

    def _call(self, params: JsonObject) -> JsonObject:
        name = params.get("name")
        if not isinstance(name, str):
            raise _invalid_params(
                "tools/call", [{"pointer": "/name", "code": "type", "message": "expected a tool name"}]
            )

        try:
            # Before any tool (including continuation) can run, re-admit the credential and its project.
            identity = self.session.refresh()
            arguments = params.get("arguments", {})
            if name == _FETCH:
                reads = tuple(
                    tool
                    for tool in registry.TOOLS
                    if tool.name in AUTHORING_READS
                    and tool.visible_in(self.session)
                    and tool.enabled(identity)
                )
                if reads:
                    return _tool_result(self._fetch(reads, identity, arguments))
            tool = registry.lookup_tool(registry.TOOLS, name)
            if tool is None or not tool.visible_in(self.session):
                raise protocol.RpcError(protocol.METHOD_NOT_FOUND, f"unknown tool: {name}")
            permitted = tool.permitted(self.session, identity)
            if not tool.enabled(identity):
                if self.session.is_assignment and not permitted:
                    raise Forbidden(ErrorCode.FORBIDDEN, f"Access denied for {tool.name}")
                raise PreconditionFailed(
                    ErrorCode.MODULE_DISABLED,
                    f"Module {tool.module} is disabled",
                    details={"module": tool.module},
                )
            args = self._arguments(name, tool.input_schema_urn, arguments)
            if not permitted:
                raise Forbidden(ErrorCode.FORBIDDEN, f"Access denied for {tool.name}")
            limit = self.session.max_response_tokens
            payload = self._run(tool, args)
            rendered = self.receipts.render(name, args, payload, limit)
            self._validate_output(tool.output_schema_urn, rendered)
            return _tool_result(rendered)
        except SkmError as error:
            problem = error.to_problem()
            problem.pop("retryable")
            return _tool_result({"error": problem}, is_error=True)

    def dispatch(self, request: protocol.Request) -> JsonObject:
        method = request.method
        if method not in {"initialize", "ping", "tools/list", "tools/call"}:
            raise protocol.RpcError(protocol.METHOD_NOT_FOUND, f"unknown method: {method}")
        params = request.params
        if not isinstance(params, dict):
            raise _invalid_params(
                method, [{"pointer": "", "code": "type", "message": "expected a params object"}]
            )
        if method == "initialize":
            payload: JsonObject = {
                "protocolVersion": protocol.negotiate_version(params.get("protocolVersion")),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "skm", "version": __version__},
                "instructions": (
                    f"SKM project {self.session.project_id}. Permissions come from the session token."
                ),
            }
        elif method == "tools/list":
            payload = {"tools": [*registry.published_tools(self.session, self.schemas)]}
        elif method == "tools/call":
            payload = self._call(params)
        else:
            payload = {}
        return protocol.result(request.request_id, payload)


def _respond(server: _Server, message: JsonValue) -> JsonObject | None:
    try:
        request = protocol.Request.parse(message)
    except protocol.RpcError as error:
        return error.response(None)
    if request.notification or request.method == "notifications/initialized":
        return None
    try:
        return server.dispatch(request)
    except protocol.RpcError as error:
        return error.response(request.request_id)
    except Exception as error:  # noqa: BLE001 -- isolate unexpected handler failures from the stdio loop
        _LOG.error("mcp.dispatch_failed", exc=error)
        return protocol.RpcError(protocol.INTERNAL_ERROR, "Internal error").response(request.request_id)


def serve(app: App | None, session: McpSession, stdin: TextIO, stdout: TextIO) -> int:
    schemas = app.schemas if app is not None else SchemaRegistry.load_default()
    return _serve(_Server(session, schemas), stdin, stdout)


def serve_stage(
    client: SkmClient,
    project: UUID,
    tools: frozenset[str],
    admit: Callable[[], None],
    stdin: TextIO,
    stdout: TextIO,
) -> int:
    """Serve the existing tool registry with the worker's assignment credential in process."""
    session = McpSession.open(client, project_id=project)
    if not session.is_assignment:
        raise Forbidden(ErrorCode.FORBIDDEN, "Stage MCP requires assignment authority")
    return _serve(
        _Server(replace(session, stage_tools=tools), SchemaRegistry.load_default()), stdin, stdout, admit
    )


def _serve(server: _Server, stdin: TextIO, stdout: TextIO, admit: Callable[[], None] = lambda: None) -> int:
    while True:
        try:
            message = protocol.read_message(stdin)
        except EOFError:
            return 0
        except (ValueError, RecursionError):
            _LOG.warning("mcp.invalid_json")
            continue
        admit()
        response = _respond(server, message)
        if response is not None:
            protocol.write_message(stdout, response)
