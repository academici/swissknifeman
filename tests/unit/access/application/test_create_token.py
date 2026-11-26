"""``access.create_token`` through the bus on the memory backend (access §7.3, §4.5, §15).

The harness is the vertical slice of the access handlers: the real bus, the real ``ConfigLoader`` over the
packaged ``access`` section, the memory access repositories and the real ``authenticate_token``. The bus
authorizer is a thin test double over ``authz.decision`` (not the production ``RbacAuthorizer``), so
``token.own`` and the grant gates behave as ``decide`` defines them. The other test files of this
directory load
the harness with ``run_path``.

Invariants: the secret is in the one result and nowhere else (events, audit, receipts, repositories); a
refused command writes nothing; a restricted bearer never mints a credential beyond its own grant.
"""

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.access import REPOSITORIES as ACCESS_REPOSITORIES
from skm.adapters.memory.access.state import access_state
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core import REPOSITORIES as CORE_REPOSITORIES
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.memory.workspace import REPOSITORIES as WORKSPACE_REPOSITORIES
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import Authorizer, AuthzDecision
from skm.application_bus.registry import BusRegistry
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, PrincipalId, ScopeId, WorkerId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.application import authz
from skm.modules.access.domain.authorization import Allowed, Denied
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import (
    ApiToken,
    TokenId,
    TokenKind,
    generate_secret,
    hash_secret,
    parse_secret,
)
from skm.modules.access.generated import commands, queries
from skm.modules.access.module import MODULE
from skm.modules.access.permissions import PERMISSIONS as CATALOG
from skm.modules.access.ports import (
    MembershipRepository,
    PrincipalRepository,
    TokenPepperSource,
    TokenRepository,
)
from skm.modules.access.public import authenticate_token
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource
from support.registries import schemas, settings_registry

PEPPER = bytes(range(32))
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
SECRET_FORMAT = re.compile(r"^skm_live_[a-z2-7]{8}_[A-Za-z0-9_-]{43}_[0-9a-f]{8}$")


def sid(n: int) -> ScopeId:
    return ScopeId(UUID(f"01900000-0000-7000-8000-{n:012x}"))


INSTANCE, WS, P1, P2, PLAN1, RUN1, WS2, P3 = (sid(n) for n in (1, 0xA1, 0xC1, 0xC2, 0xD1, 0xE1, 0xA2, 0xC3))
EVERYTHING = frozenset(CATALOG)


class FixedPepper:
    def pepper(self) -> bytes:
        return PEPPER


class DomainAuthorizer:
    """Bus ``Authorizer`` double: the access ``decide`` over the facts of the request's unit of work."""

    def authorize(self, uow: Any, actor: Actor, permission: str | None, chain: Any) -> AuthzDecision:
        if permission is None:
            return AuthzDecision(allowed=True)
        verdict = authz.decision(uow, actor, permission, chain)
        if isinstance(verdict, Allowed):
            return AuthzDecision(allowed=True)
        assert isinstance(verdict, Denied)
        return AuthzDecision(allowed=False, reason_code=authz.BUS_REASON[verdict.reason])


class Packs:
    def generation(self) -> int:
        return 0

    def fragments(self, scope_chain: object) -> tuple[()]:
        return ()


@dataclass
class Harness:
    backend: InMemoryBackend
    bus: Bus
    clock: FrozenClock
    ids: SequentialIds
    entropy: DeterministicEntropy
    counter: int = 0
    secrets: dict[str, str] = field(default_factory=dict[str, str])  # label -> plaintext, test side only

    # ------------------------------------------------------------------ requests
    def meta(self, key: str | None = None) -> RequestMeta:
        self.counter += 1
        return RequestMeta(f"req_{self.counter:0>26}", Surface.TEST, key, self.clock.now())

    def run(self, dto: object, actor: Actor, *, key: str | None = None) -> Any:
        return self.bus.dispatch(dto, actor=actor, meta=self.meta(key))

    def ask(self, dto: object, actor: Actor) -> Any:
        return self.bus.ask(dto, actor=actor, meta=self.meta())

    def uow(self, *, readonly: bool = False) -> Any:
        return self.backend.uow_factory()(self.meta(), readonly=readonly)

    # ------------------------------------------------------------------ seeding (domain values, no bus)
    def principal(
        self,
        name: str,
        kind: PrincipalKind = PrincipalKind.HUMAN,
        roles: Mapping[ScopeId, Role] | None = None,
    ) -> PrincipalId:
        with self.uow() as uow:
            principal = new_principal(
                principal_id=PrincipalId(self.ids.new_id()),
                kind=kind,
                display_name=name,
                created_by=None,
                now=self.clock.now(),
            )
            uow.repo(PrincipalRepository).add(principal)
            for scope_id, role in (roles or {}).items():
                uow.repo(MembershipRepository).upsert(
                    Membership(scope_id, principal.id, role, None, self.clock.now())
                )
            uow.commit()
        return principal.id

    def bind_worker(self, worker: PrincipalId, workspace: ScopeId) -> None:
        from skm.modules.workspace.domain.host import HostArch, HostOs, HostPlatform
        from skm.modules.workspace.domain.worker import WorkerCapabilities, new_worker
        from skm.modules.workspace.ports import WorkerRepository

        with self.uow() as uow:
            uow.repo(WorkerRepository).add(
                new_worker(
                    worker_id=WorkerId(self.ids.new_id()),
                    workspace_id=WorkspaceId(workspace),
                    host_id=HostId(self.ids.new_id()),
                    principal_id=worker,
                    display_name="test worker",
                    capabilities=WorkerCapabilities(
                        (), ("worktree",), 1, (), HostPlatform(HostOs.LINUX, HostArch.X86_64), "0.1.0"
                    ),
                    now=self.clock.now(),
                )
            )
            uow.commit()

    def token(
        self,
        label: str,
        owner: PrincipalId,
        *,
        kind: TokenKind = TokenKind.PERSONAL,
        scope_id: ScopeId | None = None,
        permissions: Iterable[str] | None = None,
        expires_in: timedelta | None = timedelta(days=30),
        name: str | None = None,
        assignment_id: UUID | None = None,
        step_id: UUID | None = None,
    ) -> TokenId:
        secret = generate_secret(self.entropy.bytes)
        token_id = TokenId(self.ids.new_id())
        now = self.clock.now()
        with self.uow() as uow:
            uow.repo(TokenRepository).add(
                ApiToken(
                    id=token_id,
                    principal_id=owner,
                    kind=kind,
                    name=name or label,
                    prefix=secret.prefix,
                    secret_hash=hash_secret(secret, PEPPER),
                    scope_id=scope_id,
                    permissions=None if permissions is None else frozenset(permissions),
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
            )
            uow.commit()
        self.secrets[label] = str(secret)
        return token_id

    def actor(self, label_or_secret: str) -> Actor:
        """The real ``authenticate_token`` of a stored secret (by label) or of a secret text."""
        text = self.secrets.get(label_or_secret, label_or_secret)
        with self.uow(readonly=True) as uow:
            return authenticate_token(uow, text, pepper=PEPPER, now=self.clock.now())

    # ------------------------------------------------------------------ observations
    @property
    def tokens(self) -> dict[TokenId, ApiToken]:
        return dict(access_state(self.backend.committed).tokens)

    @property
    def events(self) -> list[Any]:
        return list(self.backend.committed.core.events)

    @property
    def audits(self) -> list[Any]:
        return list(self.backend.committed.core.audit)

    @property
    def receipts(self) -> list[Any]:
        return list(self.backend.committed.core.idempotency.values())

    def snapshot(self) -> tuple[object, ...]:
        """Everything a refused command must leave untouched."""
        committed = self.backend.committed
        tables = access_state(committed)
        return (
            dict(tables.tokens),
            dict(tables.principals),
            dict(tables.memberships),
            dict(tables.identities),
            len(committed.core.events),
        )

    def stored_text(self) -> str:
        """Every string the system keeps: tables, events, audit, receipts (for the no-leak checks)."""
        committed = self.backend.committed
        tables = access_state(committed)
        return "\n".join(
            [
                repr(tables),
                json.dumps([e.payload for e in committed.core.events], default=str),
                repr(committed.core.audit),
                repr(list(committed.core.idempotency.values())),
                repr(list(committed.core.outbox.values())),
            ]
        )


def harness(*, config: Mapping[str, Any] | None = None) -> Harness:
    del config
    bus_registry = BusRegistry.build(
        (MODULE,), schemas=schemas(), permission_catalog=EVERYTHING, disabled_modules=frozenset()
    )
    authorizer = DomainAuthorizer()
    packs = Packs()
    factories: dict[type, Any] = {
        **CORE_REPOSITORIES,
        **ACCESS_REPOSITORIES,
        **WORKSPACE_REPOSITORIES,
        ConfigStore: MemoryConfigStore,
        PackConfigSource: lambda _state: packs,
        Authorizer: lambda _state: authorizer,
    }
    clock, ids, entropy = FrozenClock(NOW), SequentialIds(), DeterministicEntropy()
    backend = InMemoryBackend(
        factories=factories,
        schemas=schemas(),
        subscriptions=bus_registry.subscription_index(),
        ids=ids,
        clock=clock,
    )
    bus = Bus(
        registry=bus_registry,
        schemas=schemas(),
        uow_factory=backend.uow_factory(),
        authorizer=authorizer,
        scopes=FakeScopeChain(),
        config=ConfigLoader(settings_registry(), packs),
        clock=clock,
        ids=ids,
        entropy=entropy,
        gateways=GatewayTable({TokenPepperSource: FixedPepper()}, "control_plane_gateway"),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )
    made = Harness(backend, bus, clock, ids, entropy)
    with made.uow() as uow:
        scopes = uow.repo(ScopeRegistry)
        ws, ws2 = WorkspaceId(WS), WorkspaceId(WS2)
        scopes.create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        scopes.create(WS, ScopeKind.WORKSPACE, parent=INSTANCE, workspace_id=ws)
        scopes.create(P1, ScopeKind.PROJECT, parent=WS, workspace_id=ws)
        scopes.create(P2, ScopeKind.PROJECT, parent=WS, workspace_id=ws)
        scopes.create(PLAN1, ScopeKind.PLAN, parent=P1, workspace_id=ws)
        scopes.create(RUN1, ScopeKind.RUN, parent=PLAN1, workspace_id=ws)
        scopes.create(WS2, ScopeKind.WORKSPACE, parent=INSTANCE, workspace_id=ws2)
        scopes.create(P3, ScopeKind.PROJECT, parent=WS2, workspace_id=ws2)
        uow.commit()
    return made


def world() -> dict[str, Any]:
    """An instance owner and three workspace people, each with one personal token."""
    made = harness()
    owner = made.principal("owner", roles={INSTANCE: Role.OWNER})
    alice = made.principal("alice", roles={WS: Role.MEMBER})
    bob = made.principal("bob", roles={WS: Role.VIEWER})
    made.token("owner", owner)
    made.token("alice", alice)
    made.token("bob", bob)
    return {"h": made, "owner": owner, "alice": alice, "bob": bob}


def refused(made: Harness, dto: object, actor: Actor, code: ErrorCode) -> SkmError:
    """Run ``dto``, expect ``code`` and prove that nothing was written."""
    before = made.snapshot()
    with pytest.raises(SkmError) as caught:
        made.run(dto, actor)
    assert caught.value.code is code, caught.value
    assert made.snapshot() == before
    return caught.value


def create(name: str, **fields: Any) -> commands.CreateToken:
    return commands.CreateToken(name=name, **fields)


# ---------------------------------------------------------------------------------------------------------
# the secret appears once


def test_the_secret_is_in_the_result_only() -> None:
    w = world()
    made: Harness = w["h"]
    result = made.run(create("laptop"), made.actor("alice"))
    assert SECRET_FORMAT.fullmatch(result.secret)
    assert result.prefix == parse_secret(result.secret).prefix
    stored = made.tokens[TokenId(result.token_id)]
    secret = parse_secret(result.secret)
    assert stored.secret_hash == hash_secret(secret, PEPPER)
    assert (stored.kind, stored.principal_id, stored.name) == (TokenKind.PERSONAL, w["alice"], "laptop")
    assert secret.random not in made.stored_text()
    [created] = [e for e in made.events if e.type == "urn:skm:access:event:token-created:v1"]
    assert created.payload["token_id"] == str(result.token_id)
    assert set(created.payload) == {
        "token_id",
        "principal_id",
        "kind",
        "name",
        "prefix",
        "scope_id",
        "expires_at",
    }
    assert (created.stream_kind, created.stream_id, created.workspace_id) == ("principal", w["alice"], None)
    assert made.receipts == []
    assert made.actor(result.secret).principal_id == w["alice"]  # and it works once handed over


def test_an_idempotency_key_is_refused_and_nothing_is_stored() -> None:
    w = world()
    made: Harness = w["h"]
    before = made.snapshot()
    with pytest.raises(SkmError) as caught:
        made.run(create("laptop"), made.actor("alice"), key="retry-1")
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["reason"] == "not_idempotent"
    assert made.snapshot() == before
    assert made.receipts == []


def test_a_new_token_gets_the_default_lifetime_and_an_explicit_one_is_bounded() -> None:
    w = world()
    made: Harness = w["h"]
    alice = made.actor("alice")
    assert made.run(create("a"), alice).expires_at == NOW + timedelta(days=90)
    assert made.run(create("b", expires_at=NOW + timedelta(days=7)), alice).expires_at == NOW + timedelta(
        days=7
    )
    error = refused(made, create("c", expires_at=NOW + timedelta(days=400)), alice, ErrorCode.SCHEMA_INVALID)
    assert error.details["reason"] == "exceeds_max_ttl"


def test_a_taken_name_is_already_exists_and_a_revoked_name_is_free() -> None:
    w = world()
    made: Harness = w["h"]
    alice = made.actor("alice")
    first = made.run(create("ci"), alice)
    refused(made, create("ci"), alice, ErrorCode.ALREADY_EXISTS)
    made.run(commands.RevokeToken(token_id=first.token_id), alice)
    assert made.run(create("ci"), alice).token_id != first.token_id


# ---------------------------------------------------------------------------------------------------------
# permissions of the new token


def test_permissions_wider_than_the_creator_are_forbidden() -> None:
    w = world()
    made: Harness = w["h"]
    bob = made.actor("bob")  # viewer
    error = refused(made, create("w", scope_id=WS, permissions=("plan.edit",)), bob, ErrorCode.FORBIDDEN)
    assert error.details["permission"] == "plan.edit"
    ok = made.run(create("r", scope_id=WS, permissions=("plan.read", "token.own")), bob)
    assert made.tokens[TokenId(ok.token_id)].permissions == {"plan.read", "token.own"}


def test_explicit_permissions_are_checked_where_the_token_acts() -> None:
    """A null scope is the instance (access §7.3): a workspace-only member does not hold plan.read there."""
    w = world()
    made: Harness = w["h"]
    error = refused(made, create("i", permissions=("plan.read",)), made.actor("bob"), ErrorCode.FORBIDDEN)
    assert error.details["permission"] == "plan.read"
    assert error.details["reason"] == "no_membership"


def test_credential_rights_in_a_token_need_an_instance_owner() -> None:
    w = world()
    made: Harness = w["h"]
    error = refused(
        made, create("m", permissions=("membership.manage",)), made.actor("alice"), ErrorCode.FORBIDDEN
    )
    assert error.details["permission"] == "membership.manage"
    owner = made.run(create("m", permissions=("membership.manage", "token.own")), made.actor("owner"))
    assert "membership.manage" in made.tokens[TokenId(owner.token_id)].permissions  # type: ignore[operator]


def test_an_unknown_permission_is_refused_before_a_secret_exists() -> None:
    w = world()
    made: Harness = w["h"]
    alice = made.actor("alice")
    drawn = len(made.entropy.requested)
    error = refused(made, create("u", permissions=("plan.teleport",)), alice, ErrorCode.SCHEMA_INVALID)
    assert error.details["permission"] == "plan.teleport"
    assert len(made.entropy.requested) == drawn  # the refused request drew no secret


def test_a_scoped_token_is_limited_to_its_scope() -> None:
    w = world()
    made: Harness = w["h"]
    result = made.run(create("p1", scope_id=P1), made.actor("alice"))
    assert made.tokens[TokenId(result.token_id)].scope_id == P1
    [created] = [e for e in made.events if e.type.endswith("token-created:v1")]
    assert created.workspace_id == WS  # the event belongs to the workspace feed of its scope
    refused(made, create("far", scope_id=sid(0xFFFF)), made.actor("alice"), ErrorCode.NOT_FOUND)


# ---------------------------------------------------------------------------------------------------------
# another principal


def test_a_token_for_someone_else_needs_token_any() -> None:
    w = world()
    made: Harness = w["h"]
    error = refused(made, create("x", principal_id=w["bob"]), made.actor("alice"), ErrorCode.FORBIDDEN)
    assert error.details["permission"] == "token.any"
    result = made.run(create("x", principal_id=w["bob"]), made.actor("owner"))
    stored = made.tokens[TokenId(result.token_id)]
    assert (stored.principal_id, stored.created_by) == (w["bob"], w["owner"])
    [created] = [e for e in made.events if e.type.endswith("token-created:v1")]
    assert created.stream_id == w["bob"]


def test_no_token_for_a_worker_or_a_disabled_principal() -> None:
    w = world()
    made: Harness = w["h"]
    worker = made.principal("w1", PrincipalKind.WORKER, {WS: Role.WORKER})
    error = refused(made, create("t", principal_id=worker), made.actor("owner"), ErrorCode.FORBIDDEN)
    assert error.details["reason"] == "worker_tokens_are_rotated"
    made.run(
        commands.DisablePrincipal(principal_id=w["bob"], expected_row_version=1, reason="left"),
        made.actor("owner"),
    )
    error = refused(
        made, create("t", principal_id=w["bob"]), made.actor("owner"), ErrorCode.INVALID_TRANSITION
    )
    assert error.details["reason"] == "principal_disabled"


# ---------------------------------------------------------------------------------------------------------
# delegation is closed (access §4.5, ench3)


def restricted(made: Harness, owner: PrincipalId, *, scope: ScopeId, permissions: Iterable[str]) -> Actor:
    made.token("bearer", owner, scope_id=scope, permissions=permissions, name="bearer")
    return made.actor("bearer")


def test_a_scoped_bearer_cannot_mint_an_instance_or_sibling_credential() -> None:
    w = world()
    made: Harness = w["h"]
    bearer = restricted(made, w["alice"], scope=P1, permissions={"token.own", "plan.read", "plan.edit"})
    error = refused(
        made, create("up"), bearer, ErrorCode.FORBIDDEN
    )  # scope null is the instance, not "inherit"
    assert error.details["reason"] == "token_scope_mismatch"
    refused(made, create("side", scope_id=P2), bearer, ErrorCode.FORBIDDEN)
    refused(made, create("wide", scope_id=WS), bearer, ErrorCode.FORBIDDEN)
    refused(made, create("other", scope_id=P3), bearer, ErrorCode.FORBIDDEN)
    refused(made, create("same-principal-up", principal_id=w["alice"]), bearer, ErrorCode.FORBIDDEN)
    child = made.run(create("down", scope_id=PLAN1), bearer)  # inside the bearer's scope
    assert made.tokens[TokenId(child.token_id)].scope_id == PLAN1


def test_null_permissions_keep_the_ceiling_and_an_explicit_one_is_checked_with_the_grant() -> None:
    w = world()
    made: Harness = w["h"]
    bearer = restricted(made, w["alice"], scope=P1, permissions={"token.own", "plan.read"})
    inherited = made.run(create("c1", scope_id=PLAN1), bearer)  # permissions=null
    assert made.tokens[TokenId(inherited.token_id)].permissions == {"token.own", "plan.read"}
    error = refused(
        made, create("c2", scope_id=PLAN1, permissions=("plan.edit",)), bearer, ErrorCode.FORBIDDEN
    )
    assert error.details["reason"] == "token_permission_missing"  # alice may edit plans; the grant may not
    narrower = made.run(create("c3", scope_id=PLAN1, permissions=("plan.read",)), bearer)
    assert made.tokens[TokenId(narrower.token_id)].permissions == {"plan.read"}


def test_default_permissions_freeze_the_live_rights_at_the_scope() -> None:
    w = world()
    made: Harness = w["h"]
    result = made.run(create("plain"), made.actor("alice"))
    assert made.tokens[TokenId(result.token_id)].permissions == {"token.own"}


def test_create_then_rotate_never_replaces_a_bearer_by_a_stronger_one() -> None:
    w = world()
    made: Harness = w["h"]
    bearer = restricted(made, w["alice"], scope=P1, permissions={"token.own", "plan.read"})
    child = made.run(create("kid", scope_id=PLAN1), bearer)
    kid = made.actor(child.secret)
    rotated = made.run(commands.RotateToken(token_id=child.token_id), kid)
    successor = made.tokens[TokenId(rotated.token_id)]
    assert (successor.scope_id, successor.permissions) == (PLAN1, frozenset({"token.own", "plan.read"}))
    assert made.actor(rotated.secret).grant.scope_id == PLAN1  # type: ignore[union-attr]


# ---------------------------------------------------------------------------------------------------------
# revoke_token shares the owner rules


def test_revoke_own_token_from_a_workspace_role_and_revoke_again_is_a_no_op() -> None:
    w = world()
    made: Harness = w["h"]
    alice = made.actor("alice")
    first = made.run(create("x"), alice)
    done = made.run(commands.RevokeToken(token_id=first.token_id), alice)
    assert done.revoked_at == NOW
    events = len(made.events)
    again = made.run(commands.RevokeToken(token_id=first.token_id), alice)
    assert again.revoked_at == NOW
    assert len(made.events) == events  # no second event
    [revoked] = [e for e in made.events if e.type.endswith("token-revoked:v1")]
    assert revoked.payload["revoked_by"] == str(w["alice"])


def test_revoke_of_someone_elses_token_needs_token_any() -> None:
    w = world()
    made: Harness = w["h"]
    bobs = made.run(create("b"), made.actor("bob"))
    error = refused(
        made, commands.RevokeToken(token_id=bobs.token_id), made.actor("alice"), ErrorCode.FORBIDDEN
    )
    assert error.details["permission"] == "token.any"
    assert made.tokens[TokenId(bobs.token_id)].revoked_at is None
    made.run(commands.RevokeToken(token_id=bobs.token_id), made.actor("owner"))
    assert made.tokens[TokenId(bobs.token_id)].revoked_by == w["owner"]


def test_a_worker_revokes_only_the_token_it_authenticates_with() -> None:
    w = world()
    made: Harness = w["h"]
    worker = made.principal("w1", PrincipalKind.WORKER, {WS: Role.WORKER})
    current = made.token("w-current", worker, kind=TokenKind.WORKER, expires_in=timedelta(hours=100))
    other = made.token("w-other", worker, kind=TokenKind.WORKER, expires_in=timedelta(hours=100))
    actor = made.actor("w-current")
    error = refused(made, commands.RevokeToken(token_id=other), actor, ErrorCode.FORBIDDEN)
    assert error.details["reason"] == "not_current_token"
    made.run(commands.RevokeToken(token_id=current), actor)
    assert made.tokens[current].revoked_at == NOW


def test_queries_never_return_a_hash_or_a_secret() -> None:
    w = world()
    made: Harness = w["h"]
    made.run(create("q"), made.actor("alice"))
    page = made.ask(queries.ListTokens(include_inactive=True), made.actor("alice"))
    assert {t.name for t in page.items} >= {"alice", "q"}
    text = json.dumps(page.to_json())
    for token in made.tokens.values():
        assert token.secret_hash.hex() not in text
    assert "skm_" not in text
