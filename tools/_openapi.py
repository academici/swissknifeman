"""Render the OpenAPI resource from framework-free HTTP and bus declarations."""

import copy
import json
from collections.abc import Iterable, Mapping
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from skm import __version__
from skm.application_bus.registry import CommandSpec, IdempotencyMode, QuerySpec
from skm.bootstrap.modules import MANIFESTS, MODULE_CATALOG
from skm.bootstrap.platform_module import PLATFORM_MANIFEST
from skm.entrypoints.api.routing import (  # Reuse the HTTP binder's field resolution.
    Route,
    _dto_schema,  # pyright: ignore[reportPrivateUsage]
    _property,  # pyright: ignore[reportPrivateUsage]
    build_route_table,
)
from skm.platform.schema.registry import SchemaRegistry

from .codegen.model import CodegenError
from .codegen.parse import nodes

OUTPUT = Path("src/skm/entrypoints/api/openapi.json")
_PREFIX = "/api/v1"
_SCHEMAS = "#/components/schemas/"
_JSON = "application/json"
_BINARY = {"type": "string", "format": "binary"}
_UUID = {"type": "string", "format": "uuid"}
_STRING = {"type": "string"}
_AFTER = {"type": "integer", "minimum": 0}
_PROBLEM = {"$ref": "#/components/responses/Problem"}
_ETAG = {"$ref": "#/components/headers/ETag"}
_OPEN_OPERATIONS = frozenset(
    {
        ("get", "/health/live"),
        ("get", "/health/ready"),
        ("get", "/openapi.json"),
        ("get", "/auth/csrf"),
        ("post", "/auth/login"),
        ("post", "/auth/pairing/exchange"),
    }
)
_SESSION_ONLY_OPERATIONS = frozenset(
    {
        ("post", "/auth/logout"),
        ("post", "/auth/session/reload"),
    }
)
_BEARER_ONLY_OPERATIONS: frozenset[tuple[str, str]] = frozenset()
_SAFE_METHODS = frozenset({"get", "head", "options"})
_METADATA = {"$id", "$schema", "x-skm-codegen"}


def _reference(pointer: str) -> dict[str, str]:
    return {"$ref": pointer}


def _resolve(document: Mapping[str, Any], pointer: str) -> Any:
    try:
        if not pointer.startswith("#/"):
            raise ValueError(pointer)
        node: Any = document
        for token in unquote(pointer[2:]).split("/"):
            key = token.replace("~1", "/").replace("~0", "~")
            node = node[int(key)] if isinstance(node, list) else node[key]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise CodegenError(pointer, "Unresolved OpenAPI reference") from error
    return node


class _Components:
    def __init__(self, schemas: SchemaRegistry):
        self.registry = schemas
        self.schemas: dict[str, Any] = {}
        self.owners: dict[str, str] = {}
        self.references: set[str] = set()

    def ref(self, urn_ref: str, owner: str = "") -> dict[str, str]:
        base, _, fragment = urn_ref.partition("#")
        urn = base or owner
        if not urn.startswith("urn:skm:") or (fragment and not fragment.startswith("/")):
            raise CodegenError(owner or "paths", f"Unresolved OpenAPI reference {urn_ref}")
        name = urn.removeprefix("urn:skm:").replace(":", ".")
        existing = self.owners.get(name)
        if existing is None:
            if urn not in self.registry.urns():
                raise CodegenError(urn, "Unresolved OpenAPI schema")
            self.owners[name] = urn
            self.schemas[name] = self.copy_schema(self.registry.get(urn), urn)
        elif existing != urn:
            raise CodegenError(name, f"OpenAPI component name collision for {existing} and {urn}")
        pointer = _SCHEMAS + name + fragment
        self.references.add(pointer)
        return _reference(pointer)

    def copy_schema(self, schema: Mapping[str, Any], owner: str) -> dict[str, Any]:
        result = copy.deepcopy(dict(schema))
        for _, node in nodes(result):
            for keyword in _METADATA:
                node.pop(keyword, None)
            if isinstance(settings_key := node.get("x-skm"), dict) and "chain" in settings_key:
                # A settings key's default applies during server-side resolution.
                # Clients must not populate it when sending a settings document.
                node.pop("default", None)
            if "$ref" in node:
                node["$ref"] = self.ref(node["$ref"], owner)["$ref"]
        return result

    def resolve(self, pointer: str) -> Any:
        return _resolve({"components": {"schemas": self.schemas}}, pointer)

    def validate_refs(self) -> None:
        for pointer in sorted(self.references):
            if not isinstance(self.resolve(pointer), (dict, bool)):
                raise CodegenError(pointer, "OpenAPI reference does not identify a schema")


def _parameter(name: str, location: str, schema: Mapping[str, Any], *, required: bool = False):
    return {"name": name, "in": location, "required": required, "schema": schema}


def _header(name: str, schema: Mapping[str, Any], *, required: bool = False):
    return _parameter(name, "header", schema, required=required)


def _idempotency(required: bool) -> dict[str, str]:
    mode = "Required" if required else "Optional"
    return _reference(f"#/components/parameters/IdempotencyKey{mode}")


def _content(media: str, schema: Mapping[str, Any]) -> dict[str, Any]:
    return {"content": {media: {"schema": schema}}}


def _response(description: str, schema: Mapping[str, Any], media: str = _JSON, **fields: Any):
    return {"description": description, **_content(media, schema), **fields}


def _field_required(parts: Iterable[Any], field: str) -> bool:
    return any(field in shape.get("required", ()) for shape, _ in parts)


def _parameter_schema(route: Route, name: str, field: str, c: _Components) -> dict[str, Any]:
    parts = _property(c.registry, route.dto_type, field)
    properties = {key for part in parts for key in part.get("properties", {})}
    if {"kind", "id"} <= properties or {"level", "scope_id"} <= properties:
        return {"type": "string", "description": "Scope as instance or kind:UUID."}
    if name == "include" and field == "include_tree":
        return {"type": "string", "const": "tree"}
    return c.copy_schema(parts[0], route.dto_type.SCHEMA_URN)


def _route_parameters(route: Route, c: _Components) -> list[dict[str, Any]]:
    params = [
        _parameter(name, "path", _parameter_schema(route, name, field, c), required=True)
        for name, field in route.path_params.items()
    ]
    params.extend(_parameter(name, "path", _UUID, required=True) for name in route.path_guards)
    parts = tuple(_dto_schema(c.registry, route.dto_type))
    for name, field in route.query_params.items():
        schema = _parameter_schema(route, name, field, c)
        required = _field_required(parts, field)
        parameter = _parameter(name, "query", schema, required=required)
        if schema.get("type") == "array":
            # The array binders accept both repeated keys and comma-separated values.
            parameter.update(style="form", explode=True)
        params.append(parameter)
    if route.if_match_to is not None and route.effective_operation_id != "integrations_create_projection":
        mode = "Required" if route.requires_if_match(c.registry) else "Optional"
        params.append(_reference(f"#/components/parameters/IfMatch{mode}"))
    if route.idempotency != IdempotencyMode.FORBIDDEN:
        params.append(_idempotency(route.idempotency == IdempotencyMode.REQUIRED))
    if route.etag_from and route.method == "GET":
        params.append(_header("If-None-Match", _STRING))
    elif route.bus_name in {"settings.set_value", "settings.unset_value"}:
        params.append(_header("If-None-Match", {"type": "string", "const": "*"}))
    return params


def _without_field(shape: dict[str, Any], field: str, c: _Components) -> None:
    """Remove a transport-bound field from this object and its same-instance constraints."""
    name, dot, rest = field.partition(".")
    props = shape.get("properties", {})
    if dot and name in props:
        child = props[name]
        if "$ref" in child:
            target = c.resolve(child["$ref"])
            props[name] = child = copy.deepcopy(target) | {k: v for k, v in child.items() if k != "$ref"}
        _without_field(child, rest, c)
    elif not dot:
        props.pop(name, None)
        if name in shape.get("required", ()):
            shape["required"].remove(name)
    for key in ("allOf", "anyOf", "oneOf"):
        for branch in shape.get(key, ()):
            if isinstance(branch, dict):
                _without_field(branch, field, c)
    for key in ("if", "then", "else", "not"):
        if isinstance(branch := shape.get(key), dict):
            _without_field(branch, field, c)


def _request_body(route: Route, c: _Components) -> dict[str, Any]:
    urn = route.dto_type.SCHEMA_URN
    uri = c.ref(urn)["$ref"]
    bound = [*route.path_params.values(), *route.query_params.values()]
    if route.if_match_to is not None and route.requires_if_match(c.registry):
        bound.append(route.if_match_to)
    elif route.effective_operation_id == "integrations_create_projection":
        bound.append("base_row_version")
    elif route.effective_operation_id == "settings_put_project_config":
        bound.append("scope")
    description = c.resolve(uri)
    media = "application/merge-patch+json" if route.body == "merge_patch" else _JSON
    if route.body == "merge_patch" and "merge_patch" in description.get("properties", {}):
        return {"required": True, **_content(media, c.ref(urn + "#/properties/merge_patch"))}

    shape = copy.deepcopy(description)
    for field in bound:
        _without_field(shape, field, c)
    payload: dict[str, Any] = shape if bound else _reference(uri)
    required = bool(shape.get("required"))
    if route.bus_name == "planning.save_draft":
        field = "document" if route.method == "PUT" else "changes"
        shape.pop("oneOf")
        shape["properties"] = {field: shape["properties"][field]}
        shape["required"] = [field]
        required = True
        if route.method == "PUT":
            payload = {"anyOf": [c.ref(urn + "#/properties/document"), shape]}
    elif route.bus_name == "integrations.test_hook_subscription":
        required_fields = shape.get("required", [])
        if "project_id" in required_fields:
            required_fields.remove("project_id")
            payload, required = shape, bool(required_fields)
    return {"required": required, **_content(media, payload)}


def _route_responses(route: Route, c: _Components) -> dict[str, Any]:
    urn = route.result_type.SCHEMA_URN
    schema: dict[str, Any] = c.ref(urn)
    result = c.resolve(schema["$ref"])
    properties = result.get("properties", {})
    headers: dict[str, Any] = {}
    responses: dict[str, Any] = {"default": _PROBLEM}
    if route.etag_from:
        headers["ETag"] = _ETAG
        if route.method == "GET":
            responses["304"] = {"description": "Not modified", "headers": {"ETag": _ETAG}}
    if route.success_status == 201 and route.bus_name in {
        "workspace.create_workspace",
        "workspace.create_project",
        "planning.publish_revision",
    }:
        headers["Location"] = {"schema": {"type": "string", "format": "uri-reference"}}
    if route.if_match_to is not None or route.idempotency != IdempotencyMode.FORBIDDEN:
        responses["409"] = _PROBLEM
    if route.requires_if_match(c.registry):
        responses["428"] = _PROBLEM
    if route.bus_name == "execution.claim_assignment":
        # The DTO already defines both outcomes. Reuse its disjoint branches directly.
        schema = {"oneOf": [c.ref(f"{urn}#/oneOf/{index}") for index in range(len(result["oneOf"]))]}
    elif (
        route.success_status != 200
        and isinstance(outcome := properties.get("outcome"), dict)
        and outcome.get("const") == "waiting"
    ):
        waiting = {"required": ["outcome"]}
        responses["200"] = _response("Waiting", {"allOf": [schema, waiting]})
        schema = {"allOf": [schema, {"not": waiting}]}
    media = "text/markdown" if route.path.endswith(".md") else _JSON
    if media == "text/markdown":
        schema = _STRING
        headers["Content-Disposition"] = {"schema": _STRING}
    responses[str(route.success_status)] = _response(
        HTTPStatus(route.success_status).phrase, schema, media, **({"headers": headers} if headers else {})
    )
    return responses


def _route_operation(
    route: Route, spec: CommandSpec[Any, Any] | QuerySpec[Any, Any] | None, c: _Components
) -> dict[str, Any]:
    c.ref(route.dto_type.SCHEMA_URN)
    path = route.path.removeprefix(_PREFIX)
    result = {
        "operationId": route.effective_operation_id,
        "tags": sorted({*route.tags, "worker"} if path.startswith("/worker/") else route.tags),
        "responses": _route_responses(route, c),
    }
    if spec and spec.permission:
        result["x-skm-permission"] = spec.permission
        if spec.permission_alternatives:
            result["x-skm-permission-alternatives"] = list(spec.permission_alternatives)
    if params := _route_parameters(route, c):
        result["parameters"] = params
    if route.body != "none":
        result["requestBody"] = _request_body(route, c)
    return result


def _standalone(operation_id: str, tag: str, responses: Mapping[str, Any], **fields: Any) -> dict[str, Any]:
    return {
        "operationId": operation_id,
        "tags": [tag],
        "x-skm-bus": False,
        "responses": {"default": _PROBLEM, **responses},
        **fields,
    }


def _stream(description: str) -> dict[str, Any]:
    return _response(description, _STRING, "text/event-stream")


def _blob_paths(c: _Components):
    yield (
        "/workspaces/{workspace_id}/blobs",
        "post",
        _standalone(
            "artifacts_upload_blob",
            "artifacts",
            {"201": _response("Staged blob", c.ref("urn:skm:api:staged-blob:v1"))},
            parameters=[
                _parameter("workspace_id", "path", _UUID, required=True),
                _idempotency(True),
                _header("Content-Length", _AFTER, required=True),
                _header("SKM-Expected-Digest", {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}),
                _parameter("media_type", "query", _STRING),
            ],
            requestBody={"required": True, **_content("application/octet-stream", _BINARY)},
            **{"x-skm-permission": "file.write"},
        ),
    )
    headers = {"ETag": _ETAG, "Content-Disposition": {"schema": _STRING}}
    yield (
        "/file-versions/{file_version_id}/content",
        "get",
        _standalone(
            "artifacts_open_file_version_content",
            "artifacts",
            {
                "200": _response("File version bytes", _BINARY, "application/octet-stream", headers=headers),
                "304": {"description": "Not modified", "headers": {"ETag": _ETAG}},
            },
            parameters=[
                _parameter("file_version_id", "path", _UUID, required=True),
                _header("If-None-Match", _STRING),
            ],
            **{"x-skm-permission": "file.read"},
        ),
    )


def _event_paths():
    yield (
        "/events",
        "get",
        _standalone(
            "platform_stream_events",
            "events",
            {"200": _stream("Durable events. The data field contains a JSON EventEnvelope.")},
            parameters=[
                _parameter("workspace_id", "query", _UUID, required=True),
                _parameter("after", "query", _AFTER),
                _parameter("types", "query", _STRING)
                | {"description": "Comma-separated event names or URNs."},
                _parameter("stream", "query", {"type": "array", "items": _STRING})
                | {"style": "form", "explode": True},
                _header("Last-Event-ID", _STRING),
            ],
        ),
    )
    yield (
        "/projects/{project_id}/events/stream",
        "get",
        _standalone(
            "platform_stream_project_events",
            "events",
            {"200": _stream("Durable project-scoped events. The data field contains a JSON EventEnvelope.")},
            parameters=[
                _parameter("project_id", "path", _UUID, required=True),
                _parameter("after", "query", _AFTER),
                _parameter("snapshot", "query", {"type": "boolean"})
                | {"description": "Close the stream after delivering events available at admission."},
                _parameter("types", "query", _STRING)
                | {"description": "Comma-separated event names or URNs."},
                _parameter("stream", "query", {"type": "array", "items": _STRING})
                | {"style": "form", "explode": True},
                _header("Last-Event-ID", _STRING),
            ],
            **{"x-skm-permission": "project.read"},
        ),
    )
    attempt = _parameter("attempt_id", "path", _UUID, required=True)
    yield (
        "/attempts/{attempt_id}/live",
        "get",
        _standalone(
            "execution_stream_attempt_live",
            "execution",
            {"200": _stream("Ephemeral attempt events. The data field contains a JSON SessionEvent.")},
            parameters=[attempt, _parameter("after", "query", _AFTER)],
            **{"x-skm-permission": "run.read"},
        ),
    )
    yield (
        "/worker/attempts/{attempt_id}/live",
        "post",
        _standalone(
            "execution_publish_attempt_live",
            "worker",
            {"202": {"description": "Live batch accepted"}},
            parameters=[attempt],
            requestBody={
                "required": True,
                **_content(
                    "application/x-ndjson", {"type": "string", "description": "One SessionEvent per line."}
                ),
            },
        ),
    )


def _auth_paths(c: _Components):
    session_response = {
        "type": "object",
        "additionalProperties": False,
        "required": ["session_id", "principal_id", "kind", "display_name", "expires_at", "csrf_token"],
        "properties": {
            "session_id": _UUID,
            "principal_id": _UUID,
            "kind": {"type": "string", "enum": ["human"]},
            "display_name": _STRING,
            "expires_at": {"type": "string", "format": "date-time"},
            "csrf_token": _STRING,
        },
    }
    yield (
        "/auth/csrf",
        "get",
        _standalone(
            "auth_get_csrf",
            "auth",
            {
                "200": _response(
                    "CSRF token issued",
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["csrf_token"],
                        "properties": {"csrf_token": _STRING},
                    },
                )
            },
        ),
    )
    yield (
        "/auth/login",
        "post",
        _standalone(
            "auth_login",
            "auth",
            {"200": _response("Web session established", session_response)},
            parameters=[_header("X-SKM-CSRF", _STRING, required=True)],
            requestBody={
                "required": True,
                **_content(
                    _JSON,
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["password"],
                        "properties": {"password": {"type": "string", "minLength": 1}},
                    },
                ),
            },
        ),
    )
    yield (
        "/auth/logout",
        "post",
        _standalone(
            "auth_logout",
            "auth",
            {
                "200": _response(
                    "Web session revoked",
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["status"],
                        "properties": {"status": {"type": "string", "const": "logged_out"}},
                    },
                )
            },
            parameters=[_header("X-SKM-CSRF", _STRING, required=True)],
        ),
    )
    yield (
        "/auth/session",
        "get",
        _standalone(
            "auth_get_session",
            "auth",
            {
                "200": _response(
                    "Current authenticated session or principal",
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "authenticated",
                            "mode",
                            "auth_method",
                            "principal_id",
                            "kind",
                            "display_name",
                            "session_id",
                            "expires_at",
                        ],
                        "properties": {
                            "authenticated": {"type": "boolean"},
                            "mode": {"type": "string", "enum": ["admin_login", "none"]},
                            "auth_method": {"type": "string", "enum": ["bearer", "session", "none"]},
                            "principal_id": _UUID,
                            "kind": {"type": "string", "enum": ["human", "service", "worker"]},
                            "display_name": _STRING,
                            "session_id": {"anyOf": [_UUID, {"type": "null"}]},
                            "expires_at": {
                                "anyOf": [{"type": "string", "format": "date-time"}, {"type": "null"}]
                            },
                        },
                    },
                )
            },
        ),
    )
    yield (
        "/auth/session/reload",
        "post",
        _standalone(
            "auth_reload_session",
            "auth",
            {"200": _response("Web session rotated", session_response)},
            parameters=[_header("X-SKM-CSRF", _STRING, required=True)],
        ),
    )
    yield (
        "/auth/pairing",
        "post",
        _standalone(
            "auth_create_pairing",
            "auth",
            {
                "201": _response(
                    "Pairing credential issued",
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["pairing_id", "workspace_id", "pairing_secret", "expires_at"],
                        "properties": {
                            "pairing_id": _UUID,
                            "workspace_id": _UUID,
                            "pairing_secret": _STRING,
                            "expires_at": {"type": "string", "format": "date-time"},
                        },
                    },
                )
            },
            requestBody={
                "required": True,
                **_content(
                    _JSON,
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["workspace_id"],
                        "properties": {
                            "workspace_id": _UUID,
                            "ttl_seconds": {"type": "integer", "minimum": 1, "maximum": 3600},
                            "worker_registration": {"type": "object"},
                            "principal_id": _UUID,
                            "scope_grants": {
                                "type": "object",
                                "additionalProperties": {"type": "array", "items": _STRING},
                            },
                            "replaces": _UUID,
                        },
                    },
                ),
            },
        ),
    )
    yield (
        "/auth/pairing/exchange",
        "post",
        _standalone(
            "auth_exchange_pairing",
            "auth",
            {
                "200": _response(
                    "Pairing credential exchanged",
                    c.ref("urn:skm:workspace:result:exchange-pairing-token:v1"),
                )
            },
            requestBody={
                "required": True,
                **_content(_JSON, c.ref("urn:skm:workspace:command:exchange-pairing-token:v1")),
            },
        ),
    )


def _health_paths(c: _Components):
    health = c.ref("urn:skm:api:health:v1")
    yield (
        "/health/live",
        "get",
        _standalone(
            "platform_health_live",
            "platform",
            {
                "200": _response("Process is live", health),
            },
        ),
    )
    yield (
        "/health/ready",
        "get",
        _standalone(
            "platform_health_ready",
            "platform",
            {
                "200": _response("Process is ready", health),
                "503": _response("Process is not ready", health),
            },
        ),
    )
    yield (
        "/openapi.json",
        "get",
        _standalone(
            "platform_openapi",
            "platform",
            {
                "200": _response("OpenAPI 3.1 document", {"type": "object"}),
            },
        ),
    )


def _shared_components(c: _Components) -> dict[str, Any]:
    c.ref("urn:skm:api:page:v1")
    headers = {
        "IdempotencyKey": ("Idempotency-Key", {"type": "string", "pattern": "^[A-Za-z0-9._:-]{1,128}$"}),
        "IfMatch": ("If-Match", {"type": "string", "pattern": '^W/"v[0-9]+"$'}),
    }
    return {
        "securitySchemes": {
            "bearer": {"type": "http", "scheme": "bearer"},
            "sessionCookie": {"type": "apiKey", "in": "cookie", "name": "skm_session"},
            "csrfToken": {"type": "apiKey", "in": "header", "name": "X-SKM-CSRF"},
        },
        "schemas": c.schemas,
        "responses": {
            "Problem": _response(
                "Problem details", c.ref("urn:skm:api:problem:v1"), "application/problem+json"
            )
        },
        "parameters": {
            key + label: _header(name, schema, required=required)
            for key, (name, schema) in headers.items()
            for label, required in (("Required", True), ("Optional", False))
        },
        "headers": {"ETag": {"schema": _STRING, "description": 'W/"v<N>" or "<digest>".'}},
    }


def _declared_paths(routes: Iterable[Route], c: _Components):
    specs: dict[str, CommandSpec[Any, Any] | QuerySpec[Any, Any]] = {
        spec.name: spec
        for manifest in (*MANIFESTS, PLATFORM_MANIFEST)
        for spec in (*manifest.commands, *manifest.queries)
        if isinstance(spec, (CommandSpec, QuerySpec))
    }
    for route in routes:
        urn = route.dto_type.SCHEMA_URN.split(":")
        spec = specs.get(route.bus_name)
        if route.internal or urn[3] == "host" or (spec is not None and spec.internal):
            continue
        yield (
            route.path.removeprefix(_PREFIX),
            route.method.lower(),
            _route_operation(route, spec, c),
        )


def _operation_security(method: str, path: str) -> list[dict[str, list[str]]]:
    key = (method, path)
    if key in _OPEN_OPERATIONS:
        return []
    if key in _SESSION_ONLY_OPERATIONS:
        return [{"sessionCookie": [], "csrfToken": []}]
    if key in _BEARER_ONLY_OPERATIONS or path.startswith("/worker/"):
        return [{"bearer": []}]
    if method in _SAFE_METHODS:
        return [{"bearer": []}, {"sessionCookie": []}]
    return [{"bearer": []}, {"sessionCookie": [], "csrfToken": []}]


def render(schema_root: Path) -> str:
    c = _Components(SchemaRegistry.load(schema_root, validate=False))
    routes = build_route_table(entry.id for entry in MODULE_CATALOG).describe()
    paths: dict[str, dict[str, Any]] = {}
    operation_ids: set[str] = set()
    for path, method, operation in (
        *_declared_paths(routes, c),
        *_auth_paths(c),
        *_blob_paths(c),
        *_event_paths(),
        *_health_paths(c),
    ):
        operation_id = operation["operationId"]
        item = paths.setdefault(path, {})
        if operation_id in operation_ids or method in item:
            raise CodegenError(path, f"Duplicate OpenAPI operation {method.upper()} ({operation_id})")
        operation_ids.add(operation_id)
        item[method] = operation
        if path.startswith("/health/"):
            item["servers"] = [{"url": "/"}]
        operation["security"] = _operation_security(method, path)
    document = {
        "openapi": "3.1.0",
        "info": {"title": "Swiss Knife Man API", "version": __version__},
        "servers": [{"url": _PREFIX}],
        "security": [{"bearer": []}],
        "paths": paths,
        "components": _shared_components(c),
    }
    c.validate_refs()
    return json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
