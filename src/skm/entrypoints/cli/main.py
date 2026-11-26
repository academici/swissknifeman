"""``skm`` entry point (cli §1.2): parse, set up logging, attach a backend when the group needs one, run.

``main`` returns the exit code (the console script wraps it in ``sys.exit``). Usage errors exit 2 with the
safe message of ``parse_command_line`` on ``stderr``; ``--version`` prints the bare package version.
Groups with ``requires_backend`` get their client from a ``BackendFactory``: the default is the
production one, which loads the bootstrap, composes the application and resolves the acting principal
(``--as-token`` or the owner token file; ``open_cli_app``). A caller that already holds an ``App`` (the
transient test composition) passes ``app_backend(app, actor)``.
"""

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from typing import TextIO, cast, override
from uuid import UUID

from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext
from skm.bootstrap.checkout_operations import CheckoutRunner, bind_checkout_paths, bind_checkout_runner
from skm.bootstrap.composition import (
    App,
    build_app,
    build_cli_app,
    open_cli_app,
    resolve_cli_actor,
    storage_recovery,
)
from skm.bootstrap.machine import open_machine_store, pin_machine_config, resolve_machine_profile
from skm.bootstrap.machine_access import machine_user_scope
from skm.entrypoints.cli.commands import GROUPS, CommandGroup
from skm.entrypoints.cli.commands.use import selects_instance_only
from skm.entrypoints.cli.context import Cell, CliOptions, CliRedactor, CliSession, frame, seal, untrusted
from skm.entrypoints.cli.errors import (
    EXIT_OK,
    EXIT_TERMINATED,
    EXIT_USAGE,
    Terminated,
    run_guarded,
    sigterm_unwinds,
)
from skm.entrypoints.cli.host import host_context_factory
from skm.entrypoints.cli.parser import (
    GLOBAL_FLAGS,
    build_parser,
    options_from,
    parse_command_line,
    secret_values,
)
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import WhoAmI, WhoAmIView
from skm.platform.config.bootstrap import BootstrapConfig
from skm.platform.config.sources.bootstrap import ProfileCatalog
from skm.platform.logging.redaction import MASK, Redactor
from skm.platform.logging.setup import configure_logging
from skm.platform.machine import MachinePrincipal, MachineStore
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

__all__ = ["Backend", "BackendFactory", "app_backend", "console_main", "main", "production_backend"]


@dataclass(frozen=True, slots=True)
class Backend:
    """What a backend group needs from composition: the client and, optionally, the host context."""

    client: SkmClient
    host_factory: Callable[[], HostContext] | None = None
    state_dir: Path | None = None
    instance_id: UUID | None = None
    close: Callable[[], None] | None = None
    instance_profile: str | None = None
    remote_identity: Callable[[], UUID] | None = None
    disabled_modules: Callable[[], frozenset[str]] = frozenset
    machine_store: MachineStore | None = None
    machine_scope: Callable[[], MachinePrincipal] | None = None
    checkout_operation: CheckoutRunner | None = None
    host_name: str | None = None


type BackendFactory = Callable[[CliOptions, Mapping[str, str]], Backend]


def _invocation(options: CliOptions) -> JsonObject:
    return {"set": list(options.sets), "config": options.config or []}


def _selected_bootstrap(options: CliOptions, environ: Mapping[str, str]) -> tuple[BootstrapConfig, str]:
    home = Path(environ["HOME"]) if "HOME" in environ else Path.home()
    catalog = ProfileCatalog.read(options.bootstrap, environ, home)
    selected = catalog.select(options.instance, Path.cwd())
    return storage_recovery.pinned_profile(catalog.config(selected)), selected


def _disabled_in(app: App) -> frozenset[str]:
    return app.bus._registry.disabled_modules()  # pyright: ignore[reportPrivateUsage] -- composed selection


_RUNTIME_DETECT = "runtimes.host.detect_runtimes"


def production_backend(
    options: CliOptions,
    environ: Mapping[str, str],
    on_secret: Callable[[str], None] = lambda _value: None,
    *,
    worker: bool = False,
    vault: bool = False,
    command_name: str | None = None,
    credential_ref: str | None = None,
    credential_path: Path | None = None,
) -> Backend:
    """Load the bootstrap (``BOOTSTRAP_MISSING`` -> exit 6), compose and resolve the acting principal.

    The actor is the ``--as-token`` principal, else the owner of ``<state_dir>/secrets/owner.token``; no
    fallback authorizer or actor exists. ``on_secret`` receives the owner token for redaction.
    """
    bootstrap, selected = _selected_bootstrap(options, environ)
    machine_store = None
    if bootstrap.machine_database_url is not None or bootstrap.installation_id is not None:
        machine_store = open_machine_store(bootstrap, environ, on_secret=on_secret)
        installation = bootstrap.installation_id
        assert installation is not None  # noqa: S101 -- validated by machine-store opener
        bootstrap = pin_machine_config(
            bootstrap, resolve_machine_profile(machine_store, installation, selected)
        )

    def detection_host(client: SkmClient) -> HostContext:
        from skm.bootstrap.runtime_detection import build_runtime_detection_host

        host = build_runtime_detection_host(bootstrap, client, environ, machine_store, on_secret)
        return host_context_factory(host, client)()

    if bootstrap.access_mode == "http" and not worker:
        from skm.application_bus.platform.doctor import INSTANCE_CHECK
        from skm.bootstrap.composition import knowledge_wiring
        from skm.bootstrap.instance_secrets import instance_details, open_http_client
        from skm.platform.generated.queries import Doctor
        from skm.platform.generated.results import DoctorResult

        client = open_http_client(bootstrap, environ, as_token=options.actor_hint, on_secret=on_secret)

        def remote_identity() -> UUID:
            doctor = cast("DoctorResult", client.ask(Doctor(only=(INSTANCE_CHECK,))))
            return instance_details(doctor, bootstrap.instance_id)[0]

        @cache
        def whoami() -> WhoAmIView:
            return cast("WhoAmIView", client.ask(WhoAmI()))

        def remote_disabled_modules() -> frozenset[str]:
            identity = whoami()
            return frozenset(module for module, enabled in identity.modules.items() if not enabled)

        def make_host() -> HostContext:
            if vault:
                from skm.bootstrap.worker import http_cli_vault_host

                host = http_cli_vault_host(bootstrap, client)
            else:
                from skm.bootstrap.host_services import bind_cli_research
                from skm.bootstrap.projection_wiring import bind_cli_projections

                host = knowledge_wiring.bind_http_cli_knowledge(bootstrap, client)
                host = bind_cli_projections(
                    bind_cli_research(host, client, remote=True),
                    bootstrap.state_dir,
                    client,
                    environ=environ,
                    instance_id=bootstrap.instance_id,
                )
            return host_context_factory(host, client)()

        return _managed_backend(
            Backend(
                client,
                host_factory=(lambda: detection_host(client))
                if command_name == _RUNTIME_DETECT
                else make_host,
                remote_identity=remote_identity,
                instance_id=bootstrap.instance_id,
                close=client.close,
                disabled_modules=remote_disabled_modules,
            ),
            bootstrap,
            selected,
            machine_store,
            whoami,
        )
    if worker:
        from skm.bootstrap.worker import build_worker_host

        if bootstrap.access_mode == "http":
            from skm.entrypoints.cli._run_worker import http_backend

            return http_backend(bootstrap, options, environ, on_secret, credential_ref, credential_path)

        app = build_app(bootstrap, surface=Surface.WORKER, environ=environ, invocation=_invocation(options))
        try:
            actor = resolve_cli_actor(app, bootstrap, as_token=options.actor_hint, on_secret=on_secret)
            host = build_worker_host(
                app,
                bootstrap,
                actor,
                environ=environ,
                credential_ref=credential_ref,
                credential_path=credential_path,
                on_secret=on_secret,
            )
            app = replace(app, host=host)

            def close_worker() -> None:
                try:
                    host.close()
                finally:
                    app.close()

            return _embedded_worker_backend(app, actor, bootstrap, machine_store, close_worker)
        except BaseException:
            app.close()
            raise
    app, actor = open_cli_app(
        bootstrap,
        environ=environ,
        invocation=_invocation(options),
        as_token=options.actor_hint,
        on_secret=on_secret,
        load_project_plugins=command_name not in {_RUNTIME_DETECT, "session.start"},
    )
    backend = app_backend(app, actor)
    if command_name == _RUNTIME_DETECT:
        client = backend.client
        backend = replace(backend, host_factory=lambda: detection_host(client))
    if vault and app.host is not None and "exports" not in backend.disabled_modules():
        from skm.bootstrap.worker import bind_vault_host, embedded_vault_client

        client = embedded_vault_client(app, actor, Surface.CLI, app.host.host_id)
        host = bind_vault_host(app.host, bootstrap, client)
        backend = replace(backend, host_factory=host_context_factory(host, client))
    return _managed_backend(backend, bootstrap, selected, machine_store, lambda: backend.client.ask(WhoAmI()))


def _embedded_worker_backend(
    app: App,
    actor: Actor,
    config: BootstrapConfig,
    store: MachineStore | None,
    close: Callable[[], None],
) -> Backend:
    backend = app_backend(app, actor, surface=Surface.WORKER)
    owner_store = store if actor.kind is PrincipalKind.HUMAN else None
    return replace(
        backend,
        state_dir=config.state_dir,
        host_name=config.host_name,
        machine_store=owner_store,
        machine_scope=(
            machine_user_scope(config, lambda: backend.client.ask(WhoAmI()))
            if owner_store is not None
            else None
        ),
        close=close,
    )


def _managed_backend(
    backend: Backend,
    config: BootstrapConfig,
    selected: str,
    store: MachineStore | None,
    identity: Callable[[], object],
) -> Backend:
    from skm.bootstrap.projection_wiring import bind_managed_projections

    scope = machine_user_scope(config, identity)
    factory = bind_checkout_paths(backend.host_factory, config, store, scope)

    def managed_host() -> HostContext:
        assert factory is not None  # noqa: S101
        assert store is not None  # noqa: S101
        assert scope is not None  # noqa: S101
        return bind_managed_projections(factory(), store, scope, config.state_dir)

    return replace(
        backend,
        state_dir=config.state_dir,
        host_name=config.host_name,
        instance_profile=selected,
        machine_store=store,
        machine_scope=scope,
        host_factory=managed_host
        if factory is not None and store is not None and scope is not None
        else factory,
        checkout_operation=bind_checkout_runner(config, backend.client, store, scope),
    )


def app_backend(app: App, actor: Actor, *, surface: Surface = Surface.CLI) -> Backend:
    """Embed an already composed ``App`` for ``actor`` (the transient single-process composition)."""
    client = app.client(actor=actor, surface=surface)
    return Backend(
        client=client,
        host_factory=host_context_factory(app.host, client),
        instance_id=app.instance_id,
        close=app.close,
        disabled_modules=lambda: _disabled_in(app),
    )


def _exit_code(stop: SystemExit) -> int:
    if stop.code is None:
        return 0
    return stop.code if isinstance(stop.code, int) else EXIT_USAGE


def _log_string(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)[1:-1]


class _LogRedactor(Redactor):
    """The logger's projected member names are fixed; only its metadata values are data."""

    def __init__(self, redactor: CliRedactor) -> None:
        super().__init__()
        self._redactor = redactor

    @override
    def document(self, value: JsonValue) -> JsonValue:
        if type(value) is not dict:
            raise TypeError("CLI log record must be an object")
        return {name: self._redactor.document(item) for name, item in value.items()}


class _JsonLogStream:
    """Seal the shared logger's already projected, flat JSON record at the CLI's stream boundary.

    Member names and JSON syntax are code-owned framing; every metadata value remains data. This sink
    cannot grant any fields: projection and document redaction still happen in the shared logger first.
    Only the logger uses this adapter; command errors and diagnostics keep their own stream renderers.
    """

    def __init__(self, stream: TextIO, redactor: CliRedactor) -> None:
        self._stream = stream
        self._redactor = redactor

    def write(self, text: str) -> int:
        record = cast("JsonObject", json.loads(text))
        if type(record) is not dict:
            raise TypeError("CLI JSON log record must be an object")
        cells = [frame("{")]
        for index, (name, value) in enumerate(record.items()):
            if index:
                cells.append(frame(","))
            cells.append(frame(json.dumps(name, ensure_ascii=False) + ":"))
            if type(value) is str:
                cells.extend([frame('"'), *untrusted(self._redactor.text(value), _log_string), frame('"')])
            elif value is None or type(value) in (bool, int, float):
                cells.append(
                    Cell(json.dumps(value, allow_nan=False), masked=json.dumps(MASK, ensure_ascii=False))
                )
            else:
                raise TypeError("CLI JSON log metadata must be scalar")
        cells.append(frame("}\n"))
        self._stream.write(seal(self._redactor, cells))
        return len(text)

    def flush(self) -> None:
        self._stream.flush()


def _setup_logging(options: CliOptions, stderr: TextIO, redactor: CliRedactor) -> None:
    level = "error" if options.quiet else ("debug" if options.verbosity else "info")
    fmt = "text" if stderr.isatty() and not options.json else "json"
    configure_logging(
        level=level,
        detail="debug" if options.verbosity >= 2 else "normal",
        fmt=fmt,
        stream=cast("TextIO", _JsonLogStream(stderr, redactor)) if fmt == "json" else stderr,
        redactor=_LogRedactor(redactor),
        host="localhost",
    )


def _find_group(groups: Sequence[CommandGroup], name: str) -> CommandGroup:
    return next(group for group in groups if group.name == name)


def _help_disabled_modules(arguments: list[str], env: Mapping[str, str]) -> frozenset[str]:
    if not {"--help", "-h"}.intersection(arguments):
        return frozenset()
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False, exit_on_error=False)
    for names, kwargs in GLOBAL_FLAGS:
        parser.add_argument(*names, **kwargs)
    try:
        args, rest = parser.parse_known_args(arguments)
        if rest not in (["--help"], ["-h"]):
            return frozenset()
        options = options_from(args)
        bootstrap, _ = _selected_bootstrap(options, env)
        if bootstrap.access_mode == "embedded":
            with closing(build_cli_app(bootstrap, environ=env, invocation=_invocation(options))) as app:
                return _disabled_in(app)
        attached = production_backend(options, env)
        try:
            return attached.disabled_modules()
        finally:
            if attached.close is not None:
                attached.close()
    except (argparse.ArgumentError, SkmError):
        # Static help is available before an instance has been initialized.
        return frozenset()


_TOOL_SEARCH_KEYS = ("PATH", "SYSTEMROOT")


def _environ_with_operator_search_path(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    """Keep the process search path when a caller passes a reduced environment.

    Backup verification runs ``pg_restore`` against an archive and does not need a
    project environment, so ``skm backup verify`` is invoked with an empty mapping.
    The PostgreSQL client may live outside the default search path.
    """
    if environ is None:
        return os.environ
    env = dict(environ)
    for key in _TOOL_SEARCH_KEYS:
        if key not in env and (value := os.environ.get(key)) is not None:
            env[key] = value
    return env


def console_main() -> int:
    """Install console signal handling only for the lifetime of the CLI process."""
    try:
        with sigterm_unwinds():
            return main()
    except Terminated:
        return EXIT_TERMINATED


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdin: TextIO | None = None,
    backend: BackendFactory | None = None,
    groups: Sequence[CommandGroup] | None = None,
    disabled_modules: frozenset[str] = frozenset(),
) -> int:
    env = os.environ if environ is None else environ
    arguments = list(sys.argv[1:] if argv is None else argv)
    out, err = stdout or sys.stdout, stderr or sys.stderr
    if backend is None:
        disabled_modules |= _help_disabled_modules(arguments, env)
    parser = build_parser(groups, disabled_modules=disabled_modules)
    try:
        args = parse_command_line(parser, arguments, stdout=out, stderr=err)
    except SystemExit as stop:
        return _exit_code(stop)
    if args.group in {"backup", "restore"}:
        env = _environ_with_operator_search_path(environ)
    options = options_from(args)
    if args.group == "use" and getattr(args, "instance_name", None) is not None:
        options = replace(options, instance=args.instance_name)
    redactor = CliRedactor()  # masks a credential of any length wherever it occurs, short ones too
    for secret in secret_values(arguments):  # every --as-token value, not only the one argparse kept
        redactor.register_secret(secret)
    ids = Uuid7Generator(SystemClock())
    session = CliSession(
        options=options,
        stdout=out,
        stderr=err,
        redactor=redactor,
        ids=ids,
        request_id="cli-" + str(ids.new_id()),
        stdin=stdin or sys.stdin,
        environ=env,
    )
    group = _find_group(GROUPS if groups is None else groups, args.group)
    module = getattr(args, "command_module", group.module)
    command = getattr(args, "command_name", None) or args.group
    _setup_logging(options, err, redactor)
    attached: Backend | None = None

    def production(opts: CliOptions, environment: Mapping[str, str]) -> Backend:
        worker_start = args.group == "worker" and args.verb == "start"
        if worker_start and args.token is not None:
            from skm.bootstrap.worker_credentials import resolve_worker_credential

            secret = resolve_worker_credential(
                args.token, environ=environment, on_reveal=redactor.register_secret
            )
            opts = replace(opts, actor_hint=secret)
        return production_backend(
            opts,
            environment,
            redactor.register_secret,
            worker=worker_start,
            command_name=command,
            vault=args.group == "export" and args.verb in {"vault", "vault-push", "docs-push"},
        )

    def invoke() -> int:
        nonlocal attached
        if module is not None and module in disabled_modules and module != group.module:
            raise error_for(
                ErrorCode.MODULE_DISABLED,
                f"command {command!r} belongs to module {module!r}, which is disabled",
                details={"module": module, "group": group.name},
            )
        if (
            group.requires_backend
            and group.module not in disabled_modules
            and not getattr(args, "host_local", False)
            and not (command == "integrations.host.run_doctor" and getattr(args, "offline", False))
        ):
            if args.group == "use" and selects_instance_only(args):
                # An injected backend owns its profile namespace independently of the local bootstrap.
                if args.instance_name is not None and backend is None:
                    catalog = session.profile_catalog()
                    selected = catalog.select(args.instance_name, Path.cwd())
                    if not args.clear:
                        from skm.bootstrap.instance_profiles import verified_config

                        verified_config(
                            catalog.config(selected), selected, env, session.redactor.register_secret
                        )
                return args.run(args, session)
            attached = (backend or production)(options, env)
            if module is not None and module in attached.disabled_modules():
                raise error_for(
                    ErrorCode.MODULE_DISABLED,
                    f"command {command!r} belongs to module {module!r}, which is disabled",
                    details={"module": module, "group": group.name},
                )
            if attached.instance_profile is not None:
                session.options = replace(options, instance=attached.instance_profile)
            session.client_ = attached.client
            session.host_factory = attached.host_factory
            session.state_dir = attached.state_dir
            session.instance_id = attached.instance_id
            session.remote_identity = attached.remote_identity
            session.machine_store = attached.machine_store
            session.machine_scope = attached.machine_scope
            session.checkout_operation = attached.checkout_operation
            session.host_name = attached.host_name
        return args.run(args, session)

    def close() -> int:
        if attached is not None and attached.close is not None:
            attached.close()
        return EXIT_OK

    code = run_guarded(invoke, session, command)
    # Cleanup runs behind the same guard: a failure is INTERNAL_ERROR, redacted and escaped, never a raw
    # traceback. It is reported on stderr in human form (stdout may already hold the one --json envelope) and
    # never replaces the outcome of a failed command; it only turns a success into exit 70.
    cleanup = run_guarded(close, replace(session, options=replace(options, json=False)), command)
    return code if code != EXIT_OK else cleanup


if __name__ == "__main__":
    sys.exit(console_main())
