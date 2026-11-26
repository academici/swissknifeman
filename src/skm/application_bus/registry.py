"""Registration records of bus operations and consumers, and the immutable ``BusRegistry`` (kernel §4.1).

Owner modules register implemented handlers after generating their DTOs. ``BusRegistry.build`` checks
every enabled manifest once; its immutable registry and fixed pipelines are not extension points.
"""

import inspect
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, NoReturn, cast, override

from skm.application_bus.context import (
    CommandContext,
    ExternalConsumerContext,
    QueryContext,
    SubscriberContext,
)
from skm.application_bus.ports import DeliveryPlan, ExternalConsumer, OutboxItem
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, PreconditionFailed, SkmError
from skm.kernel.events import DomainEvent, EventEnvelope
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.ports_uow import Isolation, UnitOfWork
from skm.kernel.scopes import ScopeRef
from skm.platform.schema.registry import SchemaRegistry

__all__ = [
    "COMMAND_PIPELINE",
    "OUTBOX_EXTERNAL_PREFIXES",
    "QUERY_PIPELINE",
    "SSE_DESTINATION",
    "AnyCommandSpec",
    "AnyQuerySpec",
    "BusRegistry",
    "BusRegistryError",
    "CommandSpec",
    "ExternalConsumerSpec",
    "IdempotencyMode",
    "QuerySpec",
    "ScopeResolver",
    "SubscriberSpec",
]

# The only order of command steps (kernel §4.4); bus.py runs exactly these, nothing is pluggable.
COMMAND_PIPELINE: Final = (
    "translate_errors",
    "validate_dto",
    "uow.begin",
    "resolve_scope",
    "authorize",
    "load_config",
    "idempotency",
    "handler",
    "receipt",
    "audit",
    "commit",
)
# Queries: no idempotency, no allowed audit, never committed (kernel §4.4 ``ask``).
QUERY_PIPELINE: Final = (
    "translate_errors",
    "validate_dto",
    "uow.begin",
    "resolve_scope",
    "authorize",
    "load_config",
    "events_cursor",
    "handler",
    "validate_result",
    "rollback",
)
SSE_DESTINATION: Final = "sse"
# External destination prefixes admitted by ck_outbox__destination; a new prefix is an owner migration first.
OUTBOX_EXTERNAL_PREFIXES: Final = frozenset({"hook"})

_IDENTIFIER: Final = re.compile(r"[a-z][a-z0-9_]*")


class IdempotencyMode(StrEnum):
    FORBIDDEN = "forbidden"  # a key is rejected (SCHEMA_INVALID, reason=not_idempotent)
    OPTIONAL = "optional"
    REQUIRED = "required"


type ScopeResolver[D] = Callable[[D, UnitOfWork], ScopeRef | None]
"""Server-trusted scope of an operation that names a stored resource by its id (``resolve_scope`` step).

Resolve only the owner scope in the operation's UoW. An unknown resource uses instance scope for
opaque authorization. The handler verifies that the resource belongs to the authorized scope.
"""


@dataclass(frozen=True, slots=True)
class CommandSpec[C, R]:
    name: str  # "<module>.<verb>_<noun>"
    dto: type[C]  # generated class with SCHEMA_URN, to_json/from_json
    result: type[R]  # generated class with SCHEMA_URN
    permission: str  # from the permission catalog
    scope_of: Callable[[C], ScopeRef | None] | None  # None (or a None scope) -> instance scope
    handler: Callable[[C, CommandContext, UnitOfWork], R]
    permissions_of: Callable[[C], tuple[str, ...]] | None = None  # additional permissions
    scope_resolver: ScopeResolver[C] | None = None  # by-id command: the stored resource names its scope
    idempotency: IdempotencyMode = IdempotencyMode.OPTIONAL
    isolation: Isolation = Isolation.READ_COMMITTED
    internal: bool = False  # not published to API/CLI/MCP; callable only by service/worker actors
    audit: bool = True  # allowed audit record (denied audit is always written)
    allowed_kinds: frozenset[PrincipalKind] = frozenset(PrincipalKind)
    permission_alternatives: tuple[str, ...] = ()  # OR with permission; permissions_of remains AND
    replay_guard: Callable[[C, CommandContext, UnitOfWork], None] | None = None


@dataclass(frozen=True, slots=True)
class QuerySpec[Q, R]:
    name: str
    dto: type[Q]
    result: type[R]
    permission: str | None  # None requires live admission only
    scope_of: Callable[[Q], ScopeRef | None] | None
    handler: Callable[[Q, QueryContext, UnitOfWork], R]
    isolation: Isolation = Isolation.REPEATABLE_READ
    internal: bool = False
    allowed_kinds: frozenset[PrincipalKind] = frozenset(PrincipalKind)
    scope_resolver: ScopeResolver[Q] | None = None  # by-id query: the stored resource names its scope
    permission_alternatives: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SubscriberSpec:
    consumer_id: str  # "<module>.<snake_name>"
    event_types: frozenset[str]  # event type URNs
    handler: Callable[[EventEnvelope, SubscriberContext, UnitOfWork], None]
    max_attempts: int | None = None  # narrows events.delivery.max_attempts, never widens it
    isolation: Isolation = Isolation.READ_COMMITTED


@dataclass(frozen=True, slots=True)
class ExternalConsumerSpec:
    prefix: str  # destinations "<prefix>:<id>"; ^[a-z][a-z0-9_]*$, unique, in ck_outbox__destination
    factory: Callable[[ExternalConsumerContext], ExternalConsumer]  # built once per relay process
    max_attempts: int | None = None
    # Builds the internal command the relay dispatches after the row became dead; None -> dead row only.
    on_dead: Callable[[OutboxItem, DeliveryPlan | None, str], object] | None = None


type AnyCommandSpec = CommandSpec[Any, Any]
type AnyQuerySpec = QuerySpec[Any, Any]


class BusRegistryError(ValueError):
    """Every problem of one ``BusRegistry.build``; the start fails with ``CONFIG_REGISTRY_INVALID``."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("bus registry is invalid:\n- " + "\n- ".join(self.problems))


class BusRegistry:
    """Read-only index of the operations and consumers of the enabled modules."""

    __slots__ = (
        "_command_names",
        "_command_types",
        "_disabled",
        "_disabled_names",
        "_disabled_types",
        "_event_types",
        "_external",
        "_query_names",
        "_query_types",
        "_subscribers",
        "_subscription_index",
    )

    _command_names: Mapping[str, AnyCommandSpec]
    _command_types: Mapping[type[object], AnyCommandSpec]
    _query_names: Mapping[str, AnyQuerySpec]
    _query_types: Mapping[type[object], AnyQuerySpec]
    _subscribers: tuple[SubscriberSpec, ...]
    _external: Mapping[str, ExternalConsumerSpec]
    _event_types: Mapping[str, type[DomainEvent]]
    _subscription_index: Mapping[str, tuple[str, ...]]
    _disabled: frozenset[str]
    _disabled_names: Mapping[str, str]  # operation name of a disabled module -> module id
    _disabled_types: Mapping[type[object], str]  # DTO class of a disabled module -> module id

    def __init__(self, collected: "_Collected") -> None:
        index: dict[str, list[str]] = {}
        for spec in collected.subscribers:
            for event_type in spec.event_types:
                index.setdefault(event_type, []).append(spec.consumer_id)
        values: dict[str, object] = {
            "_command_names": MappingProxyType({spec.name: spec for spec in collected.commands}),
            "_command_types": MappingProxyType({spec.dto: spec for spec in collected.commands}),
            "_query_names": MappingProxyType({spec.name: spec for spec in collected.queries}),
            "_query_types": MappingProxyType({spec.dto: spec for spec in collected.queries}),
            "_subscribers": tuple(collected.subscribers),
            "_external": MappingProxyType({spec.prefix: spec for spec in collected.external}),
            "_event_types": MappingProxyType(dict(collected.event_types)),
            "_subscription_index": MappingProxyType(
                {event_type: tuple(sorted(ids)) for event_type, ids in sorted(index.items())}
            ),
            "_disabled": collected.disabled,
            "_disabled_names": MappingProxyType(dict(collected.disabled_names)),
            "_disabled_types": MappingProxyType(dict(collected.disabled_types)),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @override
    def __setattr__(self, name: str, value: object) -> NoReturn:
        raise AttributeError(f"BusRegistry is immutable: cannot set {name!r}")

    @override
    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError(f"BusRegistry is immutable: cannot delete {name!r}")

    @classmethod
    def build(
        cls,
        manifests: Sequence[ModuleManifest],
        *,
        schemas: SchemaRegistry,
        permission_catalog: frozenset[str],
        disabled_modules: frozenset[str],
    ) -> "BusRegistry":
        """Check all enabled manifests; ``BusRegistryError`` (a ``ValueError``) lists every problem."""
        collected = _Collector(schemas=schemas, permissions=permission_catalog).collect(
            manifests, disabled_modules
        )
        if collected.problems:
            raise BusRegistryError(collected.problems)
        return cls(collected)

    # ------------------------------------------------------------------ pipeline
    @staticmethod
    def command_pipeline() -> tuple[str, ...]:
        return COMMAND_PIPELINE

    @staticmethod
    def query_pipeline() -> tuple[str, ...]:
        return QUERY_PIPELINE

    # ------------------------------------------------------------------ operations
    def command(self, dto_type: type[object]) -> AnyCommandSpec:
        """Spec of a DTO class.

        A class of a disabled module -> ``MODULE_DISABLED``; an unknown class -> ``INTERNAL_ERROR``.
        """
        spec = self._command_types.get(dto_type)
        if spec is None:
            self._missing("command", dto_type.__name__, self._disabled_types.get(dto_type))
        return spec

    def command_by_name(self, name: str) -> AnyCommandSpec:
        spec = self._command_names.get(name)
        if spec is None:
            self._missing("command", name, self._disabled_module_of(name))
        return spec

    def query(self, dto_type: type[object]) -> AnyQuerySpec:
        spec = self._query_types.get(dto_type)
        if spec is None:
            self._missing("query", dto_type.__name__, self._disabled_types.get(dto_type))
        return spec

    def query_by_name(self, name: str) -> AnyQuerySpec:
        spec = self._query_names.get(name)
        if spec is None:
            self._missing("query", name, self._disabled_module_of(name))
        return spec

    def public_commands(self) -> tuple[AnyCommandSpec, ...]:
        return tuple(spec for spec in self._command_names.values() if not spec.internal)

    def disabled_modules(self) -> frozenset[str]:
        return self._disabled

    # ------------------------------------------------------------------ events and delivery
    def subscribers(self) -> tuple[SubscriberSpec, ...]:
        return self._subscribers

    def external_consumers(self) -> Mapping[str, ExternalConsumerSpec]:
        return self._external

    def route(self, destination: str) -> SubscriberSpec | ExternalConsumerSpec | None:
        """``sse`` and unregistered destinations -> ``None`` (relay notifies / doctor shows unrouted)."""
        if destination == SSE_DESTINATION:
            return None
        prefix, separator, rest = destination.partition(":")
        if separator:
            return self._external.get(prefix) if rest else None
        return next((spec for spec in self._subscribers if spec.consumer_id == destination), None)

    def subscription_index(self) -> Mapping[str, tuple[str, ...]]:
        return self._subscription_index

    def event_types(self) -> Mapping[str, type[DomainEvent]]:
        return self._event_types

    def describe(self) -> Mapping[str, JsonValue]:
        """What is registered, for ``skm doctor --registries`` (mechanisms/03 §1 rule 3)."""
        description: JsonObject = {
            "command_pipeline": _json_names(COMMAND_PIPELINE, keep_order=True),
            "query_pipeline": _json_names(QUERY_PIPELINE, keep_order=True),
            "commands": _json_names(self._command_names),
            "queries": _json_names(self._query_names),
            "subscribers": _json_names(spec.consumer_id for spec in self._subscribers),
            "external_consumers": _json_names(self._external),
            "event_types": _json_names(self._event_types),
            "disabled_modules": _json_names(self._disabled),
        }
        return MappingProxyType(description)

    def _disabled_module_of(self, name: str) -> str | None:
        """Module of a disabled operation name, also when bootstrap passed no manifest of that module.

        Only the exact namespace before the first dot counts: ``exportsx.run`` is not ``exports``.
        """
        module_id = self._disabled_names.get(name)
        if module_id is not None:
            return module_id
        namespace, separator, _ = name.partition(".")
        return namespace if separator and namespace in self._disabled else None

    @staticmethod
    def _missing(kind: str, what: str, disabled_module: str | None) -> NoReturn:
        if disabled_module is not None:
            raise PreconditionFailed(
                ErrorCode.MODULE_DISABLED,
                f"module {disabled_module} is disabled",
                details={"module": disabled_module, "kind": kind},
            )
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, f"unregistered {kind}", details={"kind": kind, "name": what}
        )


@dataclass(slots=True)
class _Collected:
    commands: list[AnyCommandSpec]
    queries: list[AnyQuerySpec]
    subscribers: list[SubscriberSpec]
    external: list[ExternalConsumerSpec]
    event_types: dict[str, type[DomainEvent]]
    disabled: frozenset[str]
    disabled_names: dict[str, str]
    disabled_types: dict[type[object], str]
    problems: list[str]


class _Collector:
    """One pass over the manifests; every check appends to ``problems`` instead of stopping."""

    def __init__(self, *, schemas: SchemaRegistry, permissions: frozenset[str]) -> None:
        self._schemas = schemas
        self._urns = schemas.urns()
        self._permissions = permissions
        self._out = _Collected([], [], [], [], {}, frozenset(), {}, {}, [])
        self._names: dict[str, str] = {}  # command and query names share one namespace
        self._dtos: dict[type[object], str] = {}
        self._consumers: dict[str, str] = {}
        self._prefixes: dict[str, str] = {}

    def collect(self, manifests: Sequence[ModuleManifest], disabled: frozenset[str]) -> _Collected:
        out = self._out
        out.disabled = frozenset(disabled)
        ids = [manifest.id for manifest in manifests]
        for module_id in sorted({i for i in ids if ids.count(i) > 1}):
            self._problem(module_id, f"duplicate module id {module_id!r}")
        module_ids = frozenset(ids)
        enabled = [manifest for manifest in manifests if manifest.id not in disabled]
        for manifest in manifests:
            if manifest.id in disabled:
                self._remember_disabled(manifest)
        for manifest in enabled:
            self._events(manifest)
        for manifest in enabled:
            for raw in manifest.commands:
                self._command(manifest, raw)
            for raw in manifest.queries:
                self._query(manifest, raw)
            for raw in manifest.subscribers:
                self._subscriber(manifest, raw)
            for raw in manifest.external_consumers:
                self._external(manifest, raw, module_ids)
        return out

    def _problem(self, module_id: str, message: str) -> None:
        self._out.problems.append(f"{module_id}: {message}")

    def _remember_disabled(self, manifest: ModuleManifest) -> None:
        for raw in (*manifest.commands, *manifest.queries):
            if isinstance(raw, CommandSpec | QuerySpec):
                spec = cast("AnyCommandSpec | AnyQuerySpec", raw)
                self._out.disabled_names[spec.name] = manifest.id
                self._out.disabled_types[spec.dto] = manifest.id

    def _events(self, manifest: ModuleManifest) -> None:
        for event in manifest.events:
            candidate = cast("object", event)
            if not (isinstance(candidate, type) and issubclass(candidate, DomainEvent)):
                self._problem(manifest.id, f"event {event!r} is not a DomainEvent class")
                continue
            try:
                event.validate_registration(self._schemas)
            except (ValueError, SkmError) as exc:
                self._problem(manifest.id, f"event {event.__name__}: {exc}")
                continue
            owner = self._out.event_types.get(event.event_type)
            if owner is not None:
                self._problem(manifest.id, f"event_type {event.event_type} is already registered")
                continue
            self._out.event_types[event.event_type] = event

    def _operation(self, manifest: ModuleManifest, spec: "AnyCommandSpec | AnyQuerySpec", kind: str) -> bool:
        problems = len(self._out.problems)
        name = spec.name
        where = f"{kind} {name!r}"
        if name.startswith(f"{manifest.id}.host."):
            self._problem(manifest.id, f"{where} uses the host operation namespace <module>.host.*")
        elif not _is_operation_name(name, manifest.id):
            self._problem(manifest.id, f"{where} must be named {manifest.id}.<verb>_<noun>")
        if name in self._names:
            self._problem(manifest.id, f"duplicate operation name {name!r} (also in {self._names[name]})")
        else:
            self._names[name] = manifest.id
        if spec.dto in self._dtos:
            self._problem(manifest.id, f"{where}: DTO class is already registered by {self._dtos[spec.dto]}")
        else:
            self._dtos[spec.dto] = name
        if spec.permission not in self._permissions and not (kind == "query" and spec.permission is None):
            self._problem(manifest.id, f"{where}: permission {spec.permission!r} is not in the catalog")
        choices = spec.permission_alternatives
        if not _is(choices, tuple) or any(not _is(p, str) or p not in self._permissions for p in choices):
            self._problem(
                manifest.id, f"{where}: permission_alternatives must be catalogued permission names"
            )
        elif choices and spec.permission is None:
            self._problem(manifest.id, f"{where}: permission_alternatives require a primary permission")
        for role, model in (("dto", spec.dto), ("result", spec.result)):
            urn = getattr(model, "SCHEMA_URN", None)
            if not isinstance(urn, str) or urn not in self._urns:
                self._problem(manifest.id, f"{where}: {role} schema {urn!r} is not in the schema registry")
        self._operation_fields(manifest, spec, where)
        return len(self._out.problems) == problems

    def _operation_fields(
        self, manifest: ModuleManifest, spec: "AnyCommandSpec | AnyQuerySpec", where: str
    ) -> None:
        if not _accepts_three(spec.handler):
            self._problem(manifest.id, f"{where}: handler must be a callable of (dto, ctx, uow)")
        if spec.scope_of is not None and not callable(spec.scope_of):
            self._problem(manifest.id, f"{where}: scope_of must be callable or None")
        if spec.scope_resolver is not None:
            if not callable(spec.scope_resolver) or not _accepts_two(spec.scope_resolver):
                self._problem(
                    manifest.id, f"{where}: scope_resolver must be a callable of (dto, uow) or None"
                )
            if spec.scope_of is not None:
                self._problem(manifest.id, f"{where}: scope_of and scope_resolver exclude each other")
        if not _is(spec.isolation, Isolation):
            self._problem(manifest.id, f"{where}: isolation must be an Isolation")
        kinds = spec.allowed_kinds
        if not _is(kinds, frozenset) or not kinds or not kinds <= frozenset(PrincipalKind):
            self._problem(manifest.id, f"{where}: allowed_kinds must be a non-empty set of PrincipalKind")
        elif spec.internal and kinds <= {PrincipalKind.HUMAN}:
            self._problem(manifest.id, f"{where}: an internal operation must allow service or worker actors")

    def _command(self, manifest: ModuleManifest, raw: object) -> None:
        if not isinstance(raw, CommandSpec):
            self._problem(manifest.id, f"commands holds {type(raw).__name__}, not CommandSpec")
            return
        spec = cast("AnyCommandSpec", raw)
        sound = self._operation(manifest, spec, "command")
        where = f"command {spec.name!r}"
        if not _is(spec.idempotency, IdempotencyMode):
            self._problem(manifest.id, f"{where}: idempotency must be an IdempotencyMode")
            sound = False
        if spec.permissions_of is not None and not callable(spec.permissions_of):
            self._problem(manifest.id, f"{where}: permissions_of must be callable or None")
            sound = False
        if sound:
            self._out.commands.append(spec)

    def _query(self, manifest: ModuleManifest, raw: object) -> None:
        if not isinstance(raw, QuerySpec):
            self._problem(manifest.id, f"queries holds {type(raw).__name__}, not QuerySpec")
            return
        spec = cast("AnyQuerySpec", raw)
        if self._operation(manifest, spec, "query"):
            self._out.queries.append(spec)

    def _subscriber(self, manifest: ModuleManifest, raw: object) -> None:
        if not isinstance(raw, SubscriberSpec):
            self._problem(manifest.id, f"subscribers holds {type(raw).__name__}, not SubscriberSpec")
            return
        problems = len(self._out.problems)
        consumer_id = raw.consumer_id
        where = f"subscriber {consumer_id!r}"
        if not _is_operation_name(consumer_id, manifest.id):
            self._problem(manifest.id, f"{where} must be named {manifest.id}.<snake_name>")
        if consumer_id in self._consumers:
            other = self._consumers[consumer_id]
            self._problem(manifest.id, f"duplicate consumer_id {consumer_id!r} (also in {other})")
        else:
            self._consumers[consumer_id] = manifest.id
        if not _is(raw.event_types, frozenset) or not raw.event_types:
            self._problem(manifest.id, f"{where}: event_types must be a non-empty frozenset")
        else:
            for event_type in sorted(raw.event_types):
                if event_type not in self._out.event_types:
                    message = f"{where}: event_type {event_type} is not declared by an enabled module"
                    self._problem(manifest.id, message)
        if not _accepts_three(raw.handler):
            self._problem(manifest.id, f"{where}: handler must be a callable of (envelope, ctx, uow)")
        _check_attempts(raw.max_attempts, lambda message: self._problem(manifest.id, f"{where}: {message}"))
        if len(self._out.problems) == problems:
            self._out.subscribers.append(raw)

    def _external(self, manifest: ModuleManifest, raw: object, module_ids: frozenset[str]) -> None:
        if not isinstance(raw, ExternalConsumerSpec):
            found = type(raw).__name__
            self._problem(manifest.id, f"external_consumers holds {found}, not ExternalConsumerSpec")
            return
        problems = len(self._out.problems)
        prefix = raw.prefix
        where = f"external consumer prefix {prefix!r}"
        if not _is(prefix, str) or _IDENTIFIER.fullmatch(prefix) is None:
            self._problem(manifest.id, f"{where} must match ^[a-z][a-z0-9_]*$")
        elif prefix == SSE_DESTINATION:
            self._problem(manifest.id, f"{where} is reserved for the sse destination")
        elif prefix in module_ids:
            self._problem(manifest.id, f"{where} equals a module id; routing would be ambiguous")
        elif prefix not in OUTBOX_EXTERNAL_PREFIXES:
            allowed = ", ".join(sorted(OUTBOX_EXTERNAL_PREFIXES))
            self._problem(manifest.id, f"{where} is not admitted by ck_outbox__destination ({allowed})")
        if prefix in self._prefixes:
            self._problem(manifest.id, f"duplicate {where} (also in {self._prefixes[prefix]})")
        else:
            self._prefixes[prefix] = manifest.id
        if not callable(raw.factory):
            self._problem(manifest.id, f"{where}: factory must be callable")
        if raw.on_dead is not None and not callable(raw.on_dead):
            self._problem(manifest.id, f"{where}: on_dead must be callable or None")
        _check_attempts(raw.max_attempts, lambda message: self._problem(manifest.id, f"{where}: {message}"))
        if len(self._out.problems) == problems:
            self._out.external.append(raw)


def _is_operation_name(name: object, module_id: str) -> bool:
    if not isinstance(name, str):
        return False
    module, separator, rest = name.partition(".")
    return separator == "." and module == module_id and _IDENTIFIER.fullmatch(rest) is not None


def _accepts_three(handler: object) -> bool:
    if not callable(handler):
        return False
    try:
        inspect.signature(handler).bind(None, None, None)
    except TypeError:
        return False
    except ValueError:  # no signature available (builtins): trust the declaration
        return True
    return True


def _accepts_two(resolver: object) -> bool:
    if not callable(resolver):
        return False
    try:
        inspect.signature(resolver).bind(None, None)
    except TypeError:
        return False
    except ValueError:  # no signature available (builtins): trust the declaration
        return True
    return True


def _check_attempts(value: object, report: Callable[[str], None]) -> None:
    if value is not None and (type(value) is not int or value < 1):
        report("max_attempts must be a positive integer or None")


def _is(value: object, kind: type[object] | tuple[type[object], ...]) -> bool:
    """``isinstance`` on a typed field: specs are plain dataclasses, nothing checks them on creation."""
    return isinstance(value, kind)


def _json_names(names: Iterable[str], *, keep_order: bool = False) -> list[JsonValue]:
    result: list[JsonValue] = []
    result.extend(names if keep_order else sorted(names))
    return result
