"""Inspect curated lessons and deprecate a reviewed version."""

import argparse
from typing import Any

from skm.entrypoints.cli._run_io import ask, dispatch, identifier
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.memory import read_pages
from skm.entrypoints.cli.commands.project import resolve_project_view
from skm.entrypoints.cli.commands.workspace import resolve_workspace_id
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import kv_lines, render
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.knowledge import public as knowledge

__all__ = ["GROUP", "register"]

_HELP = {
    "list": "list workspace lessons",
    "show": "inspect a lesson and its evidence",
    "deprecate": "deprecate a reviewed lesson version",
}
_OPERATIONS = {
    "list": knowledge.ListLessons,
    "show": knowledge.GetLesson,
    "deprecate": knowledge.DeprecateLesson,
}
_WRITES = frozenset({"deprecate"})


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    project = (
        resolve_project_view(ctx, args.project, workspace_ref=args.workspace)
        if getattr(args, "project", None)
        else None
    )
    workspace = str(
        project.workspace_id if project and not args.workspace else resolve_workspace_id(ctx, args.workspace)
    )
    if args.verb == "list":
        result = read_pages(
            ctx,
            args.operation,
            args,
            workspace_id=workspace,
            project_id=str(project.project_id) if project else None,
            kind=args.kind,
            state=args.state,
        )
    else:
        lesson = str(identifier(args.ref, "lesson"))
        if args.verb not in _WRITES:
            result = ask(ctx, args.operation, workspace_id=workspace, lesson_id=lesson)
        else:
            if not (args.yes or ctx.assume_yes or ctx.confirm(f"Deprecate lesson {lesson}?")):
                raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Deprecation requires confirmation")
            result = dispatch(
                ctx,
                args.operation,
                workspace_id=workspace,
                lesson_id=lesson,
                reason=args.reason,
                expected_row_version=args.expected_version,
            )

    def human(value: dict[str, Any]) -> list[str]:
        rows = value.get("items", [value])
        lines: list[str] = []
        for row in rows:
            fields: dict[str, Any] = dict(row)
            if "confidence" in fields:
                fields["freshness"] = fields.get("freshness", "unknown")
                fields["potential_conflict_ids"] = fields.get("potential_conflict_ids", "unknown")
            labels = {"confidence": "source association", "confidence_tier": "source association tier"}
            lines.extend(kv_lines(ctx, [(labels.get(key, key), val) for key, val in fields.items()]))
        if value.get("next_cursor"):
            lines.extend(kv_lines(ctx, [("next", value["next_cursor"])]))
        return lines or ["no lessons"]

    return render(ctx, result, command=args.command_name, human=human)


def register(sub: SubParsers) -> None:
    group = sub.add_parser("lessons", help=GROUP.help)
    verbs = group.add_subparsers(dest="verb", required=True)
    for verb, operation in _OPERATIONS.items():
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--workspace")
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if verb == "list":
            command.add_argument("--project")
            command.add_argument("--state", choices=("curated", "deprecated"))
            command.add_argument("--kind", choices=("heuristic", "procedure", "gotcha"))
            command.add_argument("--after")
            command.add_argument("--limit", type=int, default=50)
            command.add_argument("--all", action="store_true")
        if verb in ("show", "deprecate"):
            command.add_argument("ref")
        if verb == "deprecate":
            command.add_argument("--reason", required=True)
            command.add_argument("--expected-version", required=True, type=int)
            command.add_argument("--yes", action="store_true")
        operation_name = operation.SCHEMA_URN.split(":")[-2].replace("-", "_")
        command.set_defaults(run=_run, command_name="knowledge." + operation_name, operation=operation)


GROUP = CommandGroup("lessons", "inspect and curate lessons", register, module="knowledge")
