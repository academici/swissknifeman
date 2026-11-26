"""Bus step ``load_config`` with the real ``ConfigLoader`` over the memory backend (settings §B.13.1).

``ctx.config`` is computed once per request, after authorization, inside the request's unit of work and from
the ports of that unit of work. A handler that writes configuration sees its own writes through the same
ports (settings preview); a failed command leaves no snapshot in the shared cache; another bus with its own
loader over the same backend sees the new generation after commit.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from runpy import run_path
from typing import Any, cast, override
from uuid import UUID, uuid4

import pytest

from fakes.app import FakeGateways, FakeScopeChain, request_id
from fakes.authorizer import FakeAuthorizer
from fakes.clock import FrozenClock
from fakes.demo_module import (
    ECHO,
    GET_ECHO,
    PERMISSIONS,
    SCHEMA_ROOT,
    Echo,
    EchoResult,
    GetEcho,
    GetEchoResult,
    manifest,
)
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.config_store import (
    MemoryConfigStore,
    increment_config_generation,
    write_config_entry,
)
from skm.adapters.memory.core import REPOSITORIES
from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.uow import InMemoryBackend
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.context import CommandContext, QueryContext
from skm.application_bus.registry import BusRegistry
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, InternalError, ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.access import settings as access_settings
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.keys import Chain
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.scopes import ScopeRef as ConfigScopeRef
from skm.platform.config.store import ConfigStore, EmptyPackConfigSource, ScopeTree, StoredContribution
from skm.platform.schema.registry import SchemaRegistry
from support.seed import Seed, seed_backend

h = run_path(str(Path(__file__).parents[1] / "platform" / "config" / "test_frozen.py"))


class ConfigWrites:
    """Test-only repository port: the writes a settings handler performs inside its unit of work."""

    def __init__(self, state: MemoryBackendState) -> None:
        self.state = state

    def set(self, scope_id: Any, key: str, value: JsonValue) -> None:
        write_config_entry(self.state, scope_id, StoredContribution(uuid4(), key, "set", value, False, 1))
        increment_config_generation(self.state)


class SpyLoader(ConfigLoader):
    """The production loader; records each ``effective`` call and whether its store had pending writes."""

    def __init__(self, registry: SettingsRegistry) -> None:
        super().__init__(registry, EmptyPackConfigSource())
        self.calls: list[tuple[bool, ConfigScopeRef | ScopeRef | None]] = []

    @override
    def effective(self, store: Any, scopes: Any, scope: Any, kind: Chain = Chain.WORK, **kwargs: Any) -> Any:
        self.calls.append((store.pending_writes(), scope))
        return super().effective(store, scopes, scope, kind, **kwargs)


@dataclass
class Rig:
    backend: InMemoryBackend
    bus: Bus
    loader: SpyLoader
    authorizer: FakeAuthorizer
    seed: Seed
    seen: list[EffectiveConfig] = field(default_factory=list[EffectiveConfig])
    previews: list[EffectiveConfig] = field(default_factory=list[EffectiveConfig])

    def meta(self) -> RequestMeta:
        return RequestMeta(
            request_id=request_id(),
            surface=Surface.TEST,
            idempotency_key=None,
            received_at=FrozenClock().now(),
        )

    def echo(self, text: str) -> EchoResult:
        cmd = Echo(workspace_id=self.seed.workspace_id, text=text)
        return cast("EchoResult", self.bus.dispatch(cmd, actor=self.seed.actor(), meta=self.meta()))

    def ask(self) -> GetEchoResult:
        query = GetEcho(workspace_id=self.seed.workspace_id)
        return cast("GetEchoResult", self.bus.ask(query, actor=self.seed.actor(), meta=self.meta()))


def _read(config: object) -> str:
    """``demo.rounds`` of a work chain, ``demo.host_restart`` of a host chain."""
    effective = cast("EffectiveConfig", config)
    key = "demo.host_restart" if effective.chain.kind is Chain.HOST else "demo.rounds"
    return str(effective.get(key))


def build_rig(
    registry: SettingsRegistry,
    backend: InMemoryBackend | None = None,
    *,
    scope_of: Callable[[object], ScopeRef] | None = None,
    audit: bool = False,
) -> Rig:
    """``demo.echo`` reads or writes ``demo.rounds``: ``read``, ``set:<n>`` or ``set:<n>:fail``; ``plain``
    reads no key.

    ``scope_of`` replaces the scope of both operations (a host-scoped operation, settings §A.7/A.8);
    ``audit`` turns the allowed audit of the command on.
    """
    schemas = SchemaRegistry.load(SCHEMA_ROOT)
    holder: list[Rig] = []

    def handle(cmd: Echo, ctx: CommandContext, uow: UnitOfWork) -> EchoResult:
        rig = holder[0]
        rig.seen.append(cast("EffectiveConfig", ctx.config))
        if cmd.text.startswith("set:"):
            _verb, value, *fail = cmd.text.split(":")
            uow.repo(ConfigWrites).set(rig.seed.workspace_id, "demo.rounds", int(value))
            scope = ScopeRef(kind=ScopeKind.WORKSPACE, id=ctx.scope.id)
            rig.previews.append(rig.loader.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), scope))
            if fail:
                raise RuntimeError("handler failed after the write")
        if cmd.text == "plain":
            return EchoResult(text=cmd.text)
        return EchoResult(text=_read(ctx.config))

    def handle_query(query: GetEcho, ctx: QueryContext, uow: UnitOfWork) -> GetEchoResult:
        holder[0].seen.append(cast("EffectiveConfig", ctx.config))
        return GetEchoResult(texts=(_read(ctx.config),))

    command = replace(ECHO, handler=handle, audit=audit)
    query = replace(GET_ECHO, handler=handle_query)
    if scope_of is not None:
        command, query = replace(command, scope_of=scope_of), replace(query, scope_of=scope_of)
    bus_registry = BusRegistry.build(
        (manifest(commands=(command,), queries=(query,)),),
        schemas=schemas,
        permission_catalog=PERMISSIONS,
        disabled_modules=frozenset(),
    )
    clock, ids = FrozenClock(), SequentialIds()
    seed: Seed
    if backend is None:
        factories: dict[type, Any] = {
            **REPOSITORIES,
            ConfigStore: MemoryConfigStore,
            ConfigWrites: ConfigWrites,
        }
        backend = InMemoryBackend(
            factories=factories,
            schemas=schemas,
            subscriptions=bus_registry.subscription_index(),
            ids=ids,
            clock=clock,
        )
        seed = seed_backend(backend.uow_factory())
    else:
        from support.seed import SEED

        seed = SEED
    loader = SpyLoader(registry)
    authorizer = FakeAuthorizer()
    bus = Bus(
        registry=bus_registry,
        schemas=schemas,
        uow_factory=backend.uow_factory(),
        authorizer=authorizer,
        scopes=FakeScopeChain(),
        config=loader,
        clock=clock,
        ids=ids,
        entropy=DeterministicEntropy(),
        gateways=cast("Any", FakeGateways()),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )
    rig = Rig(backend=backend, bus=bus, loader=loader, authorizer=authorizer, seed=seed)
    holder.append(rig)
    return rig


@pytest.fixture(scope="module")
def registry(tmp_path_factory: pytest.TempPathFactory) -> SettingsRegistry:
    return h["build_registry"](tmp_path_factory.mktemp("bus-config"), h["PROPERTIES"])


@pytest.fixture
def rig(registry: SettingsRegistry) -> Rig:
    return build_rig(registry)


def test_ctx_config_is_the_effective_config_of_the_command_scope(rig: Rig) -> None:
    assert rig.echo("read").text == "2"
    (config,) = rig.seen
    assert isinstance(config, EffectiveConfig)
    assert config.chain.kind is Chain.WORK
    assert config.chain.ids() == (rig.seed.instance_id, rig.seed.workspace_id)
    assert config.generation == 0
    assert len(rig.loader.calls) == 1  # computed once per command


def test_load_config_runs_only_after_authorization(rig: Rig) -> None:
    rig.authorizer.allowed = set()
    with pytest.raises(Forbidden):
        rig.echo("read")
    with pytest.raises(Forbidden):
        rig.ask()
    assert rig.loader.calls == []
    assert rig.seen == []


def test_queries_get_the_config_of_their_readonly_unit_of_work(rig: Rig) -> None:
    rig.echo("set:5")
    assert rig.ask().texts == ("5",)
    assert rig.seen[-1].generation == 1
    assert rig.loader.calls[-1][0] is False


def test_settings_preview_sees_own_writes_and_a_failed_command_leaves_the_cache_clean(rig: Rig) -> None:
    before = (rig.echo("read"), rig.seen[-1])
    with pytest.raises(InternalError) as failed:
        rig.echo("set:7:fail")
    assert failed.value.code is ErrorCode.INTERNAL_ERROR
    (preview,) = rig.previews
    assert (preview.generation, preview.get("demo.rounds")) == (1, 7)  # own uncommitted write
    assert rig.loader.calls[-1][0] is True  # the preview ran with pending writes
    assert rig.seen[-1].get("demo.rounds") == 2  # ctx.config was loaded before the handler wrote
    assert rig.echo("read").text == before[0].text == "2"
    assert rig.seen[-1] is before[1]  # still the committed snapshot of generation 0
    rig.echo("set:9")  # commits generation 1 again, with other content
    assert rig.echo("read").text == "9"
    assert rig.seen[-1].generation == 1


def test_ctx_config_is_cached_between_commands_until_a_config_commit(rig: Rig) -> None:
    rig.echo("read")
    rig.echo("read")
    assert rig.seen[0] is rig.seen[1]
    rig.echo("set:4")
    rig.echo("read")
    assert rig.seen[-1] is not rig.seen[0]
    assert rig.seen[-1].get("demo.rounds") == 4


def test_host_scoped_operations_get_the_host_chain_after_authorization(registry: SettingsRegistry) -> None:
    host = ScopeId(UUID("00000000-0000-4000-8000-000000000123"))
    rig = build_rig(registry, scope_of=lambda _dto: ScopeRef(kind=ScopeKind.HOST, id=host))
    with rig.backend.uow_factory()(rig.meta()) as uow:
        uow.repo(ScopeRegistry).create(host, ScopeKind.HOST, parent=rig.seed.instance_id, workspace_id=None)
        uow.repo(ConfigWrites).set(host, "demo.host_restart", "this-host")
        uow.commit()
    assert rig.ask().texts == ("this-host",)
    assert rig.echo("read").text == "this-host"
    assert [call.scope_id for call in rig.authorizer.calls] == [host, host]
    query_config, command_config = rig.seen
    for config in (query_config, command_config):
        assert config.chain.kind is Chain.HOST
        assert config.chain.ids() == (rig.seed.instance_id, host)
    assert command_config is query_config  # one committed host snapshot, not mixed with the work cache
    work = build_rig(registry, rig.backend)
    assert work.echo("read").text == "2"
    assert work.seen[-1].chain.kind is Chain.WORK
    with pytest.raises(ValidationFailed) as no_host_key:
        work.seen[-1].get("demo.host_restart")  # a work chain resolves no host key
    assert no_host_key.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED


def test_another_bus_with_its_own_loader_sees_the_new_generation_after_commit(registry, rig: Rig) -> None:
    other = build_rig(registry, rig.backend)
    assert other.echo("read").text == "2"
    rig.echo("set:6")
    assert other.echo("read").text == "6"
    assert other.seen[-1].generation == 1


# ---------------------------------------------------------------- allowed audit policy (kernel §4.4)

HOST = ScopeId(UUID("00000000-0000-4000-8000-000000000456"))
HOST_REF = ScopeRef(kind=ScopeKind.HOST, id=HOST)
RECORD_ALLOWED = "access.audit.record_allowed"


@pytest.fixture(scope="module")
def access_registry() -> SettingsRegistry:
    """The packaged ``access`` section: ``access.audit.record_allowed`` is a work key (instance/workspace)."""
    return SettingsRegistry.build(
        SchemaRegistry.load_default(),
        ["urn:skm:settings:access:v1"],
        views=access_settings.VIEWS,
        validators=access_settings.VALIDATORS,
        known_permissions=frozenset(),
    )


def host_rig(registry: SettingsRegistry, **policy: JsonValue) -> Rig:
    """An audited host-scoped ``demo.echo``; ``policy`` writes ``record_allowed`` per level name."""
    rig = build_rig(registry, scope_of=lambda _dto: HOST_REF, audit=True)
    levels = {"instance": rig.seed.instance_id, "workspace": rig.seed.workspace_id}
    with rig.backend.uow_factory()(rig.meta()) as uow:
        uow.repo(ScopeRegistry).create(HOST, ScopeKind.HOST, parent=rig.seed.instance_id, workspace_id=None)
        for level, value in policy.items():
            uow.repo(ConfigWrites).set(levels[level], RECORD_ALLOWED, value)
        uow.commit()
    return rig


def test_host_scoped_command_reads_the_audit_policy_from_the_instance_work_chain(access_registry) -> None:
    rig = host_rig(access_registry)
    assert rig.echo("plain").text == "plain"  # was CONFIG_SCOPE_NOT_ALLOWED from the host chain
    (config,) = rig.seen
    assert config.chain.kind is Chain.HOST  # ctx.config stays the host chain
    with pytest.raises(ValidationFailed) as host_chain:
        config.get(RECORD_ALLOWED)
    assert host_chain.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    assert [scope for _pending, scope in rig.loader.calls] == [HOST_REF, None]  # host chain, then instance
    (audit,) = rig.backend.committed.core.audit
    assert (audit.decision, audit.action, audit.workspace_id) == ("allowed", "demo.echo", None)
    assert audit.target == {"scope": {"kind": "host", "id": str(HOST)}, "permission": "demo.echo"}


def test_instance_policy_switches_host_audit_off_and_a_workspace_policy_does_not(access_registry) -> None:
    quiet_workspace = host_rig(access_registry, workspace=False)
    assert quiet_workspace.echo("plain").text == "plain"
    (audit,) = quiet_workspace.backend.committed.core.audit  # a host has no workspace: instance decides
    assert audit.target["scope"] == {"kind": "host", "id": str(HOST)}
    work = build_rig(access_registry, quiet_workspace.backend, audit=True)
    work.echo("plain")  # the workspace command follows its workspace policy
    assert len(quiet_workspace.backend.committed.core.audit) == 1

    quiet_instance = host_rig(access_registry, instance=False)
    assert quiet_instance.echo("plain").text == "plain"
    assert quiet_instance.backend.committed.core.audit == []


def test_invalid_audit_policy_fails_the_host_command_before_the_handler(access_registry) -> None:
    rig = host_rig(access_registry, instance="sometimes")
    with pytest.raises(ValidationFailed) as raised:
        rig.echo("plain")
    assert raised.value.code is ErrorCode.CONFIG_INVALID  # fail closed: no unaudited mutation
    assert rig.seen == []
    assert rig.backend.committed.core.audit == []
    assert rig.backend.committed.core.events == []
