"""Manage the local PostgreSQL, API and worker processes."""

import argparse
import json
import re
import sys
from collections.abc import Callable, Generator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from typing import Final, cast
from urllib.parse import quote, urlsplit
from uuid import UUID

from skm.application_bus.middleware import require_restore_admission
from skm.bootstrap.composition import App, build_app, resolve_cli_actor, storage_recovery
from skm.bootstrap.composition_resources import OWNER_TOKEN_FILE, owner_token
from skm.bootstrap.lifecycle import (
    DEFAULT_BIND,
    ComponentStatus,
    LocalProcesses,
    Role,
    embedded_dsn,
    follow_log,
    local_migrate,
    parse_bind,
    ready,
    runtime_settings,
    tail,
)
from skm.bootstrap.local_cleanup import clean_files, clean_worktrees
from skm.bootstrap.local_postgres import (
    SERVICE,
    compose_file,
    compose_status,
    compose_stop,
    external_status,
    init_machine_profile,
    installation_id_from_env,
    local_postgres_state,
    machine_postgres_status,
    managed_postgres,
    manages_postgres,
    postgres_logs,
    postgres_up,
    prepare_machine_storage,
    provision_local_postgres,
)
from skm.bootstrap.machine import open_machine_store
from skm.bootstrap.machine_access import machine_user_scope
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.errors import Terminated
from skm.entrypoints.cli.output import render, render_table, safe_text
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, CapabilityUnavailable, SkmError, ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import WhoAmI
from skm.platform.config.bootstrap import BootstrapConfig, validate_worker_host
from skm.platform.logging.redaction import Redactor
from skm.platform.process.runner import run
from skm.platform.storage.restore import restore_profile_root
from skm.platform.system_clock import SystemClock

__all__ = ["GROUP", "compose_file", "register"]

_HELP = {
    "up": "start local PostgreSQL, apply migrations and start serve and worker",
    "down": "stop local worker, serve and managed PostgreSQL",
    "status": "show local PostgreSQL, serve and worker status",
    "logs": "read local component logs",
    "open": "open the local web UI",
    "clean": "clean selected local files and worktrees",
    "token": "show the local owner token path",
}
_COMMAND_SECONDS: Final = 60.0
_STDERR_TAIL: Final = 2000
_ROLES = ("serve", "worker")


@dataclass(frozen=True, slots=True)
class _Local:
    ctx: CliSession
    config: BootstrapConfig

    @classmethod
    def load(cls, args: argparse.Namespace, ctx: CliContext, *, allow_http: bool = False) -> "_Local":
        session = cast("CliSession", ctx)
        catalog = session.profile_catalog()
        profile = catalog.select(args.instance, Path.cwd())
        config = storage_recovery.pinned_profile(catalog.config(profile))
        if (config.access_mode != "embedded" and not allow_http) or config.instance_id is None:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Local lifecycle needs an embedded instance")
        return cls(session, config)

    @property
    def processes(self) -> LocalProcesses:
        return LocalProcesses(self.config)

    @property
    def compose_marker(self) -> Path:
        return self.processes.pids / "postgres.compose"

    def postgres_identity(self) -> str:
        return str(self.config.installation_id or self.config.instance_id)

    def manages_postgres(self) -> bool:
        return manages_postgres(self.compose_marker, self.postgres_identity())

    def compose_environment(self) -> Mapping[str, str]:
        managed = managed_postgres(self.config.state_dir)
        if managed is None and self.config.machine_database_url is not None:
            reference = self.config.machine_database_url
            if reference.scheme == "file":
                managed = managed_postgres(Path(reference.path).parent.parent)
        if managed is None or managed.installation_id != self.config.installation_id:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Local PostgreSQL installation metadata is missing or mismatched"
            )
        return managed.environment(self.ctx.environ, self.ctx.redactor.register_secret)

    def postgres_status(self) -> ComponentStatus:
        if self.manages_postgres():
            return compose_status(self.compose_environment())
        if self.config.access_mode == "http":
            return machine_postgres_status(self.config, self.ctx.environ, self.ctx.redactor.register_secret)
        return external_status(self.dsn())

    def dsn(self) -> str:
        return embedded_dsn(self.config, self.ctx.environ, self.ctx.redactor.register_secret)

    def secret(self) -> str:
        return owner_token(self.config.state_dir, self.ctx.redactor.register_secret)

    def argv(self, *arguments: str) -> list[str]:
        options = self.ctx.options
        overrides = [part for setting in options.sets for part in ("--set", setting)]
        if options.config:
            overrides += ["--config", options.config]
        return [
            sys.executable,
            "-m",
            "skm.entrypoints.cli.main",
            "--bootstrap",
            self.config.source,
            *(
                ("--instance", self.config.instance_profile)
                if self.config.instance_profile is not None
                else ()
            ),
            *overrides,
            *arguments,
        ]

    def app(self) -> App:
        options = self.ctx.options
        return build_app(
            self.config,
            surface=Surface.CLI,
            environ=self.ctx.environ,
            invocation={"set": list(options.sets), "config": options.config or []},
        )

    @contextmanager
    def owner(self) -> Generator[tuple[App, CliSession]]:
        with closing(self.app()) as app:
            actor = resolve_cli_actor(
                app, self.config, as_token=None, on_secret=self.ctx.redactor.register_secret
            )
            client = app.client(actor=actor, surface=Surface.CLI)
            store = (
                open_machine_store(self.config, self.ctx.environ, on_secret=self.ctx.redactor.register_secret)
                if self.config.installation_id is not None
                else None
            )
            yield (
                app,
                replace(
                    self.ctx,
                    client_=client,
                    state_dir=self.config.state_dir,
                    instance_id=app.instance_id,
                    machine_store=store,
                    machine_scope=machine_user_scope(self.config, lambda: client.ask(WhoAmI())),
                ),
            )


def _worker_id(local: _Local) -> str:
    from skm.entrypoints.cli.commands.workspace import resolve_workspace_id
    from skm.modules.workspace.public import ListWorkers, ListWorkersView

    config = local.config
    if config.host_id == "auto" and not (config.state_dir / "host.json").exists():
        _owner_command(local, "host", "register", config.host_name)
    host = validate_worker_host(config).host_id
    with local.owner() as (_, session):
        workspace = resolve_workspace_id(session)
        matches: list[UUID] = []
        after = None
        while True:
            page = cast(
                "ListWorkersView", session.client.ask(ListWorkers(workspace_id=workspace, after=after))
            )
            matches.extend(
                item.worker_id for item in page.items if item.host_id == host and item.state != "retired"
            )
            after = page.next
            if after is None:
                break
    if len(matches) > 1:
        raise ValidationFailed(
            ErrorCode.AMBIGUOUS_REFERENCE,
            "Multiple workers on this host; use local up --no-worker and worker start --worker",
        )
    if matches:
        return str(matches[0])
    registered = _owner_command(local, "worker", "register", "--host", str(host))
    return str(registered["worker_id"])


def _owner_command(local: _Local, *args: str) -> dict[str, JsonValue]:
    result = run(
        local.argv("--json", *args),
        cwd=Path.cwd(),
        env=local.ctx.environ,
        timeout_seconds=_COMMAND_SECONDS,
    )
    if result.exit_code:
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE,
            f"Could not run skm {args[0]} {args[1]}",
            details={"stderr": result.stderr.decode("utf-8", "replace")[-_STDERR_TAIL:]},
        )
    return cast("dict[str, JsonValue]", json.loads(result.stdout)["result"])


def _bind(local: _Local, port: int | None) -> tuple[str, int]:
    with closing(local.app()) as app:
        values = runtime_settings(app)
    bind = str(values.get("api.bind", DEFAULT_BIND))
    host, configured = parse_bind(bind)
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Local serve requires a loopback api.bind")
    address = f"[{host}]" if ":" in host else host
    return f"{address}:{configured if port is None else port}", cast(
        "int", values["api.shutdown.grace_seconds"]
    )


def _components(local: _Local, postgres: ComponentStatus) -> tuple[ComponentStatus, ...]:
    processes = local.processes
    serve = processes.lookup("serve")
    worker = processes.lookup("worker")
    url = None if serve is None else serve.url
    http = url is not None and ready(url)
    return (
        postgres,
        ComponentStatus(
            "serve",
            ("ready" if http else "starting") if serve else "stopped",
            f"pid {serve.identity.pid}, {url}" if serve else "",
        ),
        ComponentStatus(
            "worker", "running" if worker else "stopped", f"pid {worker.identity.pid}" if worker else ""
        ),
    )


def _rows(ctx: CliContext, components: tuple[ComponentStatus, ...]) -> list[str]:
    return render_table(
        ctx, ("component", "state", "detail"), [[c.component, c.state, c.detail] for c in components]
    )


def _pending_postgres(
    ctx: CliSession, operation: Callable[[Mapping[str, str]], ComponentStatus]
) -> ComponentStatus:
    state = local_postgres_state(ctx.environ, Path(ctx.environ.get("HOME") or Path.home()))
    managed = managed_postgres(state)
    if managed is None:
        return ComponentStatus(SERVICE, "absent", "run skm local up")
    return operation(managed.environment(ctx.environ, ctx.redactor.register_secret))


def _up_before_init(args: argparse.Namespace, ctx: CliSession) -> int:
    state = local_postgres_state(ctx.environ, Path(ctx.environ.get("HOME") or Path.home()))
    managed = provision_local_postgres(
        state,
        "standalone",
        installation_id_from_env(ctx.environ),
        ctx.environ,
        on_secret=ctx.redactor.register_secret,
        wait=args.wait,
    )
    postgres = compose_status(managed.environment(ctx.environ, ctx.redactor.register_secret))
    return render(
        ctx,
        {"postgres": postgres, "components": (postgres,)},
        human=lambda _: [*_rows(ctx, (postgres,)), "run skm init to prepare the databases"],
        command=args.command_name,
    )


def _up(args: argparse.Namespace, ctx: CliContext) -> int:
    if args.wait < 1 or (args.port is not None and not 1 <= args.port <= 65535):
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Use a positive --wait and a --port in 1..65535")
    if args.no_serve and args.port is not None:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "--port requires serve")
    try:
        local = _Local.load(args, ctx, allow_http=True)
    except SkmError as error:
        if error.code is not ErrorCode.BOOTSTRAP_MISSING:
            raise
        return _up_before_init(args, cast("CliSession", ctx))
    if local.config.access_mode == "http":
        machine = init_machine_profile(
            Path(local.config.source),
            local.config,
            local.ctx.environ,
            Path(local.ctx.environ.get("HOME") or Path.home()),
            on_secret=ctx.redactor.register_secret,
        )
        return render(
            ctx,
            machine,
            human=lambda value: f"ready machine {value.installation_id}",
            command=args.command_name,
        )
    require_restore_admission(restore_profile_root(local.config) is None, "local.up")
    processes = local.processes
    with processes.lock().hold(timeout_seconds=args.wait):
        postgres = postgres_up(
            local.dsn(),
            local.compose_environment() if local.manages_postgres() else local.ctx.environ,
            local.compose_marker,
            local.postgres_identity(),
            args.wait,
        )
        applied, current = (), None
        if not any(processes.lookup(role) for role in _ROLES):
            if local.config.machine_database_url is not None:
                prepare_machine_storage(
                    local.config, local.ctx.environ, on_secret=ctx.redactor.register_secret
                )
            applied, current = local_migrate(local.config, local.ctx.environ, ctx.redactor.register_secret)
        _start_local(local, args)
        components = _components(local, postgres)
    result = {
        "postgres": postgres,
        "migrations": {"applied": applied, "current": current},
        "components": components,
    }
    return render(ctx, result, human=lambda _: _rows(ctx, components), command=args.command_name)


def _start_local(local: _Local, args: argparse.Namespace) -> None:
    processes = local.processes
    started: list[Role] = []
    try:
        if not args.no_serve:
            existing = processes.lookup("serve")
            if existing is None:
                bind, grace = _bind(local, args.port)
                url = f"http://{bind}"
                existing = processes.start(
                    "serve",
                    local.argv("--json", "serve", "--bind", bind),
                    local.ctx.environ,
                    url=url,
                    grace=grace + 2,
                )
                started.append("serve")
            else:
                url = cast("str", existing.url)
                if args.port is not None and urlsplit(url).port != args.port:
                    raise ValidationFailed(
                        ErrorCode.CONFIG_INVALID, "Local serve is already listening on another port"
                    )
            processes.wait_ready(existing, local.secret(), args.wait)
        if not args.no_worker and processes.lookup("worker") is None:
            from skm.entrypoints.cli.commands.worker import resolve_worker_view

            worker = _worker_id(local)
            with local.owner() as (_, session):
                launched = SystemClock().now()
                processes.start(
                    "worker", local.argv("--json", "worker", "start", "--worker", worker), local.ctx.environ
                )
                started.append("worker")

                def healthy() -> bool:
                    heartbeat = resolve_worker_view(session, worker).last_heartbeat_at
                    return heartbeat is not None and heartbeat >= launched

                processes.wait_worker(args.wait, healthy)
    except BaseException:
        for role in reversed(started):
            processes.stop(role)
        raise


def _down(args: argparse.Namespace, ctx: CliContext) -> int:
    operation = compose_status if args.keep_db else compose_stop
    try:
        local = _Local.load(args, ctx, allow_http=True)
    except SkmError as error:
        if error.code is not ErrorCode.BOOTSTRAP_MISSING:
            raise
        postgres = _pending_postgres(cast("CliSession", ctx), operation)
        return render(ctx, {"postgres": postgres}, human=lambda _: "stopped", command=args.command_name)
    processes = local.processes
    with processes.lock().hold(timeout_seconds=60):
        processes.stop("worker")
        processes.stop("serve")
        if local.manages_postgres():
            postgres = operation(local.compose_environment())
        else:
            postgres = local.postgres_status()
    return render(
        ctx, {"postgres": postgres, "stopped": _ROLES}, human=lambda _: "stopped", command=args.command_name
    )


def _machine_status(args: argparse.Namespace, local: _Local, postgres: ComponentStatus) -> int:
    from skm.bootstrap.machine import machine_socket_path, open_machine_store

    session = local.ctx
    result: dict[str, object] = {"components": (postgres,)}
    notes: list[str] = []
    if postgres.state == "running":
        store = open_machine_store(local.config, session.environ, on_secret=session.redactor.register_secret)
        installation = store.get_installation_id()
        assert installation is not None  # noqa: S101 -- validated by the machine-store opener
        path = machine_socket_path(session.environ, session.home, installation)
        result.update(
            machine_database="ready",
            installation_id=str(installation),
            machine_socket=str(path),
        )
        notes.append(safe_text(session, f"machine database ready, socket {path}"))
    return render(
        session, result, human=lambda _: [*_rows(session, (postgres,)), *notes], command=args.command_name
    )


def _status(args: argparse.Namespace, ctx: CliContext) -> int:
    try:
        local = _Local.load(args, ctx, allow_http=True)
    except SkmError as error:
        if error.code is not ErrorCode.BOOTSTRAP_MISSING:
            raise
        components = (_pending_postgres(cast("CliSession", ctx), compose_status),)
    else:
        postgres = local.postgres_status()
        if local.config.access_mode == "http":
            return _machine_status(args, local, postgres)
        components = _components(local, postgres)
    return render(
        ctx, {"components": components}, human=lambda _: _rows(ctx, components), command=args.command_name
    )


def _logs(args: argparse.Namespace, ctx: CliContext) -> int:
    if args.lines < 0:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "--lines must be non-negative")
    local = _Local.load(args, ctx)
    local.secret()
    local.dsn()
    redact = Redactor().text
    with closing(_log_lines(local, args)) as lines:
        if ctx.json:
            if args.follow:
                raise ValidationFailed(
                    ErrorCode.CONFIG_INVALID, "Streaming logs require human-readable output"
                )
            result = {"component": args.component, "lines": [redact(line.rstrip("\r\n")) for line in lines]}
            return render(ctx, result, human=lambda _: [], command=args.command_name)
        try:
            for line in lines:
                ctx.stdout.write(safe_text(ctx, redact(line.rstrip("\r\n"))) + "\n")
                ctx.stdout.flush()
        except Terminated:
            raise
        except KeyboardInterrupt:
            if not args.follow:
                raise
    return 0


def _log_lines(local: _Local, args: argparse.Namespace) -> Generator[str]:
    role = args.component
    if role == SERVICE:
        if not local.manages_postgres():
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE, "PostgreSQL logs belong to the external database"
            )
        yield from postgres_logs(local.compose_environment(), args.lines, follow=args.follow)
    else:
        path = local.processes.logs / f"{role}.log"
        if args.follow:
            yield from follow_log(path, lambda: local.processes.lookup(role) is not None, args.lines)
        else:
            yield from tail(path, args.lines)


def _open(args: argparse.Namespace, ctx: CliContext) -> int:
    local = _Local.load(args, ctx)
    process = local.processes.lookup("serve")
    if process is None:
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "No owned local serve is running")
    secret = local.secret()
    local.processes.wait_ready(process, secret, 1)
    url = cast("str", process.url)
    opened = False
    if not args.print:
        import webbrowser

        opened = webbrowser.open(url + "/#token=" + quote(secret, safe=""))
    return render(
        ctx,
        {"url": url, "opened": opened},
        human=lambda _: url,
        essential=lambda _: url,
        command=args.command_name,
    )


def _token(args: argparse.Namespace, ctx: CliContext) -> int:
    local = _Local.load(args, ctx)
    path = str(local.config.state_dir / OWNER_TOKEN_FILE)
    if args.show:
        # This is the explicit credential reveal, with normal escaping and outer CLI formatting.
        token = owner_token(local.config.state_dir, lambda _: None)
        return render(ctx, {"path": path, "token": token}, human=lambda _: token, command=args.command_name)
    return render(
        ctx, {"path": path}, human=lambda _: path, essential=lambda _: path, command=args.command_name
    )


def _clean(args: argparse.Namespace, ctx: CliContext) -> int:
    if not any((args.logs, args.staging, args.materialized, args.worktrees)):
        message = "Select cleanup targets with --logs, --staging, --materialized or --worktrees"
        return render(
            ctx, {"message": message, "targets": {}}, human=lambda _: message, command=args.command_name
        )
    if args.older_than is not None and (
        not args.logs or re.fullmatch(r"[0-9]{1,6}d", args.older_than) is None
    ):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "--older-than requires --logs and a day count such as 14d"
        )
    local = _Local.load(args, ctx)
    if not args.dry_run and not (args.yes or ctx.confirm("Remove the selected local cleanup targets?")):
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Use --yes to confirm cleanup outside a terminal")
    if args.dry_run:
        targets = _clean_targets(local, args)
    else:
        with local.processes.lock().hold(timeout_seconds=60):
            targets = _clean_targets(local, args)
    action = "would remove" if args.dry_run else "removed"
    return render(
        ctx,
        {"dry_run": args.dry_run, "targets": targets},
        human=lambda _: [f"{action} {name}  {data}" for name, data in targets.items()],
        command=args.command_name,
    )


def _clean_targets(local: _Local, args: argparse.Namespace) -> dict[str, object]:
    age = timedelta(days=int((args.older_than or "14d")[:-1])) if args.logs else None
    if not (args.staging or args.materialized or args.worktrees):
        return dict(
            clean_files(
                local.config,
                local.processes,
                None,
                log_age=age,
                staging_age=None,
                materialized=False,
                dry_run=args.dry_run,
            )
        )
    with local.owner() as (app, session):
        values = runtime_settings(app)
        staging = (
            timedelta(hours=cast("int", values["artifacts.staging.ttl_hours"])) if args.staging else None
        )
        result: dict[str, object] = dict(
            clean_files(
                local.config,
                local.processes,
                session.client,
                log_age=age,
                staging_age=staging,
                materialized=args.materialized,
                dry_run=args.dry_run,
            )
        )
        if args.worktrees:
            result["worktrees"] = clean_worktrees(local.config, session.client, values, dry_run=args.dry_run)
        return result


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("local", help=GROUP.help)
    verbs = parser.add_subparsers(dest="local_verb", required=True)
    for verb in ("up", "down", "status", "logs", "open", "clean", "token"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_RUN[verb], command_name=f"cli.local.{verb}")
        if verb != "logs":
            command.add_argument(
                "--json", default=argparse.SUPPRESS, action="store_true", help="machine-readable output"
            )
        if verb == "up":
            command.add_argument("--no-worker", action="store_true")
            command.add_argument("--no-serve", action="store_true")
            command.add_argument("--port", type=int, metavar="N")
            command.add_argument("--wait", type=int, default=60, metavar="SECONDS")
        if verb == "down":
            command.add_argument("--keep-db", action="store_true")
        if verb == "logs":
            command.add_argument("component", choices=("serve", "worker", "postgres"))
            command.add_argument("--follow", action="store_true")
            command.add_argument("--lines", type=int, default=200, metavar="N")
        if verb == "open":
            command.add_argument("--print", action="store_true")
        if verb == "token":
            command.add_argument("--show", action="store_true")
        if verb == "clean":
            command.add_argument("--logs", action="store_true")
            command.add_argument("--older-than", metavar="DAYS", help="log retention (default 14d)")
            command.add_argument("--staging", action="store_true")
            command.add_argument("--materialized", action="store_true")
            command.add_argument("--worktrees", action="store_true")
            command.add_argument("--dry-run", action="store_true")
            command.add_argument("--yes", default=argparse.SUPPRESS, action="store_true")


_RUN = {
    "up": _up,
    "down": _down,
    "status": _status,
    "logs": _logs,
    "open": _open,
    "clean": _clean,
    "token": _token,
}
GROUP = CommandGroup(
    "local", "manage local PostgreSQL, serve and worker", register, requires_backend=False, order=30
)
