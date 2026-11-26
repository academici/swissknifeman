"""BusRegistry build checks, routing and the fixed pipeline; pure pipeline steps.

Full dispatch/receipt/denied-audit scenarios need the memory UoW and live in ``test_bus_dispatch.py``.
"""

import inspect
from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import UTC, datetime
from typing import Any, ClassVar, cast, override
from uuid import UUID

import pytest

from fakes.demo_module import (
    ECHO,
    ECHO_PERMISSION,
    GET_ECHO,
    HOOK_CONSUMER,
    MANIFEST,
    ON_ECHOED,
    PERMISSIONS,
    READ_PERMISSION,
    SCHEMA_ROOT,
    Echo,
    Echoed,
    EchoResult,
    GetEcho,
    manifest,
)
from skm.application_bus.context import SubscriberContext
from skm.application_bus.middleware import (
    bind_meta,
    from_receipt,
    idempotency_key,
    is_waiting,
    kind_allowed,
    request_digest,
    required_permissions,
)
from skm.application_bus.ports import IdempotencyReceipt
from skm.application_bus.registry import (
    COMMAND_PIPELINE,
    QUERY_PIPELINE,
    BusRegistry,
    BusRegistryError,
    ExternalConsumerSpec,
    IdempotencyMode,
    SubscriberSpec,
)
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, PreconditionFailed, ValidationFailed
from skm.kernel.events import DomainEvent, EventEnvelope
from skm.kernel.ids import PrincipalId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.outcomes import Waiting
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork
from skm.platform.jsonc.digest import digest
from skm.platform.schema.registry import SchemaRegistry

WORKSPACE = UUID("0191e2a4-7c3f-7b21-8a54-3f6d2c1b9e07")
NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
ECHO_SPEC = ECHO
QUERY_SPEC = GET_ECHO
SUBSCRIBER = ON_ECHOED


@pytest.fixture(scope="module")
def schemas() -> SchemaRegistry:
    return SchemaRegistry.load(SCHEMA_ROOT)


def build(
    schemas: SchemaRegistry,
    *manifests: ModuleManifest,
    permissions: frozenset[str] = PERMISSIONS,
    disabled: frozenset[str] = frozenset(),
) -> BusRegistry:
    return BusRegistry.build(
        manifests or (MANIFEST,), schemas=schemas, permission_catalog=permissions, disabled_modules=disabled
    )


def problems(schemas: SchemaRegistry, *manifests: ModuleManifest, **options: Any) -> tuple[str, ...]:
    with pytest.raises(BusRegistryError) as raised:
        build(schemas, *manifests, **options)
    assert isinstance(raised.value, ValueError)  # the start fails with CONFIG_REGISTRY_INVALID
    assert str(raised.value).startswith("bus registry is invalid:")
    return raised.value.problems


def other(**fields: Any) -> ModuleManifest:
    values: dict[str, Any] = {"id": "other", "depends_on": (), "optional": True, "db_schema": None}
    values["settings_sections"] = ()
    values.update(fields)
    return ModuleManifest(**values)


def meta(key: str | None = None) -> RequestMeta:
    return RequestMeta(request_id="req_01", surface=Surface.TEST, idempotency_key=key, received_at=NOW)


def actor(kind: PrincipalKind = PrincipalKind.HUMAN) -> Actor:
    return Actor(principal_id=PrincipalId(WORKSPACE), kind=kind, display_name="tester")


def ignore_event(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
    return None


# ---------------------------------------------------------------- positive build and lookups


def test_build_indexes_operations_events_and_consumers(schemas: SchemaRegistry) -> None:
    registry = build(schemas, manifest(external_consumers=(HOOK_CONSUMER,)))
    assert registry.command(Echo) is ECHO_SPEC
    assert registry.command_by_name("demo.echo") is ECHO_SPEC
    assert registry.query(GetEcho) is QUERY_SPEC
    assert registry.query_by_name("demo.get_echo") is QUERY_SPEC
    assert registry.public_commands() == (ECHO_SPEC,)
    assert registry.subscribers() == (SUBSCRIBER,)
    assert dict(registry.external_consumers()) == {"hook": HOOK_CONSUMER}
    assert dict(registry.subscription_index()) == {Echoed.event_type: ("demo.on_echoed",)}
    assert dict(registry.event_types()) == {Echoed.event_type: Echoed}
    assert registry.disabled_modules() == frozenset()
    described = registry.describe()
    assert described["commands"] == ["demo.echo"]
    assert described["external_consumers"] == ["hook"]


def test_route_separates_sse_external_prefixes_and_consumers(schemas: SchemaRegistry) -> None:
    registry = build(schemas, manifest(external_consumers=(HOOK_CONSUMER,)))
    assert registry.route("sse") is None  # the relay notifies itself
    assert registry.route("hook:0193aa00") is HOOK_CONSUMER
    assert registry.route("demo.on_echoed") is SUBSCRIBER
    for unrouted in ("hook:", "mail:1", "demo.unknown", "other.on_echoed", ""):
        assert registry.route(unrouted) is None


def test_internal_commands_are_not_public(schemas: SchemaRegistry) -> None:
    internal = replace(ECHO_SPEC, internal=True, allowed_kinds=frozenset({PrincipalKind.SERVICE}))
    registry = build(schemas, manifest(commands=(internal,)))
    assert registry.public_commands() == ()
    assert registry.command(Echo) is internal


# ---------------------------------------------------------------- immutability and the fixed pipeline


def test_registry_is_immutable(schemas: SchemaRegistry) -> None:
    registry = build(schemas)
    for name in ("_command_types", "_subscribers", "extra"):
        with pytest.raises(AttributeError, match="immutable"):
            setattr(registry, name, {})
        with pytest.raises(AttributeError, match="immutable"):
            delattr(registry, name)
    with pytest.raises(TypeError):
        cast("dict[str, object]", registry.external_consumers())["hook"] = HOOK_CONSUMER
    with pytest.raises(TypeError):
        cast("dict[str, object]", registry.event_types())["x"] = Echoed
    with pytest.raises(TypeError):
        cast("dict[str, object]", registry.subscription_index())["x"] = ()
    field = "name"
    with pytest.raises(FrozenInstanceError):
        setattr(ECHO_SPEC, field, "demo.other")
    assert registry.command(Echo) is ECHO_SPEC
    assert registry.command_by_name("demo.echo") is ECHO_SPEC


def test_pipeline_order_is_fixed_and_not_configurable(schemas: SchemaRegistry) -> None:
    registry = build(schemas)
    assert registry.command_pipeline() == (
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
    assert registry.query_pipeline() == (
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
    assert registry.command_pipeline() is COMMAND_PIPELINE
    assert registry.query_pipeline() is QUERY_PIPELINE
    assert isinstance(COMMAND_PIPELINE, tuple)
    parameters = set(inspect.signature(BusRegistry.build).parameters)
    assert parameters == {"manifests", "schemas", "permission_catalog", "disabled_modules"}
    assert registry.describe()["command_pipeline"] == list(COMMAND_PIPELINE)


# ---------------------------------------------------------------- negative fixtures


def test_duplicate_operation_names_and_dto_classes_are_rejected(schemas: SchemaRegistry) -> None:
    twin = replace(ECHO_SPEC, dto=GetEcho)
    found = problems(schemas, manifest(commands=(ECHO_SPEC, twin)))
    assert any("duplicate operation name 'demo.echo'" in problem for problem in found)
    found = problems(schemas, manifest(queries=(replace(QUERY_SPEC, name="demo.echo", dto=GetEcho),)))
    assert any("duplicate operation name 'demo.echo'" in problem for problem in found)
    found = problems(schemas, manifest(commands=(ECHO_SPEC, replace(ECHO_SPEC, name="demo.echo_again"))))
    assert any("DTO class is already registered" in problem for problem in found)


def test_permission_must_be_in_the_catalog(schemas: SchemaRegistry) -> None:
    found = problems(schemas, permissions=frozenset({READ_PERMISSION}))
    assert found == (f"demo: command 'demo.echo': permission {ECHO_PERMISSION!r} is not in the catalog",)
    found = problems(schemas, permissions=frozenset({ECHO_PERMISSION}))
    assert found == (f"demo: query 'demo.get_echo': permission {READ_PERMISSION!r} is not in the catalog",)


@dataclass(frozen=True, slots=True)
class Unschematized:
    SCHEMA_URN: ClassVar[str] = "urn:skm:demo:command:missing:v1"


def test_dto_and_result_schemas_must_be_registered(schemas: SchemaRegistry) -> None:
    found = problems(schemas, manifest(commands=(replace(ECHO_SPEC, dto=Unschematized),)))
    assert found == (
        "demo: command 'demo.echo': dto schema 'urn:skm:demo:command:missing:v1' is not in "
        "the schema registry",
    )
    found = problems(schemas, manifest(commands=(replace(ECHO_SPEC, result=object),)))
    assert found == ("demo: command 'demo.echo': result schema None is not in the schema registry",)


def test_disabled_module_is_skipped_and_reports_module_disabled(schemas: SchemaRegistry) -> None:
    registry = build(schemas, disabled=frozenset({"demo"}))
    assert registry.disabled_modules() == frozenset({"demo"})
    assert registry.public_commands() == ()
    assert registry.subscribers() == ()
    assert dict(registry.event_types()) == {}
    for lookup in (lambda: registry.command(Echo), lambda: registry.command_by_name("demo.echo")):
        with pytest.raises(PreconditionFailed) as raised:
            lookup()
        assert raised.value.code is ErrorCode.MODULE_DISABLED
        assert raised.value.details["module"] == "demo"
    for lookup in (lambda: registry.query(GetEcho), lambda: registry.query_by_name("demo.get_echo")):
        with pytest.raises(PreconditionFailed):
            lookup()
    # A disabled module is not checked: its broken specs never fail the start.
    build(schemas, manifest(commands=(replace(ECHO_SPEC, permission="nope"),)), disabled=frozenset({"demo"}))


@pytest.mark.parametrize(
    "manifests", [(), (MANIFEST,), (MANIFEST, other())], ids=["none", "demo", "demo+other"]
)
def test_disabled_module_without_manifest_reports_module_disabled_by_name(
    schemas: SchemaRegistry, manifests: tuple[ModuleManifest, ...]
) -> None:
    # Bootstrap (kernel §5.3 step 10) passes only enabled manifests and the disabled ids separately.
    registry = BusRegistry.build(
        manifests, schemas=schemas, permission_catalog=PERMISSIONS, disabled_modules=frozenset({"exports"})
    )
    lookups = (registry.command_by_name, registry.query_by_name)
    for lookup, name in zip(lookups, ("exports.purge_notes", "exports.get_export"), strict=True):
        with pytest.raises(PreconditionFailed) as raised:
            lookup(name)
        assert raised.value.code is ErrorCode.MODULE_DISABLED
        assert raised.value.details["module"] == "exports"
    # Only the exact namespace component matches; a partial prefix or a bare id stays unknown.
    unknown_names = ("exportsx.purge_notes", "export.purge_notes", "exports", "exports_purge_notes")
    for name in (*unknown_names, "demo.exports"):
        for lookup in lookups:
            with pytest.raises(InternalError) as unknown:
                lookup(name)
            assert unknown.value.code is ErrorCode.INTERNAL_ERROR
    if manifests:
        assert registry.command_by_name("demo.echo") is ECHO_SPEC
        assert registry.query_by_name("demo.get_echo") is QUERY_SPEC
        assert registry.command(Echo) is ECHO_SPEC


def test_unknown_operation_is_internal_error(schemas: SchemaRegistry) -> None:
    registry = build(schemas)
    for lookup in (
        lambda: registry.command(GetEcho),
        lambda: registry.command_by_name("demo.get_echo"),
        lambda: registry.query(Echo),
        lambda: registry.query_by_name("demo.unknown"),
    ):
        with pytest.raises(InternalError) as raised:
            lookup()
        assert raised.value.code is ErrorCode.INTERNAL_ERROR


def test_subscription_to_an_event_of_a_disabled_module_is_rejected(schemas: SchemaRegistry) -> None:
    listener = SubscriberSpec(
        consumer_id="other.on_echoed", event_types=frozenset({Echoed.event_type}), handler=ignore_event
    )
    registry = build(schemas, MANIFEST, other(subscribers=(listener,)))
    assert registry.subscription_index()[Echoed.event_type] == ("demo.on_echoed", "other.on_echoed")
    found = problems(schemas, MANIFEST, other(subscribers=(listener,)), disabled=frozenset({"demo"}))
    assert found == (
        f"other: subscriber 'other.on_echoed': event_type {Echoed.event_type} is not declared by an "
        "enabled module",
    )


@pytest.mark.parametrize(
    ("prefix", "reason"),
    [
        ("sse", "is reserved for the sse destination"),
        ("demo", "equals a module id; routing would be ambiguous"),
        ("other", "equals a module id; routing would be ambiguous"),
        ("Hook", "must match ^[a-z][a-z0-9_]*$"),
        ("hook:x", "must match ^[a-z][a-z0-9_]*$"),
        ("", "must match ^[a-z][a-z0-9_]*$"),
        ("webhook", "is not admitted by ck_outbox__destination (hook)"),
    ],
)
def test_external_consumer_prefix_negative(schemas: SchemaRegistry, prefix: str, reason: str) -> None:
    spec = replace(HOOK_CONSUMER, prefix=prefix)
    found = problems(schemas, manifest(external_consumers=(spec,)), other())
    assert found == (f"demo: external consumer prefix {prefix!r} {reason}",)


def test_external_consumer_prefix_is_unique_across_modules(schemas: SchemaRegistry) -> None:
    found = problems(
        schemas,
        manifest(external_consumers=(HOOK_CONSUMER,)),
        other(external_consumers=(HOOK_CONSUMER,)),
    )
    assert found == ("other: duplicate external consumer prefix 'hook' (also in demo)",)


def test_external_consumer_prefix_checks_disabled_module_ids(schemas: SchemaRegistry) -> None:
    spec = replace(HOOK_CONSUMER, prefix="other")
    found = problems(schemas, manifest(external_consumers=(spec,)), other(), disabled=frozenset({"other"}))
    assert found == ("demo: external consumer prefix 'other' equals a module id; routing would be ambiguous",)


def test_external_consumer_callables_and_attempts(schemas: SchemaRegistry) -> None:
    factory: Any = "nope"
    on_dead: Any = 3
    spec = ExternalConsumerSpec(prefix="hook", factory=factory, max_attempts=0, on_dead=on_dead)
    found = problems(schemas, manifest(external_consumers=(spec,)))
    assert found == (
        "demo: external consumer prefix 'hook': factory must be callable",
        "demo: external consumer prefix 'hook': on_dead must be callable or None",
        "demo: external consumer prefix 'hook': max_attempts must be a positive integer or None",
    )


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("demo.host.echo", "uses the host operation namespace <module>.host.*"),
        ("other.echo", "must be named demo.<verb>_<noun>"),
        ("demo", "must be named demo.<verb>_<noun>"),
        ("demo.Echo", "must be named demo.<verb>_<noun>"),
    ],
)
def test_operation_names_stay_in_the_bus_namespace_of_the_module(
    schemas: SchemaRegistry, name: str, reason: str
) -> None:
    found = problems(schemas, manifest(commands=(replace(ECHO_SPEC, name=name),)))
    assert found == (f"demo: command {name!r} {reason}",)
    registry = build(schemas)
    with pytest.raises(InternalError):
        registry.command_by_name("demo.host.echo")


def test_handler_and_spec_fields_are_checked(schemas: SchemaRegistry) -> None:
    def two(dto: object, ctx: object) -> None:
        return None

    broken = replace(
        ECHO_SPEC,
        handler=two,
        idempotency="optional",
        allowed_kinds=frozenset(),
        isolation="serializable",
    )
    found = problems(schemas, manifest(commands=(broken,)))
    assert found == (
        "demo: command 'demo.echo': handler must be a callable of (dto, ctx, uow)",
        "demo: command 'demo.echo': isolation must be an Isolation",
        "demo: command 'demo.echo': allowed_kinds must be a non-empty set of PrincipalKind",
        "demo: command 'demo.echo': idempotency must be an IdempotencyMode",
    )
    humans_only = replace(ECHO_SPEC, internal=True, allowed_kinds=frozenset({PrincipalKind.HUMAN}))
    found = problems(schemas, manifest(commands=(humans_only,)))
    assert found == ("demo: command 'demo.echo': an internal operation must allow service or worker actors",)


def test_wrong_record_types_are_reported(schemas: SchemaRegistry) -> None:
    found = problems(
        schemas,
        manifest(
            commands=(QUERY_SPEC,), queries=(ECHO_SPEC,), subscribers=("demo.x",), external_consumers=(1,)
        ),
    )
    assert found == (
        "demo: commands holds QuerySpec, not CommandSpec",
        "demo: queries holds CommandSpec, not QuerySpec",
        "demo: subscribers holds str, not SubscriberSpec",
        "demo: external_consumers holds int, not ExternalConsumerSpec",
    )


def test_subscriber_checks(schemas: SchemaRegistry) -> None:
    unknown = "urn:skm:demo:event:unknown:v1"
    renamed = replace(SUBSCRIBER, consumer_id="other.on_echoed")
    empty = replace(SUBSCRIBER, consumer_id="demo.empty", event_types=frozenset())
    stray = replace(SUBSCRIBER, consumer_id="demo.stray", event_types=frozenset({unknown}), max_attempts=0)
    found = problems(schemas, manifest(subscribers=(SUBSCRIBER, SUBSCRIBER, renamed, empty, stray)))
    assert found == (
        "demo: duplicate consumer_id 'demo.on_echoed' (also in demo)",
        "demo: subscriber 'other.on_echoed' must be named demo.<snake_name>",
        "demo: subscriber 'demo.empty': event_types must be a non-empty frozenset",
        f"demo: subscriber 'demo.stray': event_type {unknown} is not declared by an enabled module",
        "demo: subscriber 'demo.stray': max_attempts must be a positive integer or None",
    )


@dataclass(frozen=True, slots=True)
class Untyped(DomainEvent):
    """An event without ``event_type`` fails at registration (registry test contract)."""

    stream_kind: ClassVar[str] = "workspace"

    @override
    def stream_id(self) -> UUID:
        return WORKSPACE

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return None

    @override
    def payload(self) -> JsonObject:
        return {}


def test_event_registration_checks(schemas: SchemaRegistry) -> None:
    found = problems(schemas, manifest(events=(Echoed, Untyped)))
    assert found == ("demo: event Untyped: event type must be a canonical event URN",)
    found = problems(schemas, MANIFEST, other(events=(Echoed,)))
    assert found == (f"other: event_type {Echoed.event_type} is already registered",)
    found = problems(schemas, manifest(events=(Echoed, str)))
    assert found == ("demo: event <class 'str'> is not a DomainEvent class",)
    found = problems(schemas, manifest(events=(Echoed, "not-a-class")))
    assert found == ("demo: event 'not-a-class' is not a DomainEvent class",)


def test_every_problem_is_reported_at_once(schemas: SchemaRegistry) -> None:
    bad_name = replace(ECHO_SPEC, name="demo.host.echo", permission="nope")
    found = problems(
        schemas,
        manifest(commands=(bad_name,), external_consumers=(replace(HOOK_CONSUMER, prefix="sse"),)),
        MANIFEST,
    )
    assert "demo: duplicate module id 'demo'" in found
    assert any("host operation namespace" in problem for problem in found)
    assert any("'nope' is not in the catalog" in problem for problem in found)
    assert any("reserved for the sse destination" in problem for problem in found)


# ---------------------------------------------------------------- pure pipeline steps


@pytest.mark.parametrize(
    ("mode", "key", "expected"),
    [
        (IdempotencyMode.OPTIONAL, None, None),
        (IdempotencyMode.OPTIONAL, "k-1", "k-1"),
        (IdempotencyMode.REQUIRED, "k-1", "k-1"),
        (IdempotencyMode.FORBIDDEN, None, None),
    ],
)
def test_idempotency_modes_accept(mode: IdempotencyMode, key: str | None, expected: str | None) -> None:
    assert idempotency_key(replace(ECHO_SPEC, idempotency=mode), meta(key)) == expected


def test_idempotency_required_and_forbidden_reject() -> None:
    with pytest.raises(ValidationFailed) as raised:
        idempotency_key(replace(ECHO_SPEC, idempotency=IdempotencyMode.REQUIRED), meta())
    assert raised.value.code is ErrorCode.SCHEMA_INVALID
    with pytest.raises(ValidationFailed) as raised:
        idempotency_key(replace(ECHO_SPEC, idempotency=IdempotencyMode.FORBIDDEN), meta("k-1"))
    assert raised.value.code is ErrorCode.SCHEMA_INVALID
    assert raised.value.details["reason"] == "not_idempotent"


def test_request_digest_has_one_form() -> None:
    cmd = Echo(workspace_id=WORKSPACE, text="hello")
    assert request_digest(ECHO_SPEC, cmd) == digest({"operation": "demo.echo", "dto": cmd.to_json()})
    assert request_digest(ECHO_SPEC, cmd) != request_digest(ECHO_SPEC, replace(cmd, text="hello!"))
    renamed = replace(ECHO_SPEC, name="demo.echo_twice")
    assert request_digest(ECHO_SPEC, cmd) != request_digest(renamed, cmd)
    with pytest.raises(InternalError):
        request_digest(ECHO_SPEC, object())


def test_receipt_replay_compares_the_digest() -> None:
    cmd = Echo(workspace_id=WORKSPACE, text="hello")
    receipt = IdempotencyReceipt(
        workspace_id=WorkspaceId(WORKSPACE),
        principal_id=PrincipalId(WORKSPACE),
        operation="demo.echo",
        key="k-1",
        request_digest=request_digest(ECHO_SPEC, cmd),
        result={"text": "hello"},
        created_at=NOW,
        expires_at=NOW,
    )
    assert from_receipt(ECHO_SPEC, receipt, request_digest(ECHO_SPEC, cmd)) == EchoResult(text="hello")
    with pytest.raises(Conflict) as raised:
        from_receipt(ECHO_SPEC, receipt, request_digest(ECHO_SPEC, replace(cmd, text="other")))
    assert raised.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED


def test_permissions_of_adds_permissions_without_duplicates() -> None:
    cmd = Echo(workspace_id=WORKSPACE, text="hello")
    assert required_permissions(ECHO_SPEC, cmd) == (ECHO_PERMISSION,)
    extended = replace(ECHO_SPEC, permissions_of=lambda dto: ("demo.read", ECHO_PERMISSION, "demo.read"))
    assert required_permissions(extended, cmd) == (ECHO_PERMISSION, "demo.read")
    for wrong in (["demo.read"], ("demo.read", 1), "demo.read"):
        broken = replace(ECHO_SPEC, permissions_of=lambda dto, value=wrong: value)
        with pytest.raises(InternalError):
            required_permissions(broken, cmd)


def test_actor_kinds_and_internal_operations() -> None:
    assert kind_allowed(ECHO_SPEC, actor())
    internal = replace(ECHO_SPEC, internal=True)
    assert not kind_allowed(internal, actor())
    assert kind_allowed(internal, actor(PrincipalKind.SERVICE))
    workers = replace(ECHO_SPEC, allowed_kinds=frozenset({PrincipalKind.WORKER}))
    assert not kind_allowed(workers, actor(PrincipalKind.SERVICE))
    assert not kind_allowed(replace(QUERY_SPEC, internal=True), actor())


@dataclass(frozen=True, slots=True)
class Claimed:
    outcome: Waiting | None


def test_waiting_results_and_correlation() -> None:
    waiting = Waiting(code=ErrorCode.MANUAL_PENDING, message="wait")
    assert is_waiting(waiting)
    assert is_waiting(Claimed(outcome=waiting))
    assert not is_waiting(Claimed(outcome=None))
    assert not is_waiting(EchoResult(text="x"))
    assert bind_meta(meta()).correlation_id == "req_01"
    assert bind_meta(replace(meta(), correlation_id="req_root")).correlation_id == "req_root"
