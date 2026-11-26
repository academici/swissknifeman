"""SQLite episodic memory kept in a private directory on the originating host."""

import os
import sqlite3
import stat
from collections.abc import Generator
from contextlib import closing, contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import NamedTuple, cast, override
from uuid import UUID

from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, Forbidden, ValidationFailed
from skm.modules.knowledge.domain.memory_kind import MemoryKind
from skm.modules.knowledge.ports import EpisodeRecordStatus, EpisodeScope, LocalEpisode, LocalEpisodicMemory

__all__ = ["LocalSqliteMemoryStore"]

_DEFAULT_TTL_SECONDS = 7 * 24 * 3600
_MAX_TTL_SECONDS = 30 * 24 * 3600
_HEALTH_TTL_SECONDS = 300
_HEALTH_INTERVAL_SECONDS = 30
_HEALTH_CAP = 8
_TEXT_LIMIT = 2000
_SUMMARY_COUNT = 8
_SUMMARY_WIDTH = 180
# Descriptor-based repairs must run before any store connection acquires POSIX locks in this process.
_CONNECTION_LOCK = Lock()


class _ScopeKey(NamedTuple):
    workspace: str
    project: str

    @classmethod
    def of(cls, scope: EpisodeScope) -> "_ScopeKey":
        return cls(str(scope.workspace_id), str(scope.project_id) if scope.project_id is not None else "")


def _file_mode(info: os.stat_result) -> int:
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
        raise OSError("unsafe SQLite file")
    return stat.S_IMODE(info.st_mode)


def _secure_file(path: Path, *, before_connect: bool, missing_ok: bool = False) -> None:
    try:
        if _file_mode(path.lstat()) == 0o600:
            return
        if before_connect:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                if _file_mode(os.fstat(fd)) != 0o600:
                    os.fchmod(fd, 0o600)
            finally:
                os.close(fd)
        elif os.chmod in os.supports_follow_symlinks:
            os.chmod(path, 0o600, follow_symlinks=False)
        else:
            # The owner-only directory and validated entry permit path chmod without opening another fd.
            os.chmod(path, 0o600)
    except FileNotFoundError:
        if not missing_ok:
            raise


def _prepare_db(path: Path, *, create: bool) -> None:
    if create:
        with suppress(FileExistsError):
            path.touch(mode=0o600, exist_ok=False)
    _secure_file(path, before_connect=True)


def _create_tables(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL, project_id TEXT NOT NULL, session_id TEXT NOT NULL,
            kind TEXT NOT NULL, body TEXT NOT NULL, expires_at REAL NOT NULL,
            UNIQUE (workspace_id, project_id, session_id, kind, body)
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS episodes_expiry ON episodes (expires_at)")
    db.execute("CREATE INDEX IF NOT EXISTS episodes_scope ON episodes (workspace_id, project_id, id DESC)")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS health_probe_limits (
            workspace_id TEXT NOT NULL, project_id TEXT NOT NULL, next_at REAL NOT NULL,
            PRIMARY KEY (workspace_id, project_id)
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS health_probe_expiry ON health_probe_limits (next_at)")
    db.execute("CREATE TABLE IF NOT EXISTS private_consumption (session_id TEXT PRIMARY KEY)")


def _prune(db: sqlite3.Connection, now: float) -> int:
    db.execute("DELETE FROM health_probe_limits WHERE next_at <= ?", (now,))
    return db.execute("DELETE FROM episodes WHERE expires_at <= ?", (now,)).rowcount


def _mark_consumed(db: sqlite3.Connection, session_id: UUID) -> None:
    # This receipt must outlive episode TTLs and process restarts.
    db.execute("INSERT OR IGNORE INTO private_consumption (session_id) VALUES (?)", (str(session_id),))


class LocalSqliteMemoryStore(LocalEpisodicMemory):
    def __init__(self, path: Path, clock: Clock) -> None:
        self._path = path
        self._clock = clock

    def _secure_sidecars(self, *, before_connect: bool = False) -> None:
        for suffix in ("-wal", "-shm", "-journal"):
            _secure_file(
                self._path.with_name(self._path.name + suffix), before_connect=before_connect, missing_ok=True
            )

    @contextmanager
    def _transaction(self, *, create: bool = True) -> Generator[sqlite3.Connection]:
        try:
            with _CONNECTION_LOCK:
                directory = self._path.parent
                if create:
                    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                info = directory.lstat()
                if (
                    not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o700
                ):
                    raise OSError("unsafe SQLite directory")
                _prepare_db(self._path, create=create)
                self._secure_sidecars(before_connect=True)
                uri = self._path.absolute().as_uri() + "?mode=rw"
                with closing(sqlite3.connect(uri, uri=True, isolation_level=None)) as db:
                    if db.execute("PRAGMA journal_mode = WAL").fetchone() != ("wal",):
                        raise sqlite3.OperationalError("WAL unavailable")
                    db.execute("PRAGMA synchronous = FULL")
                    db.execute("PRAGMA secure_delete = ON")
                    db.execute("PRAGMA temp_store = MEMORY")
                    with db:
                        db.execute("BEGIN IMMEDIATE")
                        self._secure_sidecars()
                        if create:
                            _create_tables(db)
                        yield db
                    # The transaction committed. Check sidecars before SQLite can remove them on close.
                    self._secure_sidecars()
        except (OSError, sqlite3.Error):
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE, "Local episodic memory is unavailable"
            ) from None

    @override
    def record(
        self,
        scope: EpisodeScope,
        session_id: UUID,
        kind: MemoryKind,
        text: str,
        *,
        ttl_seconds: int | None = None,
    ) -> EpisodeRecordStatus:
        text = text.strip()
        if not text or len(text) > _TEXT_LIMIT or "\x00" in text:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid local episode text")
        ttl = _DEFAULT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        if not 1 <= ttl <= _MAX_TTL_SECONDS:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid local episode TTL")
        health = kind is MemoryKind.HEALTH_PROBE
        if health:
            ttl = min(ttl, _HEALTH_TTL_SECONDS)
        key = _ScopeKey.of(scope)
        values = (*key, str(session_id), kind.value, text)
        with self._transaction() as db:
            now = self._clock.now().timestamp()
            _prune(db, now)
            duplicate = db.execute(
                "SELECT 1 FROM episodes WHERE workspace_id = ? AND project_id = ?"
                " AND session_id = ? AND kind = ? AND body = ?",
                values,
            ).fetchone()
            if duplicate is not None:
                return "deduplicated"
            if health and not self._admit_probe(db, key, now):
                return "rate_limited"
            db.execute(
                "INSERT INTO episodes (workspace_id, project_id, session_id, kind, body, expires_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (*values, now + ttl),
            )
            if health:
                db.execute(
                    "DELETE FROM episodes WHERE id IN ("
                    " SELECT id FROM episodes WHERE workspace_id = ? AND project_id = ? AND kind = ?"
                    " ORDER BY id DESC LIMIT -1 OFFSET ?)",
                    (*key, MemoryKind.HEALTH_PROBE.value, _HEALTH_CAP),
                )
        return "recorded"

    @staticmethod
    def _admit_probe(db: sqlite3.Connection, key: _ScopeKey, now: float) -> bool:
        return (
            db.execute(
                "INSERT OR IGNORE INTO health_probe_limits (workspace_id, project_id, next_at)"
                " VALUES (?, ?, ?)",
                (*key, now + _HEALTH_INTERVAL_SECONDS),
            ).rowcount
            == 1
        )

    @override
    def search(
        self,
        scope: EpisodeScope,
        session_id: UUID,
        *,
        query: str = "",
        limit: int = 10,
        inherit_workspace: bool = False,
    ) -> tuple[LocalEpisode, ...]:
        if not 1 <= limit <= 20:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid local episode search limit")
        with self._transaction() as db:
            _prune(db, self._clock.now().timestamp())
            rows = cast(
                "list[tuple[int, str, str, str, float]]",
                db.execute(
                    "SELECT id, session_id, kind, body, expires_at FROM episodes WHERE workspace_id = ?"
                    " AND (project_id = ? OR (? AND project_id = '')) AND instr(lower(body), lower(?)) > 0"
                    " ORDER BY id DESC LIMIT ?",
                    (*_ScopeKey.of(scope), inherit_workspace, query, limit),
                ).fetchall(),
            )
            if rows:
                _mark_consumed(db, session_id)
            return tuple(
                LocalEpisode(id_, UUID(source), MemoryKind(kind), body, datetime.fromtimestamp(expires, UTC))
                for id_, source, kind, body, expires in rows
            )

    @override
    def summarize_session(
        self, scope: EpisodeScope, session_id: UUID, *, source_session_id: UUID | None = None
    ) -> str:
        with self._transaction() as db:
            _prune(db, self._clock.now().timestamp())
            rows = cast(
                "list[tuple[str, str]]",
                db.execute(
                    "SELECT kind, body FROM episodes WHERE workspace_id = ? AND project_id = ?"
                    " AND session_id = ? ORDER BY id DESC LIMIT ?",
                    (*_ScopeKey.of(scope), str(source_session_id or session_id), _SUMMARY_COUNT),
                ).fetchall(),
            )
            if rows:
                _mark_consumed(db, session_id)
            lines: list[str] = []
            for kind, body in reversed(rows):
                text = " ".join(body.split())
                excerpt = text if len(text) <= _SUMMARY_WIDTH else text[: _SUMMARY_WIDTH - 1] + "…"
                lines.append(f"- {kind}: {excerpt}")
            return "\n".join(lines)

    @override
    def prune_expired(self) -> int:
        with self._transaction() as db:
            return _prune(db, self._clock.now().timestamp())

    @override
    def require_syncable(self, session_id: UUID) -> None:
        with self._transaction(create=False) as db:
            consumed = db.execute(
                "SELECT 1 FROM private_consumption WHERE session_id = ?", (str(session_id),)
            ).fetchone()
            if consumed is not None:
                raise Forbidden(
                    ErrorCode.FORBIDDEN,
                    "Sync refused because this run consumed HOST_PRIVATE episodes",
                    details={"reason": "host_private_consumption"},
                )
