"""Lazy subscription gateways for host surfaces and the built-in control-plane sink."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

__all__ = ["bind_cli_subscriptions", "dto", "webhook_sinks", "with_subscription_gateways"]


def dto(name: str, payload: dict[str, Any]) -> object:
    from skm.bootstrap.modules import MANIFESTS

    declaration = next(
        spec
        for manifest in MANIFESTS
        for spec in (*manifest.commands, *manifest.queries)
        if getattr(spec, "name", None) == name
    )
    return cast("Any", declaration).dto.from_json(payload)


def with_subscription_gateways(
    ctx: Any,
    state_dir: Path,
    environ: Mapping[str, str],
    *,
    config_provider: Callable[[], object] | None = None,
    native_drain: bool = False,
) -> Any:
    from skm.adapters.host_commands.subprocess_runner import (
        LocalSubscriptionState,
        SubprocessHostCommandRunner,
    )
    from skm.adapters.secrets.env import EnvSecretResolver
    from skm.adapters.secrets.file import FileSecretResolver
    from skm.kernel.gateways import GatewayTable
    from skm.modules.integrations.host.host_subscriptions import SubscriptionState
    from skm.modules.integrations.ports import HostCommandRunner
    from skm.platform.config.secrets import SecretResolvers

    entries = dict(ctx.gateways.entries)
    entries.setdefault(HostCommandRunner, SubprocessHostCommandRunner.for_session(environ))
    entries.setdefault(
        SubscriptionState,
        LocalSubscriptionState(
            state_dir,
            environ=environ,
            request_factory=dto,
            config_provider=config_provider,
            native_drain=native_drain,
            secrets=SecretResolvers(
                (EnvSecretResolver(environ), FileSecretResolver()), on_reveal=lambda _value: None
            ),
        ),
    )
    return replace(ctx, gateways=GatewayTable(entries, "host_gateway"))


def bind_cli_subscriptions(app: Any, bootstrap: Any, environ: Mapping[str, str]) -> Any:
    from uuid import UUID

    from skm.application_bus.host import HostContext, HostServices
    from skm.bootstrap.host_services import read_recorded_host_id
    from skm.kernel.cancel import CancelSource
    from skm.kernel.errors import ValidationFailed
    from skm.kernel.gateways import GatewayTable
    from skm.kernel.ids import HostId, ScopeId
    from skm.kernel.ports_uow import RequestMeta, Surface
    from skm.kernel.scopes import ScopeKind, ScopeRef
    from skm.modules.integrations.host.registry import HOST_OPERATIONS
    from skm.platform.config.store import ConfigStore, ScopeTree
    from skm.platform.logging.logger import get_logger
    from skm.platform.system_clock import SystemClock
    from skm.platform.system_ids import Uuid7Generator

    if app.host is not None:
        return app
    configured_host = bootstrap.host_id
    try:
        host_id = (
            HostId(configured_host)
            if isinstance(configured_host, UUID)
            else read_recorded_host_id(bootstrap.state_dir)
        )
    except ValidationFailed:
        # Leave the CLI usable to register the host again if its local record is damaged.
        return app
    if host_id is None:
        return app
    clock = SystemClock()
    ids = Uuid7Generator(clock)

    def config() -> object:
        meta = RequestMeta(f"hook-host-{ids.new_id()}", Surface.CLI, None, clock.now())
        with app.uow_factory(meta, readonly=True) as unit:
            return app.config.effective_host(
                unit.repo(ConfigStore), unit.repo(ScopeTree), ScopeRef(ScopeKind.HOST, ScopeId(host_id))
            )

    context = HostContext(
        cast("Any", None),
        GatewayTable({}, "host_gateway"),
        host_id,
        {},
        get_logger("cli.hooks"),
        CancelSource().token,
    )
    context = with_subscription_gateways(context, bootstrap.state_dir, environ, config_provider=config)
    services = HostServices(
        host_id,
        Surface.CLI,
        context.gateways,
        config,
        {op.name: op for op in HOST_OPERATIONS if ".host." in op.name},
    )
    return replace(app, host=services, host_id=host_id)


def webhook_sinks(clock: Any) -> Any:
    from skm import __version__
    from skm.adapters.event_sinks._pinned_http import PinnedHttpClient
    from skm.adapters.event_sinks.webhook import WebhookSink
    from skm.application_bus.subscribers import EventSinkRegistry
    from skm.platform.system_clock import SystemClock

    return EventSinkRegistry(
        (
            WebhookSink(
                http=PinnedHttpClient(), settings={}, clock=clock or SystemClock(), version=__version__
            ),
        )
    )
