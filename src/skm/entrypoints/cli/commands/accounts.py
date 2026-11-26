"""List account slots registered on this host."""

import argparse
from pathlib import Path
from typing import cast

from skm.bootstrap.provider_accounts import load_provider_accounts
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.output import render, render_table

__all__ = ["GROUP", "register"]

_HELP = {"": "list registered provider account slots"}


def _accounts(args: argparse.Namespace, ctx: CliContext) -> int:
    session = cast("CliSession", ctx)
    slots = load_provider_accounts(args.registry, session.environ, session.home).slots
    return render(
        ctx,
        slots,
        command=args.command_name,
        human=lambda _: (
            render_table(ctx, ("runtime", "slot"), [(s.runtime_id, s.slot_id) for s in slots])
            if slots
            else "no provider accounts registered"
        ),
    )


def register(sub: SubParsers) -> None:
    for verb in ("",):
        command = sub.add_parser("accounts", help=_HELP[verb])
        command.set_defaults(run=_accounts, command_name="accounts")
        command.add_argument("--registry", type=Path, metavar="PATH", help="host provider pool TOML file")
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")


GROUP = CommandGroup("accounts", _HELP[""], register, requires_backend=False, module="runtimes", order=65)
