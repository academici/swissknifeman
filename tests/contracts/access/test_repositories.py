"""Access repositories: one contract over memory and PostgreSQL, plus PostgreSQL guards (access §6, §11, §15).

memory ∥ pg: CRUD of principals, identities, tokens and memberships; unique prefix, identity and active name;
the name a superseded token frees; keyset pagination; ``count_active_owners``; no revival through ``save``;
live reads of a committed revoke (ACCESS-02). The memory adapter does not imitate FK/CHECK/triggers (adapters
§2.2), so those cases, the runtime role ``skm_app`` and the real-concurrency cases run on PostgreSQL only.

Concurrency (PostgreSQL, real threads, READ COMMITTED, the real access handlers through the bus): a first
command stops before COMMIT, a second one must queue on a lock (seen in ``pg_locks``), then the first commits.
Two owner removals keep an active owner (the second gets ``LAST_OWNER_REQUIRED``); two rotations of one token
give exactly one successor; revoke and rotate queue on the token row and never revive a revoked token; the
loser of a prefix race keeps a usable transaction; an assignment renewal does not revive a revoked token. A
control run without the owner lock and its row locks loses the last owner, so the race driven here is real.
"""

import itertools
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from runpy import run_path
from types import TracebackType
from typing import Any, LiteralString, Self, cast, override
from uuid import UUID

import psycopg
import pytest
from psycopg import errors as pgerr
from psycopg import sql

from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from skm.adapters.memory.access import REPOSITORIES as MEMORY_ACCESS
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core import REPOSITORIES as MEMORY_CORE
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.postgres.access import repositories as pg_access
from skm.adapters.postgres.access.repositories import (
    PostgresIdentityRepository,
    PostgresMembershipRepository,
    PostgresPrincipalRepository,
    PostgresTokenRepository,
)
from skm.adapters.postgres.config_store import PostgresConfigStore
from skm.adapters.postgres.core.audit import PostgresAuditLog
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.core.idempotency import PostgresIdempotencyStore
from skm.adapters.postgres.uow import PostgresUowFactory
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import AuditLog, Authorizer, IdempotencyStore
from skm.application_bus.registry import BusRegistry
from skm.bootstrap.adapters import postgres_repository_table
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    Conflict,
    NotFound,
    PreconditionFailed,
    SkmError,
    Unauthenticated,
    ValidationFailed,
)
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import Isolation, RequestMeta, Surface, UnitOfWork, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.application import authz, facade
from skm.modules.access.application.tokens import default_settings
from skm.modules.access.domain.identity import PrincipalIdentity
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import Principal, PrincipalState, disable, new_principal
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import (
    ApiToken,
    TokenId,
    TokenKind,
    generate_secret,
    grant_of,
    hash_secret,
    revoke,
    rotate,
)
from skm.modules.access.module import MODULE
from skm.modules.access.ports import (
    IdentityRepository,
    MembershipRepository,
    PrincipalRepository,
    TokenPepperSource,
    TokenRepository,
)
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource
from support.backend import LockedIds, PostgresTestBackend
from support.pg import TestDatabase, clean_test_database, pg_session, test_database  # noqa: F401
from support.seed import seed_backend
from support.sides import BACKEND_PARAMS, iter_pg_side, iter_side

h = run_path(str(Path(__file__).parents[2] / "unit" / "access" / "application" / "test_create_token.py"))
commands = h["commands"]
NOW, PEPPER, EVERYTHING = h["NOW"], h["PEPPER"], h["EVERYTHING"]
INSTANCE, WS, WS2, P1, PLAN1, RUN1 = (h[n] for n in ("INSTANCE", "WS", "WS2", "P1", "PLAN1", "RUN1"))
SETTINGS = default_settings()


class LockedEntropy(DeterministicEntropy):
    """Deterministic entropy that concurrent commands of one test may share."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()

    @override
    def bytes(self, n: int) -> bytes:
        with self._lock:
            return super().bytes(n)


# ---------------------------------------------------------------------------------------------------------
# the two sides


@dataclass
class Side:
    """One backend with the access repositories, the real bus over it and seeding helpers."""

    kind: str
    uow_factory: UnitOfWorkFactory
    clock: FrozenClock
    ids: LockedIds
    registry: BusRegistry
    authorizer: Any
    packs: Any
    pg: PostgresTestBackend | None = None
    memory: InMemoryBackend | None = None
    entropy: LockedEntropy = field(default_factory=LockedEntropy)
    requests: Iterator[int] = field(default_factory=lambda: itertools.count(1))

    def meta(self) -> RequestMeta:
        return RequestMeta(f"req_{next(self.requests):0>26}", Surface.TEST, None, self.clock.now())

    def uow(self, *, readonly: bool = False, isolation: Isolation = Isolation.READ_COMMITTED) -> UnitOfWork:
        return self.uow_factory(self.meta(), readonly=readonly, isolation=isolation)

    def bus(self, uow_factory: UnitOfWorkFactory | None = None) -> Bus:
        return Bus(
            registry=self.registry,
            schemas=h["schemas"](),
            uow_factory=uow_factory or self.uow_factory,
            authorizer=self.authorizer,
            scopes=FakeScopeChain(),
            config=ConfigLoader(h["settings_registry"](), self.packs),
            clock=self.clock,
            ids=self.ids,
            entropy=self.entropy,
            gateways=GatewayTable({TokenPepperSource: h["FixedPepper"]()}, "control_plane_gateway"),
            retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
            idempotency_ttl=timedelta(hours=1),
        )

    def run(self, dto: object, actor: Actor, *, bus: Bus | None = None) -> Any:
        return (bus or self.bus()).dispatch(dto, actor=actor, meta=self.meta())

    @property
    def dsn(self) -> str:
        assert self.pg is not None
        return self.pg.database.dsn

    def execute_rows(self, statement: str) -> list[tuple[Any, ...]]:
        """Committed-state SQL through the observer connection (PostgreSQL only)."""
        assert self.pg is not None
        return self.pg.execute(statement)

    def stored_text(self) -> str:
        """Every committed row of every table as text: access, events, audit, receipts, outbox, config."""
        if self.memory is not None:
            committed = self.memory.committed
            core = committed.core
            return "\n".join(
                [
                    repr(committed.modules),
                    repr(list(core.events)),
                    repr(core.audit),
                    repr(list(core.idempotency.values())),
                    repr(list(core.outbox.values())),
                ]
            )
        tables = self.execute_rows(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' AND table_schema LIKE 'skm\\_%' ORDER BY 1, 2"
        )
        assert self.pg is not None
        texts: list[str] = []
        for schema, table in tables:
            query = sql.SQL("SELECT row_to_json(t)::text FROM {} t").format(sql.Identifier(schema, table))
            texts.extend(row[0] for row in self.pg.observer.execute(query).fetchall())
        return "\n".join(texts)

    def close(self) -> None:
        if self.pg is not None:
            self.pg.close()

    # ------------------------------------------------------------------ seeding through the repositories
    def new_principal(self, name: str, kind: PrincipalKind = PrincipalKind.HUMAN) -> Principal:
        return new_principal(
            principal_id=PrincipalId(self.ids.new_id()),
            kind=kind,
            display_name=name,
            created_by=None,
            now=self.clock.now(),
        )

    def principal(
        self, name: str, kind: PrincipalKind = PrincipalKind.HUMAN, roles: dict[ScopeId, Role] | None = None
    ) -> PrincipalId:
        made = self.new_principal(name, kind)
        with self.uow() as uow:
            uow.repo(PrincipalRepository).add(made)
            for scope_id, role in (roles or {}).items():
                uow.repo(MembershipRepository).upsert(
                    Membership(scope_id, made.id, role, None, self.clock.now())
                )
            uow.commit()
        return made.id

    def new_token(
        self,
        owner: PrincipalId,
        name: str,
        *,
        kind: TokenKind = TokenKind.PERSONAL,
        prefix: str | None = None,
        scope_id: ScopeId | None = None,
        permissions: frozenset[str] | None = None,
        expires_in: timedelta | None = timedelta(days=30),
        assignment_id: UUID | None = None,
        step_id: UUID | None = None,
    ) -> tuple[ApiToken, str]:
        secret = generate_secret(self.entropy.bytes)
        if prefix is not None:
            secret = replace(secret, prefix=prefix)
        now = self.clock.now()
        token = ApiToken(
            id=TokenId(self.ids.new_id()),
            principal_id=owner,
            kind=kind,
            name=name,
            prefix=secret.prefix,
            secret_hash=hash_secret(secret, PEPPER),
            scope_id=scope_id,
            permissions=permissions,
            expires_at=None if expires_in is None else now + expires_in,
            created_at=now,
            created_by=owner,
            last_used_at=None,
            revoked_at=None,
            revoked_by=None,
            assignment_id=assignment_id,
            step_id=step_id,
            superseded_by=None,
        )
        return token, str(secret)

    def token(self, owner: PrincipalId, name: str, **fields: Any) -> tuple[ApiToken, str]:
        token, secret = self.new_token(owner, name, **fields)
        with self.uow() as uow:
            uow.repo(TokenRepository).add(token)
            uow.commit()
        return token, secret

    def stored(self, token_id: TokenId) -> ApiToken:
        with self.uow(readonly=True) as uow:
            return uow.repo(TokenRepository).get(token_id)

    def tokens_of(self, owner: PrincipalId) -> list[ApiToken]:
        with self.uow(readonly=True) as uow:
            return list(
                uow.repo(TokenRepository).list_for(owner, include_inactive=True, after=None, limit=200).items
            )

    def active_owners(self) -> int:
        with self.uow() as uow:
            return uow.repo(MembershipRepository).count_active_owners(INSTANCE)


def _collaborators() -> tuple[BusRegistry, Any, Any, FrozenClock, LockedIds]:
    registry = BusRegistry.build(
        (MODULE,), schemas=h["schemas"](), permission_catalog=EVERYTHING, disabled_modules=frozenset()
    )
    return registry, h["DomainAuthorizer"](), h["Packs"](), FrozenClock(NOW), LockedIds()


def _seed_tree(uow_factory: UnitOfWorkFactory, clock: FrozenClock) -> None:
    """A project, plan and run under the seeded workspace ``WS`` (instance and workspaces are seeded)."""
    with uow_factory(RequestMeta("req_TREE", Surface.TEST, None, clock.now())) as uow:
        scopes, ws = uow.repo(ScopeRegistry), WorkspaceId(WS)
        scopes.create(P1, ScopeKind.PROJECT, parent=WS, workspace_id=ws)
        scopes.create(PLAN1, ScopeKind.PLAN, parent=P1, workspace_id=ws)
        scopes.create(RUN1, ScopeKind.RUN, parent=PLAN1, workspace_id=ws)
        uow.commit()


def memory_side() -> Side:
    registry, authorizer, packs, clock, ids = _collaborators()
    factories: dict[type, Any] = {
        **MEMORY_CORE,
        **MEMORY_ACCESS,
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
    _seed_tree(uow_factory, clock)
    return Side("memory", uow_factory, clock, ids, registry, authorizer, packs, memory=backend)


def postgres_side(database: TestDatabase) -> Side:
    registry, authorizer, packs, clock, ids = _collaborators()
    pg = PostgresTestBackend(database, pool_max_size=8)
    factories: dict[type, Callable[[psycopg.Connection], object]] = {
        **cast("dict[type, Callable[[psycopg.Connection], object]]", postgres_repository_table(("access",))),
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
    _seed_tree(uow_factory, clock)  # clean_database seeded the instance and both workspaces
    return Side("postgres", uow_factory, clock, ids, registry, authorizer, packs, pg=pg)


@pytest.fixture(params=BACKEND_PARAMS)
def side(request: pytest.FixtureRequest) -> Iterator[Side]:
    yield from iter_side(request, memory_side, postgres_side)


@pytest.fixture
def pg_side(clean_test_database: TestDatabase) -> Iterator[Side]:  # noqa: F811 - the imported fixture
    yield from iter_pg_side(clean_test_database, postgres_side)


def human(principal_id: PrincipalId) -> Actor:
    return Actor(principal_id=principal_id, kind=PrincipalKind.HUMAN, display_name="tester")


# ---------------------------------------------------------------------------------------------------------
# principals and identities


def test_principals_round_trip_and_save_compares_the_row_version(side: Side) -> None:
    made = side.new_principal("  Ann  ")
    with side.uow() as uow:
        uow.repo(PrincipalRepository).add(made)
        uow.commit()
    with side.uow(readonly=True) as uow:
        assert uow.repo(PrincipalRepository).get(made.id) == made
        with pytest.raises(NotFound) as missing:
            uow.repo(PrincipalRepository).get(PrincipalId(side.ids.new_id()))
    assert missing.value.details["kind"] == "principal"
    with side.uow() as uow, pytest.raises(Conflict) as duplicate:
        uow.repo(PrincipalRepository).add(made)
    assert duplicate.value.code is ErrorCode.ALREADY_EXISTS
    with side.uow() as uow:
        uow.repo(PrincipalRepository).save(disable(made), expected_version=1)
        uow.commit()
    with side.uow() as uow:
        repo = uow.repo(PrincipalRepository)
        assert repo.get(made.id).state is PrincipalState.DISABLED
        with pytest.raises(Conflict) as stale:
            repo.save(replace(made, display_name="Bob", row_version=2), expected_version=1)
        assert stale.value.code is ErrorCode.VERSION_CONFLICT
        assert stale.value.details == {"expected": 1, "actual": 2}
        with pytest.raises(ValueError, match="keeps its id, kind"):
            repo.save(replace(made, kind=PrincipalKind.SERVICE, row_version=3), expected_version=2)
        with pytest.raises(NotFound):
            repo.save(side.new_principal("ghost"), expected_version=1)


def test_principals_page_by_creation_time_then_id(side: Side) -> None:
    made: list[Principal] = []
    with side.uow() as uow:
        for n, kind in enumerate([PrincipalKind.HUMAN, PrincipalKind.SERVICE, PrincipalKind.HUMAN] * 2):
            if n % 2 == 0:
                side.clock.advance(timedelta(seconds=1))  # pairs share a created_at: the id breaks the tie
            principal = side.new_principal(f"p{n}", kind)
            uow.repo(PrincipalRepository).add(principal)
            made.append(principal)
        uow.commit()
    expected = sorted(made, key=lambda p: (p.created_at, str(p.id)))
    with side.uow(readonly=True) as uow:
        repo = uow.repo(PrincipalRepository)
        seen: list[Principal] = []
        after: str | None = None
        while True:
            page = repo.list(kind=None, after=after, limit=4)
            seen.extend(page.items)
            if page.next is None:
                break
            after = page.next
        assert seen == expected
        services = repo.list(kind=PrincipalKind.SERVICE, after=None, limit=200).items
        assert list(services) == [p for p in expected if p.kind is PrincipalKind.SERVICE]
        with pytest.raises(ValidationFailed) as bad:
            repo.list(kind=None, after="bm90LWEtY3Vyc29y", limit=2)
    assert bad.value.code is ErrorCode.SCHEMA_INVALID
    assert bad.value.details["field"] == "after"


def test_identities_are_unique_per_issuer_and_subject(side: Side) -> None:
    owner = side.principal("ann")
    first = PrincipalIdentity(owner, "local", "owner", side.clock.now())
    later = PrincipalIdentity(
        owner, "oidc:https://id.example", "ann", side.clock.now() + timedelta(seconds=1)
    )
    with side.uow() as uow:
        uow.repo(IdentityRepository).add(later)
        uow.repo(IdentityRepository).add(first)
        uow.commit()
    other = side.principal("bob")
    with side.uow() as uow:
        repo = uow.repo(IdentityRepository)
        with pytest.raises(Conflict) as taken:
            repo.add(PrincipalIdentity(other, "local", "owner", side.clock.now()))
        assert taken.value.code is ErrorCode.ALREADY_EXISTS
        assert taken.value.details["kind"] == "identity"
        repo.add(PrincipalIdentity(other, "local", "bob", side.clock.now()))  # the unit of work stays usable
        uow.commit()
    with side.uow(readonly=True) as uow:
        repo = uow.repo(IdentityRepository)
        assert repo.find("local", "owner") == first
        assert repo.find("local", "nobody") is None
        assert repo.for_principal(owner) == (first, later)
        assert [i.subject for i in repo.for_principal(other)] == ["bob"]


# ---------------------------------------------------------------------------------------------------------
# tokens


def test_tokens_round_trip_with_the_assignment_binding(side: Side) -> None:
    worker = side.principal("w", PrincipalKind.WORKER, {WS: Role.WORKER})
    assignment, step = UUID(int=0xA55), UUID(int=0x57E9)
    token, _ = side.token(
        worker,
        f"assignment-{assignment}-step-{step}",
        kind=TokenKind.ASSIGNMENT,
        scope_id=RUN1,
        permissions=frozenset({"run.read", "step.note", "plan.read"}),
        expires_in=timedelta(hours=1),
        assignment_id=assignment,
        step_id=step,
    )
    with side.uow(readonly=True) as uow:
        repo = uow.repo(TokenRepository)
        assert repo.get(token.id) == token
        assert repo.find_by_prefix(token.prefix) == token
        assert repo.find_by_prefix("aaaaaaaa") is None
        with pytest.raises(NotFound) as missing:
            repo.get(TokenId(side.ids.new_id()))
    assert missing.value.details["kind"] == "token"


def test_a_taken_prefix_id_or_active_name_is_a_conflict_and_the_unit_of_work_goes_on(side: Side) -> None:
    ann = side.principal("ann")
    first, _ = side.token(ann, "laptop", prefix="abcdefgh")
    clash, _ = side.new_token(ann, "phone", prefix="abcdefgh")
    renamed, _ = side.new_token(ann, "laptop")
    with side.uow() as uow:
        repo = uow.repo(TokenRepository)
        with pytest.raises(Conflict) as prefix:
            repo.add(clash)
        with pytest.raises(Conflict) as same_id:
            repo.add(replace(renamed, id=first.id))
        with pytest.raises(Conflict) as name:
            repo.add(renamed)
        fresh, _ = side.new_token(ann, "phone")
        repo.add(fresh)  # after three refusals the same transaction still writes and commits
        uow.commit()
    assert [(e.value.code, e.value.details["field"]) for e in (prefix, same_id, name)] == [
        (ErrorCode.ALREADY_EXISTS, "prefix"),
        (ErrorCode.ALREADY_EXISTS, "id"),
        (ErrorCode.ALREADY_EXISTS, "name"),
    ]
    assert {t.id for t in side.tokens_of(ann)} == {first.id, fresh.id}


def test_a_revoked_or_superseded_token_frees_its_name(side: Side) -> None:
    ann = side.principal("ann")
    first, _ = side.token(ann, "laptop")
    collider, _ = side.token(ann, "other")
    side.clock.advance(timedelta(minutes=1))
    with side.uow() as uow:
        repo = uow.repo(TokenRepository)
        old = repo.get_for_update(first.id)
        attempts = []
        for prefix in (collider.prefix, "zzzzzzzz"):  # the first successor collides: draw again, same UoW
            secret = replace(generate_secret(side.entropy.bytes), prefix=prefix)
            superseded, successor = rotate(
                old,
                new_id=TokenId(side.ids.new_id()),
                new_secret_hash=hash_secret(secret, PEPPER),
                new_prefix=secret.prefix,
                now=side.clock.now(),
                settings=SETTINGS,
                grace=timedelta(minutes=10),
            )
            repo.save(superseded)  # frees the name; superseded_by is checked at commit
            try:
                repo.add(successor)
            except Conflict as error:
                attempts.append(error.details["field"])
                continue
            break
        uow.commit()
    assert attempts == ["prefix"]
    assert side.stored(first.id).superseded_by == successor.id
    assert side.stored(successor.id).name == "laptop"
    again, _ = side.new_token(ann, "laptop")
    with side.uow() as uow, pytest.raises(Conflict) as taken:
        uow.repo(TokenRepository).add(again)  # the successor holds the name now
    assert taken.value.details["field"] == "name"
    current = side.stored(successor.id)
    with side.uow() as uow:
        uow.repo(TokenRepository).save(revoke(current, ann, side.clock.now()))
        uow.repo(TokenRepository).add(again)  # revoked: the name is free again
        uow.commit()


def test_save_never_revives_a_revocation_or_replaces_a_stored_successor(side: Side) -> None:
    ann = side.principal("ann")
    token, _ = side.token(ann, "laptop")
    stale = side.stored(token.id)
    revoked = revoke(stale, ann, side.clock.now())
    with side.uow() as uow:
        uow.repo(TokenRepository).save(revoked)
        uow.commit()
    side.clock.advance(timedelta(minutes=1))
    with side.uow() as uow:
        repo = uow.repo(TokenRepository)
        for copy in (
            replace(stale, expires_at=stale.created_at + timedelta(days=60)),
            revoke(stale, ann, side.clock.now()),
        ):
            with pytest.raises(PreconditionFailed) as refused:
                repo.save(copy)
            assert refused.value.code is ErrorCode.INVALID_TRANSITION
            assert refused.value.details["reason"] == "token_revoked"
        repo.save(revoked)  # the same revocation again is a no-op write
        with pytest.raises(ValueError, match="keeps its identity"):
            repo.save(replace(revoked, scope_id=WS))
        uow.commit()
    rotated, _ = side.token(ann, "phone")
    side.clock.advance(timedelta(minutes=1))
    secret = generate_secret(side.entropy.bytes)
    superseded, successor = rotate(
        rotated,
        new_id=TokenId(side.ids.new_id()),
        new_secret_hash=hash_secret(secret, PEPPER),
        new_prefix=secret.prefix,
        now=side.clock.now(),
        settings=SETTINGS,
        grace=timedelta(minutes=10),
    )
    with side.uow() as uow:
        uow.repo(TokenRepository).save(superseded)
        uow.repo(TokenRepository).add(successor)
        uow.commit()
    with side.uow() as uow:
        repo = uow.repo(TokenRepository)
        for copy in (rotated, replace(superseded, superseded_by=TokenId(side.ids.new_id()))):
            with pytest.raises(PreconditionFailed) as refused:
                repo.save(copy)
            assert refused.value.details["reason"] == "token_superseded"
    assert side.stored(rotated.id).superseded_by == successor.id
    assert side.stored(token.id).revoked_at == revoked.revoked_at


def test_assignment_tokens_touch_and_listing(side: Side) -> None:
    worker = side.principal("w", PrincipalKind.WORKER, {WS: Role.WORKER})
    ann = side.principal("ann")
    first, second = UUID(int=1), UUID(int=2)

    def assignment(assignment_id: UUID, step: int) -> ApiToken:
        return side.token(
            worker,
            f"assignment-{assignment_id}-step-{UUID(int=step)}",
            kind=TokenKind.ASSIGNMENT,
            scope_id=RUN1,
            permissions=frozenset({"run.read"}),
            expires_in=timedelta(hours=1),
            assignment_id=assignment_id,
            step_id=UUID(int=step),
        )[0]

    a1 = assignment(first, 1)
    side.clock.advance(timedelta(seconds=1))
    a2 = assignment(first, 2)
    b1 = assignment(second, 3)
    personal, _ = side.token(ann, "laptop", expires_in=timedelta(minutes=5))
    endless, _ = side.token(ann, "desk", expires_in=None)
    with side.uow() as uow:
        repo = uow.repo(TokenRepository)
        repo.save(revoke(repo.get_for_update(a2.id), worker, side.clock.now()))
        uow.commit()
    with side.uow(readonly=True) as uow:
        repo = uow.repo(TokenRepository)
        assert repo.for_assignment(first) == (a1,)
        assert [t.id for t in repo.for_assignment(second)] == [b1.id]
    start = side.clock.now()
    with side.uow() as uow:
        repo = uow.repo(TokenRepository)
        repo.touch(personal.id, start)
        repo.touch(personal.id, start + timedelta(seconds=30))  # throttled: within 60 s
        with pytest.raises(NotFound):
            repo.touch(TokenId(side.ids.new_id()), start)
    assert side.stored(personal.id).last_used_at is None  # the failed unit of work wrote nothing
    with side.uow() as uow:
        repo = uow.repo(TokenRepository)
        repo.touch(personal.id, start)
        repo.touch(personal.id, start + timedelta(seconds=30))
        uow.commit()
    assert side.stored(personal.id).last_used_at == start
    with side.uow() as uow:
        uow.repo(TokenRepository).touch(personal.id, start + timedelta(seconds=61))
        uow.commit()
    assert side.stored(personal.id).last_used_at == start + timedelta(seconds=61)
    side.clock.advance(timedelta(minutes=10))  # the personal token has expired by the backend clock
    with side.uow(readonly=True) as uow:
        repo = uow.repo(TokenRepository)
        assert [t.id for t in repo.list_for(ann, include_inactive=False, after=None, limit=10).items] == [
            endless.id
        ]
        everyone = repo.list_for(None, include_inactive=True, after=None, limit=2)
        rest = repo.list_for(None, include_inactive=True, after=everyone.next, limit=10)
        listed = [*everyone.items, *rest.items]
        assert listed == sorted(listed, key=lambda t: (t.created_at, str(t.id)))
        assert {t.id for t in listed} == {a1.id, a2.id, b1.id, personal.id, endless.id}
        worker_kind = repo.list_for(
            None, include_inactive=False, after=None, limit=10, kind=TokenKind.ASSIGNMENT
        )
        assert [t.id for t in worker_kind.items] == [a1.id, b1.id]
        if side.kind == "postgres":  # adapters §1.9 binds a PostgreSQL cursor to the filter that made it
            with pytest.raises(ValidationFailed) as foreign:
                repo.list_for(ann, include_inactive=False, after=everyone.next, limit=2)
            assert foreign.value.details["field"] == "after"


# ---------------------------------------------------------------------------------------------------------
# memberships


def test_memberships_upsert_replace_list_and_count_active_owners(side: Side) -> None:
    ann = side.principal("ann", roles={INSTANCE: Role.OWNER, WS: Role.MEMBER})
    bob = side.principal("bob", roles={INSTANCE: Role.OWNER})
    side.clock.advance(timedelta(seconds=1))
    cid = side.principal("cid", roles={INSTANCE: Role.MAINTAINER, P1: Role.VIEWER, WS2: Role.OWNER})
    with side.uow() as uow:
        repo = uow.repo(MembershipRepository)
        assert repo.count_active_owners(INSTANCE) == 2
        assert repo.count_active_owners(WS2) == 1
        assert repo.count_active_owners(WS) == 0
        uow.repo(PrincipalRepository).save(
            disable(uow.repo(PrincipalRepository).get(bob)), expected_version=1
        )
        assert repo.count_active_owners(INSTANCE) == 1  # disabled owners do not count
        repo.upsert(Membership(INSTANCE, cid, Role.OWNER, ann, side.clock.now()))
        assert repo.count_active_owners(INSTANCE) == 2
        repo.delete(INSTANCE, ann)
        repo.delete(INSTANCE, ann)  # deleting nothing is fine
        assert repo.count_active_owners(INSTANCE) == 1
        uow.commit()
    with side.uow(readonly=True) as uow:
        repo = uow.repo(MembershipRepository)
        assert repo.get(INSTANCE, ann) is None
        held = repo.get(INSTANCE, cid)
        assert held is not None
        assert (held.role, held.granted_by) == (Role.OWNER, ann)
        # one granted_at: the scope id breaks the tie
        assert [m.scope_id for m in repo.for_principal(cid, [P1, INSTANCE, WS])] == [INSTANCE, P1]
        assert repo.for_principal(cid, []) == ()
        assert repo.has_workspace_membership(ann)
        assert repo.has_workspace_membership(cid)
        assert not repo.has_workspace_membership(bob)
        listed = []
        after: str | None = None
        while True:
            page = repo.list(scope_id=None, principal_id=None, after=after, limit=2)
            listed.extend(page.items)
            if page.next is None:
                break
            after = page.next
        assert listed == sorted(listed, key=lambda m: (m.granted_at, str(m.scope_id), str(m.principal_id)))
        assert len(listed) == 5
        assert {
            m.principal_id for m in repo.list(scope_id=INSTANCE, principal_id=None, after=None, limit=9).items
        } == {
            bob,
            cid,
        }
        assert [
            m.scope_id for m in repo.list(scope_id=None, principal_id=ann, after=None, limit=9).items
        ] == [WS]


# ---------------------------------------------------------------------------------------------------------
# live reads (ACCESS-02)


@pytest.mark.parametrize("isolation", [Isolation.READ_COMMITTED, Isolation.REPEATABLE_READ])
def test_a_revoke_or_disable_committed_before_admission_is_seen(side: Side, isolation: Isolation) -> None:
    ann = side.principal("ann", roles={WS: Role.MEMBER})
    bob = side.principal("bob", roles={WS: Role.MEMBER})
    token, _ = side.token(ann, "laptop")
    other, _ = side.token(bob, "laptop")
    actor = replace(human(ann), grant=grant_of(token))
    peer = replace(human(bob), grant=grant_of(other))
    with side.uow(readonly=True, isolation=isolation) as uow:
        authz.ensure_live(uow, actor, side.clock.now())  # usable before the revoke
    with side.uow() as uow:
        repo = uow.repo(TokenRepository)
        repo.save(revoke(repo.get_for_update(token.id), ann, side.clock.now()))
        principals = uow.repo(PrincipalRepository)
        principals.save(disable(principals.get(bob)), expected_version=1)
        uow.commit()
    for refused in (actor, peer):
        with side.uow(readonly=True, isolation=isolation) as uow, pytest.raises(Unauthenticated):
            authz.ensure_live(uow, refused, side.clock.now())


# ---------------------------------------------------------------------------------------------------------
# PostgreSQL: snapshots, constraints and the runtime role


def _revoke_elsewhere(side: Side, token_id: TokenId, by: PrincipalId) -> None:
    with side.uow() as uow:
        repo = uow.repo(TokenRepository)
        repo.save(revoke(repo.get_for_update(token_id), by, side.clock.now()))
        uow.commit()


@pytest.mark.pg
def test_admission_sees_revokes_committed_before_its_statement_or_snapshot(pg_side: Side) -> None:
    ann = pg_side.principal("ann")
    tokens = [pg_side.token(ann, f"t{n}")[0] for n in range(3)]
    actors = [replace(human(ann), grant=grant_of(t)) for t in tokens]
    # READ COMMITTED: every statement reads what is committed when it starts, also late in a unit of work
    with pg_side.uow(readonly=True) as uow:
        authz.ensure_live(uow, actors[0], pg_side.clock.now())
        _revoke_elsewhere(pg_side, tokens[0].id, ann)
        with pytest.raises(Unauthenticated):
            authz.ensure_live(uow, actors[0], pg_side.clock.now())
    # REPEATABLE READ: the snapshot is taken by the first read, not when the unit of work opens
    with pg_side.uow(readonly=True, isolation=Isolation.REPEATABLE_READ) as uow:
        _revoke_elsewhere(pg_side, tokens[1].id, ann)
        with pytest.raises(Unauthenticated):
            authz.ensure_live(uow, actors[1], pg_side.clock.now())
    # an admitted snapshot may finish its read: a later revoke is not promised to abort it (access §4.6)
    with pg_side.uow(readonly=True, isolation=Isolation.REPEATABLE_READ) as uow:
        authz.ensure_live(uow, actors[2], pg_side.clock.now())
        _revoke_elsewhere(pg_side, tokens[2].id, ann)
        authz.ensure_live(uow, actors[2], pg_side.clock.now())
    with pg_side.uow(readonly=True) as uow, pytest.raises(Unauthenticated):
        authz.ensure_live(uow, actors[2], pg_side.clock.now())


_CONSTRAINTS = (
    "ck_api_tokens__kind",
    "ck_api_tokens__kind_expiry",
    "ck_api_tokens__assignment",
    "ck_api_tokens__step",
    "ck_api_tokens__assignment_scope",
    "ck_api_tokens__superseded",
    "ck_api_tokens__prefix",
    "ck_api_tokens__secret_hash",
    "ck_api_tokens__name",
    "ck_api_tokens__revoked",
    "ck_api_tokens__expiry",
    "uq_api_tokens__prefix",
    "fk_api_tokens__superseded_by",
)


@pytest.mark.pg
def test_the_migrated_schema_keeps_the_constraints_of_0006(pg_side: Side) -> None:
    rows = pg_side.execute_rows(
        "SELECT conname, condeferrable, condeferred FROM pg_constraint "
        "WHERE conrelid = 'skm_access.api_tokens'::regclass"
    )
    found = {row[0]: (row[1], row[2]) for row in rows}
    assert set(_CONSTRAINTS) <= set(found)
    assert found["fk_api_tokens__superseded_by"] == (True, True)
    indexes = {
        row[0]: row[1]
        for row in pg_side.execute_rows(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'skm_access' AND tablename = 'api_tokens'"
        )
    }
    assert (
        "WHERE ((revoked_at IS NULL) AND (superseded_by IS NULL))"
        in indexes["uq_api_tokens__principal_id_name_active"]
    )
    columns = {
        row[0]
        for row in pg_side.execute_rows(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'skm_access' AND table_name = 'api_tokens'"
        )
    }
    assert "step_id" in columns
    assert not {"secret", "token", "plaintext"} & columns  # only the peppered hash is stored


def _app_role(conn: psycopg.Connection) -> None:
    if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'skm_app'").fetchone() is None:
        pytest.skip("skm_app was not created: the test user can neither create roles nor see them")


@pytest.mark.pg
def test_the_adapters_work_as_the_runtime_role_and_cannot_bypass_constraints(pg_side: Side) -> None:
    ann = pg_side.principal("ann", roles={INSTANCE: Role.OWNER})
    worker = pg_side.principal("w", PrincipalKind.WORKER, {WS: Role.WORKER})
    with psycopg.connect(pg_side.dsn, connect_timeout=5) as conn:
        _app_role(conn)
        conn.execute("SET ROLE skm_app")
        tokens, principals = (
            PostgresTokenRepository(conn, clock=pg_side.clock),
            PostgresPrincipalRepository(conn),
        )
        memberships, identities = PostgresMembershipRepository(conn), PostgresIdentityRepository(conn)
        with conn.transaction():
            bob = pg_side.new_principal("bob")
            principals.add(bob)
            identities.add(PrincipalIdentity(bob.id, "local", "bob", pg_side.clock.now()))
            memberships.upsert(Membership(INSTANCE, bob.id, Role.OWNER, ann, pg_side.clock.now()))
            assert memberships.count_active_owners(INSTANCE) == 2  # advisory lock and row locks as skm_app
            token, _ = pg_side.new_token(bob.id, "laptop")
            tokens.add(token)
            tokens.save(revoke(tokens.get_for_update(token.id), ann, pg_side.clock.now()))
            principals.save(disable(bob), expected_version=1)
            assert tokens.list_for(bob.id, include_inactive=True, after=None, limit=5).items[0].revoked_at
        refusals: list[tuple[Callable[[], object], ErrorCode, str | None]] = [
            (lambda: tokens.add(pg_side.new_token(worker, "wrong-kind")[0]), ErrorCode.SCHEMA_INVALID, None),
            (
                lambda: tokens.add(pg_side.new_token(ann, "bad/name")[0]),
                ErrorCode.SCHEMA_INVALID,
                "ck_api_tokens__name",
            ),
            (
                lambda: tokens.add(pg_side.new_token(ann, "late", expires_in=timedelta(0))[0]),
                ErrorCode.SCHEMA_INVALID,
                "ck_api_tokens__expiry",
            ),
            (
                lambda: tokens.add(
                    replace(pg_side.new_token(PrincipalId(pg_side.ids.new_id()), "ghost")[0], created_by=ann)
                ),
                ErrorCode.INVALID_REFERENCE,
                "fk_api_tokens__principals",
            ),
            (
                lambda: memberships.upsert(
                    Membership(INSTANCE, worker, Role.WORKER, None, pg_side.clock.now())
                ),
                ErrorCode.SCHEMA_INVALID,
                None,
            ),
        ]
        for call, code, constraint in refusals:
            with pytest.raises(SkmError) as caught, conn.transaction():
                call()
            assert caught.value.code is code, caught.value
            assert caught.value.details.get("constraint") == constraint
        good, _ = pg_side.new_token(ann, "raw")
        insert = (
            "INSERT INTO skm_access.api_tokens (id, principal_id, kind, name, prefix, secret_hash, scope_id, "
            "expires_at, created_at, created_by, assignment_id, step_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        now = pg_side.clock.now()
        raw = [
            # an assignment token without its step, and a step on a personal token (ck_api_tokens__step)
            (
                pgerr.CheckViolation,
                "ck_api_tokens__step",
                (
                    UUID(int=7),
                    worker,
                    "assignment",
                    "a",
                    "aaaaaaab",
                    good.secret_hash,
                    RUN1,
                    now + timedelta(hours=1),
                    now,
                    worker,
                    UUID(int=1),
                    None,
                ),
            ),
            (
                pgerr.CheckViolation,
                "ck_api_tokens__step",
                (
                    UUID(int=8),
                    ann,
                    "personal",
                    "p",
                    "aaaaaaac",
                    good.secret_hash,
                    None,
                    None,
                    now,
                    ann,
                    None,
                    UUID(int=1),
                ),
            ),
            (
                pgerr.CheckViolation,
                "ck_api_tokens__prefix",
                (
                    UUID(int=9),
                    ann,
                    "personal",
                    "p",
                    "NOTBASE3",
                    good.secret_hash,
                    None,
                    None,
                    now,
                    ann,
                    None,
                    None,
                ),
            ),
            (
                pgerr.UniqueViolation,
                "uq_api_tokens__principal_id_name_active",
                (
                    UUID(int=10),
                    ann,
                    "personal",
                    "raw",
                    "aaaaaaad",
                    good.secret_hash,
                    None,
                    None,
                    now,
                    ann,
                    None,
                    None,
                ),
            ),
        ]
        with conn.transaction():
            conn.execute(
                insert,
                (
                    UUID(int=11),
                    ann,
                    "personal",
                    "raw",
                    "aaaaaaae",
                    good.secret_hash,
                    None,
                    None,
                    now,
                    ann,
                    None,
                    None,
                ),
            )
            for error, constraint, params in raw:
                with pytest.raises(error) as caught, conn.transaction():
                    conn.execute(insert, params)
                assert caught.value.diag.constraint_name == constraint
            raise psycopg.Rollback  # drop the raw row again
        for statement in (
            "ALTER TABLE skm_access.api_tokens DISABLE TRIGGER ALL",
            "SET session_replication_role = replica",
            "SELECT 1 FROM skm_core.scopes WHERE kind = 'instance' FOR UPDATE",
        ):
            with pytest.raises(pgerr.InsufficientPrivilege), conn.transaction():
                conn.execute(statement)  # pyright: ignore[reportArgumentType]


# ---------------------------------------------------------------------------------------------------------
# PostgreSQL: real concurrency


class HoldCommit(AbstractContextManager["HoldCommit"]):
    """A unit of work that stops before COMMIT until ``release`` is set."""

    def __init__(self, inner: UnitOfWork, reached: threading.Event, release: threading.Event) -> None:
        self._inner, self._reached, self._release = inner, reached, release

    @override
    def __enter__(self) -> Self:
        self._inner.__enter__()
        return self

    @override
    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._inner.__exit__(exc_type, exc, tb)

    def commit(self) -> None:
        self._reached.set()
        assert self._release.wait(15), "the held commit was never released"
        self._inner.commit()

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


class Run(threading.Thread):
    def __init__(self, call: Callable[[], object]) -> None:
        super().__init__(daemon=True)
        self._call = call
        self.result: object = None
        self.error: BaseException | None = None

    @override
    def run(self) -> None:
        try:
            self.result = self._call()
        except BaseException as exc:  # noqa: BLE001 - handed to the test thread
            self.error = exc


def _waiting_or_done(dsn: str, racer: Run) -> bool:
    """True when ``racer`` queues on a lock, False when it finished without waiting."""
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            row = conn.execute(
                "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                "WHERE NOT l.granted AND a.datname = current_database()"
            ).fetchone()
            if row is not None and cast("int", row[0]) > 0:
                return True
            if not racer.is_alive():
                return False
            time.sleep(0.02)
    raise AssertionError("the second command neither waited nor finished")


def race(side: Side, first: Callable[[Bus], object], second: Callable[[], object]) -> tuple[Run, Run, bool]:
    """Run ``first`` with its commit held, start ``second``, then let ``first`` commit."""
    reached, release = threading.Event(), threading.Event()

    def holding(meta: RequestMeta, **options: Any) -> UnitOfWork:
        return cast("UnitOfWork", HoldCommit(side.uow_factory(meta, **options), reached, release))

    holder = Run(lambda: first(side.bus(cast("UnitOfWorkFactory", holding))))
    holder.start()
    assert reached.wait(15), holder.error
    racer = Run(second)
    racer.start()
    try:
        waited = _waiting_or_done(side.dsn, racer)
    finally:
        release.set()
        holder.join(15)
        racer.join(15)
    assert holder.error is None, holder.error
    return holder, racer, waited


def _owners(side: Side) -> tuple[PrincipalId, PrincipalId]:
    return (
        side.principal("ann", roles={INSTANCE: Role.OWNER}),
        side.principal("bob", roles={INSTANCE: Role.OWNER}),
    )


def _remove(side: Side, how: str, actor: PrincipalId, target: PrincipalId, bus: Bus | None = None) -> object:
    if how == "revoke":
        dto: object = commands.RevokeMembership(scope_id=INSTANCE, principal_id=target)
    elif how == "demote":
        dto = commands.GrantMembership(scope_id=INSTANCE, principal_id=target, role=commands.Role.MAINTAINER)
    else:
        dto = commands.DisablePrincipal(principal_id=target, expected_row_version=1, reason="leaving")
    return side.run(dto, human(actor), bus=bus)


PAIRS = [
    ("revoke", "revoke"),
    ("disable", "disable"),
    ("revoke", "disable"),
    ("disable", "revoke"),
    ("demote", "disable"),
]


@pytest.mark.pg
@pytest.mark.parametrize(("first", "second"), PAIRS)
def test_two_concurrent_owner_removals_keep_an_active_owner(pg_side: Side, first: str, second: str) -> None:
    ann, bob = _owners(pg_side)
    _, racer, waited = race(
        pg_side,
        lambda bus: _remove(pg_side, first, ann, bob, bus),
        lambda: _remove(pg_side, second, bob, ann),
    )
    assert waited, "the second removal did not queue on the owner lock"
    assert isinstance(racer.error, PreconditionFailed), racer.error
    assert racer.error.code is ErrorCode.LAST_OWNER_REQUIRED
    assert pg_side.active_owners() == 1
    with pg_side.uow(readonly=True) as uow:
        assert uow.repo(PrincipalRepository).get(ann).state is PrincipalState.ACTIVE


@pytest.mark.pg
def test_the_owner_lock_alone_serializes_the_removals(pg_side: Side, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pg_access,
        "_ACTIVE_OWNERS",
        "SELECT count(*) FROM skm_access.memberships m JOIN skm_access.principals p ON p.id = m.principal_id "
        "WHERE m.scope_id = %s AND m.role = 'owner' AND p.state = 'active'",
    )
    ann, bob = _owners(pg_side)
    _, racer, waited = race(
        pg_side,
        lambda bus: _remove(pg_side, "disable", ann, bob, bus),
        lambda: _remove(pg_side, "disable", bob, ann),
    )
    assert waited
    assert isinstance(racer.error, PreconditionFailed), racer.error
    assert pg_side.active_owners() == 1


@pytest.mark.pg
@pytest.mark.parametrize("how", ["disable", "revoke"])
def test_control_without_the_owner_guards_the_race_loses_the_last_owner(
    pg_side: Side, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    """Negative control: the same interleaving with a plain count lets both removals commit."""
    monkeypatch.setattr(pg_access, "_OWNER_LOCK", "SELECT %s::int4 + %s::int4")
    monkeypatch.setattr(
        pg_access,
        "_ACTIVE_OWNERS",
        "SELECT count(*) FROM skm_access.memberships m JOIN skm_access.principals p ON p.id = m.principal_id "
        "WHERE m.scope_id = %s AND m.role = 'owner' AND p.state = 'active'",
    )
    ann, bob = _owners(pg_side)
    _, racer, waited = race(
        pg_side,
        lambda bus: _remove(pg_side, how, ann, bob, bus),
        lambda: _remove(pg_side, how, bob, ann),
    )
    assert not waited
    assert racer.error is None, racer.error
    assert pg_side.active_owners() == 0


def _rotate(side: Side, owner: PrincipalId, token_id: TokenId, bus: Bus | None = None) -> object:
    return side.run(commands.RotateToken(token_id=token_id, grace_minutes=5), human(owner), bus=bus)


def _revoke(side: Side, owner: PrincipalId, token_id: TokenId, bus: Bus | None = None) -> object:
    return side.run(commands.RevokeToken(token_id=token_id), human(owner), bus=bus)


@pytest.mark.pg
def test_parallel_rotations_of_one_token_give_exactly_one_successor(pg_side: Side) -> None:
    ann = pg_side.principal("ann", roles={WS: Role.MEMBER})
    token, _ = pg_side.token(ann, "laptop")
    pg_side.clock.advance(timedelta(minutes=1))
    holder, racer, waited = race(
        pg_side, lambda bus: _rotate(pg_side, ann, token.id, bus), lambda: _rotate(pg_side, ann, token.id)
    )
    assert waited, "the second rotation did not queue on the token row"
    assert isinstance(racer.error, PreconditionFailed), racer.error
    assert racer.error.code is ErrorCode.INVALID_TRANSITION
    successor = TokenId(cast("Any", holder.result).token_id)
    stored = pg_side.tokens_of(ann)
    assert {t.id for t in stored} == {token.id, successor}
    assert pg_side.stored(token.id).superseded_by == successor


@pytest.mark.pg
def test_a_revoke_and_a_rotation_queue_on_the_row_and_never_revive(pg_side: Side) -> None:
    ann = pg_side.principal("ann", roles={WS: Role.MEMBER})
    first, _ = pg_side.token(ann, "laptop")
    second, _ = pg_side.token(ann, "phone")
    pg_side.clock.advance(timedelta(minutes=1))
    # revoke first: the queued rotation sees the revocation and issues nothing
    _, racer, waited = race(
        pg_side, lambda bus: _revoke(pg_side, ann, first.id, bus), lambda: _rotate(pg_side, ann, first.id)
    )
    assert waited
    assert isinstance(racer.error, PreconditionFailed), racer.error
    assert racer.error.code is ErrorCode.INVALID_TRANSITION
    revoked = pg_side.stored(first.id)
    assert (revoked.revoked_by, revoked.superseded_by) == (ann, None)
    # rotate first: the queued revoke ends the superseded token and keeps its successor
    holder, racer, waited = race(
        pg_side, lambda bus: _rotate(pg_side, ann, second.id, bus), lambda: _revoke(pg_side, ann, second.id)
    )
    assert waited
    assert racer.error is None, racer.error
    successor = TokenId(cast("Any", holder.result).token_id)
    old = pg_side.stored(second.id)
    assert (old.superseded_by, old.revoked_by) == (successor, ann)
    assert pg_side.stored(successor).revoked_at is None
    assert {t.name for t in pg_side.tokens_of(ann) if t.revoked_at is None} == {"phone"}


@pytest.mark.pg
def test_the_loser_of_a_prefix_race_gets_a_conflict_and_a_usable_transaction(pg_side: Side) -> None:
    ann = pg_side.principal("ann")
    winner, _ = pg_side.new_token(ann, "one", prefix="mmmmmmmm")
    loser, _ = pg_side.new_token(ann, "two", prefix="mmmmmmmm")
    later, _ = pg_side.new_token(ann, "two")
    reached, release = threading.Event(), threading.Event()

    def hold() -> None:
        with pg_side.uow() as uow:
            uow.repo(TokenRepository).add(winner)
            reached.set()
            assert release.wait(15)
            uow.commit()

    def collide() -> str:
        with pg_side.uow() as uow:
            repo = uow.repo(TokenRepository)
            try:
                repo.add(loser)
            except Conflict as error:
                repo.add(later)  # draw again in the same transaction
                uow.commit()
                return cast("str", error.details["field"])
        return "inserted"

    holder = Run(hold)
    holder.start()
    assert reached.wait(15)
    racer = Run(collide)
    racer.start()
    try:
        assert _waiting_or_done(pg_side.dsn, racer)
    finally:
        release.set()
        holder.join(15)
        racer.join(15)
    assert (holder.error, racer.error, racer.result) == (None, None, "prefix")
    assert {t.id for t in pg_side.tokens_of(ann)} == {winner.id, later.id}


@pytest.mark.pg
def test_an_assignment_renewal_that_queues_behind_a_revoke_does_not_revive(pg_side: Side) -> None:
    worker = pg_side.principal("w", PrincipalKind.WORKER, {WS: Role.WORKER})
    pg_side.token(worker, "worker", kind=TokenKind.WORKER, expires_in=timedelta(days=1))
    assignment, step = UUID(int=0xA1), UUID(int=0xB1)
    token, _ = pg_side.token(
        worker,
        f"assignment-{assignment}-step-{step}",
        kind=TokenKind.ASSIGNMENT,
        scope_id=RUN1,
        permissions=frozenset({"run.read"}),
        expires_in=timedelta(minutes=10),
        assignment_id=assignment,
        step_id=step,
    )
    reached, release = threading.Event(), threading.Event()

    def revoke_held() -> None:
        with pg_side.uow() as uow:
            facade.revoke_assignment_tokens(uow, assignment_id=assignment, by=worker, now=pg_side.clock.now())
            reached.set()
            assert release.wait(15)
            uow.commit()

    def renew() -> object:
        with pg_side.uow() as uow:
            facade.extend_assignment_tokens(
                uow,
                assignment_id=assignment,
                expires_at=pg_side.clock.now() + timedelta(hours=1),
                now=pg_side.clock.now(),
            )
            uow.commit()
        return None

    holder = Run(revoke_held)
    holder.start()
    assert reached.wait(15)
    racer = Run(renew)
    racer.start()
    try:
        assert _waiting_or_done(pg_side.dsn, racer)
    finally:
        release.set()
        holder.join(15)
        racer.join(15)
    assert holder.error is None, holder.error
    assert racer.error is None, racer.error
    stored = pg_side.stored(token.id)
    assert stored.revoked_at is not None
    assert stored.revoked_by == worker


@pytest.mark.pg
def test_access_credential_acl_as_skm_app(pg_side: Side) -> None:
    principal = pg_side.principal("local owner", roles={INSTANCE: Role.OWNER})
    now = pg_side.clock.now()
    token, _ = pg_side.new_token(principal, "immutable")
    session_id = pg_side.ids.new_id()
    pairing_id = pg_side.ids.new_id()
    with psycopg.connect(pg_side.dsn, connect_timeout=5) as conn:
        _app_role(conn)
        conn.execute("SET ROLE skm_app")
        tokens = PostgresTokenRepository(conn, clock=pg_side.clock)
        principals = PostgresPrincipalRepository(conn, clock=pg_side.clock)
        tokens.add(token)
        assert principals.set_first_password(principal, bytes(48))
        assert not principals.set_first_password(principal, b"!" * 48)
        conn.execute(
            "INSERT INTO skm_access.web_sessions (id, principal_id, secret_hash, created_at, expires_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (session_id, principal, bytes(32), now, now + timedelta(hours=1)),
        )
        conn.execute(
            "INSERT INTO skm_access.pairing_tokens "
            "(id, issuer_id, issuer_token_id, workspace_id, secret_hash, binding, created_at, expires_at) "
            "VALUES (%s, %s, %s, %s, %s, '{}'::jsonb, %s, %s)",
            (pairing_id, principal, token.id, WS, bytes(32), now, now + timedelta(minutes=5)),
        )
        for statement, row_id in (
            ("UPDATE skm_access.api_tokens SET scope_grants = '{}'::jsonb WHERE id = %s", token.id),
            ("UPDATE skm_access.web_sessions SET principal_id = NULL WHERE id = %s", session_id),
            ("UPDATE skm_access.pairing_tokens SET workspace_id = NULL WHERE id = %s", pairing_id),
            ("DELETE FROM skm_access.api_tokens WHERE id = %s", token.id),
        ):
            with pytest.raises(pgerr.InsufficientPrivilege), conn.transaction():
                conn.execute(cast("LiteralString", statement), (row_id,))
        for revoke_sql, row_id in (
            ("UPDATE skm_access.web_sessions SET revoked_at = %s WHERE id = %s", session_id),
            ("UPDATE skm_access.pairing_tokens SET revoked_at = %s WHERE id = %s", pairing_id),
        ):
            changed = conn.execute(cast("LiteralString", revoke_sql), (now, row_id))
            assert changed.rowcount == 1
        with pytest.raises(pgerr.CheckViolation), conn.transaction():
            conn.execute("UPDATE skm_access.web_sessions SET revoked_at = NULL WHERE id = %s", (session_id,))
        conn.execute("RESET ROLE")
        with pytest.raises(pgerr.CheckViolation), conn.transaction():
            conn.execute("UPDATE skm_access.api_tokens SET permissions = '{}' WHERE id = %s", (token.id,))
