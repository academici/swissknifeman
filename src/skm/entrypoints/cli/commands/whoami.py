"""``skm whoami`` (cli §6, access §8): who the acting credential is and what it may do, read live.

The query needs no permission of its own, but the bus still checks the credential against the stored token and
principal, so a revoked or expired token is ``UNAUTHENTICATED`` (exit 5) here too.
"""

import argparse
from typing import Final

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import kv_lines, render
from skm.kernel.json_types import JsonObject
from skm.modules.access import public as access

__all__ = ["GROUP", "register"]

_HELP: Final = {"": "show the acting principal, its memberships and effective permissions"}
COMMAND: Final = "access.whoami"


def _human(ctx: CliContext, view: access.WhoAmIView) -> list[str]:
    roles = ", ".join(f"{item.role.value}@{item.scope_kind}:{item.scope_id}" for item in view.memberships)
    pairs: list[tuple[str, object]] = [
        ("principal", f"{view.principal.display_name} ({view.principal.kind.value})"),
        ("id", view.principal.principal_id),
        ("roles", roles or "none"),
        ("permissions", ", ".join(view.effective_permissions) or "none"),
    ]
    if view.token is not None:
        pairs.append(("token", f"{view.token.name} ({view.token.kind.value}, {view.token.state})"))
    return kv_lines(ctx, pairs)


def _whoami(args: argparse.Namespace, ctx: CliContext) -> int:
    payload: JsonObject = {}
    scope = getattr(args, "scope", None)
    if scope is not None:
        payload["scope_id"] = str(ctx.resolve_scope(scope).id)
    view = ctx.client.ask(access.WhoAmI.from_json(payload))
    assert isinstance(view, access.WhoAmIView)  # noqa: S101 -- the bus validated the result
    return render(
        ctx,
        view,
        human=lambda value: _human(ctx, value),
        command=args.command_name,
        essential=lambda value: str(value.principal.principal_id),
    )


def register(sub: SubParsers) -> None:
    for verb in ("",):
        command = sub.add_parser("whoami", help=_HELP[verb])
        command.set_defaults(run=_whoami, command_name=COMMAND)
        command.add_argument(
            "--json",
            default=argparse.SUPPRESS,
            action="store_true",
            help="machine-readable output (as global --json)",
        )
        command.add_argument(
            "--scope",
            default=argparse.SUPPRESS,
            metavar="SCOPE",
            help="show effective permissions at this scope",
        )


GROUP = CommandGroup(
    "whoami", "show the acting principal and its permissions", register, module="access", order=40
)
