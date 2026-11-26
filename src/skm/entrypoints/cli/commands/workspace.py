"""``skm workspace`` (cli §6, workspace §10): manage workspaces and sync projections."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Literal, cast

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliSession
from skm.entrypoints.cli.output import kv_lines, render, render_table, safe_text
from skm.entrypoints.cli.refs import RefForm, RefKind, as_uuid, parse_ref
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import WorkspaceId
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.entrypoints.cli.context import CliContext

__all__ = ["GROUP", "register", "resolve_workspace_id", "resolve_workspace_view"]

_HELP = {
    "create": "create a workspace",
    "list": "list workspaces",
    "show": "show a workspace",
    "archive": "archive a workspace",
    "sync-projections": "sync projections and Git excludes for local checkouts in a workspace",
}

_COMMAND = {
    "create": "workspace.create_workspace",
    "list": "workspace.list_workspaces",
    "show": "workspace.get_workspace",
    "archive": "workspace.archive_workspace",
    "sync-projections": "integrations.host.sync_projections",
}


def _env_workspace(ctx: CliContext) -> str | None:
    if isinstance(ctx, CliSession):
        if ctx.options.scope and ctx.options.scope.startswith(("ws:", "workspace:")):
            return ctx.options.scope
        val = ctx.environ.get("SKM_WORKSPACE")
        if val:
            return val
    return None


def _normalize_ws_ref(text: str) -> str:
    if text.startswith("ws:"):
        tail = text.removeprefix("ws:")
        if as_uuid(tail) is not None:
            return f"workspace:{tail}"
        return tail
    if as_uuid(text) is not None:
        return f"workspace:{text}"
    return text


def _remote_workspace(ctx: CliContext, slug: str) -> workspace.WorkspaceView:
    after = None
    while True:
        page = cast("workspace.ListWorkspacesView", ctx.client.ask(workspace.ListWorkspaces(after=after)))
        for item in page.items:
            if item.slug == slug:
                return cast(
                    "workspace.WorkspaceView",
                    ctx.client.ask(workspace.GetWorkspace(workspace_id=item.workspace_id)),
                )
        if page.next is None:
            raise NotFound(ErrorCode.NOT_FOUND, f"Workspace {slug!r} not found")
        after = page.next


def resolve_workspace_view(ctx: CliContext, raw: str | None = None) -> workspace.WorkspaceView:
    """Resolve a workspace reference (or active workspace context) to a ``WorkspaceView``."""
    candidate = raw or _env_workspace(ctx)
    if candidate is None:
        ws_id = ctx.resolve_workspace(None)
        view = ctx.client.ask(workspace.GetWorkspace(workspace_id=ws_id))
        assert isinstance(view, workspace.WorkspaceView)  # noqa: S101
        return view

    parsed = parse_ref(RefKind.WORKSPACE, _normalize_ws_ref(candidate))
    if parsed.form is RefForm.UUID and parsed.uuid is not None:
        view = ctx.client.ask(workspace.GetWorkspace(workspace_id=WorkspaceId(parsed.uuid)))
        assert isinstance(view, workspace.WorkspaceView)  # noqa: S101
        return view
    if parsed.form is RefForm.SLUG:
        from skm.bootstrap.instance_secrets import is_http_client

        if is_http_client(ctx.client):
            return _remote_workspace(ctx, parsed.text)
        view = ctx.client.ask(workspace.GetWorkspace(slug=parsed.text))
        assert isinstance(view, workspace.WorkspaceView)  # noqa: S101
        return view
    raise ValidationFailed(
        ErrorCode.INVALID_REFERENCE,
        f"invalid workspace reference: {candidate!r}",
        details={"ref": candidate, "expected": RefKind.WORKSPACE.value},
    )


def resolve_workspace_id(ctx: CliContext, raw: str | None = None) -> WorkspaceId:
    """Resolve a workspace reference (UUID, ``ws:<uuid>``, ``ws:<slug>`` or ``<slug>``) to ``WorkspaceId``."""
    candidate = raw or _env_workspace(ctx)
    if candidate is None:
        return ctx.resolve_workspace(None)
    parsed = parse_ref(RefKind.WORKSPACE, _normalize_ws_ref(candidate))
    if parsed.form is RefForm.UUID and parsed.uuid is not None:
        return WorkspaceId(parsed.uuid)
    if parsed.form is RefForm.SLUG:
        return WorkspaceId(resolve_workspace_view(ctx, candidate).workspace_id)
    raise ValidationFailed(
        ErrorCode.INVALID_REFERENCE,
        f"invalid workspace reference: {candidate!r}",
        details={"ref": candidate, "expected": RefKind.WORKSPACE.value},
    )


def _create(args: argparse.Namespace, ctx: CliContext) -> int:
    title = args.title if args.title is not None else args.slug
    result = cast(
        "workspace.CreateWorkspaceResult",
        ctx.client.dispatch(
            workspace.CreateWorkspace(slug=args.slug, title=title),
            idempotency_key=ctx.new_idempotency_key(),
        ),
    )
    return render(
        ctx,
        result,
        human=lambda value: kv_lines(
            ctx,
            [
                ("workspace_id", value.workspace_id),
                ("slug", value.slug),
            ],
        ),
        command=args.command_name,
        essential=lambda value: str(value.workspace_id),
    )


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    if getattr(args, "include_archived", False):
        state_filter: Literal["active", "suspended", "archived"] | None = None
    else:
        raw_state = getattr(args, "state", "active") or "active"
        state_filter = (
            None if raw_state == "all" else cast("Literal['active', 'suspended', 'archived']", raw_state)
        )
    view = cast(
        "workspace.ListWorkspacesView",
        ctx.client.ask(
            workspace.ListWorkspaces(
                state=state_filter,
                after=args.after,
                limit=args.limit,
            )
        ),
    )

    def human(value: workspace.ListWorkspacesView) -> list[str]:
        if not value.items:
            return ["no workspaces"]
        rows = [[item.workspace_id, item.slug, item.title, item.state] for item in value.items]
        lines = render_table(ctx, ("workspace_id", "slug", "title", "state"), rows)
        if value.next is not None:
            lines.append(safe_text(ctx, f"next: {value.next} (use --after)"))
        return lines

    return render(
        ctx,
        view,
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(str(item.workspace_id) for item in value.items),
    )


def _show(args: argparse.Namespace, ctx: CliContext) -> int:
    view = resolve_workspace_view(ctx, args.workspace)
    return render(
        ctx,
        view,
        human=lambda value: kv_lines(
            ctx,
            [
                ("workspace_id", value.workspace_id),
                ("slug", value.slug),
                ("title", value.title),
                ("state", value.state),
                ("project_count", value.project_count),
                ("row_version", value.row_version),
            ],
        ),
        command=args.command_name,
        essential=lambda value: str(value.workspace_id),
    )


def _archive(args: argparse.Namespace, ctx: CliContext) -> int:
    ws_id = resolve_workspace_id(ctx, args.workspace)
    if not getattr(args, "yes", False) and not ctx.confirm(f"Archive workspace {ws_id}?"):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "Confirmation required; pass --yes to confirm",
            details={"reason": "confirmation_required", "workspace_id": str(ws_id)},
        )
    expected = args.expected_version
    if expected is None:
        current = cast(
            "workspace.WorkspaceView",
            ctx.client.ask(workspace.GetWorkspace(workspace_id=ws_id)),
        )
        expected = current.row_version
    result = cast(
        "workspace.ArchiveWorkspaceResult",
        ctx.client.dispatch(
            workspace.ArchiveWorkspace(
                workspace_id=ws_id,
                expected_row_version=expected,
                reason=args.reason or "archived via CLI",
            ),
            idempotency_key=ctx.new_idempotency_key(),
        ),
    )
    return render(
        ctx,
        result,
        human=lambda value: [f"archived workspace {value.workspace_id}"],
        command=args.command_name,
        essential=lambda value: str(value.workspace_id),
    )


def _sync_projections(args: argparse.Namespace, ctx: CliContext) -> int:
    from skm.entrypoints.cli.commands.integrations import sync_checkout_projections

    return sync_checkout_projections(ctx, args.command_name, resolve_workspace_id(ctx, args.workspace))


_HANDLERS = {
    "create": _create,
    "list": _list,
    "show": _show,
    "archive": _archive,
    "sync-projections": _sync_projections,
}


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("workspace", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", metavar="VERB", required=True)
    for verb in ("create", "list", "show", "archive", "sync-projections"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
        if verb == "create":
            command.add_argument("slug")
            command.add_argument("--title")
        if verb == "list":
            command.add_argument(
                "--state",
                choices=("active", "suspended", "archived", "all"),
                default="active",
            )
            command.add_argument("--include-archived", action="store_true", help=argparse.SUPPRESS)
            command.add_argument("--after")
            command.add_argument("--limit", type=int, default=50)
        if verb in ("show", "archive", "sync-projections"):
            command.add_argument("workspace", nargs="?")
        if verb == "archive":
            command.add_argument("--expected-version", type=int, default=None)
            command.add_argument("--reason", default="archived via CLI")
            command.add_argument("--yes", action="store_true")
        command.set_defaults(run=_HANDLERS[verb], command_name=_COMMAND[verb])


GROUP = CommandGroup(
    name="workspace",
    help="create, inspect and archive workspaces and sync projections",
    register=register,
    requires_backend=True,
    module="workspace",
    order=10,
)
