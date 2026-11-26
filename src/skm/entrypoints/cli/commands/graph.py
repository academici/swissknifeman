"""Manage a native CodeGraph index or inspect the optional knowledge graph."""

import argparse
from typing import Any, cast
from uuid import UUID

from skm.bootstrap.composition import knowledge_wiring
from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_id, resolve_project_view
from skm.entrypoints.cli.commands.workspace import resolve_workspace_id
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import kv_lines, render, render_table, safe_text
from skm.kernel.errors import Forbidden, NotFound
from skm.kernel.ports_uow import Surface
from skm.modules.knowledge import public as knowledge

__all__ = ["GROUP", "register"]

_OPERATIONS = {
    "init": "context.host.codegraph",
    "index": "context.host.codegraph",
    "status": "context.host.codegraph",
    "doctor": "context.host.codegraph",
    "neighbors": "knowledge.graph_neighbors",
    "path": "knowledge.graph_path",
    "stats": "knowledge.graph_stats",
    "subgraph": "knowledge.graph_subgraph",
    "indexes": "knowledge.list_graph_indexes",
    "derive": "knowledge.host.derive_project_graph",
    "import-code": "knowledge.host.import_code_graph",
}
_QUERIES = {
    "neighbors": knowledge.GraphNeighbors,
    "path": knowledge.GraphPath,
    "stats": knowledge.GraphStats,
    "subgraph": knowledge.GraphSubgraph,
    "indexes": knowledge.ListGraphIndexes,
}
_HELP = {
    "init": "initialize and index the checkout with CodeGraph",
    "index": "rebuild the checkout's CodeGraph index",
    "status": "show the checkout's CodeGraph index status",
    "doctor": "check CodeGraph readiness and show its MCP configuration",
    "neighbors": "inspect the neighborhood of a node",
    "path": "find a path between two nodes",
    "stats": "summarize a workspace or project graph",
    "subgraph": "inspect the graph induced by one or more roots",
    "indexes": "list the latest graph indexes by source and repository",
    "import-code": "import an existing Serena graph export",
    "derive": "import dependency declarations from package manifests",
}


def _human_answer(ctx: CliContext, answer: dict[str, Any]) -> list[str]:
    lines = kv_lines(
        ctx,
        [
            ("freshness", answer["freshness"]["state"]),
            ("completeness", answer["completeness"]),
            ("revision", answer["revision"]),
            ("basis", answer["basis"]),
        ],
    )
    if answer["stats"] is not None:
        lines.extend(kv_lines(ctx, list(answer["stats"].items())))
    if answer["query"]["op"] == "path":
        path = answer["path"]
        lines.append(safe_text(ctx, " → ".join(path)) if path else "no path in this answer")
    if answer["nodes"]:
        lines.extend(
            render_table(
                ctx,
                ("node", "type", "source"),
                [(node["node_key"], node["type"], node["source"]) for node in answer["nodes"]],
            )
        )
    if answer["edges"]:
        lines.extend(
            render_table(
                ctx,
                ("from", "relation", "to", "basis"),
                [(edge["src_key"], edge["type"], edge["dst_key"], edge["basis"]) for edge in answer["edges"]],
            )
        )
    for limitation in answer["limitations"]:
        lines.extend(kv_lines(ctx, [(limitation["code"], limitation["message"])]))
    return lines


def _human_indexes(ctx: CliContext, result: dict[str, Any]) -> list[str]:
    columns = ("source", "repository_id", "generation", "revision", "indexed_at", "completeness")
    return render_table(ctx, columns, [tuple(row[key] for key in columns) for row in result["items"]])


def _run_native(args: argparse.Namespace, ctx: CliContext) -> int:
    operation = next(
        spec
        for module in MANIFESTS
        if module.id == "context"
        for spec in module.host_operations
        if spec.name == args.command_name and Surface.CLI in spec.surfaces
    )
    report = cast(
        "dict[str, Any]",
        operation.run(
            ctx.host_context(),
            {
                "action": args.verb,
                "project_id": str(resolve_project_id(ctx, args.project)),
                "mount": args.mount,
            },
        ),
    )
    render(ctx, report, command=args.command_name, human=lambda value: kv_lines(ctx, list(value.items())))
    return int(args.verb == "doctor" and not report["healthy"])


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    if args.verb in ("import-code", "derive"):
        operation = next(
            spec
            for module in MANIFESTS
            if module.id == "knowledge"
            for spec in module.host_operations
            if spec.name == args.command_name and Surface.CLI in spec.surfaces
        )
        report = cast(
            "dict[str, Any]",
            operation.run(
                ctx.host_context(),
                {
                    "project_id": str(resolve_project_id(ctx, args.project)),
                    "mount": args.mount,
                },
            ),
        )
        return render(
            ctx,
            report,
            command=args.command_name,
            human=lambda value: kv_lines(
                ctx,
                [
                    ("source", value["source"]),
                    ("generation", value["generation"]),
                    ("nodes imported", value["nodes_upserted"]),
                    ("edges imported", value["edges_added"]),
                    ("edges rejected", len(value["edges_rejected"])),
                    ("chunks", value["chunks"]),
                ],
            ),
        )

    fields = {key: getattr(args, key) for key in args.fields if getattr(args, key) is not None}
    project = (
        resolve_project_view(ctx, args.project, workspace_ref=args.workspace)
        if (args.verb == "stats" and args.project)
        else None
    )
    fields["workspace_id"] = str(
        project.workspace_id if project and not args.workspace else resolve_workspace_id(ctx, args.workspace)
    )
    if project is not None:
        fields["project_id"] = str(project.project_id)
    if args.verb in {"neighbors", "path", "subgraph"}:
        try:
            checkout_project = resolve_project_view(ctx, workspace_ref=args.workspace)
        except (Forbidden, NotFound):
            checkout_project = None
        head = knowledge_wiring.current_checkout_revision(
            ctx.client,
            UUID(fields["workspace_id"]),
            project=checkout_project,
            fallback=fields.pop("at_revision", None),
        )
        if head is not None:
            fields["at_revision"] = head
    answer = ctx.client.ask(_QUERIES[args.verb].from_json(fields))
    present = _human_indexes if args.verb == "indexes" else _human_answer
    return render(ctx, answer, command=args.command_name, human=lambda value: present(ctx, value))


def register(sub: SubParsers) -> None:
    group = sub.add_parser("graph", help=GROUP.help)
    verbs = group.add_subparsers(dest="verb", required=True)
    for verb in _OPERATIONS:
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        command.set_defaults(command_name=_OPERATIONS[verb], command_module="knowledge", run=_run)
        if verb in ("init", "index", "status", "doctor"):
            command.add_argument("--project", help="project reference (defaults to active)")
            command.add_argument("--mount", help="checkout mount (defaults to main)")
            command.set_defaults(run=_run_native, command_module="context")
        elif verb in ("import-code", "derive"):
            command.add_argument("--project")
            command.add_argument("--mount")
        else:
            command.add_argument("--workspace")
            fields: list[str] = []
            if verb == "neighbors":
                command.add_argument("node_key")
                fields.append("node_key")
            if verb == "path":
                command.add_argument("src_key")
                command.add_argument("dst_key")
                fields.extend(("src_key", "dst_key"))
            if verb == "subgraph":
                command.add_argument("roots", nargs="+")
                fields.append("roots")
            if verb == "stats":
                command.add_argument("--project")
            elif verb == "indexes":
                command.add_argument("--repository", dest="repository_id")
                command.add_argument("--source")
                fields.extend(("repository_id", "source"))
            else:
                command.add_argument("--direction", choices=("in", "out", "both"))
                command.add_argument("--edge-type", action="append", dest="edge_types")
                command.add_argument("--at-revision")
                fields.extend(("direction", "edge_types", "at_revision"))
            if verb in ("neighbors", "subgraph"):
                command.add_argument("--depth", type=int)
                fields.append("depth")
            command.set_defaults(fields=fields)


GROUP = CommandGroup(
    name="graph", help="manage CodeGraph and inspect the project knowledge graph", register=register
)
