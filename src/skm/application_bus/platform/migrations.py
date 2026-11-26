"""``platform.migration_status`` (kernel-platform §5.6): the migration chain against the applied history.

The only migration operation of the bus. Applying migrations is not one (K21): ``skm db migrate`` is a local
CLI operation over ``MigrationRunner`` with the migrator's DSN; ``platform.apply_migrations`` does not exist.
The handler reads through the ``SchemaVersionReader`` repository port inside the read-only unit of work: the
packaged chain and the applied history, both as plain values. It compares them and never writes, never opens a
connection of its own and never runs a migration. Names, versions and timestamps are returned; checksums are
compared here and not disclosed.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ports_uow import UnitOfWork, repository_port
from skm.platform.generated.queries import MigrationStatus
from skm.platform.generated.results import MigrationStatusResult, MigrationStatusResultMigrationsItem

__all__ = ["MIGRATION_STATUS", "AppliedMigration", "PackagedMigration", "SchemaVersionReader", "handle"]

type _SchemaState = Literal["ok", "not_migrated", "too_new"]
type _MigrationState = Literal["applied", "pending", "modified", "unknown"]


@dataclass(frozen=True, slots=True)
class PackagedMigration:
    """One migration file of the chain shipped with this code."""

    version: int
    name: str
    checksum: str


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    """One row of ``skm_core.schema_migrations``."""

    version: int
    name: str
    checksum: str
    applied_at: datetime


@repository_port
class SchemaVersionReader(Protocol):
    """Read-only view of the migration chain and its history on the connection of the current unit of work.

    ``applied`` is empty while ``skm_core.schema_migrations`` does not exist; the reader runs SELECTs only.
    """

    def packaged(self) -> Sequence[PackagedMigration]:
        """The chain shipped with this code, any order."""
        ...

    def applied(self) -> Sequence[AppliedMigration]:
        """The history rows, any order."""
        ...

    def check_baseline(self) -> None:
        """Require the persisted baseline marker to match the packaged prefix."""
        ...


def _schema_state(known: int, applied: Sequence[AppliedMigration]) -> tuple[int, _SchemaState]:
    """Same classification as the start-up gate: an empty history or an older database is ``not_migrated``."""
    if not applied:
        return 0, "not_migrated"
    newest = max(row.version for row in applied)
    if newest < known:
        return newest, "not_migrated"
    return newest, "too_new" if newest > known else "ok"


def _entry(
    version: int, packaged: PackagedMigration | None, applied: AppliedMigration | None
) -> MigrationStatusResultMigrationsItem:
    if applied is None:
        name = "" if packaged is None else packaged.name  # the version comes from one of the two sides
        return MigrationStatusResultMigrationsItem(version=version, name=name, state="pending")
    state: _MigrationState
    if packaged is None:
        state = "unknown"
    else:
        state = "applied" if packaged.checksum == applied.checksum else "modified"
    name = applied.name if packaged is None else packaged.name
    return MigrationStatusResultMigrationsItem(
        version=version, name=name, state=state, applied_at=applied.applied_at
    )


def handle(query: MigrationStatus, ctx: QueryContext, uow: UnitOfWork) -> MigrationStatusResult:
    del query, ctx  # the request has no fields; authorization happened before the handler
    reader = uow.repo(SchemaVersionReader)
    packaged = {item.version: item for item in reader.packaged()}
    applied = {item.version: item for item in reader.applied()}
    known = max(packaged, default=0)
    db_version, state = _schema_state(known, tuple(applied.values()))
    return MigrationStatusResult(
        known_version=known,
        db_version=db_version,
        state=state,
        migrations=tuple(
            _entry(version, packaged.get(version), applied.get(version))
            for version in sorted(packaged.keys() | applied.keys())
        ),
    )


MIGRATION_STATUS: Final = QuerySpec(
    name="platform.migration_status",
    dto=MigrationStatus,
    result=MigrationStatusResult,
    permission="admin.storage",
    scope_of=None,  # instance: the schema belongs to the whole installation
    handler=handle,
)
