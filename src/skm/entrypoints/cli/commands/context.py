"""Assemble, explain and compare project context manifests."""

import argparse
import json
from typing import cast

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import kv_lines, render
from skm.kernel.json_types import JsonObject
from skm.modules.context import public as context

__all__ = ["GROUP"]


def _assemble(args: argparse.Namespace, ctx: CliContext) -> int:
    command = context.AssembleContext.from_json(
        {
            "project_id": str(resolve_project_id(ctx, args.project)),
            "role": args.role,
            "runtime_id": args.runtime,
            "model": args.model,
            "context_window_tokens": args.context_window,
        }
    )
    result = cast(
        "context.AssembleContextResult",
        ctx.client.dispatch(command, idempotency_key=ctx.new_idempotency_key()),
    )
    return render(
        ctx,
        result,
        command=args.command_name,
        human=lambda value: kv_lines(
            ctx, [("manifest", value.manifest_id), ("draft digest", value.draft_digest)]
        ),
        essential=lambda value: str(value.manifest_id),
    )


def _explain(args: argparse.Namespace, ctx: CliContext) -> int:
    project = str(resolve_project_id(ctx, args.project))
    selector = "step_id" if args.step else "manifest_id"
    query = context.ExplainContextRequest.from_json({"project_id": project, selector: args.target})
    result = cast("context.ContextExplainResponse", ctx.client.ask(query))
    return render(ctx, result.to_json(), command=args.command_name, human=_human)


def _diff(args: argparse.Namespace, ctx: CliContext) -> int:
    project = str(resolve_project_id(ctx, args.project))
    selector = "step_id" if args.step else "target_manifest_id"
    query = context.DiffContextsRequest.from_json(
        {"project_id": project, "base_manifest_id": args.base, selector: args.target}
    )
    result = cast("context.ContextDiffResponse", ctx.client.ask(query))
    return render(ctx, result.to_json(), command=args.command_name, human=_human)


def _human(value: JsonObject) -> list[str]:
    return json.dumps(value, indent=2, ensure_ascii=False).splitlines()


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("context", help="assemble and inspect context manifests")
    verbs = parser.add_subparsers(dest="context_verb", required=True)
    assemble = verbs.add_parser("assemble", help="assemble a standalone context draft")
    assemble.add_argument("--project", help="project UUID or alias")
    assemble.add_argument(
        "--role",
        default="executor",
        choices=("scout", "executor", "reviewer", "triager", "advisor", "researcher", "registrar"),
        help="agent role (default executor)",
    )
    assemble.add_argument("--runtime", required=True, help="target runtime ID")
    assemble.add_argument("--model", required=True, help="target model")
    assemble.add_argument("--context-window", type=int, required=True, help="model context window in tokens")
    assemble.set_defaults(run=_assemble, command_name="context.assemble_context")

    explain = verbs.add_parser("explain", help="explain a manifest or step context")
    explain.add_argument("--project", help="project UUID or alias")
    explain.add_argument("target", help="manifest ID")
    explain.add_argument("--step", action="store_true", help="interpret target as a step ID")
    explain.set_defaults(run=_explain, command_name="context.explain_context")

    diff = verbs.add_parser("diff", help="compare two context manifests")
    diff.add_argument("--project", help="project UUID or alias")
    diff.add_argument("base", help="base manifest ID")
    diff.add_argument("target", help="target manifest ID")
    diff.add_argument("--step", action="store_true", help="interpret target as a step ID")
    diff.set_defaults(run=_diff, command_name="context.diff_contexts")


GROUP = CommandGroup(
    "context", "assemble and inspect context manifests", register, module="context", order=64
)
