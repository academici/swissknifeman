"""Project-scoped memory commands."""

import argparse
from typing import Any

from skm.entrypoints.cli._run_io import ask, dispatch, identifier, show
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import kv_lines, render, render_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.modules.knowledge import public as knowledge
from skm.platform.schema.registry import SchemaRegistry

__all__ = ["GROUP", "read_pages", "register"]

_HELP = {
    "remember": "save a short memory entry",
    "search": "recall project memory",
    "list": "page through stored memory",
    "forget": "forget an entry or the active handoff",
}
_OPERATIONS = {
    "remember": knowledge.Remember,
    "search": knowledge.SearchMemory,
    "list": knowledge.ListMemory,
    "forget": knowledge.Forget,
}
_WRITES = frozenset({"remember", "forget"})


def _project(ctx: CliContext, raw: str | None) -> str:
    try:
        return str(resolve_project_id(ctx, raw))
    except NotFound as error:
        if error.details.get("kind") == "project" and error.details.get("hint") == "skm use":
            raise PreconditionFailed(
                ErrorCode.MEMORY_SCOPE_REQUIRED, "Memory requires a project scope"
            ) from error
        raise


def _scope(raw: str) -> dict[str, str]:
    if raw.startswith("ns:") and raw[3:]:
        return {"kind": "namespace", "namespace": raw[3:]}
    if raw in {"global", "project"}:
        return {"kind": raw}
    raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Expected project, global or ns:NAME")


def read_pages(ctx: CliContext, dto: Any, args: argparse.Namespace, **fields: Any) -> dict[str, Any]:
    page = ask(ctx, dto, after=args.after, limit=args.limit, **fields)
    items = list(page["items"])
    while args.all and page["next_cursor"]:
        page = ask(ctx, dto, after=page["next_cursor"], limit=args.limit, **fields)
        items.extend(page["items"])
    return {**page, "items": items}


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    project = _project(ctx, args.project)
    operation = args.operation
    scope = _scope(args.scope) if args.scope else None
    if args.verb == "search":
        if args.limit < 1:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Expected a positive limit")
        result = ask(
            ctx,
            operation,
            project_id=project,
            query=args.query,
            include_shared=args.shared,
            scope=scope,
        )
        result = {
            **result,
            "items": result["items"][: args.limit],
            "truncated": result["truncated"] or len(result["items"]) > args.limit,
        }
    elif args.verb == "list":
        result = read_pages(
            ctx,
            operation,
            args,
            project_id=project,
            scope=scope,
            include_expired=args.include_expired,
        )
    elif args.verb in _WRITES:
        if args.verb == "remember":
            payload = {
                "project_id": project,
                "scope": scope or {"kind": "project"},
                "kind": args.key.replace("-", "_"),
                "body": args.text,
                "ttl_hours": args.ttl_hours,
                "source": "cli",
                "expected_handoff_id": str(identifier(args.expected_handoff_id, "memory"))
                if args.expected_handoff_id
                else None,
            }
            SchemaRegistry.load_default().require_valid(operation.SCHEMA_URN, payload)
            result = ctx.client.dispatch(
                operation.from_json(payload), idempotency_key=ctx.new_idempotency_key()
            )
        else:
            if bool(args.ref) == args.handoff or (args.ref and scope and scope["kind"] != "project"):
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID, "Use REF [--scope project] or --handoff [--scope SCOPE]"
                )
            target = (
                {"entry_id": str(identifier(args.ref, "memory"))}
                if args.ref
                else {"kind": "active_handoff", "scope": scope or {"kind": "project"}}
            )
            result = dispatch(ctx, operation, project_id=project, **target)
        return show(ctx, args.command_name, result)
    else:
        raise ValueError(f"Unknown memory verb: {args.verb}")

    def human(page: dict[str, Any]) -> list[str]:
        columns = ("id", "kind", "scope", "body", "expires_at")
        lines = (
            render_table(ctx, columns, [[row[key] for key in columns] for row in page["items"]])
            if page["items"]
            else ["no entries"]
        )
        if page.get("next_cursor"):
            lines.extend(kv_lines(ctx, [("next", page["next_cursor"])]))
        if page.get("truncated"):
            lines.append("recall truncated")
        return lines

    return render(ctx, result, command=args.command_name, human=human)


def register(sub: SubParsers) -> None:
    group = sub.add_parser("memory", help=GROUP.help)
    verbs = group.add_subparsers(dest="verb", required=True)
    for verb, operation in _OPERATIONS.items():
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--project")
        command.add_argument("--scope", help="project, global or ns:NAME")
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if verb == "remember":
            command.add_argument("text")
            command.add_argument("--key", default="context")
            command.add_argument("--ttl-hours", type=float)
            command.add_argument("--expected-handoff-id")
        if verb == "search":
            command.add_argument("query", nargs="?")
            command.add_argument("--shared", action="store_true")
        if verb in ("search", "list"):
            command.add_argument("--limit", type=int, default=50)
        if verb == "list":
            command.add_argument("--after")
            command.add_argument("--all", action="store_true")
            command.add_argument("--include-expired", action="store_true")
        if verb == "forget":
            command.add_argument("ref", nargs="?")
            command.add_argument("--handoff", action="store_true")
        operation_name = operation.SCHEMA_URN.split(":")[-2].replace("-", "_")
        command.set_defaults(run=_run, command_name="knowledge." + operation_name, operation=operation)


GROUP = CommandGroup("memory", "recall and maintain project memory", register, module="knowledge")
