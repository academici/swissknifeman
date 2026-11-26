"""Runtime, plugin, account and model gateways on the worker machine."""

from __future__ import annotations

import os
import stat
from dataclasses import replace
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from skm import __version__
from skm.adapters.runtimes.grok.runtime import grok_account_available
from skm.adapters.runtimes.launch_identity import matches_cli_binary
from skm.bootstrap.runtimes import RUNTIME_FACTORIES, WorkerRuntimeSettings
from skm.bootstrap.worker_credentials import resolve_worker_credential
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, NotFound, SkmError, ValidationFailed
from skm.modules.runtimes.domain.catalog_records import WORKER_OFFER_TTL
from skm.modules.runtimes.domain.installation import public_runtime_version
from skm.modules.runtimes.public import AuthState, Capability, Effort
from skm.modules.settings.public import worker_identifiers
from skm.platform.config.secrets import SecretRef
from skm.platform.logging.redaction import Redactor
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.system_clock import SystemClock
from skm.plugin_api.manifest import ComponentKind

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from datetime import datetime

    from skm.adapters.http_client.worker_config import RemoteWorkerConfig
    from skm.bootstrap.plugins import LoadedPlugin, PluginSchema, PluginSchemas
    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.host.context import WorkerServices
    from skm.modules.execution.host.stages.base import StageRequest
    from skm.modules.execution.ports import StageDeps
    from skm.modules.runtimes.public import (
        AgentRequest,
        AgentRuntime,
        RuntimeInstallation,
        RuntimeRegistry,
    )
    from skm.modules.settings.public import GetHostConfigResultPlugins
    from skm.platform.config import EffectiveConfig
    from skm.platform.config.bootstrap import BootstrapConfig
    from skm.platform.fs.storage_budget import StorageBudget
    from skm.platform.machine import MachineStore

__all__ = [
    "HostPlugins",
    "WorkerHostConfig",
    "WorkerRuntimes",
    "local_account_available",
    "machine_runtime_settings",
    "runtime_auth",
    "with_worker_model_policy",
    "worker_redactor",
]


def worker_redactor(
    bootstrap: BootstrapConfig, environ: Mapping[str, str], on_secret: Callable[[str], None]
) -> tuple[Redactor, Callable[[str], None]]:
    redactor = Redactor()

    def remember(value: str) -> None:
        redactor.register_secret(value)
        on_secret(value)

    for key, value in environ.items():
        if any(
            part in key
            for part in (
                "TOKEN",
                "SECRET",
                "PASSWORD",
                "CREDENTIAL",
                "API_KEY",
                "DSN",
                "DATABASE_URL",
                "MIGRATOR_URL",
            )
        ):
            remember(value)
    for source in (
        bootstrap.database_url,
        bootstrap.database_migrator_url,
        bootstrap.machine_database_url,
        bootstrap.machine_database_migrator_url,
        bootstrap.api_credential,
        bootstrap.token_pepper,
    ):
        if isinstance(source, SecretRef) and source.scheme == "env":
            if value := environ.get(source.path):
                remember(value)
        elif isinstance(source, str):
            remember(source)
    return redactor, remember


def machine_runtime_settings(
    bootstrap: BootstrapConfig,
    environ: Mapping[str, str],
    machine_store: MachineStore | None,
    remember: Callable[[str], None],
) -> Callable[[], WorkerRuntimeSettings]:
    if machine_store is None and bootstrap.machine_database_url is not None:
        from skm.adapters.postgres.machine import PostgresMachineStore

        dsn = resolve_worker_credential(
            str(bootstrap.machine_database_url), environ=environ, on_reveal=remember
        )
        machine_store = PostgresMachineStore(dsn)
    if machine_store is None:
        return WorkerRuntimeSettings
    frozen_store = machine_store
    if (
        bootstrap.installation_id is not None
        and bootstrap.installation_id != frozen_store.get_installation_id()
    ):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Worker machine installation does not match bootstrap"
        )
    return lambda: WorkerRuntimeSettings.read(frozen_store)


def runtime_auth(
    refs: Mapping[str, SecretRef],
    bootstrap: BootstrapConfig,
    environ: Mapping[str, str],
    redactor: Redactor,
    on_secret: Callable[[str], None],
) -> dict[str, str]:
    protected = (
        bootstrap.database_url,
        bootstrap.database_migrator_url,
        bootstrap.machine_database_url,
        bootstrap.machine_database_migrator_url,
        bootstrap.api_credential,
        bootstrap.token_pepper,
    )
    values: dict[str, str] = {}
    for name, ref in refs.items():
        try:
            if ref in protected or (ref.scheme == "env" and ref.path.startswith("SKM_")):
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Protected credential")
            value = resolve_worker_credential(str(ref), environ=environ, on_reveal=lambda _value: None)
            if (
                value in protected
                or value.startswith(("postgres://", "postgresql://", "skm_"))
                or "dbname=" in value
            ):
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Protected credential")
        except SkmError:
            raise CapabilityUnavailable(
                ErrorCode.RUNTIME_AUTH_EXPIRED, "Local runtime account is unavailable"
            ) from None
        redactor.register_secret(value)
        on_secret(value)
        values[name] = value
    return values


def _private_account_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and info.st_size > 0
        and not info.st_mode & 0o077
    )


def local_account_available(
    local: WorkerRuntimeSettings, installation: RuntimeInstallation, environ: Mapping[str, str]
) -> bool:
    """Check selected local account material without copying its contents into observations."""
    runtime_id = installation.runtime_id
    refs = local.accounts.get(runtime_id)
    if not (runtime_id == "codex" and refs) and installation.auth_state in {
        AuthState.MISSING,
        AuthState.EXPIRED,
    }:
        return False
    if runtime_id == "grok":
        return grok_account_available(local.grok_account_home)
    if refs:
        return all(
            bool(environ.get(ref.path))
            if ref.scheme == "env"
            else ref.scheme == "file" and _private_account_file(Path(ref.path).expanduser())
            for ref in refs.values()
        )
    if runtime_id not in RUNTIME_FACTORIES:
        return installation.auth_state is AuthState.OK
    native = {"codex": ".codex/auth.json", "claude_code": ".claude/.credentials.json"}.get(runtime_id)
    copy = local.get("runtimes.credentials.copy")
    if native is None or not isinstance(copy, dict) or copy.get(runtime_id) is not True:
        return False
    home_env = environ.get("HOME")
    return (
        home_env is not None
        and (runtime_id != "codex" or installation.auth_state is AuthState.OK)
        and _private_account_file(Path(home_env) / native)
    )


class WorkerHostConfig:
    def __init__(self, project: EffectiveConfig | RemoteWorkerConfig, local: WorkerRuntimeSettings) -> None:
        self._project = project
        self._local = local

    def get(self, key: str) -> object:
        if key.startswith("runtimes.") or key.startswith("plugins."):
            return self._local.get(key)
        getter = self._project.get
        return getter(key)


def with_worker_model_policy(
    services: WorkerServices,
    local: Callable[[], WorkerRuntimeSettings],
    runtimes: WorkerRuntimes | None,
    registry: RuntimeRegistry | None = None,
) -> WorkerServices:
    def runtime_request(stage: StageRequest, deps: StageDeps) -> AgentRequest:
        request = services.runtime_request(stage, deps)
        if not local().allows_model(request.runtime_id, request.model, request.effort):
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE, "Model is unavailable on this worker"
            )
        return request

    def verify(request: AgentRequest, digest: str | None) -> None:
        services.verify_runtime(request, digest)
        if runtimes is not None:
            runtimes.verify_runtime(request, digest, registry=registry)

    return replace(services, runtime_request=runtime_request, verify_runtime=verify)


def _load_host_plugins(
    config: WorkerRuntimeSettings, allowed: tuple[str, ...], required: frozenset[str]
) -> tuple[LoadedPlugin, ...]:
    from skm.bootstrap.plugins import (
        PluginSchemas,
        default_context,
        load_plugins,
        merged_schemas,
        plugin_settings_view,
    )

    schemas = SchemaRegistry.load_default()

    def phase2(documents: Sequence[PluginSchema], urns: Sequence[str]) -> PluginSchemas:
        merged = merged_schemas(schemas, documents)
        return PluginSchemas(merged, {urn: plugin_settings_view(merged, urn) for urn in urns})

    return load_plugins(
        allowed=allowed,
        required=required,
        side="host",
        skm_version=__version__,
        schemas=schemas,
        settings_phase2=phase2,
        context=lambda plugin, view, registry: default_context(plugin, view, registry, lambda: config),
    )


class HostPlugins:
    def __init__(
        self,
        local: Callable[[], WorkerRuntimeSettings],
        limits: Callable[[], GetHostConfigResultPlugins],
    ) -> None:
        self._local, self._limits = local, limits
        self._lock = RLock()
        self._loaded_for = None
        self._plugins: tuple[LoadedPlugin, ...] = ()

    def components(self, kind: ComponentKind) -> tuple[object, ...]:
        with self._lock:
            local, project = self._local(), self._limits()
            allowed = tuple(plugin for plugin in local.plugins if plugin in project.allowed)
            required = frozenset(project.required)
            if required - set(allowed):
                raise CapabilityUnavailable(
                    ErrorCode.CAPABILITY_UNAVAILABLE, "A required plugin is unavailable on this worker"
                )
            identity = (local, allowed, required)
            if identity != self._loaded_for:
                self._plugins = _load_host_plugins(local, allowed, required)
                self._loaded_for = identity
            return tuple(
                component
                for plugin in self._plugins
                for (component_kind, _key), component in plugin.instances.items()
                if component_kind is kind
            )


class WorkerRuntimes:
    def __init__(
        self,
        plugins: HostPlugins,
        local: Callable[[], WorkerRuntimeSettings],
        project: Callable[[], JsonValue],
        state_dir: Path,
        storage: StorageBudget,
        environ: Mapping[str, str],
        auth: Callable[[Mapping[str, SecretRef]], dict[str, str]],
        account: Callable[[WorkerRuntimeSettings, RuntimeInstallation], bool] | None = None,
    ) -> None:
        self._plugins, self._local, self._project = plugins, local, project
        self._state_dir, self._storage, self._environ, self._auth = state_dir, storage, environ, auth
        self._account = account
        self._clock = SystemClock()
        self._lock = RLock()
        self._settings: WorkerRuntimeSettings | None = None
        self._builtin: dict[str, AgentRuntime] = {}
        self._observed: dict[str, tuple[AgentRuntime, RuntimeInstallation]] = {}

    def _build(self, local: WorkerRuntimeSettings, name: str) -> AgentRuntime:
        options: dict[str, object] = {"environ": self._environ}
        if name != "cursor":
            options.update(state_dir=self._state_dir, storage_budget=self._storage)
        if name == "grok":
            options["account_home"] = local.grok_account_home
        if refs := local.accounts.get(name):
            if name not in {"antigravity", "claude_code", "codex", "gemini_cli"}:
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Local account uses an unsupported runtime")
            options["local_auth"] = lambda: self._auth(refs)
        return RUNTIME_FACTORIES[name](SimpleNamespace(config=local), **options)

    def _items(self) -> dict[str, AgentRuntime]:
        with self._lock:
            local = self._local()
            allowed = self._project()
            project = (
                None if allowed is None else frozenset(worker_identifiers(allowed, key="runtimes.allowed"))
            )
            if self._settings != local:
                builtins = ("antigravity", "claude_code", "codex", "cursor", "gemini_cli", "grok")
                self._builtin = {
                    name: self._build(local, name)
                    for name in builtins
                    if name in local.allowed and (name != "grok" or local.grok_account_home is not None)
                }
                self._settings = local
            runtimes = cast("tuple[AgentRuntime, ...]", self._plugins.components(ComponentKind.RUNTIME))
            items = dict(self._builtin)
            if "grok" in items and not grok_account_available(local.grok_account_home):
                items.pop("grok", None)
            for runtime in runtimes:
                if runtime.runtime_id not in items and (runtime.runtime_id in local.allowed):
                    items[runtime.runtime_id] = runtime
            return {name: runtime for name, runtime in items.items() if project is None or name in project}

    def verify_runtime(
        self, request: AgentRequest, expected_digest: str | None, *, registry: RuntimeRegistry | None
    ) -> None:
        runtime_id = request.runtime_id
        local = self._local()
        if not local.allows_model(runtime_id, request.model, request.effort):
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE, "Model is unavailable on this worker"
            )
        runtime = (self if registry is None else registry).get(runtime_id)
        with self._lock:
            recorded = self._observed.get(runtime_id)
        if recorded is not None and recorded[0] is runtime:
            installation = recorded[1]
            digest = installation.details.get("executable_sha256") or installation.details.get(
                "binary_sha256"
            )
            version = public_runtime_version(installation.version)
            now = self.now()
            if (
                installation.host_id == request.process_owner.host_id
                and installation.detected_at <= now < installation.detected_at + WORKER_OFFER_TTL
                and version is not None
                and version == request.expected_runtime_version
                and (expected_digest is None or digest == expected_digest)
                and self.account_available(installation)
                and runtime.capabilities().supports(Capability.HEADLESS_EXECUTION)
                and self._matches_binary(local, runtime, request, installation, digest)
            ):
                return
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE, "Worker runtime authorization or installation changed"
        )

    def _matches_binary(
        self,
        local: WorkerRuntimeSettings,
        runtime: AgentRuntime,
        request: AgentRequest,
        installation: RuntimeInstallation,
        digest: str | None,
    ) -> bool:
        binaries = cast("dict[str, str] | None", local.get("runtimes.binaries")) or {}
        candidate = binaries.get(request.runtime_id)
        context = request.verification_context
        if candidate is None and context is None and request.runtime_id not in RUNTIME_FACTORIES:
            return True  # Plugin runtimes can have no local CLI executable.
        locator = installation.binary_locator
        if locator is None or digest is None or (context is not None and context.binary_sha256 != digest):
            return False
        return matches_cli_binary(
            candidate or getattr(runtime, "default_binary", locator),
            locator=locator,
            digest=digest,
            environ=self._environ,
            runtime_id=request.runtime_id,
        )

    def observe_installation(self, runtime: AgentRuntime, installation: RuntimeInstallation | None) -> None:
        """Retain local probe facts for handoff without probing from the assignment path."""
        with self._lock:
            if installation is None:
                self._observed.pop(runtime.runtime_id, None)
            else:
                self._observed[runtime.runtime_id] = (runtime, installation)

    def now(self) -> datetime:
        return self._clock.now()

    def allows_model(self, runtime_id: str, model_id: str, effort: Effort) -> bool:
        return self._local().allows_model(runtime_id, model_id, effort)

    def account_available(self, installation: RuntimeInstallation) -> bool:
        if self._account is None:
            return installation.auth_state is AuthState.OK
        return self._account(self._local(), installation)

    def ids(self) -> frozenset[str]:
        return frozenset(self._items())

    def get(self, runtime_id: str) -> AgentRuntime:
        try:
            return self._items()[runtime_id]
        except KeyError:
            raise NotFound(ErrorCode.NOT_FOUND, "Runtime is unavailable on this worker") from None
