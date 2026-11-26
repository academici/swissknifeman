"""Inspect learning evidence and record human curation decisions."""

import argparse
from typing import Any

from skm.entrypoints.cli._run_io import ask, dispatch
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_view
from skm.entrypoints.cli.commands.workspace import resolve_workspace_id
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import kv_lines, render
from skm.entrypoints.cli.refs import as_uuid
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.modules.learning import public as learning

__all__ = ["GROUP", "register"]

_STATES = ("observed", "candidate", "promoted", "rejected", "deprecated")
_HELP = {
    "candidates": "list lesson candidates",
    "show": "inspect a candidate and its evidence",
    "review": "record a candidate review",
    "promote": "create a lesson from a candidate",
    "recompute": "recompute source association",
    "stats": "inspect pathology frequencies",
}
_OPERATIONS = {
    "candidates": learning.ListCandidates,
    "show": learning.GetCandidate,
    "review": learning.ReviewCandidate,
    "promote": learning.PromoteCandidate,
    "recompute": learning.RecomputeConfidence,
    "stats": learning.PathologyStats,
}


def _candidate_id(ctx: CliContext, workspace: str, project: str | None, ref: str) -> str:
    if (candidate_id := as_uuid(ref.removeprefix("candidate:"))) is not None:
        return str(candidate_id)
    if not ref.startswith("LC-") or not ref[3:].isascii() or not ref[3:].isdigit():
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "Expected a candidate UUID or LC display key")
    if project is None:
        view = resolve_project_view(ctx, workspace_ref=workspace)
        project = str(view.project_id)
    after = None
    while True:
        page = ask(
            ctx,
            learning.ListCandidates,
            workspace_id=workspace,
            project_id=project,
            states=list(_STATES),
            after=after,
        )
        if (match := next((row for row in page["items"] if row["display_key"] == ref), None)) is not None:
            return str(match["candidate_id"])
        after = page["next_cursor"]
        if after is None:
            raise NotFound(ErrorCode.NOT_FOUND, "Candidate not found")


def _review(
    ctx: CliContext, args: argparse.Namespace, path: dict[str, str], candidate: dict[str, Any]
) -> Any:
    return dispatch(
        ctx,
        _OPERATIONS["review"],
        **path,
        expected_row_version=args.expected_version
        if args.expected_version is not None
        else candidate["row_version"],
        verdict=args.verdict,
        note=args.note,
        edited_trigger=args.trigger,
        edited_action=args.action,
        edited_kind=args.kind,
        proposal_id=args.proposal,
    )


def _promote(
    ctx: CliContext, args: argparse.Namespace, path: dict[str, str], candidate: dict[str, Any]
) -> Any:
    if not (args.yes or ctx.assume_yes):
        fields = (
            ("trigger", candidate["trigger"]),
            ("action", candidate["action"]),
            ("source association", candidate["confidence"]),
        )
        for line in kv_lines(ctx, fields):
            ctx.stderr.write(line + "\n")
        if not ctx.confirm(f"Promote {candidate['display_key']}?"):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Promotion requires confirmation")
    return dispatch(
        ctx,
        _OPERATIONS["promote"],
        **path,
        expected_row_version=args.expected_version
        if args.expected_version is not None
        else candidate["row_version"],
        override_low_confidence=args.override_low_confidence,
        override_reason=args.reason,
        resolve_conflict=args.resolve_conflict,
        supersedes_lesson_id=args.supersedes_lesson_id,
    )


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    operation = _OPERATIONS[args.verb]
    project = (
        resolve_project_view(ctx, args.project, workspace_ref=args.workspace)
        if args.project or args.verb == "stats"
        else None
    )
    project_id = str(project.project_id) if project else None
    if args.verb == "stats":
        result = ask(ctx, operation, project_id=project_id, window=args.window)
    else:
        workspace = str(
            project.workspace_id
            if project and not args.workspace
            else resolve_workspace_id(ctx, args.workspace)
        )
        if args.verb == "candidates":
            result = ask(
                ctx,
                operation,
                workspace_id=workspace,
                project_id=project_id,
                states=args.state,
                detector=args.detector,
                min_tier=args.min_tier,
                after=args.after,
                limit=args.limit,
            )
        elif args.verb == "recompute":
            result = dispatch(
                ctx,
                operation,
                workspace_id=workspace,
                project_id=project_id,
                batch=args.batch,
            )
        else:
            path = {
                "workspace_id": workspace,
                "candidate_id": _candidate_id(ctx, workspace, project_id, args.ref),
            }
            candidate = ask(ctx, _OPERATIONS["show"], **path)
            if project_id and candidate["project_id"] != project_id:
                raise NotFound(ErrorCode.NOT_FOUND, "Candidate not found")
            if args.verb == "show":
                result = {**candidate, "signals": ask(ctx, learning.ListSignals, **path)}
            elif args.verb == "review":
                result = _review(ctx, args, path, candidate)
            else:
                result = _promote(ctx, args, path, candidate)

    def human(value: dict[str, Any]) -> list[str]:
        labels = {"confidence": "source association", "confidence_tier": "source association tier"}
        lines = [
            line
            for row in value.get("items", [value])
            for line in kv_lines(ctx, [(labels.get(str(key), str(key)), val) for key, val in row.items()])
        ]
        if value.get("next_cursor"):
            lines.extend(kv_lines(ctx, [("next", value["next_cursor"])]))
        return lines or ["no candidates"]

    return render(ctx, result, command=args.command_name, human=human)


def _detector(value: str) -> str:
    return {
        "A": "resolved_failure",
        "B": "workaround",
        "C": "pathology",
        "D": "workflow_relaunch",
    }.get(value, value)


def register(sub: SubParsers) -> None:
    group = sub.add_parser("learning", help=GROUP.help)
    verbs = group.add_subparsers(dest="verb", required=True)
    for verb, operation in _OPERATIONS.items():
        command = verbs.add_parser(verb, help=_HELP[verb])
        name = operation.SCHEMA_URN.split(":")[-2].replace("-", "_")
        command.set_defaults(run=_run, command_name="learning." + name)
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        command.add_argument("--workspace")
        command.add_argument("--project")
        if verb in ("show", "review", "promote"):
            command.add_argument("ref")
        if verb in ("review", "promote"):
            command.add_argument("--expected-version", type=int)
        if verb == "candidates":
            command.add_argument(
                "--state",
                choices=("observed", "candidate", "promoted", "rejected", "deprecated"),
                action="append",
            )
            command.add_argument(
                "--detector",
                type=_detector,
                choices=("resolved_failure", "workaround", "pathology", "workflow_relaunch"),
            )
            command.add_argument("--min-tier", choices=("none", "tentative", "moderate", "strong", "core"))
            command.add_argument("--after")
            command.add_argument("--limit", type=int, default=50)
        if verb == "review":
            decisions = command.add_mutually_exclusive_group(required=True)
            for flag in ("--approve", "--reject", "--edit", "--comment"):
                decisions.add_argument(flag, action="store_const", dest="verdict", const=flag[2:])
            command.add_argument("--note")
            command.add_argument("--trigger")
            command.add_argument("--action")
            command.add_argument("--kind", choices=("heuristic", "procedure", "gotcha"))
            command.add_argument("--proposal")
        if verb == "promote":
            command.add_argument("--override-low-confidence", action="store_true")
            command.add_argument("--reason")
            command.add_argument("--resolve-conflict", choices=("supersede", "keep_both"))
            command.add_argument("--supersedes-lesson-id")
            command.add_argument("--yes", action="store_true")
        if verb == "recompute":
            command.add_argument("--batch", type=int, default=500)
        if verb == "stats":
            command.add_argument("--window", type=int, default=20)


GROUP = CommandGroup("learning", "inspect and curate lesson candidates", register, module="learning")
