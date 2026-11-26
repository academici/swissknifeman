"""Embedded and HTTP worker composition with host-local gateways and durable credentials."""

from __future__ import annotations

import os
import ssl
from collections.abc import Callable, Generator, Mapping
from contextlib import ExitStack, closing, contextmanager, nullcontext
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, cast, override
from uuid import UUID

from skm.adapters.checkout_fs.docs import LocalDocsCheckoutFs
from skm.adapters.exports.obsidian.vault_fs import LocalVaultFs
from skm.adapters.http_client.client import HttpSkmClient
from skm.adapters.http_client.live import LivePublisher
from skm.adapters.http_client.spool import BoundedLocalSpool
from skm.adapters.http_client.worker_config import RemoteWorkerConfig, worker_credential_workspace
from skm.application_bus.client import SkmClient, new_request_id
from skm.application_bus.host import HostContext, HostServices
from skm.background.vault_push import VaultConfig, VaultHostClient, VaultPush, export_settings
from skm.bootstrap.checkout_operations import worker_checkout_root
from skm.bootstrap.host_services import (
    build_context_inputs,
    build_host_services,
    build_host_storage,
    build_worker_services,
    read_recorded_host_id,
    resolve_host_id,
    with_worker_tick,
)
from skm.bootstrap.runtimes import WorkerRuntimeSettings, runtime_environment
from skm.bootstrap.worker_credentials import resolve_worker_credential
from skm.bootstrap.worker_rotation import RotatingClient, TokenRotation, WorkerCredential
from skm.bootstrap.worker_runtimes import (
    HostPlugins,
    WorkerHostConfig,
    WorkerRuntimes,
    local_account_available,
    machine_runtime_settings,
    runtime_auth,
    with_worker_model_policy,
    worker_redactor,
)
from skm.kernel.actor import Actor
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.public import ListTokens, ListTokensView, WhoAmI, WhoAmIView
from skm.modules.execution.host.context import WorkerServices
from skm.modules.execution.host.stage_client import claim_json
from skm.modules.execution.host.stages.registry import HostStage, StageRegistry
from skm.modules.exports.host.push_vault_docs import DocsCheckoutFs
from skm.modules.exports.module import HOST_OPERATIONS as VAULT_OPERATIONS
from skm.modules.exports.ports import VaultFs
from skm.modules.exports.public import VaultRequestMeta
from skm.modules.runtimes.public import RuntimeRegistry, SecretStr, WorkerModelOfferPolicy
from skm.modules.settings.public import GetHostConfigResultPlugins, worker_identifiers
from skm.platform.config.bootstrap import BootstrapConfig, validate_worker_host
from skm.platform.config.secrets import SecretRef, SecretValue
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.logging.logger import get_logger
from skm.platform.logging.redaction import Redactor
from skm.platform.system_clock import SystemClock, SystemMonotonic
from skm.platform.system_ids import Uuid7Generator
from skm.plugin_api.manifest import ComponentKind

if TYPE_CHECKING:
    from skm.bootstrap.composition import App
    from skm.modules.execution.domain.lease import WorkerClaim
    from skm.modules.execution.host.context import StageToolBinding
    from skm.modules.workspace.public import MountView
    from skm.platform.config import EffectiveConfig
    from skm.platform.fs.storage_budget import StorageBudget
    from skm.platform.machine import MachineStore

__all__ = [
    "bind_vault_host",
    "build_http_worker",
    "build_worker_host",
    "embedded_vault_client",
    "http_cli_vault_host",
    "run_vault_host",
    "worker_host_from_context",
]


def embedded_vault_client(app: App, actor: Actor, surface: Surface, host_id: HostId) -> SkmClient:
    client, clock = app.client(actor=actor, surface=surface), SystemClock()
    ids = Uuid7Generator(clock)

    def meta(key: str | None = None) -> VaultRequestMeta:
        return VaultRequestMeta(new_request_id(ids), surface, key, clock.now(), host_id=host_id)

    return cast(
        "SkmClient",
        VaultHostClient(
            client,
            lambda query: app.bus.ask(query, actor=actor, meta=meta()),
            lambda command, key: app.bus.dispatch(command, actor=actor, meta=meta(key)),
        ),
    )


def bind_vault_host(host: HostServices, bootstrap: BootstrapConfig, client: SkmClient) -> HostServices:
    state = bootstrap.state_dir
    gateways = {**host.gateways.entries, VaultFs: LocalVaultFs(Path("/"), state)}
    if host.surface is Surface.CLI:
        roots = (state, bootstrap.blobs_root, bootstrap.backups_root, bootstrap.materialized_root)
        gateways[DocsCheckoutFs] = LocalDocsCheckoutFs(roots)
    operations = {op.name: op for op in VAULT_OPERATIONS if host.surface in op.surfaces}
    config = host.host_config
    host = replace(
        host,
        gateways=GatewayTable(gateways, "host_gateway"),
        operations={**host.operations, **operations},
        host_config=lambda: VaultConfig(config(), client.ask),
    )
    if host.surface is not Surface.WORKER:
        return host
    interval = cast("VaultConfig", host.host_config()).get("exports.vault.push_interval_seconds")
    if type(interval) is not int or interval <= 0:
        return host
    service = VaultPush(
        client.ask,
        lambda workspace, cancel: cast(
            "JsonObject",
            host.run(
                "exports.host.push_vault_notes",
                {"workspace_id": str(workspace)},
                client=client,
                cancel=cancel,
            ),
        ),
        interval=interval,
        log=get_logger("worker.host").warning,
    )
    return with_worker_tick(
        replace(host, owned_resources=(*host.owned_resources, service.close)), service.poll
    )


def http_cli_vault_host(bootstrap: BootstrapConfig, client: HttpSkmClient) -> HostServices | None:
    host_id = (
        HostId(bootstrap.host_id)
        if isinstance(bootstrap.host_id, UUID)
        else read_recorded_host_id(bootstrap.state_dir)
    )
    if host_id is None:
        return None
    client.bind_host(host_id)
    host = HostServices(
        host_id,
        Surface.CLI,
        GatewayTable({}, "host_gateway"),
        lambda: export_settings(client.ask, "host", host_id),
        {},
    )
    return bind_vault_host(host, bootstrap, client)


def run_vault_host(context: HostContext, name: str, request: JsonObject) -> JsonObject:
    host = worker_host_from_context(context, surface=Surface.CLI)
    return cast(
        "JsonObject", host.run(name, request, client=context.client, cancel=context.cancel, log=context.log)
    )


def worker_host_from_context(context: HostContext, *, surface: Surface = Surface.WORKER) -> HostServices:
    if not isinstance(context.gateways, GatewayTable):
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Worker requires composed host gateways")
    operations = {op.name: op for op in VAULT_OPERATIONS if surface in op.surfaces}
    return HostServices(context.host_id, surface, context.gateways, lambda: context.config, operations)


def _is_host_stage(value: object) -> bool:
    return getattr(value, "side", None) == "host"


def build_worker_host(  # noqa: PLR0915 - compose local runtime, rotation, recovery and scope once
    app: App,
    bootstrap: BootstrapConfig,
    actor: Actor,
    *,
    environ: Mapping[str, str],
    credential_ref: str | None = None,
    credential_path: Path | None = None,
    on_secret: Callable[[str], None] = lambda _value: None,
    machine_store: MachineStore | None = None,
) -> HostServices:
    from skm.bootstrap._quarantine_rebind import embedded_worker_stages
    from skm.platform.config.store import ConfigStore, ScopeTree

    registered = validate_worker_host(bootstrap)
    host_id = cast("HostId", registered.host_id)
    client = embedded_vault_client(app, actor, Surface.WORKER, host_id)

    workspace_id = (
        worker_credential_workspace(cast("WhoAmIView", client.ask(WhoAmI())))
        if actor.grant and actor.grant.kind == "worker"
        else None
    )

    def config(*, host: bool = True) -> EffectiveConfig:
        clock = SystemClock()
        meta = RequestMeta(new_request_id(Uuid7Generator(clock)), Surface.WORKER, None, clock.now())
        with app.uow_factory(meta, readonly=True) as uow:
            store, scopes = uow.repo(ConfigStore), uow.repo(ScopeTree)
            if host:
                return app.config.effective_host(store, scopes, ScopeRef(ScopeKind.HOST, ScopeId(host_id)))
            scope = None if workspace_id is None else ScopeRef(ScopeKind.WORKSPACE, ScopeId(workspace_id))
            return app.config.effective(store, scopes, scope)

    recovery = getattr(app.bus, "guard", None) is not None
    redactor, remember = worker_redactor(bootstrap, environ, on_secret)
    machine_settings = machine_runtime_settings(bootstrap, environ, machine_store, remember)
    machine = WorkerRuntimeSettings() if recovery else machine_settings()
    storage = build_host_storage(bootstrap.state_dir)
    if recovery:
        runtimes = None
        stages, gateways = embedded_worker_stages(app, bootstrap, host_id, recovery=True)
    else:

        def project_plugins() -> GetHostConfigResultPlugins:
            work = config(host=False)
            return GetHostConfigResultPlugins(
                worker_identifiers(work.get("plugins.allowed"), key="plugins.allowed"),
                worker_identifiers(work.get("plugins.required"), key="plugins.required"),
            )

        plugins = HostPlugins(lambda: machine, project_plugins)
        runtimes = WorkerRuntimes(
            plugins,
            lambda: machine,
            lambda: config(host=False).get("runtimes.allowed"),
            bootstrap.state_dir,
            storage,
            runtime_environment(environ, redactor),
            lambda refs: runtime_auth(refs, bootstrap, environ, redactor, on_secret),
            lambda local, installation: local_account_available(local, installation, environ),
        )
        gateways = _local_gateways(bootstrap, host_id, WorkerHostConfig(config(), machine), runtimes, storage)
        stages = _worker_stages(
            bootstrap,
            host_id,
            client,
            plugins,
            gateways,
            checkout_root=worker_checkout_root(bootstrap, host_id, machine_store, environ, remember),
        )
    services = build_worker_services(
        bootstrap.state_dir,
        stages=stages,
        context_inputs=None if recovery else build_context_inputs(),
        resolve=lambda _ownership: None,
        storage=storage,
    )

    def refresh_machine() -> bool:
        nonlocal machine
        if not recovery:
            machine = machine_settings()
        return True

    if credential_ref is not None and actor.grant is not None and actor.grant.kind == "worker":
        grant = actor.grant
        after = None
        credential = None
        while True:
            page = cast("ListTokensView", client.ask(ListTokens(after=after)))
            credential = next((item for item in page.items if item.token_id == grant.token_id), None)
            if credential is not None or page.next is None:
                break
            after = page.next
        if credential is None or credential.expires_at is None:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "worker credential must have an expiry")
        secret = resolve_worker_credential(credential_ref, environ=environ, on_reveal=remember)
        reference = SecretRef.parse(credential_ref)
        target = Path(reference.path).expanduser() if reference.scheme == "file" else credential_path
        if target is None:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "worker rotation needs a credential file")

        def save(value: WorkerCredential) -> None:
            revealed = value.secret.reveal()
            remember(revealed)
            atomic_write(target, (revealed + "\n").encode(), mode=0o600, private=True)

        def make_client(value: SecretStr) -> SkmClient:
            revealed = value.reveal()
            remember(revealed)
            return embedded_vault_client(app, app.authenticate(revealed), Surface.WORKER, host_id)

        gateways[TokenRotation] = TokenRotation(
            WorkerCredential(grant.token_id, credential.expires_at, SecretStr(secret)),
            RotatingClient(client),
            clock=SystemClock(),
            monotonic=SystemMonotonic(),
            config=lambda key: config(host=False).get(key),
            save=save,
            make_client=make_client,
        )

    def stage_client(_binding: StageToolBinding, secret: SecretStr) -> nullcontext[SkmClient]:
        return nullcontext(app.client(actor=app.authenticate(secret.reveal()), surface=Surface.MCP))

    host = build_host_services(
        {"host": {"id": str(host_id)}},
        client=client,
        plugins=(),
        environ=environ,
        surface=Surface.WORKER,
        host_config=lambda: WorkerHostConfig(config(), machine),
        gateways=gateways,
        worker_services=replace(
            with_worker_model_policy(services, machine_settings, runtimes),
            refresh_config=refresh_machine,
            workspace_id=workspace_id,
            stage_tool_client=stage_client,
            redact_runtime_probe=redactor.text,
        ),
    )
    if recovery or "exports" in app.bus._registry.disabled_modules():  # pyright: ignore[reportPrivateUsage]
        return host
    worker_client = (
        rotation.client if isinstance(rotation := gateways.get(TokenRotation), TokenRotation) else client
    )
    return bind_vault_host(host, bootstrap, worker_client)


class _HttpStages(StageRegistry):
    def __init__(self, plugins: HostPlugins, builtin: tuple[HostStage, ...]) -> None:
        super().__init__(builtin)
        self._builtin = builtin
        self._plugins = plugins

    @override
    def for_stage(self, stage_type: str, *, side: str = "host") -> HostStage:
        extensions = filter(_is_host_stage, self._plugins.components(ComponentKind.STAGE_HANDLER))
        stages = (*self._builtin, *cast("tuple[HostStage, ...]", tuple(extensions)))
        return StageRegistry(stages).for_stage(stage_type, side=side)


def _worker_stages(
    bootstrap: BootstrapConfig,
    host_id: HostId,
    client: SkmClient,
    plugins: HostPlugins,
    gateways: Mapping[type[object], object],
    *,
    checkout_root: Callable[[MountView], Path] | None = None,
) -> StageRegistry:
    from skm.bootstrap.worker_stages import builtin_worker_stages
    from skm.modules.execution.ports import ExecutionEnvironmentManager
    from skm.modules.workspace.public import ListProjectRepositories, ListProjectRepositoriesView

    manager = cast("ExecutionEnvironmentManager", gateways[ExecutionEnvironmentManager])

    def repositories_for_project(project: UUID) -> ListProjectRepositoriesView:
        return cast("ListProjectRepositoriesView", client.ask(ListProjectRepositories(project, host_id)))

    return _HttpStages(
        plugins,
        builtin_worker_stages(bootstrap, manager, repositories_for_project, checkout_root=checkout_root),
    )


def _local_gateways(
    bootstrap: BootstrapConfig,
    host_id: HostId,
    config: WorkerHostConfig,
    runtimes: WorkerRuntimes,
    storage: StorageBudget,
) -> dict[type[object], object]:
    from skm.adapters.checks.registry import build_check_registry
    from skm.adapters.git.environments.worktree import git_worktree_environments
    from skm.adapters.git.integration import git_integration_vcs
    from skm.adapters.git.runner import GitRunner
    from skm.adapters.sandbox.registry import build_isolation_registry
    from skm.modules.execution.ports import (
        CheckRunnerRegistry,
        ExecutionEnvironmentManager,
        IsolationRegistry,
        Vcs,
    )

    git = GitRunner()
    isolation = build_isolation_registry()
    return {
        RuntimeRegistry: runtimes,
        WorkerModelOfferPolicy: runtimes,
        ExecutionEnvironmentManager: git_worktree_environments(git, worktrees_root=bootstrap.worktrees_root),
        Vcs: git_integration_vcs(
            git,
            worktrees_root=bootstrap.state_dir / "integration",
            now=SystemClock().now,
            monotonic=SystemMonotonic().monotonic,
        ),
        IsolationRegistry: isolation,
        CheckRunnerRegistry: build_check_registry(
            storage=storage,
            capture_floor_bytes=int(cast("int", config.get("worker.disk_min_bytes"))),
            state_dir=bootstrap.state_dir,
            isolation_registry=isolation,
            profile="landlock",
            host=host_id,
            sanitized_env={"PATH": os.defpath},
        ),
    }


def _http_credential(
    bootstrap: BootstrapConfig,
    environ: Mapping[str, str],
    on_secret: Callable[[str], None],
) -> tuple[SecretRef, str]:
    credential = bootstrap.api_credential
    if isinstance(credential, SecretRef):
        return credential, resolve_worker_credential(str(credential), environ=environ, on_reveal=on_secret)
    if credential:
        on_secret(credential)
        return SecretRef.parse("secret://env/SKM_API_TOKEN"), credential
    raise PreconditionFailed(ErrorCode.SECRET_UNAVAILABLE, "HTTP worker credential is required")


def build_http_worker(  # noqa: PLR0915 - explicit HTTP worker composition and cleanup
    bootstrap: BootstrapConfig,
    *,
    environ: Mapping[str, str],
    credential_ref: str | None = None,
    credential_path: Path | None = None,
    on_secret: Callable[[str], None] = lambda _value: None,
    local_host: HostServices | None = None,
    machine_store: MachineStore | None = None,
) -> tuple[HostServices, SkmClient]:
    """Start a worker host with the credential and route table, without an embedded application."""
    # Use the same wire declarations as the HTTP hook, including the worker-only routes.
    from skm.bootstrap._http_mode import _client_routes as routes_for_dto  # pyright: ignore[reportPrivateUsage]

    host_id = resolve_host_id(
        {"host": {"id": str(bootstrap.host_id)}, "paths": {"state_dir": str(bootstrap.state_dir)}},
        Surface.WORKER,
        "http",
        None,
    )
    if local_host is not None and local_host.host_id != host_id:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Worker gateways belong to a different host")
    endpoint = bootstrap.api_endpoint
    if not endpoint:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "HTTP worker requires an API endpoint")
    if credential_ref is not None:
        bootstrap = replace(bootstrap, api_credential=SecretRef.parse(credential_ref))
    credential_path = credential_path or bootstrap.state_dir / "secrets" / "worker.token"
    source = bootstrap.api_credential
    if (
        source is not None
        and not (isinstance(source, SecretRef) and source.scheme == "file")
        and credential_path.exists()
    ):
        bootstrap = replace(
            bootstrap, api_credential=SecretRef.parse("secret://file/" + str(credential_path))
        )
    redactor, remember = worker_redactor(bootstrap, environ, on_secret)
    reference, secret = _http_credential(bootstrap, environ, remember)
    machine_settings = machine_runtime_settings(bootstrap, environ, machine_store, remember)
    machine = machine_settings()
    target = Path(reference.path) if reference.scheme == "file" else credential_path
    verify = (
        ssl.create_default_context(cafile=str(bootstrap.api_ca_bundle)) if bootstrap.api_ca_bundle else True
    )
    local: Mapping[type[object], object] = local_host.gateways.entries if local_host is not None else {}
    services = cast("WorkerServices | None", local.get(WorkerServices))
    storage = services.storage if services is not None else build_host_storage(bootstrap.state_dir)
    local_spool = BoundedLocalSpool(bootstrap.state_dir / "worker-spool", clock=SystemClock())
    clients = ExitStack()
    try:

        def http_client(value: SecretStr, run_id: UUID | None = None) -> HttpSkmClient:
            revealed = value.reveal()
            remember(revealed)
            return HttpSkmClient(
                endpoint,
                SecretValue(reference, revealed),
                routes_for_dto,
                spool_root=bootstrap.state_dir / "http-upload",
                storage_budget=storage,
                min_free_bytes=0,
                timeout_seconds=bootstrap.api_timeout_seconds,
                verify=verify,
                host_id=host_id,
                local_spool=local_spool,
                expected_instance_id=bootstrap.instance_id,
                run_scope_id=run_id,
            )

        def make_client(value: SecretStr) -> SkmClient:
            replacement = http_client(value)
            # Requests using the old credential can still be in flight during the grace period.
            clients.callback(replacement.close)
            return replacement

        client = RotatingClient(make_client(SecretStr(secret)))
        identity = cast("WhoAmIView", client.ask(WhoAmI()))
        token = identity.token
        if token is None or token.kind != "worker" or token.expires_at is None:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "HTTP worker requires an expiring worker token")

        config = RemoteWorkerConfig(client.ask, host_id, identity)

        def save(value: WorkerCredential) -> None:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            atomic_write(target, (value.secret.reveal() + "\n").encode(), mode=0o600, private=True)

        rotation = TokenRotation(
            WorkerCredential(token.token_id, token.expires_at, SecretStr(secret)),
            client,
            clock=SystemClock(),
            monotonic=SystemMonotonic(),
            config=config.rotation_setting,
            save=save,
            make_client=make_client,
        )
        plugins = HostPlugins(lambda: machine, lambda: config.snapshot().plugins)
        runtimes = WorkerRuntimes(
            plugins,
            lambda: machine,
            lambda: config.get("runtimes.allowed"),
            bootstrap.state_dir,
            storage,
            runtime_environment(environ, redactor),
            lambda refs: runtime_auth(refs, bootstrap, environ, redactor, on_secret),
            lambda local, installation: local_account_available(local, installation, environ),
        )
        gateways = _local_gateways(bootstrap, host_id, WorkerHostConfig(config, machine), runtimes, storage)

        def refresh() -> bool:
            nonlocal machine
            if not config.refresh():
                return False
            machine = machine_settings()
            return True

        if services is None:
            services = build_worker_services(
                bootstrap.state_dir,
                stages=_worker_stages(
                    bootstrap,
                    host_id,
                    client,
                    plugins,
                    gateways,
                    checkout_root=worker_checkout_root(bootstrap, host_id, machine_store, environ, remember),
                ),
                context_inputs=build_context_inputs(),
                resolve=lambda _ownership: None,
                storage=storage,
            )

        @contextmanager
        def live(claim: WorkerClaim, redactor: Redactor) -> Generator[Callable[[bytes], bool]]:
            publisher = LivePublisher(
                endpoint.removesuffix("/").removesuffix("/api/v1"),
                rotation.live_token,
                claim_json(claim),
                settings=config.snapshot().values,
                redactor=redactor,
                verify=verify,
                expected_instance_id=bootstrap.instance_id,
            )
            try:
                yield publisher.offer
                publisher.flush()
            finally:
                publisher.close()

        def stage_client(binding: StageToolBinding, secret: SecretStr) -> closing[HttpSkmClient]:
            return closing(http_client(secret, binding.run_id))

        host = build_host_services(
            {"host": {"id": str(host_id)}},
            client=client,
            plugins=(),
            environ=environ,
            surface=Surface.WORKER,
            host_config=lambda: WorkerHostConfig(config, machine),
            gateways={**gateways, **local, TokenRotation: rotation},
            owned_resources=(clients.close,),
            worker_services=replace(
                with_worker_model_policy(
                    services,
                    machine_settings,
                    runtimes,
                    cast("RuntimeRegistry | None", local.get(RuntimeRegistry)),
                ),
                refresh_config=refresh,
                workspace_id=config.workspace_id,
                stage_tool_client=stage_client,
                redact_runtime_probe=redactor.text,
                live=live,
            ),
            access_mode="http",
        )
        from skm.modules.runtimes.host.detect_runtimes import detect_runtimes

        detect_runtimes(
            host.context(client=client, cancel=CancelSource().token, log=get_logger("worker.host")),
            publish_local_details=False,
            redact=redactor.text,
        )
        if identity.modules.get("exports"):
            host = bind_vault_host(host, bootstrap, client)
    except BaseException:
        clients.close()
        raise
    return host, client
