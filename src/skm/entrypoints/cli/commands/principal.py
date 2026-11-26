"""``skm principal`` (cli §6, access §14): create, list, show and disable principals via ``access.public``.

The surface sends the commands of the owner module and prints what the bus returns; who may do it is the
bus's decision (``principal.manage``), made against the stored principal and memberships of the acting
credential. A principal reference is a UUID or ``principal:<uuid>``.
"""

import argparse
from typing import Final
from uuid import UUID

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import kv_lines, render, render_table, safe_text
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.kernel.pagination import Cursor, Page
from skm.modules.access import public as access

__all__ = ["GROUP", "principal_ref", "register"]

_HELP: Final = {
    "create": "create a principal (human, service or worker)",
    "list": "list principals",
    "show": "show one principal",
    "disable": "disable a principal; its credentials stop working",
}
_COMMAND: Final = {
    "create": "access.create_principal",
    "list": "access.list_principals",
    "show": "access.get_principal",
    "disable": "access.disable_principal",
}
_PREFIX: Final = "principal:"


def principal_ref(text: str) -> UUID:
    """``<uuid>`` or ``principal:<uuid>``; names are not unique, so nothing else is accepted."""
    raw = text.removeprefix(_PREFIX)
    try:
        return UUID(raw)
    except ValueError:
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            f'"{text.replace(chr(34), chr(39))}" is not a principal reference (expected principal:<uuid>)',
            details={"kind": "principal", "expected": "principal:<uuid>"},
        ) from None


def _create(args: argparse.Namespace, ctx: CliContext) -> int:
    result = ctx.client.dispatch(
        access.CreatePrincipal.from_json({"kind": args.kind, "display_name": args.name, "identity": None}),
        idempotency_key=ctx.new_idempotency_key(),
    )
    assert isinstance(result, access.CreatePrincipalResult)  # noqa: S101 -- the bus validated the result
    return render(
        ctx,
        result,
        human=lambda value: f"created principal {value.principal_id}",
        command=args.command_name,
        essential=lambda value: str(value.principal_id),
    )


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    payload: JsonObject = {"limit": args.limit, "after": args.after, "kind": args.kind}
    view = ctx.client.ask(
        access.ListPrincipals.from_json({k: v for k, v in payload.items() if v is not None})
    )
    assert isinstance(view, access.ListPrincipalsView)  # noqa: S101 -- the bus validated the result
    page = Page(items=view.items, next=None if view.next is None else Cursor(view.next))

    def human(value: Page[access.PrincipalSummaryView]) -> list[str]:
        rows = [[item.principal_id, item.kind.value, item.state, item.display_name] for item in value.items]
        lines = render_table(ctx, ("id", "kind", "state", "name"), rows)
        if value.next is not None:
            lines.append(safe_text(ctx, f"next: {value.next} (use --after)"))
        return lines

    return render(
        ctx,
        view,
        human=lambda _: human(page),
        command=args.command_name,
        essential=lambda _: "\n".join(str(item.principal_id) for item in page.items),
    )


def _show(args: argparse.Namespace, ctx: CliContext) -> int:
    view = ctx.client.ask(access.GetPrincipal(principal_id=principal_ref(args.principal)))
    assert isinstance(view, access.GetPrincipalView)  # noqa: S101 -- the bus validated the result

    def human(value: access.GetPrincipalView) -> list[str]:
        pairs: list[tuple[str, object]] = [
            ("id", value.principal_id),
            ("name", value.display_name),
            ("kind", value.kind.value),
            ("state", value.state),
            ("created", value.created_at.isoformat()),
            ("version", value.row_version),
        ]
        pairs.extend(("identity", f"{item.issuer}:{item.subject}") for item in value.identities)
        return kv_lines(ctx, pairs)

    return render(
        ctx, view, human=human, command=args.command_name, essential=lambda value: str(value.principal_id)
    )


def _disable(args: argparse.Namespace, ctx: CliContext) -> int:
    target = principal_ref(args.principal)
    current = ctx.client.ask(access.GetPrincipal(principal_id=target))
    assert isinstance(current, access.GetPrincipalView)  # noqa: S101 -- the bus validated the result
    result = ctx.client.dispatch(
        access.DisablePrincipal(
            principal_id=target, expected_row_version=current.row_version, reason=args.reason
        ),
        idempotency_key=ctx.new_idempotency_key(),
    )
    assert isinstance(result, access.DisablePrincipalResult)  # noqa: S101 -- the bus validated the result
    return render(
        ctx,
        result,
        human=lambda value: f"disabled principal {value.principal_id}",
        command=args.command_name,
        essential=lambda value: str(value.principal_id),
    )


_RUN: Final = {"create": _create, "list": _list, "show": _show, "disable": _disable}


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("principal", help="create, list, show and disable principals")
    verbs = parser.add_subparsers(dest="principal_verb", required=True)
    for verb in ("create", "list", "show", "disable"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_RUN[verb], command_name=_COMMAND[verb])
        command.add_argument(
            "--json",
            default=argparse.SUPPRESS,
            action="store_true",
            help="machine-readable output (as global --json)",
        )
        if verb == "create":
            command.add_argument("name", help="display name")
            command.add_argument(
                "--kind",
                choices=("human", "service", "worker"),
                default="human",
                help="principal kind (default human)",
            )
        elif verb == "list":
            command.add_argument(
                "--kind", choices=("human", "service", "worker"), help="only principals of this kind"
            )
            command.add_argument(
                "--after", metavar="NEXT", help="continue from the next value of the previous page"
            )
            command.add_argument("--limit", type=int, default=50, metavar="N", help="page size (default 50)")
        elif verb == "show":
            command.add_argument("principal", metavar="PRINCIPAL", help="principal uuid or principal:<uuid>")
        elif verb == "disable":
            command.add_argument("principal", metavar="PRINCIPAL", help="principal uuid or principal:<uuid>")
            command.add_argument("--reason", default="", help="reason recorded in the audit trail")


GROUP = CommandGroup(
    "principal", "create, list, show and disable principals", register, module="access", order=40
)
