"""``skm db migrate|status|verify|snapshot`` (cli §6.3, adapters §1.10, kernel-platform §5.6).

Local operations over ``MigrationRunner`` with the DSN of the migrator role, outside the bus and with no API
route (K21): the group needs no backend, so it works on a database that is not migrated, too new or empty.
The DSN is ``--database-url``, else bootstrap ``database.migrator_url``, else ``database.url``; a profile
without one (``access.mode = http``) is refused with a hint and no API call. ``snapshot`` writes nothing
unless ``--output`` or ``--write`` says so; ``--write`` replaces the package ``schema.snapshot.sql`` and only
from a database that is fully migrated and verifies clean.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from skm.bootstrap import platform_module
from skm.bootstrap.platform_module import (
    SNAPSHOT_FILE,
    local_migration_runner,
    local_schema_snapshot,
    resolve_migrator_dsn,
)
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.output import render, render_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import Diagnostic, Severity
from skm.platform.fs.atomic_write import atomic_write

if TYPE_CHECKING:
    from skm.bootstrap.platform_module import MigrationFile, MigrationRunner, MigrationState

__all__ = ["GROUP", "register"]

_HELP = {
    "migrate": "apply pending migrations with the migrator's DSN (local only)",
    "status": "show the migration chain against the database history",
    "verify": "check the database history against the packaged migrations",
    "snapshot": "print the normalized schema-only snapshot of a migrated database",
}


@dataclass(frozen=True, slots=True)
class MigrateResult:
    applied: tuple[int, ...]
    pending: tuple[int, ...]
    current: int
    dry_run: bool


@dataclass(frozen=True, slots=True)
class StatusEntry:
    version: int
    name: str
    state: str


@dataclass(frozen=True, slots=True)
class StatusResult:
    known_version: int
    db_version: int
    state: str
    migrations: tuple[StatusEntry, ...]


@dataclass(frozen=True, slots=True)
class VerifyResult:
    ok: bool
    known_version: int
    pending: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SnapshotResult:
    snapshot: str


@dataclass(frozen=True, slots=True)
class SnapshotWritten:
    path: str
    bytes: int


def _runner(args: argparse.Namespace, ctx: CliContext) -> tuple[MigrationRunner, str]:
    environ = dict(ctx.environ) if isinstance(ctx, CliSession) else {}
    home = Path(environ["HOME"]) if "HOME" in environ else Path.home()
    try:
        target = resolve_migrator_dsn(
            args.database_url,
            bootstrap_path=args.bootstrap,
            instance=args.instance,
            environ=environ,
            home=home,
        )
    except PreconditionFailed as error:
        if error.code is not ErrorCode.BOOTSTRAP_MISSING:
            raise
        # skm db works without an instance: the generic "run skm init" hides the direct way.
        raise PreconditionFailed(
            ErrorCode.BOOTSTRAP_MISSING,
            "no bootstrap and no --database-url: the migrator DSN is unknown",
            details={"hint": "pass --database-url URL with the migrator role's DSN, or run `skm init`"},
        ) from error
    for secret in target.secrets:  # before anything can be printed: the DSN and its password never appear
        ctx.redactor.register_secret(secret)
    return local_migration_runner(target.dsn), target.dsn


def _label(files: Sequence[MigrationFile], version: int) -> str:
    for item in files:
        if item.version == version:
            return item.filename.removesuffix(".py").removesuffix(".sql").removesuffix(".data")
    return f"{version:04d}"


def _span(files: Sequence[MigrationFile], versions: Sequence[int]) -> str:
    first, last = _label(files, versions[0]), _label(files, versions[-1])
    return f"{len(versions)} ({first})" if len(versions) == 1 else f"{len(versions)} ({first} … {last})"


def _current(entries: Sequence[tuple[MigrationFile | None, int, MigrationState]]) -> int:
    pending = platform_module.MigrationState.PENDING
    return max((version for _, version, state in entries if state is not pending), default=0)


def _migrate(args: argparse.Namespace, ctx: CliContext) -> int:
    runner, _ = _runner(args, ctx)
    done = runner.migrate(target=args.target, dry_run=args.dry_run)
    entries = runner.status()
    pending = platform_module.MigrationState.PENDING
    result = MigrateResult(
        applied=() if args.dry_run else done,
        pending=done if args.dry_run else tuple(v for _, v, s in entries if s is pending),
        current=_current(entries),
        dry_run=args.dry_run,
    )
    files = runner.files

    def human(value: MigrateResult) -> str:
        if value.dry_run and value.pending:
            return f"pending {_span(files, value.pending)}"
        if value.applied:
            return f"applied {_span(files, value.applied)}"
        return f"up to date ({value.current:04d})"

    return render(ctx, result, human=human, command=args.command_name, essential=human)


def _status(args: argparse.Namespace, ctx: CliContext) -> int:
    runner, _ = _runner(args, ctx)
    entries = runner.status()
    known = max((item.version for item in runner.files), default=0)
    stored = _current(entries)
    state = "not_migrated" if stored == 0 or stored < known else ("too_new" if stored > known else "ok")
    result = StatusResult(
        known_version=known,
        db_version=stored,
        state=state,
        migrations=tuple(
            StatusEntry(version, item.filename if item is not None else "-", migration.value)
            for item, version, migration in entries
        ),
    )

    def human(value: StatusResult) -> list[str]:
        rows = [[f"{e.version:04d}", e.name, e.state] for e in value.migrations]
        head = f"schema  database {value.db_version:04d}, code {value.known_version:04d} ({value.state})"
        return [head, *render_table(ctx, ("version", "name", "state"), rows)]

    return render(ctx, result, human=human, command=args.command_name)


def _verify(args: argparse.Namespace, ctx: CliContext) -> int:
    runner, _ = _runner(args, ctx)
    diagnostics = runner.verify()
    errors = [item for item in diagnostics if item.severity is Severity.ERROR]
    if errors:
        findings: list[JsonValue] = [
            {"code": item.code, "target": item.target, "details": dict(item.details)} for item in errors
        ]
        raise PreconditionFailed(
            ErrorCode(errors[0].code),
            "migration history does not match the packaged migrations",
            details={
                "findings": findings,
                "hint": "restore the changed migration file; never edit an applied one",
            },
        )
    known = max((item.version for item in runner.files), default=0)
    pending = platform_module.MigrationState.PENDING
    versions = tuple(version for _, version, state in runner.status() if state is pending)
    result = VerifyResult(ok=True, known_version=known, pending=versions)

    def human(value: VerifyResult) -> str:
        suffix = f", {len(value.pending)} pending" if value.pending else ""
        return f"migrations verified ({value.known_version:04d}{suffix})"

    notes: Sequence[Diagnostic] = diagnostics
    return render(ctx, result, human=human, command=args.command_name, diagnostics=notes)


def _snapshot(args: argparse.Namespace, ctx: CliContext) -> int:
    if args.write and args.output:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "--write and --output are mutually exclusive")
    runner, dsn = _runner(args, ctx)
    destination = SNAPSHOT_FILE if args.write else (Path(args.output) if args.output else None)
    if args.write:
        # The package copy is a contract: only a fully applied, unmodified chain may define it.
        problems = runner.verify()
        if problems:
            raise PreconditionFailed(
                ErrorCode(problems[0].code),
                "refusing to write the snapshot: the database is not fully migrated or does not verify",
                details={"hint": "run `skm db migrate` and `skm db verify` first"},
            )
    text = local_schema_snapshot(dsn)
    if destination is None:
        if ctx.json:
            return render(ctx, SnapshotResult(text), human=lambda _: "", command=args.command_name)
        ctx.stdout.write(ctx.redactor.text(text))  # a file-shaped document: no terminal framing around it
        return 0
    atomic_write(destination, text.encode("utf-8"))
    written = SnapshotWritten(str(destination), len(text.encode("utf-8")))
    return render(ctx, written, human=lambda value: str(value.path), command=args.command_name)


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("db", help="migrate, inspect and snapshot the database (local)")
    verbs = parser.add_subparsers(dest="db_verb", required=True)
    for verb in ("migrate", "status", "verify", "snapshot"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_RUN[verb], command_name=f"db.{verb}")
        command.add_argument(
            "--json",
            default=argparse.SUPPRESS,
            action="store_true",
            help="machine-readable output (as global --json)",
        )
        command.add_argument("--database-url", metavar="URL", help="DSN of the migrator role")
        if verb == "migrate":
            command.add_argument("--target", type=int, metavar="N", help="apply up to this migration number")
            command.add_argument("--dry-run", action="store_true", help="list pending migrations only")
        elif verb == "snapshot":
            command.add_argument("--output", metavar="PATH", help="write the snapshot to this file")
            command.add_argument(
                "--write", action="store_true", help="replace the package schema.snapshot.sql"
            )


_RUN = {"migrate": _migrate, "status": _status, "verify": _verify, "snapshot": _snapshot}

GROUP = CommandGroup(
    "db",
    "migrate, inspect and snapshot the database (local)",
    register,
    requires_backend=False,
    order=40,
)
