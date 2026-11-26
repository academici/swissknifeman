"""Host SQLite file safety, expiration, deduplication and scope isolation."""

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from stat import S_IMODE
from types import TracebackType
from typing import Literal, override
from uuid import uuid4

import pytest

from fakes.clock import FrozenClock
from skm.adapters.knowledge.local_sqlite_memory import LocalSqliteMemoryStore
from skm.kernel.data_classification import HOST_PRIVATE
from skm.kernel.errors import BackendUnavailable, Forbidden
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.modules.knowledge.ports import EpisodeScope
from skm.modules.knowledge.public import MemoryKind


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "private" / "episodes.sqlite3"


@pytest.fixture
def scope() -> EpisodeScope:
    return EpisodeScope(WorkspaceId(uuid4()), ProjectId(uuid4()))


def test_private_wal_expiry_and_durable_consumption(path: Path, scope: EpisodeScope) -> None:
    clock = FrozenClock()
    store = LocalSqliteMemoryStore(path, clock)
    session = uuid4()
    assert store.record(scope, session, MemoryKind.FACT, "private fact", ttl_seconds=12) == "recorded"
    store.require_syncable(session)
    assert S_IMODE(path.parent.stat().st_mode) == 0o700
    with closing(sqlite3.connect(path)) as reader:
        assert reader.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        (episode,) = store.search(scope, session)
        assert episode.classification == HOST_PRIVATE
        assert episode.expires_at == clock.now() + timedelta(seconds=12)
        assert "private fact" not in repr(episode)
        for file in (path, path.with_suffix(".sqlite3-wal"), path.with_suffix(".sqlite3-shm")):
            assert S_IMODE(file.stat().st_mode) == 0o600
        clock.advance(timedelta(seconds=12))
        assert store.prune_expired() == 1
        assert reader.execute("SELECT count(*) FROM episodes").fetchone() == (0,)
        assert store.search(scope, uuid4()) == ()
    with pytest.raises(Forbidden, match="consumed HOST_PRIVATE"):
        LocalSqliteMemoryStore(path, clock).require_syncable(session)


def test_repairs_existing_files_before_connect(
    path: Path, scope: EpisodeScope, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalSqliteMemoryStore(path, FrozenClock())
    assert store.prune_expired() == 0
    files = (path, path.with_suffix(".sqlite3-wal"), path.with_suffix(".sqlite3-shm"))
    for file in files:
        file.touch()
        file.chmod(0o644)

    connect = sqlite3.connect

    def check_permissions(database: str, *, uri: bool, isolation_level: None) -> sqlite3.Connection:
        assert [S_IMODE(file.stat().st_mode) for file in files] == [0o600, 0o600, 0o600]
        return connect(database, uri=uri, isolation_level=isolation_level)

    monkeypatch.setattr(sqlite3, "connect", check_permissions)
    assert store.record(scope, uuid4(), MemoryKind.FACT, "private fact") == "recorded"


def test_repairs_sidecars_after_commit_without_nofollow_chmod(
    path: Path, scope: EpisodeScope, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecars = (path.with_suffix(".sqlite3-wal"), path.with_suffix(".sqlite3-shm"))
    chmod = os.chmod

    def chmod_without_nofollow(file: Path, mode: int, *, follow_symlinks: bool = True) -> None:
        if not follow_symlinks:
            raise NotImplementedError("chmod does not support follow_symlinks=False")
        chmod(file, mode)

    monkeypatch.setattr(os, "supports_follow_symlinks", os.supports_follow_symlinks - {chmod})
    monkeypatch.setattr(os, "chmod", chmod_without_nofollow)

    class CommitWithPermissiveSidecars(sqlite3.Connection):
        @override
        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            value: BaseException | None,
            traceback: TracebackType | None,
            /,
        ) -> Literal[False]:
            result = super().__exit__(exc_type, value, traceback)
            if exc_type is None:
                assert not self.in_transaction
                for file in sidecars:
                    file.chmod(0o644)
            return result

        @override
        def close(self) -> None:
            try:
                assert [S_IMODE(file.stat().st_mode) for file in sidecars] == [0o600, 0o600]
            finally:
                super().close()

    connect = sqlite3.connect

    def connect_with_permissive_commit(
        database: str, *, uri: bool, isolation_level: None
    ) -> sqlite3.Connection:
        return connect(
            database, factory=CommitWithPermissiveSidecars, uri=uri, isolation_level=isolation_level
        )

    monkeypatch.setattr(sqlite3, "connect", connect_with_permissive_commit)
    store = LocalSqliteMemoryStore(path, FrozenClock())
    assert store.record(scope, uuid4(), MemoryKind.FACT, "private fact") == "recorded"


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm"])
def test_refuses_symlink_without_touching_target(path: Path, scope: EpisodeScope, suffix: str) -> None:
    path.parent.mkdir(mode=0o700)
    target = path.parent.parent / "target"
    target.write_text("unrelated file", encoding="utf-8")
    path.with_name(path.name + suffix).symlink_to(target)
    store = LocalSqliteMemoryStore(path, FrozenClock())
    with pytest.raises(BackendUnavailable, match="Local episodic memory is unavailable"):
        store.record(scope, uuid4(), MemoryKind.CONTEXT, "sensitive data")
    assert target.read_text(encoding="utf-8") == "unrelated file"


def test_deduplication_is_atomic_across_store_connections(path: Path, scope: EpisodeScope) -> None:
    clock = FrozenClock()
    store = LocalSqliteMemoryStore(path, clock)
    session = uuid4()

    def record(_: int) -> str:
        return LocalSqliteMemoryStore(path, clock).record(scope, session, MemoryKind.FACT, " repeat ")

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(record, range(12)))
    assert statuses.count("recorded") == 1
    assert statuses.count("deduplicated") == 11
    (found,) = store.search(scope, session, query="REPEAT")
    assert found.text == "repeat"


def test_health_probes_have_scoped_rate_and_retention_limits(path: Path, scope: EpisodeScope) -> None:
    clock = FrozenClock()
    store = LocalSqliteMemoryStore(path, clock)
    session = uuid4()
    sibling = EpisodeScope(scope.workspace_id, ProjectId(uuid4()))
    health = MemoryKind.HEALTH_PROBE
    assert store.record(scope, session, health, "probe 0") == "recorded"
    assert store.record(scope, session, health, "probe 0") == "deduplicated"
    assert store.record(scope, uuid4(), health, "new") == "rate_limited"
    assert store.record(sibling, session, health, "sibling") == "recorded"
    assert store.record(scope, session, MemoryKind.FACT, "unrelated") == "recorded"
    for index in range(1, 9):
        clock.advance(timedelta(seconds=30))
        assert store.record(scope, session, health, f"probe {index}", ttl_seconds=900) == "recorded"
    episodes = store.search(scope, session)
    assert len(episodes) == 9
    assert "probe 0" not in {episode.text for episode in episodes}
    assert "unrelated" in {episode.text for episode in episodes}
    assert episodes[0].expires_at == clock.now() + timedelta(seconds=300)


def test_scope_inheritance_and_compact_summaries(path: Path, scope: EpisodeScope) -> None:
    store = LocalSqliteMemoryStore(path, FrozenClock())
    session, consumer = uuid4(), uuid4()
    sibling = EpisodeScope(scope.workspace_id, ProjectId(uuid4()))
    workspace = EpisodeScope(scope.workspace_id, None)
    foreign = EpisodeScope(WorkspaceId(uuid4()), None)
    for target, value in ((sibling, "sibling"), (workspace, "inherited"), (foreign, "foreign")):
        store.record(target, session, MemoryKind.CONTEXT, value)
    assert store.search(scope, consumer) == ()
    assert store.summarize_session(scope, consumer, source_session_id=session) == ""
    store.require_syncable(consumer)
    (inherited,) = store.search(scope, consumer, inherit_workspace=True)
    assert inherited.text == "inherited"
    for index in range(9):
        store.record(scope, session, MemoryKind.FACT, f"entry {index} \n" + "x" * 200)
    store.record(scope, uuid4(), MemoryKind.FACT, "another session")
    summarizer = uuid4()
    summary = store.summarize_session(scope, summarizer, source_session_id=session)
    assert len(summary.splitlines()) == 8
    assert summary.startswith("- fact: entry 1 x")
    assert summary.endswith("…")
    assert all(item not in summary for item in ("entry 0", "inherited", "another session"))
    with pytest.raises(Forbidden, match="consumed HOST_PRIVATE"):
        store.require_syncable(summarizer)
