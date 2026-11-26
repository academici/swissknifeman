"""Transactional-only migration runner (adapters §1.10).

One session-level advisory lock serializes runners; every migration body and its history row commit in
one transaction. There is no autocommit fallback: a statement PostgreSQL refuses inside a transaction
fails the migration. Discovery, ``verify`` and ``migrate`` reject non-transactional files before the
bootstrap or any DDL runs.
"""

import hashlib
import importlib.resources
import json
import re
import sys
import types
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import closing, suppress
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import ClassVar, Final, Literal, LiteralString, cast, override

import psycopg
import psycopg.abc
from psycopg import sql
from psycopg.rows import dict_row

from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.clock import Clock
from skm.kernel.errors import (
    BackendUnavailable,
    Forbidden,
    InternalError,
    PreconditionFailed,
    SkmError,
    error_for,
)
from skm.kernel.generated.error_codes import ErrorCode
from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import Diagnostic, Severity
from skm.platform.logging.logger import get_logger

# ``MigrationFile``, ``MigrationRunner``, ``MigrationSession`` and ``MigrationState`` are concrete types,
# not port bindings: importable by name, not exports.
__all__ = [
    "check_migration_sql",
    "directory_loader",
    "discover_migrations",
    "known_version",
    "package_loader",
    "validate_chain",
]

_FILE_NAME: Final = re.compile(r"^(\d{4})_([a-z]+)_([a-z0-9_]+)(\.data)?\.(sql|py)$")
# Module ids (src/skm/modules) and the infrastructure owners of both databases.
_MODULES: Final = frozenset(
    {
        "core",
        "config",
        "access",
        "artifacts",
        "context",
        "execution",
        "exports",
        "extensions",
        "integrations",
        "knowledge",
        "learning",
        "planning",
        "policy",
        "runtimes",
        "settings",
        "workspace",
    }
)
_IGNORED: Final = frozenset({"runner_bootstrap.sql", "__init__.py", "__pycache__", "README.md"})
_NO_TRANSACTION_MARKER: Final = re.compile(r"skm:no-transaction", re.IGNORECASE)
_WORD: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LINE_END: Final = re.compile(r"[\r\n]")  # PostgreSQL ends a -- comment at either character
_IDENTIFIER: Final = re.compile(
    r"[A-Za-z_\u0080-\U0010ffff][A-Za-z0-9_$\u0080-\U0010ffff]*"
)  # "$" continues a name
_ROUTINE: Final = re.compile(r"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\b", re.IGNORECASE)
_BEGIN_ATOMIC: Final = re.compile(r"\bBEGIN\s+ATOMIC\b", re.IGNORECASE)
_DOLLAR_TAG: Final = re.compile(r"\$(?:[A-Za-z_\u0080-\U0010ffff][A-Za-z0-9_\u0080-\U0010ffff]*)?\$")
_TRANSACTION_WORDS: Final = frozenset({"BEGIN", "COMMIT", "END", "ROLLBACK", "ABORT"})
_PACKAGE: Final = "skm.adapters.postgres.migrations"
type MigrationDatabase = Literal["project", "machine"]
_SCHEMA_NAMES: Final = {"project": "skm_core", "machine": "skm_host"}
_PACKAGE_DIRS: Final = {"project": "sql", "machine": "machine_sql"}
_MIGRATOR_ROLES: Final = {"project": "skm_migrator", "machine": "skm_host_migrator"}
BASELINE_EPOCH: Final = "0.1.0"
BASELINE_VERSION: Final = 1
_MACHINE_EPOCH: Final = "0.1.0-host"
type BaselineFingerprint = tuple[str, str]

# Normal object allocation starts at 16384. The dependency catalogs cover objects such as collations and
# text search dictionaries. A few classes can lack dependency records when their owner and referenced
# objects are built into PostgreSQL. Include those classes and schemas directly.
_NONEMPTY_DATABASE: Final = """
SELECT EXISTS (
    SELECT FROM pg_catalog.pg_namespace
    WHERE nspname NOT IN ('public', 'information_schema') AND nspname !~ '^pg_'
    UNION ALL
    SELECT FROM pg_catalog.pg_depend WHERE objid >= 16384
    UNION ALL
    SELECT FROM pg_catalog.pg_shdepend
    WHERE dbid = (SELECT oid FROM pg_catalog.pg_database WHERE datname = current_database())
      AND deptype = 'o' AND objid >= 16384
    UNION ALL
    SELECT FROM pg_catalog.pg_extension WHERE extname <> 'plpgsql'
    UNION ALL
    SELECT FROM pg_catalog.pg_cast WHERE oid >= 16384
    UNION ALL
    SELECT FROM pg_catalog.pg_largeobject_metadata
    UNION ALL
    SELECT FROM pg_catalog.pg_publication
    UNION ALL
    SELECT FROM pg_catalog.pg_foreign_data_wrapper
)
"""
_MIGRATOR_ALLOWED: Final = """
SELECT login.rolsuper OR EXISTS (
    SELECT FROM pg_catalog.pg_roles AS migrator
    WHERE migrator.rolname = %s AND pg_catalog.pg_has_role(current_user, migrator.oid, 'USAGE')
)
FROM pg_catalog.pg_roles AS login
WHERE login.rolname = current_user
"""

_log = get_logger("db.migrations")


@dataclass(frozen=True, slots=True)
class MigrationFile:
    version: int
    module: str
    slug: str
    kind: Literal["sql", "data_sql", "py"]
    checksum: str
    transactional: Literal[True]

    @property
    def filename(self) -> str:
        data = ".data" if self.kind == "data_sql" else ""
        return f"{self.version:04d}_{self.module}_{self.slug}{data}.{'py' if self.kind == 'py' else 'sql'}"


class MigrationState(StrEnum):
    APPLIED = "applied"
    PENDING = "pending"
    MODIFIED = "modified"
    UNKNOWN = "unknown"


class MigrationSession:
    """What a Python migration gets: checked SQL in, values out. No connection, cursor, commit or
    autocommit.

    Migration files are trusted operator code; this prevents accidental transaction control, it is not a
    sandbox.
    """

    __slots__ = ("_conn", "_file")

    def __init__(self, conn: psycopg.Connection, file: str) -> None:
        self._conn = conn
        self._file = file

    # The screened text is a plain str, not a LiteralString; the architecture allowlist pins these calls.
    def execute(self, sql: str, params: object = None) -> None:
        check_migration_sql(sql, file=self._file)
        self._conn.execute(cast("str", sql), cast("psycopg.abc.Params | None", params))  # pyright: ignore[reportUnnecessaryCast, reportArgumentType]

    def executemany(self, sql: str, params: Iterable[object]) -> None:
        check_migration_sql(sql, file=self._file)
        with self._conn.cursor() as cursor:
            cursor.executemany(cast("str", sql), cast("Iterable[psycopg.abc.Params]", params))  # pyright: ignore[reportUnnecessaryCast, reportArgumentType]

    def fetchall(self, sql: str, params: object = None) -> tuple[Mapping[str, object], ...]:
        check_migration_sql(sql, file=self._file)
        with self._conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(cast("str", sql), cast("psycopg.abc.Params | None", params))  # pyright: ignore[reportUnnecessaryCast, reportArgumentType]
            if cursor.description is None:
                return ()
            return tuple(cursor.fetchall())


type Loader = Callable[[MigrationFile], str | Callable[[MigrationSession], None]]


# --- SQL inspection ------------------------------------------------------------------------------------


def _non_transactional(file: str) -> InternalError:
    return InternalError(
        ErrorCode.INTERNAL_ERROR,
        "migration is not transactional",
        details={"reason": "non_transactional_migration", "file": file},
    )


def _scan(text: str) -> tuple[list[str], list[str]]:  # noqa: PLR0912 - one lexer loop over the SQL syntax
    """Split SQL into statements with literals, quoted identifiers and comments blanked; also return the
    comments."""
    statements: list[str] = []
    comments: list[str] = []
    buf: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        c = text[i]
        if text.startswith("--", i):
            end = _LINE_END.search(text, i)
            j = n if end is None else end.start()
            comments.append(text[i + 2 : j])
            buf.append(" ")
            i = j
        elif text.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif text.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            comments.append(text[i + 2 : j])
            buf.append(" ")
            i = j
        elif c in "'\"":
            escapes = (
                c == "'"
                and i > 0
                and text[i - 1] in "eE"
                and (i < 2 or not (text[i - 2].isalnum() or text[i - 2] == "_"))
            )
            j = i + 1
            while j < n:
                if escapes and text[j] == "\\":
                    j += 2
                elif text[j] == c:
                    if text.startswith(c * 2, j):
                        j += 2
                    else:
                        j += 1
                        break
                else:
                    j += 1
            buf.append(" ")
            i = min(j, n)
        elif (
            c == "$"
            and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_"))
            and (m := _DOLLAR_TAG.match(text, i))
        ):
            end = text.find(m.group(), m.end())
            buf.append(" ")
            i = n if end < 0 else end + len(m.group())
        elif _IDENTIFIER.match(c):  # a whole name, so a "$" inside it never opens a dollar quote
            name = _IDENTIFIER.match(text, i)
            end = name.end() if name else i + 1
            buf.append(text[i:end])
            i = end
        elif c == ";":
            statements.append("".join(buf))
            buf.clear()
            i += 1
        else:
            buf.append(c)
            i += 1
    statements.append("".join(buf))
    return statements, comments


def _opens_atomic_body(stripped: str) -> str | None:
    """For ``CREATE FUNCTION|PROCEDURE ... BEGIN ATOMIC`` outside parentheses, the text after ``ATOMIC``."""
    if _ROUTINE.match(stripped) is None:
        return None
    for found in _BEGIN_ATOMIC.finditer(stripped):
        before = stripped[: found.start()]
        if before.count("(") == before.count(")"):
            return stripped[found.end() :]
    return None


def _transaction_control(statements: Sequence[str]) -> bool:
    in_atomic_body = False
    for code in statements:
        stripped = code.strip()
        if not stripped:
            continue
        words = [w.upper() for w in _WORD.findall(stripped)]
        first = words[0] if words else ""
        if in_atomic_body:  # statements of CREATE FUNCTION ... BEGIN ATOMIC ...; END
            if words == ["END"]:
                in_atomic_body = False
            elif first in _TRANSACTION_WORDS:
                return True
            continue
        if stripped.startswith("\\"):  # psql meta-command, e.g. \set AUTOCOMMIT off
            return True
        second = words[1] if len(words) > 1 else ""
        if first in _TRANSACTION_WORDS or (first in {"START", "PREPARE"} and second == "TRANSACTION"):
            return True
        body = _opens_atomic_body(stripped)
        if body is not None:
            in_atomic_body = [w.upper() for w in _WORD.findall(body)] != ["END"]  # BEGIN ATOMIC END is closed
    return False


def check_migration_sql(text: str, *, file: str) -> None:
    """Reject the no-transaction marker and transaction control outside literals and comments."""
    statements, comments = _scan(text)
    if any(_NO_TRANSACTION_MARKER.search(comment) for comment in comments) or _transaction_control(
        statements
    ):
        raise _non_transactional(file)


# --- Discovery -----------------------------------------------------------------------------------------


def _checksum(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _build_error(file: str, reason: str) -> InternalError:
    return InternalError(
        ErrorCode.INTERNAL_ERROR, "migration chain cannot be built", details={"file": file, "reason": reason}
    )


def validate_chain(files: Sequence[MigrationFile], *, database: MigrationDatabase = "project") -> None:
    """Build-time checks: transactional only, known module, unique and gap-free numbering from 0001."""
    seen: dict[int, MigrationFile] = {}
    owners = _MODULES if database == "project" else {"host"}
    for item in files:
        if item.transactional is not True:
            raise _non_transactional(item.filename)
        if item.module not in owners:
            raise _build_error(item.filename, "unknown_module")
        if item.version in seen:
            raise _build_error(item.filename, "duplicate_version")
        seen[item.version] = item
    for expected, version in enumerate(sorted(seen), start=1):
        if version != expected:
            raise _build_error(seen[version].filename, "gap_in_numbering")


def _package_root(database: MigrationDatabase = "project") -> Traversable:
    return importlib.resources.files(_PACKAGE).joinpath(_PACKAGE_DIRS[database])


def discover_migrations(
    root: Traversable | Path | None = None, *, database: MigrationDatabase = "project"
) -> tuple[MigrationFile, ...]:
    """Numbered migration files for the selected database, in version order."""
    directory: Traversable = _package_root(database) if root is None else root
    found: list[MigrationFile] = []
    for entry in directory.iterdir():
        name = entry.name
        if name in _IGNORED or entry.is_dir() or not name.endswith((".sql", ".py")):
            continue
        match = _FILE_NAME.match(name)
        if match is None or (match.group(4) and match.group(5) == "py"):
            raise _build_error(name, "bad_file_name")
        number, module, slug, data, extension = match.groups()
        data_bytes = entry.read_bytes()
        if extension == "py" and _NO_TRANSACTION_MARKER.search(data_bytes.decode("utf-8", errors="replace")):
            raise _non_transactional(name)
        kind: Literal["sql", "data_sql", "py"] = (
            "py" if extension == "py" else ("data_sql" if data else "sql")
        )
        found.append(MigrationFile(int(number), module, slug, kind, _checksum(data_bytes), True))
    found.sort(key=lambda item: item.version)
    validate_chain(found, database=database)
    return tuple(found)


def known_version(files: Sequence[MigrationFile]) -> int:
    """The highest migration number of the chain (0 for an empty chain)."""
    return max((item.version for item in files), default=0)


def baseline_chain_sha256(history: Mapping[int, tuple[str, str]]) -> str:
    prefix = [(version, *history[version]) for version in range(1, BASELINE_VERSION + 1)]
    encoded = json.dumps(prefix, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def packaged_baseline(
    files: Sequence[MigrationFile] | None = None, *, database: MigrationDatabase = "project"
) -> BaselineFingerprint:
    files = discover_migrations(database=database) if files is None else files
    history = {item.version: (item.filename, item.checksum) for item in files}
    if not all(version in history for version in range(1, BASELINE_VERSION + 1)):
        raise _build_error(f"{BASELINE_VERSION:04d}", "baseline_prefix_incomplete")
    epoch = BASELINE_EPOCH if database == "project" else _MACHINE_EPOCH
    return epoch, baseline_chain_sha256(history)


def read_migration_history(
    conn: psycopg.Connection, *, database: MigrationDatabase = "project"
) -> dict[int, tuple[str, str]]:
    probe = conn.execute(
        "SELECT pg_catalog.to_regclass(%s) IS NOT NULL", (f"{_SCHEMA_NAMES[database]}.schema_migrations",)
    ).fetchone()
    if probe is None or not probe[0]:
        return {}
    rows = conn.execute(
        sql.SQL("SELECT version, name, checksum FROM {}.schema_migrations ORDER BY version").format(
            sql.Identifier(_SCHEMA_NAMES[database])
        )
    )
    return {int(version): (str(name), str(checksum)) for version, name, checksum in rows}


def read_baseline(
    conn: psycopg.Connection, *, database: MigrationDatabase = "project"
) -> BaselineFingerprint | None:
    probe = conn.execute(
        "SELECT pg_catalog.to_regclass(%s) IS NOT NULL", (f"{_SCHEMA_NAMES[database]}.schema_baseline",)
    ).fetchone()
    if probe is None or not probe[0]:
        return None
    row = conn.execute(
        sql.SQL("SELECT epoch, chain_sha256 FROM {}.schema_baseline WHERE id").format(
            sql.Identifier(_SCHEMA_NAMES[database])
        )
    ).fetchone()
    return None if row is None else (str(row[0]), str(row[1]))


def require_empty_database(conn: psycopg.Connection) -> None:
    row = conn.execute(_NONEMPTY_DATABASE).fetchone()
    if row is not None and row[0]:
        raise PreconditionFailed(
            ErrorCode.MIGRATION_CHECKSUM_MISMATCH,
            "Database has objects but no SKM 0.1.0 schema baseline",
            details={"reason": "schema_baseline_missing"},
        )


def require_baseline(marker: BaselineFingerprint | None, expected: BaselineFingerprint) -> None:
    if marker != expected:
        raise PreconditionFailed(
            ErrorCode.MIGRATION_CHECKSUM_MISMATCH,
            "database schema baseline does not match the packaged migrations",
            details={"reason": "schema_baseline_missing" if marker is None else "schema_baseline_mismatch"},
        )


def _source_changed(item: MigrationFile) -> PreconditionFailed:
    return PreconditionFailed(
        ErrorCode.MIGRATION_CHECKSUM_MISMATCH,
        "migration file changed after discovery",
        details={"version": item.version, "file": item.filename, "reason": "source_changed"},
    )


def _load_apply(entry: Traversable, item: MigrationFile) -> Callable[[MigrationSession], None]:
    """Compile and run the very bytes whose checksum was verified; the file is read once."""
    data = entry.read_bytes()
    if _checksum(data) != item.checksum:
        raise _source_changed(item)
    if _NO_TRANSACTION_MARKER.search(data.decode("utf-8", errors="replace")):
        raise _non_transactional(item.filename)
    name = f"skm_migration_{item.filename.removesuffix('.py')}"
    module = types.ModuleType(name)
    module.__file__ = str(entry)
    sys.modules[name] = module  # a fresh module per load; dataclasses and typing look it up here
    try:
        exec(compile(data, str(entry), "exec", dont_inherit=True), module.__dict__)  # noqa: S102 - trusted operator file
    except BaseException:
        sys.modules.pop(name, None)
        raise
    apply = getattr(module, "apply", None)
    if not callable(apply):
        raise _build_error(item.filename, "missing_apply")
    return cast("Callable[[MigrationSession], None]", apply)


def directory_loader(root: Traversable | Path) -> Loader:
    """Loader for a directory: SQL text for ``sql`` / ``data_sql``, the ``apply`` function for ``py``."""

    def load(item: MigrationFile) -> str | Callable[[MigrationSession], None]:
        entry = root.joinpath(item.filename)
        if item.kind == "py":
            return _load_apply(entry, item)
        # bytes, not read_text(): universal newlines would also rewrite a lone "\r" and break the checksum
        return entry.read_bytes().decode("utf-8").replace("\r\n", "\n")

    return load


def package_loader(*, database: MigrationDatabase = "project") -> Loader:
    return directory_loader(_package_root(database))


# The baseline is immutable. Provision its cluster-wide roles before its check-then-create block.
_PREPARE_PROJECT_ROLES: Final = """
DO $$
DECLARE role_name text;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND (rolsuper OR rolcreaterole)) THEN
        FOREACH role_name IN ARRAY ARRAY['skm_app', 'skm_migrator'] LOOP
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                BEGIN
                    EXECUTE format('CREATE ROLE %I NOLOGIN', role_name);
                EXCEPTION WHEN duplicate_object OR unique_violation THEN
                    NULL;
                END;
            END IF;
        END LOOP;
    END IF;
END
$$
"""


def _bootstrap_sql(database: MigrationDatabase) -> LiteralString:
    """The packaged bootstrap file for the selected database."""
    return cast(
        "LiteralString",
        importlib.resources.files(_PACKAGE)
        .joinpath(_PACKAGE_DIRS[database], "runner_bootstrap.sql")
        .read_text(encoding="utf-8"),
    )


# --- Runner --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Finding:
    code: ErrorCode
    version: int
    file: str
    reason: str | None = None
    code_version: int | None = None

    def details(self) -> dict[str, JsonValue]:
        details: dict[str, JsonValue] = {"version": self.version, "file": self.file}
        if self.reason is not None:
            details["reason"] = self.reason
        if self.code_version is not None:
            details["code_version"] = self.code_version
        return details


class MigrationRunner:
    # int.from_bytes(b"SKM_MIGR", "big")
    LOCK_ID: ClassVar[int] = 6001976000115197778

    def __init__(
        self,
        dsn: str,
        files: Sequence[MigrationFile],
        loader: Loader,
        clock: Clock,
        applied_by: str,
        *,
        database: MigrationDatabase = "project",
        use_packaged_baseline: bool = True,
    ) -> None:
        ordered = tuple(sorted(files, key=lambda item: item.version))
        validate_chain(ordered, database=database)
        self._dsn = dsn
        self._files = ordered
        self._by_version = {item.version: item for item in ordered}
        self._loader = loader
        self._clock = clock
        self._applied_by = applied_by
        self._database: MigrationDatabase = database
        self._use_packaged_baseline = use_packaged_baseline

    @override
    def __repr__(self) -> str:  # the DSN holds a secret
        return f"MigrationRunner(files={len(self._files)}, applied_by={self._applied_by!r})"

    @property
    def files(self) -> tuple[MigrationFile, ...]:
        return self._files

    # -- public API --

    def status(self) -> tuple[tuple[MigrationFile | None, int, MigrationState], ...]:
        with closing(self._connect()) as conn:
            history = self._read_history(conn)
        return self._entries(history)

    def check_baseline(self) -> None:
        expected = self._expected_baseline()
        try:
            with closing(self._connect()) as conn, conn.transaction():
                self._read_checked(conn, expected)
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc

    def migrate(self, *, target: int | None = None, dry_run: bool = False) -> tuple[int, ...]:
        limit = self._limit(target)
        sources = self._preflight()
        expected = self._expected_baseline()
        if dry_run:
            with closing(self._connect()) as conn, conn.transaction():
                history, _ = self._read_for_migration(conn, expected)
            return self._pending(history, limit)
        conn = self._connect()
        try:
            self._lock(conn)
            try:
                with conn.transaction():
                    history, marker = self._read_for_migration(conn, expected)
                    if marker is None and not self._files:
                        self._initialize(conn, expected)
                pending = self._pending(history, limit)
                for version in pending:
                    self._apply_one(
                        conn,
                        self._by_version[version],
                        sources[version],
                        initialize=expected if marker is None and version == BASELINE_VERSION else None,
                    )
                return pending
            finally:
                self._unlock(conn)
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc
        finally:
            conn.close()

    def verify(self) -> tuple[Diagnostic, ...]:
        self._preflight()
        with closing(self._connect()) as conn:
            history = self._read_history(conn)
        diagnostics = [
            Diagnostic(
                finding.code.value,
                "migration history does not match the packaged migrations",
                Severity.ERROR,
                target=finding.file,
                details=finding.details(),
            )
            for finding in self._findings(history)
        ]
        diagnostics.extend(
            Diagnostic(
                ErrorCode.SCHEMA_NOT_MIGRATED.value,
                "migration is pending",
                Severity.WARNING,
                target=self._by_version[version].filename,
                details={"version": version},
            )
            for version in self._pending(history, None)
        )
        return tuple(diagnostics)

    # -- test seams (called inside / right after the migration transaction) --

    def _record_applied(self, conn: psycopg.Connection, item: MigrationFile, duration_ms: int) -> None:
        conn.execute(
            sql.SQL(
                "INSERT INTO {}.schema_migrations (version, name, checksum, applied_by, duration_ms) "
                "VALUES (%s, %s, %s, %s, %s)"
            ).format(sql.Identifier(_SCHEMA_NAMES[self._database])),
            (item.version, item.filename, item.checksum, self._applied_by, duration_ms),
        )

    def _after_commit(self, item: MigrationFile) -> None:
        """Runs once the migration transaction has committed."""

    # -- internals --

    def _limit(self, target: int | None) -> int | None:
        if target is None:
            return None
        if isinstance(target, bool) or target not in self._by_version:
            raise error_for(
                ErrorCode.SCHEMA_INVALID, "target is not a migration number", details={"field": "target"}
            )
        return target

    def _connect(self) -> psycopg.Connection:
        """A separate autocommit connection; the caller closes it."""
        try:
            return psycopg.connect(self._dsn, autocommit=True)
        except psycopg.Error as exc:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE, "cannot connect to the database", details={"phase": "connect"}
            ) from translate_pg_error(exc)

    def _lock(self, conn: psycopg.Connection) -> None:
        conn.execute("SELECT pg_advisory_lock(%s)", (self.LOCK_ID,))

    def _unlock(self, conn: psycopg.Connection) -> None:
        with suppress(psycopg.Error):  # a broken connection drops its session lock when it closes
            conn.execute("SELECT pg_advisory_unlock(%s)", (self.LOCK_ID,))

    def _preflight(self) -> dict[int, str | Callable[[MigrationSession], None]]:
        """Load and check every source before any connection is opened."""
        sources: dict[int, str | Callable[[MigrationSession], None]] = {}
        for item in self._files:
            if item.transactional is not True:
                raise _non_transactional(item.filename)
            source = self._loader(item)
            if isinstance(source, str):
                check_migration_sql(source, file=item.filename)
                if _checksum(source.encode("utf-8")) != item.checksum:
                    raise _source_changed(item)
            elif not callable(source):
                raise _build_error(item.filename, "missing_apply")
            sources[item.version] = source
        return sources

    def _expected_baseline(self) -> BaselineFingerprint:
        if not self._files and not self._use_packaged_baseline:
            return packaged_baseline(database=self._database)
        baseline = packaged_baseline(self._files, database=self._database)
        if self._use_packaged_baseline:
            require_baseline(baseline, packaged_baseline(database=self._database))
        return baseline

    def _read_history(self, conn: psycopg.Connection) -> dict[int, tuple[str, str]]:
        return read_migration_history(conn, database=self._database)

    def _read_checked(
        self, conn: psycopg.Connection, expected: BaselineFingerprint
    ) -> tuple[dict[int, tuple[str, str]], BaselineFingerprint | None]:
        history = self._read_history(conn)
        marker = read_baseline(conn, database=self._database)
        if history or marker is not None:
            require_baseline(marker, expected)
        else:
            require_empty_database(conn)
        return history, marker

    def _read_for_migration(
        self, conn: psycopg.Connection, expected: BaselineFingerprint
    ) -> tuple[dict[int, tuple[str, str]], BaselineFingerprint | None]:
        history, marker = self._read_checked(conn, expected)
        role = _MIGRATOR_ROLES[self._database]
        allowed = conn.execute(_MIGRATOR_ALLOWED, (role,)).fetchone()
        if allowed != (True,):
            raise Forbidden(
                ErrorCode.FORBIDDEN,
                "Database migration requires the configured migrator role",
                details={"reason": "migrator_role_required", "database": self._database, "role": role},
            )
        self._raise_first(history)
        return history, marker

    def _initialize(self, conn: psycopg.Connection, expected: BaselineFingerprint) -> None:
        conn.execute(_bootstrap_sql(self._database))
        conn.execute(
            sql.SQL(
                "INSERT INTO {}.schema_baseline (epoch, chain_sha256, updated_at) VALUES (%s, %s, now())"
            ).format(sql.Identifier(_SCHEMA_NAMES[self._database])),
            expected,
        )

    def _findings(self, history: Mapping[int, tuple[str, str]]) -> list[_Finding]:
        findings: list[_Finding] = []
        newest = known_version(self._files)
        for version in sorted(history):
            name, checksum = history[version]
            item = self._by_version.get(version)
            if item is None and version > newest:
                findings.append(_Finding(ErrorCode.SCHEMA_TOO_NEW, version, name, code_version=newest))
            elif item is None:
                findings.append(
                    _Finding(ErrorCode.MIGRATION_CHECKSUM_MISMATCH, version, name, "deleted_file")
                )
            elif item.checksum != checksum:
                findings.append(
                    _Finding(ErrorCode.MIGRATION_CHECKSUM_MISMATCH, version, item.filename, "checksum")
                )
            elif item.filename != name:
                findings.append(
                    _Finding(ErrorCode.MIGRATION_CHECKSUM_MISMATCH, version, item.filename, "name")
                )
        highest = max(history, default=0)
        findings.extend(
            _Finding(ErrorCode.MIGRATION_CHECKSUM_MISMATCH, item.version, item.filename, "out_of_order")
            for item in self._files
            if item.version not in history and item.version < highest
        )
        return findings

    def _raise_first(self, history: Mapping[int, tuple[str, str]]) -> None:
        for finding in self._findings(history):
            raise PreconditionFailed(
                finding.code, "migration history does not match", details=finding.details()
            )

    def _pending(self, history: Mapping[int, tuple[str, str]], limit: int | None) -> tuple[int, ...]:
        return tuple(
            item.version
            for item in self._files
            if item.version not in history and (limit is None or item.version <= limit)
        )

    def _entries(
        self, history: Mapping[int, tuple[str, str]]
    ) -> tuple[tuple[MigrationFile | None, int, MigrationState], ...]:
        entries: list[tuple[MigrationFile | None, int, MigrationState]] = []
        for version in sorted(set(history) | set(self._by_version)):
            item = self._by_version.get(version)
            if version not in history:
                state = MigrationState.PENDING
            elif item is None:
                state = MigrationState.UNKNOWN
            elif history[version] == (item.filename, item.checksum):
                state = MigrationState.APPLIED
            else:
                state = MigrationState.MODIFIED
            entries.append((item, version, state))
        return tuple(entries)

    def _apply_one(
        self,
        conn: psycopg.Connection,
        item: MigrationFile,
        source: str | Callable[[MigrationSession], None],
        *,
        initialize: BaselineFingerprint | None = None,
    ) -> None:
        started = self._clock.now()
        try:
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(hashtext('skm.migrations'))")
                if initialize is not None:
                    self._initialize(conn, initialize)
                if self._database == "project" and item.filename == "0001_core_baseline.sql":
                    conn.execute(_PREPARE_PROJECT_ROLES)
                if isinstance(source, str):
                    conn.execute(cast("str", source))  # pyright: ignore[reportUnnecessaryCast, reportArgumentType, reportCallIssue]
                else:
                    source(MigrationSession(conn, item.filename))
                duration_ms = max(0, self._elapsed_ms(started))
                self._record_applied(conn, item, duration_ms)
        except psycopg.Error as exc:
            raise self._failure(item, exc) from exc
        except SkmError:
            raise
        except Exception as exc:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "migration failed",
                details={"version": item.version, "file": item.filename, "reason": "apply_failed"},
            ) from exc
        _log.info("db.migration.applied", version=item.version, duration_ms=duration_ms)
        self._after_commit(item)

    def _elapsed_ms(self, started: datetime) -> int:
        return int((self._clock.now() - started).total_seconds() * 1000)

    def _failure(self, item: MigrationFile, exc: psycopg.Error) -> SkmError:
        translated = translate_pg_error(exc)
        details: dict[str, JsonValue] = {**translated.details, "version": item.version, "file": item.filename}
        position = exc.diag.statement_position
        if position is not None and str(position).isdigit():
            details["statement_position"] = int(position)
        return error_for(translated.code, "migration failed", details=details, retryable=translated.retryable)
