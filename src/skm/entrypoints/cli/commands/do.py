"""Run a writable prompt on a local provider slot, optionally with an acceptance gate."""

import argparse

from skm.bootstrap.local_modes import DoRequest, local_do
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.ask import render_answer, runtime_args, session_gateways
from skm.entrypoints.cli.context import CliSession

__all__ = ["GROUP"]


def _run(args: argparse.Namespace, ctx: CliSession) -> int:
    request = DoRequest(
        args.prompt,
        args.slot,
        args.cwd,
        args.gate,
        args.gate_shell,
        args.max_gate_retries,
        args.allow_fresh_retry,
        ctx.redactor,
    )
    return render_answer(ctx, args.command_name, local_do(session_gateways(args, ctx), request))


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("do", help="run a writable prompt on a local provider slot")
    runtime_args(parser)
    parser.add_argument("--slot", help="provider slot ID")
    parser.add_argument("--gate", help="acceptance command as shell-quoted arguments")
    parser.add_argument("--gate-shell", action="store_true", help="run the gate through /bin/sh")
    parser.add_argument("--max-gate-retries", type=int, default=0, help="retries after a failed gate")
    parser.add_argument(
        "--allow-fresh-retry", action="store_true", help="allow retries without session resume"
    )
    parser.set_defaults(run=_run, command_name="execution.host.local_do")


GROUP = CommandGroup("do", "run a local task", register, requires_backend=False, order=67)
