"""Immutable, framework-free HTTP wire declarations and DTO binding."""

import copy
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, NoReturn, cast, override
from uuid import UUID

from skm.application_bus.registry import IdempotencyMode
from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import HostId
from skm.kernel.ports_uow import RequestMeta
from skm.platform.schema.registry import SchemaRegistry

from .etag import check_version

__all__ = [
    "Route",
    "RouteMethodNotAllowed",
    "RouteTable",
    "build_route_table",
    "decode_scope",
    "encode_scope",
]

type HostMetadataFactory = Callable[[RequestMeta, HostId], RequestMeta]


@dataclass(frozen=True, slots=True)
class Route:
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    result_type: type[Any]
    command: type[Any] | None = None
    query: type[Any] | None = None
    path_params: Mapping[str, str] = field(default_factory=dict[str, str])
    query_params: Mapping[str, str] = field(default_factory=dict[str, str])
    body: Literal["json", "merge_patch", "none"] = "json"
    success_status: int = 200
    idempotency: IdempotencyMode = IdempotencyMode.FORBIDDEN
    etag_from: str | None = None
    if_match_to: str | None = None
    tags: tuple[str, ...] = ()
    operation_id: str | None = None
    internal: bool = False
    body_limit_key: str = "api.limits.max_body_bytes"
    # A path component may guard token provenance without becoming a DTO property.
    path_guards: Mapping[str, str] = field(default_factory=dict[str, str])
    host_metadata: HostMetadataFactory | None = None
    validate_payload: Callable[[Mapping[str, Any]], None] | None = None

    def __post_init__(self) -> None:
        for name in ("path_params", "query_params", "path_guards"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))
        object.__setattr__(self, "tags", tuple(self.tags))
        if (self.command is None) == (self.query is None):
            raise ValueError("Route needs exactly one command or query")
        if self.query is not None and self.idempotency != IdempotencyMode.FORBIDDEN:
            raise ValueError("Queries forbid idempotency keys")
        if self.method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("Unsupported HTTP method")
        if self.body not in {"json", "merge_patch", "none"}:
            raise ValueError("Unsupported body codec")

    @property
    def dto_type(self) -> type[Any]:
        return cast("type[Any]", self.command or self.query)

    @property
    def bus_name(self) -> str:
        parts = self.dto_type.SCHEMA_URN.split(":")
        return f"{parts[2]}.{parts[-2].replace('-', '_')}"

    @property
    def effective_operation_id(self) -> str:
        return self.operation_id or self.bus_name.replace(".", "_")

    def requires_if_match(self, schemas: SchemaRegistry) -> bool:
        return any(
            self.if_match_to in part.get("required", ()) for part, _ in _dto_schema(schemas, self.dto_type)
        )

    def bind(
        self,
        body: Mapping[str, Any],
        path: Mapping[str, str],
        query: Mapping[str, str],
        *,
        actor: Actor | None = None,
        schemas: SchemaRegistry | None = None,
        version: int | None = None,
    ) -> Any:
        """Merge without overwriting conflicting body values, then validate the complete wire DTO."""
        schemas = schemas or SchemaRegistry.load_default()
        merged = self._dto_body(body, schemas)
        if version is not None and self.if_match_to is not None:
            supplied = merged.setdefault(self.if_match_to, version)
            if supplied is not None and type(supplied) is not int:
                _invalid("Invalid body version")
            check_version(version, supplied)
        for key, guard in self.path_guards.items():
            grant = None if actor is None else actor.grant
            expected = None if grant is None else grant.scope_id
            if guard != "actor.grant.scope_id" or expected is None or path[key] != str(expected):
                raise error_for(ErrorCode.FORBIDDEN, "Path does not match token scope")
        for source, mapping in ((path, self.path_params), (query, self.query_params)):
            for key, target in mapping.items():
                if key not in source:
                    continue
                schema = _property(schemas, self.dto_type, target)
                value = _parameter(source[key], schema)
                node = merged
                parts = target.split(".")
                for part in parts[:-1]:
                    if part not in node:
                        node[part] = {}
                    if not isinstance(node[part], dict):
                        _invalid("Path/body collision")
                    node = node[part]
                leaf = parts[-1]
                if leaf in node:
                    existing: Any = node[leaf]
                    if isinstance(existing, str) and isinstance(value, dict):
                        existing = _parameter(existing, schema)
                    if type(cast("Any", existing)) is not type(cast("Any", value)) or existing != value:
                        _invalid("Path/body collision")
                node[leaf] = value
        schemas.require_valid(self.dto_type.SCHEMA_URN, merged)
        if self.validate_payload is not None:
            self.validate_payload(merged)
        return self.dto_type.from_json(merged)

    def _dto_body(self, body: Mapping[str, Any], schemas: SchemaRegistry) -> dict[str, Any]:
        merged = copy.deepcopy(dict(body))
        if self.body == "merge_patch":
            field = "merge_patch"
        elif self.method == "PUT" and "schema" in merged:
            field = "document"
        else:
            return merged
        if field in merged or not any(
            field in part.get("properties", {}) for part, _ in _dto_schema(schemas, self.dto_type)
        ):
            return merged
        if self.if_match_to is not None and self.if_match_to in merged:
            version = merged.pop(self.if_match_to)
            return {field: merged, self.if_match_to: version}
        return {field: merged}


def _invalid(message: str) -> NoReturn:
    raise error_for(ErrorCode.SCHEMA_INVALID, message)


_NIL_UUID = "00000000-0000-0000-0000-000000000000"


def decode_scope(value: str) -> dict[str, Any]:
    if value == "instance":
        return {"kind": "instance", "id": _NIL_UUID}
    kind, sep, identifier = value.partition(":")
    if not sep or kind not in {"instance", "workspace", "project", "plan", "run", "host"}:
        _invalid("Invalid scope")
    try:
        return {"kind": kind, "id": str(UUID(identifier))}
    except ValueError:
        _invalid("Invalid scope UUID")


def encode_scope(value: Mapping[str, Any]) -> str:
    settings = "level" in value
    kind_key, id_key = ("level", "scope_id") if settings else ("kind", "id")
    kind, identifier = value.get(kind_key), value.get(id_key)
    wire = "instance" if kind == "instance" and identifier in (None, _NIL_UUID) else f"{kind}:{identifier}"
    scope = decode_scope(wire)
    expected = (
        {"kind": "instance", "id": identifier}
        if not settings and kind == "instance" and identifier in (None, _NIL_UUID)
        else scope
    )
    if (_settings_scope(scope) if settings else expected) != dict(value):
        _invalid("Invalid scope")
    return wire


def _settings_scope(scope: dict[str, Any]) -> dict[str, Any]:
    result = {"level": scope["kind"]}
    if scope["kind"] != "instance" and scope["id"] is not None:
        result["scope_id"] = scope["id"]
    return result


def _resolve(schema: Any, resolver: Any, seen: frozenset[int] = frozenset()) -> Iterator[tuple[Any, Any]]:
    """Yield conjuncts with their own resolver for field discovery and parameter codecs."""
    if not isinstance(schema, Mapping):
        return
    shape = cast("Mapping[str, Any]", schema)
    if id(shape) in seen:
        raise ValueError("Circular field reference")
    seen = seen | {id(shape)}
    yield shape, resolver
    if "$ref" in shape:
        resolved = resolver.lookup(shape["$ref"])
        yield from _resolve(resolved.contents, resolved.resolver, seen)
    for member in shape.get("allOf", ()):
        yield from _resolve(member, resolver, seen)


def _dto_schema(schemas: SchemaRegistry, dto: type[Any]) -> Iterator[tuple[Any, Any]]:
    schema = schemas.get(dto.SCHEMA_URN)
    return _resolve(schema, schemas.resolver_for(schema))


def _property(schemas: SchemaRegistry, dto: type[Any], path: str) -> tuple[Any, ...]:
    nodes = tuple(_dto_schema(schemas, dto))
    for part in path.split("."):
        properties = [
            (props[part], resolver)
            for schema, resolver in nodes
            if part in (props := schema.get("properties", {}))
        ]
        if not properties:
            raise ValueError(f"Unknown DTO field {dto.__name__}.{path}")
        nodes = tuple(node for schema, resolver in properties for node in _resolve(schema, resolver))
    return tuple(schema for schema, _ in nodes)


def _parameter(value: str, schemas: tuple[Any, ...]) -> Any:
    props = {name for schema in schemas for name in schema.get("properties", {})}
    if {"kind", "id"} <= props:
        return decode_scope(value)
    if {"level", "scope_id"} <= props:
        return _settings_scope(decode_scope(value))
    types = [schema.get("type") for schema in schemas]
    if any(kind == "integer" or (isinstance(kind, list) and "integer" in kind) for kind in types):
        if not re.fullmatch(r"-?(0|[1-9][0-9]*)", value):
            _invalid("Invalid integer parameter")
        return int(value)
    if "boolean" in types:
        if value not in {"true", "false"}:
            _invalid("Invalid boolean parameter")
        return value == "true"
    return value


class RouteTable:
    """Validated immutable indexes shared by ASGI and standalone clients."""

    __slots__ = ("_by_type", "_patterns", "_routes")

    _by_type: Mapping[type[Any], Route]
    _patterns: tuple[tuple[Route, re.Pattern[str]], ...]
    _routes: tuple[Route, ...]

    def __init__(self, routes: Iterable[Route], *, schemas: SchemaRegistry | None = None) -> None:
        schemas = schemas or SchemaRegistry.load_default()
        entries = tuple(routes)
        pairs: set[tuple[str, str]] = set()
        operations: set[str] = set()
        by_type: dict[type[Any], Route] = {}
        patterns: list[tuple[Route, re.Pattern[str]]] = []
        for route in entries:
            for dto in (route.dto_type, route.result_type):
                urn = getattr(dto, "SCHEMA_URN", None)
                if not isinstance(urn, str) or urn not in schemas.urns():
                    raise ValueError(f"Missing schema for {dto}")
            if ".host." in route.bus_name or route.internal:
                raise ValueError("Internal/host operation cannot be an HTTP route")
            pair = (route.method, route.path)
            if pair in pairs or route.effective_operation_id in operations:
                raise ValueError("Duplicate route or operation_id")
            pairs.add(pair)
            operations.add(route.effective_operation_id)
            if not route.path.startswith("/"):
                raise ValueError("Route path must be absolute")
            names = re.findall(r"\{([a-z][a-z0-9_]*)\}", route.path)
            if len(names) != len(set(names)) or set(names) != set(route.path_params) | set(route.path_guards):
                raise ValueError("Unbound or unknown path parameter")
            if set(route.path_params) & set(route.path_guards):
                raise ValueError("Path parameter cannot be both DTO field and guard")
            if any(g != "actor.grant.scope_id" for g in route.path_guards.values()):
                raise ValueError("Unknown path guard")
            for target in (*route.path_params.values(), *route.query_params.values()):
                _property(schemas, route.dto_type, target)
            if route.if_match_to:
                _property(schemas, route.dto_type, route.if_match_to)
            if route.etag_from:
                _property(schemas, route.result_type, route.etag_from)
            # Aliases require explicit operation IDs; the first declaration is the client default.
            by_type.setdefault(route.dto_type, route)
            pattern = re.escape(route.path)
            for name in names:
                pattern = pattern.replace(re.escape("{" + name + "}"), f"(?P<{name}>[^/]+)")
            patterns.append((route, re.compile(pattern)))
        object.__setattr__(self, "_routes", entries)
        object.__setattr__(self, "_by_type", MappingProxyType(by_type))
        object.__setattr__(self, "_patterns", tuple(patterns))

    @override
    def __setattr__(self, name: str, value: object) -> NoReturn:
        raise AttributeError("RouteTable is immutable")

    @override
    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError("RouteTable is immutable")

    def describe(self) -> tuple[Route, ...]:
        return self._routes

    def __getitem__(self, dto_type: type[Any]) -> Route:
        route = self._by_type.get(dto_type)
        if route is None:
            raise error_for(ErrorCode.INTERNAL_ERROR, f"No HTTP route for {dto_type.__name__}")
        return route

    def match(self, method: str, path: str) -> tuple[Route, Mapping[str, str]]:
        allowed = set[str]()
        for route, pattern in self._patterns:
            matched = pattern.fullmatch(path)
            if matched:
                allowed.add(route.method)
                if method == route.method:
                    return route, MappingProxyType(matched.groupdict())
        if allowed:
            # HTTP adapters project this transport distinction to 405 plus Allow.
            raise RouteMethodNotAllowed(tuple(sorted(allowed)))
        raise error_for(ErrorCode.NOT_FOUND, "Route not found")


class RouteMethodNotAllowed(ValueError):
    def __init__(self, allowed: tuple[str, ...]) -> None:
        self.allowed = allowed
        self.status_code = 405
        super().__init__("Method not allowed")


def build_route_table(enabled_module_ids: Iterable[str]) -> RouteTable:
    from .routes import discover_routes

    return RouteTable(discover_routes(enabled_module_ids))
