"""Research CLI: parse, resolve scope, invoke the host operation, render."""

from __future__ import annotations

import argparse
from typing import Any, cast

from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_view
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.host import build_host_context
from skm.entrypoints.cli.output import kv_lines, render, render_error, render_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, error_for
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.context import public as context

__all__ = ["GROUP", "query_spec", "register", "run_host_research"]

_COMMAND = {
    "query": "context.host.research_query",
    "sources": "context.host.research_query",
    "show": "context.get_research_query",
}
_HELP = {
    "query": "query configured research sources on this host",
    "sources": "list configured host research sources",
    "show": "inspect a stored research query",
}


def query_spec(args: argparse.Namespace) -> JsonObject:
    return {
        "text": args.text,
        "sources": args.source or [],
        "depth": "deep" if args.deep else "standard",
        "max_documents": args.max_documents,
        "use_cache": not args.no_cache,
        "save_as_material": args.save_as_material,
    }


def run_host_research(ctx: CliContext, request: JsonObject) -> dict[str, Any]:
    operation = next(
        (
            op
            for manifest in MANIFESTS
            if manifest.id == "context"
            for op in manifest.host_operations
            if op.name == "context.host.research_query" and Surface.CLI in op.surfaces
        ),
        None,
    )
    if operation is None:
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE, "Research host operation is unavailable"
        )
    return cast("dict[str, Any]", operation.run(build_host_context(ctx), request))


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    if args.research_action == "show":
        project = resolve_project_view(ctx, args.project)
        result = ctx.client.ask(
            context.GetResearchQuery.from_json(
                {"project_id": str(project.project_id), "query_id": args.query_id}
            )
        )
        return render(
            ctx, result, human=lambda value: kv_lines(ctx, list(value.items())), command=_COMMAND["show"]
        )
    request: JsonObject = {"action": args.research_action}
    if args.research_action != "sources":
        project = resolve_project_view(ctx, args.project)
        request.update({"workspace_id": str(project.workspace_id), "project_id": str(project.project_id)})
    if args.research_action == "query":
        request["spec"] = query_spec(args)
    result = run_host_research(ctx, request)
    if args.research_action == "sources":
        return render(
            ctx,
            result,
            human=lambda value: render_table(
                ctx,
                ("order", "id", "kind", "tier", "capabilities"),
                [
                    [s["order"], s["id"], s["kind"], s["tier"], ", ".join(s["capabilities"])]
                    for s in value["sources"]
                ],
            ),
            command=_COMMAND[args.research_action],
        )
    if args.research_action == "query" and (
        not result["results"] or all(item["status"] == "error" for item in result["results"])
    ):
        render_error(
            ctx,
            error_for(
                ErrorCode.RESEARCH_SOURCE_UNAVAILABLE,
                "All research sources failed",
                details={"results": result["results"]},
            ),
            command=_COMMAND[args.research_action],
        )
        return 1
    render(
        ctx,
        result,
        human=lambda value: kv_lines(ctx, list(value.items())),
        command=_COMMAND[args.research_action],
    )
    return 0


def register(sub: SubParsers) -> None:
    group = sub.add_parser("research", help="query and inspect host research sources")
    commands = group.add_subparsers(dest="research_action", required=True)
    for verb in ("query", "sources", "show"):
        command = commands.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_run, command_name=_COMMAND[verb])
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if verb != "sources":
            command.add_argument("--project", default=None, help="project reference (defaults to active)")
        if verb == "query":
            command.add_argument("text", help="research query text")
            command.add_argument("--source", action="append", help="source id (repeatable)")
            command.add_argument("--deep", action="store_true", help="allow configured deep research")
            command.add_argument("--max-documents", type=int, default=10, help="maximum documents per source")
            command.add_argument("--no-cache", action="store_true", help="bypass research cache")
            command.add_argument(
                "--save-as-material", action="store_true", help="capture retrieved documents"
            )
        if verb == "show":
            command.add_argument("query_id", help="stored research query id")


GROUP = CommandGroup(
    name="research",
    help="host research sources and provenance",
    register=register,
    module="context",
    order=87,
)
