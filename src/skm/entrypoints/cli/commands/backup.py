"""Local archive and staged instance recovery commands."""

import argparse
from pathlib import Path
from uuid import UUID

from skm.bootstrap.composition import KNOWN_SCHEMA_VERSION
from skm.bootstrap.composition import storage_recovery as recovery
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.output import render
from skm.kernel.json_types import JsonObject
from skm.platform.storage.restore import verification_report, verify_backup

_HELP = {
    "create": "archive a consistent PostgreSQL snapshot and final blobs",
    "verify": "check an archive's files and snapshot closure",
    "restore": "restore a verified archive to a new quarantined instance",
    "activate": "verify and activate the selected restored instance",
    "rebind": "verify a local checkout for a restored Git effect",
}


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    if not isinstance(ctx, CliSession):
        raise TypeError("Backup requires a local CLI session")
    if args.verb == "verify":
        report = verification_report(verify_backup(args.directory, KNOWN_SCHEMA_VERSION, environ=ctx.environ))
    else:
        catalog = ctx.profile_catalog()
        config = catalog.config(catalog.select(ctx.options.instance, Path.cwd()))
        if args.verb == "create":
            report = recovery.backup_create(config, ctx.environ, args.output, ctx.options.actor_hint)
        elif args.verb == "restore":
            home = Path(ctx.environ.get("HOME", str(Path.home())))
            parent = Path(ctx.environ.get("XDG_STATE_HOME", str(home / ".local/state"))) / "skm/restores"
            ctx.redactor.register_secret(args.target_database_url)
            report = recovery.backup_restore(
                config,
                args.directory,
                args.target_database_url,
                parent,
                ctx.environ,
                yes=ctx.options.assume_yes,
                token=ctx.options.actor_hint,
            )
        elif args.verb == "rebind":
            report = recovery.backup_rebind(
                config, ctx.environ, args.effect_id, args.checkout, ctx.options.actor_hint
            )
        else:
            report = recovery.backup_activate(config, ctx.environ, yes=ctx.options.assume_yes)

    def human(value: JsonObject) -> list[str]:
        if args.verb == "rebind":
            return [f"Verified checkout binding {value['binding_id']} for effect {value['effect_id']}"]
        lines = [f"Backup {value['backup_id']} is {value['state']}"]
        lines.extend(str(value[name]) for name in ("manifest", "profile") if name in value)
        if isinstance(pending := value.get("requires_rebind"), list) and pending:
            lines.append(f"{len(pending)} external dependencies require rebind")
        if isinstance(blocked := value.get("blocked_runs"), list) and blocked:
            lines.append(f"{len(blocked)} restored runs had unresolved prerequisites at activation")
        return lines

    return render(ctx, report, human=human, command=args.command_name)


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("backup", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in ("create", "verify", "restore", "activate", "rebind"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
        if verb == "create":
            command.add_argument("--output", type=Path, metavar="DIR")
        if verb in ("verify", "restore"):
            command.add_argument("directory", type=Path, metavar="DIR")
        if verb == "restore":
            command.add_argument("--target-database-url", required=True, metavar="URL")
        if verb == "rebind":
            command.add_argument("effect_id", type=UUID, metavar="EFFECT_ID")
            command.add_argument("--checkout", type=Path, required=True, metavar="DIR")
        if verb in ("restore", "activate"):
            command.add_argument("--yes", default=argparse.SUPPRESS, action="store_true")
        command.set_defaults(run=_run, command_name="backup." + verb)


GROUP = CommandGroup(
    "backup", "archive, verify, and recover an instance", register, requires_backend=False, order=89
)

__all__ = ["GROUP", "register"]
