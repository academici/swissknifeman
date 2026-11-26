"""``skm worker`` (cli §6, workspace §10, access §6.3): register, rotate, list, show, drain and retire."""

from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from skm import __version__
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.host import resolve_host_view, run_workspace_host_op
from skm.entrypoints.cli.commands.workspace import resolve_workspace_id
from skm.entrypoints.cli.context import CliSession
from skm.entrypoints.cli.output import kv_lines, render, render_table, safe_text
from skm.entrypoints.cli.refs import as_uuid
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import WorkerId, WorkspaceId
from skm.modules.workspace import public as workspace
from skm.platform.fs.atomic_write import atomic_write

if TYPE_CHECKING:
    from skm.entrypoints.cli.context import CliContext

__all__ = ["GROUP", "register", "resolve_worker_view", "worker_token_path"]

_HELP = {
    "start": "start the worker host loop",
    "register": "register a worker or rotate a worker token",
    "list": "list workers in the active workspace",
    "show": "show details of a worker",
    "status": "show status of a worker",
    "drain": "transition a worker to draining state",
    "retire": "retire a worker and revoke its tokens",
}

_COMMAND = {
    "start": "worker.start",
    "register": "workspace.register_worker",
    "list": "workspace.list_workers",
    "show": "workspace.list_workers",
    "status": "workspace.list_workers",
    "drain": "workspace.set_worker_state",
    "retire": "workspace.set_worker_state",
}


def worker_token_path(ctx: CliContext, worker_id: WorkerId, explicit_path: str | None = None) -> Path:
    """Resolve the ``0600`` secret file path ``<state_dir>/secrets/workers/<worker_id>.token``."""
    if explicit_path is not None:
        return Path(explicit_path)
    state_dir = getattr(ctx, "state_dir", None)
    if isinstance(state_dir, Path):
        return state_dir / "secrets" / "workers" / f"{worker_id}.token"
    env = dict(ctx.environ) if isinstance(ctx, CliSession) else {}
    cwd_raw = getattr(ctx, "cwd", None)
    cwd = cwd_raw if isinstance(cwd_raw, Path) else Path.cwd()
    base = (
        Path(env["XDG_STATE_HOME"])
        if env.get("XDG_STATE_HOME")
        else (Path(env["HOME"]) if env.get("HOME") else cwd) / ".local/state"
    )
    return base / "skm" / "secrets" / "workers" / f"{worker_id}.token"


def _ensure_private_dir(path: Path) -> None:
    created = False
    if not path.exists() and not path.is_symlink():
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        created = True
    try:
        st = path.lstat()
    except OSError as err:
        raise PreconditionFailed(
            ErrorCode.SECRET_PERMISSIONS,
            f"cannot stat secrets directory {path}: {err}",
            details={"path": str(path)},
        ) from err
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise PreconditionFailed(
            ErrorCode.SECRET_PERMISSIONS,
            f"secrets directory {path} must be a regular directory, not a symlink",
            details={"path": str(path)},
        )
    if created and (stat.S_IMODE(st.st_mode) & 0o077) != 0:
        os.chmod(path, 0o700)
        st = path.lstat()
    if st.st_uid != os.geteuid() or (stat.S_IMODE(st.st_mode) & 0o077) != 0:
        raise PreconditionFailed(
            ErrorCode.SECRET_PERMISSIONS,
            f"secrets directory {path} must be owned by current user with 0700 permissions",
            details={"path": str(path), "mode": oct(stat.S_IMODE(st.st_mode))},
        )


def _prepare_worker_token_target(
    ctx: CliContext,
    worker_id: WorkerId,
    explicit_path: str | None = None,
) -> Path:
    target = worker_token_path(ctx, worker_id, explicit_path)
    if explicit_path is None:
        secrets_dir = target.parent.parent
        secrets_dir.parent.mkdir(parents=True, exist_ok=True)
        _ensure_private_dir(secrets_dir)
        _ensure_private_dir(target.parent)
    else:
        _ensure_private_dir(target.parent)
    if target.exists() or target.is_symlink():
        st = target.lstat()
        if (
            stat.S_ISLNK(st.st_mode)
            or not stat.S_ISREG(st.st_mode)
            or st.st_uid != os.geteuid()
            or (stat.S_IMODE(st.st_mode) & 0o077) != 0
        ):
            raise PreconditionFailed(
                ErrorCode.SECRET_PERMISSIONS,
                f"worker token file {target} must be a 0600 regular file owned by current user",
                details={"path": str(target), "mode": oct(stat.S_IMODE(st.st_mode))},
            )
    return target


def _save_worker_token_file(
    ctx: CliContext,
    worker_id: WorkerId,
    secret: str,
    explicit_path: str | None = None,
) -> str:
    target = _prepare_worker_token_target(ctx, worker_id, explicit_path)
    atomic_write(target, (secret + "\n").encode("utf-8"), mode=0o600, private=True)
    return str(target)


def resolve_worker_view(
    ctx: CliContext,
    raw: str,
    *,
    workspace_id: WorkspaceId | None = None,
) -> workspace.WorkerView:
    """Resolve a worker reference (UUID, ``worker:<uuid>`` or display_name) to ``WorkerView``."""
    stripped = raw.removeprefix("worker:")
    by_uuid = as_uuid(stripped)
    ws_id = workspace_id if workspace_id is not None else resolve_workspace_id(ctx)

    matches: list[workspace.WorkerView] = []
    after: str | None = None
    while True:
        page = cast(
            "workspace.ListWorkersView",
            ctx.client.ask(workspace.ListWorkers(workspace_id=ws_id, after=after, limit=100)),
        )
        for item in page.items:
            if by_uuid is not None:
                if WorkerId(item.worker_id) == WorkerId(by_uuid):
                    return item
            elif item.display_name == stripped:
                matches.append(item)
        if page.next is None:
            break
        after = page.next

    if not matches:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            f"worker not found: {raw!r}",
            details={"kind": "worker", "ref": raw},
        )
    if len(matches) > 1:
        raise ValidationFailed(
            ErrorCode.AMBIGUOUS_REFERENCE,
            f"worker reference {raw!r} matches multiple workers",
            details={
                "kind": "worker",
                "ref": raw,
                "candidates": [str(m.worker_id) for m in matches],
            },
        )
    return matches[0]


def _register_or_rotate(args: argparse.Namespace, ctx: CliContext) -> int:
    positional_name = getattr(args, "worker_name", None)
    if args.rotate:
        worker_ref = args.worker or args.name or positional_name
        target_worker_id: WorkerId | None = None
        if worker_ref is not None:
            stripped = str(worker_ref).removeprefix("worker:")
            by_uuid = as_uuid(stripped)
            if by_uuid is not None:
                target_worker_id = WorkerId(by_uuid)
            else:
                target_worker_id = WorkerId(resolve_worker_view(ctx, str(worker_ref)).worker_id)

        should_save = bool(args.save_token or args.token_file)

        def _validate_target(w_id: WorkerId | None) -> None:
            if not should_save:
                return
            resolved_w_id = w_id or target_worker_id
            if resolved_w_id is None and args.token_file is None:
                raise PreconditionFailed(
                    ErrorCode.SCHEMA_INVALID,
                    "worker_id or --token-file is required to save rotated worker token",
                    details={"reason": "worker_id_required_for_save"},
                )
            fallback_id = resolved_w_id or WorkerId(UUID(int=0))
            _prepare_worker_token_target(ctx, fallback_id, args.token_file)

        def _save_secret(w_id: WorkerId | None, secret: str) -> str | None:
            if not should_save:
                return None
            resolved_w_id = w_id or target_worker_id
            if resolved_w_id is None and args.token_file is None:
                raise PreconditionFailed(
                    ErrorCode.SCHEMA_INVALID,
                    "worker_id or --token-file is required to save rotated worker token",
                    details={"reason": "worker_id_required_for_save"},
                )
            fallback_id = resolved_w_id or WorkerId(UUID(int=0))
            return _save_worker_token_file(ctx, fallback_id, secret, args.token_file)

        report = run_workspace_host_op(
            ctx,
            "workspace.host.rotate_worker_token",
            {
                "worker_id": target_worker_id,
                "operator_mode": bool(worker_ref is not None or args.operator),
                "force": bool(args.force),
                "grace_minutes": args.grace_minutes,
                "validate_target": _validate_target,
                "register_secret": ctx.redactor.register_secret,
                "save_secret": _save_secret,
            },
            allow_unregistered_host=True,
        )
        payload = cast("dict[str, Any]", report.to_json())
        return render(
            ctx,
            payload,
            human=lambda value: kv_lines(
                ctx,
                [
                    ("rotated", value["rotated"]),
                    ("worker_id", value["worker_id"]),
                    ("principal_id", value["principal_id"]),
                    ("old_token_id", value["old_token_id"]),
                    ("new_token_id", value["new_token_id"]),
                    ("saved_path", value["saved_path"]),
                ],
            ),
            command="workspace.host.rotate_worker_token",
            essential=lambda value: str(value["new_token_id"] or value["old_token_id"]),
        )

    ws_id = resolve_workspace_id(ctx)
    host_view = resolve_host_view(ctx, args.host, workspace_id=ws_id)
    display_name = args.name or positional_name or f"{host_view.name}-worker"
    os_val = args.os or host_view.platform.os.value
    arch_val = args.arch or host_view.platform.arch.value
    runtimes = tuple(args.runtime or ())
    isolations = tuple(args.isolation or ("worktree",))
    labels = tuple(args.label or ())

    capabilities_payload: dict[str, Any] = {
        "runtimes": list(runtimes),
        "isolation_profiles": list(isolations),
        "max_concurrency": args.max_concurrency,
        "labels": list(labels),
        "platform": {"os": os_val, "arch": arch_val},
        # Claim admission compares numeric release versions on the wire.
        "skm_version": args.skm_version or __version__.partition(".dev")[0],
    }
    dto = workspace.RegisterWorker.from_json(
        {
            "workspace_id": str(ws_id),
            "host_id": str(host_view.host_id),
            "display_name": display_name,
            "capabilities": capabilities_payload,
        }
    )
    # workspace.register_worker has IdempotencyMode.FORBIDDEN (secret-bearing command)
    result = cast("workspace.RegisterWorkerResult", ctx.client.dispatch(dto))

    if args.save_token or args.token_file:
        ctx.redactor.register_secret(result.token_secret)
        saved_path = _save_worker_token_file(
            ctx,
            WorkerId(result.worker_id),
            result.token_secret,
            args.token_file,
        )
        out_doc: dict[str, Any] = {
            "worker_id": str(result.worker_id),
            "principal_id": str(result.principal_id),
            "token_file": saved_path,
        }
        return render(
            ctx,
            out_doc,
            human=lambda value: kv_lines(
                ctx,
                [
                    ("worker_id", value["worker_id"]),
                    ("principal_id", value["principal_id"]),
                    ("token_file", value["token_file"]),
                ],
            ),
            command=args.command_name,
            essential=lambda value: str(value["worker_id"]),
        )

    try:
        return render(
            ctx,
            result,
            human=lambda value: [
                "Save this worker token now; it will not be shown again.",
                *kv_lines(
                    ctx,
                    [
                        ("worker_id", value.worker_id),
                        ("principal_id", value.principal_id),
                        ("token_secret", value.token_secret),
                    ],
                ),
            ],
            command=args.command_name,
            essential=lambda value: value.token_secret,
        )
    finally:
        ctx.redactor.register_secret(result.token_secret)


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    ws_id = resolve_workspace_id(ctx)
    state_filter = cast(
        "Literal['online', 'draining', 'offline', 'retired'] | None",
        None if args.state is None else ("online" if args.state == "active" else args.state),
    )
    view = cast(
        "workspace.ListWorkersView",
        ctx.client.ask(
            workspace.ListWorkers(
                workspace_id=ws_id,
                state=state_filter,
                after=args.after,
                limit=args.limit,
            )
        ),
    )

    def human(value: workspace.ListWorkersView) -> list[str]:
        if not value.items:
            return ["no workers"]
        rows = [
            [
                item.worker_id,
                item.display_name,
                item.host_id,
                item.state,
                item.capabilities.max_concurrency,
            ]
            for item in value.items
        ]
        lines = render_table(
            ctx,
            ("worker_id", "display_name", "host_id", "state", "max_concurrency"),
            rows,
        )
        if value.next is not None:
            lines.append(safe_text(ctx, f"next: {value.next} (use --after)"))
        return lines

    return render(
        ctx,
        view,
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(str(item.worker_id) for item in value.items),
    )


def _show(args: argparse.Namespace, ctx: CliContext) -> int:
    view = resolve_worker_view(ctx, args.worker)
    return render(
        ctx,
        view,
        human=lambda value: kv_lines(
            ctx,
            [
                ("worker_id", value.worker_id),
                ("workspace_id", value.workspace_id),
                ("host_id", value.host_id),
                ("display_name", value.display_name),
                ("state", value.state),
                ("runtimes", ", ".join(value.capabilities.runtimes) or "-"),
                ("isolation_profiles", ", ".join(value.capabilities.isolation_profiles) or "-"),
                ("max_concurrency", value.capabilities.max_concurrency),
                ("labels", ", ".join(value.capabilities.labels) or "-"),
                ("row_version", value.row_version),
            ],
        ),
        command=args.command_name,
        essential=lambda value: str(value.worker_id),
    )


def _set_state(
    args: argparse.Namespace,
    ctx: CliContext,
    target_state: Literal["online", "draining", "retired"],
) -> int:
    view = resolve_worker_view(ctx, args.worker)
    expected = args.expected_version if args.expected_version is not None else view.row_version
    result = cast(
        "workspace.SetWorkerStateResult",
        ctx.client.dispatch(
            workspace.SetWorkerState(
                worker_id=WorkerId(view.worker_id),
                state=target_state,
                expected_row_version=expected,
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
                ("worker_id", value.worker_id),
                ("state", value.state),
                ("row_version", value.row_version),
            ],
        ),
        command=args.command_name,
        essential=lambda value: str(value.worker_id),
    )


def _drain(args: argparse.Namespace, ctx: CliContext) -> int:
    return _set_state(args, ctx, "draining")


def _retire(args: argparse.Namespace, ctx: CliContext) -> int:
    return _set_state(args, ctx, "retired")


def _start(args: argparse.Namespace, ctx: CliContext) -> int:
    from skm.entrypoints.cli._run_worker import start

    return start(args, ctx)


_HANDLERS = {
    "start": _start,
    "register": _register_or_rotate,
    "list": _list,
    "show": _show,
    "status": _show,
    "drain": _drain,
    "retire": _retire,
}


def register(sub: SubParsers) -> None:
    from skm.entrypoints.cli._run_worker import positive_capacity

    parser = sub.add_parser("worker", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", metavar="VERB", required=True)
    for verb in ("start", "register", "list", "show", "status", "drain", "retire"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
        if verb == "start":
            command.add_argument("--once", action="store_true")
            command.add_argument("--capacity", type=positive_capacity)
            command.add_argument("--token")
            command.add_argument("--worker")
        if verb == "register":
            command.add_argument("worker_name", nargs="?", default=None, metavar="NAME")
            command.add_argument("--name")
            command.add_argument("--host")
            command.add_argument("--runtime", action="append")
            command.add_argument("--isolation", action="append")
            command.add_argument("--label", action="append")
            command.add_argument("--max-concurrency", type=int, default=1)
            command.add_argument("--os", choices=("linux", "macos", "windows"))
            command.add_argument("--arch", choices=("x86_64", "arm64", "other"))
            command.add_argument("--skm-version")
            command.add_argument("--save-token", dest="save_token", default=True, action="store_true")
            command.add_argument(
                "--no-save-token",
                dest="save_token",
                action="store_false",
                help=argparse.SUPPRESS,
            )
            command.add_argument("--token-file")
            command.add_argument("--rotate", action="store_true")
            command.add_argument("--worker")
            command.add_argument("--operator", action="store_true")
            command.add_argument("--force", action="store_true")
            command.add_argument("--grace-minutes", type=int)
        if verb == "list":
            command.add_argument(
                "--state",
                choices=("online", "active", "draining", "offline", "retired"),
            )
            command.add_argument("--after")
            command.add_argument("--limit", type=int, default=50)
        if verb in ("show", "status"):
            command.add_argument("worker")
        if verb in ("drain", "retire"):
            command.add_argument("worker")
            command.add_argument("--expected-version", type=int)
        command.set_defaults(run=_HANDLERS[verb], command_name=_COMMAND[verb])


GROUP = CommandGroup(
    name="worker",
    help="start, register, rotate, list, show, drain and retire workers",
    register=register,
    requires_backend=True,
    module="workspace",
    order=15,
)
