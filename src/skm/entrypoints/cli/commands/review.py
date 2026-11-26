"""Request a review on this host or show its stored receipt."""

from __future__ import annotations

import argparse
from typing import Any

from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli._run_io import ask, operations, run_id, show
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.follow import follow
from skm.entrypoints.cli.host import build_host_context

__all__ = ["GROUP", "register"]

queries = operations("execution")
_HELP = {
    "request": "review an immutable range or the working tree",
    "show": "show verdict, findings and reviewed tree digest",
}
_COMMAND = {"request": "execution.host.request_review", "show": "execution.get_review_receipt"}


def _request(args: argparse.Namespace, ctx: CliContext) -> int:
    spec = next(
        op
        for manifest in MANIFESTS
        if manifest.id == "execution"
        for op in manifest.host_operations
        if op.name == _COMMAND["request"]
    )
    project_id = str(resolve_project_id(ctx, args.project))
    branch = None
    if args.base is None:
        branch = ask(
            ctx,
            operations("settings").GetValue,
            scope={"level": "project", "scope_id": project_id},
            key="execution.integration.branch",
        ).value
    result: Any = spec.run(
        build_host_context(ctx),
        {
            "project_id": project_id,
            "integration_branch": branch,
            "mount": args.mount,
            "base": args.base,
            "head": args.head,
            "working_tree": args.working_tree,
            "profile_key": args.profile,
            "reason": args.reason,
            "idempotency_key": ctx.new_idempotency_key(),
        },
    )
    if args.follow:
        code = follow(ctx, result["run_id"])
        if code:
            return code
        return show(ctx, _COMMAND["show"], ask(ctx, queries.GetReviewReceipt, run_id=result["run_id"]))
    return show(ctx, _COMMAND["request"], result)


def _show(args: argparse.Namespace, ctx: CliContext) -> int:
    return show(
        ctx, _COMMAND["show"], ask(ctx, queries.GetReviewReceipt, run_id=str(run_id(ctx, args.run_ref)))
    )


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("review", help="request a review or show its receipt")
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in ("request", "show"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        if verb == "request":
            command.add_argument("--project")
            command.add_argument("--mount", default="main")
            command.add_argument("--base")
            command.add_argument("--head")
            command.add_argument("--working-tree", action="store_true")
            command.add_argument("--profile", default="reviewer")
            command.add_argument("--reason", default="Owner requested review")
            command.add_argument("--follow", action="store_true")
            command.set_defaults(run=_request)
        else:
            command.add_argument("run_ref", metavar="RUN")
            command.set_defaults(run=_show)


GROUP = CommandGroup(name="review", help="request reviews and inspect receipts", register=register)
