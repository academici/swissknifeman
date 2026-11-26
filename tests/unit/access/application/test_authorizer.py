"""``RbacAuthorizer`` as the bus authorizer of the access module (access §4.4-§4.6, §13, §15).

The harness is the vertical slice of ``test_create_token.py`` (real bus, real ``ConfigLoader``, memory access
repositories, real ``authenticate_token``) with its test double replaced by the production authorizer and the
production scope-chain resolver. Matrix: the verdict of the pure ``decide`` table reaches the bus unchanged
(allowed / denied with the reason code the audit keeps), every denial writes its audit after the rollback and
leaves no state behind, a token never widens its principal, a disabled principal / unusable credential /
forged ``Actor`` is ``UNAUTHENTICATED`` and not a permission decision, the registered permissions are all in
the catalog, and the ``SYSTEM_ACTOR`` exception exists only for system permissions.
"""

from datetime import timedelta
from pathlib import Path
from runpy import run_path
from typing import Any, cast
from uuid import UUID

import pytest

from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import AuthzDecision
from skm.application_bus.registry import AnyCommandSpec, AnyQuerySpec, BusRegistry
from skm.bootstrap.composition import StoredScopeChain
from skm.bootstrap.modules import MANIFESTS
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind, TokenGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, SkmError, Unauthenticated
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import PrincipalId
from skm.kernel.scopes import ScopeKind, ScopeRecord
from skm.modules.access.application.authorizer import RbacAuthorizer
from skm.modules.access.domain.principal import disable
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import TokenKind
from skm.modules.access.generated import commands, queries
from skm.modules.access.permissions import PERMISSIONS
from skm.modules.access.ports import PrincipalRepository, TokenPepperSource
from skm.modules.access.public import SYSTEM_ACTOR
from skm.modules.access.public import RbacAuthorizer as PublicRbacAuthorizer

h: dict[str, Any] = run_path(str(Path(__file__).with_name("test_create_token.py")))
INSTANCE, WS, WS2, P1 = h["INSTANCE"], h["WS"], h["WS2"], h["P1"]
NOW = h["NOW"]


def rbac_harness(*, wrap: Any = None, uow_factory: Any = None) -> Any:
    """The create-token harness whose bus authorizes with ``RbacAuthorizer`` over the stored scope chain.

    ``wrap`` decorates the authorizer and ``uow_factory`` replaces the unit-of-work factory (live-revocation
    tests observe admission through them).
    """
    made = h["harness"]()
    authorizer = RbacAuthorizer(made.clock)
    bus_registry = BusRegistry.build(
        (h["MODULE"],),
        schemas=h["schemas"](),
        permission_catalog=h["EVERYTHING"],
        disabled_modules=frozenset(),
    )
    made.bus = Bus(
        registry=bus_registry,
        schemas=h["schemas"](),
        uow_factory=made.backend.uow_factory() if uow_factory is None else uow_factory(made),
        authorizer=authorizer if wrap is None else wrap(authorizer, made),
        scopes=StoredScopeChain(),
        config=h["ConfigLoader"](h["settings_registry"](), h["Packs"]()),
        clock=made.clock,
        ids=made.ids,
        entropy=made.entropy,
        gateways=GatewayTable({TokenPepperSource: h["FixedPepper"]()}, "control_plane_gateway"),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )
    return made


def world(**options: Any) -> dict[str, Any]:
    made = rbac_harness(**options)
    people = {
        "owner": made.principal("owner", roles={INSTANCE: Role.OWNER}),
        "member": made.principal("member", roles={WS: Role.MEMBER}),
        "viewer": made.principal("viewer", roles={WS: Role.VIEWER}),
        "nobody": made.principal("nobody"),
    }
    for label, principal_id in people.items():
        made.token(label, principal_id)
    return {"h": made, **people}


def refused(made: Any, dto: object, actor: Actor, code: ErrorCode) -> SkmError:
    run = made.ask if hasattr(queries, type(dto).__name__) else made.run
    with pytest.raises(SkmError) as caught:
        run(dto, actor)
    assert caught.value.code is code
    return caught.value


def denied_audits(made: Any) -> list[Any]:
    return [row for row in made.audits if row.decision == "denied"]


def create_principal(name: str = "newcomer") -> commands.CreatePrincipal:
    return commands.CreatePrincipal.from_json({"kind": "human", "display_name": name})


def grant(scope: UUID, principal: UUID, role: str = "viewer") -> commands.GrantMembership:
    return commands.GrantMembership.from_json(
        {"scope_id": str(scope), "principal_id": str(principal), "role": role}
    )


def break_principal(made: Any, principal_id: PrincipalId) -> None:
    with made.uow() as uow:
        repo = uow.repo(PrincipalRepository)
        current = repo.get(principal_id)
        repo.save(disable(current), expected_version=current.row_version)
        uow.commit()


# ------------------------------------------------------------------------------------------ the verdict


def test_the_public_name_is_the_production_authorizer() -> None:
    assert PublicRbacAuthorizer is RbacAuthorizer


def test_an_owner_is_allowed_and_the_allowed_audit_is_written_with_the_command() -> None:
    w = world()
    made = w["h"]
    result = made.run(create_principal(), made.actor("owner"))
    assert made.audits[-1].decision == "allowed"
    assert made.audits[-1].action == "access.create_principal"
    assert made.audits[-1].actor_id == w["owner"]
    assert result.principal_id is not None


def test_a_viewer_write_is_refused_and_the_denial_is_audited_without_a_trace_of_the_command() -> None:
    w = world()
    made = w["h"]
    before = made.snapshot()
    error = refused(made, grant(WS, w["nobody"]), made.actor("viewer"), ErrorCode.FORBIDDEN)
    assert isinstance(error, Forbidden)
    assert error.details["reason_code"] == "ROLE_LACKS_PERMISSION"
    assert error.details["permission"] == "membership.manage"
    assert made.snapshot() == before  # the command UoW was rolled back
    [row] = denied_audits(made)
    assert (row.actor_id, row.action, row.reason_code) == (
        w["viewer"],
        "access.grant_membership",
        "ROLE_LACKS_PERMISSION",
    )
    assert row.target["permission"] == "membership.manage"
    assert row.target["scope"]["id"] == str(WS)


def test_no_membership_on_the_chain_is_a_denial_with_its_own_reason() -> None:
    w = world()
    made = w["h"]
    error = refused(made, create_principal(), made.actor("member"), ErrorCode.FORBIDDEN)
    assert error.details["reason_code"] == "NO_MEMBERSHIP"
    [row] = denied_audits(made)
    assert row.reason_code == "NO_MEMBERSHIP"
    assert made.snapshot()[1].keys() == {w["owner"], w["member"], w["viewer"], w["nobody"]}


def test_a_query_denial_is_audited_too_and_reveals_only_what_the_caller_sent() -> None:
    w = world()
    made = w["h"]
    error = refused(made, queries.ListPrincipals(), made.actor("viewer"), ErrorCode.FORBIDDEN)
    assert set(error.details) <= {"permission", "scope", "reason_code"}
    assert error.details["scope"] == str(INSTANCE)  # the scope the request itself names (none: instance)
    [row] = denied_audits(made)
    assert row.action == "access.list_principals"


def test_a_member_of_one_workspace_reads_nothing_of_another_through_the_bus() -> None:
    w = world()
    made = w["h"]
    foreign = queries.ListMemberships(scope_id=WS2)
    error = refused(made, foreign, made.actor("member"), ErrorCode.FORBIDDEN)
    assert error.details["reason_code"] in {"NO_MEMBERSHIP", "ROLE_LACKS_PERMISSION"}
    assert str(w["owner"]) not in repr(error.details)
    [row] = denied_audits(made)
    assert row.action == "access.list_memberships"


def test_the_scope_comes_from_the_store_not_from_the_dto() -> None:
    """A DTO names a scope by id only; membership on WS does not make P3 (of WS2) readable."""
    w = world()
    made = w["h"]
    refused(made, queries.ListMemberships(scope_id=h["P3"]), made.actor("member"), ErrorCode.FORBIDDEN)
    # the same member reads its own workspace through the inherited role
    page = made.ask(queries.ListMemberships(scope_id=WS), made.actor("member"))
    assert {item.principal_id for item in page.items} == {w["member"], w["viewer"]}


# ---------------------------------------------------------------------------------------- the token narrows


def test_a_token_never_widens_its_principal() -> None:
    w = world()
    made = w["h"]
    made.token("scoped", w["owner"], scope_id=WS)  # the owner of the instance, a token for one workspace
    scoped = made.actor("scoped")
    error = refused(made, create_principal(), scoped, ErrorCode.FORBIDDEN)
    assert error.details["reason_code"] == "TOKEN_SCOPE"
    made.token("narrow", w["owner"], permissions={"token.own"})
    error = refused(made, create_principal(), made.actor("narrow"), ErrorCode.FORBIDDEN)
    assert error.details["reason_code"] == "TOKEN_NARROWED"
    assert [row.reason_code for row in denied_audits(made)] == ["TOKEN_SCOPE", "TOKEN_NARROWED"]


def test_a_scoped_token_still_works_inside_its_scope_and_for_its_own_credentials() -> None:
    w = world()
    made = w["h"]
    made.token("ws-token", w["owner"], scope_id=WS)
    actor = made.actor("ws-token")
    assert made.ask(queries.ListTokens(), actor).items  # token.own is a self right (row 5c)
    assert made.ask(queries.ListMemberships(scope_id=WS), actor).items


# ----------------------------------------------------------------------------------- not a permission verdict


def test_a_disabled_principal_is_unauthenticated_not_a_permission_verdict() -> None:
    w = world()
    made = w["h"]
    actor = made.actor("owner")
    break_principal(made, w["owner"])
    assert isinstance(refused(made, create_principal(), actor, ErrorCode.UNAUTHENTICATED), Unauthenticated)
    assert made.audits == []  # not a decision of the table: nothing to deny, nothing allowed


def test_an_actor_without_a_grant_of_a_disabled_principal_is_unauthenticated() -> None:
    w = world()
    made = w["h"]
    break_principal(made, w["member"])
    bare = Actor(w["member"], PrincipalKind.HUMAN, "member")
    refused(made, queries.ListMemberships(scope_id=WS), bare, ErrorCode.UNAUTHENTICATED)


def test_an_actor_of_an_unknown_principal_has_no_rights() -> None:
    w = world()
    stranger = Actor(PrincipalId(UUID(int=99)), PrincipalKind.HUMAN, "stranger")
    refused(w["h"], create_principal(), stranger, ErrorCode.UNAUTHENTICATED)


def test_the_kind_of_an_actor_is_the_kind_of_the_stored_principal() -> None:
    w = world()
    made = w["h"]
    real = made.actor("owner")
    lie = Actor(real.principal_id, PrincipalKind.SERVICE, real.display_name, None)
    refused(made, create_principal(), lie, ErrorCode.UNAUTHENTICATED)


@pytest.mark.parametrize(
    "forge",
    [
        lambda g: TokenGrant(g.token_id, g.kind, WS, g.permissions),  # a scope the token never had
        lambda g: TokenGrant(g.token_id, g.kind, g.scope_id, frozenset(PERMISSIONS)),  # more permissions
        lambda g: TokenGrant(UUID(int=7), g.kind, g.scope_id, g.permissions),  # a token that is not stored
    ],
)
def test_a_grant_that_is_not_the_stored_binding_is_unauthenticated(forge: Any) -> None:
    w = world()
    made = w["h"]
    real = made.actor("owner")
    assert real.grant is not None
    forged = Actor(real.principal_id, real.kind, real.display_name, forge(real.grant))
    refused(made, create_principal(), forged, ErrorCode.UNAUTHENTICATED)
    refused(made, queries.WhoAmI(), forged, ErrorCode.UNAUTHENTICATED)


def test_the_grant_of_another_principals_token_is_unauthenticated() -> None:
    w = world()
    made = w["h"]
    borrowed = made.actor("member").grant
    taken = Actor(w["owner"], PrincipalKind.HUMAN, "owner", borrowed)
    refused(made, create_principal(), taken, ErrorCode.UNAUTHENTICATED)


# ------------------------------------------------------------------------------------------ system actor


def test_the_system_actor_needs_no_stored_principal_for_a_system_permission_only() -> None:
    made = rbac_harness()  # no principals at all: init has not created `system` yet
    result = made.run(commands.BootstrapLocalOwner(display_name="Local Owner"), SYSTEM_ACTOR)
    assert result.created is True
    assert result.token_secret
    # any other permission reads the stored principal like for every actor
    refused(made, create_principal(), SYSTEM_ACTOR, ErrorCode.UNAUTHENTICATED)


def test_a_service_that_claims_the_system_id_is_not_the_system_actor() -> None:
    made = rbac_harness()
    dto = commands.BootstrapLocalOwner(display_name="x")
    human = Actor(PrincipalId(SYSTEM_PRINCIPAL_ID), PrincipalKind.HUMAN, "system")
    assert refused(made, dto, human, ErrorCode.FORBIDDEN).details["reason_code"] == "KIND_NOT_ALLOWED"
    with_token = Actor(
        PrincipalId(SYSTEM_PRINCIPAL_ID),
        PrincipalKind.SERVICE,
        "system",
        TokenGrant(UUID(int=5), "personal", None, None),
    )
    assert isinstance(refused(made, dto, with_token, ErrorCode.UNAUTHENTICATED), Unauthenticated)


def test_the_stored_system_principal_is_decided_by_the_table_like_any_other() -> None:
    w = world()
    made = w["h"]
    with made.uow() as uow:
        from skm.modules.access.domain.principal import new_principal

        uow.repo(PrincipalRepository).add(
            new_principal(
                principal_id=PrincipalId(SYSTEM_PRINCIPAL_ID),
                kind=PrincipalKind.SERVICE,
                display_name="system",
                created_by=None,
                now=made.clock.now(),
            )
        )
        uow.commit()
    # row 1 allows system permissions; a non-system permission needs the instance owner membership it lacks
    refused(made, create_principal(), SYSTEM_ACTOR, ErrorCode.FORBIDDEN)


# ------------------------------------------------------------------------------------------ the protocol


def test_the_authorizer_is_the_bus_protocol_and_reads_everything_from_the_unit_of_work() -> None:
    w = world()
    made = w["h"]
    authorizer = RbacAuthorizer(made.clock)
    chain = (ScopeRecord(INSTANCE, ScopeKind.INSTANCE, None, None, NOW),)
    owner_actor, viewer_actor = made.actor("owner"), made.actor("viewer")
    with made.uow(readonly=True) as uow:
        owner = authorizer.authorize(uow, owner_actor, "principal.manage", chain)
        viewer = authorizer.authorize(uow, viewer_actor, "principal.manage", chain)
    assert owner == AuthzDecision(allowed=True)
    assert viewer == AuthzDecision(allowed=False, reason_code="NO_MEMBERSHIP")


def test_a_token_expired_at_the_trusted_now_is_unauthenticated() -> None:
    w = world()
    made = w["h"]
    actor = made.actor("owner")
    made.clock.advance(timedelta(days=31))  # the harness tokens live 30 days
    refused(made, create_principal(), actor, ErrorCode.UNAUTHENTICATED)


def test_registry_permissions_are_covered_by_the_catalog() -> None:
    """Every permission a registered command or query names exists in the permission registry."""
    catalog = frozenset(PERMISSIONS)
    named: set[str] = set()
    for manifest in MANIFESTS:
        catalog |= manifest.permissions
    for manifest in MANIFESTS:
        for raw in (*manifest.commands, *manifest.queries):
            operation = cast("AnyCommandSpec | AnyQuerySpec", raw)
            if operation.permission is not None:
                named.add(operation.permission)
            named.update(operation.permission_alternatives)
    assert named <= catalog | {"system.bootstrap", "system.internal"}
    assert {"token.own", "principal.manage", "membership.manage"} <= named


def test_token_kinds_are_not_part_of_the_verdict() -> None:
    w = world()
    made = w["h"]
    worker = made.principal("w", PrincipalKind.WORKER, {WS: Role.WORKER})
    made.token("worker", worker, kind=TokenKind.WORKER, expires_in=timedelta(hours=100))
    actor = made.actor("worker")
    assert actor.kind is PrincipalKind.WORKER
    error = refused(made, create_principal(), actor, ErrorCode.FORBIDDEN)
    assert error.details["reason_code"] in {"NO_MEMBERSHIP", "KIND_NOT_ALLOWED", "ROLE_LACKS_PERMISSION"}
