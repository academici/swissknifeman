"""Contracts of the settings module: bus registration and the repository ports (settings §A.6, §A.11).

``backend`` runs every repository contract on the memory and the PostgreSQL adapters. The repositories
write conditionally on the version read (``VERSION_CONFLICT``), keep the rows the resolver reads in step with
the full entries (a divergence fails closed), page by their keysets and leave nothing behind on rollback.
"""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest

from fakes.clock import FrozenClock
from fakes.ids import SequentialIds
from skm.adapters.memory.config_store import MemoryConfigStore, write_config_entry
from skm.adapters.memory.core import REPOSITORIES as CORE_REPOSITORIES
from skm.adapters.memory.settings import REPOSITORIES as SETTINGS_REPOSITORIES
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.postgres.config_store import PostgresConfigStore
from skm.adapters.postgres.connection import PgSettings
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.pool import create_pool
from skm.adapters.postgres.uow import PostgresUowFactory
from skm.application_bus.registry import BusRegistry
from skm.bootstrap.adapters import postgres_repository_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, SkmError
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.access.permissions import PERMISSIONS as CATALOG
from skm.modules.settings.domain.entry import ConfigEntryId, EntryOp, change_entry, new_entry, set_lock
from skm.modules.settings.domain.history import ChangeKind, history_record
from skm.modules.settings.module import MODULE
from skm.modules.settings.ports import ConfigEntryRepository, ConfigGenerationCounter, ConfigHistoryRepository
from skm.platform.config.store import ConfigStore, StoredContribution
from skm.platform.schema.registry import SchemaRegistry
from support import pg
from support.backend import LockedIds
from support.pg import clean_test_database, pg_session, test_database  # noqa: F401 - fixtures by name
from support.seed import SEED

# The instance and workspace are the rows a clean test database is seeded with.
INSTANCE = SEED.instance_id
WORKSPACE = ScopeId(SEED.workspace_id)
PROJECT = ScopeId(UUID("01900000-0000-7000-8000-0000000000c1"))
PLAN = ScopeId(UUID("01900000-0000-7000-8000-0000000000d1"))
ACTOR = PrincipalId(UUID(int=7))
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
KINDS = {
    INSTANCE: ScopeKind.INSTANCE,
    WORKSPACE: ScopeKind.WORKSPACE,
    PROJECT: ScopeKind.PROJECT,
    PLAN: ScopeKind.PLAN,
}


@cache
def schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def _meta() -> RequestMeta:
    return RequestMeta("req_" + "0" * 26, Surface.TEST, None, NOW)


class Backend:
    """One backend with the scope tree instance → workspace → project → plan."""

    def __init__(
        self,
        uow_factory: Callable[..., Any],
        *,
        seeded: bool = False,
        close: Callable[[], None] = lambda: None,
    ) -> None:
        self.uow_factory = uow_factory
        self.close = close
        with self.uow() as uow:
            scopes = uow.repo(ScopeRegistry)
            ws = WorkspaceId(WORKSPACE)
            if not seeded:
                scopes.create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
                scopes.create(WORKSPACE, ScopeKind.WORKSPACE, parent=INSTANCE, workspace_id=ws)
            scopes.create(PROJECT, ScopeKind.PROJECT, parent=WORKSPACE, workspace_id=ws)
            scopes.create(PLAN, ScopeKind.PLAN, parent=PROJECT, workspace_id=ws)
            uow.commit()

    @contextmanager
    def uow(self, *, readonly: bool = False) -> Iterator[Any]:
        with self.uow_factory(_meta(), readonly=readonly) as uow:
            yield uow


def memory_backend() -> Backend:
    backend = InMemoryBackend(
        factories={**CORE_REPOSITORIES, **SETTINGS_REPOSITORIES, ConfigStore: MemoryConfigStore},
        schemas=schemas(),
        subscriptions={},
        ids=SequentialIds(),
        clock=FrozenClock(),
    )
    return Backend(backend.uow_factory())


type _PgFactories = Mapping[type, Callable[[psycopg.Connection], object]]


def postgres_backend(database: pg.TestDatabase) -> Backend:
    ids = LockedIds()
    registry = BusRegistry.build(
        (MODULE,), schemas=schemas(), permission_catalog=frozenset(CATALOG), disabled_modules=frozenset()
    )
    writer = PostgresEventWriter(schemas=schemas(), subscriptions=registry.subscription_index(), ids=ids)
    pool = create_pool(
        PgSettings(
            dsn=database.dsn,
            application_name="skm-test",
            pool_min_size=1,
            pool_max_size=4,
            pool_timeout_seconds=5,
        )
    )
    factories: dict[type, Callable[[psycopg.Connection], object]] = {
        **cast(
            "Mapping[type, Callable[[psycopg.Connection], object]]", postgres_repository_table(("settings",))
        ),
        ConfigStore: PostgresConfigStore,
    }
    try:
        return Backend(
            PostgresUowFactory(pool, factories, writer, FrozenClock()), seeded=True, close=pool.close
        )
    except BaseException:
        pool.close()
        raise


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def backend(request: pytest.FixtureRequest) -> Iterator[Backend]:
    made = (
        memory_backend()
        if request.param == "memory"
        else postgres_backend(request.getfixturevalue("clean_test_database"))
    )
    try:
        yield made
    finally:
        made.close()


def entry(scope_id: ScopeId, key: str = "execution.review.max_rounds", value: Any = 1, *, n: int = 1) -> Any:
    return new_entry(
        entry_id=ConfigEntryId(UUID(int=n)),
        scope=ScopeRef(KINDS[scope_id], scope_id),
        key=key,
        op=EntryOp.SET,
        value=value,
        locked=False,
        reason="",
        actor=ACTOR,
        now=NOW,
    )


# ---------------------------------------------------------------------------------------------------------
# bus registration


def test_settings_operations_and_events_register_on_the_bus() -> None:
    registry = BusRegistry.build(
        (MODULE,),
        schemas=schemas(),
        permission_catalog=frozenset(CATALOG),
        disabled_modules=frozenset(),
    )
    described = registry.describe()
    assert described["commands"] == [
        "settings.import_config",
        "settings.lock_value",
        "settings.remove_value",
        "settings.set_value",
        "settings.unlock_value",
        "settings.unset_value",
    ]
    assert described["queries"] == [
        "settings.explain_config",
        "settings.export_config",
        "settings.get_generation",
        "settings.get_history",
        "settings.get_host_config",
        "settings.get_schema",
        "settings.get_value",
        "settings.list_entries",
    ]
    assert set(cast("list[str]", described["event_types"])) == {
        "urn:skm:settings:event:config-changed:v1",
        "urn:skm:settings:event:config-locked:v1",
        "urn:skm:settings:event:config-unlocked:v1",
    }
    assert {spec.permission for spec in MODULE.commands} == {"config.write"}  # type: ignore[attr-defined]
    assert {spec.permission for spec in MODULE.queries} == {"config.read"}  # type: ignore[attr-defined]
    assert all(spec.permissions_of is not None for spec in MODULE.commands)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------------------------------------
# ConfigEntryRepository


def test_add_find_and_entries(backend: Backend) -> None:
    with backend.uow() as uow:
        repo = uow.repo(ConfigEntryRepository)
        repo.add(entry(PROJECT, n=1))
        repo.add(entry(PROJECT, "execution.workflow.profile", "quick-fix", n=2))
        repo.add(entry(WORKSPACE, n=3))
        with pytest.raises(Conflict) as caught:
            repo.add(entry(PROJECT, n=4))
        assert caught.value.code is ErrorCode.ALREADY_EXISTS
        uow.commit()
    with backend.uow(readonly=True) as uow:
        repo = uow.repo(ConfigEntryRepository)
        assert repo.find(PROJECT, "execution.review.max_rounds") == entry(PROJECT, n=1)
        assert repo.find(PLAN, "execution.review.max_rounds") is None
        assert list(repo.entries_of_scope(PROJECT)) == [
            "execution.review.max_rounds",
            "execution.workflow.profile",
        ]
        assert set(repo.entries_for([PROJECT, WORKSPACE, PLAN])) == {PROJECT, WORKSPACE}
        assert repo.get(ConfigEntryId(UUID(int=3))).scope.id == WORKSPACE
        with pytest.raises(NotFound):
            repo.get(ConfigEntryId(UUID(int=99)))
        stored = uow.repo(ConfigStore).entries_for([PROJECT])[PROJECT]["execution.review.max_rounds"]
        assert stored == StoredContribution(UUID(int=1), "execution.review.max_rounds", "set", 1, False, 1)


def test_save_and_remove_are_conditional_on_the_version_read(backend: Backend) -> None:
    first = entry(PROJECT)
    with backend.uow() as uow:
        uow.repo(ConfigEntryRepository).add(first)
        uow.commit()
    changed = change_entry(first, op=EntryOp.SET, value=2, reason="", actor=ACTOR, now=NOW)
    with backend.uow() as uow:
        repo = uow.repo(ConfigEntryRepository)
        with pytest.raises(Conflict) as caught:
            repo.save(changed, expected_version=2)
        assert caught.value.details == {"expected": 2, "actual": 1}
        repo.save(changed, expected_version=1)
        with pytest.raises(Conflict):
            repo.remove(first.id, expected_version=1)
        repo.remove(first.id, expected_version=2)
        with pytest.raises(Conflict) as caught:
            repo.remove(first.id, expected_version=2)
        assert caught.value.details == {"expected": 2, "actual": 0}
        with pytest.raises(Conflict) as caught:
            repo.save(changed, expected_version=1)
        assert caught.value.details == {"expected": 1, "actual": 0}
        uow.commit()
    with backend.uow(readonly=True) as uow:
        assert uow.repo(ConfigEntryRepository).entries_of_scope(PROJECT) == {}
        assert uow.repo(ConfigStore).entries_for([PROJECT]) == {}


def test_a_compound_change_saves_version_plus_two_in_one_update(backend: Backend) -> None:
    first = entry(WORKSPACE)
    with backend.uow() as uow:
        uow.repo(ConfigEntryRepository).add(first)
        uow.commit()
    value = change_entry(first, op=EntryOp.SET, value=3, reason="", actor=ACTOR, now=NOW)
    locked = set_lock(value, locked=True, reason="", actor=ACTOR, now=NOW)
    with backend.uow() as uow:
        uow.repo(ConfigEntryRepository).save(locked, expected_version=1)
        uow.commit()
    with backend.uow(readonly=True) as uow:
        found = uow.repo(ConfigEntryRepository).find(WORKSPACE, first.key)
        assert found is not None
        assert (found.row_version, found.locked, found.value) == (3, True, 3)


def test_rollback_leaves_nothing_behind(backend: Backend) -> None:
    with backend.uow() as uow:
        uow.repo(ConfigEntryRepository).add(entry(PROJECT))
        uow.repo(ConfigGenerationCounter).increment()
        record = history_record(
            record_id=UUID(int=5),
            before=None,
            after=entry(PROJECT),
            kind=ChangeKind.CREATED,
            actor=ACTOR,
            request_id=None,
            reason="",
            generation=1,
            now=NOW,
        )
        uow.repo(ConfigHistoryRepository).append(record)
        assert uow.repo(ConfigStore).pending_writes() is True
    with backend.uow(readonly=True) as uow:
        assert uow.repo(ConfigEntryRepository).entries_of_scope(PROJECT) == {}
        assert uow.repo(ConfigGenerationCounter).current() == 0
        assert (
            uow.repo(ConfigHistoryRepository).list(scope_id=None, key=None, after=None, limit=10).items == ()
        )


def test_rows_out_of_step_with_the_entries_fail_closed() -> None:
    # Memory keeps the resolver rows apart from the full entries; PostgreSQL stores both in one row.
    backend = memory_backend()
    with backend.uow() as uow:
        uow.repo(ConfigEntryRepository).add(entry(PROJECT))
        uow.commit()
    with backend.uow() as uow:
        # A writer that bypasses the settings repositories changes the resolver row only.
        state = uow._working
        write_config_entry(
            state, PROJECT, StoredContribution(UUID(int=1), entry(PROJECT).key, "set", 9, False, 1)
        )
        with pytest.raises(InternalError):
            uow.repo(ConfigEntryRepository).entries_of_scope(PROJECT)


def test_list_keyset_and_count_shadowed_below(backend: Backend) -> None:
    with backend.uow() as uow:
        repo = uow.repo(ConfigEntryRepository)
        for n, (scope_id, key) in enumerate(
            [
                (INSTANCE, "execution.review.max_rounds"),
                (WORKSPACE, "execution.review.max_rounds"),
                (PROJECT, "execution.review.max_rounds"),
                (PLAN, "execution.review.max_rounds"),
                (PROJECT, "execution.workflow.profile"),
            ],
            start=1,
        ):
            repo.add(entry(scope_id, key, 1 if key.endswith("rounds") else "quick-fix", n=n))
        uow.commit()
    with backend.uow(readonly=True) as uow:
        repo = uow.repo(ConfigEntryRepository)
        pages, after = [], None
        while True:
            page = repo.list(scope_id=None, level=None, key_prefix="execution.", after=after, limit=2)
            pages.append([(item.key, str(item.scope.id)) for item in page.items])
            after = page.next
            if after is None:
                break
        flat = [item for page in pages for item in page]
        assert flat == sorted(flat)
        assert len(flat) == 5
        assert [len(page) for page in pages] == [2, 2, 1]
        by_level = repo.list(scope_id=None, level=ScopeKind.PROJECT, key_prefix=None, after=None, limit=10)
        assert {item.key for item in by_level.items} == {
            "execution.review.max_rounds",
            "execution.workflow.profile",
        }
        assert repo.count_shadowed_below(WORKSPACE, "execution.review.max_rounds") == 2
        assert repo.count_shadowed_below(INSTANCE, "execution.review.max_rounds") == 3
        assert repo.count_shadowed_below(PLAN, "execution.review.max_rounds") == 0
        with pytest.raises(SkmError) as caught:
            repo.list(scope_id=None, level=None, key_prefix=None, after="bm90IGEgY3Vyc29y", limit=2)
        assert caught.value.code is ErrorCode.SCHEMA_INVALID


# ---------------------------------------------------------------------------------------------------------
# ConfigHistoryRepository, ConfigGenerationCounter


def test_history_pages_newest_first_and_generation_is_monotonic(backend: Backend) -> None:
    with backend.uow() as uow:
        counter = uow.repo(ConfigGenerationCounter)
        history = uow.repo(ConfigHistoryRepository)
        assert [counter.increment() for _ in range(3)] == [1, 2, 3]
        for n in range(1, 4):
            history.append(
                history_record(
                    record_id=UUID(int=n),
                    before=None,
                    after=entry(PROJECT if n < 3 else WORKSPACE, n=n),
                    kind=ChangeKind.CREATED,
                    actor=ACTOR,
                    request_id=f"req_{n}",
                    reason="",
                    generation=n,
                    now=NOW + timedelta(seconds=n % 2),
                )
            )
        with pytest.raises(Conflict):
            history.append(
                history_record(
                    record_id=UUID(int=1),
                    before=None,
                    after=entry(PROJECT),
                    kind=ChangeKind.CREATED,
                    actor=ACTOR,
                    request_id=None,
                    reason="",
                    generation=1,
                    now=NOW,
                )
            )
        uow.commit()
    with backend.uow(readonly=True) as uow:
        assert uow.repo(ConfigGenerationCounter).current() == 3
        history = uow.repo(ConfigHistoryRepository)
        first = history.list(scope_id=None, key=None, after=None, limit=2)
        rest = history.list(scope_id=None, key=None, after=first.next, limit=2)
        order = [record.id.int for record in (*first.items, *rest.items)]
        assert order == [3, 1, 2]
        assert rest.next is None
        project = history.list(scope_id=PROJECT, key=None, after=None, limit=10)
        assert [record.id.int for record in project.items] == [1, 2]
