"""``skm token`` (cli §6, access §14): create, list, rotate and revoke credentials through ``access.public``.

``create`` and ``rotate`` print the new secret once, with a warning, or write it to ``--save PATH`` (0600) and
print the path instead; ``list`` and ``revoke`` never show a secret. A token reference is ``token:<uuid>``, a
uuid, or the name of one of the caller's own active tokens. Rights are the bus's decision (``token.own`` for
the caller's own credentials, ``token.any`` for another principal's), taken against the stored credential.
"""

import argparse
import re
from datetime import timedelta
from pathlib import Path
from typing import Final, cast
from uuid import UUID

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.principal import principal_ref
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import render, render_table, safe_text, to_jsonable
from skm.entrypoints.cli.refs import RefForm, RefKind, parse_ref
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, SkmError, ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.access import public as access
from skm.platform.fs.atomic_write import UnsafePathError, atomic_write
from skm.platform.system_clock import SystemClock

__all__ = ["GROUP", "duration", "register"]

_HELP: Final = {
    "create": "create a token for yourself or, with token.any, for another principal",
    "list": "list tokens of yourself or of another principal",
    "rotate": "replace a token by a new secret; the old one works for the grace period",
    "revoke": "revoke a token",
}
_COMMAND: Final = {
    "create": "access.create_token",
    "list": "access.list_tokens",
    "rotate": "access.rotate_token",
    "revoke": "access.revoke_token",
}
_DURATION: Final = re.compile(r"(\d+)([smhd])")
_UNITS: Final = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
_WARNING: Final = "this secret is shown once; store it now, it cannot be read again"
_PAGE: Final = 200


def duration(text: str) -> timedelta:
    """``30d``, ``12h``, ``90m`` or ``45s``; anything else is ``SCHEMA_INVALID`` before a request is made."""
    found = _DURATION.fullmatch(text)
    if found is None or int(found.group(1)) == 0:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "expected a positive duration such as 30d, 12h, 90m or 45s",
            details={"field": "expires_in"},
        )
    try:
        return timedelta(**{_UNITS[found.group(2)]: int(found.group(1))})
    except OverflowError:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "the duration is too long", details={"field": "expires_in"}
        ) from None


def _scope_id(args: argparse.Namespace, ctx: CliContext) -> UUID | None:
    """The token's own scope: only an explicit ``--scope`` narrows it (the saved context is not applied)."""
    if getattr(args, "scope", None) is None:
        return None
    return UUID(str(ctx.resolve_scope(args.scope).id))


def _token_id(ctx: CliContext, text: str) -> UUID:
    ref = parse_ref(RefKind.TOKEN, text)
    if ref.form is RefForm.UUID and ref.uuid is not None:
        return ref.uuid
    after: str | None = None
    while True:  # a name means one of the caller's own active tokens
        payload: JsonObject = {"limit": _PAGE}
        if after is not None:
            payload["after"] = after
        page = ctx.client.ask(access.ListTokens.from_json(payload))
        assert isinstance(page, access.ListTokensView)  # noqa: S101 -- the bus validated the result
        for item in page.items:
            if item.name == ref.text and item.state == "active":
                return item.token_id
        if page.next is None:
            raise NotFound(
                ErrorCode.NOT_FOUND, "no active token of yours has this name", details={"kind": "token"}
            )
        after = page.next


def _revealed(
    ctx: CliContext, args: argparse.Namespace, result: object, *, replace: bool
) -> tuple[JsonObject, str | None]:
    """The result document for output and the path the secret was saved to, if ``--save`` was given.

    The secret leaves the document when it was saved; a failed save keeps it there so it is not lost.
    """
    document = cast("JsonObject", to_jsonable(result))
    if args.save is None:
        return document, None
    path = Path(args.save)
    try:
        if path.exists() and not replace:
            raise FileExistsError(str(path))
        atomic_write(path, (str(document["secret"]) + "\n").encode(), mode=0o600, private=True)
    except (OSError, SkmError, UnsafePathError) as error:
        # The token already exists: every refusal keeps the secret in the output instead of losing it.
        if isinstance(error, UnsafePathError):
            reason = f"unsafe path ({error.reason})"
        else:
            reason = error.strerror if isinstance(error, OSError) else error.code.value
        ctx.stderr.write(
            safe_text(ctx, f"warning: cannot save the secret to {path}: {reason or 'error'}") + "\n"
        )
        return document, None
    document.pop("secret")
    document["saved_to"] = str(path)
    return document, str(path)


def _secret_lines(document: JsonObject, saved: str | None) -> list[str]:
    rows: list[tuple[str, object]] = [("token", document["token_id"]), ("prefix", document["prefix"])]
    rows.append(("expires", document["expires_at"] or "never"))
    lines = [f"{label}  {value}" for label, value in rows]
    if saved is not None:
        return [*lines, f"secret saved to {saved}"]
    return [*lines, f"secret  {document['secret']}", f"warning: {_WARNING}"]


def _create(args: argparse.Namespace, ctx: CliContext) -> int:
    expires = None if args.expires_in is None else SystemClock().now() + duration(args.expires_in)
    payload: JsonObject = {
        "name": args.name,
        "principal_id": None if args.principal is None else str(principal_ref(args.principal)),
        "scope_id": None if (scope := _scope_id(args, ctx)) is None else str(scope),
        "permissions": list(args.permission) if args.permission else None,
        "expires_at": None if expires is None else expires.isoformat(),
    }
    result = ctx.client.dispatch(access.CreateToken.from_json(payload))
    assert isinstance(result, access.CreateTokenResult)  # noqa: S101 -- the bus validated the result
    document, saved = _revealed(ctx, args, result, replace=False)
    return render(
        ctx,
        document,
        human=lambda value: _secret_lines(value, saved),
        command=args.command_name,
        essential=lambda value: str(value.get("secret", value["token_id"])),
    )


def _rotate(args: argparse.Namespace, ctx: CliContext) -> int:
    payload: JsonObject = {"token_id": str(_token_id(ctx, args.token))}
    if args.grace_minutes is not None:
        payload["grace_minutes"] = args.grace_minutes
    result = ctx.client.dispatch(access.RotateToken.from_json(payload))
    assert isinstance(result, access.RotateTokenResult)  # noqa: S101 -- the bus validated the result
    document, saved = _revealed(ctx, args, result, replace=True)

    def human(value: JsonObject) -> list[str]:
        until = value["previous_expires_at"] or "it is revoked"
        old = f"previous token {value['previous_token_id']} works until {until}"
        return [*_secret_lines(value, saved), old]

    return render(
        ctx,
        document,
        human=human,
        command=args.command_name,
        essential=lambda value: str(value.get("secret", value["token_id"])),
    )


def _revoke(args: argparse.Namespace, ctx: CliContext) -> int:
    result = ctx.client.dispatch(
        access.RevokeToken(token_id=_token_id(ctx, args.token)), idempotency_key=ctx.new_idempotency_key()
    )
    assert isinstance(result, access.RevokeTokenResult)  # noqa: S101 -- the bus validated the result
    return render(
        ctx,
        result,
        human=lambda value: f"revoked token {value.token_id}",
        command=args.command_name,
        essential=lambda value: str(value.token_id),
    )


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    payload: JsonObject = {"include_inactive": args.include_revoked, "limit": args.limit}
    if args.principal is not None:
        payload["principal_id"] = str(principal_ref(args.principal))
    if args.after is not None:
        payload["after"] = args.after
    view = ctx.client.ask(access.ListTokens.from_json(payload))
    assert isinstance(view, access.ListTokensView)  # noqa: S101 -- the bus validated the result

    def human(value: access.ListTokensView) -> list[str]:
        rows = [
            [
                item.name,
                item.token_id,
                item.scope_id or "instance",
                item.expires_at.isoformat() if item.expires_at else "never",
                item.last_used_at.isoformat() if item.last_used_at else "-",
                item.state,
            ]
            for item in value.items
        ]
        lines = render_table(ctx, ("name", "id", "scope", "expires", "last used", "state"), rows)
        if value.next is not None:
            lines.append(safe_text(ctx, f"next: {value.next} (use --after)"))
        return lines

    return render(
        ctx,
        view,
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(str(item.token_id) for item in value.items),
    )


_RUN: Final = {"create": _create, "list": _list, "rotate": _rotate, "revoke": _revoke}


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("token", help="create, list, rotate and revoke API tokens")
    verbs = parser.add_subparsers(dest="token_verb", required=True)
    for verb in ("create", "list", "rotate", "revoke"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_RUN[verb], command_name=_COMMAND[verb])
        command.add_argument(
            "--json",
            default=argparse.SUPPRESS,
            action="store_true",
            help="machine-readable output (as global --json)",
        )
        if verb == "create":
            command.add_argument("name", help="token name")
            command.add_argument(
                "--principal",
                metavar="REF",
                help="owner of the token (default: yourself; token.any for others)",
            )
            command.add_argument(
                "--scope", default=argparse.SUPPRESS, metavar="SCOPE", help="scope the token is limited to"
            )
            command.add_argument(
                "--permission",
                action="append",
                default=[],
                metavar="PERMISSION",
                help="narrow the token to this permission (repeatable)",
            )
            command.add_argument("--expires-in", metavar="DURATION", help="lifetime such as 30d or 12h")
            command.add_argument(
                "--save", metavar="PATH", help="write the secret to this file (0600), not stdout"
            )
        elif verb == "list":
            command.add_argument(
                "--principal", metavar="REF", help="list tokens of this principal (default: yourself)"
            )
            command.add_argument("--include-revoked", action="store_true", help="also list revoked tokens")
            command.add_argument(
                "--after", metavar="NEXT", help="continue from the next value of the previous page"
            )
            command.add_argument("--limit", type=int, default=50, metavar="N", help="page size (default 50)")
        elif verb == "rotate":
            command.add_argument(
                "token", metavar="TOKEN", help="token uuid, token:<uuid> or the name of your own active token"
            )
            command.add_argument(
                "--grace-minutes",
                type=int,
                metavar="N",
                help="minutes the old secret keeps working (default access.tokens.rotation_grace_minutes)",
            )
            command.add_argument(
                "--save", metavar="PATH", help="write the secret to this file (0600), not stdout"
            )
        elif verb == "revoke":
            command.add_argument(
                "token", metavar="TOKEN", help="token uuid, token:<uuid> or the name of your own active token"
            )


GROUP = CommandGroup(
    "token", "create, list, rotate and revoke API tokens", register, module="access", order=40
)
