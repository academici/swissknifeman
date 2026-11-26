"""Run the HTTP API and registered control-plane background services."""

import argparse
from contextlib import closing, suppress
from pathlib import Path
from time import monotonic
from typing import cast

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.output import render
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject

__all__ = ["GROUP", "register"]

_HELP = {"": "run the HTTP API and control-plane background services"}


def _serve_machine(args: argparse.Namespace, session: CliSession, profile: str) -> int:
    from skm.bootstrap.machine_access import build_machine_server
    from skm.entrypoints.api.app import serve_asgi

    if args.bind is not None or args.background_only:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Machine API only listens on its Unix socket")
    config = build_machine_server(
        session.profile_catalog, profile, on_secret=session.redactor.register_secret
    )
    serve_asgi(config)
    return render(
        session,
        {"status": "stopped", "socket": str(config.socket)},
        human=lambda _: "machine API stopped",
        command=args.command_name,
    )


def _serve(args: argparse.Namespace, ctx: CliContext) -> int:  # noqa: PLR0915 -- lifecycle and bind guards
    from skm.bootstrap.composition import build_app, storage_recovery
    from skm.bootstrap.composition_resources import serve_pool_shutdown
    from skm.bootstrap.lifecycle import (
        DEFAULT_BIND,
        add_background_services,
        api_settings,
        embedded_dsn,
        local_migrate,
        parse_bind,
        runtime_settings,
    )
    from skm.bootstrap.services import build_service_runner, running_services
    from skm.kernel.cancel import Cancelled
    from skm.kernel.ports_uow import Surface
    from skm.platform.logging.logger import get_logger
    from skm.platform.logging.redaction import Redactor
    from skm.platform.system_clock import SystemClock

    if args.workers != 1:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "skm serve requires exactly one worker")
    if args.background_only and (args.no_background or args.bind is not None):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "--background-only cannot be combined with --no-background or --bind"
        )
    if args.bind is not None:
        parse_bind(args.bind)
    session = cast("CliSession", ctx)
    catalog = session.profile_catalog()
    profile = catalog.select(args.instance, Path.cwd())
    config = storage_recovery.pinned_profile(catalog.config(profile))
    if args.machine or config.access_mode == "http":
        return _serve_machine(args, session, profile)
    if args.bind is not None and config.web_auth.mode == "none":
        from ipaddress import IPv6Address, ip_address

        host, _port = parse_bind(args.bind)
        loopback = host.lower() == "localhost"
        if not loopback:
            try:
                addr = ip_address(host.split("%", 1)[0])
                loopback = addr.is_loopback or (
                    isinstance(addr, IPv6Address)
                    and addr.ipv4_mapped is not None
                    and addr.ipv4_mapped.is_loopback
                )
            except ValueError:
                loopback = False
        if not loopback:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                "web_auth.mode='none' requires a loopback bind address (127.0.0.1, [::1], or localhost)",
                details={"field": "web_auth.mode", "bind": args.bind},
            )
    redactor = Redactor()

    def register_secret(value: str) -> None:
        ctx.redactor.register_secret(value)
        redactor.register_secret(value)

    embedded_dsn(config, session.environ, register_secret)
    if config.database_migrate_on_start:
        local_migrate(config, session.environ, register_secret, startup=True)
    surface = Surface.BACKGROUND if args.background_only else Surface.API
    invocation: JsonObject = {"set": list(session.options.sets), "config": session.options.config or []}
    bind = None
    with (
        serve_pool_shutdown() as drain,
        closing(build_app(config, surface=surface, environ=session.environ, invocation=invocation)) as app,
    ):
        core = app if args.no_background else add_background_services(app)
        if args.background_only:
            values = runtime_settings(core)
            log = get_logger("entrypoints.cli.serve")
            runner = build_service_runner(core.services, config=values, clock=SystemClock(), log=log)
            grace = float(cast("int", values["api.shutdown.grace_seconds"]))
            with (
                suppress(Cancelled),
                running_services(runner, timeout_seconds=grace) as cancel,
            ):
                try:
                    while not cancel.wait(1.0):
                        pass
                finally:
                    drain(monotonic() + grace)
        else:
            from skm.entrypoints.api.app import serve_asgi

            bind = args.bind or str(api_settings(core).get("api.bind", DEFAULT_BIND))

            serve_asgi(
                core,
                bind,
                no_background=args.no_background,
                redactor=redactor,
                on_shutdown=drain,
            )
    result = {"status": "stopped", "bind": bind, "background": not args.no_background}
    return render(ctx, result, human=lambda _: "serve stopped", command=args.command_name)


def register(sub: SubParsers) -> None:
    # The reference generator treats the empty verb as the command's own declaration.
    for verb in ("",):
        command = sub.add_parser("serve", help=_HELP[verb])
        command.set_defaults(run=_serve, command_name="cli.serve")
        command.add_argument("--bind", metavar="HOST:PORT", help="override api.bind")
        command.add_argument(
            "--machine", action="store_true", help="serve the machine API on its Unix socket"
        )
        command.add_argument("--no-background", action="store_true", help="serve HTTP only")
        command.add_argument(
            "--background-only", action="store_true", help="run services without an HTTP listener"
        )
        command.add_argument(
            "--workers", type=int, default=1, metavar="N", help="number of processes (1 only)"
        )
        command.add_argument(
            "--json", default=argparse.SUPPRESS, action="store_true", help="machine-readable output"
        )


GROUP = CommandGroup("serve", _HELP[""], register, requires_backend=False, order=31)
