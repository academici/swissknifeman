"""Native hook forwarding, using the same evaluator and output as skm-hook."""

from __future__ import annotations

import argparse
import sys
from typing import cast

from skm.bootstrap.hook import invoke
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext

COMMAND = "integrations.host.evaluate_hook"
HELP = "evaluate a native client hook"

__all__ = ["GROUP", "register"]


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    return invoke(
        args,
        getattr(ctx, "stdin", sys.stdin),
        ctx.stdout,
        ctx.stderr,
        getattr(ctx, "environ", {}),
        getattr(getattr(ctx, "options", None), "bootstrap", None),
    )


def add_parser(sub: SubParsers, name: str = "hook") -> None:
    parser = sub.add_parser(name, help=HELP, allow_abbrev=False)
    parser.add_argument("event_name", metavar="EVENT")
    parser.add_argument("--target", required=True)
    parser.add_argument("--surface", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--class", dest="hook_class", choices=("enforcement", "workflow", "observation"))
    parser.set_defaults(run=_run, command_name=COMMAND)


def register(sub: SubParsers) -> None:
    add_parser(sub)
    integrations = sub.choices.get("integrations")
    if integrations is not None:
        for action in integrations._actions:
            if isinstance(action, argparse._SubParsersAction):  # pyright: ignore[reportPrivateUsage]
                add_parser(cast("SubParsers", action))


GROUP = CommandGroup(
    "hook",
    "evaluate a native client hook",
    register,
    requires_backend=False,
    module="integrations",
    order=101,
)
