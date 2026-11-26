"""Two-backend harness of the workspace contract suite: memory ∥ PostgreSQL (workspace §6, §11, §15).

Each side runs the real bus with the ``access`` and ``workspace`` modules, the production authorizer
(``RbacAuthorizer``) and the repositories of its backend; ids, clock and entropy are deterministic. Both sides
start from the same state: the instance scope and the two seeded workspace scopes of ``support.seed`` (the
PostgreSQL side gets them from ``clean_test_database``). People and workers are seeded as domain values
through the repositories, never through a handler under test.

The PostgreSQL side builds every workspace and access repository with the side's clock, so ``updated_at`` and
the ``added_at`` of remotes follow the test clock as the memory side does.
"""

import itertools
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from runpy import run_path
from typing import Any, cast

import psycopg
import pytest

from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from skm.adapters.memory.access import REPOSITORIES as MEMORY_ACCESS
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core import REPOSITORIES as MEMORY_CORE
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.memory.workspace import REPOSITORIES as MEMORY_WORKSPACE
from skm.adapters.postgres.access.repositories import PostgresPrincipalRepository, PostgresTokenRepository
from skm.adapters.postgres.config_store import PostgresConfigStore
from skm.adapters.postgres.core.audit import PostgresAuditLog
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.core.idempotency import PostgresIdempotencyStore
from skm.adapters.postgres.uow import PostgresUowFactory
from skm.adapters.postgres.workspace import REPOSITORIES as POSTGRES_WORKSPACE
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import AuditLog, Authorizer, IdempotencyStore
from skm.application_bus.registry import BusRegistry
from skm.bootstrap.adapters import postgres_repository_table
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, PrincipalId, ProjectId, RepositoryId, ScopeId, WorkerId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork, UnitOfWorkFactory
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.module import MODULE as ACCESS
from skm.modules.access.ports import (
    MembershipRepository,
    PrincipalRepository,
    TokenPepperSource,
    TokenRepository,
)
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.workspace.domain.worker import Worker, WorkerCapabilities, WorkerState
from skm.modules.workspace.generated.commands import HostArch, HostOs
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.modules.workspace.ports import WorkerRepository
from skm.modules.workspace.public import (
    CreateProject,
    CreateWorkspace,
    RegisterHost,
    RegisterHostDefsHostPlatform,
    RegisterRepository,
)
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource
from support.backend import LockedIds, PostgresTestBackend
from support.pg import TestDatabase, clean_test_database, pg_session, test_database  # noqa: F401
from support.seed import SEED, seed_backend
from support.sides import BACKEND_PARAMS, iter_pg_side, iter_side

h = run_path(str(Path(__file__).parents[2] / "unit" / "workspace" / "application" / "conftest.py"))
NOW = h["NOW"]
REMOTE: str = h["REMOTE"]
EVERYTHING = h["EVERYTHING"]
make_capabilities: Callable[..., WorkerCapabilities] = h["make_capabilities"]
INSTANCE = SEED.instance_id


@dataclass
class Side:
    """One backend with the real bus over it, seeding helpers and committed-state observations."""

    kind: str
    uow_factory: UnitOfWorkFactory
    clock: FrozenClock
    ids: LockedIds
    bus: Bus
    pg: PostgresTestBackend | None = None
    memory: InMemoryBackend | None = None
    people: dict[str, Actor] = field(default_factory=dict[str, Actor])
    requests: Iterator[int] = field(default_factory=lambda: itertools.count(1))

    # ------------------------------------------------------------------ requests
    def meta(self, key: str | None = None) -> RequestMeta:
        return RequestMeta(f"req_{next(self.requests):0>26}", Surface.TEST, key, self.clock.now())

    def uow(self, *, readonly: bool = False) -> UnitOfWork:
        return self.uow_factory(self.meta(), readonly=readonly)

    def actor(self, who: Actor | str) -> Actor:
        return self.people[who] if isinstance(who, str) else who

    def run(self, dto: object, actor: Actor | str = "owner", *, key: str | None = None) -> Any:
        return self.bus.dispatch(dto, actor=self.actor(actor), meta=self.meta(key))

    def ask(self, dto: object, actor: Actor | str = "owner") -> Any:
        return self.bus.ask(dto, actor=self.actor(actor), meta=self.meta())

    # ------------------------------------------------------------------ seeding
    def person(
        self,
        name: str,
        roles: Mapping[ScopeId, Role] | None = None,
        *,
        kind: PrincipalKind = PrincipalKind.HUMAN,
    ) -> Actor:
        principal = new_principal(
            principal_id=PrincipalId(self.ids.new_id()),
            kind=kind,
            display_name=name,
            created_by=None,
            now=self.clock.now(),
        )
        with self.uow() as uow:
            uow.repo(PrincipalRepository).add(principal)
            for scope_id, role in (roles or {}).items():
                uow.repo(MembershipRepository).upsert(
                    Membership(scope_id, principal.id, role, None, self.clock.now())
                )
            uow.commit()
        actor = Actor(principal_id=principal.id, kind=kind, display_name=name)
        self.people[name] = actor
        return actor

    def workspace(self, slug: str = "personal", title: str = "Personal") -> WorkspaceId:
        return WorkspaceId(self.run(CreateWorkspace(slug=slug, title=title)).workspace_id)

    def project(self, workspace_id: WorkspaceId, slug: str = "skm", title: str = "SKM") -> ProjectId:
        return ProjectId(
            self.run(CreateProject(workspace_id=workspace_id, slug=slug, title=title)).project_id
        )

    def host(self, name: str = "laptop") -> HostId:
        platform = RegisterHostDefsHostPlatform(os=HostOs.LINUX, arch=HostArch.X86_64)
        return HostId(self.run(RegisterHost(name=name, platform=platform)).host_id)

    def repository(
        self, workspace_id: WorkspaceId, title: str = "app", remote: str | None = REMOTE
    ) -> RepositoryId:
        return RepositoryId(
            self.run(
                RegisterRepository(
                    workspace_id=workspace_id, title=title, remote_url=remote, external_id=None
                )
            ).repository_id
        )

    def worker(
        self,
        workspace_id: WorkspaceId,
        host_id: HostId,
        name: str = "w1",
        *,
        state: WorkerState = WorkerState.OFFLINE,
        capabilities: WorkerCapabilities | None = None,
    ) -> tuple[Actor, Worker]:
        """A worker principal with its ``worker`` membership and a ``Worker`` row, as domain values."""
        principal = new_principal(
            principal_id=PrincipalId(self.ids.new_id()),
            kind=PrincipalKind.WORKER,
            display_name=name,
            created_by=None,
            now=self.clock.now(),
        )
        worker = Worker(
            id=WorkerId(self.ids.new_id()),
            workspace_id=workspace_id,
            host_id=host_id,
            principal_id=principal.id,
            display_name=name,
            capabilities=capabilities or make_capabilities(),
            state=state,
            last_heartbeat_at=None,
            registered_at=self.clock.now(),
            row_version=1,
        )
        with self.uow() as uow:
            uow.repo(PrincipalRepository).add(principal)
            uow.repo(MembershipRepository).upsert(
                Membership(ScopeId(workspace_id), principal.id, Role.WORKER, None, self.clock.now())
            )
            uow.repo(WorkerRepository).add(worker)
            uow.commit()
        actor = Actor(principal_id=principal.id, kind=PrincipalKind.WORKER, display_name=name)
        self.people[name] = actor
        return actor, worker

    def tick(self, seconds: float = 1.0) -> None:
        self.clock.advance(timedelta(seconds=seconds))

    # ------------------------------------------------------------------ observations
    def events(self, name: str | None = None) -> list[tuple[str, dict[str, Any]]]:
        """Committed events as ``(type, payload)``, in commit order."""
        if self.memory is not None:
            found = [(e.type, dict(e.payload)) for e in self.memory.committed.core.events]
        else:
            assert self.pg is not None
            rows = self.pg.execute(
                "SELECT event_type, payload FROM skm_core.domain_events ORDER BY recorded_at, stream_kind, "
                "stream_id, stream_seq"
            )
            found = [(cast("str", row[0]), cast("dict[str, Any]", row[1])) for row in rows]
        if name is None:
            return found
        return [item for item in found if item[0] == f"urn:skm:workspace:event:{name}:v1"]

    def sql(self, statement: str, params: object = None) -> list[tuple[Any, ...]]:
        """Committed-state SQL through the observer connection (PostgreSQL only)."""
        assert self.pg is not None
        return self.pg.execute(statement, params)

    def close(self) -> None:
        if self.pg is not None:
            self.pg.close()


def _bus(uow_factory: UnitOfWorkFactory, registry: BusRegistry, clock: FrozenClock, ids: LockedIds) -> Bus:
    packs = h["Packs"]()
    return Bus(
        registry=registry,
        schemas=h["schemas"](),
        uow_factory=uow_factory,
        authorizer=RbacAuthorizer(clock),
        scopes=FakeScopeChain(),
        config=ConfigLoader(h["settings_registry"](), packs),
        clock=clock,
        ids=ids,
        entropy=DeterministicEntropy(),
        gateways=GatewayTable({TokenPepperSource: h["FixedPepper"]()}, "control_plane_gateway"),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )


def _registry() -> BusRegistry:
    return BusRegistry.build(
        (ACCESS, WORKSPACE),
        schemas=h["schemas"](),
        permission_catalog=EVERYTHING,
        disabled_modules=frozenset(),
    )


def memory_side() -> Side:
    registry, clock, ids = _registry(), FrozenClock(NOW), LockedIds()
    packs, authorizer = h["Packs"](), RbacAuthorizer(clock)
    factories: dict[type, Callable[[Any], object]] = {
        **MEMORY_CORE,
        **MEMORY_ACCESS,
        **MEMORY_WORKSPACE,
        ConfigStore: MemoryConfigStore,
        PackConfigSource: lambda _state: packs,
        Authorizer: lambda _state: authorizer,
    }
    backend = InMemoryBackend(
        factories=factories,
        schemas=h["schemas"](),
        subscriptions=registry.subscription_index(),
        ids=ids,
        clock=clock,
    )
    uow_factory = backend.uow_factory()
    seed_backend(uow_factory)
    made = Side("memory", uow_factory, clock, ids, _bus(uow_factory, registry, clock, ids), memory=backend)
    made.person("owner", {INSTANCE: Role.OWNER})
    return made


def postgres_side(database: TestDatabase) -> Side:
    registry, clock, ids = _registry(), FrozenClock(NOW), LockedIds()
    packs, authorizer = h["Packs"](), RbacAuthorizer(clock)
    pg = PostgresTestBackend(database, pool_max_size=8)
    clocked = {
        port: (lambda conn, adapter=adapter: adapter(conn, clock=clock))
        for port, adapter in cast("Mapping[type, Any]", POSTGRES_WORKSPACE).items()
    }
    factories: dict[type, Callable[[psycopg.Connection], object]] = {
        **cast(
            "dict[type, Callable[[psycopg.Connection], object]]",
            postgres_repository_table(("access", "workspace")),
        ),
        **clocked,
        PrincipalRepository: lambda conn: PostgresPrincipalRepository(conn, clock=clock),
        TokenRepository: lambda conn: PostgresTokenRepository(conn, clock=clock),
        IdempotencyStore: PostgresIdempotencyStore,
        AuditLog: PostgresAuditLog,
        ConfigStore: PostgresConfigStore,
        PackConfigSource: lambda _conn: packs,
        Authorizer: lambda _conn: authorizer,
    }
    writer = PostgresEventWriter(schemas=h["schemas"](), subscriptions=registry.subscription_index(), ids=ids)
    uow_factory = PostgresUowFactory(pg.pool, factories, writer, clock)
    made = Side("postgres", uow_factory, clock, ids, _bus(uow_factory, registry, clock, ids), pg=pg)
    made.person("owner", {INSTANCE: Role.OWNER})
    return made


@pytest.fixture(params=BACKEND_PARAMS)
def side(request: pytest.FixtureRequest) -> Iterator[Side]:
    yield from iter_side(request, memory_side, postgres_side)


@pytest.fixture
def pg_side(clean_test_database: TestDatabase) -> Iterator[Side]:  # noqa: F811 - the imported fixture
    yield from iter_pg_side(clean_test_database, postgres_side)
