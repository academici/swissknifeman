"""List, inspect and select bootstrap instance profiles."""

from __future__ import annotations

import argparse
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit
from uuid import UUID

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliSession
from skm.entrypoints.cli.output import kv_lines, render, render_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.platform.config.sources.bootstrap import NewProfile, add_profile, cli_state_path, save_selection
from skm.platform.generated.queries import Doctor

if TYPE_CHECKING:
    from skm.application_bus.client import SkmClient
    from skm.entrypoints.cli.context import CliContext
    from skm.kernel.json_types import JsonObject
    from skm.platform.config.bootstrap import BootstrapConfig
    from skm.platform.generated.results import DoctorResult

__all__ = ["GROUP", "register"]

_HELP = {
    "list": "list bootstrap instance profiles",
    "show": "show a profile, its health and database schema version",
    "use": "select a profile globally or for the current checkout",
    "add": "add a bootstrap instance profile",
    "rebind": "authentically move a pinned HTTPS profile to another origin",
}


def _endpoint(config: BootstrapConfig) -> str:
    if config.access_mode == "embedded":
        return "PostgreSQL"
    try:
        parsed = urlsplit(config.api_endpoint or "")
        if (
            parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and parsed.hostname
            and parsed.scheme in ("http", "https")
        ):
            # Only expose the origin. An endpoint may also carry a credential in a path segment.
            return f"{parsed.scheme}://{parsed.netloc}"
    except ValueError:
        pass
    raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Invalid API endpoint")


def _health(client: SkmClient, expected: UUID | None) -> JsonObject:
    from skm.bootstrap.instance_secrets import instance_details

    doctor = cast("DoctorResult", client.ask(Doctor()))
    identity, version = instance_details(doctor, expected)
    return {
        "instance_id": str(identity),
        "available": True,
        "healthy": all(check.status != "fail" for check in doctor.checks),
        "schema_version": version,
    }


def _inspect(config: BootstrapConfig, ctx: CliSession) -> JsonObject:
    from skm.bootstrap.composition import open_cli_app
    from skm.kernel.ports_uow import Surface

    if config.access_mode == "http":
        from skm.bootstrap.instance_secrets import open_http_client

        with closing(
            open_http_client(
                config,
                ctx.environ,
                as_token=ctx.actor_hint,
                on_secret=ctx.redactor.register_secret,
                health_details=True,
            )
        ) as client:
            return _health(client, config.instance_id)

    app, actor = open_cli_app(
        config,
        environ=ctx.environ,
        invocation={"set": list(ctx.options.sets), "config": ctx.options.config or []},
        as_token=ctx.actor_hint,
        on_secret=ctx.redactor.register_secret,
    )
    with closing(app):
        return _health(app.client(actor=actor, surface=Surface.CLI), config.instance_id)


def _modify_profile(args: argparse.Namespace, ctx: CliSession) -> int:
    from skm.bootstrap.instance import find_bootstrap
    from skm.bootstrap.instance_profiles import activate_http_profile, verified_config

    target, _ = find_bootstrap(ctx.options.bootstrap, ctx.environ, ctx.home)
    previous = None
    if args.verb == "rebind":
        config = ctx.profile_catalog().config(args.name)
        previous = verified_config(config, args.name, ctx.environ, ctx.redactor.register_secret)
        if previous.access_mode != "http":
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Rebind requires a verified HTTP profile")
    expected = previous.instance_id if previous is not None else args.instance_id
    ca_bundle = args.ca_bundle
    if ca_bundle is not None:
        ca_bundle = (
            ctx.home / str(ca_bundle)[2:] if str(ca_bundle).startswith("~/") else ca_bundle
        ).absolute()
    new = NewProfile(
        name=args.name,
        instance_id=expected or ctx.ids.new_id(),
        mode=args.mode,
        database_url=args.database_url,
        endpoint=args.api_endpoint,
        credential=args.credential,
        ca_bundle=ca_bundle,
    )
    if args.mode == "http":
        activate_http_profile(
            target,
            new,
            ctx.environ,
            ctx.home,
            on_secret=ctx.redactor.register_secret,
            expected=expected,
            previous=previous,
        )
    else:
        add_profile(target, new, home=ctx.home)
    verb = "rebound" if previous is not None else "added"
    return render(
        ctx,
        {"name": args.name},
        command=args.command_name,
        human=lambda _: f"{verb} instance {args.name}",
        essential=lambda _: args.name,
    )


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    if not isinstance(ctx, CliSession):
        raise TypeError("instance commands require a CLI session")
    if args.verb in ("add", "rebind"):
        return _modify_profile(args, ctx)

    catalog = ctx.profile_catalog()
    cwd = Path.cwd()
    if args.verb == "use":
        selected = catalog.select(args.name, cwd)
        if not args.clear:
            from skm.bootstrap.instance_profiles import verified_config

            verified_config(catalog.config(selected), selected, ctx.environ, ctx.redactor.register_secret)
        directory = cwd.resolve() if args.here else None
        name = None if args.clear else selected
        save_selection(cli_state_path(ctx.environ, ctx.home), name=name, directory=directory)
        message = "cleared instance selection" if args.clear else f"using instance {selected}"
        if directory is not None:
            message += f" in {directory}"
        return render(
            ctx,
            {"instance": name, "checkout": str(directory) if directory else None},
            human=lambda _: message,
            command=args.command_name,
            essential=lambda _: name or "",
        )

    if args.verb == "show":
        from skm.bootstrap.instance_profiles import verified_config

        selected = catalog.select(args.name if args.name is not None else ctx.options.instance, cwd)
        config = verified_config(
            catalog.config(selected), selected, ctx.environ, ctx.redactor.register_secret
        )
        detail: JsonObject = {
            "name": selected,
            "mode": config.access_mode,
            "target": _endpoint(config),
            "state_dir": str(config.state_dir),
            "blobs_root": str(config.blobs_root),
            **_inspect(config, ctx),
        }
        return render(
            ctx,
            detail,
            command=args.command_name,
            human=lambda _: kv_lines(ctx, list(detail.items())),
            essential=lambda _: selected,
        )

    current = catalog.select(ctx.options.instance, cwd)
    rows: list[JsonObject] = []
    for name in catalog.names:
        config = catalog.config(name)
        rows.append(
            {
                "name": name,
                "mode": config.access_mode,
                "target": _endpoint(config),
                "current": name == current,
                "default": name == catalog.default,
            }
        )
    return render(
        ctx,
        rows,
        command=args.command_name,
        human=lambda _: render_table(
            ctx,
            ("name", "mode", "endpoint/database", "current", "default"),
            [list(row.values()) for row in rows],
        ),
    )


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("instance", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in ("list", "show", "use", "add", "rebind"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if verb == "show":
            command.add_argument("name", nargs="?")
        if verb in ("use", "add", "rebind"):
            command.add_argument("name")
        if verb == "use":
            command.add_argument("--here", action="store_true")
            command.add_argument("--clear", action="store_true")
        if verb == "add":
            command.add_argument("--mode", choices=("embedded", "http"), default="embedded")
            command.add_argument("--instance-id", type=UUID)
            command.add_argument("--database-url")
        if verb in ("add", "rebind"):
            if verb == "rebind":
                command.set_defaults(mode="http", database_url=None, instance_id=None)
            command.add_argument("--api-endpoint", required=verb == "rebind")
            command.add_argument("--credential", required=verb == "rebind")
            command.add_argument("--ca-bundle", type=Path)
        command.set_defaults(run=_run, command_name=f"cli.instance.{verb}")


GROUP = CommandGroup(
    name="instance", help="manage bootstrap profiles", register=register, requires_backend=False, order=12
)
