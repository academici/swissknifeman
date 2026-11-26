"""Shared command transport for the two ad hoc CLI entry points."""

import argparse
from typing import cast

from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import kv_lines, render
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.execution import public as execution

__all__ = ["register_args", "start"]


def register_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("prompt", help="task instructions")
    parser.add_argument("--project", help="project UUID or alias")


def start(args: argparse.Namespace, ctx: CliContext, **fields: object) -> int:
    payload = {"project_id": str(resolve_project_id(ctx, args.project)), "prompt": args.prompt, **fields}
    if (work_kind := getattr(args, "work_kind", None)) is not None:
        payload["work_kind"] = work_kind
    try:
        dto = execution.RunAdhoc.from_json(cast("JsonObject", payload))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid ad hoc command or workflow") from exc
    result = cast(
        "execution.StartRunResult",
        ctx.client.dispatch(dto, idempotency_key=ctx.new_idempotency_key()),
    )
    return render(
        ctx,
        result,
        command=args.command_name,
        human=lambda value: kv_lines(ctx, [("run", value.run_id), ("status", value.status)]),
        essential=lambda value: str(value.run_id),
    )
