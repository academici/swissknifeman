"""``gui state check|rebuild``: integrity of ``gui.db`` and its rebuild into a fresh, fully migrated file (stdlib + aicore).

The operator's decisions (plugins, grants, their history) live only in SQLite (D22), so :func:`rebuild` never drops a
row: it copies a backup first, builds the new database next to the old one, copies every table row by row, compares
the rows of both files, checks the new file and only then swaps it in with ``os.replace``. Any failure before the
swap leaves ``gui.db`` byte for byte as it was. The caller holds the backend ``InstanceLock``.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from ..storage import db

# runs before run_transitions: the child table has a foreign key.
TABLES = ("projects", "prefs", "audit", "plugins", "plugin_events", "grants", "runs", "run_transitions")
OPERATOR_TABLES = ("plugins", "plugin_events", "grants")
MISSING = "STATE_MISSING"
REBUILD_FAILED = "STATE_REBUILD_FAILED"
INCOMPATIBLE = "STATE_INCOMPATIBLE"


class StateError(Exception):
    """A failure of ``gui state``: the code names it, the message says what to do; ``gui.db`` is untouched."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _uri(path: Path) -> str:
    return "file:" + quote(str(path.resolve())) + "?mode=ro"


def _open_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(_uri(path), uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn: sqlite3.Connection, schema: str = "main") -> List[str]:
    return [row[0] for row in conn.execute(f"SELECT name FROM {schema}.sqlite_master WHERE type = 'table'")]


def _columns(conn: sqlite3.Connection, table: str, schema: str = "main") -> List[str]:
    return [row[1] for row in conn.execute(f"PRAGMA {schema}.table_info({table})")]


def check(path: Path) -> Dict[str, Any]:
    """Read-only report: integrity, foreign keys, schema version and row counts; ``ok`` says whether all is well."""
    path = Path(path)
    report: Dict[str, Any] = {"path": str(path), "exists": path.is_file(), "ok": False, "integrity": [],
                              "foreign_key_violations": 0, "schema_version": None, "known_version": db.schema_version(),
                              "tables": {}, "missing_tables": [], "problems": []}
    if not report["exists"]:
        report["problems"].append(f"{path.name} does not exist")
        return report
    try:
        conn = _open_ro(path)
    except sqlite3.Error as error:
        report["problems"].append(f"cannot open: {error}")
        return report
    try:
        report["integrity"] = [str(row[0]) for row in conn.execute("PRAGMA integrity_check")]
        if report["integrity"] != ["ok"]:
            report["problems"].append("integrity_check reports damage")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        report["foreign_key_violations"] = len(violations)
        if violations:
            report["problems"].append(f"{len(violations)} foreign key violation(s)")
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        report["schema_version"] = version
        if version > report["known_version"]:
            report["problems"].append(f"schema version {version} is newer than this gui knows "
                                      f"({report['known_version']})")
        present = set(_tables(conn))
        for table in TABLES:
            if table in present:
                report["tables"][table] = int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        if version == report["known_version"]:
            report["missing_tables"] = [table for table in TABLES if table not in present]
            if report["missing_tables"]:
                report["problems"].append("tables missing: " + ", ".join(report["missing_tables"]))
    except sqlite3.Error as error:
        report["problems"].append(f"not a readable gui database: {error}")
    finally:
        conn.close()
    report["ok"] = not report["problems"]
    return report


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _backup_path(folder: Path) -> Path:
    base = folder / f"{db.DB_NAME}.bak-{_stamp()}"
    candidate, number = base, 0
    while candidate.exists():
        number += 1
        candidate = Path(f"{base}-{number}")
    return candidate


def _plan(source: Path) -> Dict[str, Any]:
    """What a rebuild would copy: per table the rows and the columns shared by the old and the new schema."""
    scratch = sqlite3.connect(":memory:")
    try:
        db.migrate(scratch, db.MIGRATIONS)
        fresh = {table: _columns(scratch, table) for table in TABLES}
    finally:
        scratch.close()
    try:
        conn = _open_ro(source)
    except sqlite3.Error as error:
        raise StateError(REBUILD_FAILED, f"{source.name} cannot be opened: {error}") from None
    try:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version > db.schema_version():
            raise StateError(INCOMPATIBLE, f"{source.name} has schema version {version}, this gui knows up to "
                                           f"{db.schema_version()}; use the newer gui")
        present = set(_tables(conn))
        tables: Dict[str, Any] = {}
        for table in TABLES:
            if table not in present:
                continue
            shared = [column for column in fresh[table] if column in set(_columns(conn, table))]
            tables[table] = {"rows": int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]),
                             "columns": shared}
    except sqlite3.Error as error:
        raise StateError(REBUILD_FAILED, f"{source.name} cannot be read: {error}") from None
    finally:
        conn.close()
    return {"from_version": version, "to_version": db.schema_version(), "tables": tables}


def _copy_table(conn: sqlite3.Connection, table: str, columns: List[str]) -> None:
    names = ", ".join(columns)
    conn.execute(f"INSERT INTO main.{table} ({names}) SELECT {names} FROM old.{table}")


def _compare(conn: sqlite3.Connection, table: str, columns: List[str]) -> None:
    """The rows of ``old`` and ``main`` are the same multiset (counts equal, no row on one side only)."""
    names = ", ".join(columns)
    before = int(conn.execute(f"SELECT count(*) FROM old.{table}").fetchone()[0])
    after = int(conn.execute(f"SELECT count(*) FROM main.{table}").fetchone()[0])
    lost = int(conn.execute(f"SELECT count(*) FROM (SELECT {names} FROM old.{table} EXCEPT "
                            f"SELECT {names} FROM main.{table})").fetchone()[0])
    extra = int(conn.execute(f"SELECT count(*) FROM (SELECT {names} FROM main.{table} EXCEPT "
                             f"SELECT {names} FROM old.{table})").fetchone()[0])
    if before != after or lost or extra:
        raise StateError(REBUILD_FAILED, f"table {table}: {before} row(s) before, {after} after, "
                                         f"{lost} lost, {extra} changed")


def _remove(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink()
        except OSError:
            pass


def rebuild(folder: Path, *, dry_run: bool = False) -> Dict[str, Any]:
    """Rebuild ``folder/gui.db``; returns the report. ``dry_run`` reads the old file and writes nothing."""
    folder = Path(folder)
    source = folder / db.DB_NAME
    if not source.is_file():
        raise StateError(MISSING, f"{source} does not exist; nothing to rebuild")
    plan = _plan(source)
    report: Dict[str, Any] = {"path": str(source), "dry_run": dry_run, "rebuilt": False, "backup": None, **plan}
    if dry_run:
        report["backup"] = str(_backup_path(folder))
        return report

    backup = _backup_path(folder)
    work = folder / f".{db.DB_NAME}.new-{os.getpid()}"
    sidecars = [Path(f"{work}-wal"), Path(f"{work}-shm"), Path(f"{work}-journal")]
    _remove(work, *sidecars)
    new: Optional[sqlite3.Connection] = None
    try:
        reader = _open_ro(source)
        try:
            copy = sqlite3.connect(str(backup))
            try:
                reader.backup(copy)
                copy.execute("PRAGMA journal_mode = DELETE")  # a single, self-contained file
            finally:
                copy.close()
        finally:
            reader.close()
        os.chmod(backup, 0o600)

        new = db.open_db(work)
        new.execute("ATTACH DATABASE ? AS old", (str(backup),))  # the snapshot: what the rows are compared with
        new.execute("BEGIN IMMEDIATE")
        try:
            for table, entry in plan["tables"].items():
                _copy_table(new, table, entry["columns"])
            for table, entry in plan["tables"].items():
                _compare(new, table, entry["columns"])
            new.execute("COMMIT")
        except BaseException:
            new.execute("ROLLBACK")
            raise
        new.execute("DETACH DATABASE old")
        found = [str(row[0]) for row in new.execute("PRAGMA integrity_check")]
        if found != ["ok"]:
            raise StateError(REBUILD_FAILED, "the new database fails integrity_check: " + "; ".join(found[:3]))
        if new.execute("PRAGMA foreign_key_check").fetchall():
            raise StateError(REBUILD_FAILED, "the new database has foreign key violations")
        new.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        new.execute("PRAGMA journal_mode = DELETE")  # one file: no -wal of the new file can outlive the swap
        new.close()
        new = None

        # The old WAL is folded into gui.db now, so the leftovers removed after the swap hold nothing.
        old = sqlite3.connect(str(source), timeout=5)
        try:
            old.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            old.close()
        os.replace(work, source)
        _remove(Path(f"{source}-wal"), Path(f"{source}-shm"))
    except StateError:
        _cleanup(new, work, sidecars)
        raise
    except (sqlite3.Error, OSError) as error:
        _cleanup(new, work, sidecars)
        raise StateError(REBUILD_FAILED, f"{error}; {source.name} was not changed (backup: {backup})") from None
    except BaseException:
        _cleanup(new, work, sidecars)
        raise
    report.update(rebuilt=True, backup=str(backup))
    return report


def _cleanup(new: Optional[sqlite3.Connection], work: Path, sidecars: List[Path]) -> None:
    if new is not None:
        try:
            new.close()
        except sqlite3.Error:
            pass
    _remove(work, *sidecars)
