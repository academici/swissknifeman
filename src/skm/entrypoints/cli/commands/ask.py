"""Run a read-only prompt on a local provider slot."""

import argparse
from pathlib import Path

from skm.bootstrap.local_modes import AskRequest, LocalAnswer, LocalModeOptions, local_ask, runtime_gateways
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.accounts import register_args as register_accounts_args
from skm.entrypoints.cli.context import CliSession
from skm.entrypoints.cli.output import kv_lines, render
from skm.kernel.gateways import GatewayTable

__all__ = ["GROUP", "render_answer", "runtime_args", "session_gateways"]


def runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("prompt", help="instructions to the model")
    parser.add_argument("--model", help="model selector (default first native model of the slot)")
    parser.add_argument("--cwd", type=Path, default=Path("."), help="checkout directory (default current)")
    register_accounts_args(parser)
    parser.set_defaults(registry=None)


def session_gateways(args: argparse.Namespace, ctx: CliSession) -> GatewayTable:
    return runtime_gateways(
        LocalModeOptions(args.cwd, args.registry, args.model), ctx.environ, ctx.home, ctx.redactor
    )


def render_answer(ctx: CliSession, command: str, answer: LocalAnswer) -> int:
    render(
        ctx,
        answer,
        command=command,
        human=lambda value: (value.error or value.answer or "").splitlines(),
        essential=lambda value: value.error or value.answer or "",
    )
    return int(answer.error is not None)


def _run(args: argparse.Namespace, ctx: CliSession) -> int:
    if args.dry_run:
        preview = {
            "prompt": args.prompt,
            "cwd": str(args.cwd),
            "slot": args.slot,
            "model": args.model,
            "schema": str(args.schema) if args.schema is not None else None,
            "config_mode": "isolated",
            "read_only": True,
        }
        return render(
            ctx, preview, command=args.command_name, human=lambda value: kv_lines(ctx, value.items())
        )
    request = AskRequest(args.prompt, args.slot, args.schema)
    return render_answer(ctx, args.command_name, local_ask(session_gateways(args, ctx), request))


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("ask", help="run a read-only prompt on a local provider slot")
    runtime_args(parser)
    parser.add_argument("--slot", help="provider slot ID")
    parser.add_argument("--schema", type=Path, help="validate the response against a local JSON Schema")
    parser.add_argument("--dry-run", action="store_true", help="preview the request offline")
    parser.set_defaults(run=_run, command_name="execution.host.local_ask")


GROUP = CommandGroup("ask", "ask a local model", register, requires_backend=False, order=66)
