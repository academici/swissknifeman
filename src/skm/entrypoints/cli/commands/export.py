"""Render Markdown and deliver queued notes to the locally bound vault."""

import argparse
from hashlib import sha256
from pathlib import Path
from typing import cast

from skm.bootstrap.worker import run_vault_host
from skm.entrypoints.cli._run_io import identifier, run_id
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.plan import resolve_plan_id
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.commands.workspace import resolve_workspace_id
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import kv_lines, render, render_error
from skm.entrypoints.cli.refs import as_uuid
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, ValidationFailed, error_for
from skm.kernel.json_types import JsonObject
from skm.modules.access.public import WhoAmI, WhoAmIView
from skm.modules.exports import public as exports
from skm.platform.fs.atomic_write import UnsafePathError, atomic_write

__all__ = ["GROUP", "register", "register_run_report_args"]

_HELP = {
    "vault": "discover the local vault or explicitly manage its writer identity",
    "docs-push": "publish checkout documents to the bound vault",
    "vault-push": "deliver pending notes to the local vault",
    "plan": "render a published plan as Markdown",
    "run": "render a run report as Markdown",
    "notes": "list vault notes and delivery receipts",
    "requeue": "open a new delivery generation for a note",
}
_OPERATIONS = {
    "vault": "exports.host.locate_vault",
    "docs-push": "exports.host.push_vault_docs",
    "vault-push": "exports.host.push_vault_notes",
    "plan": exports.RenderPlanMarkdown,
    "run": exports.RenderRunReport,
    "notes": exports.ListVaultNotes,
    "requeue": exports.RequeueNote,
}


def _markdown(args: argparse.Namespace, ctx: CliContext) -> int:
    if args.verb == "plan":
        plan = as_uuid(args.ref) or resolve_plan_id(ctx, args.ref)
        payload = {"plan_id": str(plan)}
        if args.revision is not None:
            payload["revision_no"] = args.revision
        query: exports.RenderPlanMarkdown | exports.RenderRunReport = exports.RenderPlanMarkdown.from_json(
            payload
        )
    else:
        query = exports.RenderRunReport(run_id(ctx, args.ref), "summary" if args.summary else "full")
    result = ctx.client.ask(query)
    if isinstance(result, (exports.PlanMarkdownView, exports.RunReportView)):
        markdown = result.markdown
    else:
        markdown = str(cast("JsonObject", result)["markdown"])
    data = markdown.encode("utf-8")
    digest = "sha256:" + sha256(data).hexdigest()
    if args.output is None:
        report = {"markdown": markdown, "digest": digest}
        return render(
            ctx, report, command=args.command_name, human=lambda _: markdown.removesuffix("\n").split("\n")
        )
    try:
        atomic_write(Path(args.output), data, mode=0o600)
    except (OSError, UnsafePathError):
        raise ValidationFailed(
            ErrorCode.INTEGRATION_UNSAFE_TARGET, "Cannot write Markdown to the output path"
        ) from None
    report = {"output": args.output, "digest": digest}
    return render(ctx, report, command=args.command_name, human=lambda _: kv_lines(ctx, list(report.items())))


def _vault(args: argparse.Namespace, ctx: CliContext) -> int:
    request: JsonObject = {}
    if args.verb == "docs-push":
        project = resolve_project_id(ctx, args.project)
        request = {
            "project_id": str(project),
            "mount": args.mount,
            "dry_run": args.dry_run,
            "force": args.force,
        }
        if args.pattern is not None:
            request["patterns"] = args.pattern
    elif args.verb == "vault-push":
        workspace = resolve_workspace_id(ctx, args.workspace)
        request = {"workspace_id": str(workspace), "limit": args.limit, "dry_run": args.dry_run}
    else:
        project = None
        try:
            project = resolve_project_id(ctx, args.project)
        except (NotFound, ValidationFailed) as exc:
            if args.project is not None or exc.code not in (ErrorCode.INVALID_REFERENCE, ErrorCode.NOT_FOUND):
                raise
        if project is not None:
            request["project_id"] = str(project)
        if args.bind_writer or args.fork_identity:
            identity = cast("WhoAmIView", ctx.client.ask(WhoAmI(project)))
            if (
                "export.run" not in identity.effective_permissions
                or identity.principal.kind not in ("human", "service")
                or (identity.token is not None and identity.token.kind == "assignment")
            ):
                raise Forbidden(ErrorCode.FORBIDDEN, "Managing vault identity requires export.run")
            if args.bind_writer:
                request["bind_writer"] = str(identifier(args.bind_writer, "host"))
            if args.fork_identity:
                if not ctx.confirm("Replace the vault UUID?"):
                    raise ValidationFailed(
                        ErrorCode.SCHEMA_INVALID,
                        "Confirmation required; pass --yes to confirm",
                        details={"reason": "confirmation_required"},
                    )
                request["fork_identity"] = True
    report = run_vault_host(ctx.host_context(), args.command_name, request)
    if report.get("partial") or report.get("mapping_error"):
        status = (
            ErrorCode.EXPORT_VAULT_PROJECT_UNKNOWN
            if report.get("mapping_error")
            else ErrorCode.INVALID_TRANSITION
        )
        return render_error(
            ctx,
            error_for(status, "Vault operation requires attention", details={"report": report}),
            command=args.command_name,
            extra=() if ctx.json else tuple(f"{key}  {value}" for key, value in report.items()),
        )
    return render(ctx, report, command=args.command_name, human=lambda _: kv_lines(ctx, list(report.items())))


def _notes(args: argparse.Namespace, ctx: CliContext) -> int:
    project = resolve_project_id(ctx, args.project)
    if args.verb == "requeue":
        note = identifier(args.ref, "vault note")
        command = exports.RequeueNote.from_json(
            {
                "project_id": str(project),
                "note_id": str(note),
                "expected_generation": args.expected_generation,
            }
        )
        result = cast(
            "exports.RequeueNoteResult",
            ctx.client.dispatch(command, idempotency_key=ctx.new_idempotency_key()),
        )
        return render(
            ctx,
            result,
            command=args.command_name,
            human=lambda _: kv_lines(ctx, list(result.to_json().items())),
        )
    page = cast(
        "exports.VaultNotesView", ctx.client.ask(exports.ListVaultNotes(project, args.after, args.limit))
    )
    return render(
        ctx,
        page,
        command=args.command_name,
        human=lambda _: (
            [
                *(line for item in page.items for line in kv_lines(ctx, list(item.to_json().items()))),
                *kv_lines(ctx, [("next", page.next_cursor)] if page.next_cursor else []),
            ]
            or ["no vault notes"]
        ),
    )


def register_run_report_args(command: argparse.ArgumentParser) -> None:
    command.add_argument("ref", metavar="RUN")
    command.add_argument("--summary", action="store_true")
    command.add_argument("--output", "-o")
    command.set_defaults(run=_markdown, command_name="exports.render_run_report")


def register(sub: SubParsers) -> None:
    group = sub.add_parser("export", help=GROUP.help)
    verbs = group.add_subparsers(dest="verb", required=True)
    for verb, operation in _OPERATIONS.items():
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if verb in ("vault", "docs-push", "notes", "requeue"):
            command.add_argument("--project")
        if verb == "vault":
            identity = command.add_mutually_exclusive_group()
            identity.add_argument(
                "--bind-writer",
                metavar="HOST_ID",
                help="bind this host after any previous writer has stopped and reconciled",
            )
            identity.add_argument(
                "--fork-identity",
                action="store_true",
                help="mint an unbound vault identity after stopping writers",
            )
            command.add_argument(
                "--yes",
                "-y",
                action="store_true",
                default=argparse.SUPPRESS,
                help="confirm vault identity fork",
            )
        if verb == "docs-push":
            command.add_argument("--mount", default="main")
            command.add_argument("--pattern", action="append", metavar="GLOB")
            command.add_argument("--dry-run", action="store_true")
            command.add_argument(
                "--force",
                action="store_true",
                help="replace the current destination, including changes since preview",
            )
        if verb == "vault-push":
            command.add_argument("--workspace")
            command.add_argument("--limit", type=int, default=100)
            command.add_argument("--dry-run", action="store_true")
        if verb == "run":
            register_run_report_args(command)
        if verb in ("plan", "requeue"):
            command.add_argument("ref", metavar=verb.upper() if verb != "requeue" else "NOTE_ID")
        if verb == "plan":
            command.add_argument("--output", "-o")
            command.add_argument("--revision", type=int)
        if verb == "notes":
            command.add_argument("--after")
            command.add_argument("--limit", type=int)
        if verb == "requeue":
            command.add_argument("--expected-generation", type=int, required=True)
        if verb in ("vault", "vault-push", "docs-push"):
            command.set_defaults(run=_vault, command_name=operation)
        else:
            name = "exports." + cast("type[exports.RenderPlanMarkdown]", operation).SCHEMA_URN.split(":")[
                -2
            ].replace("-", "_")
            command.set_defaults(run=_markdown if verb in ("plan", "run") else _notes, command_name=name)


GROUP = CommandGroup("export", "render Markdown and deliver vault notes", register, module="exports")
