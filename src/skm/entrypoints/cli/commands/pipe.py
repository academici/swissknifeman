"""Start an ad hoc task with a supplied ADR 0013 workflow."""

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue

from ._adhoc import register_args, start

__all__ = ["GROUP"]


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    try:
        source = sys.stdin.read() if args.workflow == "-" else Path(args.workflow).read_text(encoding="utf-8")
        workflow = cast("JsonValue", json.loads(source))
    except (OSError, ValueError) as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "cannot read workflow JSON") from exc
    if not isinstance(workflow, dict):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "workflow must be a JSON object")
    return start(args, ctx, workflow=workflow)


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("pipe", help="start an ad hoc task with a workflow")
    parser.add_argument("workflow", help="ADR 0013 workflow JSON file or - for stdin")
    register_args(parser)
    parser.add_argument(
        "--work-kind",
        choices=("research", "code", "docs", "config", "test", "review", "ops"),
        help="work kind accepted by the workflow (default research)",
    )
    parser.set_defaults(run=_run, command_name="execution.run_adhoc")


GROUP = CommandGroup("pipe", "start an ad hoc task with a workflow", register, module="execution", order=63)
