"""Shared real memory/PostgreSQL hook routing harness for P10.08.a regressions."""

from __future__ import annotations

import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar, cast, override
from uuid import UUID

import pytest

from contracts.extensions.harness import FakeEstimator
from contracts.integrations import harness as integration_harness
from contracts.integrations.harness import Side, memory_side, postgres_side
from fakes.app import FakeScopeChain
from fakes.entropy import DeterministicEntropy
from skm.adapters.event_sinks._pinned_http import PinnedHttpClient
from skm.adapters.event_sinks.webhook import WebhookSink
from skm.adapters.host_commands.subprocess_runner import LocalSubscriptionState, SubprocessHostCommandRunner
from skm.adapters.secrets.env import EnvSecretResolver
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.host import HostContext
from skm.application_bus.ports import EventReader, OutboxStore
from skm.application_bus.registry import BusRegistry
from skm.application_bus.subscribers import (
    DeliverySettings,
    EventConfigLoader,
    EventSinkRegistry,
    OutboxRelayPass,
    SinkDeliveryResult,
)
from skm.bootstrap.modules import MANIFESTS, select_modules
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.cancel import CancelSource
from skm.kernel.errors import NotFound
from skm.kernel.events import DomainEvent, EventEnvelope
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import EventId, HostId, PlanId, ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import PrincipalRepository, TokenPepperSource
from skm.modules.access.public import RbacAuthorizer
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.integrations.domain.hook_events import HookEventKind, NormalizedHookEvent
from skm.modules.integrations.domain.hook_subscriptions import parse_subscriptions, subscription_json
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.host.host_subscriptions import SubscriptionState
from skm.modules.integrations.ports import HostCommandRunner
from skm.modules.planning.domain.events import PlanCreated
from skm.modules.planning.domain.plan import PlanPurpose
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.workspace.generated.commands import CreateProject, CreateWorkspace
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.secrets import SecretResolver, SecretResolvers
from skm.platform.config.store import EmptyPackConfigSource
from skm.platform.logging.logger import StructLogger
from support import pg as pg_support
from unit.integrations.test_subscriptions import _cached_bundle
from unit.policy.application.harness import FixedPepper, schemas

pg_session = pg_support.pg_session
test_database = pg_support.test_database
clean_test_database = pg_support.clean_test_database

HOOKABLE_EVENT_URN = "urn:skm:policy:event:intent-proposed:v1"
PLAN_EVENT_URN = PlanCreated.event_type


class _CaptureLogger(StructLogger):
    def __init__(self) -> None:
        super().__init__("test.hook_routing")
        self.records: list[dict[str, Any]] = []

    @override
    def warning(self, event: str, /, **fields: object) -> None:
        self.records.append({"level": "warning", "event": event, "fields": dict(fields)})

    @override
    def error(self, event: str, /, *, exc: BaseException | None = None, **fields: object) -> None:
        self.records.append({"level": "error", "event": event, "fields": dict(fields)})


class _DummySink:
    def __init__(self, sink_id: str) -> None:
        self.sink_id = sink_id

    def deliver(self, envelope: EventEnvelope, config: Mapping[str, JsonValue]) -> SinkDeliveryResult:
        raise NotImplementedError

    def config_schema(self) -> str:
        return "urn:skm:kernel:defs:v1"


@dataclass(frozen=True, slots=True)
class _SyntheticIntentProposed(DomainEvent):
    event_type: ClassVar[str] = HOOKABLE_EVENT_URN
    stream_kind: ClassVar[str] = "intent"
    intent_id: UUID
    ws_id: WorkspaceId | None

    @override
    def stream_id(self) -> UUID:
        return self.intent_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.ws_id

    @override
    def payload(self) -> JsonObject:
        return {
            "intent_id": str(self.intent_id),
            "scope_id": str(self.ws_id or UUID(int=1)),
            "kind": "git_push",
            "risk": "medium",
            "args_digest": "sha256:" + "a" * 64,
            "state": "proposed",
            "subject_ref": "test",
        }


class _RoutingWorld:
    def __init__(self, base: Side, *, sink_ids: tuple[str, ...] = ("jira-sink",)) -> None:
        self.base = base
        self.schemas = schemas()
        self.registry = base.bus._registry
        self.uow_factory = base.uow_factory
        self.clock = base.clock
        self.ids = base.ids
        self.logger = _CaptureLogger()
        self.owner_actor = base.actor("owner")
        self.system_actor = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")
        self._req_counter = 0
        with self.uow_factory(self._meta(), readonly=False) as uow:
            principals = uow.repo(PrincipalRepository)
            try:
                principals.get(SYSTEM_PRINCIPAL_ID)
            except NotFound:
                principals.add(
                    new_principal(
                        principal_id=SYSTEM_PRINCIPAL_ID,
                        kind=PrincipalKind.SERVICE,
                        display_name="system",
                        created_by=None,
                        now=self.clock.now(),
                    )
                )
                uow.commit()
        self.rebind_sinks(sink_ids)

    def rebind_sinks(self, sink_ids: tuple[str, ...]) -> None:
        sinks = EventSinkRegistry(
            (
                WebhookSink(http=PinnedHttpClient(), settings={}, clock=self.clock, version="test"),
                *(_DummySink(sid) for sid in sink_ids),
            )
        )
        self.gateways = GatewayTable(
            {
                TokenPepperSource: FixedPepper(),
                TokenEstimator: FakeEstimator(),
                BuiltinPacks: self.base.builtin,
                EventSinkRegistry: sinks,
            },
            "control_plane_gateway",
        )
        _, settings_reg, _, _ = _cached_bundle(sink_ids)
        self.loader = ConfigLoader(settings_reg, EmptyPackConfigSource())
        self.bus = Bus(
            registry=self.registry,
            schemas=self.schemas,
            uow_factory=self.uow_factory,
            authorizer=RbacAuthorizer(self.clock),
            scopes=FakeScopeChain(),
            config=self.loader,
            clock=self.clock,
            ids=self.ids,
            entropy=DeterministicEntropy(),
            gateways=self.gateways,
            retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
            idempotency_ttl=timedelta(hours=1),
        )

    def _meta(self, idempotency_key: str | None = None) -> RequestMeta:
        self._req_counter += 1
        return RequestMeta(f"req_{self._req_counter:026d}", Surface.CLI, idempotency_key, self.clock.now())

    def dispatch(self, cmd: object, *, actor: Actor | None = None, idempotency_key: str | None = None) -> Any:
        return self.bus.dispatch(cmd, actor=actor or self.owner_actor, meta=self._meta(idempotency_key))

    def ask(self, query: object, *, actor: Actor | None = None) -> Any:
        return self.bus.ask(query, actor=actor or self.owner_actor, meta=self._meta())

    def create_workspace(self, slug: str) -> WorkspaceId:
        return WorkspaceId(self.dispatch(CreateWorkspace(slug=slug, title=slug)).workspace_id)

    def create_project(self, ws_id: WorkspaceId, slug: str) -> ProjectId:
        return ProjectId(self.dispatch(CreateProject(workspace_id=ws_id, slug=slug, title=slug)).project_id)

    def set_subscriptions(self, *, level: str, scope_id: UUID | None, subscriptions: dict[str, Any]) -> None:
        ref = SetValueDefsScopeRef(level=cast("Any", level), scope_id=scope_id)
        self.dispatch(
            SetValue(scope=ref, key="hooks.subscriptions", value=subscriptions, reason="test", confirmed=True)
        )

    def emit_hookable(
        self, *, workspace_id: WorkspaceId | None, extra: JsonObject | None = None
    ) -> EventEnvelope:
        iid = self.ids.new_id()
        pid = ProjectId(UUID(str(extra["project_id"]))) if extra else None
        ws = cast("WorkspaceId", workspace_id)
        source = (
            PlanCreated(PlanId(iid), ws, pid, "test", "Test", PlanPurpose.STANDARD)
            if pid is not None
            else _SyntheticIntentProposed(intent_id=iid, ws_id=workspace_id)
        )
        with self.uow_factory(self._meta(), readonly=False) as uow:
            uow.record(source)
            uow.commit()
        with self.uow_factory(self._meta(), readonly=True) as uow:
            reader = uow.repo(EventReader)
            if workspace_id is not None:
                batch = reader.after_workspace_seq(workspace_id, 0, types=None, limit=500)
            else:
                batch = reader.after_global_position(0, limit=500)
            return next(e for e in reversed(batch) if e.stream_id == iid)

    def run_relay_pass(self) -> None:
        if self.base.pg is not None:
            (row,) = self.base.pg.execute("SELECT clock_timestamp()")
            if (db_now := cast("datetime", row[0])) > self.clock.now():
                self.clock.set(db_now)
        delivery = DeliverySettings(max_attempts=3, backoff_seconds=2, backoff_max_seconds=60)
        OutboxRelayPass(
            registry=self.registry,
            uow_factory=self.uow_factory,
            config=cast("EventConfigLoader", self.loader),
            clock=self.clock,
            ids=self.ids,
            log=self.logger,
            gateways=self.gateways,
            relay_id="relay-test",
            settings=lambda: delivery,
            batch_size=200,
            secrets=cast("SecretResolver", EnvSecretResolver({})),
            dispatcher=self.bus,
            actor=self.system_actor,
        ).run_once()

    def hook_destinations_for(self, event_id: EventId, *, workspace_id: WorkspaceId | None) -> list[str]:
        with self.uow_factory(self._meta(), readonly=True) as uow:
            page = uow.repo(OutboxStore).list(
                destination_prefix="hook:", state=None, workspace_id=workspace_id, after=None, limit=200
            )
            return sorted(item.destination for item in page.items if item.event_id == event_id)


def _webhook_cfg(
    *,
    event_types: list[str] | None = None,
    enabled: bool = True,
    class_: str = "observation",
    failure_policy: str = "retry",
    url: str = "https://hooks.example.com/skm",
) -> dict[str, Any]:
    return {
        "class": class_,
        "kind": "webhook",
        "execution_location": "control_plane",
        "event_types": event_types or [HOOKABLE_EVENT_URN, PLAN_EVENT_URN],
        "target": {"url": url, "secret": "secret://env/SKM_HOOK_SECRET"},
        "timeout_ms": 5000,
        "failure_policy": failure_policy,
        "enabled": enabled,
    }


def _host_guard_cfg(argv0: str = "/opt/skm/guard.py") -> dict[str, Any]:
    return {
        "class": "enforcement",
        "kind": "command",
        "execution_location": "host",
        "event_types": ["client:pre_shell"],
        "target": {"argv": [argv0], "cwd": "checkout"},
        "failure_policy": "deny",
    }


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def world(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[_RoutingWorld]:
    # Extend the shared harness's dependency closure with the real planning event registrations.
    monkeypatch.setattr(
        integration_harness,
        "_registry",
        lambda: BusRegistry.build(
            select_modules(MANIFESTS, frozenset()).manifests,
            schemas=schemas(),
            permission_catalog=frozenset().union(*(m.permissions for m in MANIFESTS)),
            disabled_modules=frozenset(),
        ),
    )
    base = (
        memory_side()
        if request.param == "memory"
        else postgres_side(request.getfixturevalue("clean_test_database"))
    )
    try:
        yield _RoutingWorld(base)
    finally:
        base.close()


def _host(
    tmp_path: Path,
    *,
    cls: str = "enforcement",
    code: str = "",
    trusted: bool = True,
    refs: dict[str, str] | None = None,
) -> tuple[HostContext, dict[str, Any], NormalizedHookEvent]:
    config = {
        "class": cls,
        "kind": "command",
        "execution_location": "host",
        "event_types": ["client:pre_shell"],
        "target": {
            "argv": [sys.executable, "-c", code],
            "cwd": "checkout",
            "env_allow": ["CI", "SKM_API_TOKEN"],
            "env_refs": refs or {},
        },
        "failure_policy": "deny" if cls == "enforcement" else "retry",
        "timeout_ms": 250,
        "retry": {"max_attempts": 2, "backoff": {"initial_ms": 100, "factor": 1.0, "max_ms": 100}},
    }
    parsed, errors = parse_subscriptions(cast("Any", {"audit": config}), {"audit": "project"})
    assert not errors
    (sub,) = parsed
    row: Any = subscription_json(sub)
    view = {
        "id": sub.id,
        "digest": sub.digest,
        **row["target"],
        **{key: row[key] for key in ("class", "event_types", "timeout_ms", "retry", "failure_policy")},
    }
    state = LocalSubscriptionState(
        tmp_path,
        environ={"PATH": "/usr/bin:/bin", "CI": "yes", "SKM_API_TOKEN": "must-not-leak"},
        request_factory=lambda *_a: None,
        secrets=SecretResolvers([EnvSecretResolver({"USER_SECRET": "allowed"})], on_reveal=lambda _s: None),
    )
    ctx = HostContext(
        client=cast("Any", None),
        gateways=GatewayTable(
            {SubscriptionState: state, HostCommandRunner: SubprocessHostCommandRunner()}, "host_gateway"
        ),
        host_id=HostId(UUID(int=2)),
        config={"hooks.host.trusted": {sub.id: sub.digest} if trusted else {}},
        log=None,
        cancel=CancelSource().token,
    )
    event = NormalizedHookEvent(
        TargetId.CLAUDE_CODE,
        HookEventKind.PRE_SHELL,
        None,
        str(tmp_path),
        "shell",
        "echo hi",
        (),
        None,
        None,
        "PreToolUse",
    )
    return ctx, {"project_id": str(UUID(int=3)), "subscriptions": [view]}, event


def configured_host_subscription(env: Any) -> Any:
    from types import SimpleNamespace

    from skm.bootstrap.hook import with_hook_state
    from skm.bootstrap.hook_subscriptions import bind_cli_subscriptions
    from skm.modules.integrations.application.queries.get_hook_policy import GetHookPolicy

    marker = env.checkout_dir / "command-ran"
    code = (
        f"open({str(marker)!r}, 'w').write('ran'); "
        'print(\'{"schema":"urn:skm:integrations:host-command-output:v1","decision":"deny"}\')'
    )
    subscription = {
        "class": "enforcement",
        "kind": "command",
        "execution_location": "host",
        "event_types": ["client:pre_shell"],
        "target": {"argv": [sys.executable, "-c", code], "cwd": "checkout"},
        "failure_policy": "deny",
    }

    def configure() -> None:
        env.client.dispatch(
            SetValue.from_json(
                {
                    "scope": {"level": "project", "scope_id": str(env.project_id)},
                    "key": "hooks.subscriptions",
                    "value": {"audit": subscription},
                    "reason": "test",
                    "confirmed": True,
                }
            )
        )

    configure()
    app = bind_cli_subscriptions(
        env.app, SimpleNamespace(host_id=env.ctx.host_id, state_dir=env.state_dir), {}
    )
    ctx = app.host.context(client=env.client, cancel=CancelSource().token, log=env.ctx.log)
    ctx = with_hook_state(ctx, env.state_dir)
    query = GetHookPolicy.from_json({"project_id": str(env.project_id), "target": "claude_code"})
    policy = env.client.ask(query)
    return SimpleNamespace(
        ctx=ctx, app=app, marker=marker, subscription=subscription, configure=configure, policy=policy
    )
