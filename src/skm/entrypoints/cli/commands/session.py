"""Start and manage a local interactive runtime."""

import argparse
from pathlib import Path

from skm.bootstrap.interactive_sessions import (
    InteractiveLauncher,
    InteractiveSession,
    local_launcher,
    start_session,
)
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.context import CliSession
from skm.entrypoints.cli.host import build_host_context
from skm.entrypoints.cli.output import kv_lines, render, render_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

__all__ = ["GROUP"]


def _launcher(session: CliSession) -> InteractiveLauncher:
    return local_launcher(
        state_dir=session.state_dir,
        bootstrap=session.options.bootstrap,
        instance=session.options.instance,
        environ=session.environ,
        home=session.home,
    )


def _start(args: argparse.Namespace, ctx: CliSession) -> int:
    if ctx.machine_store is None:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Interactive sessions require machine storage")
    catalog = ctx.profile_catalog()
    bootstrap = catalog.config(catalog.select(ctx.options.instance, Path.cwd()))
    project_id = resolve_project_id(ctx, args.project, workspace_ref=args.workspace)
    result = start_session(
        _launcher(ctx),
        build_host_context(ctx),
        project_id,
        mount=args.mount,
        role=args.role,
        runtime=args.runtime,
        model=args.model,
        bootstrap=bootstrap,
        machine_store=ctx.machine_store,
        environ=ctx.environ,
        on_secret=ctx.redactor.register_secret,
    )
    return render(
        ctx,
        result,
        command=args.command_name,
        human=lambda value: [
            *kv_lines(
                ctx, [("session", value.session_id), ("runtime", value.runtime), ("model", value.model)]
            ),
            f"Attach with skm session attach {value.session_id}",
        ],
        essential=lambda value: value.session_id,
    )


def _list(args: argparse.Namespace, ctx: CliSession) -> int:
    sessions = _launcher(ctx).list()

    def human(value: tuple[InteractiveSession, ...]) -> list[str]:
        if not value:
            return ["no active interactive sessions"]
        return render_table(
            ctx,
            ("session", "project", "runtime", "model", "checkout"),
            [(s.session_id, s.project_id, s.runtime, s.model, s.checkout) for s in value],
        )

    return render(
        ctx,
        sessions,
        command=args.command_name,
        human=human,
        essential=lambda value: "\n".join(s.session_id for s in value),
    )


def _attach(args: argparse.Namespace, ctx: CliSession) -> int:
    if ctx.json:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Attach streams a terminal and cannot use --json")
    _launcher(ctx).attach(args.session_id, ctx.stdin, ctx.stdout)
    return 0


def _stop(args: argparse.Namespace, ctx: CliSession) -> int:
    result = _launcher(ctx).stop(args.session_id)
    return render(
        ctx,
        result,
        command=args.command_name,
        human=lambda value: [f"stopped session {value.session_id}"],
        essential=lambda value: value.session_id,
    )


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("session", help="manage local interactive agent sessions")
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="VERB")
    start = verbs.add_parser("start", help="sync project projections and start a detached runtime")
    start.add_argument("--project", help="project UUID or alias")
    start.add_argument("--workspace", help="workspace UUID or alias for project resolution")
    start.add_argument("--mount", default="main", help="project checkout mount (default: main)")
    start.add_argument(
        "--role",
        choices=("scout", "executor", "reviewer", "triager", "advisor", "researcher", "registrar"),
        default="executor",
        help="role for runtime routing",
    )
    start.add_argument("--runtime", help="request a specific runtime")
    start.add_argument("--model", help="request a specific model")
    start.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    start.set_defaults(run=_start, command_name="session.start")

    listing = verbs.add_parser("list", help="list running sessions on this host")
    listing.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    listing.set_defaults(run=_list, command_name="session.list", host_local=True)

    attach = verbs.add_parser("attach", help="attach a terminal to a session (Ctrl-] to detach)")
    attach.add_argument("session_id")
    attach.set_defaults(run=_attach, command_name="session.attach", host_local=True)

    stop = verbs.add_parser("stop", help="stop a session and remove its local record")
    stop.add_argument("session_id")
    stop.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    stop.set_defaults(run=_stop, command_name="session.stop", host_local=True)


GROUP = CommandGroup("session", "manage local interactive agent sessions", register, order=67)
