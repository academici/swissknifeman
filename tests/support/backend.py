"""``TestBackend`` and the ``backend`` fixture: one contract suite over memory and PostgreSQL (testing §4).

Both backends get the same collaborators: the demo module's schemas and subscriptions, a ``FrozenClock``,
deterministic thread-safe ids and the seed of ``support.seed`` (the instance scope and two workspaces). The
memory backend is new for every test. The PostgreSQL backend runs ``PostgresUowFactory`` over a small pool on
the session database of ``support.pg``, cleaned before the test: rows one test commits never reach the next.
Persisted state is observed from outside the units of work: the committed memory state, or a separate
autocommit connection, so "nothing written" means nothing another session can see.

A module that uses these fixtures imports ``backend`` (or ``pg_backend``) together with ``pg_session``,
``test_database`` and ``clean_test_database``; pytest finds fixtures by the names a test module or conftest
holds. ``pg_backend`` is the PostgreSQL-only variant for FK/CHECK/trigger and real-concurrency cases
(adapters §2.2 ``pg_only``); its tests carry the ``pg`` marker themselves.
"""

import itertools
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar, Final, Literal, Protocol, cast, override
from uuid import UUID

import httpx
import psycopg
import pytest

from fakes.app import FakeConfigStore, request_id
from fakes.clock import FrozenClock
from fakes.demo_module import MANIFEST, PERMISSIONS, SCHEMA_ROOT
from fakes.ids import SequentialIds
from integration.artifacts.test_upload_flow import OWNER_ID, dispatch_new, seed_principals
from skm.adapters.memory.core import REPOSITORIES as MEMORY_CORE
from skm.adapters.memory.core.audit import MemoryAuditLog
from skm.adapters.memory.core.state import NIL_UUID
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.postgres.connection import PgSettings
from skm.adapters.postgres.core.audit import PostgresAuditLog
from skm.adapters.postgres.core.events_store import PostgresEventReader, PostgresEventWriter
from skm.adapters.postgres.core.idempotency import PostgresIdempotencyStore
from skm.adapters.postgres.pool import PoolHandle, create_pool
from skm.adapters.postgres.uow import PostgresUnitOfWork, PostgresUowFactory
from skm.application_bus.client import SkmClient
from skm.application_bus.ports import AuditLog, AuditRecord, IdempotencyStore
from skm.application_bus.registry import BusRegistry
from skm.bootstrap.adapters import postgres_repository_table
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.bootstrap.composition_resources import TokenPepper, token_authenticator
from skm.entrypoints.api import request_context
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, NotFound
from skm.kernel.events import EventEnvelope
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import EventId, PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access import public as access
from skm.modules.workspace import public as workspace
from skm.platform.config.store import ConfigStore
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.system_clock import SystemClock
from support import pg
from support.app import BackendTestApp, TestApp
from support.client_transport import api_bootstrap, bearer_embedded_client, client_api, http_client
from support.fault_injection import FaultPlan, FaultPoint, FaultyClient, InjectedFault, faulty_uow_factory
from support.http_server import loopback_server
from support.seed import SEED, Seed, seed_backend

__all__ = [
    "MEMORY_CORE_TABLES",
    "ClientBackend",
    "LockedIds",
    "MemoryTestBackend",
    "OutboxRow",
    "PostgresTestBackend",
    "TestBackend",
    "backend",
    "client_backend",
    "pg_backend",
]

# The tables of skm_core that the memory state models; ``table_counts("skm_core")`` has exactly these keys on
# both backends (the migration history is not state).
MEMORY_CORE_TABLES: Final = (
    "audit_records",
    "consumer_receipts",
    "domain_events",
    "event_streams",
    "idempotency_receipts",
    "outbox",
    "scopes",
    "workspace_event_counters",
)
_POSTGRES_FACTORIES: Final[Mapping[type, Callable[[psycopg.Connection], object]]] = MappingProxyType(
    {
        **cast("Mapping[type, Callable[[psycopg.Connection], object]]", postgres_repository_table(())),
        IdempotencyStore: PostgresIdempotencyStore,
        AuditLog: PostgresAuditLog,
        ConfigStore: lambda conn: FakeConfigStore(),
    }
)
_WORKSPACE_ROW: Final = (
    "INSERT INTO skm_workspace.workspaces (id, slug, title, created_at, updated_at) "
    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING"
)
_OUTBOX: Final = "SELECT id, event_id, destination, state, attempts FROM skm_core.outbox ORDER BY id"
_EVENT_IDS: Final = (
    "SELECT id FROM skm_core.domain_events WHERE %(w)s::uuid IS NULL OR workspace_id = %(w)s ORDER BY id"
)


class TestBackend(Protocol):
    __test__: ClassVar[bool] = False
    kind: Literal["memory", "postgres"]
    clock: FrozenClock
    ids: SequentialIds
    seed: Seed
    schemas: SchemaRegistry
    registry: BusRegistry

    @property
    def uow_factory(self) -> UnitOfWorkFactory: ...

    def meta(
        self, key: str | None = None, *, correlation_id: str | None = None, causation_id: str | None = None
    ) -> RequestMeta: ...

    def uow(
        self, *, readonly: bool = False, seed_workspace: WorkspaceId | None = None
    ) -> AbstractContextManager[UnitOfWork]: ...

    def app(
        self,
        *,
        actor_role: str = "owner",
        uow_factory: UnitOfWorkFactory | None = None,
        registry: BusRegistry | None = None,
    ) -> TestApp: ...

    def table_counts(self, schema: str) -> Mapping[str, int]: ...

    def envelopes(self, *, workspace_id: WorkspaceId | None = None) -> list[EventEnvelope]: ...

    def outbox_rows(self) -> list["OutboxRow"]: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class OutboxRow:
    """A committed ``skm_core.outbox`` row as both backends report it."""

    id: UUID
    event_id: EventId
    destination: str
    state: str
    attempts: int


class LockedIds(SequentialIds):
    """Deterministic ids that concurrent units of work of one test may share."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()

    @override
    def new_id(self) -> UUID:
        with self._lock:
            return super().new_id()


class _Backend:
    """What both backends share: collaborators, request metadata, seeded workspaces and the bus app."""

    __test__: ClassVar[bool] = False
    kind: Literal["memory", "postgres"]
    uow_factory: UnitOfWorkFactory

    def __init__(self) -> None:
        self.clock = FrozenClock()
        self.ids: SequentialIds = LockedIds()
        self.seed: Seed = SEED
        self.schemas = SchemaRegistry.load(SCHEMA_ROOT)
        self.registry = BusRegistry.build(
            (MANIFEST,), schemas=self.schemas, permission_catalog=PERMISSIONS, disabled_modules=frozenset()
        )
        self._requests = itertools.count(1)

    def meta(
        self, key: str | None = None, *, correlation_id: str | None = None, causation_id: str | None = None
    ) -> RequestMeta:
        return RequestMeta(
            request_id(next(self._requests)),
            Surface.TEST,
            key,
            self.clock.now(),
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    @contextmanager
    def uow(
        self, *, readonly: bool = False, seed_workspace: WorkspaceId | None = None
    ) -> Iterator[UnitOfWork]:
        """A unit of work of this backend; ``seed_workspace`` is committed before it opens."""
        if seed_workspace is not None:
            self.ensure_workspace(seed_workspace)
        with self.uow_factory(self.meta(), readonly=readonly) as uow:
            yield uow

    def ensure_workspace(self, workspace_id: WorkspaceId) -> None:
        """The workspace scope under the seeded instance (and its row where the backend has the table)."""
        with self.uow_factory(self.meta()) as uow:
            registry = uow.repo(ScopeRegistry)
            try:
                existing = registry.get(ScopeId(workspace_id))
            except NotFound:
                registry.create(
                    ScopeId(workspace_id),
                    ScopeKind.WORKSPACE,
                    parent=self.seed.instance_id,
                    workspace_id=workspace_id,
                )
            else:
                if existing.kind is not ScopeKind.WORKSPACE:
                    raise ValueError(f"scope {workspace_id} exists as a {existing.kind.value}")
            self._workspace_row(uow, workspace_id)
            uow.commit()

    def _workspace_row(self, uow: UnitOfWork, workspace_id: WorkspaceId) -> None:
        """Memory has no workspace state before the workspace adapters."""

    def app(
        self,
        *,
        actor_role: str = "owner",
        uow_factory: UnitOfWorkFactory | None = None,
        registry: BusRegistry | None = None,
    ) -> TestApp:
        """The real bus over this backend.

        ``uow_factory`` replaces the factory (fault wrappers, testing spec §8); ``registry`` replaces the demo
        registry, e.g. with a handler that fails on purpose. Its events and subscribers must stay those of the
        demo module: the backend's outbox fan-out was built from them.
        """
        if registry is not None and registry.subscription_index() != self.registry.subscription_index():
            raise ValueError("a replaced registry must keep the subscriptions of the backend")
        return BackendTestApp(
            self,
            actor_role=actor_role,
            uow_factory=uow_factory or self.uow_factory,
            registry=registry or self.registry,
        )

    def table_counts(self, schema: str) -> Mapping[str, int]:
        """Committed row counts of ``schema``'s tables, seen from outside every unit of work."""
        raise NotImplementedError

    def envelopes(self, *, workspace_id: WorkspaceId | None = None) -> list[EventEnvelope]:
        """Committed events, oldest first, optionally of one workspace."""
        raise NotImplementedError

    def outbox_rows(self) -> list[OutboxRow]:
        """Committed outbox rows in insertion order."""
        raise NotImplementedError

    def close(self) -> None:
        """Release what the backend holds."""


class MemoryTestBackend(_Backend):
    kind: Literal["memory", "postgres"] = "memory"

    def __init__(self) -> None:
        super().__init__()
        factories: dict[type, Any] = {**MEMORY_CORE, ConfigStore: lambda state: FakeConfigStore()}
        self.memory = InMemoryBackend(
            factories=factories,
            schemas=self.schemas,
            subscriptions=self.registry.subscription_index(),
            ids=self.ids,
            clock=self.clock,
        )
        self.uow_factory = self.memory.uow_factory()
        seed_backend(self.uow_factory)

    @override
    def table_counts(self, schema: str) -> Mapping[str, int]:
        if schema != "skm_core":
            raise ValueError(f"the memory backend models skm_core only, not {schema!r}")
        core = self.memory.committed.core
        counts = {
            "audit_records": len(core.audit),
            "consumer_receipts": len(core.consumer_receipts),
            "domain_events": len(core.events),
            "event_streams": len(core.stream_seq) + (NIL_UUID in core.feed_seq),
            "idempotency_receipts": len(core.idempotency),
            "outbox": len(core.outbox),
            "scopes": len(core.scopes),
            "workspace_event_counters": sum(1 for feed in core.feed_seq if feed != NIL_UUID),
        }
        return MappingProxyType(counts)

    @override
    def envelopes(self, *, workspace_id: WorkspaceId | None = None) -> list[EventEnvelope]:
        events = self.memory.committed.core.events
        return [event for event in events if workspace_id is None or event.workspace_id == workspace_id]

    @override
    def outbox_rows(self) -> list[OutboxRow]:
        rows = sorted(self.memory.committed.core.outbox.values(), key=lambda row: row.id)
        return [
            OutboxRow(row.id, row.event_id, row.destination, row.state.value, row.attempts) for row in rows
        ]


class PostgresTestBackend(_Backend):
    kind: Literal["memory", "postgres"] = "postgres"

    def __init__(self, database: pg.TestDatabase, *, pool_max_size: int = 4) -> None:
        super().__init__()
        self.database = database
        self.pool: PoolHandle = create_pool(
            PgSettings(
                dsn=database.dsn,
                application_name="skm-test",
                pool_min_size=1,
                pool_max_size=pool_max_size,
                pool_timeout_seconds=5,
            )
        )
        try:
            writer = PostgresEventWriter(
                schemas=self.schemas, subscriptions=self.registry.subscription_index(), ids=self.ids
            )
            self.uow_factory = PostgresUowFactory(self.pool, _POSTGRES_FACTORIES, writer, self.clock)
            self.observer = psycopg.connect(database.dsn, autocommit=True, connect_timeout=5)
        except BaseException:
            self.pool.close()
            raise

    @override
    def _workspace_row(self, uow: UnitOfWork, workspace_id: WorkspaceId) -> None:
        now = self.clock.now()
        connection = cast("PostgresUnitOfWork", uow).connection
        connection.execute(
            _WORKSPACE_ROW, (workspace_id, f"ws-{workspace_id.hex}", "Test workspace", now, now)
        )

    @override
    def table_counts(self, schema: str) -> Mapping[str, int]:
        return pg.table_counts(self.observer, schema)

    @override
    def envelopes(self, *, workspace_id: WorkspaceId | None = None) -> list[EventEnvelope]:
        rows = self.observer.execute(_EVENT_IDS, {"w": workspace_id}).fetchall()
        return list(PostgresEventReader(self.observer).by_ids([EventId(row[0]) for row in rows]))

    @override
    def outbox_rows(self) -> list[OutboxRow]:
        rows = self.observer.execute(_OUTBOX).fetchall()
        return [OutboxRow(row[0], EventId(row[1]), row[2], row[3], row[4]) for row in rows]

    def execute(self, statement: str, params: object = None) -> list[tuple[Any, ...]]:
        """Committed-state SQL through the observer connection (PostgreSQL-only assertions)."""
        cursor = self.observer.execute(cast("Any", statement), cast("Any", params))
        return cursor.fetchall() if cursor.description is not None else []

    @override
    def close(self) -> None:
        try:
            self.observer.close()
        finally:
            self.pool.close()


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def backend(request: pytest.FixtureRequest) -> Iterator[TestBackend]:
    """Memory, then PostgreSQL (``pg``: skipped without a test DSN, a failure under ``SKM_REQUIRE_PG=1``)."""
    made: MemoryTestBackend | PostgresTestBackend
    if request.param == "memory":
        made = MemoryTestBackend()
    else:
        made = PostgresTestBackend(request.getfixturevalue("clean_test_database"))
    try:
        yield made
    finally:
        made.close()


@pytest.fixture
def pg_backend(clean_test_database: pg.TestDatabase) -> Iterator[PostgresTestBackend]:
    """The PostgreSQL backend alone, for cases memory does not model; the test is marked ``pg``."""
    made = PostgresTestBackend(clean_test_database, pool_max_size=8)
    try:
        yield made
    finally:
        made.close()


type ClientKind = Literal["embedded-memory", "embedded-pg", "http-pg"]
_CLIENT_PEPPER = b"client-contracts fixed test pepper"


@dataclass(frozen=True)
class ClientSeed:
    workspace_id: WorkspaceId
    project_id: ProjectId
    other_workspace_id: WorkspaceId
    principals: Mapping[str, PrincipalId]
    tokens: Mapping[str, access.CreateTokenResult]
    instance_id: ScopeId = SEED.instance_id


@dataclass
class ClientBackend:
    kind: ClientKind
    seed: ClientSeed
    clock: FrozenClock
    app: App
    root: Path
    dsn: str | None
    _stack: ExitStack
    endpoint: str | None = None

    def client(
        self,
        role: str = "owner",
        *,
        token: str | None = None,
        on_response: Callable[[httpx.Response], None] | None = None,
    ) -> SkmClient:
        secret = self.seed.tokens[role].secret if token is None else token
        if self.endpoint is None:
            return bearer_embedded_client(self.app, secret)
        return http_client(self._stack, self.endpoint, self.root, secret, self.clock, on_response)

    def revoke(self, role: str) -> None:
        """Revoke the bearer in the shared control plane before exercising caller replay."""
        self.client().dispatch(access.RevokeToken(self.seed.tokens[role].token_id))

    @contextmanager
    def lose_response(self, client: SkmClient) -> Iterator[SkmClient]:
        """Fail once after a real commit, leaving the caller in control of the retry."""
        if self.kind == "http-pg":
            point = FaultPoint.CLIENT_AFTER_SERVER_COMMIT
            with pytest.raises(InjectedFault) as caught:
                yield cast("SkmClient", FaultyClient(client, FaultPlan({point: 1})))
            assert caught.value.point is point
        else:
            point = FaultPoint.UOW_AFTER_COMMIT
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(
                    self.app.bus,
                    "_uow_factory",
                    faulty_uow_factory(self.app.uow_factory, FaultPlan({point: 1})),
                )
                with pytest.raises(InternalError) as caught:
                    yield client
                assert caught.value.code is ErrorCode.INTERNAL_ERROR
                assert isinstance(caught.value.__cause__, InjectedFault)
                assert caught.value.__cause__.point is point

    @contextmanager
    def uow(self, *, readonly: bool = True) -> Iterator[UnitOfWork]:
        with self.app.uow_factory(
            RequestMeta("client-contract-observer", Surface.TEST, None, self.clock.now()), readonly=readonly
        ) as uow:
            yield uow

    def audit_records(self, action: str) -> list[AuditRecord]:
        with self.uow() as uow:
            if self.dsn is None:
                log = cast("MemoryAuditLog", uow.repo(AuditLog))
                return [row for row in log._core.audit if row.action == action]
            with psycopg.connect(self.dsn, autocommit=True, connect_timeout=5) as conn:
                rows = conn.execute(
                    "SELECT id, workspace_id, actor_id, action, target, decision, reason_code, request_id, "
                    "recorded_at FROM skm_core.audit_records WHERE action = %s ORDER BY id",
                    (action,),
                )
                return [AuditRecord(*row) for row in rows]


def _seed_clients(app: App, storage: str) -> ClientSeed:
    principals = {
        "owner": OWNER_ID,
        **{
            name: PrincipalId(UUID(int=OWNER_ID.int + offset))
            for offset, name in enumerate(("editor", "other-editor", "viewer", "foreign"), start=1)
        },
    }
    actor = seed_principals(
        app,
        storage,
        people=(
            (SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system"),
            *((pid, PrincipalKind.HUMAN, name) for name, pid in principals.items()),
        ),
        roles=(
            (SEED.instance_id, OWNER_ID, access.Role.OWNER),
            (SEED.instance_id, SYSTEM_PRINCIPAL_ID, access.Role.OWNER),
        ),
    )
    bootstrap_owner = app.client(actor=actor, surface=Surface.CLI)
    owner_token = cast("access.CreateTokenResult", bootstrap_owner.dispatch(access.CreateToken("owner")))
    owner = app.client(actor=app.authenticate(owner_token.secret), surface=Surface.API)
    main = dispatch_new(owner, workspace.CreateWorkspace("main", "Main"))
    foreign = dispatch_new(owner, workspace.CreateWorkspace("foreign", "Foreign"))
    project = dispatch_new(owner, workspace.CreateProject(main.workspace_id, "sample", "Sample"))
    tokens = {"owner": owner_token}
    for name, scope, role in (
        ("editor", main.workspace_id, "maintainer"),
        ("other-editor", main.workspace_id, "maintainer"),
        ("viewer", main.workspace_id, "viewer"),
        ("foreign", foreign.workspace_id, "maintainer"),
    ):
        owner.dispatch(
            access.GrantMembership.from_json(
                {
                    "scope_id": str(scope),
                    "principal_id": str(principals[name]),
                    "role": role,
                }
            )
        )
        token = owner.dispatch(access.CreateToken(name, principal_id=principals[name], scope_id=scope))
        tokens[name] = cast("access.CreateTokenResult", token)
    return ClientSeed(
        WorkspaceId(main.workspace_id),
        ProjectId(project.project_id),
        WorkspaceId(foreign.workspace_id),
        principals,
        tokens,
    )


@pytest.fixture(
    params=[
        "embedded-memory",
        pytest.param("embedded-pg", marks=pytest.mark.pg),
        pytest.param("http-pg", marks=[pytest.mark.pg, pytest.mark.slow]),
    ]
)
def client_backend(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ClientBackend]:
    from contracts.execution._client_execution import runtime_gateways

    kind = cast("ClientKind", request.param)
    storage = "memory" if kind == "embedded-memory" else "postgres"
    database = (
        None
        if storage == "memory"
        else cast("pg.TestDatabase", request.getfixturevalue("clean_test_database"))
    )
    dsn = database.dsn if database else None
    clock, ids = FrozenClock(SystemClock().now()), LockedIds()
    boot = api_bootstrap(tmp_path, dsn)
    with ExitStack() as stack:
        app = build_app(
            boot,
            surface=Surface.API,
            environ={},
            invocation={},
            backend=storage,
            overrides=CompositionOverrides(
                access.RbacAuthorizer(clock),
                StoredScopeChain(),
                clock=clock,
                ids=ids,
                gateways=GatewayTable(
                    {**runtime_gateways(tmp_path), access.TokenPepperSource: TokenPepper(_CLIENT_PEPPER)},
                    "control_plane_gateway",
                ),
            ),
        )
        stack.callback(app.close)
        app = replace(
            app, authenticator=token_authenticator(app.uow_factory, _CLIENT_PEPPER, Surface.API, ids, clock)
        )
        side = ClientBackend(kind, _seed_clients(app, storage), clock, app, tmp_path, dsn, stack)
        if kind == "http-pg":
            monkeypatch.setattr(request_context, "_CLOCK", clock)
            side.endpoint = stack.enter_context(loopback_server(lambda address: client_api(app, address)))
        yield side
