"""Read-only analytics for recorded execution activity."""

import argparse
from typing import cast

from skm.entrypoints.cli._run_io import run_id
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import kv_lines, render
from skm.modules.execution.public import GetReviewRoi, ReviewRoiView

__all__ = ["GROUP", "register"]


def _review_roi(args: argparse.Namespace, ctx: CliContext) -> int:
    view = cast("ReviewRoiView", ctx.client.ask(GetReviewRoi(run_id(ctx, args.run_ref))))
    pairs = [
        ("Run", view.run_id),
        ("Completed agent reviews", view.completed_agent_reviews),
        ("Completed human reviews", view.completed_human_reviews),
        ("Unique findings", view.unique_findings),
        ("Resolved findings", view.resolved_findings),
        ("Rejected findings", view.rejected_findings),
        ("Finished reviewer steps", view.finished_reviewer_steps),
        (
            "Observed cost (USD)",
            view.observed_cost_usd if view.observed_cost_usd is not None else "unavailable",
        ),
        ("Steps with cost data", view.priced_reviewer_steps),
        (
            "Observed capture time (ms)",
            view.observed_duration_ms if view.observed_duration_ms is not None else "unavailable",
        ),
        ("Steps with capture time", view.timed_reviewer_steps),
    ]
    return render(
        ctx,
        view,
        command=args.command_name,
        human=lambda _: [
            *kv_lines(ctx, pairs),
            "Costs and time cover measured steps only. Review impact requires a labeled comparison sample.",
        ],
    )


def register(sub: SubParsers) -> None:
    group = sub.add_parser("analytics", help="inspect recorded execution outcomes and costs")
    verbs = group.add_subparsers(dest="verb", required=True)
    command = verbs.add_parser("review-roi", help="show observed review outcomes and costs for a run")
    command.add_argument("run_ref", metavar="RUN", help="run UUID, prefix, or 'last' for the current project")
    command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    command.set_defaults(run=_review_roi, command_name="execution.get_review_roi")


GROUP = CommandGroup(
    "analytics", "inspect recorded execution outcomes and costs", register, module="execution"
)
