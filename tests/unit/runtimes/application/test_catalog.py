"""Catalog parsing/merging/overrides, application bus handlers, host detection and ``skm runtime`` CLI."""

from __future__ import annotations

import io
import json
import tomllib
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from secrets import token_bytes
from typing import Any, cast
from uuid import UUID

import pytest

from contracts.extensions.harness import (
    PROMPT_BLOCKS,
    FakeBuiltinPacks,
    FakeEstimator,
    pack_payload,
    profile_toml,
)
from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.access import REPOSITORIES as ACCESS_REPOSITORIES
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core import REPOSITORIES as CORE_REPOSITORIES
from skm.adapters.memory.extensions import REPOSITORIES as EXTENSIONS_REPOSITORIES
from skm.adapters.memory.policy import REPOSITORIES as POLICY_REPOSITORIES
from skm.adapters.memory.runtimes import REPOSITORIES as RUNTIMES_REPOSITORIES
from skm.adapters.memory.settings import REPOSITORIES as SETTINGS_REPOSITORIES
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.memory.workspace import REPOSITORIES as WORKSPACE_REPOSITORIES
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.client import EmbeddedClient, EventReaderSession, new_request_id
from skm.application_bus.host import HostServices
from skm.application_bus.ports import Authorizer, EventReader
from skm.application_bus.registry import BusRegistry
from skm.entrypoints.cli.commands import runtime as runtime_cli
from skm.entrypoints.cli.commands.runtime import GROUP as RUNTIME_GROUP
from skm.entrypoints.cli.context import CliRedactor, CliSession
from skm.entrypoints.cli.host import host_context_factory
from skm.entrypoints.cli.parser import build_parser, options_from, parse_command_line
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    BackendUnavailable,
    Conflict,
    Forbidden,
    NotFound,
    PreconditionFailed,
    ValidationFailed,
)
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, PrincipalId, ProjectId, ResourceVersionId, ScopeId, WorkerId, WorkspaceId
from skm.kernel.isolation import IsolationProfile
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.kernel.tokens import TokenEstimator
from skm.modules.access import public as access
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.module import MODULE as ACCESS
from skm.modules.access.ports import MembershipRepository, PrincipalRepository, TokenPepperSource
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.extensions import public as extensions
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.module import MODULE as EXTENSIONS
from skm.modules.extensions.ports import BuiltinPacks, RuntimeCatalogSeeder
from skm.modules.policy.module import MODULE as POLICY
from skm.modules.runtimes import public as runtimes
from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    RuntimeCapabilities,
    StaticCapabilityCatalog,
    VerificationContext,
)
from skm.modules.runtimes.domain.catalog import (
    ModelStatus,
    is_catalog_stale,
    load_catalog,
    merge_catalogs,
)
from skm.modules.runtimes.domain.classes import ModelClass
from skm.modules.runtimes.domain.detection import CancellationResult, DetectProbe
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.domain.usage import UsageReport, UsageStatus, cost, unknown_usage
from skm.modules.runtimes.generated.commands import (
    RecordHostRuntimes,
    RecordHostRuntimesInstallationsItem,
    RecordHostRuntimesModelOffersItem,
)
from skm.modules.runtimes.module import DETECT_RUNTIMES_SPEC
from skm.modules.runtimes.module import MODULE as RUNTIMES
from skm.modules.runtimes.ports import (
    AgentRuntime,
    CapabilityCatalog,
    HostRuntimeRepository,
    ModelCatalogRepository,
    RuntimeRegistry,
    SessionHandle,
)
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.settings.module import MODULE as SETTINGS
from skm.modules.workspace.domain.host import (
    HostArch as DomainHostArch,
)
from skm.modules.workspace.domain.host import (
    HostOs as DomainHostOs,
)
from skm.modules.workspace.domain.host import (
    HostPlatform as DomainHostPlatform,
)
from skm.modules.workspace.domain.worker import Worker, WorkerCapabilities, WorkerState
from skm.modules.workspace.generated.commands import HostArch, HostOs
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.modules.workspace.ports import WorkerRepository
from skm.modules.workspace.public import (
    CreateProject,
    CreateWorkspace,
    RegisterHost,
    RegisterHostDefsHostPlatform,
)
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource, ScopeTree
from unit.policy.application.harness import (
    EVERYTHING,
    INSTANCE,
    NOW,
    FixedPepper,
    Packs,
    schemas,
    settings_registry,
)

ROOT = Path(__file__).resolve().parents[4]
CORE_MODELS_TOML = (ROOT / "resources/packs/core/runtimes/models.toml").read_text(encoding="utf-8")
BINARY_SHA = "sha256:" + "d" * 64
LAUNCH_SHA = "sha256:" + "c" * 64

PLUGIN_MODELS_TOML = """
schema = "urn:skm:runtimes:model-catalog:v1"
catalog_version = "1.2.0"

[runtimes.acme_cli]
class_selectors = { economy = ["acme-lite"], implementation = ["acme-pro"], frontier = ["acme-max"] }
effort_selectors = { low = "low", medium = "medium", high = "high", xhigh = "xhigh" }

[[runtimes.acme_cli.models]]
id = "acme-pro"
display_name = "Acme Pro"
classes = ["implementation"]
suited_roles = ["executor"]
context_window_tokens = 160000
patterns = ["acme-pro-\\\\d+"]
status = "confirmed"
verified_at = "2026-10-20"
source = "https://acme.example/pricing"
notes = ""

[runtimes.acme_cli.models.pricing]
input_per_mtok_usd = "2.50"
output_per_mtok_usd = "10.00"
currency = "USD"
verified_at = "2026-10-20"
source = "https://acme.example/pricing"
"""


@dataclass(frozen=True, slots=True)
class _FakeCatalogResource:
    key: str
    resource_version_id: ResourceVersionId
    manifest: Mapping[str, JsonValue]


def _resource(key: str, idx: int, toml_text: str) -> _FakeCatalogResource:
    raw = tomllib.loads(toml_text)
    return _FakeCatalogResource(
        key=key,
        resource_version_id=ResourceVersionId(UUID(int=idx)),
        manifest=cast("Mapping[str, JsonValue]", raw),
    )


def _static_caps(runtime_id: str) -> RuntimeCapabilities:
    records = {
        Capability.HEADLESS_EXECUTION: CapabilityRecord(
            Capability.HEADLESS_EXECUTION, CapabilityStatus.NATIVE, "cli", None, "", None
        ),
        Capability.STRUCTURED_RESULT: CapabilityRecord(
            Capability.STRUCTURED_RESULT, CapabilityStatus.NATIVE, "json", None, "", None
        ),
        Capability.STREAM_EVENTS: CapabilityRecord(
            Capability.STREAM_EVENTS, CapabilityStatus.NATIVE, "jsonl", None, "", None
        ),
        Capability.MODEL_SELECTION: CapabilityRecord(
            Capability.MODEL_SELECTION, CapabilityStatus.NATIVE, "-m", None, "", None
        ),
        Capability.EFFORT_CONTROL: CapabilityRecord(
            Capability.EFFORT_CONTROL, CapabilityStatus.NATIVE, "--effort", None, "", None
        ),
        Capability.USAGE_REPORTING: CapabilityRecord(
            Capability.USAGE_REPORTING, CapabilityStatus.NATIVE, "usage", None, "", None
        ),
        Capability.CONFIG_ISOLATION: CapabilityRecord(
            Capability.CONFIG_ISOLATION, CapabilityStatus.ADAPTED, "HOME", None, "", None
        ),
    }
    return RuntimeCapabilities(
        runtime_id=runtime_id,
        adapter_version="1.0.0",
        records=records,
        self_loads=(),
        read_only_network=False,
        config_isolation=None,
    )


class _FakeAdapter:
    def __init__(self, runtime_id: str, detect_fn: Callable[[DetectProbe], RuntimeInstallation]) -> None:
        self.runtime_id = runtime_id
        self._detect_fn = detect_fn

    def capabilities(self) -> RuntimeCapabilities:
        return _static_caps(self.runtime_id)

    def detect(self, probe: DetectProbe) -> RuntimeInstallation:
        return self._detect_fn(probe)

    def self_loaded_context(self, request: runtimes.AgentRequest) -> tuple[runtimes.SelfLoadedSource, ...]:
        raise NotImplementedError

    def start(self, request: runtimes.AgentRequest) -> SessionHandle:
        raise NotImplementedError

    def events(self, handle: SessionHandle) -> Iterator[runtimes.SessionEvent]:
        raise NotImplementedError

    def cancel(self, handle: SessionHandle, *, grace_seconds: float) -> CancellationResult:
        raise NotImplementedError

    def result(self, handle: SessionHandle) -> runtimes.RuntimeResult:
        raise NotImplementedError


class _FakeRuntimeRegistry:
    def __init__(self, adapters: Mapping[str, AgentRuntime]) -> None:
        self._adapters = dict(adapters)

    def set_adapters(self, adapters: Mapping[str, AgentRuntime]) -> None:
        self._adapters = dict(adapters)

    def ids(self) -> frozenset[str]:
        return frozenset(self._adapters)

    def get(self, runtime_id: str) -> AgentRuntime:
        adapter = self._adapters.get(runtime_id)
        if adapter is None:
            raise NotFound(ErrorCode.NOT_FOUND, f"unknown {runtime_id}", details={"kind": "runtime"})
        return adapter


@dataclass
class _RuntimesWorld:
    backend: InMemoryBackend
    bus: Bus
    clock: FrozenClock
    ids: SequentialIds
    loader: ConfigLoader
    builtin: FakeBuiltinPacks
    gateways: GatewayTable
    runtime_registry: _FakeRuntimeRegistry
    owner: Actor
    workspace_id: WorkspaceId
    project_id: ProjectId
    run_scope_id: ScopeId
    host_a: HostId
    host_b: HostId
    counter: int = 0
    people: dict[str, Actor] = field(default_factory=dict[str, Actor])

    def meta(self, key: str | None = None) -> RequestMeta:
        self.counter += 1
        return RequestMeta(f"req_{self.counter:0>26}", Surface.TEST, key, self.clock.now())

    def uow(self, *, readonly: bool = False) -> Any:
        return self.backend.uow_factory()(self.meta(), readonly=readonly)

    def actor(self, who: Actor | str) -> Actor:
        return self.people[who] if isinstance(who, str) else who

    def dispatch(self, dto: object, actor: Actor | str = "owner", *, key: str | None = None) -> Any:
        return self.bus.dispatch(dto, actor=self.actor(actor), meta=self.meta(key))

    def ask(self, dto: object, actor: Actor | str = "owner") -> Any:
        return self.bus.ask(dto, actor=self.actor(actor), meta=self.meta())

    def set_config(self, key: str, value: JsonValue, level: str = "instance") -> None:
        scope = SetValueDefsScopeRef(level=cast("Any", level))
        self.dispatch(SetValue(scope=scope, key=key, value=value))

    def effective_config(self, uow: Any) -> Any:
        return self.loader.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.RUN, self.run_scope_id)
        )

    def runtime_events(self, name: str) -> list[Any]:
        urn = f"urn:skm:runtimes:event:{name}:v1"
        return [ev for ev in self.backend.committed.core.events if ev.type == urn]

    def seed_worker(self, name: str, host_id: HostId, runtimes: tuple[str, ...] = ("codex",)) -> Actor:
        principal = new_principal(
            principal_id=PrincipalId(self.ids.new_id()),
            kind=PrincipalKind.WORKER,
            display_name=name,
            created_by=None,
            now=self.clock.now(),
        )
        caps = WorkerCapabilities(
            runtimes=runtimes,
            isolation_profiles=(IsolationProfile.WORKTREE.value,),
            max_concurrency=1,
            labels=(),
            platform=DomainHostPlatform(DomainHostOs.LINUX, DomainHostArch.X86_64),
            skm_version="2.0.0",
        )
        worker = Worker(
            id=WorkerId(self.ids.new_id()),
            workspace_id=self.workspace_id,
            host_id=host_id,
            principal_id=principal.id,
            display_name=name,
            capabilities=caps,
            state=WorkerState.ONLINE,
            last_heartbeat_at=self.clock.now(),
            registered_at=self.clock.now(),
            row_version=1,
        )
        with self.uow() as uow:
            uow.repo(PrincipalRepository).add(principal)
            uow.repo(MembershipRepository).upsert(
                Membership(ScopeId(self.workspace_id), principal.id, Role.WORKER, None, self.clock.now())
            )
            uow.repo(WorkerRepository).add(worker)
            pepper = self.gateways.get(TokenPepperSource).pepper()
            _, secret = access.issue_bound_worker_token(
                uow,
                principal_id=principal.id,
                issuer=self.owner,
                worker_id=worker.id,
                workspace_scope_id=ScopeId(self.workspace_id),
                host_scope_id=ScopeId(host_id),
                token_name=name,
                pepper=pepper,
                entropy=token_bytes,
                now=self.clock.now(),
                settings=None,
            )
            actor = access.authenticate_token(uow, secret, pepper=pepper, now=self.clock.now())
            uow.commit()
        self.people[name] = actor
        return actor

    def client(self, actor: Actor | str = "owner", *, surface: Surface = Surface.CLI) -> EmbeddedClient:
        @contextmanager
        def reader_session() -> Iterator[EventReader]:
            with self.uow(readonly=True) as uow:
                yield uow.repo(EventReader)

        def open_events() -> EventReaderSession:
            return reader_session()

        return EmbeddedClient(
            self.bus,
            actor=self.actor(actor),
            surface=surface,
            events=open_events,
            clock=self.clock,
            ids=self.ids,
            client_label="test-cli",
        )

    def host_services(self, *, host_id: HostId | None = None) -> HostServices:
        target_host = self.host_a if host_id is None else host_id
        cap_cat = StaticCapabilityCatalog(
            declarations={
                rid: _static_caps(rid) for rid in ("codex", "claude_code", "grok", "cursor", "antigravity")
            },
            rules={},
        )
        host_gateways = GatewayTable(
            {RuntimeRegistry: self.runtime_registry, CapabilityCatalog: cap_cat},
            "host_gateway",
        )

        def host_cfg() -> object:
            with self.uow(readonly=True) as uow:
                return self.loader.effective(
                    uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.HOST, ScopeId(target_host))
                )

        return HostServices(
            host_id=target_host,
            surface=Surface.CLI,
            gateways=host_gateways,
            host_config=host_cfg,
            operations={DETECT_RUNTIMES_SPEC.name: DETECT_RUNTIMES_SPEC},
        )


def _build_world() -> _RuntimesWorld:
    bus_registry = BusRegistry.build(
        (ACCESS, WORKSPACE, SETTINGS, POLICY, EXTENSIONS, RUNTIMES),
        schemas=schemas(),
        permission_catalog=EVERYTHING,
        disabled_modules=frozenset(),
    )
    clock, ids, entropy = FrozenClock(NOW), SequentialIds(), DeterministicEntropy()
    packs, authorizer = Packs(), RbacAuthorizer(clock)
    factories: dict[type, Callable[[Any], object]] = {
        **CORE_REPOSITORIES,
        **ACCESS_REPOSITORIES,
        **WORKSPACE_REPOSITORIES,
        **SETTINGS_REPOSITORIES,
        **POLICY_REPOSITORIES,
        **EXTENSIONS_REPOSITORIES,
        **RUNTIMES_REPOSITORIES,
        ConfigStore: MemoryConfigStore,
        PackConfigSource: lambda _state: packs,
        Authorizer: lambda _state: authorizer,
    }
    backend = InMemoryBackend(
        factories=factories,
        schemas=schemas(),
        subscriptions=bus_registry.subscription_index(),
        ids=ids,
        clock=clock,
    )
    core_pack = pack_payload(
        "core",
        "1.0.0",
        files={
            **PROMPT_BLOCKS,
            "agent-profiles/executor.toml": profile_toml(),
            "runtimes/models.toml": CORE_MODELS_TOML,
        },
    )
    builtin = FakeBuiltinPacks(core_pack)
    cap_cat = StaticCapabilityCatalog(
        declarations={
            rid: _static_caps(rid) for rid in ("codex", "claude_code", "grok", "cursor", "antigravity")
        },
        rules={},
    )
    runtime_registry = _FakeRuntimeRegistry({})
    loader = ConfigLoader(settings_registry(), packs)
    cp_gateways = GatewayTable(
        {
            TokenPepperSource: FixedPepper(),
            BuiltinPacks: builtin,
            RuntimeCatalogSeeder: runtimes.seed_builtin_model_catalog,
            TokenEstimator: FakeEstimator(),
            CapabilityCatalog: cap_cat,
        },
        "control_plane_gateway",
    )
    bus = Bus(
        registry=bus_registry,
        schemas=schemas(),
        uow_factory=backend.uow_factory(),
        authorizer=authorizer,
        scopes=FakeScopeChain(),
        config=loader,
        clock=clock,
        ids=ids,
        entropy=entropy,
        gateways=cp_gateways,
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )

    uow_factory = backend.uow_factory()
    meta = RequestMeta("req_" + "0" * 26, Surface.TEST, None, clock.now())
    with uow_factory(meta, readonly=False) as uow:
        uow.repo(ScopeRegistry).create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        owner_p = new_principal(
            principal_id=PrincipalId(ids.new_id()),
            kind=PrincipalKind.HUMAN,
            display_name="owner",
            created_by=None,
            now=clock.now(),
        )
        uow.repo(PrincipalRepository).add(owner_p)
        uow.repo(MembershipRepository).upsert(Membership(INSTANCE, owner_p.id, Role.OWNER, None, NOW))
        uow.commit()

    owner = Actor(principal_id=owner_p.id, kind=PrincipalKind.HUMAN, display_name="owner")
    world = _RuntimesWorld(
        backend=backend,
        bus=bus,
        clock=clock,
        ids=ids,
        loader=loader,
        builtin=builtin,
        gateways=cp_gateways,
        runtime_registry=runtime_registry,
        owner=owner,
        workspace_id=WorkspaceId(UUID(int=0)),
        project_id=ProjectId(UUID(int=0)),
        run_scope_id=ScopeId(UUID(int=0)),
        host_a=HostId(UUID(int=0)),
        host_b=HostId(UUID(int=0)),
        people={"owner": owner},
    )
    world.workspace_id = WorkspaceId(
        world.dispatch(CreateWorkspace(slug="personal", title="Personal")).workspace_id
    )
    world.project_id = ProjectId(
        world.dispatch(CreateProject(workspace_id=world.workspace_id, slug="skm", title="SKM")).project_id
    )
    plan_id, run_id = ScopeId(world.ids.new_id()), ScopeId(world.ids.new_id())
    with world.uow() as uow:
        scopes = uow.repo(ScopeRegistry)
        scopes.create(
            plan_id, ScopeKind.PLAN, parent=ScopeId(world.project_id), workspace_id=world.workspace_id
        )
        scopes.create(run_id, ScopeKind.RUN, parent=plan_id, workspace_id=world.workspace_id)
        uow.commit()
    world.run_scope_id = run_id
    platform = RegisterHostDefsHostPlatform(os=HostOs.LINUX, arch=HostArch.X86_64)
    world.host_a = HostId(world.dispatch(RegisterHost(name="host-a", platform=platform)).host_id)
    world.host_b = HostId(world.dispatch(RegisterHost(name="host-b", platform=platform)).host_id)
    world.dispatch(SyncBuiltinPacks())
    return world


# ---------------------------------------------------------------------------
# Pure catalog domain tests (domain/catalog.py)
# ---------------------------------------------------------------------------


def _usage(inp: int, out: int) -> UsageReport:
    return replace(
        unknown_usage(),
        input_tokens=inp,
        output_tokens=out,
        cache_read_tokens=0,
        cache_write_tokens=0,
        status=UsageStatus.REPORTED,
        source="stream:result",
    )


def test_parse_real_core_catalog_and_merge_plugin_catalog() -> None:
    core_res = _resource("models", 1, CORE_MODELS_TOML)
    plugin_res = _resource("acme-models", 2, PLUGIN_MODELS_TOML)

    merged_ab = merge_catalogs([core_res, plugin_res])
    merged_ba = merge_catalogs([plugin_res, core_res])
    assert merged_ab.digest == merged_ba.digest
    assert merged_ab.digest.startswith("sha256:")
    assert merged_ab.catalog_version == "2.0.2"
    assert set(merged_ab.runtimes) == {
        "antigravity",
        "claude_code",
        "codex",
        "grok",
        "cursor",
        "gemini_cli",
        "acme_cli",
    }

    gemini = merged_ab.pick("gemini_cli", ModelClass.ECONOMY)
    assert gemini is not None
    assert gemini.id == "gemini-3.8-flash"

    picked = merged_ab.pick("codex", ModelClass.ECONOMY)
    assert picked is not None
    assert picked.id == "gpt-6-luna"
    astra_variant = merged_ab.model("codex", "gpt-6.2-astra")
    assert astra_variant is not None
    assert astra_variant.id == "gpt-6-astra"
    assert astra_variant.pricing is None

    usage = _usage(100_000, 50_000)
    assert cost(usage, astra_variant.pricing) is None

    acme = merged_ab.model("acme_cli", "acme-pro-2026")
    assert acme is not None
    assert acme.pricing is not None
    assert acme.pricing.input_per_mtok_usd == Decimal("2.50")
    assert acme.pricing.output_per_mtok_usd == Decimal("10.00")
    assert cost(usage, acme.pricing) == 750_000


def test_merge_catalogs_rejects_duplicate_runtime_and_floats() -> None:
    dup_a = _resource("a-first", 1, CORE_MODELS_TOML)
    dup_b = _resource("z-second", 2, CORE_MODELS_TOML)
    with pytest.raises(Conflict) as conflict_info:
        merge_catalogs([dup_b, dup_a])
    assert conflict_info.value.code is ErrorCode.EXTENSION_OVERRIDE_NOT_DECLARED
    assert conflict_info.value.details == {
        "reason": "CONFIG_CONFLICT",
        "runtime_id": "antigravity",
        "resources": ["a-first", "z-second"],
    }

    bad_float_manifest: dict[str, Any] = {
        "schema": "urn:skm:runtimes:model-catalog:v1",
        "catalog_version": "1.0.0",
        "runtimes": {"acme": {"bad_float": 1.5}},
    }
    bad_res = _FakeCatalogResource("bad", ResourceVersionId(UUID(int=9)), bad_float_manifest)
    with pytest.raises(ValidationFailed) as float_err:
        merge_catalogs([bad_res])
    assert float_err.value.code is ErrorCode.CONFIG_INVALID
    assert float_err.value.details.get("reason") == "float_in_catalog"


def test_load_catalog_applies_overrides_and_recomputes_digest_and_staleness() -> None:
    core_res = _resource("models", 1, CORE_MODELS_TOML)
    base = load_catalog([core_res])
    overridden = load_catalog(
        [core_res],
        overrides={
            "codex:gpt-6-luna": {"status": "deprecated"},
            "codex:gpt-6-sol": {
                "context_window_tokens": 256000,
                "input_usd_per_mtok": "1.25",
                "output_usd_per_mtok": "5.00",
            },
        },
    )
    assert overridden.digest != base.digest
    economy = overridden.pick("codex", ModelClass.ECONOMY)
    assert economy is not None
    assert economy.id == "gpt-5.6-luna"

    sol = overridden.model("codex", "gpt-6-sol")
    assert sol is not None
    assert sol.status is ModelStatus.UNVERIFIED
    assert sol.context_window_tokens == 256000
    assert sol.pricing is not None
    assert sol.pricing.input_per_mtok_usd == Decimal("1.25")
    assert sol.pricing.output_per_mtok_usd == Decimal("5.00")

    assert not is_catalog_stale(base, today=date(2026, 10, 25), max_age_days=45)
    assert is_catalog_stale(base, today=date(2026, 12, 1), max_age_days=45)


# ---------------------------------------------------------------------------
# Application bus, public facade, host detection and CLI runtime group tests
# ---------------------------------------------------------------------------


def test_facade_catalog_pricing_context_window_and_pack_pins() -> None:
    world = _build_world()
    usage = _usage(200_000, 100_000)

    with world.uow(readonly=True) as uow:
        cfg = world.effective_config(uow)
        cat = runtimes.catalog(uow, config=cfg)
        assert runtimes.model_context_window("gpt-6-sol", catalog=cat) == 128000
        assert runtimes.model_context_window("grok-4.7", catalog=cat) is None
        assert runtimes.model_context_window("unknown-model", catalog=cat) is None
        unpriced = runtimes.usage_cost(uow, usage, "codex", "gpt-6-sol", config=cfg)
        assert unpriced.cost_usd_micros is None
        pins = extensions.pinned_pack_versions(uow, config=cfg)

    updated_toml = CORE_MODELS_TOML.replace(
        'id = "gpt-6-sol"\ndisplay_name = "GPT-6 Sol"\nclasses = ["implementation"]\n'
        'suited_roles = ["executor", "reviewer", "triager"]\ncontext_window_tokens = 128000',
        'id = "gpt-6-sol"\ndisplay_name = "GPT-6 Sol"\nclasses = ["implementation"]\n'
        'suited_roles = ["executor", "reviewer", "triager"]\ncontext_window_tokens = 256000',
    )
    world.builtin.current = (
        *world.builtin.current,
        pack_payload(
            "core",
            "1.1.0",
            files={
                **PROMPT_BLOCKS,
                "agent-profiles/executor.toml": profile_toml(),
                "runtimes/models.toml": updated_toml,
            },
        ),
    )
    world.dispatch(SyncBuiltinPacks())

    with world.uow(readonly=True) as uow:
        cfg = world.effective_config(uow)
        pinned_entry = runtimes.model_entry(uow, "codex", "gpt-6-sol", config=cfg, pins=pins)
        latest_entry = runtimes.model_entry(uow, "codex", "gpt-6-sol", config=cfg)
        assert pinned_entry is not None
        assert pinned_entry.context_window_tokens == 128000
        assert latest_entry is not None
        assert latest_entry.context_window_tokens == 256000

    world.set_config(
        "runtimes.models.overrides",
        {"codex:gpt-6-sol": {"input_usd_per_mtok": 2, "output_usd_per_mtok": 8}},
    )
    with world.uow(readonly=True) as uow:
        cfg = world.effective_config(uow)
        priced = runtimes.usage_cost(uow, usage, "codex", "gpt-6-sol", config=cfg)
        assert priced.cost_usd_micros == 1_200_000


def test_builtin_sync_seeds_catalog_with_shared_identities_and_null_prices() -> None:
    world = _build_world()
    world.dispatch(SyncBuiltinPacks())
    with world.uow(readonly=True) as uow:
        ctx_config = world.effective_config(uow)
        catalog = runtimes.catalog(uow, config=ctx_config)
        repo = uow.repo(ModelCatalogRepository)
        (version_id,) = catalog.resource_version_ids
        guidelines = repo.list_guidelines(version_id)
        models = {model.id for runtime in catalog.runtimes.values() for model in runtime.models}
        assert tuple(row.model_id for row in repo.list_models()) == tuple(sorted(models))
        assert len(guidelines) == sum(len(runtime.models) for runtime in catalog.runtimes.values())
        for runtime_id, inventory in catalog.runtimes.items():
            offerings = {row.model_id: row for row in repo.list_offerings(runtime_id)}
            assert set(offerings) == {model.id for model in inventory.models}
            assert all(offerings[model.id].pricing == model.pricing for model in inventory.models)
        grok = next(row for row in repo.list_offerings("grok") if row.model_id == "grok-4.7")
        cursor = next(row for row in repo.list_offerings("cursor") if row.model_id == "grok-4.7")
        assert grok.pricing is cursor.pricing is None
        assert grok.display_name != cursor.display_name


def test_publish_runtime_catalog_snapshot_preserves_pack_pins_and_caller_rollback() -> None:
    world = _build_world()
    world.set_config("extensions.packs.enabled", ["catalog-snapshot"])

    def publish(version: str, *, commit: bool = True) -> extensions.InstallPackResult:
        manifest = pack_payload(
            "catalog-snapshot",
            version,
            trust="operator",
            extra_manifest='[[overrides]]\nkind = "runtime_catalog"\nkey = "models"\nreason = "sync"\n',
        ).manifest_text
        with world.uow() as uow:
            result = extensions.publish_runtime_catalog_snapshot(
                uow,
                pack_manifest=manifest,
                catalog_toml=CORE_MODELS_TOML.replace(
                    'catalog_version = "2.0.2"', f'catalog_version = "{version}"'
                ),
                installed_by=world.owner.principal_id,
                clock=world.clock,
                ids=world.ids,
                config=world.effective_config(uow),
                estimator=world.gateways.get(TokenEstimator),
            )
            if commit:
                uow.commit()
            return result

    first = publish("3.0.0")
    assert publish("3.0.0").pack_version_id == first.pack_version_id
    with world.uow(readonly=True) as uow:
        pins = extensions.pinned_pack_versions(uow, config=world.effective_config(uow))
    assert pins["catalog-snapshot"] == first.pack_version_id

    publish("3.1.0", commit=False)
    with world.uow(readonly=True) as uow:
        assert runtimes.catalog(uow, config=world.effective_config(uow)).catalog_version == "3.0.0"
    publish("3.1.0")
    with world.uow(readonly=True) as uow:
        cfg = world.effective_config(uow)
        assert runtimes.catalog(uow, config=cfg).catalog_version == "3.1.0"
        assert runtimes.catalog(uow, config=cfg, pins=pins).catalog_version == "3.0.0"


class _SilentTransport:
    def get_text(self, url: str) -> str:
        raise AssertionError(url)


class _PricedCatalogTransport:
    def get_text(self, url: str) -> str:
        if url != "https://models.dev/api.json":
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "document not staged")
        return json.dumps(
            {
                "openai": {
                    "models": {
                        "gpt-6-sol": {
                            "name": 'Reviewed "Sol"\nmodel',
                            "cost": {"input": "1.50", "output": "6.00", "cache_read": "0.10"},
                            "limit": {"context": 256000},
                        },
                        "reviewed-model": {"name": "Reviewed model"},
                        "pending-model": {"name": "Pending model"},
                    }
                }
            }
        )


def test_activate_approved_sync_candidates_for_builtin_runtime() -> None:
    world = _build_world()
    report = runtimes.ModelCatalogSyncJob(
        transport=_PricedCatalogTransport(), today=NOW.date(), provider_runtimes={"openai": "codex"}
    ).run()
    selected = tuple(
        row.candidate for row in report.pending if row.candidate.model_id in {"gpt-6-sol", "reviewed-model"}
    )
    assert len(selected) == 2
    with pytest.raises(ValidationFailed) as rejected:
        report.approve(replace(selected[0], display_name="Different candidate"))
    assert rejected.value.details["reason"] == "candidate_not_pending"
    approved = report.approve(*selected)
    assert report.active == ()
    assert approved.source_errors == report.source_errors

    with world.uow() as uow:
        cfg = world.effective_config(uow)
        pins = extensions.pinned_pack_versions(uow, config=cfg)
        before = runtimes.catalog(uow, config=cfg, pins=pins)
        runtimes.activate_staged_catalog(
            uow,
            approved,
            catalog_version="9.0.0",
            installed_by=world.owner.principal_id,
            clock=world.clock,
            ids=world.ids,
            config=cfg,
            estimator=world.gateways.get(TokenEstimator),
        )
        uow.commit()

    world.set_config("extensions.packs.enabled", ["catalog-sync"])
    with world.uow(readonly=True) as uow:
        cfg = world.effective_config(uow)
        fresh = runtimes.catalog(uow, config=cfg)
        pinned = runtimes.catalog(uow, config=cfg, pins=pins)
    assert pinned == before
    assert fresh.runtimes["codex"].class_selectors == before.runtimes["codex"].class_selectors
    assert fresh.runtimes["codex"].effort_selectors == before.runtimes["codex"].effort_selectors
    assert fresh.pick("codex", ModelClass.ECONOMY) == before.pick("codex", ModelClass.ECONOMY)
    sol = fresh.model("codex", "gpt-6-sol")
    assert sol is not None
    assert sol.pricing is not None
    assert sol.display_name == 'Reviewed "Sol"\nmodel'
    assert sol.pricing.input_per_mtok_usd == Decimal("1.50")
    assert fresh.model("codex", "reviewed-model") is not None
    assert fresh.model("codex", "pending-model") is None


def test_activation_publishes_snapshot_and_preserves_pack_pins() -> None:
    world = _build_world()
    today = date(2026, 11, 23)
    trusted = runtimes.CatalogCandidate(
        source_id=runtimes.CatalogSourceId.MODELS_DEV,
        runtime_id="acme_cli",
        model_id="sync-model",
        provider_model_id="sync-model",
        display_name="Sync model",
        context_window_tokens=128000,
        classes=frozenset({ModelClass.ECONOMY}),
        suited_roles=frozenset({runtimes.RoleId.SCOUT}),
        verified_at=today,
        source="models.dev",
        trust=runtimes.CandidateTrust.OPERATOR,
        pricing=runtimes.PriceQuote(Decimal("1.50"), Decimal("6.00"), verified_at=today, source="models.dev"),
    )
    pending = replace(
        runtimes.FallbackGeneralizationsSource().fetch(
            _SilentTransport(), today=today, provider_runtimes={"acme": "acme_cli"}
        )[0],
        runtime_id="acme_cli",
        model_id="pending-external",
        provider_model_id="pending-external",
    )
    report = runtimes.CatalogSyncReport(runtimes.stage_candidates((pending, trusted)))

    with world.uow(readonly=True) as uow:
        pins = extensions.pinned_pack_versions(uow, config=world.effective_config(uow))
        before = runtimes.catalog(uow, config=world.effective_config(uow), pins=pins).catalog_version
    world.set_config("extensions.packs.enabled", ["catalog-sync"])

    with world.uow() as uow:
        published = runtimes.activate_staged_catalog(
            uow,
            report,
            catalog_version="9.0.0",
            installed_by=world.owner.principal_id,
            clock=world.clock,
            ids=world.ids,
            config=world.effective_config(uow),
            estimator=world.gateways.get(TokenEstimator),
            verified_at=today,
        )
        uow.commit()

    assert published.slug == "catalog-sync"
    assert published.version == "9.0.0"
    with world.uow(readonly=True) as uow:
        cfg = world.effective_config(uow)
        pinned = runtimes.catalog(uow, config=cfg, pins=pins)
        fresh = runtimes.catalog(uow, config=cfg)
        offering = next(
            row
            for row in uow.repo(ModelCatalogRepository).list_offerings("acme_cli")
            if row.model_id == "sync-model"
        )
    assert pinned.catalog_version == before
    assert fresh.catalog_version == before
    assert fresh.model("acme_cli", "sync-model") is not None
    assert pinned.model("acme_cli", "sync-model") is None
    assert pending.model_id not in {
        model.id for runtime in fresh.runtimes.values() for model in runtime.models
    }
    assert offering.pricing is not None
    assert offering.pricing.input_per_mtok_usd == Decimal("1.50")


def test_activation_refuses_untrusted_external_candidates() -> None:
    world = _build_world()
    report = runtimes.ModelCatalogSyncJob(
        transport=_PricedCatalogTransport(), today=NOW.date(), provider_runtimes={"openai": "codex"}
    ).run()
    assert report.pending
    with pytest.raises(PreconditionFailed) as err, world.uow() as uow:
        runtimes.activate_staged_catalog(
            uow,
            report,
            catalog_version="9.0.1",
            installed_by=world.owner.principal_id,
            clock=world.clock,
            ids=world.ids,
            config=world.effective_config(uow),
            estimator=world.gateways.get(TokenEstimator),
        )
    assert err.value.details.get("reason") == "nothing_to_activate"


def test_record_host_runtimes_diff_idempotence_and_worker_isolation() -> None:
    world = _build_world()
    t0 = NOW
    t1 = NOW + timedelta(minutes=5)
    codex_item = RecordHostRuntimesInstallationsItem(
        runtime_id="codex",
        version="0.42.0",
        binary_locator="/usr/local/bin/codex",
        auth_state="ok",
        detected_at=t0,
        details={"channel": "stable"},
    )
    claude_item = RecordHostRuntimesInstallationsItem(
        runtime_id="claude_code",
        version="2.1.0",
        binary_locator="/usr/local/bin/claude",
        auth_state="ok",
        detected_at=t0,
        details={},
    )

    res1 = world.dispatch(RecordHostRuntimes(host_id=world.host_a, installations=(codex_item, claude_item)))
    assert isinstance(res1, runtimes.RecordHostRuntimesResult)
    assert [r.changed for r in res1.runtimes] == [True, True]
    assert len(world.runtime_events("host-runtimes-recorded")) == 1

    res2 = world.dispatch(
        RecordHostRuntimes(
            host_id=world.host_a,
            installations=(replace(codex_item, detected_at=t1), replace(claude_item, detected_at=t1)),
        )
    )
    assert [r.changed for r in res2.runtimes] == [False, False]
    assert len(world.runtime_events("host-runtimes-recorded")) == 1

    res3 = world.dispatch(RecordHostRuntimes(host_id=world.host_a, installations=(codex_item,)))
    assert res3.removed == ("claude_code",)
    assert len(world.runtime_events("host-runtimes-recorded")) == 2

    bad_item = replace(codex_item, runtime_id="unregistered_rt")
    with pytest.raises(ValidationFailed) as bad_rt:
        world.dispatch(RecordHostRuntimes(host_id=world.host_a, installations=(bad_item,)))
    assert bad_rt.value.code is ErrorCode.SCHEMA_INVALID

    worker_a = world.seed_worker("w-host-a", world.host_a)
    own_res = world.dispatch(
        RecordHostRuntimes(
            host_id=world.host_a,
            installations=(codex_item,),
            model_offers_observed_at=NOW,
            model_offers=(),
            refresh_model_offers=True,
        ),
        actor=worker_a,
    )
    assert own_res.host_id == world.host_a
    with pytest.raises(Forbidden) as foreign_err:
        world.dispatch(RecordHostRuntimes(host_id=world.host_b, installations=(codex_item,)), actor=worker_a)
    assert foreign_err.value.code is ErrorCode.FORBIDDEN


def test_record_capability_verification_enforcing_context_and_worker_scope() -> None:
    world = _build_world()
    before = world.ask(runtimes.GetCapabilities(runtime_id="codex", runtime_version="0.42.0"))
    assert isinstance(before, runtimes.RuntimeCapabilitiesView)
    iso_before = next(r for r in before.records if r.capability.value == "config_isolation")
    assert iso_before.status == "unknown"
    assert iso_before.source == "static"

    vctx = VerificationContext(
        host_id=world.host_a,
        binary_sha256=BINARY_SHA,
        os="linux",
        kernel="6.8",
        adapter_version="1.0.0",
        isolation_profile=IsolationProfile.WORKTREE,
        launch_config_digest=LAUNCH_SHA,
    )
    rec_res = world.dispatch(
        runtimes.RecordCapabilityVerification(
            runtime_id="codex",
            runtime_version="0.42.0",
            capability="config_isolation",
            status="native",
            evidence="isolated HOME verified",
            limitations="",
            verified_at=NOW.date(),
            verification_context=vctx,
        )
    )
    assert isinstance(rec_res, runtimes.RecordCapabilityVerificationResult)
    assert rec_res.runtime_id == "codex"
    assert rec_res.status == "native"
    cap_events = world.runtime_events("capability-verified")
    assert len(cap_events) == 1
    assert cap_events[0].payload == {
        "runtime_id": "codex",
        "runtime_version": "0.42.0",
        "capability": "config_isolation",
        "status": "native",
    }

    with world.uow(readonly=True) as uow:
        cfg = world.effective_config(uow)
        eff = runtimes.capabilities(
            uow,
            world.gateways,
            "codex",
            "0.42.0",
            verification_context=vctx,
            config=cfg,
            today=NOW.date(),
        )
        assert eff.status(Capability.CONFIG_ISOLATION) is CapabilityStatus.NATIVE
        assert eff.records[Capability.CONFIG_ISOLATION].verification_context == vctx

    after = world.ask(runtimes.GetCapabilities(runtime_id="codex", runtime_version="0.42.0"))
    assert isinstance(after, runtimes.RuntimeCapabilitiesView)
    iso_after = next(r for r in after.records if r.capability.value == "config_isolation")
    assert iso_after.status == "native"
    assert iso_after.source == "verified"

    worker_a = world.seed_worker("w-verify-a", world.host_a)
    with pytest.raises(Forbidden):
        world.dispatch(
            runtimes.RecordCapabilityVerification(
                runtime_id="codex",
                runtime_version="0.42.0",
                capability="headless_execution",
                status="native",
                evidence="probe",
                limitations="",
                verified_at=NOW.date(),
                verification_context=None,
            ),
            actor=worker_a,
        )
    foreign_ctx = replace(vctx, host_id=world.host_b)
    with pytest.raises(Forbidden):
        world.dispatch(
            runtimes.RecordCapabilityVerification(
                runtime_id="codex",
                runtime_version="0.42.0",
                capability="config_isolation",
                status="native",
                evidence="probe",
                limitations="",
                verified_at=NOW.date(),
                verification_context=foreign_ctx,
            ),
            actor=worker_a,
        )


def test_queries_and_explain_routing_dry_run() -> None:
    world = _build_world()
    world.set_config("runtimes.allowed", ["codex", "claude_code"])
    world.set_config("runtimes.preference", ["codex", "claude_code"])
    world.set_config("runtimes.config_isolation.required", False)

    codex_item = RecordHostRuntimesInstallationsItem(
        runtime_id="codex",
        version="0.42.0",
        binary_locator="/usr/local/bin/codex",
        auth_state="ok",
        detected_at=NOW,
        details={},
    )
    world.dispatch(
        RecordHostRuntimes(
            host_id=world.host_a,
            installations=(codex_item,),
            model_offers=tuple(
                RecordHostRuntimesModelOffersItem(
                    "codex", "gpt-6-sol", effort.value, NOW, NOW + timedelta(minutes=5)
                )
                for effort in runtimes.Effort
            ),
        )
    )

    listed = world.ask(runtimes.ListRuntimes(host_id=world.host_a))
    assert isinstance(listed, runtimes.ListRuntimesResult)
    by_id = {item.runtime_id: item for item in listed.items}
    assert by_id["codex"].allowed_in_scope is True
    assert len(by_id["codex"].installations) == 1

    models_view = world.ask(runtimes.ListModels.from_json({"runtime_id": "codex", "model_class": "economy"}))
    assert isinstance(models_view, runtimes.ModelsView)
    assert {m["id"] for m in models_view.models} == {"gpt-6-luna", "gpt-5.6-luna"}

    explained = world.ask(
        runtimes.ExplainRouting.from_json(
            {
                "role": "executor",
                "scope": {"kind": "run", "id": str(world.run_scope_id)},
                "host_id": str(world.host_a),
            }
        )
    )
    assert isinstance(explained, runtimes.RouteExplainView)
    assert explained.error is None
    assert explained.decision is not None
    assert explained.decision["runtime_id"] == "codex"
    assert explained.decision["model"] == "gpt-6-sol"

    world.set_config("runtimes.allowed", [])
    blocked = world.ask(
        runtimes.ExplainRouting.from_json(
            {"role": "executor", "scope": {"kind": "run", "id": str(world.run_scope_id)}}
        )
    )
    assert isinstance(blocked, runtimes.RouteExplainView)
    assert blocked.decision is None
    assert blocked.error is not None
    assert blocked.error.code == ErrorCode.CAPABILITY_UNAVAILABLE.value


def test_routing_requires_one_fresh_offer_for_the_entire_route() -> None:
    world = _build_world()
    world.set_config("runtimes.allowed", ["codex"])
    world.set_config("runtimes.config_isolation.required", False)
    install = RecordHostRuntimesInstallationsItem("codex", "0.42.0", "/bin/codex", "ok", NOW, {})
    expires = NOW + timedelta(seconds=30)
    other_model = RecordHostRuntimesModelOffersItem("codex", "gpt-6-luna", "high", NOW, expires)
    other_effort = RecordHostRuntimesModelOffersItem("codex", "gpt-6-sol", "low", NOW, expires)
    required = RecordHostRuntimesModelOffersItem("codex", "gpt-6-sol", "high", NOW, expires)
    for host, offers in ((world.host_b, (required,)), (world.host_a, (other_model, other_effort))):
        world.dispatch(RecordHostRuntimes(host_id=host, installations=(install,), model_offers=offers))
    query = runtimes.ExplainRouting.from_json(
        {
            "role": "executor",
            "scope": {"kind": "run", "id": str(world.run_scope_id)},
            "host_id": str(world.host_a),
        }
    )
    refused = world.ask(query)
    assert refused.decision is None
    assert any(r["reason"] == "host_offer_unavailable" for r in refused.rejected)

    world.dispatch(
        RecordHostRuntimes(host_id=world.host_a, installations=(install,), model_offers=(required,)),
    )
    assert world.ask(query).decision["model"] == "gpt-6-sol"
    world.set_config("runtimes.host.enabled_runtimes", [])
    assert world.ask(query).decision is None
    world.set_config("runtimes.host.enabled_runtimes", ["codex"])
    assert world.ask(query).decision["model"] == "gpt-6-sol"
    world.clock.advance(timedelta(seconds=30))
    assert world.ask(query).decision is None


def test_detect_runtimes_isolates_adapter_errors_and_omits_uninstalled() -> None:
    world = _build_world()
    world.set_config("runtimes.extra_env_allow", {"codex": ["OPENAI_BASE_URL"]})
    observed_probes: dict[str, DetectProbe] = {}

    def ok_codex(probe: DetectProbe) -> RuntimeInstallation:
        observed_probes["codex"] = probe
        return RuntimeInstallation(
            host_id=probe.host_id,
            runtime_id="codex",
            version="0.42.0",
            binary_locator="/usr/local/bin/codex",
            auth_state=AuthState.OK,
            detected_at=NOW,
            details={},
        )

    def broken_claude(_probe: DetectProbe) -> RuntimeInstallation:
        raise RuntimeError("boom\x1b[31m\nbad")

    def missing_grok(_probe: DetectProbe) -> RuntimeInstallation:
        raise FileNotFoundError("grok binary missing")

    world.runtime_registry.set_adapters(
        {
            "codex": _FakeAdapter("codex", ok_codex),
            "claude_code": _FakeAdapter("claude_code", broken_claude),
            "grok": _FakeAdapter("grok", missing_grok),
        }
    )
    services = world.host_services()
    report = services.run(
        DETECT_RUNTIMES_SPEC.name,
        runtimes.DetectRuntimesRequest(),
        client=world.client(),
        cancel=CancelSource().token,
    )
    assert isinstance(report, runtimes.DetectRuntimesReport)
    assert observed_probes["codex"].env_allowlist == ("OPENAI_BASE_URL",)
    by_id = {item.runtime_id: item for item in report.runtimes}
    assert set(by_id) == {"claude_code", "codex"}
    assert by_id["codex"].auth_state == "ok"
    assert by_id["claude_code"].auth_state == "unknown"

    listed = world.ask(runtimes.ListRuntimes(host_id=world.host_a))
    listed_by_id = {item.runtime_id: item for item in listed.items}
    assert listed_by_id["claude_code"].installations[0].auth_state == "unknown"
    assert listed_by_id["claude_code"].installations[0].version is None
    assert listed_by_id["grok"].installations == ()

    with world.uow(readonly=True) as uow:
        stored = {i.runtime_id: i for i in uow.repo(HostRuntimeRepository).list_for_host(world.host_a)}
    assert stored["claude_code"].details == {"error": "boom [31m bad"}
    assert "grok" not in stored


def _run_cli(world: _RuntimesWorld, argv: list[str]) -> tuple[int, str]:
    parser = build_parser(groups=(RUNTIME_GROUP,))
    stdout = io.StringIO()
    stderr = io.StringIO()
    args = parse_command_line(parser, argv, stdout=stdout, stderr=stderr)
    client = world.client()
    services = world.host_services()
    session = CliSession(
        options=options_from(args),
        stdout=stdout,
        stderr=stderr,
        redactor=CliRedactor(),
        ids=world.ids,
        request_id=new_request_id(world.ids),
        client_=client,
        host_factory=host_context_factory(services, client),
        instance_id=UUID(str(INSTANCE)),
    )
    code = cast("int", args.run(args, session))
    return code, stdout.getvalue()


def test_cli_runtime_sync_json_serializes_nested_tariffs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runtime_cli, "_https_transport", lambda: (_PricedCatalogTransport(), {"openai": "codex"})
    )

    code, output = _run_cli(_build_world(), ["runtime", "sync", "--json"])
    assert code == 0
    envelope = json.loads(output)
    assert envelope["ok"] is True
    assert envelope["command"] == "runtimes.catalog_sync"
    staged = {row["candidate"]["model_id"]: row for row in envelope["result"]["staged"]}
    assert staged["gpt-6-sol"]["active"] is False
    quote = staged["gpt-6-sol"]["candidate"]["pricing"]
    assert quote["input_per_mtok_usd"] == "1.50"
    assert quote["output_per_mtok_usd"] == "6.00"
    assert quote["cache_read_per_mtok_usd"] == "0.10"
    assert quote["cache_write_per_mtok_usd"] is None
    assert staged["pending-model"]["candidate"]["pricing"] is None


def test_cli_runtime_group_json_and_human_modes() -> None:
    world = _build_world()
    world.set_config("runtimes.allowed", ["codex"])
    world.set_config("runtimes.preference", ["codex"])
    world.set_config("runtimes.config_isolation.required", False)
    world.runtime_registry.set_adapters(
        {
            "codex": _FakeAdapter(
                "codex",
                lambda probe: RuntimeInstallation(
                    host_id=probe.host_id,
                    runtime_id="codex",
                    version="0.42.0",
                    binary_locator="/usr/local/bin/codex",
                    auth_state=AuthState.OK,
                    detected_at=NOW,
                    details={},
                ),
            )
        }
    )

    code, detect_json = _run_cli(world, ["--json", "runtime", "detect"])
    assert code == 0
    envelope = json.loads(detect_json)
    assert envelope["ok"] is True
    assert envelope["command"] == "runtimes.host.detect_runtimes"
    assert envelope["result"]["runtimes"][0]["runtime_id"] == "codex"
    world.dispatch(
        RecordHostRuntimes(
            host_id=world.host_a,
            installations=(RecordHostRuntimesInstallationsItem("codex", "0.42.0", None, "ok", NOW, {}),),
            model_offers=tuple(
                RecordHostRuntimesModelOffersItem(
                    "codex", "gpt-6-sol", effort.value, NOW, NOW + timedelta(minutes=5)
                )
                for effort in runtimes.Effort
            ),
        )
    )

    host_ref = f"host:{world.host_a}"
    code, list_human = _run_cli(world, ["runtime", "list", "--host", host_ref])
    assert code == 0
    assert "codex" in list_human

    code, caps_json = _run_cli(world, ["--json", "runtime", "capabilities", "codex", "--version", "0.42.0"])
    assert code == 0
    assert json.loads(caps_json)["result"]["runtime_id"] == "codex"

    code, models_human = _run_cli(world, ["runtime", "models", "--runtime", "codex", "--class", "economy"])
    assert code == 0
    assert "gpt-6-luna" in models_human

    code, route_json = _run_cli(
        world,
        [
            "--json",
            "runtime",
            "route",
            "executor",
            "--scope",
            f"run:{world.run_scope_id}",
            "--host",
            host_ref,
        ],
    )
    assert code == 0
    route_env = json.loads(route_json)
    assert route_env["result"]["decision"]["runtime_id"] == "codex"
    assert route_env["result"]["decision"]["model"] == "gpt-6-sol"

    code, route_human = _run_cli(
        world,
        ["runtime", "route", "executor", "--scope", f"run:{world.run_scope_id}", "--host", host_ref],
    )
    assert code == 0
    assert "gpt-6-sol" in route_human


def test_worker_scoped_offers_do_not_merge_runtime_facts_on_a_shared_host() -> None:
    world = _build_world()
    world.set_config("runtimes.allowed", ["grok", "codex", "antigravity"])
    worker_a = world.seed_worker("grok-worker", world.host_a, ("grok",))
    worker_b = world.seed_worker("codex-agy-worker", world.host_a, ("codex", "antigravity"))
    grok = ("grok", "grok-4.7")
    codex = ("codex", "gpt-6-sol")
    agy = ("antigravity", "gemini-4-neon")

    def publish(actor: Actor, *routes: tuple[str, str]) -> None:
        observed = world.clock.now()
        world.dispatch(
            RecordHostRuntimes(
                host_id=world.host_a,
                model_offers_observed_at=observed,
                installations=tuple(
                    RecordHostRuntimesInstallationsItem(name, "1.0.0", None, "ok", observed, {})
                    for name, _ in routes
                ),
                model_offers=tuple(
                    RecordHostRuntimesModelOffersItem(
                        name, model, "high", observed, observed + timedelta(minutes=5)
                    )
                    for name, model in routes
                ),
                refresh_model_offers=True,
            ),
            actor=actor,
        )

    def allows(actor: Actor, chosen: tuple[str, str]) -> bool:
        assert actor.grant is not None
        assert actor.grant.worker_id is not None
        with world.uow(readonly=True) as uow:
            return runtimes.host_route_is_fresh(
                uow,
                world.effective_config(uow),
                world.host_a,
                runtimes.RouteKey(*chosen, runtimes.Effort.HIGH),
                as_of=world.clock.now(),
                worker_id=WorkerId(actor.grant.worker_id),
                runtime_version="1.0.0",
                binary_sha256=None,
            )

    publish(worker_a, grok)
    publish(worker_b, codex, agy)
    assert allows(worker_a, grok)
    assert not allows(worker_a, codex)
    assert not allows(worker_a, agy)
    assert allows(worker_b, codex)
    assert allows(worker_b, agy)
    assert not allows(worker_b, grok)

    world.clock.advance(timedelta(seconds=1))
    publish(worker_b, codex)
    assert not allows(worker_b, agy)
    assert allows(worker_b, codex)
    assert allows(worker_a, grok)
    world.set_config("runtimes.host.enabled_runtimes", ["grok"])
    assert not allows(worker_b, codex)
    assert allows(worker_a, grok)
