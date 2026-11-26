"""Explain permissions and preflight tool calls through the policy facade."""

import argparse
import json
from pathlib import Path
from typing import Any

from skm.entrypoints.cli._run_io import ask, operations, show
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed

CheckToolCall = operations("policy").CheckToolCall
ExplainPermissions = operations("policy").ExplainPermissions

_HELP = {"show": "explain effective permissions", "check": "check a JSON tool call without executing it"}


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    try:
        sid = str(ctx.resolve_scope(args.scope).id)
    except CapabilityUnavailable as error:
        if error.details.get("kind") != "instance":
            raise
        sid = str(ctx.instance_id) if isinstance(ctx, CliSession) and ctx.instance_id else None
    if sid is None:
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "policy requires a resolved scope")
    payload: dict[str, Any] = {"scope_id": sid, "profile_id": args.profile}
    if args.verb == "show":
        return show(ctx, "policy.explain_permissions", ask(ctx, ExplainPermissions, **payload))
    if args.shell_command is not None:
        cwd = str(Path(args.cwd or ".").resolve())
        call = {"tool": "shell.run", "command": args.shell_command, "cwd": cwd}
        roots: dict[str, Any] = {
            "worktrees": {"repo": cwd},
            "materials": None,
            "tmp": None,
            "home": None,
            "safe_dirs": [],
            "protected": [],
            "remote_hosts": [],
        }
    elif args.call is not None and args.roots is not None:
        try:
            call, roots = json.loads(args.call), json.loads(args.roots)
        except ValueError as error:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "call and roots require JSON") from error
    else:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "pass --command or CALL with --roots")
    try:
        payload.update(
            call=call,
            roots=roots,
            observed_origins=json.loads(args.observed_origins),
            mode=args.mode,
            interactive=args.mode == "interactive",
        )
    except ValueError as error:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "observed origins require JSON") from error
    return show(ctx, "policy.check_tool_call", ask(ctx, CheckToolCall, **payload))


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("policy", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in ("show", "check"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--scope", default=None)
        command.add_argument("--profile")
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if verb == "check":
            command.add_argument("call", nargs="?", help="tool call JSON")
            command.add_argument("--command", dest="shell_command")
            command.add_argument("--cwd")
            command.add_argument("--roots", help="scope roots JSON")
            command.add_argument("--observed-origins", default="{}")
            command.add_argument("--mode", choices=("agent_unattended", "interactive"), default="interactive")
        command.set_defaults(run=_run, command_name="policy." + verb)


GROUP = CommandGroup(
    name="policy",
    help="explain permissions and check tool calls",
    register=register,
    module="policy",
    order=32,
)

__all__ = ["GROUP"]
