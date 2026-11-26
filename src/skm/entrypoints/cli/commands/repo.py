"""``skm repo`` (cli §6, workspace §10): register, attach, detach, bind, verify and list repositories."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.host import resolve_host_id, run_workspace_host_op
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.commands.workspace import resolve_workspace_id
from skm.entrypoints.cli.context import CliSession
from skm.entrypoints.cli.output import kv_lines, render, render_table, safe_text
from skm.entrypoints.cli.refs import as_uuid
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.entrypoints.cli.context import CliContext

__all__ = ["GROUP", "register", "resolve_repository_id"]

_HELP = {
    "register": "register a repository in the active workspace",
    "add-remote": "add a remote URL to a repository",
    "attach": "attach a repository as a mount in a project",
    "detach": "detach a mounted repository from a project",
    "bind": "bind a local Git checkout to a repository on this host",
    "verify": "re-verify local checkout bindings on this host",
    "list": "list repositories in the workspace or mounts in a project",
}

_COMMAND = {
    "register": "workspace.register_repository",
    "add-remote": "workspace.add_repository_remote",
    "attach": "workspace.attach_repository",
    "detach": "workspace.detach_repository",
    "bind": "workspace.host.bind_checkout",
    "verify": "workspace.host.verify_checkout",
    "list": "workspace.list_repositories",
}


def resolve_repository_id(
    ctx: CliContext,
    raw: str,
    *,
    workspace_id: WorkspaceId | None = None,
) -> RepositoryId:
    """Resolve a repository reference (UUID, ``repo:<uuid>``, title or remote) to ``RepositoryId``."""
    stripped = raw.removeprefix("repo:").removeprefix("repository:")
    by_uuid = as_uuid(stripped)
    if by_uuid is not None:
        return RepositoryId(by_uuid)

    lookup = stripped
    ws_id = workspace_id if workspace_id is not None else resolve_workspace_id(ctx)
    normalized_lookup: str | None = None
    try:
        norm = workspace.normalize_remote(lookup)
        normalized_lookup = None if norm is None else norm.value
    except Exception:  # noqa: BLE001
        normalized_lookup = None

    matches: list[workspace.RepositoryView] = []
    after: str | None = None
    while True:
        page = cast(
            "workspace.ListRepositoriesView",
            ctx.client.ask(workspace.ListRepositories(workspace_id=ws_id, after=after, limit=100)),
        )
        matches.extend(
            item
            for item in page.items
            if item.title == lookup
            or (normalized_lookup is not None and item.canonical_remote == normalized_lookup)
        )
        if page.next is None:
            break
        after = page.next

    if not matches:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            f"repository not found: {raw!r}",
            details={"kind": "repository", "ref": raw},
        )
    if len(matches) > 1:
        raise ValidationFailed(
            ErrorCode.AMBIGUOUS_REFERENCE,
            f"repository reference {raw!r} matches multiple repositories",
            details={
                "kind": "repository",
                "ref": raw,
                "candidates": [str(m.repository_id) for m in matches],
            },
        )
    return RepositoryId(matches[0].repository_id)


def _default_repo_title(remote_url: str | None) -> str:
    if not remote_url:
        return "repository"
    try:
        norm = workspace.normalize_remote(remote_url)
        candidate = norm.value if norm is not None else remote_url
    except Exception:  # noqa: BLE001
        candidate = remote_url
    cleaned = candidate.rstrip("/").removesuffix(".git")
    tail = cleaned.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return tail or "repository"


def _register_repo(args: argparse.Namespace, ctx: CliContext) -> int:
    ws_id = resolve_workspace_id(ctx, getattr(args, "workspace", None))
    remote_url = args.remote or getattr(args, "remote_flag", None)
    title = args.title or _default_repo_title(remote_url)
    result = cast(
        "workspace.RegisterRepositoryResult",
        ctx.client.dispatch(
            workspace.RegisterRepository(
                workspace_id=ws_id,
                title=title,
                remote_url=remote_url,
                external_id=args.external_id,
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
                ("repository_id", value.repository_id),
                ("canonical_remote", value.canonical_remote),
                ("provider", value.provider),
            ],
        ),
        command=args.command_name,
        essential=lambda value: str(value.repository_id),
    )


def _add_remote(args: argparse.Namespace, ctx: CliContext) -> int:
    ws_id = resolve_workspace_id(ctx)
    repo_id = resolve_repository_id(ctx, args.repository, workspace_id=ws_id)
    result = cast(
        "workspace.AddRepositoryRemoteResult",
        ctx.client.dispatch(
            workspace.AddRepositoryRemote(
                repository_id=repo_id,
                url=args.url,
                make_primary=bool(args.primary),
            ),
            idempotency_key=ctx.new_idempotency_key(),
        ),
    )
    return render(
        ctx,
        result,
        human=lambda value: [f"added remote to {value.repository_id}"],
        command=args.command_name,
        essential=lambda value: str(value.repository_id),
    )


def _attach(args: argparse.Namespace, ctx: CliContext) -> int:
    ws_id = resolve_workspace_id(ctx)
    proj_id = resolve_project_id(ctx, args.project)
    repo_id = resolve_repository_id(ctx, args.repository, workspace_id=ws_id)
    role_map: dict[str, Literal["primary", "secondary", "docs", "infra"]] = {
        "primary": "primary",
        "secondary": "secondary",
        "dependency": "secondary",
        "docs": "docs",
        "reference": "docs",
        "infra": "infra",
    }
    role = role_map.get(args.role, "primary")
    result = cast(
        "workspace.AttachRepositoryResult",
        ctx.client.dispatch(
            workspace.AttachRepository(
                project_id=proj_id,
                repository_id=repo_id,
                mount_name=args.mount,
                role=role,
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
                ("repository_id", value.repository_id),
                ("mount_name", value.mount_name),
            ],
        ),
        command=args.command_name,
        essential=lambda value: f"{value.project_id}:{value.mount_name}",
    )


def _detach(args: argparse.Namespace, ctx: CliContext) -> int:
    proj_id = resolve_project_id(ctx, args.project)
    result = cast(
        "workspace.DetachRepositoryResult",
        ctx.client.dispatch(
            workspace.DetachRepository(project_id=proj_id, mount_name=args.mount_name),
            idempotency_key=ctx.new_idempotency_key(),
        ),
    )
    return render(
        ctx,
        result,
        human=lambda value: [f"detached mount {value.mount_name} from {value.project_id}"],
        command=args.command_name,
        essential=lambda value: str(value.mount_name),
    )


def _operate(
    ctx: CliContext, verb: Literal["bind", "verify"], payload: dict[str, Any], request_id: UUID | None
) -> dict[str, Any]:
    if isinstance(ctx, CliSession) and ctx.checkout_operation is not None:
        return ctx.checkout_operation(verb, payload, request_id)
    report = run_workspace_host_op(ctx, _COMMAND[verb], payload)
    return cast("dict[str, Any]", report.to_json())


def _bind(args: argparse.Namespace, ctx: CliContext) -> int:
    ws_id = resolve_workspace_id(ctx)
    proj_id: ProjectId | None = None
    if args.project is not None:
        proj_id = resolve_project_id(ctx, args.project)
    else:
        try:
            proj_id = resolve_project_id(ctx, None)
        except Exception:  # noqa: BLE001
            proj_id = None

    repo_id = None if args.repo is None else resolve_repository_id(ctx, args.repo, workspace_id=ws_id)
    assume_yes = bool(getattr(args, "yes", False) or ctx.assume_yes)
    inst_id = getattr(ctx, "instance_id", None)
    target_path = args.path or getattr(args, "positional_path", None) or "."

    def _confirm(decision: workspace.AttachDecisionView) -> bool:
        return ctx.confirm(f"Bind checkout to existing repository {decision.repository_id}?")

    payload = _operate(
        ctx,
        "bind",
        {
            "workspace_id": ws_id,
            "path": str(Path(target_path).absolute()),
            "project_id": proj_id,
            "repository_id": repo_id,
            "mount_name": args.mount,
            "role": args.role,
            "title": args.title,
            "assume_yes": assume_yes,
            "register_missing": bool(args.register),
            "write_marker": bool(args.write_marker),
            "instance_id": inst_id if isinstance(inst_id, UUID) else None,
            "confirm": None if assume_yes else _confirm,
        },
        args.request_id,
    )

    def _human_bind(value: dict[str, Any]) -> list[str]:
        lines = kv_lines(
            ctx,
            [
                ("binding_id", value["binding_id"]),
                ("repository_id", value["repository_id"]),
                ("project_id", value["project_id"]),
                ("mount_name", value["mount_name"]),
                ("state", value["state"]),
                ("reason", value["reason"]),
                ("marker_written", value["marker_written"]),
            ],
        )
        if value.get("marker_written"):
            lines.append(
                safe_text(ctx, 'hint: git add .skm/project.json && git commit -m "chore: bind skm project"')
            )
        return lines

    return render(
        ctx,
        payload,
        human=_human_bind,
        command=args.command_name,
        essential=lambda value: str(value["binding_id"]),
    )


def _verify(args: argparse.Namespace, ctx: CliContext) -> int:
    proj_id = resolve_project_id(ctx, args.project)
    repo_id: RepositoryId | None = None
    if args.repo is not None:
        ws_id = resolve_workspace_id(ctx)
        repo_id = resolve_repository_id(ctx, args.repo, workspace_id=ws_id)

    payload = _operate(
        ctx,
        "verify",
        {"project_id": proj_id, "repository_id": repo_id, "mount_name": args.mount},
        args.request_id,
    )
    return render(
        ctx,
        payload,
        human=lambda value: (
            render_table(
                ctx,
                ("mount", "binding_id", "state", "reason", "row_version"),
                [
                    [
                        item["mount_name"] or "-",
                        item["binding_id"],
                        item["state"],
                        item["reason"],
                        item["row_version"],
                    ]
                    for item in value["items"]
                ],
            )
            if value["items"]
            else ["no bound checkouts"]
        ),
        command=args.command_name,
        essential=lambda value: "\n".join(str(item["binding_id"]) for item in value["items"]),
    )


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    if args.project is not None or args.mounts:
        proj_id = resolve_project_id(ctx, args.project)
        try:
            host_id = resolve_host_id(ctx, args.host)
        except Exception:  # noqa: BLE001
            host_id = None
        mounts_view = cast(
            "workspace.ListProjectRepositoriesView",
            ctx.client.ask(workspace.ListProjectRepositories(project_id=proj_id, host_id=host_id)),
        )
        return render(
            ctx,
            mounts_view,
            human=lambda value: (
                render_table(
                    ctx,
                    ("mount", "role", "repository_id", "title", "binding_state"),
                    [
                        [
                            m.mount_name,
                            m.role,
                            m.repository.repository_id,
                            m.repository.title,
                            "-" if m.binding is None else m.binding.state,
                        ]
                        for m in value.items
                    ],
                )
                if value.items
                else ["no mounted repositories"]
            ),
            command="workspace.list_project_repositories",
            essential=lambda value: "\n".join(str(m.repository.repository_id) for m in value.items),
        )

    ws_id = resolve_workspace_id(ctx)
    view = cast(
        "workspace.ListRepositoriesView",
        ctx.client.ask(
            workspace.ListRepositories(
                workspace_id=ws_id,
                after=args.after,
                limit=args.limit,
            )
        ),
    )

    def human(value: workspace.ListRepositoriesView) -> list[str]:
        if not value.items:
            return ["no repositories"]
        rows = [
            [item.repository_id, item.title, item.provider, item.canonical_remote or "-"]
            for item in value.items
        ]
        lines = render_table(ctx, ("repository_id", "title", "provider", "canonical_remote"), rows)
        if value.next is not None:
            lines.append(safe_text(ctx, f"next: {value.next} (use --after)"))
        return lines

    return render(
        ctx,
        view,
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(str(item.repository_id) for item in value.items),
    )


_HANDLERS = {
    "register": _register_repo,
    "add-remote": _add_remote,
    "attach": _attach,
    "detach": _detach,
    "bind": _bind,
    "verify": _verify,
    "list": _list,
}


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("repo", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", metavar="VERB", required=True)
    for verb in ("register", "add-remote", "attach", "detach", "bind", "verify", "list"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
        if verb == "register":
            command.add_argument("remote", nargs="?", default=None, metavar="REMOTE")
            command.add_argument("--workspace")
            command.add_argument("--title")
            command.add_argument("--remote", dest="remote_flag", help=argparse.SUPPRESS)
            command.add_argument("--external-id")
        if verb == "add-remote":
            command.add_argument("repository")
            command.add_argument("url")
            command.add_argument("--primary", action="store_true")
        if verb == "attach":
            command.add_argument("repository")
            command.add_argument("--project")
            command.add_argument("--mount", default="main")
            command.add_argument(
                "--role",
                choices=("primary", "secondary", "docs", "infra", "dependency", "reference"),
                default="primary",
            )
        if verb == "detach":
            command.add_argument("mount_name")
            command.add_argument("--project")
        if verb == "bind":
            command.add_argument(
                "positional_path",
                nargs="?",
                default=None,
                metavar="PATH",
                help=argparse.SUPPRESS,
            )
            command.add_argument("--path", dest="path", default=None)
            command.add_argument("--project")
            command.add_argument("--repo")
            command.add_argument("--mount", default="main")
            command.add_argument(
                "--role",
                choices=("primary", "secondary", "docs", "infra", "dependency", "reference"),
                default="primary",
            )
            command.add_argument("--title")
            command.add_argument("--register", action="store_true")
            command.add_argument("--write-marker", action="store_true")
            command.add_argument("--yes", action="store_true")
        if verb in {"bind", "verify"}:
            command.add_argument(
                "--request-id", type=UUID, help="reuse a checkout request after interruption"
            )
        if verb == "verify":
            command.add_argument("--project")
            command.add_argument("--repo")
            command.add_argument("--mount")
        if verb == "list":
            command.add_argument("--project")
            command.add_argument("--mounts", action="store_true")
            command.add_argument("--host")
            command.add_argument("--after")
            command.add_argument("--limit", type=int, default=50)
        command.set_defaults(run=_HANDLERS[verb], command_name=_COMMAND[verb])


GROUP = CommandGroup(
    name="repo",
    help="register, attach, detach, bind, verify and list repositories",
    register=register,
    requires_backend=True,
    module="workspace",
    order=12,
)
