"""Control the local LLM router independently of the SKM backend."""

import argparse
from pathlib import Path
from typing import cast

from skm.bootstrap.router import control_router, router_status, start_router
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.output import render

__all__ = ["GROUP", "register"]

_HELP = {
    "start": "start the loopback LLM router",
    "stop": "stop the local LLM router",
    "status": "show the local LLM router status",
    "reload": "reload the local LLM router configuration",
}


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    session = cast("CliSession", ctx)
    match args.verb:
        case "start":
            result = start_router(
                session.environ,
                session.home,
                config=args.config,
                port=args.port,
                daemon=args.daemon,
            )
        case "stop" | "reload":
            result = control_router(session.environ, session.home, reload=args.verb == "reload")
        case _:
            result = router_status(session.environ, session.home)
    return render(ctx, result, command=args.command_name, human=lambda _: f"router {result['status']}")


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("router", help="control the local LLM router")
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in ("start", "stop", "status", "reload"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_run, command_name=f"router.{verb}")
        if verb == "start":
            command.add_argument("--daemon", action="store_true", help="detach from the terminal")
            command.add_argument("--port", type=int, help="override the listen port (default 8317)")
            command.add_argument("--config", type=Path, help="provider pool configuration file")
        if verb == "status":
            command.add_argument(
                "--json", default=argparse.SUPPRESS, action="store_true", help="machine-readable status"
            )


GROUP = CommandGroup(
    "router", "control the local LLM router", register, requires_backend=False, module="runtimes"
)
