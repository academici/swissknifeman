"""Schema compatibility gate: the database version against the version this code knows (adapters §1.10)."""

from collections.abc import Callable, Sequence
from datetime import datetime
from enum import StrEnum
from functools import cache

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.migrations.runner import (
    BASELINE_VERSION,
    BaselineFingerprint,
    MigrationFile,
    baseline_chain_sha256,
    discover_migrations,
    packaged_baseline,
    read_baseline,
    read_migration_history,
    require_baseline,
    require_empty_database,
)
from skm.kernel.errors import PreconditionFailed
from skm.kernel.generated.error_codes import ErrorCode

__all__ = ["PostgresSchemaVersionReader"]

_TABLE_PROBE = "SELECT pg_catalog.to_regclass('skm_core.schema_migrations') IS NOT NULL"
_HISTORY = "SELECT version, name, checksum, applied_at FROM skm_core.schema_migrations ORDER BY version"


@cache
def _packaged() -> tuple[tuple[int, str, str], ...]:
    return tuple((item.version, item.filename, item.checksum) for item in discover_migrations())


class PostgresSchemaVersionReader[P, A]:
    """Read-only status repository. Bootstrap supplies the owning port's row constructors.

    The adapter depends on scalar SQL rows, without importing handler-bearing bus modules.
    """

    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        packaged_row: Callable[[int, str, str], P],
        applied_row: Callable[[int, str, str, datetime], A],
    ) -> None:
        self._conn = conn
        self._packaged_row, self._applied_row = packaged_row, applied_row

    def packaged(self) -> tuple[P, ...]:
        return tuple(self._packaged_row(*row) for row in _packaged())

    def applied(self) -> tuple[A, ...]:
        try:
            probe = self._conn.execute(_TABLE_PROBE).fetchone()
            if probe is None or not probe[0]:
                return ()
            return tuple(self._applied_row(*row) for row in self._conn.execute(_HISTORY))
        except psycopg.Error as error:
            raise translate_pg_error(error) from error

    def check_baseline(self) -> None:
        try:
            require_baseline(read_baseline(self._conn), packaged_baseline())
        except psycopg.Error as error:
            raise translate_pg_error(error) from error


class SchemaCompatibility(StrEnum):
    COMPATIBLE = "compatible"
    NOT_MIGRATED = "not_migrated"  # no history table, or the database is older than the code
    TOO_NEW = "too_new"  # the database is newer than the code
    INVALID = "invalid"


class SchemaVersionReader:
    """Read the migration history and verify its baseline against the packaged prefix."""

    def __init__(self, known_version: int, *, files: Sequence[MigrationFile] | None = None) -> None:
        if isinstance(known_version, bool) or known_version < 0:
            raise ValueError("known_version must be a non-negative integer")
        self._known = known_version
        self._files = files

    @property
    def known_version(self) -> int:
        return self._known

    def read(self, conn: psycopg.Connection) -> int | None:
        """The verified applied maximum, or ``None`` for a missing or empty history."""
        return self.read_fingerprint(conn)[0]

    def read_fingerprint(self, conn: psycopg.Connection) -> tuple[int | None, BaselineFingerprint | None]:
        with conn.transaction():
            history = read_migration_history(conn)
            marker = read_baseline(conn)
            if not history and marker is None:
                require_empty_database(conn)
                return None, None
        files = discover_migrations() if self._files is None else self._files
        expected = packaged_baseline(files)
        require_baseline(marker, expected)
        if not history:
            return None, marker
        newest = max(history)
        if not all(version in history for version in range(1, BASELINE_VERSION + 1)):
            raise PreconditionFailed(
                ErrorCode.MIGRATION_CHECKSUM_MISMATCH,
                "migration history is missing a baseline entry",
                details={"reason": "schema_baseline_incomplete"},
            )
        require_baseline((expected[0], baseline_chain_sha256(history)), expected)
        if BASELINE_VERSION < newest <= self._known:
            suffix = {
                item.version: (item.filename, item.checksum)
                for item in files
                if BASELINE_VERSION < item.version <= newest
            }
            if suffix != {version: row for version, row in history.items() if version > BASELINE_VERSION}:
                raise PreconditionFailed(
                    ErrorCode.MIGRATION_CHECKSUM_MISMATCH,
                    "migration history does not match the packaged migrations after the baseline",
                    details={"reason": "migration_history_mismatch"},
                )
        return newest, marker

    def compatibility(self, conn: psycopg.Connection) -> SchemaCompatibility:
        try:
            return self.classify(self.read(conn))
        except PreconditionFailed as error:
            if error.code is ErrorCode.MIGRATION_CHECKSUM_MISMATCH:
                return SchemaCompatibility.INVALID
            raise

    def classify(self, applied: int | None) -> SchemaCompatibility:
        if applied is None or applied < self._known:
            return SchemaCompatibility.NOT_MIGRATED
        if applied > self._known:
            return SchemaCompatibility.TOO_NEW
        return SchemaCompatibility.COMPATIBLE

    def require(self, conn: psycopg.Connection) -> int:
        """The applied version when it equals the known one; otherwise ``SCHEMA_NOT_MIGRATED`` /
        ``SCHEMA_TOO_NEW``."""
        applied = self.read(conn)
        state = self.classify(applied)
        if applied is None or state is SchemaCompatibility.NOT_MIGRATED:  # classify(None) is NOT_MIGRATED
            raise PreconditionFailed(
                ErrorCode.SCHEMA_NOT_MIGRATED,
                "database schema is not migrated",
                details={"database_version": applied, "code_version": self._known, "hint": "skm db migrate"},
            )
        if state is SchemaCompatibility.TOO_NEW:
            raise PreconditionFailed(
                ErrorCode.SCHEMA_TOO_NEW,
                "database schema is newer than this code",
                details={"database_version": applied, "code_version": self._known},
            )
        return applied
