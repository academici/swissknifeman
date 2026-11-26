"""The real bus of the policy tests over PostgreSQL: the memory tests' ``World`` on a PostgreSQL backend.

``World`` talks to its backend through ``uow_factory()`` only for ``uow()``, which is all the PostgreSQL
scenarios use besides the bus; the memory-state observers of ``World`` (events, snapshots) are not available
here, the scenarios read PostgreSQL through ``Side.sql``-style queries instead.
"""

from collections.abc import Callable, Mapping
from datetime import timedelta
from typing import Any, cast

import psycopg

from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from skm.adapters.postgres.access.repositories import PostgresPrincipalRepository, PostgresTokenRepository
from skm.adapters.postgres.config_store import PostgresConfigStore
from skm.adapters.postgres.core.audit import PostgresAuditLog
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.core.idempotency import PostgresIdempotencyStore
from skm.adapters.postgres.policy import REPOSITORIES as POSTGRES_POLICY
from skm.adapters.postgres.uow import PostgresUowFactory
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import AuditLog, Authorizer, IdempotencyStore
from skm.application_bus.registry import BusRegistry
from skm.bootstrap.adapters import postgres_repository_table
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.module import MODULE as ACCESS
from skm.modules.access.ports import PrincipalRepository, TokenPepperSource, TokenRepository
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.policy.module import MODULE as POLICY
from skm.modules.settings.module import MODULE as SETTINGS
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource
from support.backend import LockedIds, PostgresTestBackend
from support.pg import TestDatabase
from support.seed import SEED
from unit.policy.application.harness import (
    ALL_EFFECTS,
    EVERYTHING,
    NOW,
    FixedPepper,
    Packs,
    World,
    schemas,
    settings_registry,
)

__all__ = ["PgWorld", "build_pg_world"]


class PgWorld(World):
    """``World`` whose observers read PostgreSQL."""

    pg: PostgresTestBackend

    def sql(self, statement: str, params: object = None) -> list[tuple[Any, ...]]:
        return self.pg.execute(statement, params)

    def states(self) -> dict[Any, str]:
        return {row[0]: row[1] for row in self.sql("SELECT id, state FROM skm_policy.tool_intents")}

    def spent(self) -> int:
        return int(self.sql("SELECT count(*) FROM skm_policy.approvals WHERE used_at IS NOT NULL")[0][0])

    def started_events(self) -> int:
        return int(
            self.sql(
                "SELECT count(*) FROM skm_core.domain_events WHERE event_type = %s",
                ("urn:skm:policy:event:intent-execution-started:v1",),
            )[0][0]
        )

    def close(self) -> None:
        self.pg.close()


def build_pg_world(database: TestDatabase) -> PgWorld:
    registry = BusRegistry.build(
        (ACCESS, WORKSPACE, SETTINGS, POLICY),
        schemas=schemas(),
        permission_catalog=EVERYTHING,
        disabled_modules=frozenset(),
    )
    clock, ids = FrozenClock(NOW), LockedIds()
    packs, authorizer = Packs(), RbacAuthorizer(clock)
    pg = PostgresTestBackend(database, pool_max_size=8)
    table = cast(
        "Mapping[type, Callable[[psycopg.Connection], object]]",
        postgres_repository_table(("access", "workspace", "settings", "policy")),
    )
    clocked = {
        port: (lambda conn, adapter=adapter: adapter(conn, clock=clock))
        for port, adapter in cast("Mapping[type, Any]", POSTGRES_POLICY).items()
        if port.__name__ == "ToolIntentRepository"
    }
    factories: dict[type, Callable[[psycopg.Connection], object]] = {
        **table,
        **clocked,
        PrincipalRepository: lambda conn: PostgresPrincipalRepository(conn, clock=clock),
        TokenRepository: lambda conn: PostgresTokenRepository(conn, clock=clock),
        IdempotencyStore: PostgresIdempotencyStore,
        AuditLog: PostgresAuditLog,
        ConfigStore: PostgresConfigStore,
        PackConfigSource: lambda _conn: packs,
        Authorizer: lambda _conn: authorizer,
    }
    writer = PostgresEventWriter(schemas=schemas(), subscriptions=registry.subscription_index(), ids=ids)
    uow_factory = PostgresUowFactory(pg.pool, factories, writer, clock)
    loader = ConfigLoader(settings_registry(), packs)
    bus = Bus(
        registry=registry,
        schemas=schemas(),
        uow_factory=uow_factory,
        authorizer=authorizer,
        scopes=FakeScopeChain(),
        config=loader,
        clock=clock,
        ids=ids,
        entropy=DeterministicEntropy(),
        gateways=GatewayTable({TokenPepperSource: FixedPepper()}, "control_plane_gateway"),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )

    class _Backend:
        def uow_factory(self) -> Any:
            return uow_factory

    world = PgWorld(cast("Any", _Backend()), bus, clock, ids, loader)
    world.pg = pg
    world.person("owner", {SEED.instance_id: Role.OWNER})
    world.workspace_id = WorkspaceId(
        world.run(CreateWorkspace(slug="personal", title="Personal")).workspace_id
    )
    world.project_id = ProjectId(
        world.run(CreateProject(workspace_id=world.workspace_id, slug="skm", title="SKM")).project_id
    )
    plan, run = ScopeId(ids.new_id()), ScopeId(ids.new_id())
    with world.uow() as uow:
        scopes = uow.repo(ScopeRegistry)
        scopes.create(plan, ScopeKind.PLAN, parent=ScopeId(world.project_id), workspace_id=world.workspace_id)
        scopes.create(run, ScopeKind.RUN, parent=plan, workspace_id=world.workspace_id)
        uow.commit()
    world.scope_id = run
    world.allow_effects(*ALL_EFFECTS)
    return world
