"""Composition of remote CLI clients and the hook host configuration snapshot."""

from __future__ import annotations

import ssl
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from time import monotonic
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.bootstrap.host_services import build_host_storage
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed
from skm.kernel.ids import HostId
from skm.kernel.json_types import JsonObject
from skm.platform.config.secrets import SecretValue

if TYPE_CHECKING:
    from skm.adapters.http_client.client import HttpSkmClient, RouteTable
    from skm.platform.config.bootstrap import BootstrapConfig

__all__ = ["HttpHookApp", "build_http_client", "build_http_hook_app"]

_HOST_KEYS = ("integrations.hook.cache_ttl_seconds", "integrations.hook.timeout_ms")


@dataclass(frozen=True, slots=True)
class HttpHookApp:
    client: HttpSkmClient
    host_id: HostId
    config: JsonObject
    principal: UUID

    def close(self) -> None:
        self.client.close()


@cache
def _module_routes(modules: tuple[str, ...]):
    from skm.entrypoints.api.routing import build_route_table

    return build_route_table(modules)


def _client_routes(dto: type[object]) -> RouteTable:
    from skm.entrypoints.api.routes import MODULE_IDS

    # Most native hooks need only settings, integrations and workspace. Other surfaces
    # (e.g. worker aliases) are still available through the full declaration table.
    urn = getattr(dto, "SCHEMA_URN", "").split(":")
    if len(urn) > 2 and urn[2] in MODULE_IDS:
        table = _module_routes((urn[2],))
        if any(route.dto_type is dto for route in table.describe()):
            return table
    return _module_routes(MODULE_IDS)


@cache
def _health_routes():
    """Use the health alias of Doctor only for instance inspection."""
    platform = _module_routes(("access", "settings", "workspace"))
    return type(platform)(route for route in platform.describe() if route.path == "/health/details")


def build_http_client(
    bootstrap: BootstrapConfig,
    token: SecretValue,
    *,
    health_details: bool = False,
    deadline: Callable[[], float] | None = None,
    run_scope_id: UUID | None = None,
) -> HttpSkmClient:
    from skm.adapters.http_client.client import HttpSkmClient
    from skm.modules.execution.generated.settings import WorkerSettings
    from skm.platform.schema.registry import SchemaRegistry

    if not bootstrap.api_endpoint:
        raise PreconditionFailed(ErrorCode.CONFIG_INVALID, "HTTP requires an API endpoint")
    verify = (
        ssl.create_default_context(cafile=str(bootstrap.api_ca_bundle)) if bootstrap.api_ca_bundle else True
    )
    worker_schema = SchemaRegistry.load_default().get(WorkerSettings.SCHEMA_URN)
    worker_properties = cast("dict[str, JsonObject]", worker_schema["properties"])
    floor = cast("int", worker_properties["disk_min_bytes"]["default"])
    return HttpSkmClient(
        bootstrap.api_endpoint,
        token,
        _health_routes() if health_details else _client_routes,
        spool_root=bootstrap.state_dir / "http-upload",
        storage_budget=build_host_storage(bootstrap.state_dir),
        min_free_bytes=floor,
        timeout_seconds=bootstrap.api_timeout_seconds,
        verify=verify,
        max_attempts=1 if deadline else 4,
        deadline=deadline,
        run_scope_id=run_scope_id,
        expected_instance_id=bootstrap.instance_id,
    )


def build_http_hook_app(
    bootstrap: BootstrapConfig,
    environ: Mapping[str, str],
    credential: SecretValue,
    *,
    started: float | None = None,
    drain: bool = False,
) -> HttpHookApp:
    from skm.bootstrap.hook import hook_principal

    start = monotonic() if started is None else started
    override_ms = environ.get("SKM__INTEGRATIONS__HOOK__TIMEOUT_MS")
    deadline = start + max(1, int(override_ms or "2000")) / 1000
    from skm.modules.settings.application.queries.explain_config import ExplainConfigResult
    from skm.modules.settings.generated.queries import ExplainConfig, ExplainConfigDefsScopeRef

    if (
        not bootstrap.api_endpoint
        or not isinstance(bootstrap.host_id, UUID)
        or bootstrap.installation_id is None
        or bootstrap.instance_id is None
    ):
        raise PreconditionFailed(ErrorCode.CONFIG_INVALID, "HTTP hook requires a verified profile and host")
    client = build_http_client(
        bootstrap, credential, deadline=None if drain and started is None else lambda: deadline
    )
    try:
        principal = hook_principal(client)
        if drain:
            return HttpHookApp(client, HostId(bootstrap.host_id), {}, principal)
        try:
            result = cast(
                "ExplainConfigResult",
                client.ask(
                    ExplainConfig(
                        ExplainConfigDefsScopeRef("host", bootstrap.host_id),
                        keys=_HOST_KEYS,
                        detail="value",
                    )
                ),
            )
        except Forbidden:
            # A workspace-limited hook credential need not read host settings.
            return HttpHookApp(
                client,
                HostId(bootstrap.host_id),
                {_HOST_KEYS[1]: max(1, int(override_ms or "2000"))},
                principal,
            )
        config: JsonObject = {
            entry["key"]: entry["value"]
            for entry in cast("list[JsonObject]", result.report["keys"])
            if isinstance(entry["key"], str)
            and entry["present"]
            and entry.get("valid", True)
            and "value" in entry
        }
        timeout_ms = (
            int(override_ms) if override_ms is not None else cast("int", config.get(_HOST_KEYS[1], 2000))
        )
        config[_HOST_KEYS[1]] = max(1, timeout_ms)
        deadline = start + max(1, timeout_ms) / 1000
        return HttpHookApp(client, HostId(bootstrap.host_id), config, principal)
    except BaseException:
        client.close()
        raise
