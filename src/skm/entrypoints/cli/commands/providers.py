"""Inspect the configured quota groups of local provider accounts."""

import argparse
from pathlib import Path
from typing import cast

from skm.bootstrap.provider_accounts import load_provider_accounts
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.output import render, render_table

__all__ = ["GROUP", "register"]

_HELP = {"probe": "probe quota groups for registered provider account slots"}


def _probe(args: argparse.Namespace, ctx: CliContext) -> int:
    session = cast("CliSession", ctx)
    readings = load_provider_accounts(args.registry, session.environ, session.home).probe()
    rows = [
        (
            r.slot.runtime_id,
            r.slot.slot_id,
            r.group.group_id,
            r.state,
            r.remaining if r.remaining is not None else "unknown",
        )
        for r in readings
    ]
    return render(
        ctx,
        readings,
        command=args.command_name,
        human=lambda _: (
            render_table(ctx, ("runtime", "slot", "group", "state", "remaining"), rows)
            if rows
            else "no provider accounts registered"
        ),
    )


def register(sub: SubParsers) -> None:
    group = sub.add_parser("providers", help="inspect provider quota")
    verbs = group.add_subparsers(dest="verb", required=True)
    for verb in ("probe",):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_probe, command_name="providers.probe")
        command.add_argument("--registry", type=Path, metavar="PATH", help="host provider pool TOML file")
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")


GROUP = CommandGroup(
    "providers", "inspect provider quota", register, requires_backend=False, module="runtimes", order=65
)
