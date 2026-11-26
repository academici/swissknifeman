"""Resident first-turn budget estimates (cli §6.12, integrations §14)."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from typing import Any, cast

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.doctor import run_host_operation
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import render, render_table, safe_text
from skm.kernel.json_types import JsonObject
from skm.modules.integrations.public import TargetId

__all__ = ["GROUP", "add_parser", "register"]


COMMAND = "integrations.host.first_turn_budget"
HELP = "estimate all five resident first-turn sources"


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    payload: JsonObject = {
        "project_id": str(resolve_project_id(ctx, args.project)),
        "target": args.target,
        "include_plugins": False,
    }
    report = cast(
        "Mapping[str, Any]", run_host_operation(ctx, "integrations.host.first_turn_budget", payload)
    )

    def human(value: Mapping[str, Any]) -> list[str]:
        rows = [
            [source["kind"], "unknown" if source["tokens"] is None else source["tokens"], source["method"]]
            for source in value["sources"]
        ]
        lines = render_table(ctx, ("source", "estimated tokens", "method"), rows)
        lines.insert(
            0,
            safe_text(
                ctx,
                f"project: {value['project_id']}; target: {value['target']}; "
                f"include_plugins: {value.get('include_plugins', False)}",
            ),
        )
        lines.extend(
            safe_text(ctx, source["kind"] + ": " + json.dumps(source.get("detail", {}), sort_keys=True))
            for source in value["sources"]
        )
        total = "unknown" if value["total"] is None else value["total"]
        lines.append(
            safe_text(
                ctx,
                f"estimated total: {total}; verdict: {value['verdict']}; "
                f"target: {value['thresholds']['target']}; warn: {value['thresholds']['warn']}",
            )
        )
        return "\n".join(lines).splitlines()

    render(ctx, report, human=human, command="integrations.host.first_turn_budget")
    return int(args.strict and report["verdict"] in ("warn", "incomplete"))


def add_parser(sub: SubParsers) -> None:
    parser = sub.add_parser("budget", help=HELP)
    parser.set_defaults(run=_run, command_name=COMMAND)
    parser.add_argument("--project", default=None, help="project reference (defaults to active)")
    parser.add_argument(
        "--target", required=True, choices=[t.value for t in TargetId], help="integration target"
    )
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    parser.add_argument("--strict", action="store_true", help="exit 1 for warn or incomplete estimates")


def register(sub: SubParsers) -> None:
    add_parser(sub)


GROUP = CommandGroup(
    name="budget",
    help="estimate resident first-turn context tokens",
    register=register,
    module="integrations",
    order=87,
)
