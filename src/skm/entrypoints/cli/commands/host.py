"""``skm host`` (cli §6, workspace §10): register, list and show hosts."""

from __future__ import annotations

import argparse
import json
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.workspace import resolve_workspace_id
from skm.entrypoints.cli.host import build_host_context
from skm.entrypoints.cli.output import kv_lines, render, render_table, safe_text
from skm.entrypoints.cli.refs import RefForm, RefKind, as_uuid, parse_ref
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    CapabilityUnavailable,
    InternalError,
    PreconditionFailed,
    ValidationFailed,
)
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, WorkspaceId
from skm.kernel.ports_uow import Surface
from skm.modules.workspace import public as workspace
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.file_lock import FileLock, LockTimeout
from skm.platform.logging.logger import get_logger

if TYPE_CHECKING:
    from skm.entrypoints.cli.context import CliContext
    from skm.kernel.module_manifest import HostOperationSpec

__all__ = [
    "GROUP",
    "register",
    "resolve_host_id",
    "resolve_host_view",
    "run_workspace_host_op",
]

_HELP = {
    "register": "register this host in the instance",
    "list": "list registered hosts",
    "show": "show a registered host",
}

_COMMAND = {
    "register": "workspace.host.register_this_host",
    "list": "workspace.list_hosts",
    "show": "workspace.get_host",
}


def _state_dir(ctx: CliContext) -> Path | None:
    val = getattr(ctx, "state_dir", None)
    return val if isinstance(val, Path) else None


def _find_workspace_host_spec(name: str) -> HostOperationSpec:
    for manifest in MANIFESTS:
        if manifest.id == "workspace":
            for op in manifest.host_operations:
                if op.name == name:
                    return op
    raise InternalError(
        ErrorCode.INTERNAL_ERROR,
        f"host operation {name} is not registered",
        details={"operation": name},
    )


def _fallback_host_context(ctx: CliContext) -> HostContext:
    recorded_id = _read_state_host_id(_state_dir(ctx)) or HostId(UUID(int=0))
    return HostContext(
        client=ctx.client,
        gateways=GatewayTable(entries={}, kind="host_gateway"),
        host_id=recorded_id,
        config={},
        log=get_logger("cli.host"),
        cancel=CancelSource().token,
    )


def run_workspace_host_op(
    ctx: CliContext,
    name: str,
    request: object,
    *,
    allow_unregistered_host: bool = False,
) -> Any:
    """Invoke a ``workspace.host.*`` operation on the CLI surface."""
    spec = _find_workspace_host_spec(name)
    if Surface.CLI not in spec.surfaces:
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            f"host operation {name} is not registered for CLI",
            details={"operation": name},
        )
    try:
        host_ctx = build_host_context(ctx)
        recorded = _read_state_host_id(_state_dir(ctx))
        if recorded is not None and recorded != host_ctx.host_id:
            host_ctx = replace(host_ctx, host_id=recorded)
    except (CapabilityUnavailable, PreconditionFailed, ValidationFailed):
        if not allow_unregistered_host:
            raise
        host_ctx = _fallback_host_context(ctx)
    return spec.run(host_ctx, request)


def _read_state_host_id(state_dir: Path | None) -> HostId | None:
    if state_dir is None:
        return None
    host_file = state_dir / "host.json"
    if not host_file.is_file():
        return None
    try:
        data = json.loads(host_file.read_text(encoding="utf-8"))
        return HostId(UUID(str(data["host_id"])))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _persist_state_host_id(state_dir: Path | None, host_id: HostId) -> None:
    if state_dir is None:
        return
    state_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(
        state_dir / "host.json",
        (json.dumps({"host_id": str(host_id)}, sort_keys=True) + "\n").encode("utf-8"),
        mode=0o600,
    )


def _optional_workspace_id(ctx: CliContext) -> WorkspaceId | None:
    try:
        return resolve_workspace_id(ctx)
    except Exception:  # noqa: BLE001
        return None


def _normalize_host_ref(text: str) -> str:
    if as_uuid(text) is not None:
        return f"host:{text}"
    return text


def resolve_host_view(
    ctx: CliContext,
    raw: str | None = None,
    *,
    workspace_id: WorkspaceId | None = None,
) -> workspace.HostView:
    """Resolve a host reference (or the current local host) to ``HostView``."""
    ws_id = workspace_id if workspace_id is not None else _optional_workspace_id(ctx)
    if raw is None:
        host_id = _read_state_host_id(_state_dir(ctx))
        if host_id is None:
            host_id = build_host_context(ctx).host_id
        view = ctx.client.ask(workspace.GetHost(host_id=host_id, workspace_id=ws_id))
        assert isinstance(view, workspace.HostView)  # noqa: S101
        return view

    parsed = parse_ref(RefKind.HOST, _normalize_host_ref(raw))
    if parsed.form is RefForm.UUID and parsed.uuid is not None:
        view = ctx.client.ask(workspace.GetHost(host_id=HostId(parsed.uuid), workspace_id=ws_id))
        assert isinstance(view, workspace.HostView)  # noqa: S101
        return view
    if parsed.form is RefForm.SLUG:
        view = ctx.client.ask(workspace.GetHost(name=parsed.text, workspace_id=ws_id))
        assert isinstance(view, workspace.HostView)  # noqa: S101
        return view
    raise ValidationFailed(
        ErrorCode.INVALID_REFERENCE,
        f"invalid host reference: {raw!r}",
        details={"ref": raw, "expected": RefKind.HOST.value},
    )


def resolve_host_id(
    ctx: CliContext,
    raw: str | None = None,
    *,
    workspace_id: WorkspaceId | None = None,
) -> HostId:
    """Resolve a host reference (or current host) to ``HostId``."""
    if raw is None:
        recorded = _read_state_host_id(_state_dir(ctx))
        if recorded is not None:
            return recorded
        return build_host_context(ctx).host_id
    parsed = parse_ref(RefKind.HOST, _normalize_host_ref(raw))
    if parsed.form is RefForm.UUID and parsed.uuid is not None:
        return HostId(parsed.uuid)
    return HostId(resolve_host_view(ctx, raw, workspace_id=workspace_id).host_id)


def _register(args: argparse.Namespace, ctx: CliContext) -> int:
    state_dir = _state_dir(ctx)

    def persist(host_id: HostId) -> None:
        _persist_state_host_id(state_dir, host_id)

    os_val = args.os
    arch_val = args.arch
    platform_arg = getattr(args, "platform", None)
    if isinstance(platform_arg, str) and platform_arg:
        parts = platform_arg.replace("/", "-").split("-", 1)
        if not os_val and parts[0]:
            os_val = parts[0]
        if not arch_val and len(parts) > 1 and parts[1]:
            arch_val = parts[1]

    if state_dir is not None:
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with (
            FileLock(state_dir / "host-register.lock").hold(timeout_seconds=30)
            if state_dir
            else nullcontext()
        ):
            report = run_workspace_host_op(
                ctx,
                "workspace.host.register_this_host",
                {
                    "name": args.name or getattr(args, "host_name", None),
                    "default_name": getattr(ctx, "host_name", None),
                    "os": os_val,
                    "arch": arch_val,
                    "recorded_host_id": _read_state_host_id(state_dir),
                    "replace": args.replace,
                    "persist_host_id": persist if state_dir is not None else None,
                },
                allow_unregistered_host=True,
            )
    except LockTimeout as exc:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION, "Another host registration is in progress"
        ) from exc
    payload = report.to_json()
    return render(
        ctx,
        payload,
        human=lambda value: kv_lines(
            ctx,
            [
                ("host_id", value["host_id"]),
                ("name", value["name"]),
                ("os", value["platform"]["os"]),
                ("arch", value["platform"]["arch"]),
            ],
        ),
        command=args.command_name,
        essential=lambda value: str(value["host_id"]),
    )


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    ws_id = _optional_workspace_id(ctx)
    view = cast(
        "workspace.ListHostsView",
        ctx.client.ask(
            workspace.ListHosts(
                workspace_id=ws_id,
                after=args.after,
                limit=args.limit,
            )
        ),
    )

    def human(value: workspace.ListHostsView) -> list[str]:
        if not value.items:
            return ["no hosts"]
        rows = [
            [item.host_id, item.name, item.platform.os.value, item.platform.arch.value, item.state]
            for item in value.items
        ]
        lines = render_table(ctx, ("host_id", "name", "os", "arch", "state"), rows)
        if value.next is not None:
            lines.append(safe_text(ctx, f"next: {value.next} (use --after)"))
        return lines

    return render(
        ctx,
        view,
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(str(item.host_id) for item in value.items),
    )


def _show(args: argparse.Namespace, ctx: CliContext) -> int:
    view = resolve_host_view(ctx, args.host)
    return render(
        ctx,
        view,
        human=lambda value: kv_lines(
            ctx,
            [
                ("host_id", value.host_id),
                ("name", value.name),
                ("os", value.platform.os.value),
                ("arch", value.platform.arch.value),
                ("state", value.state),
                ("registered_at", value.registered_at.isoformat()),
                ("last_seen_at", None if value.last_seen_at is None else value.last_seen_at.isoformat()),
            ],
        ),
        command=args.command_name,
        essential=lambda value: str(value.host_id),
    )


_HANDLERS = {
    "register": _register,
    "list": _list,
    "show": _show,
}


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("host", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", metavar="VERB", required=True)
    for verb in ("register", "list", "show"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
        if verb == "register":
            command.add_argument("host_name", nargs="?", default=None, metavar="NAME")
            command.add_argument("--name")
            command.add_argument(
                "--replace",
                action="store_true",
                help="register under another name although this machine already has a host",
            )
            command.add_argument("--platform")
            command.add_argument("--os", choices=("linux", "macos", "windows"))
            command.add_argument("--arch", choices=("x86_64", "arm64", "other"))
        if verb == "list":
            command.add_argument("--after")
            command.add_argument("--limit", type=int, default=50)
        if verb == "show":
            command.add_argument("host", nargs="?")
        command.set_defaults(run=_HANDLERS[verb], command_name=_COMMAND[verb])


GROUP = CommandGroup(
    name="host",
    help="register, list and show hosts",
    register=register,
    requires_backend=True,
    module="workspace",
    order=14,
)
