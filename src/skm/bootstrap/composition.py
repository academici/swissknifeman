"""Production PostgreSQL and explicit memory test composition (kernel-platform §5.3)."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import timedelta
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, cast, overload
from uuid import UUID

from skm.adapters.execution.context_owner import ExecutionContextOwnerGuard
from skm.adapters.memory.artifacts.blob_coordination import bind_memory_artifacts
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.postgres.artifacts.blob_coordination import bind_postgres_artifacts
from skm.adapters.postgres.config_store import PostgresConfigStore
from skm.adapters.postgres.connection import PgSettings
from skm.adapters.postgres.core.audit import PostgresAuditLog
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.core.idempotency import PostgresIdempotencyStore
from skm.adapters.postgres.core.schema_version import PostgresSchemaVersionReader
from skm.adapters.postgres.extensions.pack_config_source import PackConnectionSlot, PostgresPackConfigSource
from skm.adapters.postgres.pool import PoolHandle, create_pool
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.client import SkmClient, embedded_client_factory
from skm.application_bus.host import HostServices
from skm.application_bus.middleware import StoredScopeChain as StoredScopeChain
from skm.application_bus.platform.doctor import CHECK_IDS
from skm.application_bus.platform.migrations import AppliedMigration, PackagedMigration
from skm.application_bus.platform.migrations import SchemaVersionReader as MigrationStatusReader
from skm.application_bus.ports import (
    AuditLog,
    Authorizer,
    CurrentProcessObservation,
    DoctorRunner,
    IdempotencyStore,
    PendingRestart,
    RegisteredCheckReport,
    ScopeChainResolver,
)
from skm.application_bus.registry import BusRegistry
from skm.application_bus.subscribers import EventSinkRegistry
from skm.background.service_runner import BackgroundService
from skm.bootstrap import _knowledge_wiring as knowledge_wiring
from skm.bootstrap import _quarantine as storage_recovery
from skm.bootstrap.adapters import memory_repository_table, postgres_repository_table
from skm.bootstrap.builtins import builtin_runtime_data
from skm.bootstrap.composition_resources import TokenPepper, TrackedUow, token_authenticator
from skm.bootstrap.composition_resources import TrackedUowFactory as _TrackedUowFactory
from skm.bootstrap.composition_resources import add_storage_gateways as _add_storage_gateways
from skm.bootstrap.composition_resources import database_dsn as _database_dsn
from skm.bootstrap.composition_resources import invocation_from_json as invocation_from_json
from skm.bootstrap.composition_resources import owner_token as _owner_token
from skm.bootstrap.composition_resources import pg_blob_store as _pg_blob_store
from skm.bootstrap.composition_resources import start_process as _start_process
from skm.bootstrap.composition_resources import token_pepper as _token_pepper
from skm.bootstrap.doctor import DoctorCheckCollector, DoctorCheckRegistry, ServingProcessObserver
from skm.bootstrap.modules import MANIFESTS, resolve_section_urns, select_modules, topological_order
from skm.bootstrap.platform_module import (
    MEMORY_STORAGE_REPOSITORIES,
    PLATFORM_MANIFEST,
    local_known_version,
    memory_uow_open,
    storage_command_uows,
)
from skm.bootstrap.plugins import LoadedPlugin, PluginViews, ProcessPlugins, capability_catalog
from skm.kernel.actor import Actor
from skm.kernel.clock import Clock
from skm.kernel.entropy import EntropySource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    CapabilityUnavailable,
    NotFound,
    ValidationFailed,
)
from skm.kernel.gateways import GatewayTable
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import HostId
from skm.kernel.json_types import JsonObject
from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWorkFactory
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.permissions import PERMISSIONS
from skm.modules.access.ports import PrincipalRepository, TokenPepperSource
from skm.modules.access.public import SYSTEM_ACTOR, RbacAuthorizer
from skm.modules.artifacts.application.upload import bind_embedded_upload
from skm.modules.context.ports import ContextOwnerGuard
from skm.modules.extensions.ports import BuiltinPacks, RuntimeCatalogSeeder
from skm.modules.extensions.public import SyncBuiltinPacks
from skm.modules.integrations.settings import validators_for
from skm.modules.runtimes.ports import CapabilityCatalog
from skm.modules.runtimes.public import seed_builtin_model_catalog
from skm.platform.config.bootstrap import BootstrapConfig, WebAuthConfig
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.registry import SectionValidatorFn, SettingsRegistry
from skm.platform.config.sources.cli_overrides import invocation_layers
from skm.platform.config.store import ConfigStore, EmptyPackConfigSource, PackConfigSource, ScopeTree
from skm.platform.config.validators import VALIDATORS as PLATFORM_VALIDATORS
from skm.platform.config.validators import VIEWS as PLATFORM_VIEWS
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.system_clock import SystemClock
from skm.platform.system_entropy import SystemEntropy
from skm.platform.system_ids import Uuid7Generator
from skm.platform.tokens.heuristic import HeuristicTokenEstimator

if TYPE_CHECKING:
    from skm.bootstrap._http_mode import HttpHookApp

__all__ = [
    "KNOWN_SCHEMA_VERSION",
    "OWNER_TOKEN_FILE",
    "App",
    "CompositionOverrides",
    "build_app",
    "build_cli_app",
    "invocation_from_json",
    "knowledge_wiring",
    "open_cli_app",
    "resolve_cli_actor",
]
type RepoFactory = Callable[[MemoryBackendState], object]
type PgFactories = Mapping[type, Callable[[Any], object]]
type AppInputs = tuple[Mapping[str, str], JsonObject, CompositionOverrides]
KNOWN_SCHEMA_VERSION: Final = local_known_version()
OWNER_TOKEN_FILE: Final = Path("secrets") / "owner.token"
_IDEMPOTENCY_TTL = timedelta(hours=24)
_HOST_SURFACES: Final = frozenset({Surface.CLI, Surface.WORKER, Surface.HOOK})
_TrackedUow = TrackedUow  # Preserve the existing composition guard probe.


@dataclass(frozen=True, slots=True)
class CompositionOverrides:
    authorizer: Authorizer
    scopes: ScopeChainResolver
    clock: Clock | None = None
    ids: IdGenerator | None = None
    entropy: EntropySource | None = None
    packs: PackConfigSource | None = None
    repositories: Mapping[type, RepoFactory] = field(default_factory=dict[type, RepoFactory])
    disabled_modules: frozenset[str] = frozenset()
    gateways: GatewayTable | None = None
    host: HostServices | None = None
    instance_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class App:
    bus: Bus
    schemas: SchemaRegistry
    settings: SettingsRegistry
    config: ConfigLoader
    uow_factory: UnitOfWorkFactory
    gateways: GatewayTable
    host: HostServices | None
    services: tuple[BackgroundService, ...]
    instance_id: UUID
    host_id: HostId | None
    client_factory: Callable[[Actor, Surface], SkmClient] | None = field(default=None, repr=False)
    doctor: DoctorCheckCollector | None = field(default=None, repr=False)
    closers: tuple[Callable[[], None], ...] = field(default=(), repr=False)
    authenticator: Callable[[str], Actor] | None = field(default=None, repr=False)
    plugins: tuple[LoadedPlugin, ...] = field(default=(), repr=False)  # step 9a: every discovered entry point
    closed: list[bool] = field(default_factory=lambda: [False], repr=False, compare=False)
    web_auth: WebAuthConfig = field(default_factory=WebAuthConfig)
    clock: Clock = field(default_factory=SystemClock, repr=False)

    def client(self, *, actor: Actor, surface: Surface) -> SkmClient:
        if self.client_factory is None:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "this composition has no client",
                details={"owner": "P04.02.c"},
            )
        return self.client_factory(actor, surface)

    def authenticate(self, secret_text: str) -> Actor:
        if self.authenticator is None:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "this composition does not authenticate tokens",
                details={"reason": "no_authenticator"},
            )
        return self.authenticator(secret_text)

    def close(self) -> None:
        if self.closed[0]:
            return
        self.closed[0] = True
        first: BaseException | None = None
        for closer in (*reversed(self.closers), *((self.host.close,) if self.host is not None else ())):
            try:
                closer()
            except Exception as exc:  # noqa: BLE001 - keep closing the rest
                first = first or exc
        if first is not None:
            raise first


def _unavailable(what: str, owner: str) -> CapabilityUnavailable:
    return CapabilityUnavailable(
        ErrorCode.CAPABILITY_UNAVAILABLE,
        f"{what} is not available in this build ({owner})",
        details={"owner": owner},
    )


class _DoctorRunner:
    def __init__(self, collector: DoctorCheckCollector, loader: ConfigLoader) -> None:
        self._collector = collector
        self._observer = ServingProcessObserver(loader)

    def check_ids(self) -> frozenset[str]:
        return self._collector.ids()

    def reports(self, only: frozenset[str] | None) -> tuple[RegisteredCheckReport, ...]:
        return self._collector.reports(only)

    def observe(self, store: ConfigStore, scopes: ScopeTree) -> CurrentProcessObservation:
        found = self._observer.observe(store, scopes)
        return CurrentProcessObservation(
            state=found.state,
            instance_scope_id=found.instance_scope_id,
            host_target=found.host_target,
            process_generation=found.process_generation,
            pending=tuple(
                PendingRestart(item.key, item.chain, item.target, item.severity) for item in found.pending
            ),
        )


def _doctor_registry(manifests: tuple[ModuleManifest, ...]) -> DoctorCheckRegistry:
    registry = DoctorCheckRegistry([spec for manifest in manifests for spec in manifest.doctor_checks])
    reserved = registry.ids() & CHECK_IDS
    if reserved:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "doctor check ids are reserved by platform.doctor",
            details={"reason": "reserved_check_id", "check_ids": [*sorted(reserved)]},
        )
    return registry


def _control_plane_gateways(
    config: ConfigLoader,
    doctor: DoctorCheckCollector,
    supplied: GatewayTable | None,
    pepper: bytes | None = None,
    catalog: CapabilityCatalog | None = None,
    defaults: Mapping[type[object], object] | None = None,
    clock: Clock | None = None,
) -> GatewayTable:
    from skm.bootstrap.hook_subscriptions import webhook_sinks

    src = Path(__file__).resolve().parents[2]
    entries: dict[type[object], object] = {
        EventSinkRegistry: webhook_sinks(clock),
        DoctorRunner: _DoctorRunner(doctor, config),
        ContextOwnerGuard: ExecutionContextOwnerGuard(config),
        TokenEstimator: HeuristicTokenEstimator(),
        BuiltinPacks: PackagedBuiltinPacks(src.parent / "resources/packs" if src.name == "src" else None),
        RuntimeCatalogSeeder: seed_builtin_model_catalog,
        **(defaults or {}),
    }
    if pepper is not None:
        entries[TokenPepperSource] = TokenPepper(pepper)
    if catalog is not None:  # step 12: built-in runtime data and the step 2a data of allowed plugins
        entries[CapabilityCatalog] = catalog
    if supplied is not None:
        entries.update(supplied.entries)
    _add_storage_gateways(entries)
    if entries.get(ContextOwnerGuard) is None:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "ContextOwnerGuard is required at bootstrap")
    return GatewayTable(entries, "control_plane_gateway")


@cache
def _settings_module(module_id: str) -> Any:
    return importlib.import_module(f"skm.modules.{module_id}.settings")


@cache
def _default_registries() -> tuple[SchemaRegistry, SettingsRegistry]:
    schemas = SchemaRegistry.load_default()
    return schemas, _settings_registry(schemas)


def _settings_registry(schemas: SchemaRegistry, extra: PluginViews | None = None) -> SettingsRegistry:
    views = {**PLATFORM_VIEWS, **{view.SECTION: view for view in (extra or {}).values()}}
    validators: dict[str, SectionValidatorFn] = dict(PLATFORM_VALIDATORS)
    for manifest in MANIFESTS:
        if manifest.settings_sections:
            module = _settings_module(manifest.id)
            views.update(module.VIEWS)
            validators.update(module.VALIDATORS)
    hookable = {urn for urn in schemas.urns() if schemas.get(urn).get("x-skm-hookable") is True}
    validators.update(validators_for(hookable_types=hookable, sink_ids=EventSinkRegistry(()).ids()))
    known = frozenset(PERMISSIONS).union(*(manifest.permissions for manifest in MANIFESTS))
    return SettingsRegistry.build(
        schemas,
        (*resolve_section_urns(MANIFESTS, schemas), *(extra or {})),
        views=views,
        validators=validators,
        known_permissions=known | PLATFORM_MANIFEST.permissions,
    )


def _base_setup(environ: Mapping[str, str], invocation: JsonObject, ov: CompositionOverrides) -> Any:
    schemas, settings = _default_registries()
    topological_order(MANIFESTS)
    sel = select_modules(MANIFESTS, ov.disabled_modules)
    packs = ov.packs if ov.packs is not None else EmptyPackConfigSource()
    layers = invocation_layers(settings, environ, invocation_from_json(invocation))
    cfg = ConfigLoader(settings, packs, layers)
    clock = ov.clock if ov.clock is not None else SystemClock()
    entropy = ov.entropy if ov.entropy is not None else SystemEntropy()
    ids = ov.ids if ov.ids is not None else Uuid7Generator(clock, entropy)
    has_art = any(m.id == "artifacts" for m in sel.manifests)
    return (schemas, settings, sel, has_art), (packs, cfg, clock, entropy, ids)


def _bus_registry(selection: Any, schemas: SchemaRegistry) -> BusRegistry:
    disabled = tuple(m for m in MANIFESTS if m.id in selection.disabled)
    return BusRegistry.build(
        (*selection.manifests, *disabled, PLATFORM_MANIFEST),
        schemas=schemas,
        permission_catalog=frozenset(PERMISSIONS).union(PLATFORM_MANIFEST.permissions),
        disabled_modules=selection.disabled,
    )


def _assemble_app(
    left: tuple[Any, ...],
    right: tuple[Any, ...],
    extra: tuple[Any, ...] = ((), (), None),
    *,
    bus_config: ConfigLoader | None = None,
    recovery: storage_recovery.RecoveryGuard | None = None,
    web_auth: WebAuthConfig | None = None,
) -> App:
    registry, schemas, settings, cfg, has_art, clock, ids, entropy = left
    uow_f, gw, doc, ov, surf, be, inst_id, host_id = right
    gw = knowledge_wiring.bind_memory_retriever(gw, registry.disabled_modules(), cfg, clock)
    closers, plugins, auth = extra
    bus, gw = storage_recovery.recovery_wiring(
        recovery,
        gw,
        registry=registry,
        schemas=schemas,
        uow_factory=storage_command_uows(uow_f, _IDEMPOTENCY_TTL),
        authorizer=ov.authorizer,
        scopes=ov.scopes,
        config=cfg if bus_config is None else bus_config,
        clock=clock,
        ids=ids,
        entropy=entropy,
        retry=RetryPolicy(),
        idempotency_ttl=_IDEMPOTENCY_TTL,
    )
    cb = (
        bind_embedded_upload(uow_f, ov.authorizer, ov.scopes, cfg, gw, clock, ids, bus.dispatch, bus.ask)
        if has_art
        else (None, None)
    )
    make_client = embedded_client_factory(
        bus, uow_f, surface=surf, ids=ids, clock=clock, backend=be, callbacks=cb
    )
    host = ov.host if surf in _HOST_SURFACES else None
    h_id = HostId(host_id) if isinstance(host_id, UUID) else None
    b1, b2 = (bus, schemas, settings, cfg, uow_f), (gw, host, (), inst_id, h_id)
    return App(
        *b1,
        *b2,
        make_client,
        doc,
        closers,
        auth,
        plugins,
        web_auth=web_auth if web_auth is not None else WebAuthConfig(),
        clock=clock,
    )


def _build_memory_app(bs: BootstrapConfig, surf: Surface, args: AppInputs) -> App:
    environ, invocation, ov = args
    (schemas, settings, sel, has_art), (packs, cfg, clock, entropy, ids) = _base_setup(
        environ, invocation, ov
    )
    reg = _bus_registry(sel, schemas)
    factories: dict[type, RepoFactory] = {
        **memory_repository_table(tuple(m.id for m in sel.manifests)),
        **MEMORY_STORAGE_REPOSITORIES,
        ConfigStore: MemoryConfigStore,
        PackConfigSource: lambda _state: packs,
        Authorizer: lambda _state: ov.authorizer,
        **ov.repositories,
    }
    backend = InMemoryBackend(
        factories=factories, schemas=schemas, subscriptions=reg.subscription_index(), ids=ids, clock=clock
    )
    defaults = bind_memory_artifacts(backend.committed, ov.gateways, clock) if has_art else {}
    uow_f = backend.uow_factory()
    doc = DoctorCheckCollector(
        _doctor_registry((*sel.manifests, PLATFORM_MANIFEST)), in_unit_of_work=memory_uow_open(backend)
    )
    gw = _control_plane_gateways(cfg, doc, ov.gateways, defaults=defaults, clock=clock)
    inst_id = ov.instance_id or bs.instance_id or UUID(int=0)
    left = (reg, schemas, settings, cfg, has_art, clock, ids, entropy)
    return _assemble_app(
        left, (uow_f, gw, doc, ov, surf, "memory", inst_id, bs.host_id), web_auth=bs.web_auth
    )


def _sync_startup_packs(app: App, surface: Surface, clock: Clock) -> None:
    meta = RequestMeta("startup-pack-sync", surface, None, clock.now())
    with app.uow_factory(meta, readonly=True) as uow:
        try:
            uow.repo(PrincipalRepository).get(SYSTEM_ACTOR.principal_id)
        except NotFound:
            # ``skm init`` opens the composition before it creates the system principal.
            return
    app.client(actor=SYSTEM_ACTOR, surface=surface).dispatch(SyncBuiltinPacks())


def _build_postgres_app(
    bs: BootstrapConfig,
    surf: Surface,
    args: AppInputs,
    *,
    production: bool = False,
    load_project_plugins: bool = True,
) -> App:
    from skm.adapters.postgres.core.storage_inspector import PostgresStorageInspector
    from skm.application_bus.platform.storage import StorageInspector

    environ, invocation, ov = args
    if ov.repositories:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "memory repository factories cannot back the PostgreSQL composition",
            details={"reason": "memory_repositories_override"},
        )
    dsn, pepper = _database_dsn(bs, environ), (_token_pepper(bs, environ) if production else None)
    recovery = storage_recovery.guard_for(bs, dsn, surf)
    environ, invocation = (environ, invocation) if recovery is None else (dict[str, str](), {})
    (schemas, settings, sel, has_art), (packs, cfg, clock, entropy, ids) = _base_setup(
        environ, invocation, ov
    )
    tracker = PackConnectionSlot()
    use_pg_packs = ov.packs is None and any(m.id == "extensions" for m in sel.manifests)

    def _make_loader(final: SettingsRegistry) -> ConfigLoader:
        layers = invocation_layers(final, environ, invocation_from_json(invocation))
        src = PostgresPackConfigSource(tracker.connection, final, layers) if use_pg_packs else packs
        return ConfigLoader(final, src, layers)

    if use_pg_packs:
        cfg = _make_loader(settings)
    plugins = ProcessPlugins(
        schemas=schemas,
        settings=settings,
        host_surface=surf in _HOST_SURFACES,
        build_settings=_settings_registry,
        loader=_make_loader,
        use_project_settings=load_project_plugins and not (production and surf is Surface.WORKER),
    )
    api_layers = (
        invocation_layers(settings, environ, invocation_from_json(invocation)) if surf is Surface.API else ()
    )
    bs, cfg, restricted = _start_process(  # 6a, 9a
        cfg,
        bs,
        dsn,
        surface=surf,
        plugins=plugins,
        slot=tracker,
        api_layers=api_layers,
    )
    schemas, settings = plugins.schemas, plugins.settings
    proc = cfg.process
    disabled = tuple(m.id for m in MANIFESTS if proc and proc.work.get(f"modules.{m.id}.enabled") is False)
    if disabled:
        sel = select_modules(MANIFESTS, sel.disabled.union(disabled))
    reg = _bus_registry(sel, schemas)
    uow_max = cast("int", bs.database_pool_max_size)
    app_name, timeout = bs.database_application_name, bs.database_pool_timeout_seconds
    hook_ms = (
        max(1, int(environ.get("SKM__INTEGRATIONS__HOOK__TIMEOUT_MS", "2000")))
        if surf is Surface.HOOK
        else None
    )
    pool = create_pool(
        PgSettings(
            dsn,
            app_name,
            bs.database_pool_min_size,
            uow_max,
            timeout,
            statement_timeout_ms=hook_ms if hook_ms is not None else 30000,
            lock_timeout_ms=hook_ms if hook_ms is not None else 10000,
        )
    )
    tracker.bind_pool(pool)
    coord_pool: PoolHandle | None = None
    try:
        uow_ref = cast("list[UnitOfWorkFactory]", [])
        store_fn = lambda: _pg_blob_store(bs, (uow_ref, cfg, tracker, surf, clock, ids))  # noqa: E731
        defaults, extra_repos, coord_pool = (
            bind_postgres_artifacts(dsn, app_name, uow_max, timeout, ov.gateways, store_fn)
            if has_art and not restricted
            else ({}, {}, None)
        )
        factories: PgFactories = {
            **postgres_repository_table(tuple(m.id for m in sel.manifests)),
            StorageInspector: PostgresStorageInspector,
            **storage_recovery.recovery_repositories(recovery, extra_repos),
            IdempotencyStore: lambda conn: PostgresIdempotencyStore(conn, ids),
            AuditLog: PostgresAuditLog,
            ConfigStore: PostgresConfigStore,
            PackConfigSource: (
                lambda conn: PostgresPackConfigSource(conn, settings) if use_pg_packs else packs
            ),
            Authorizer: lambda _conn: ov.authorizer,
            MigrationStatusReader: lambda conn: PostgresSchemaVersionReader(
                conn, packaged_row=PackagedMigration, applied_row=AppliedMigration
            ),
        }
        writer = PostgresEventWriter(schemas=schemas, subscriptions=reg.subscription_index(), ids=ids)
        uow_f = _TrackedUowFactory(pool, factories, writer, clock, tracker=tracker)
        uow_ref.append(uow_f)
        if not restricted:
            plugins.bind_config(uow_f, cfg, surface=surf, ids=ids, clock=clock)
        doc = DoctorCheckCollector(
            _doctor_registry((*sel.manifests, PLATFORM_MANIFEST)), in_unit_of_work=tracker.holds
        )
        catalog = capability_catalog(plugins.plugins, builtin_runtime_data())
        gw = _control_plane_gateways(cfg, doc, ov.gateways, pepper, catalog, defaults, clock)
        closers = (pool.close, coord_pool.close) if coord_pool is not None else (pool.close,)
        auth = None if pepper is None else token_authenticator(uow_f, pepper, surf, ids, clock)
        left = (reg, schemas, settings, cfg, has_art and not restricted, clock, ids, entropy)
        right = (uow_f, gw, doc, ov, surf, "postgres", cast("UUID", bs.instance_id), bs.host_id)
        # Restricted status queries resolve stored scopes in a readonly UoW without plugins/packs.
        status_config = ConfigLoader(settings, EmptyPackConfigSource(), api_layers) if restricted else None
        app = _assemble_app(
            left,
            right,
            (closers, plugins.plugins, auth),
            bus_config=status_config,
            recovery=recovery,
            web_auth=bs.web_auth,
        )
        if (
            surf is not Surface.HOOK
            and not restricted
            and recovery is None
            and use_pg_packs
            and proc is not None
            and proc.host.get("extensions.sync_on_start") is True
            and any(module.id == "extensions" for module in sel.manifests)
        ):
            _sync_startup_packs(app, surf, clock)
    except BaseException:
        if coord_pool is not None:
            coord_pool.close()
        pool.close()
        raise
    else:
        return app


@overload
def build_app(
    bootstrap: BootstrapConfig,
    *,
    surface: Literal[Surface.CLI, Surface.WORKER, Surface.API, Surface.BACKGROUND, Surface.MCP, Surface.TEST],
    environ: Mapping[str, str],
    invocation: JsonObject,
    backend: Literal["postgres", "memory"] | None = None,
    overrides: CompositionOverrides | None = None,
    load_project_plugins: bool = True,
) -> App: ...
@overload
def build_app(
    bootstrap: BootstrapConfig,
    *,
    surface: Surface,
    environ: Mapping[str, str],
    invocation: JsonObject,
    backend: Literal["postgres", "memory"] | None = None,
    overrides: CompositionOverrides | None = None,
    load_project_plugins: bool = True,
) -> App | HttpHookApp: ...
def build_app(
    bootstrap: BootstrapConfig,
    *,
    surface: Surface,
    environ: Mapping[str, str],
    invocation: JsonObject,
    backend: Literal["postgres", "memory"] | None = None,
    overrides: CompositionOverrides | None = None,
    load_project_plugins: bool = True,
) -> App | HttpHookApp:
    bootstrap = storage_recovery.pinned_profile(bootstrap)
    if bootstrap.access_mode == "http":
        if surface is not Surface.HOOK:
            raise _unavailable("the HTTP composition on this surface", "P11.04.a")
        from skm.bootstrap._http_mode import build_http_hook_app
        from skm.bootstrap.hook import hook_bootstrap, hook_credential

        pinned = hook_bootstrap(environ, bootstrap.source)
        return build_http_hook_app(pinned, environ, hook_credential(pinned))
    if overrides is None:
        if backend == "memory":
            raise _unavailable("the memory backend outside the test composition", "tests only")
        clock = SystemClock()
        prod = CompositionOverrides(authorizer=RbacAuthorizer(clock), scopes=StoredScopeChain(), clock=clock)
        return _build_postgres_app(
            bootstrap,
            surface,
            (environ, invocation, prod),
            production=True,
            load_project_plugins=load_project_plugins,
        )
    if backend == "postgres":
        return _build_postgres_app(
            bootstrap, surface, (environ, invocation, overrides), load_project_plugins=load_project_plugins
        )
    return _build_memory_app(bootstrap, surface, (environ, invocation, overrides))


def build_cli_app(
    bootstrap: BootstrapConfig,
    *,
    environ: Mapping[str, str],
    invocation: JsonObject,
    load_project_plugins: bool = True,
) -> App:
    return build_app(
        bootstrap,
        surface=Surface.CLI,
        environ=environ,
        invocation=invocation,
        load_project_plugins=load_project_plugins,
    )


def resolve_cli_actor(
    app: App,
    bootstrap: BootstrapConfig,
    *,
    as_token: str | None,
    on_secret: Callable[[str], None] = lambda _value: None,
) -> Actor:
    secret = as_token if as_token is not None else _owner_token(bootstrap.state_dir, on_secret)
    return app.authenticate(secret)


def open_cli_app(
    bootstrap: BootstrapConfig,
    *,
    environ: Mapping[str, str],
    invocation: JsonObject,
    as_token: str | None,
    on_secret: Callable[[str], None] = lambda _value: None,
    load_project_plugins: bool = True,
) -> tuple[App, Actor]:
    app = build_cli_app(
        bootstrap, environ=environ, invocation=invocation, load_project_plugins=load_project_plugins
    )
    try:
        from skm.bootstrap.hook_subscriptions import bind_cli_subscriptions
        from skm.bootstrap.host_services import bind_cli_research
        from skm.bootstrap.projection_wiring import bind_cli_projections

        actor = resolve_cli_actor(app, bootstrap, as_token=as_token, on_secret=on_secret)
        app, actor = knowledge_wiring.bind_cli_knowledge(
            bind_cli_subscriptions(app, bootstrap, environ), actor
        )
        client = app.client(actor=actor, surface=Surface.CLI)
        host = bind_cli_research(app.host, client, app.plugins)
        return replace(
            app,
            host=bind_cli_projections(
                host, bootstrap.state_dir, client, environ=environ, instance_id=app.instance_id
            ),
        ), actor
    except BaseException:
        app.close()
        raise
