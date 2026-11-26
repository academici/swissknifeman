"""Two-backend harness of the policy contract suite: memory ∥ PostgreSQL (policy §6, §11, §15).

Each side offers a unit-of-work factory over the repositories of its backend with the same deterministic clock
and ids, and the same seed: the instance scope, the two workspace scopes of ``support.seed`` (the PostgreSQL
side gets them from ``clean_test_database``), a ``Workspace`` row for each (the composite FK of
``tool_intents``) and a few principals. Intents live in the workspace scope itself: the foreign key of
``scope_id`` needs a real scope and the repositories do not care about its kind.
"""

import itertools
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from functools import cache
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest

from fakes.clock import FrozenClock
from skm.adapters.memory.access import REPOSITORIES as MEMORY_ACCESS
from skm.adapters.memory.core import REPOSITORIES as MEMORY_CORE
from skm.adapters.memory.policy import REPOSITORIES as MEMORY_POLICY
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.memory.workspace import REPOSITORIES as MEMORY_WORKSPACE
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.policy import REPOSITORIES as POSTGRES_POLICY
from skm.adapters.postgres.uow import PostgresUowFactory
from skm.bootstrap.adapters import postgres_repository_table
from skm.kernel.actor import PrincipalKind
from skm.kernel.ids import PrincipalId, ScopeId, ToolIntentId
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork, UnitOfWorkFactory
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import PrincipalRepository
from skm.modules.policy.domain.approval import Approval, ApprovalDecision, ApprovalId
from skm.modules.policy.domain.tool_intent import (
    EffectKind,
    IntentState,
    RiskClass,
    ToolIntent,
    args_digest,
    normalize_args,
)
from skm.modules.policy.ports import ToolIntentRepository
from skm.modules.workspace.domain.slug import Slug
from skm.modules.workspace.domain.workspace import Workspace, WorkspaceState
from skm.modules.workspace.ports import WorkspaceRepository
from skm.platform.schema.registry import SchemaRegistry
from support.backend import LockedIds, PostgresTestBackend
from support.pg import TestDatabase, clean_test_database, pg_session, test_database  # noqa: F401
from support.seed import SEED, seed_backend
from support.sides import BACKEND_PARAMS, iter_pg_side, iter_side
from unit.policy.application.harness import NOW, commit_args

__all__ = ["Side", "memory_side", "pg_side", "postgres_side", "side"]

WORKSPACE = SEED.workspace_id
OTHER_WORKSPACE = SEED.other_workspace_id
ACTORS = (SEED.principal_id, PrincipalId(UUID(int=1)), PrincipalId(UUID(int=2)))
APPROVER = ACTORS[1]


@dataclass
class Side:
    """One backend with the repositories of the policy module and the seed."""

    kind: str
    uow_factory: UnitOfWorkFactory
    clock: FrozenClock
    ids: LockedIds
    pg: PostgresTestBackend | None = None
    memory: InMemoryBackend | None = None
    requests: Iterator[int] = field(default_factory=lambda: itertools.count(1))

    def meta(self) -> RequestMeta:
        return RequestMeta(f"req_{next(self.requests):0>26}", Surface.TEST, None, self.clock.now())

    def uow(self, *, readonly: bool = False) -> UnitOfWork:
        return self.uow_factory(self.meta(), readonly=readonly)

    def tick(self, seconds: float = 1.0) -> None:
        self.clock.advance(timedelta(seconds=seconds))

    def sql(self, statement: str, params: object = None) -> list[tuple[Any, ...]]:
        """Committed-state SQL through the observer connection (PostgreSQL only)."""
        assert self.pg is not None
        return self.pg.execute(statement, params)

    def close(self) -> None:
        if self.pg is not None:
            self.pg.close()

    # ------------------------------------------------------------------ builders
    def intent(self, **changes: Any) -> ToolIntent:
        """A ``proposed`` ``git_commit`` intent with a fresh digest; ``changes`` replace fields."""
        tree = "sha256:" + f"{next(self.requests):0>64x}"
        args = normalize_args(EffectKind.GIT_COMMIT, commit_args(tree_digest=tree))
        values: dict[str, Any] = {
            "id": ToolIntentId(self.ids.new_id()),
            "workspace_id": WORKSPACE,
            "scope_id": ScopeId(WORKSPACE),
            "subject_ref": "run:1/attempt:1",
            "actor_id": ACTORS[0],
            "kind": EffectKind.GIT_COMMIT,
            "normalized_args": args,
            "args_digest": args_digest(EffectKind.GIT_COMMIT, args),
            "risk": RiskClass.LOW,
            "reason": "integrate",
            "state": IntentState.PROPOSED,
            "denied_reason": None,
            "created_at": self.clock.now(),
            "expires_at": self.clock.now() + timedelta(days=3),
            "row_version": 1,
        }
        values.update(changes)
        return ToolIntent(**values)

    def approval(self, intent: ToolIntent, **changes: Any) -> Approval:
        values: dict[str, Any] = {
            "id": ApprovalId(self.ids.new_id()),
            "intent_id": intent.id,
            "approver_id": APPROVER,
            "decision": ApprovalDecision.APPROVE,
            "args_digest": intent.args_digest,
            "single_use": True,
            "expires_at": self.clock.now() + timedelta(hours=1),
            "used_at": None,
            "reason": "ok",
            "created_at": self.clock.now(),
        }
        values.update(changes)
        return Approval(**values)

    def store(self, *intents: ToolIntent) -> None:
        with self.uow() as uow:
            for item in intents:
                uow.repo(ToolIntentRepository).add(item)
            uow.commit()


def _seed(side: Side) -> None:
    with side.uow() as uow:
        for name, workspace_id in (("one", WORKSPACE), ("two", OTHER_WORKSPACE)):
            uow.repo(WorkspaceRepository).add(
                Workspace(
                    id=workspace_id,
                    slug=Slug(name),
                    title=name,
                    state=WorkspaceState.ACTIVE,
                    row_version=1,
                    created_at=side.clock.now(),
                )
            )
        for principal_id in ACTORS:
            uow.repo(PrincipalRepository).add(
                new_principal(
                    principal_id=principal_id,
                    kind=PrincipalKind.HUMAN,
                    display_name=f"p-{str(principal_id)[-4:]}",
                    created_by=None,
                    now=side.clock.now(),
                )
            )
        uow.commit()


@cache
def _schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def memory_side() -> Side:
    clock, ids = FrozenClock(NOW), LockedIds()
    factories: dict[type, Callable[[Any], object]] = {
        **MEMORY_CORE,
        **MEMORY_ACCESS,
        **MEMORY_WORKSPACE,
        **MEMORY_POLICY,
    }
    backend = InMemoryBackend(factories=factories, schemas=_schemas(), subscriptions={}, ids=ids, clock=clock)
    uow_factory = backend.uow_factory()
    seed_backend(uow_factory)
    made = Side("memory", uow_factory, clock, ids, memory=backend)
    _seed(made)
    return made


def postgres_side(database: TestDatabase) -> Side:
    clock, ids = FrozenClock(NOW), LockedIds()
    pg = PostgresTestBackend(database, pool_max_size=8)
    table = cast(
        "Mapping[type, Callable[[psycopg.Connection], object]]",
        postgres_repository_table(("access", "workspace", "policy")),
    )
    clocked = {
        port: (lambda conn, adapter=adapter: adapter(conn, clock=clock))
        for port, adapter in cast("Mapping[type, Any]", POSTGRES_POLICY).items()
        if port.__name__ == "ToolIntentRepository"
    }
    factories: dict[type, Callable[[psycopg.Connection], object]] = {**table, **clocked}
    writer = PostgresEventWriter(schemas=_schemas(), subscriptions={}, ids=ids)
    uow_factory = PostgresUowFactory(pg.pool, factories, writer, clock)
    made = Side("postgres", uow_factory, clock, ids, pg=pg)
    _seed(made)
    return made


@pytest.fixture(params=BACKEND_PARAMS)
def side(request: pytest.FixtureRequest) -> Iterator[Side]:
    yield from iter_side(request, memory_side, postgres_side)


@pytest.fixture
def pg_side(clean_test_database: TestDatabase) -> Iterator[Side]:  # noqa: F811 - the imported fixture
    yield from iter_pg_side(clean_test_database, postgres_side)
