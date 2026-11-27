"""Shared command transport for the two ad hoc CLI entry points."""

import argparse
from typing import cast
from uuid import UUID

from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.output import kv_lines, render
from skm.entrypoints.cli.refs import as_uuid
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.execution import public as execution

__all__ = ["register_args", "start"]


def register_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("prompt", help="task instructions")
    parser.add_argument("--project", help="project UUID or alias")
    parser.add_argument(
        "--dry-run", dest="host_local", action="store_true", help="preview the request offline"
    )


def _dto(args: argparse.Namespace, project: UUID, fields: dict[str, object]) -> execution.RunAdhoc:
    payload = {"project_id": str(project), "prompt": args.prompt, **fields}
    if (work_kind := getattr(args, "work_kind", None)) is not None:
        payload["work_kind"] = work_kind
    try:
        return execution.RunAdhoc.from_json(cast("JsonObject", payload))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid ad hoc command or workflow") from exc


def _preview(args: argparse.Namespace, ctx: CliContext, fields: dict[str, object]) -> int:
    raw: str = (
        args.project
        or (ctx.environ.get("SKM_PROJECT") if isinstance(ctx, CliSession) else None)
        or "current project"
    )
    project = as_uuid(raw.removeprefix("project:").removeprefix("proj:"))
    payload = _dto(args, project if project is not None else UUID(int=0), fields).to_json()
    if project is None:
        payload["project_id"] = None
    result = {
        "project_ref": str(project) if project is not None else f"{raw} (unresolved in offline dry-run)",
        "slot": "deferred (resolved by control-plane worker at claim time)",
        "payload": payload,
    }
    return render(ctx, result, command=args.command_name, human=lambda value: kv_lines(ctx, value.items()))


def start(args: argparse.Namespace, ctx: CliContext, **fields: object) -> int:
    if getattr(args, "host_local", False):
        return _preview(args, ctx, fields)
    dto = _dto(args, resolve_project_id(ctx, args.project), fields)
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
