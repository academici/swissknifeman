"""``skm member`` (cli §6, access §14): grant, revoke and list memberships through ``access.public``.

A membership is a role of a principal on one scope. The scope is the explicit ``--scope`` (or the saved
context); whether the actor may grant a role (no escalation, ``can_grant``) is decided by the owner handler
after the bus checked ``membership.manage`` at that scope.
"""

import argparse
from typing import Final
from uuid import UUID

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.principal import principal_ref
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import render, render_table, safe_text
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, NotFound
from skm.kernel.json_types import JsonObject
from skm.modules.access import public as access

__all__ = ["GROUP", "register"]

_HELP: Final = {
    "grant": "grant a role to a principal on a scope",
    "revoke": "remove the membership of a principal on a scope",
    "list": "list memberships by scope and/or principal",
}
_COMMAND: Final = {
    "grant": "access.grant_membership",
    "revoke": "access.revoke_membership",
    "list": "access.list_memberships",
}


def _scope_id(args: argparse.Namespace, ctx: CliContext) -> UUID:
    """The scope's id; the instance scope is found through the actor's own membership on it."""
    try:
        return UUID(str(ctx.resolve_scope(getattr(args, "scope", None)).id))
    except CapabilityUnavailable as error:
        if error.details.get("kind") != "instance":
            raise
    view = ctx.client.ask(access.WhoAmI())
    assert isinstance(view, access.WhoAmIView)  # noqa: S101 -- the bus validated the result
    for membership in view.memberships:
        if membership.scope_kind == "instance":
            return membership.scope_id
    raise NotFound(
        ErrorCode.NOT_FOUND,
        "the instance scope is known to its members only; pass --scope workspace:<uuid>",
        details={"kind": "scope"},
    )


def _grant(args: argparse.Namespace, ctx: CliContext) -> int:
    result = ctx.client.dispatch(
        access.GrantMembership.from_json(
            {
                "scope_id": str(_scope_id(args, ctx)),
                "principal_id": str(principal_ref(args.principal)),
                "role": args.role,
            }
        ),
        idempotency_key=ctx.new_idempotency_key(),
    )
    assert isinstance(result, access.GrantMembershipResult)  # noqa: S101 -- the bus validated the result
    return render(
        ctx,
        result,
        human=lambda value: f"granted {value.role.value} to {value.principal_id} on {value.scope_id}",
        command=args.command_name,
        essential=lambda value: str(value.principal_id),
    )


def _revoke(args: argparse.Namespace, ctx: CliContext) -> int:
    result = ctx.client.dispatch(
        access.RevokeMembership.from_json(
            {"scope_id": str(_scope_id(args, ctx)), "principal_id": str(principal_ref(args.principal))}
        ),
        idempotency_key=ctx.new_idempotency_key(),
    )
    assert isinstance(result, access.RevokeMembershipResult)  # noqa: S101 -- the bus validated the result
    return render(
        ctx,
        result,
        human=lambda value: "revoked" if value.removed else "no membership to revoke",
        command=args.command_name,
        essential=lambda value: str(value.principal_id),
    )


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    payload: JsonObject = {"limit": args.limit}
    if args.principal is None or getattr(args, "scope", None) is not None:
        payload["scope_id"] = str(_scope_id(args, ctx))  # a listing needs a scope or a principal
    if args.principal is not None:
        payload["principal_id"] = str(principal_ref(args.principal))
    if args.after is not None:
        payload["after"] = args.after
    view = ctx.client.ask(access.ListMemberships.from_json(payload))
    assert isinstance(view, access.ListMembershipsView)  # noqa: S101 -- the bus validated the result

    def human(value: access.ListMembershipsView) -> list[str]:
        rows = [
            [item.role.value, item.scope_kind, item.scope_id, item.principal_id, item.display_name]
            for item in value.items
        ]
        lines = render_table(ctx, ("role", "scope", "scope id", "principal", "name"), rows)
        if value.next is not None:
            lines.append(safe_text(ctx, f"next: {value.next} (use --after)"))
        return lines

    return render(
        ctx,
        view,
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(str(item.principal_id) for item in value.items),
    )


_RUN: Final = {"grant": _grant, "revoke": _revoke, "list": _list}


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("member", help="grant, revoke and list memberships")
    verbs = parser.add_subparsers(dest="member_verb", required=True)
    for verb in ("grant", "revoke", "list"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_RUN[verb], command_name=_COMMAND[verb])
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
            help="membership scope (default: the saved context)",
        )
        if verb == "grant":
            command.add_argument("principal", metavar="PRINCIPAL", help="principal uuid or principal:<uuid>")
            command.add_argument(
                "role", choices=("owner", "maintainer", "member", "viewer", "worker"), help="role to grant"
            )
        elif verb == "revoke":
            command.add_argument("principal", metavar="PRINCIPAL", help="principal uuid or principal:<uuid>")
        elif verb == "list":
            command.add_argument("--principal", metavar="REF", help="only memberships of this principal")
            command.add_argument(
                "--after", metavar="NEXT", help="continue from the next value of the previous page"
            )
            command.add_argument("--limit", type=int, default=50, metavar="N", help="page size (default 50)")


GROUP = CommandGroup("member", "grant, revoke and list memberships", register, module="access", order=40)
