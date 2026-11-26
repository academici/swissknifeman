"""``skm use`` (cli §3.1, §6): select or inspect the active workspace/project/instance CLI context.

Updates local ``cli-context.json`` and ``cli-state.json`` atomically without mutating database authority.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_view
from skm.entrypoints.cli.commands.workspace import resolve_workspace_view
from skm.entrypoints.cli.context import CONTEXT_SCHEMA, CliSession
from skm.entrypoints.cli.output import kv_lines, render
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.modules.settings import public as settings
from skm.modules.workspace import public as workspace
from skm.platform.config.sources.bootstrap import cli_state_path as profile_state_path
from skm.platform.config.sources.bootstrap import edit_cli_state, read_cli_state, save_selection
from skm.platform.fs.atomic_write import atomic_write

if TYPE_CHECKING:
    from skm.entrypoints.cli.context import CliContext
    from skm.kernel.json_types import JsonObject

__all__ = ["GROUP", "cli_context_path", "cli_state_path", "register", "selects_instance_only"]

_HELP = {
    "": "select or inspect the active workspace, project and instance context",
}


def _environ(ctx: CliContext) -> dict[str, str]:
    return dict(ctx.environ) if isinstance(ctx, CliSession) else {}


def _cwd(ctx: CliContext) -> Path:
    cwd = getattr(ctx, "cwd", None)
    return cwd if isinstance(cwd, Path) else Path.cwd()


def _home(environ: Mapping[str, str], cwd: Path) -> Path:
    raw = environ.get("HOME")
    return Path(raw) if raw else cwd


def cli_context_path(ctx: CliContext) -> Path:
    state_dir = getattr(ctx, "state_dir", None)
    if isinstance(state_dir, Path):
        return state_dir / "cli-context.json"
    env = _environ(ctx)
    base = (
        Path(env["XDG_STATE_HOME"]) if env.get("XDG_STATE_HOME") else _home(env, _cwd(ctx)) / ".local/state"
    )
    return base / "skm/cli-context.json"


def cli_state_path(ctx: CliContext) -> Path:
    if isinstance(ctx, CliSession):
        return profile_state_path(ctx.environ, ctx.home)
    return profile_state_path(_environ(ctx), _home(_environ(ctx), _cwd(ctx)))


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return {}
    return dict(cast("Mapping[str, Any]", data)) if isinstance(data, Mapping) else {}


def _write_context_and_state(
    ctx: CliContext,
    context_doc: dict[str, Any],
    *,
    current_instance: str | None = None,
    update_current_instance: bool = False,
    checkout_binding: tuple[str, str | None] | None = None,
) -> None:
    changes = {
        "workspace_id": cast("str | None", context_doc.get("workspace_id")),
        "workspace_slug": cast("str | None", context_doc.get("workspace_slug")),
        "project_id": cast("str | None", context_doc.get("project_id")),
        "project_slug": cast("str | None", context_doc.get("project_slug")),
    }
    state_dir = getattr(ctx, "state_dir", None)
    saved_via_ctx = False
    managed = isinstance(ctx, CliSession) and ctx.machine_store is not None
    remote = isinstance(ctx, CliSession) and ctx.remote_identity is not None
    if managed or remote or isinstance(state_dir, Path):
        ctx.save_context(**changes)
        saved_via_ctx = True

    if not saved_via_ctx:
        clean_doc: dict[str, Any] = {
            "schema": CONTEXT_SCHEMA,
            **{k: v for k, v in changes.items() if v is not None},
        }
        instance_id = getattr(ctx, "instance_id", None)
        if instance_id is not None:
            clean_doc["instance_id"] = str(instance_id)
        ctx_bytes = (json.dumps(clean_doc, indent=2, sort_keys=True) + "\n").encode("utf-8")
        ctx_file = cli_context_path(ctx)
        ctx_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(ctx_file, ctx_bytes, mode=0o600)

    with edit_cli_state(cli_state_path(ctx)) as state_doc:
        bindings = cast("dict[str, str]", state_doc["checkout_bindings"])
        if checkout_binding is not None:
            chk_path, chk_instance = checkout_binding
            if chk_instance is None:
                bindings.pop(chk_path, None)
            else:
                bindings[chk_path] = chk_instance
        if update_current_instance:
            if current_instance is None:
                state_doc.pop("current_instance", None)
            else:
                state_doc["current_instance"] = current_instance
        if managed:
            state_doc.pop("last_workspace_id", None)
            state_doc.pop("last_project_id", None)
        else:
            state_doc["last_workspace_id"] = changes.get("workspace_id")
            state_doc["last_project_id"] = changes.get("project_id")


def _find_marker(start: Path, *, verified: bool = False) -> dict[str, Any] | None:
    if verified:
        from skm.bootstrap.instance_profiles import verified_checkout_marker

        return verified_checkout_marker(start)
    current = start.resolve()
    for directory in (current, *current.parents):
        candidate = directory / ".skm/project.json"
        if candidate.is_file():
            try:
                loaded = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                loaded = None
            if isinstance(loaded, Mapping):
                return dict(cast("Mapping[str, Any]", loaded))
    return None


def _assert_active(
    ws_view: workspace.WorkspaceView | None,
    proj_view: workspace.ProjectView | None,
) -> None:
    if ws_view is not None and ws_view.state != "active":
        raise PreconditionFailed(
            ErrorCode.PROJECT_ARCHIVED,
            f"workspace {ws_view.slug!r} is not active ({ws_view.state})",
            details={"workspace_id": str(ws_view.workspace_id), "state": ws_view.state},
        )
    if proj_view is not None and proj_view.state != "active":
        raise PreconditionFailed(
            ErrorCode.PROJECT_ARCHIVED,
            f"project {proj_view.slug!r} is archived",
            details={"project_id": str(proj_view.project_id), "state": proj_view.state},
        )


def _resolve_default_project(
    ctx: CliContext,
    ws_view: workspace.WorkspaceView,
) -> workspace.ProjectView | None:
    try:
        val_view = cast(
            "settings.GetValueView",
            ctx.client.ask(
                settings.GetValue.from_json(
                    {
                        "key": "workspace.default_project",
                        "scope": {"level": "workspace", "scope_id": str(ws_view.workspace_id)},
                    }
                )
            ),
        )
    except Exception:  # noqa: BLE001
        return None
    default_ref = val_view.value
    if isinstance(default_ref, str) and default_ref.strip():
        return resolve_project_view(ctx, default_ref.strip(), workspace_ref=ws_view.slug)
    return None


def _resolve_target(
    ctx: CliContext,
    target: str | None,
    project_flag: str | None,
) -> tuple[workspace.WorkspaceView | None, workspace.ProjectView | None]:
    if target is None and project_flag is None:
        return None, None

    if target is not None:
        if "/" in target or target.startswith(("proj:", "project:")):
            proj_view = resolve_project_view(ctx, target)
            ws_view = cast(
                "workspace.WorkspaceView",
                ctx.client.ask(workspace.GetWorkspace(workspace_id=WorkspaceId(proj_view.workspace_id))),
            )
            _assert_active(ws_view, proj_view)
            return ws_view, proj_view
        ws_view = resolve_workspace_view(ctx, target)
        if project_flag is not None:
            proj_view = resolve_project_view(ctx, project_flag, workspace_ref=ws_view.slug)
            _assert_active(ws_view, proj_view)
            return ws_view, proj_view
        default_proj = _resolve_default_project(ctx, ws_view)
        _assert_active(ws_view, default_proj)
        return ws_view, default_proj

    proj_view = resolve_project_view(ctx, project_flag)
    ws_view = cast(
        "workspace.WorkspaceView",
        ctx.client.ask(workspace.GetWorkspace(workspace_id=WorkspaceId(proj_view.workspace_id))),
    )
    _assert_active(ws_view, proj_view)
    return ws_view, proj_view


def selects_instance_only(args: argparse.Namespace) -> bool:
    if args.clear and any(ref is not None for ref in (args.target, args.project_ref, args.workspace_ref)):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "--clear conflicts with a workspace or project reference"
        )
    return (
        args.target is None
        and args.workspace_ref is None
        and args.project_ref is None
        and (args.instance_name is not None or (args.here and args.clear))
    )


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    if selects_instance_only(args):
        directory = _cwd(ctx).resolve() if args.here else None
        name = None if args.clear else args.instance_name
        state = save_selection(cli_state_path(ctx), name=name, directory=directory)
        result = {
            "instance": name,
            "checkout": str(directory) if directory else None,
            "checkout_bindings": state["checkout_bindings"],
        }
        message = "cleared instance selection" if args.clear else f"using instance {name}"
        if directory is not None:
            message += f" in {directory}"
        return render(
            ctx, result, command=args.command_name, human=lambda _: message, essential=lambda _: name or ""
        )

    current = (
        ctx.load_context()
        if isinstance(ctx, CliSession)
        and (ctx.state_dir is not None or ctx.machine_store is not None or ctx.remote_identity is not None)
        else _read_json_file(cli_context_path(ctx))
    )
    current_state = read_cli_state(cli_state_path(ctx))
    selected = ctx.options.instance if isinstance(ctx, CliSession) else None
    effective_instance = selected or current_state.get("current_instance")

    if args.here and args.target is None and args.workspace_ref is None and args.project_ref is None:
        cwd = _cwd(ctx).resolve()
        real_cwd = str(cwd)
        managed = isinstance(ctx, CliSession) and ctx.machine_store is not None
        marker = _find_marker(cwd, verified=managed)
        if marker is None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "no .skm/project.json marker found in current directory or parents",
                details={"cwd": real_cwd},
            )
        if isinstance(ctx, CliSession) and managed and marker.get("instance_id") != str(ctx.instance_id):
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Checkout marker belongs to another instance")

        ws_marker = marker.get("workspace_id")
        proj_marker = marker.get("project_id")
        if (
            not isinstance(ws_marker, str)
            or not ws_marker.strip()
            or not isinstance(proj_marker, str)
            or not proj_marker.strip()
        ):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "Invalid .skm/project.json marker",
                details={"reason": "invalid_checkout_marker", "cwd": real_cwd},
            )

        ws_id = WorkspaceId(resolve_workspace_view(ctx, ws_marker).workspace_id)
        proj_id = ProjectId(resolve_project_view(ctx, proj_marker).project_id)
        ws_view = cast("workspace.WorkspaceView", ctx.client.ask(workspace.GetWorkspace(workspace_id=ws_id)))
        proj_view = cast("workspace.ProjectView", ctx.client.ask(workspace.GetProject(project_id=proj_id)))
        _assert_active(ws_view, proj_view)
        updated: dict[str, Any] = {
            "schema": CONTEXT_SCHEMA,
            "instance": effective_instance,
            "workspace_id": str(ws_view.workspace_id),
            "workspace_slug": ws_view.slug,
            "project_id": str(proj_view.project_id),
            "project_slug": proj_view.slug,
        }
        _write_context_and_state(ctx, updated)
        return render(
            ctx,
            updated,
            human=lambda value: kv_lines(
                ctx,
                [
                    ("workspace_id", value["workspace_id"]),
                    ("workspace_slug", value["workspace_slug"]),
                    ("project_id", value["project_id"]),
                    ("project_slug", value["project_slug"]),
                ],
            ),
            command=args.command_name,
            essential=lambda value: f"{value['workspace_id']}/{value['project_id']}",
        )

    if args.clear:
        cleared: dict[str, Any] = {
            "schema": CONTEXT_SCHEMA,
            "instance": args.instance_name,
            "workspace_id": None,
            "workspace_slug": None,
            "project_id": None,
            "project_slug": None,
        }
        _write_context_and_state(
            ctx,
            cleared,
            current_instance=args.instance_name,
            update_current_instance=True,
        )
        return render(
            ctx,
            cleared,
            human=lambda _value: ["cleared CLI context"],
            command=args.command_name,
            essential=lambda _value: "",
        )

    if args.target is not None and args.workspace_ref is not None:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Choose one workspace reference")
    target = args.target or args.workspace_ref
    project_flag = args.project_ref
    instance_name = args.instance_name

    if target is not None or project_flag is not None or instance_name is not None:
        ws_view, proj_view = _resolve_target(ctx, target, project_flag)
        updated = {
            "schema": CONTEXT_SCHEMA,
            "instance": effective_instance,
            "workspace_id": str(ws_view.workspace_id) if ws_view is not None else current.get("workspace_id"),
            "workspace_slug": ws_view.slug if ws_view is not None else current.get("workspace_slug"),
            "project_id": str(proj_view.project_id)
            if proj_view is not None
            else (None if ws_view is not None else current.get("project_id")),
            "project_slug": proj_view.slug
            if proj_view is not None
            else (None if ws_view is not None else current.get("project_slug")),
        }
        _write_context_and_state(
            ctx,
            updated,
            current_instance=instance_name,
            update_current_instance=instance_name is not None and not args.here,
            checkout_binding=(str(_cwd(ctx).resolve()), instance_name)
            if args.here and instance_name is not None
            else None,
        )
        return render(
            ctx,
            updated,
            human=lambda value: kv_lines(
                ctx,
                [
                    ("instance", value.get("instance")),
                    ("workspace_id", value.get("workspace_id")),
                    ("workspace_slug", value.get("workspace_slug")),
                    ("project_id", value.get("project_id")),
                    ("project_slug", value.get("project_slug")),
                ],
            ),
            command=args.command_name,
            essential=lambda value: str(value.get("project_id") or value.get("workspace_id") or ""),
        )

    view_doc: JsonObject = {
        "schema": CONTEXT_SCHEMA,
        "instance": effective_instance,
        "workspace_id": current.get("workspace_id"),
        "workspace_slug": current.get("workspace_slug"),
        "project_id": current.get("project_id"),
        "project_slug": current.get("project_slug"),
    }
    return render(
        ctx,
        view_doc,
        human=lambda value: kv_lines(
            ctx,
            [
                ("instance", value.get("instance")),
                ("workspace_id", value.get("workspace_id")),
                ("workspace_slug", value.get("workspace_slug")),
                ("project_id", value.get("project_id")),
                ("project_slug", value.get("project_slug")),
            ],
        ),
        command=args.command_name,
        essential=lambda value: str(value.get("project_id") or value.get("workspace_id") or ""),
    )


def register(sub: SubParsers) -> None:
    for verb in ("",):
        command = sub.add_parser("use", help=_HELP[verb])
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
        command.add_argument("target", nargs="?")
        command.add_argument("--workspace", dest="workspace_ref")
        command.add_argument("--project", dest="project_ref")
        command.add_argument("--instance", dest="instance_name")
        command.add_argument("--here", action="store_true")
        command.add_argument("--clear", action="store_true")
        command.set_defaults(run=_run, command_name="cli.use")


GROUP = CommandGroup(
    name="use",
    help=_HELP[""],
    register=register,
    requires_backend=True,
    module="workspace",
    order=13,
)
