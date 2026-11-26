"""Outbox operator commands; reads and writes use the platform bus DTOs."""

import argparse

from skm.entrypoints.cli._run_io import ask, dispatch, identifier, show
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext
from skm.platform.generated.commands import RetryOutbox
from skm.platform.generated.queries import ListDeadOutbox

_HELP = {"dead": "list dead outbox deliveries", "retry": "requeue dead deliveries of an event"}


def _dead(args: argparse.Namespace, ctx: CliContext) -> int:
    return show(
        ctx, "platform.list_dead_outbox", ask(ctx, ListDeadOutbox, after=args.after, limit=args.limit)
    )


def _retry(args: argparse.Namespace, ctx: CliContext) -> int:
    return show(
        ctx,
        "platform.retry_outbox",
        dispatch(
            ctx, RetryOutbox, event_id=str(identifier(args.event, "event")), destination=args.destination
        ),
    )


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("events", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in ("dead", "retry"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if verb == "dead":
            command.add_argument("--limit", type=int, default=50)
            command.add_argument("--after")
            command.set_defaults(run=_dead)
        if verb == "retry":
            command.add_argument("event")
            command.add_argument("--destination")
            command.set_defaults(run=_retry)
        command.set_defaults(
            command_name="platform." + {"dead": "list_dead_outbox", "retry": "retry_outbox"}[verb]
        )


GROUP = CommandGroup(
    name="events", help="inspect and retry dead outbox deliveries", register=register, order=90
)

__all__ = ["GROUP"]
