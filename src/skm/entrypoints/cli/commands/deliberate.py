"""Run the same read-only prompt on several isolated provider slots."""

import argparse

from skm.bootstrap.local_modes import DeliberateRequest, DeliberateResult, local_deliberate
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.ask import runtime_args, session_gateways
from skm.entrypoints.cli.context import CliSession
from skm.entrypoints.cli.output import render

__all__ = ["GROUP"]


def _human(result: DeliberateResult) -> list[str]:
    lines: list[str] = []
    for answer in result.answers:
        lines.append(f"[{answer.slot}]")
        lines.extend((answer.error or answer.answer or "").splitlines())
    return lines


def _run(args: argparse.Namespace, ctx: CliSession) -> int:
    request = DeliberateRequest(args.prompt, tuple(args.slot), args.allow_partial)
    result = local_deliberate(session_gateways(args, ctx), request)
    render(ctx, result, command=args.command_name, human=_human)
    return result.exit_code


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("deliberate", help="ask distinct local provider slots in parallel")
    runtime_args(parser)
    parser.add_argument(
        "--slot", action="append", required=True, help="provider slot ID (repeat for each slot)"
    )
    parser.add_argument("--allow-partial", action="store_true", help="succeed if at least one slot answers")
    parser.set_defaults(run=_run, command_name="execution.host.local_deliberate")


GROUP = CommandGroup("deliberate", "ask local models in parallel", register, requires_backend=False, order=68)
