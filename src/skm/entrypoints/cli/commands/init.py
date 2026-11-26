"""``skm init`` (cli §6.1, kernel-platform §5.5, access §7.7): the local instance and its first identities.

Creates (or verifies) the bootstrap profile, the state directory with its private ``secrets/``, the token
pepper, the migrated schema, the instance scope, the ``system`` principal, the local owner with its token
file ``<state_dir>/secrets/owner.token`` (0600) and the default workspace through
``bootstrap.instance.init_instance``. The DSN is ``--database-url``, else ``SKM_DATABASE_URL``; a rerun on an
existing profile resolves it from the profile like ``skm db migrate``. The DSN, its password and the owner
secret are registered with the redactor before anything can be printed; the secret is never printed and the
DSN never written to the profile. The display name of a new owner is the OS user name. A workspace created
by this run, or one picked while no workspace is selected, becomes the local owner's selection. A later
selection is kept.
"""

import argparse
import os
import pwd
from pathlib import Path

from skm.bootstrap.instance import (
    DEFAULT_WORKSPACE,
    InitReport,
    find_bootstrap,
    init_instance,
)
from skm.bootstrap.local_postgres import init_machine_profile
from skm.bootstrap.machine import open_machine_store
from skm.bootstrap.machine_access import SELECTION_KEY
from skm.bootstrap.platform_module import resolve_migrator_dsn
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.output import kv_lines, render
from skm.kernel.errors import NotFound
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.config.sources.bootstrap import ProfileCatalog
from skm.platform.machine import MachinePrincipal

__all__ = ["GROUP", "register"]

COMMAND = "cli.init"
_OWNER_FALLBACK = "local-owner"
_NAME_MAX = 200
# The reference emitter reads a ``register`` loop over literal verbs; ``skm init`` has one unnamed verb.
_HELP = {"": "create or verify the local instance, its owner, owner token and default workspace (local)"}


def _environ(ctx: CliContext) -> dict[str, str]:
    return dict(ctx.environ) if isinstance(ctx, CliSession) else {}


def _dsn(
    args: argparse.Namespace, ctx: CliContext, bootstrap: Path, exists: bool, instance: str | None
) -> str | None:
    environ = _environ(ctx)
    home = Path(environ["HOME"]) if "HOME" in environ else Path.home()
    explicit = args.database_url or environ.get("SKM_DATABASE_MIGRATOR_URL")
    if not exists:
        explicit = explicit or environ.get("SKM_DATABASE_URL")
        if explicit is None:
            return None
    target = resolve_migrator_dsn(
        explicit,
        bootstrap_path=None if explicit else str(bootstrap),
        instance=instance,
        environ=environ,
        home=home,
    )
    for secret in target.secrets:  # before anything can be printed
        ctx.redactor.register_secret(secret)
    return target.dsn


def _owner_name(environ: dict[str, str]) -> str:
    """The OS user name (access §7.7), cleaned to a valid display name; ``local-owner`` without one."""
    name = environ.get("USER") or environ.get("LOGNAME") or ""
    if not name:
        try:
            name = pwd.getpwuid(os.geteuid()).pw_name
        except KeyError:
            name = ""
    cleaned = "".join(char for char in name if ord(char) >= 0x20 and char != "\x7f").strip()[:_NAME_MAX]
    return cleaned or _OWNER_FALLBACK


def _select(ctx: CliContext, report: InitReport, instance: str | None) -> bool:
    """Select a new default workspace or fill an empty selection."""
    workspace = report.workspace
    if workspace is None or not isinstance(ctx, CliSession):
        return False
    config = load_bootstrap(str(report.bootstrap_path), ctx.environ, ctx.home, instance=instance)
    if config.installation_id is not None:
        store = open_machine_store(config, ctx.environ, on_secret=ctx.redactor.register_secret)
        scope = MachinePrincipal(config.installation_id, report.instance_id, report.owner_principal_id)
        selected = store.get_user_setting(scope, SELECTION_KEY)
        if workspace.created or not isinstance(selected, dict) or not selected.get("workspace_id"):
            store.set_user_setting(
                scope, SELECTION_KEY, {"workspace_id": str(workspace.workspace_id), "project_id": None}
            )
            return True
        return False
    ctx.state_dir, ctx.instance_id = report.state_dir, report.instance_id
    if not workspace.created:
        try:
            ctx.resolve_workspace(None)
        except NotFound:
            pass
        else:
            return False  # a selection of the user (skm use) stays
    ctx.save_context(workspace_id=str(workspace.workspace_id), workspace_slug=workspace.slug)
    return True


def _migrations(report: InitReport) -> str:
    applied = report.migrations.applied
    if not applied:
        return f"up to date ({report.migrations.current:04d})"
    span = f"{applied[0]:04d}" if len(applied) == 1 else f"{applied[0]:04d} … {applied[-1]:04d}"
    return f"applied {len(applied)} ({span})"


def _human(ctx: CliContext, report: InitReport, selected: bool) -> list[str]:
    pepper = (
        "(managed outside skm init)"
        if report.token_pepper_path is None
        else f"{report.token_pepper_path} (0600, {'new' if report.token_pepper_created else 'kept'})"
    )
    owner = report.owner
    workspace = report.workspace
    pairs: list[tuple[str, object]] = [
        ("bootstrap", f"{report.bootstrap_path} ({'kept' if report.already_initialized else 'new'})"),
        ("instance", report.instance_id),
        ("state", report.state_dir),
        ("pepper", pepper),
        ("migrations", _migrations(report)),
        ("scope", f"instance {'created' if report.instance_scope_created else 'present'}"),
        ("system", "created" if report.system_principal_created else "present"),
        ("owner", f"{owner.principal_id} ({'new' if owner.created else 'kept'}) — owner@instance"),
        ("token", f"{'saved to' if owner.created else 'kept in'} {owner.token_path} (0600)"),
    ]
    if workspace is not None:
        state = "created" if workspace.created else "present"
        chosen = ", selected" if selected else ""
        pairs.append(("workspace", f"{workspace.slug} {workspace.workspace_id} ({state}{chosen})"))
    head = [f"already initialized: instance {report.instance_id}"] if report.already_initialized else []
    return [*head, *kv_lines(ctx, pairs)]


def _init(args: argparse.Namespace, ctx: CliContext) -> int:
    environ = _environ(ctx)
    home = Path(environ["HOME"]) if "HOME" in environ else Path.home()
    bootstrap, exists = find_bootstrap(args.bootstrap, environ, home)
    instance = args.instance
    if exists:
        catalog = ProfileCatalog.read(str(bootstrap), environ, home)
        config = catalog.config(catalog.select(args.instance, Path.cwd()))
        instance = config.instance_profile
        if config.access_mode == "http":
            machine = init_machine_profile(
                bootstrap, config, environ, home, on_secret=ctx.redactor.register_secret
            )
            return render(
                ctx,
                machine,
                human=lambda value: f"initialized machine {value.installation_id}",
                command=args.command_name,
                essential=lambda value: str(value.installation_id),
            )
    dsn = _dsn(args, ctx, bootstrap, exists, instance)
    owner_password = environ.get("SKM_FIRST_ADMIN_PASSWORD") or None
    if owner_password is not None:
        ctx.redactor.register_secret(owner_password)
    report = init_instance(
        bootstrap,
        database_url=dsn,
        state_dir=Path(args.state_dir) if args.state_dir else None,
        blobs_root=Path(args.blobs_root) if args.blobs_root else None,
        host_name=args.host_name,
        instance=instance,
        environ=environ,
        home=home,
        owner_name=_owner_name(environ),
        owner_password=owner_password,
        workspace=args.workspace,
        on_secret=ctx.redactor.register_secret,
    )
    selected = _select(ctx, report, instance)
    return render(
        ctx,
        report,
        human=lambda value: _human(ctx, value, selected),
        command=args.command_name,
        essential=lambda value: str(value.instance_id),
    )


def register(sub: SubParsers) -> None:
    for verb in ("",):
        command = sub.add_parser("init", help=_HELP[verb])
        command.set_defaults(run=_init, command_name=COMMAND)
        command.add_argument(
            "--json",
            default=argparse.SUPPRESS,
            action="store_true",
            help="machine-readable output (as global --json)",
        )
        command.add_argument(
            "--database-url",
            metavar="URL",
            help="project migrator DSN (default: local PostgreSQL for a new profile)",
        )
        command.add_argument("--state-dir", metavar="PATH", help="state directory of a new profile")
        command.add_argument("--blobs-root", metavar="PATH", help="blob store root of a new profile")
        command.add_argument("--host-name", metavar="NAME", help="host name recorded in a new profile")
        # One destination: the last of --workspace/--no-workspace wins; None means no default workspace.
        command.add_argument(
            "--workspace",
            metavar="SLUG",
            default=DEFAULT_WORKSPACE,
            help=f"default workspace of the local owner (default {DEFAULT_WORKSPACE})",
        )
        command.add_argument(
            "--no-workspace",
            dest="workspace",
            action="store_const",
            const=None,
            help="create no default workspace",
        )


GROUP = CommandGroup(
    "init",
    "create or verify the local instance, its owner and default workspace (no backend needed)",
    register,
    requires_backend=False,
    order=10,
)
