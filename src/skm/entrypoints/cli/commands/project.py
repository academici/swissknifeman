"""``skm project`` (cli §6, workspace §10): manage and activate projects."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.host import resolve_host_id
from skm.entrypoints.cli.commands.workspace import resolve_workspace_id, resolve_workspace_view
from skm.entrypoints.cli.context import CliSession
from skm.entrypoints.cli.errors import Terminated
from skm.entrypoints.cli.output import kv_lines, render, render_table, safe_text, to_jsonable
from skm.entrypoints.cli.refs import RefForm, RefKind, as_uuid, parse_ref
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, NotFound, ValidationFailed
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.settings import public as settings
from skm.modules.workspace import public as workspace
from skm.platform.fs.atomic_write import atomic_write

if TYPE_CHECKING:
    from skm.entrypoints.cli.context import CliContext

__all__ = ["GROUP", "register", "resolve_project_id", "resolve_project_view"]

_CONFIG_EVENT_TYPES = frozenset(
    {
        "urn:skm:settings:event:config-changed:v1",
        "urn:skm:settings:event:config-locked:v1",
        "urn:skm:settings:event:config-unlocked:v1",
    }
)

_HELP = {
    "create": "create a project in the active workspace",
    "list": "list projects in the active workspace",
    "show": "show a project and its mounted repositories",
    "archive": "archive a project",
    "activate": "sync local projections and select a project and its workspace",
    "config": "pull, push, or watch project-scoped configuration",
}

_COMMAND = {
    "create": "workspace.create_project",
    "list": "workspace.list_projects",
    "show": "workspace.get_project",
    "archive": "workspace.archive_project",
    "activate": "integrations.host.sync_projections",
}


def _env_project(ctx: CliContext) -> str | None:
    if isinstance(ctx, CliSession):
        val = ctx.environ.get("SKM_PROJECT")
        if val:
            return val
    return None


def _normalize_proj_ref(text: str) -> str:
    if text.startswith("proj:"):
        tail = text.removeprefix("proj:")
        if as_uuid(tail) is not None:
            return f"project:{tail}"
        return tail
    if as_uuid(text) is not None:
        return f"project:{text}"
    return text


def _remote_project(ctx: CliContext, slug: str, workspace_id: WorkspaceId) -> workspace.ProjectView:
    after = None
    while True:
        page = cast(
            "workspace.ListProjectsView",
            ctx.client.ask(workspace.ListProjects(workspace_id=workspace_id, after=after)),
        )
        for item in page.items:
            if item.slug == slug:
                return cast(
                    "workspace.ProjectView", ctx.client.ask(workspace.GetProject(project_id=item.project_id))
                )
        if page.next is None:
            raise NotFound(ErrorCode.NOT_FOUND, f"Project {slug!r} not found")
        after = page.next


def resolve_project_view(
    ctx: CliContext,
    raw: str | None = None,
    *,
    workspace_ref: str | None = None,
) -> workspace.ProjectView:
    """Resolve a project reference (UUID, ``proj:<ref>``, ``<ws>/<proj>`` or ``<slug>``) to a view."""
    candidate = raw or _env_project(ctx)
    if candidate is None:
        proj_id = ctx.resolve_project(None)
        view = ctx.client.ask(workspace.GetProject(project_id=proj_id))
        assert isinstance(view, workspace.ProjectView)  # noqa: S101
        return view

    parsed = parse_ref(RefKind.PROJECT, _normalize_proj_ref(candidate))
    if parsed.form is RefForm.UUID and parsed.uuid is not None:
        view = ctx.client.ask(workspace.GetProject(project_id=ProjectId(parsed.uuid)))
        assert isinstance(view, workspace.ProjectView)  # noqa: S101
        return view
    if parsed.form in (RefForm.QUALIFIED_SLUG, RefForm.SLUG):
        slug = parsed.text.rsplit("/", 1)[-1]
        from skm.bootstrap.instance_secrets import is_http_client

        if is_http_client(ctx.client):
            return _remote_project(ctx, slug, resolve_workspace_id(ctx, parsed.qualifier or workspace_ref))
        ws_slug = parsed.qualifier or resolve_workspace_view(ctx, workspace_ref).slug
        view = ctx.client.ask(workspace.GetProject(workspace_slug=ws_slug, project_slug=slug))
        assert isinstance(view, workspace.ProjectView)  # noqa: S101
        return view
    raise ValidationFailed(
        ErrorCode.INVALID_REFERENCE,
        f"invalid project reference: {candidate!r}",
        details={"ref": candidate, "expected": RefKind.PROJECT.value},
    )


def resolve_project_id(
    ctx: CliContext,
    raw: str | None = None,
    *,
    workspace_ref: str | None = None,
) -> ProjectId:
    """Resolve a project reference to ``ProjectId``."""
    candidate = raw or _env_project(ctx)
    if candidate is None:
        return ctx.resolve_project(None)
    parsed = parse_ref(RefKind.PROJECT, _normalize_proj_ref(candidate))
    if parsed.form is RefForm.UUID and parsed.uuid is not None:
        return ProjectId(parsed.uuid)
    return ProjectId(resolve_project_view(ctx, candidate, workspace_ref=workspace_ref).project_id)


def _create(args: argparse.Namespace, ctx: CliContext) -> int:
    ws_id: WorkspaceId = resolve_workspace_id(ctx, getattr(args, "workspace", None))
    title = args.title if args.title is not None else args.slug
    result = cast(
        "workspace.CreateProjectResult",
        ctx.client.dispatch(
            workspace.CreateProject(
                workspace_id=ws_id,
                slug=args.slug,
                title=title,
                description=args.description,
            ),
            idempotency_key=ctx.new_idempotency_key(),
        ),
    )
    return render(
        ctx,
        result,
        human=lambda value: kv_lines(
            ctx,
            [
                ("project_id", value.project_id),
                ("slug", value.slug),
            ],
        ),
        command=args.command_name,
        essential=lambda value: str(value.project_id),
    )


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    ws_id = resolve_workspace_id(ctx, getattr(args, "workspace", None))
    if getattr(args, "include_archived", False):
        state_filter: Literal["active", "archived"] | None = None
    else:
        raw_state = getattr(args, "state", "active") or "active"
        state_filter = None if raw_state == "all" else cast("Literal['active', 'archived']", raw_state)
    view = cast(
        "workspace.ListProjectsView",
        ctx.client.ask(
            workspace.ListProjects(
                workspace_id=ws_id,
                state=state_filter,
                after=args.after,
                limit=args.limit,
            )
        ),
    )

    def human(value: workspace.ListProjectsView) -> list[str]:
        if not value.items:
            return ["no projects"]
        rows = [[item.project_id, item.slug, item.title, item.state] for item in value.items]
        lines = render_table(ctx, ("project_id", "slug", "title", "state"), rows)
        if value.next is not None:
            lines.append(safe_text(ctx, f"next: {value.next} (use --after)"))
        return lines

    return render(
        ctx,
        view,
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(str(item.project_id) for item in value.items),
    )


def _show(args: argparse.Namespace, ctx: CliContext) -> int:
    view = resolve_project_view(ctx, args.project, workspace_ref=getattr(args, "workspace", None))
    try:
        host_id = resolve_host_id(ctx, None, workspace_id=WorkspaceId(view.workspace_id))
    except Exception:  # noqa: BLE001
        host_id = None
    mounts_view = cast(
        "workspace.ListProjectRepositoriesView",
        ctx.client.ask(
            workspace.ListProjectRepositories(project_id=ProjectId(view.project_id), host_id=host_id)
        ),
    )
    payload: dict[str, Any] = dict(view.to_json())
    payload["repositories"] = [item.to_json() for item in mounts_view.items]

    def human(value: dict[str, Any]) -> list[str]:
        lines = kv_lines(
            ctx,
            [
                ("project_id", value["project_id"]),
                ("workspace_id", value["workspace_id"]),
                ("slug", value["slug"]),
                ("title", value["title"]),
                ("description", value["description"]),
                ("state", value["state"]),
                ("row_version", value["row_version"]),
            ],
        )
        if mounts_view.items:
            rows = [
                [
                    m.mount_name,
                    m.role,
                    m.repository.repository_id,
                    m.repository.canonical_remote or "-",
                    "-" if m.binding is None else m.binding.state,
                ]
                for m in mounts_view.items
            ]
            lines.extend(
                render_table(ctx, ("mount", "role", "repository_id", "remote", "binding_state"), rows)
            )
        elif view.mounts:
            rows = [[m.mount_name, m.role, m.repository_id, m.canonical_remote or "-"] for m in view.mounts]
            lines.extend(render_table(ctx, ("mount", "role", "repository_id", "remote"), rows))
        return lines

    return render(
        ctx,
        payload,
        human=human,
        command=args.command_name,
        essential=lambda value: str(value["project_id"]),
    )


def _archive(args: argparse.Namespace, ctx: CliContext) -> int:
    proj_id = resolve_project_id(ctx, args.project, workspace_ref=getattr(args, "workspace", None))
    if not getattr(args, "yes", False) and not ctx.confirm(f"Archive project {proj_id}?"):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "Confirmation required; pass --yes to confirm",
            details={"reason": "confirmation_required", "project_id": str(proj_id)},
        )
    expected = args.expected_version
    if expected is None:
        current = cast(
            "workspace.ProjectView",
            ctx.client.ask(workspace.GetProject(project_id=proj_id)),
        )
        expected = current.row_version
    result = cast(
        "workspace.ArchiveProjectResult",
        ctx.client.dispatch(
            workspace.ArchiveProject(
                project_id=proj_id,
                expected_row_version=expected,
                reason=args.reason or "archived via CLI",
            ),
            idempotency_key=ctx.new_idempotency_key(),
        ),
    )
    return render(
        ctx,
        result,
        human=lambda value: [f"archived project {value.project_id}"],
        command=args.command_name,
        essential=lambda value: str(value.project_id),
    )


def _activate(args: argparse.Namespace, ctx: CliContext) -> int:
    from skm.entrypoints.cli.commands.integrations import sync_checkout_projections

    project = resolve_project_view(ctx, args.project, workspace_ref=getattr(args, "workspace", None))
    ws = resolve_workspace_view(ctx, str(project.workspace_id))
    return sync_checkout_projections(
        ctx, args.command_name, WorkspaceId(ws.workspace_id), project=project, workspace_slug=ws.slug
    )


def _finite_float(text: str) -> float:
    number = float(text)
    if not math.isfinite(number):
        raise ValueError(f"number {text} is not finite")
    return number


def _reject_json_constant(text: str) -> float:
    raise ValueError(f"{text} is not a JSON number")


def _read_config_file(path_text: str) -> tuple[str, str | JsonObject]:
    path = Path(path_text)
    fmt = path.suffix.lower().removeprefix(".")
    if fmt not in {"toml", "json"}:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "project config push requires a .toml or .json file")
    try:
        with path.open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("document exceeds 1 MiB")
        text = data.decode("utf-8")
        if fmt == "toml":
            return fmt, text
        document = json.loads(text, parse_float=_finite_float, parse_constant=_reject_json_constant)
        if not isinstance(document, dict):
            raise ValueError("JSON document must be an object")
    except (OSError, ValueError, RecursionError) as exc:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            f"cannot read project config document: {exc}",
            details={"path": path_text},
        ) from None
    return fmt, cast("JsonObject", document)


def _export_project_config(
    ctx: CliContext, project_id: ProjectId, *, fmt: str, portable_only: bool
) -> settings.ExportConfigView:
    query = settings.ExportConfig.from_json(
        {
            "scope": {"level": "project", "scope_id": str(project_id)},
            "format": fmt,
            "portable_only": portable_only,
        }
    )
    return cast("settings.ExportConfigView", ctx.client.ask(query))


def _serialize_exported_document(view: settings.ExportConfigView) -> str:
    if isinstance(view.document, str):
        return view.document
    return json.dumps(to_jsonable(view.document), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _config_pull(args: argparse.Namespace, ctx: CliContext) -> int:
    proj_id = resolve_project_id(ctx, args.project, workspace_ref=getattr(args, "workspace", None))
    fmt = args.format
    if fmt is None:
        fmt = "json" if args.file and Path(args.file).suffix.lower() == ".json" else "toml"
    view = _export_project_config(ctx, proj_id, fmt=fmt, portable_only=args.portable_only)
    text = _serialize_exported_document(view)
    written_path: str | None = None
    if args.file:
        target = Path(args.file)
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, text.encode("utf-8"), mode=0o600)
        written_path = str(target)
    if not ctx.json and written_path is None:
        for line in text.splitlines():
            ctx.stdout.write(safe_text(ctx, line) + "\n")
        return 0
    payload: dict[str, Any] = {
        "project_id": str(proj_id),
        "format": view.format,
        "digest": view.digest,
        "document": to_jsonable(view.document),
        "path": written_path,
    }
    return render(
        ctx,
        payload,
        human=lambda value: kv_lines(
            ctx,
            [
                ("project_id", value["project_id"]),
                ("format", value["format"]),
                ("digest", value["digest"]),
                ("path", value["path"] or "-"),
            ],
        ),
        command=args.command_name,
        essential=lambda value: str(value["digest"]),
    )


def _config_push(args: argparse.Namespace, ctx: CliContext) -> int:
    proj_id = resolve_project_id(ctx, args.project, workspace_ref=getattr(args, "workspace", None))
    if args.expect_digest is None and not args.force:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "project config push requires --expect-digest for CAS revision check (or pass --force to bypass)",
            details={"reason": "cas_digest_required"},
        )
    fmt, document = _read_config_file(args.file)
    payload: JsonObject = {
        "scope": {"level": "project", "scope_id": str(proj_id)},
        "format": fmt,
        "document": document,
        "mode": "replace" if args.replace else "merge",
        "dry_run": args.dry_run,
        "expected_entries_digest": args.expect_digest,
        "reason": args.reason,
        "confirmed": ctx.assume_yes,
    }
    cmd = settings.ImportConfig.from_json(payload)
    result = cast(
        "settings.ImportConfigResult",
        ctx.client.dispatch(cmd, idempotency_key=ctx.new_idempotency_key()),
    )
    render(
        ctx,
        result,
        human=lambda value: kv_lines(
            ctx,
            [
                ("project_id", str(proj_id)),
                ("applied", str(value.applied).lower()),
                ("dry_run", str(value.dry_run).lower()),
                ("digest_before", value.entries_digest_before),
                ("digest_after", value.entries_digest_after),
                ("changes", str(len(value.changes))),
                ("problems", str(len(value.problems))),
            ],
        ),
        command=args.command_name,
        essential=lambda value: str(value.entries_digest_after),
    )
    return 1 if result.problems else 0


def _project_event_stream(
    ctx: CliContext,
    *,
    project_id: ProjectId,
    workspace_id: WorkspaceId,
    after: int,
    wait_seconds: float,
) -> Iterator[EventEnvelope]:
    stream_fn = getattr(ctx.client, "project_events", None)
    if callable(stream_fn):
        return cast(
            "Iterator[EventEnvelope]",
            stream_fn(
                project_id=project_id,
                workspace_id=workspace_id,
                after=after,
                types=_CONFIG_EVENT_TYPES,
                wait_seconds=wait_seconds,
            ),
        )
    target = str(project_id)
    return (
        event
        for event in ctx.client.events(
            workspace_id=workspace_id,
            after=after,
            types=_CONFIG_EVENT_TYPES,
            wait_seconds=wait_seconds,
        )
        if event.stream_id == project_id or event.payload.get("project_id") == target
    )


def _config_watch(args: argparse.Namespace, ctx: CliContext) -> int:
    project = resolve_project_view(ctx, args.project, workspace_ref=getattr(args, "workspace", None))
    proj_id = ProjectId(project.project_id)
    ws_id = WorkspaceId(project.workspace_id)
    fmt = args.format
    if fmt is None:
        fmt = "json" if args.file and Path(args.file).suffix.lower() == ".json" else "toml"
    after = args.after
    if after is None:
        _, meta = ctx.client.ask_with_meta(
            settings.GetGeneration.from_json({"scope": {"level": "project", "scope_id": str(proj_id)}})
        )
        after = meta.events_cursor or 0
    seen = 0
    retry_delay = 1.0
    try:
        while True:
            try:
                for event in _project_event_stream(
                    ctx, project_id=proj_id, workspace_id=ws_id, after=after, wait_seconds=args.wait
                ):
                    _sync_config_event(args, ctx, proj_id, fmt, event)
                    if event.workspace_seq is not None:
                        after = max(after, event.workspace_seq)
                    retry_delay = 1.0
                    seen += 1
                    if args.max_events is not None and seen >= args.max_events:
                        return 0
            except BackendUnavailable as error:
                if args.wait <= 0 or not error.retryable:
                    raise
                time.sleep(retry_delay)
                retry_delay = min(30.0, retry_delay * 2)
                continue
            if args.wait <= 0:
                return 0
    except Terminated:
        raise
    except KeyboardInterrupt:
        return 0


def _sync_config_event(
    args: argparse.Namespace, ctx: CliContext, project_id: ProjectId, fmt: str, event: EventEnvelope
) -> None:
    digest = None
    if args.file:
        view = _export_project_config(ctx, project_id, fmt=fmt, portable_only=args.portable_only)
        target = Path(args.file)
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, _serialize_exported_document(view).encode("utf-8"), mode=0o600)
        digest = view.digest
    if ctx.json:
        record = {
            "seq": event.workspace_seq,
            "type": event.type,
            "project_id": str(project_id),
            "digest": digest,
        }
        ctx.stdout.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    elif not ctx.quiet:
        suffix = f" digest={digest}" if digest else ""
        ctx.stdout.write(safe_text(ctx, f"{event.workspace_seq} {event.type}{suffix}") + "\n")
    ctx.stdout.flush()


_HANDLERS = {
    "create": _create,
    "list": _list,
    "show": _show,
    "archive": _archive,
    "activate": _activate,
}


def _register_config_subcommands(verbs: SubParsers) -> None:
    cfg = verbs.add_parser("config", help=_HELP["config"])
    cfg_verbs = cfg.add_subparsers(dest="project_config_verb", metavar="ACTION", required=True)

    pull = cfg_verbs.add_parser("pull", help="export project configuration and its CAS digest")
    pull.add_argument("project", nargs="?")
    pull.add_argument("--workspace", default=argparse.SUPPRESS)
    pull.add_argument("--file", default=None, help="write exported config to this path")
    pull.add_argument("--format", choices=("toml", "json"), default=None)
    pull.add_argument("--portable-only", action="store_true")
    pull.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
    pull.set_defaults(run=_config_pull, command_name="settings.export_config")

    push = cfg_verbs.add_parser("push", help="import project configuration with CAS revision check")
    push.add_argument("file", help="path to .toml or .json config document")
    push.add_argument("--project", default=None, help="target project reference")
    push.add_argument("--workspace", default=argparse.SUPPRESS)
    push.add_argument("--expect-digest", default=None, help="expected entries digest for CAS check")
    push.add_argument("--force", action="store_true", help="bypass CAS revision check")
    push.add_argument("--replace", action="store_true", help="remove keys absent from the document")
    push.add_argument("--dry-run", action="store_true", help="preview changes without writing")
    push.add_argument("--reason", default="", help="reason recorded in config history")
    push.add_argument("--yes", default=argparse.SUPPRESS, action="store_true")
    push.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
    push.set_defaults(run=_config_push, command_name="settings.import_config")

    watch = cfg_verbs.add_parser("watch", help="watch project config events over the project SSE stream")
    watch.add_argument("project", nargs="?")
    watch.add_argument("--workspace", default=argparse.SUPPRESS)
    watch.add_argument("--after", type=int, default=None, help="start after this workspace event cursor")
    watch.add_argument(
        "--wait", type=float, default=30.0, help="seconds per stream window (0 reads a snapshot)"
    )
    watch.add_argument("--max-events", type=int, default=None, help="stop after N config events")
    watch.add_argument("--file", default=None, help="re-pull updated config into this file on change")
    watch.add_argument("--format", choices=("toml", "json"), default=None)
    watch.add_argument("--portable-only", action="store_true")
    watch.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
    watch.set_defaults(run=_config_watch, command_name="settings.export_config")


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("project", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", metavar="VERB", required=True)
    for verb in ("create", "list", "show", "archive", "activate"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
        command.add_argument("--workspace", default=argparse.SUPPRESS)
        if verb == "create":
            command.add_argument("slug")
            command.add_argument("--title")
            command.add_argument("--description", default="")
        if verb == "list":
            command.add_argument(
                "--state",
                choices=("active", "archived", "all"),
                default="active",
            )
            command.add_argument("--include-archived", action="store_true", help=argparse.SUPPRESS)
            command.add_argument("--after")
            command.add_argument("--limit", type=int, default=50)
        if verb in ("show", "archive"):
            command.add_argument("project", nargs="?")
        if verb == "activate":
            command.add_argument("project")
        if verb == "archive":
            command.add_argument("--expected-version", type=int, default=None)
            command.add_argument("--reason", default="archived via CLI")
            command.add_argument("--yes", action="store_true")
        command.set_defaults(run=_HANDLERS[verb], command_name=_COMMAND[verb])
    _register_config_subcommands(verbs)


GROUP = CommandGroup(
    name="project",
    help="create, inspect, archive and activate projects",
    register=register,
    requires_backend=True,
    module="workspace",
    order=11,
)
