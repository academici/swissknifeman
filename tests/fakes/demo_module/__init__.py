"""Test-only ``demo`` module: command ``demo.echo``, query ``demo.get_echo``, event ``demo.echoed``.

The DTO classes mirror the shape of generated classes (``SCHEMA_URN``, ``to_json``/``from_json``); their
schemas live in ``schemas/demo`` and load with ``SchemaRegistry.load(SCHEMA_ROOT)``. Nothing here is a
production module: ``MANIFEST`` exists only for bus registry and dispatch tests.
"""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, ClassVar, Final, Self, override
from uuid import UUID

from skm.application_bus.context import (
    CommandContext,
    ExternalConsumerContext,
    QueryContext,
    SubscriberContext,
)
from skm.application_bus.ports import DeliveryPlan, ExternalConsumer, OutboxItem, SendResult, Sent
from skm.application_bus.registry import (
    CommandSpec,
    ExternalConsumerSpec,
    IdempotencyMode,
    QuerySpec,
    SubscriberSpec,
)
from skm.kernel.cancel import CancelToken
from skm.kernel.events import DomainEvent, EventEnvelope
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef

__all__ = [
    "ECHO",
    "ECHO_PERMISSION",
    "ECHO_SECRET",
    "GET_ECHO",
    "HOOK_CONSUMER",
    "MANIFEST",
    "ON_ECHOED",
    "PERMISSIONS",
    "READ_PERMISSION",
    "SCHEMA_ROOT",
    "Echo",
    "EchoResult",
    "EchoSecret",
    "Echoed",
    "GetEcho",
    "GetEchoResult",
    "Noted",
    "manifest",
]

SCHEMA_ROOT: Final = Path(__file__).with_name("schemas")
ECHO_PERMISSION: Final = "demo.echo"
READ_PERMISSION: Final = "demo.read"
PERMISSIONS: Final = frozenset({ECHO_PERMISSION, READ_PERMISSION})


@dataclass(frozen=True, slots=True)
class Echo:
    workspace_id: UUID
    text: str

    SCHEMA_URN: ClassVar[str] = "urn:skm:demo:command:echo:v1"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(workspace_id=UUID(data["workspace_id"]), text=data["text"])

    def to_json(self) -> JsonObject:
        return {"workspace_id": str(self.workspace_id), "text": self.text}


@dataclass(frozen=True, slots=True)
class EchoSecret:
    """``Echo`` plus a secret that the request digest covers but no receipt, log or error may contain."""

    workspace_id: UUID
    text: str
    secret: str

    SCHEMA_URN: ClassVar[str] = "urn:skm:demo:command:echo-secret:v1"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(workspace_id=UUID(data["workspace_id"]), text=data["text"], secret=data["secret"])

    def to_json(self) -> JsonObject:
        return {"workspace_id": str(self.workspace_id), "text": self.text, "secret": self.secret}


@dataclass(frozen=True, slots=True)
class EchoResult:
    text: str

    SCHEMA_URN: ClassVar[str] = "urn:skm:demo:result:echo:v1"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(text=data["text"])

    def to_json(self) -> JsonObject:
        return {"text": self.text}


@dataclass(frozen=True, slots=True)
class GetEcho:
    workspace_id: UUID

    SCHEMA_URN: ClassVar[str] = "urn:skm:demo:query:get-echo:v1"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(workspace_id=UUID(data["workspace_id"]))

    def to_json(self) -> JsonObject:
        return {"workspace_id": str(self.workspace_id)}


@dataclass(frozen=True, slots=True)
class GetEchoResult:
    texts: tuple[str, ...]

    SCHEMA_URN: ClassVar[str] = "urn:skm:demo:result:get-echo:v1"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        return cls(texts=tuple(data["texts"]))

    def to_json(self) -> JsonObject:
        return {"texts": list(self.texts)}


@dataclass(frozen=True, slots=True)
class Echoed(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:demo:event:echoed:v1"
    stream_kind: ClassVar[str] = "workspace"

    workspace_id: WorkspaceId
    text: str

    @override
    def stream_id(self) -> UUID:
        return self.workspace_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return {"workspace_id": str(self.workspace_id), "text": self.text}


@dataclass(frozen=True, slots=True)
class Noted(DomainEvent):
    """Instance-level event, kept out of ``MANIFEST``: UoW tests use it for the instance feed."""

    event_type: ClassVar[str] = "urn:skm:demo:event:noted:v1"
    stream_kind: ClassVar[str] = "config"

    stream: UUID
    text: str

    @override
    def stream_id(self) -> UUID:
        return self.stream

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return None

    @override
    def payload(self) -> JsonObject:
        return {"text": self.text}


def _workspace_scope(dto: Echo | EchoSecret | GetEcho) -> ScopeRef:
    return ScopeRef(kind=ScopeKind.WORKSPACE, id=ScopeId(dto.workspace_id))


def handle_echo(cmd: Echo | EchoSecret, ctx: CommandContext, uow: UnitOfWork) -> EchoResult:
    uow.record(Echoed(workspace_id=WorkspaceId(cmd.workspace_id), text=cmd.text))
    return EchoResult(text=cmd.text)


def handle_get_echo(query: GetEcho, ctx: QueryContext, uow: UnitOfWork) -> GetEchoResult:
    return GetEchoResult(texts=())


def on_echoed(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
    """Consumes ``demo.echoed``; the delivery tests observe the consumer receipt, not a side effect."""


class _HookConsumer:
    """External consumer of ``hook:*`` destinations; delivery is exercised by the relay tests."""

    def prepare(
        self, item: OutboxItem, envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork
    ) -> DeliveryPlan | None:
        return DeliveryPlan(payload={"event_id": str(envelope.id), "destination": item.destination})

    def send(
        self, plan: DeliveryPlan, *, attempt: int, timeout_seconds: float, cancel: CancelToken
    ) -> SendResult:
        return Sent()


def _hook_factory(ctx: ExternalConsumerContext) -> ExternalConsumer:
    return _HookConsumer()


ECHO: Final = CommandSpec(
    name="demo.echo",
    dto=Echo,
    result=EchoResult,
    permission=ECHO_PERMISSION,
    scope_of=_workspace_scope,
    handler=handle_echo,
    idempotency=IdempotencyMode.OPTIONAL,
)
ECHO_SECRET: Final = CommandSpec(
    name="demo.echo_secret",
    dto=EchoSecret,
    result=EchoResult,
    permission=ECHO_PERMISSION,
    scope_of=_workspace_scope,
    handler=handle_echo,
    idempotency=IdempotencyMode.OPTIONAL,
)
GET_ECHO: Final = QuerySpec(
    name="demo.get_echo",
    dto=GetEcho,
    result=GetEchoResult,
    permission=READ_PERMISSION,
    scope_of=_workspace_scope,
    handler=handle_get_echo,
)
ON_ECHOED: Final = SubscriberSpec(
    consumer_id="demo.on_echoed",
    event_types=frozenset({Echoed.event_type}),
    handler=on_echoed,
)
HOOK_CONSUMER: Final = ExternalConsumerSpec(prefix="hook", factory=_hook_factory)

MANIFEST: Final = ModuleManifest(
    id="demo",
    depends_on=(),
    optional=True,
    db_schema=None,
    settings_sections=(),
    commands=(ECHO,),
    queries=(GET_ECHO,),
    subscribers=(ON_ECHOED,),
    events=(Echoed,),
    permissions=PERMISSIONS,
)


def manifest(**changes: Any) -> ModuleManifest:
    """``MANIFEST`` with fields replaced, for negative registry fixtures."""
    return replace(MANIFEST, **changes)
