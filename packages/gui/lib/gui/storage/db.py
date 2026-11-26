"""``gui.db``: SQLite state of the backend in ``state_dir("gui")`` (decision D8).

Canonical SKM files stay the source of truth (I1); the database holds the project registry, preferences, the audit
trail and, from migration 2, runs. Migrations only get appended: ``PRAGMA user_version`` names the last one applied
and each runs in its own ``BEGIN IMMEDIATE`` transaction. A database written by a newer gui (``user_version`` above
the last known migration) is refused with ``STATE_INCOMPATIBLE`` before anything is written to it.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Mapping, Optional, Tuple, Union

from aicore.state.locations import ensure_dir, state_dir

from ..errors import GuiError

DB_NAME = "gui.db"

MIGRATIONS: List[Tuple[int, str]] = [
    (1, """
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    root TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    trusted INTEGER NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('open', 'user')),
    added_at TEXT NOT NULL
);
CREATE TABLE prefs (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE audit (
    id INTEGER PRIMARY KEY,
    at TEXT,
    actor TEXT,
    action TEXT,
    target TEXT,
    decision TEXT,
    details_json TEXT,
    correlation_id TEXT
);
"""),
    (2, """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    command TEXT NOT NULL,
    owner TEXT NOT NULL,
    state TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    project_id TEXT,
    context_json TEXT NOT NULL,
    input_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    exit_code INTEGER,
    exit_signal TEXT,
    pid INTEGER,
    pid_start TEXT,
    executable_json TEXT,
    argv_json TEXT,
    cwd TEXT,
    actor_json TEXT NOT NULL,
    permission_json TEXT NOT NULL,
    log_json TEXT NOT NULL,
    error_json TEXT,
    correlation_id TEXT NOT NULL
);
CREATE INDEX runs_by_state ON runs (state);
CREATE INDEX runs_by_project ON runs (project_id, created_at);
CREATE TABLE run_transitions (
    run_id TEXT NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    at TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
"""),
    (3, """
CREATE TABLE plugins (
    id TEXT PRIMARY KEY,
    desired TEXT NOT NULL CHECK (desired IN ('new', 'enabled', 'disabled')),
    quarantined_at TEXT,
    quarantine_code TEXT,
    reapproval INTEGER NOT NULL DEFAULT 0,
    digest TEXT,
    effects_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE plugin_events (
    id INTEGER PRIMARY KEY,
    plugin TEXT NOT NULL,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    code TEXT,
    detail TEXT
);
CREATE INDEX plugin_events_by_plugin ON plugin_events (plugin, id);
CREATE TABLE grants (
    id TEXT PRIMARY KEY,
    plugin TEXT NOT NULL,
    capability TEXT NOT NULL,
    project_id TEXT,
    manifest_digest TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    expires_at TEXT,
    granted_by TEXT NOT NULL,
    revoked_at TEXT,
    voided_at TEXT,
    void_reason TEXT
);
CREATE INDEX grants_by_plugin ON grants (plugin);
"""),
]


def schema_version() -> int:
    """The ``user_version`` this code writes: the number of the last migration."""
    return MIGRATIONS[-1][0] if MIGRATIONS else 0


def now() -> str:
    """The current UTC time as RFC 3339 with seconds (``2026-10-16T12:00:00Z``)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_path(env: Optional[Mapping[str, str]] = None) -> Path:
    return state_dir("gui", env=env) / DB_NAME


def open_db(path: Union[str, Path, None] = None, *, env: Optional[Mapping[str, str]] = None,
            migrations: Optional[List[Tuple[int, str]]] = None) -> sqlite3.Connection:
    """Open (creating when missing) and migrate ``gui.db``: WAL, foreign keys, autocommit with explicit transactions.

    The folder is created owner-only and the file is ``0600``. ``STATE_INCOMPATIBLE`` when the file is newer than
    the known migrations; the file is then not written.
    """
    target = Path(path) if path is not None else default_path(env)
    steps = MIGRATIONS if migrations is None else migrations
    known = steps[-1][0] if steps else 0
    ensure_dir(target.parent)
    existed = target.exists()
    if existed:
        found = _peek_version(target)
        if found > known:
            raise GuiError("STATE_INCOMPATIBLE", f"{target.name} has schema version {found}, this gui knows up to "
                                                 f"{known}; use the newer gui or move the file away")
    else:
        os.close(os.open(str(target), os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600))
    conn = sqlite3.connect(str(target), isolation_level=None, check_same_thread=False)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        migrate(conn, steps)
    except BaseException:
        conn.close()
        raise
    return conn


def _peek_version(target: Path) -> int:
    """``user_version`` read through a read-only connection, so a newer file is never touched."""
    uri = target.resolve().as_uri() + "?mode=ro"
    try:
        probe = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        raise GuiError("STATE_INCOMPATIBLE", f"{target.name} cannot be opened: {error}") from None
    try:
        return int(probe.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.DatabaseError as error:
        raise GuiError("STATE_INCOMPATIBLE", f"{target.name} is not a gui database: {error}") from None
    finally:
        probe.close()


def migrate(conn: sqlite3.Connection, migrations: Optional[List[Tuple[int, str]]] = None) -> int:
    """Apply the missing migrations in order, one transaction each; returns the resulting ``user_version``."""
    steps = MIGRATIONS if migrations is None else migrations
    numbers = [number for number, _ in steps]
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError("migrations must be numbered 1, 2, 3, ... without gaps")
    known = numbers[-1] if numbers else 0
    for number, script in steps:
        conn.execute("BEGIN IMMEDIATE")
        try:
            current = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if current > known:
                raise GuiError("STATE_INCOMPATIBLE", f"database schema version {current} is newer than {known}")
            if current >= number:
                conn.execute("COMMIT")
                continue
            for statement in _statements(script):
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {int(number)}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _statements(script: str) -> List[str]:
    """Split a migration into statements (``executescript`` would commit the open transaction)."""
    found, buffer = [], ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                found.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        raise ValueError(f"incomplete SQL statement in a migration: {buffer.strip()[:60]!r}")
    return found


def audit(conn: sqlite3.Connection, *, actor: str, action: str, target: str, decision: str,
          details: Optional[Mapping[str, object]] = None, correlation_id: Optional[str] = None) -> int:
    """Append one audit row (in the caller's transaction when one is open); returns its id."""
    cursor = conn.execute(
        "INSERT INTO audit (at, actor, action, target, decision, details_json, correlation_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (now(), actor, action, target, decision, json.dumps(dict(details or {}), ensure_ascii=False, sort_keys=True),
         correlation_id))
    return int(cursor.lastrowid)
