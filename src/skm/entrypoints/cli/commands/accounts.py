"""Manage registered account slots on this host."""

import argparse
from pathlib import Path
from typing import cast

from skm.bootstrap.provider_accounts import ProviderAccounts, execute_account, load_provider_accounts
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.output import render, render_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

__all__ = ["GROUP", "register"]


def _load(args: argparse.Namespace, ctx: CliContext) -> ProviderAccounts:
    session = cast("CliSession", ctx)
    return load_provider_accounts(args.registry, session.environ, session.home)


def _accounts(args: argparse.Namespace, ctx: CliContext) -> int:
    accounts = _load(args, ctx)
    slots = accounts.pool(initialize=False).active_slots() if args.verb == "active" else accounts.slots
    payload = (
        slots
        if accounts.schema_version == 2
        else tuple(
            {
                "runtime_id": s.runtime_id,
                "slot_id": s.slot_id,
                "host_dispatches_tools": s.host_dispatches_tools,
            }
            for s in slots
        )
    )
    return render(
        ctx,
        payload,
        command=args.command_name,
        human=lambda _: (
            render_table(ctx, ("runtime", "slot"), [(s.runtime_id, s.slot_id) for s in slots])
            if slots
            else "no active provider accounts"
            if args.verb == "active"
            else "no provider accounts registered"
        ),
    )


def _doctor(args: argparse.Namespace, ctx: CliContext) -> int:
    accounts = _load(args, ctx)
    slot = accounts.get_slot(args.slot_id)
    config = accounts.config_for(slot.slot_id)
    pool = accounts.pool(initialize=False)
    isolation = pool.credential_isolation(slot.slot_id)
    warnings: list[str] = []
    if any(".ssh" in map(str.casefold, Path(name).parts) for name in config.symlink_host_files):
        warnings.append(".ssh is explicitly shared with the provider session")
    if isolation == "unsupported":
        warnings.append("tool-level credential isolation is unsupported for this account")
    return render(
        ctx,
        {"slot": slot, "credential_isolation": isolation, "warnings": warnings},
        command=args.command_name,
        human=lambda _: [
            f"{slot.slot_id} ({slot.runtime_id})",
            f"credential isolation: {isolation}",
            f"egress proxy: {slot.proxy_scheme or 'direct'}",
            *warnings,
        ],
    )


def _exec(args: argparse.Namespace, ctx: CliContext) -> int:
    invocation: list[str] = args.invocation
    if len(invocation) < 5 or invocation[1] != "--cwd" or invocation[3] != "--":
        raise ValidationFailed(
            ErrorCode.RUNTIME_INVALID_REQUEST, "usage: accounts exec SLOT --cwd DIR -- COMMAND [ARG ...]"
        )
    session = cast("CliSession", ctx)
    return execute_account(
        _load(args, ctx), invocation[0], Path(invocation[2]), invocation[4:], session.environ
    )


def register_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--registry",
        type=Path,
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="host provider pool TOML file",
    )
    parser.add_argument("--json", default=argparse.SUPPRESS, action="store_true")


def register(sub: SubParsers) -> None:
    group = sub.add_parser("accounts", help="manage registered provider account slots")
    group.set_defaults(run=_accounts, command_name="accounts", registry=None)
    register_args(group)
    verbs = group.add_subparsers(dest="verb")

    doctor = verbs.add_parser("doctor", help="inspect a provider account's isolation and egress")
    register_args(doctor)
    doctor.set_defaults(run=_doctor, command_name="accounts.doctor")
    doctor.add_argument("slot_id")

    active = verbs.add_parser("active", help="list slots with active leases")
    register_args(active)
    active.set_defaults(run=_accounts, command_name="accounts.active")

    execute = verbs.add_parser(
        "exec",
        help="run a local command with a provider account",
        usage="%(prog)s [--registry PATH] SLOT --cwd DIR -- COMMAND [ARG ...]",
    )
    register_args(execute)
    execute.set_defaults(run=_exec, command_name="accounts.exec")
    execute.add_argument("invocation", nargs="...", metavar="SLOT --cwd DIR -- COMMAND")


GROUP = CommandGroup(
    "accounts",
    "manage registered provider account slots",
    register,
    requires_backend=False,
    module="runtimes",
    order=65,
)
