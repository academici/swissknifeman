"""Every row of the authorization table (access §4.4), inheritance, token narrowing, isolation boundary."""

import dataclasses
from datetime import UTC, datetime
from uuid import UUID

import pytest

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind, TokenGrant
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.domain.authorization import (
    Allowed,
    AuthzDecision,
    Denied,
    DenyReason,
    decide,
    effective_permissions,
    is_system_actor,
)
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import Principal, PrincipalState
from skm.modules.access.domain.roles import ROLE_PERMISSIONS, SYSTEM_PERMISSIONS, Role
from skm.modules.access.permissions import PERMISSIONS

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def ref(kind: ScopeKind, number: int) -> ScopeRef:
    return ScopeRef(kind, ScopeId(UUID(int=number)))


INSTANCE = ref(ScopeKind.INSTANCE, 100)
WS1 = ref(ScopeKind.WORKSPACE, 101)
WS2 = ref(ScopeKind.WORKSPACE, 102)
PROJECT_A = ref(ScopeKind.PROJECT, 111)
PROJECT_B = ref(ScopeKind.PROJECT, 112)
PLAN_1 = ref(ScopeKind.PLAN, 121)
PLAN_2 = ref(ScopeKind.PLAN, 122)
RUN_1 = ref(ScopeKind.RUN, 131)
RUN_2 = ref(ScopeKind.RUN, 132)
HOST_H = ref(ScopeKind.HOST, 141)
HOST_H2 = ref(ScopeKind.HOST, 142)
OTHER_WS_PROJECT = ref(ScopeKind.PROJECT, 151)

CHAINS: dict[ScopeRef, tuple[ScopeRef, ...]] = {
    INSTANCE: (INSTANCE,),
    WS1: (INSTANCE, WS1),
    WS2: (INSTANCE, WS2),
    PROJECT_A: (INSTANCE, WS1, PROJECT_A),
    PROJECT_B: (INSTANCE, WS1, PROJECT_B),
    PLAN_1: (INSTANCE, WS1, PROJECT_A, PLAN_1),
    PLAN_2: (INSTANCE, WS1, PROJECT_A, PLAN_2),
    RUN_1: (INSTANCE, WS1, PROJECT_A, PLAN_1, RUN_1),
    RUN_2: (INSTANCE, WS1, PROJECT_A, PLAN_2, RUN_2),
    HOST_H: (INSTANCE, HOST_H),
    HOST_H2: (INSTANCE, HOST_H2),
    OTHER_WS_PROJECT: (INSTANCE, WS2, OTHER_WS_PROJECT),
}
RUN_1_ANCESTORS = tuple(item.id for item in CHAINS[RUN_1][:-1])

HUMAN_ID = PrincipalId(UUID(int=1))
SERVICE_ID = PrincipalId(UUID(int=2))
WORKER_ID = PrincipalId(UUID(int=3))
IDS = {PrincipalKind.HUMAN: HUMAN_ID, PrincipalKind.SERVICE: SERVICE_ID, PrincipalKind.WORKER: WORKER_ID}


def principal_of(kind: PrincipalKind, state: PrincipalState = PrincipalState.ACTIVE) -> Principal:
    return Principal(IDS[kind], kind, kind.value, state, 1, NOW, None)


def actor_of(kind: PrincipalKind, grant: TokenGrant | None = None) -> Actor:
    return Actor(IDS[kind], kind, kind.value, grant)


def member(scope: ScopeRef, role: Role, kind: PrincipalKind = PrincipalKind.HUMAN) -> Membership:
    return Membership(scope.id, IDS[kind], role, None, NOW)


def check(
    permission: str,
    target: ScopeRef,
    *,
    kind: PrincipalKind = PrincipalKind.HUMAN,
    memberships: tuple[Membership, ...] = (),
    grant: TokenGrant | None = None,
    state: PrincipalState = PrincipalState.ACTIVE,
    hosts: frozenset[ScopeId] = frozenset(),
    workspace_member: bool = False,
) -> AuthzDecision:
    return decide(
        actor_of(kind, grant),
        permission,
        CHAINS[target],
        principal_of(kind, state),
        memberships,
        worker_host_ids=hosts,
        has_workspace_membership=workspace_member,
    )


def allowed(decision: AuthzDecision) -> bool:
    return isinstance(decision, Allowed)


def reason(decision: AuthzDecision) -> DenyReason:
    assert isinstance(decision, Denied), decision
    return decision.reason


def personal_grant(scope: ScopeRef | None = None, permissions: frozenset[str] | None = None) -> TokenGrant:
    return TokenGrant(UUID(int=500), "personal", None if scope is None else scope.id, permissions)


def worker_grant(scope: ScopeRef | None = None, permissions: frozenset[str] | None = None) -> TokenGrant:
    return TokenGrant(UUID(int=501), "worker", None if scope is None else scope.id, permissions)


def assignment_grant(
    permissions: frozenset[str] | None = None,
    run: ScopeRef = RUN_1,
    ancestors: tuple[ScopeId, ...] = RUN_1_ANCESTORS,
) -> TokenGrant:
    return TokenGrant(
        UUID(int=502),
        "assignment",
        run.id,
        frozenset({"plan.read", "run.read", "project.read", "memory.write", "step.note", "worker.claim"})
        if permissions is None
        else permissions,
        assignment_id=UUID(int=600),
        step_id=UUID(int=601),
        scope_ancestors=ancestors,
    )


# --- rows 1-2: system permissions ---


SYSTEM_ACTOR = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")
SYSTEM_PRINCIPAL = Principal(
    SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system", PrincipalState.ACTIVE, 1, NOW, None
)


@pytest.mark.parametrize("permission", sorted(SYSTEM_PERMISSIONS))
def test_row_1_the_canonical_system_actor_holds_system_permissions(permission: str) -> None:
    decision = decide(SYSTEM_ACTOR, permission, CHAINS[INSTANCE], SYSTEM_PRINCIPAL, ())
    assert decision == Allowed({"via": "system"})
    assert is_system_actor(SYSTEM_ACTOR)


@pytest.mark.parametrize("permission", sorted(SYSTEM_PERMISSIONS))
@pytest.mark.parametrize("kind", list(PrincipalKind))
def test_row_2_nobody_else_holds_them_even_as_instance_owner(permission: str, kind: PrincipalKind) -> None:
    decision = check(permission, INSTANCE, kind=kind, memberships=(member(INSTANCE, Role.OWNER, kind),))
    assert reason(decision) is DenyReason.SYSTEM_ONLY


def test_row_2_a_spoofed_system_identity_is_not_the_system_actor() -> None:
    owner = (Membership(INSTANCE.id, SYSTEM_PRINCIPAL_ID, Role.OWNER, None, NOW),)
    spoofed = [
        Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.HUMAN, "system"),
        Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.WORKER, "system"),
        Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system", personal_grant()),
        Actor(HUMAN_ID, PrincipalKind.SERVICE, "system"),
    ]
    for actor in spoofed:
        assert not is_system_actor(actor)
        decision = decide(actor, "system.bootstrap", CHAINS[INSTANCE], SYSTEM_PRINCIPAL, owner)
        assert reason(decision) is DenyReason.SYSTEM_ONLY


def test_system_permissions_are_denied_in_any_scope_to_ordinary_actors() -> None:
    for scope in CHAINS:
        assert reason(check("system.internal", scope)) is DenyReason.SYSTEM_ONLY


# --- ACCESS-01: actor and principal record must agree ---


@pytest.mark.parametrize("claimed", [PrincipalKind.HUMAN, PrincipalKind.SERVICE])
def test_a_service_cannot_present_itself_as_human(claimed: PrincipalKind) -> None:
    record = principal_of(PrincipalKind.SERVICE)
    forged = Actor(SERVICE_ID, claimed, "x")
    owner = (member(INSTANCE, Role.OWNER, PrincipalKind.SERVICE),)
    decision = decide(forged, "plan.read", CHAINS[INSTANCE], record, owner)
    if claimed is PrincipalKind.SERVICE:
        assert allowed(decision)
    else:
        assert reason(decision) is DenyReason.PERMISSION_MISSING
        assert isinstance(decision, Denied)
        assert decision.details["reason"] == "actor_principal_mismatch"


def test_a_foreign_principal_record_is_refused() -> None:
    decision = decide(
        actor_of(PrincipalKind.HUMAN),
        "plan.read",
        CHAINS[WS1],
        principal_of(PrincipalKind.SERVICE),
        (member(WS1, Role.OWNER),),
    )
    assert reason(decision) is DenyReason.PERMISSION_MISSING


def test_memberships_of_other_principals_never_count() -> None:
    others = (member(WS1, Role.OWNER, PrincipalKind.SERVICE), member(WS1, Role.OWNER, PrincipalKind.WORKER))
    assert reason(check("plan.read", WS1, memberships=others)) is DenyReason.NO_MEMBERSHIP


def test_memberships_outside_the_target_chain_never_count() -> None:
    elsewhere = (member(WS2, Role.OWNER), member(PROJECT_B, Role.OWNER), member(PLAN_2, Role.OWNER))
    assert reason(check("plan.read", PLAN_1, memberships=elsewhere)) is DenyReason.NO_MEMBERSHIP


# --- row 3: disabled ---


@pytest.mark.parametrize("permission", ["plan.read", "token.own", "config.read"])
def test_row_3_disabled_principal_is_denied_even_for_own_tokens(permission: str) -> None:
    decision = check(permission, WS1, memberships=(member(WS1, Role.OWNER),), state=PrincipalState.DISABLED)
    assert reason(decision) is DenyReason.PRINCIPAL_DISABLED


# --- row 4b: token scope ---


def test_row_4b_token_scope_includes_the_scope_and_below_only() -> None:
    owner = (member(INSTANCE, Role.OWNER),)
    grant = personal_grant(PROJECT_A)
    assert allowed(check("plan.read", PROJECT_A, memberships=owner, grant=grant))
    assert allowed(check("plan.read", PLAN_1, memberships=owner, grant=grant))
    assert allowed(check("plan.read", RUN_1, memberships=owner, grant=grant))
    for outside in (WS1, INSTANCE, PROJECT_B, OTHER_WS_PROJECT, HOST_H):
        assert (
            reason(check("plan.read", outside, memberships=owner, grant=grant))
            is DenyReason.TOKEN_SCOPE_MISMATCH
        )


def test_row_4b_a_personal_token_never_gets_the_ancestor_read_exception() -> None:
    owner = (member(INSTANCE, Role.OWNER),)
    decision = check("project.read", WS1, memberships=owner, grant=personal_grant(PROJECT_A))
    assert reason(decision) is DenyReason.TOKEN_SCOPE_MISMATCH
    worker_owner = (member(INSTANCE, Role.OWNER, PrincipalKind.WORKER),)
    decision = check(
        "project.read",
        WS1,
        kind=PrincipalKind.WORKER,
        memberships=worker_owner,
        grant=worker_grant(PROJECT_A),
    )
    assert reason(decision) is DenyReason.TOKEN_SCOPE_MISMATCH


def test_row_4b_without_scope_the_token_does_not_narrow_the_place() -> None:
    owner = (member(INSTANCE, Role.OWNER),)
    for target in CHAINS:
        assert allowed(check("plan.read", target, memberships=owner, grant=personal_grant()))


# --- row 5: token permissions ---


def test_row_5_token_permissions_narrow_the_role() -> None:
    owner = (member(INSTANCE, Role.OWNER),)
    grant = personal_grant(permissions=frozenset({"plan.read"}))
    assert allowed(check("plan.read", PLAN_1, memberships=owner, grant=grant))
    assert (
        reason(check("plan.edit", PLAN_1, memberships=owner, grant=grant))
        is DenyReason.TOKEN_PERMISSION_MISSING
    )


def test_row_5_a_token_never_adds_permissions_the_role_lacks() -> None:
    viewer = (member(WS1, Role.VIEWER),)
    grant = personal_grant(permissions=frozenset({"plan.read", "plan.edit"}))
    assert allowed(check("plan.read", PLAN_1, memberships=viewer, grant=grant))
    assert (
        reason(check("plan.edit", PLAN_1, memberships=viewer, grant=grant)) is DenyReason.PERMISSION_MISSING
    )


def test_row_5_an_empty_permission_set_allows_nothing_not_even_own_tokens() -> None:
    owner = (member(INSTANCE, Role.OWNER),)
    grant = personal_grant(permissions=frozenset())
    assert (
        reason(check("plan.read", WS1, memberships=owner, grant=grant)) is DenyReason.TOKEN_PERMISSION_MISSING
    )
    assert (
        reason(check("token.own", WS1, memberships=owner, grant=grant)) is DenyReason.TOKEN_PERMISSION_MISSING
    )


def test_row_5_scope_is_checked_before_permissions() -> None:
    grant = personal_grant(PROJECT_A, frozenset({"plan.read"}))
    decision = check("plan.edit", PROJECT_B, memberships=(member(INSTANCE, Role.OWNER),), grant=grant)
    assert reason(decision) is DenyReason.TOKEN_SCOPE_MISMATCH


# --- row 5c: own tokens ---


@pytest.mark.parametrize("role", [Role.OWNER, Role.MAINTAINER, Role.MEMBER, Role.VIEWER, Role.WORKER])
def test_row_5c_own_token_with_a_role_on_a_workspace(role: Role) -> None:
    kind = PrincipalKind.WORKER if role is Role.WORKER else PrincipalKind.HUMAN
    decision = check("token.own", INSTANCE, kind=kind, memberships=(member(WS1, role, kind),))
    assert decision == Allowed({"via": "self"})


def test_row_5c_needs_no_membership_at_all() -> None:
    for kind in PrincipalKind:
        assert check("token.own", INSTANCE, kind=kind) == Allowed({"via": "self"})
        assert allowed(check("token.own", WS2, kind=kind))


def test_row_5c_a_workspace_scoped_token_still_manages_its_own_token_on_the_instance() -> None:
    owner = (member(WS1, Role.MEMBER),)
    grant = personal_grant(WS1, frozenset({"token.own", "plan.read"}))
    assert allowed(check("token.own", INSTANCE, memberships=owner, grant=grant))
    assert (
        reason(check("plan.read", INSTANCE, memberships=owner, grant=grant))
        is DenyReason.TOKEN_SCOPE_MISMATCH
    )


def test_row_5c_does_not_grant_other_tokens() -> None:
    for role in (Role.VIEWER, Role.MEMBER, Role.WORKER):
        kind = PrincipalKind.WORKER if role is Role.WORKER else PrincipalKind.HUMAN
        decision = check("token.any", INSTANCE, kind=kind, memberships=(member(WS1, role, kind),))
        assert reason(decision) is DenyReason.NO_MEMBERSHIP
        decision = check("token.any", WS1, kind=kind, memberships=(member(WS1, role, kind),))
        assert reason(decision) is DenyReason.PERMISSION_MISSING


def test_row_5c_token_any_needs_a_maintainer_or_owner_on_the_instance() -> None:
    assert allowed(check("token.any", INSTANCE, memberships=(member(INSTANCE, Role.OWNER),)))
    assert allowed(check("token.any", INSTANCE, memberships=(member(INSTANCE, Role.MAINTAINER),)))
    assert reason(check("token.any", INSTANCE, memberships=(member(INSTANCE, Role.MEMBER),))) is (
        DenyReason.PERMISSION_MISSING
    )


# --- row 6: no membership ---


def test_row_6_no_membership_at_all() -> None:
    for kind in PrincipalKind:
        assert reason(check("plan.read", PLAN_1, kind=kind)) is DenyReason.NO_MEMBERSHIP
        assert reason(check("workspace.read", INSTANCE, kind=kind)) is DenyReason.NO_MEMBERSHIP


def test_row_6_worker_claim_in_its_own_workspace_only() -> None:
    worker = PrincipalKind.WORKER
    membership = (member(WS1, Role.WORKER, worker),)
    assert allowed(check("worker.claim", WS1, kind=worker, memberships=membership))
    assert reason(check("worker.claim", WS2, kind=worker, memberships=membership)) is DenyReason.NO_MEMBERSHIP
    assert (
        reason(check("worker.claim", INSTANCE, kind=worker, memberships=membership))
        is DenyReason.NO_MEMBERSHIP
    )


def test_row_6_a_worker_with_workspace_membership_claims_below_the_workspace_too() -> None:
    worker = PrincipalKind.WORKER
    membership = (member(WS1, Role.WORKER, worker),)
    for target in (PROJECT_A, PLAN_1, RUN_1):
        assert allowed(check("worker.claim", target, kind=worker, memberships=membership))


# --- rows 6a / 6b: host scope ---


@pytest.mark.parametrize(
    "permission", ["config.read", "runtime.manage", "runtime.read", "workspace.read", "worker.claim"]
)
def test_row_6a_worker_of_host_h_acts_on_host_h(permission: str) -> None:
    worker = PrincipalKind.WORKER
    hosts = frozenset({HOST_H.id})
    assert check(permission, HOST_H, kind=worker, hosts=hosts) == Allowed(
        {"via": "host_worker", "via_scope": str(HOST_H.id)}
    )
    assert reason(check(permission, HOST_H2, kind=worker, hosts=hosts)) is DenyReason.NO_MEMBERSHIP


def test_row_6a_a_retired_or_unregistered_worker_has_no_host() -> None:
    assert (
        reason(check("config.read", HOST_H, kind=PrincipalKind.WORKER, hosts=frozenset()))
        is DenyReason.NO_MEMBERSHIP
    )


def test_row_6a_stops_at_the_worker_host_permissions() -> None:
    worker = PrincipalKind.WORKER
    hosts = frozenset({HOST_H.id})
    for permission in (
        "config.write",
        "config.write_shared",
        "host.manage",
        "plan.read",
        "file.read",
        "memory.write",
    ):
        assert reason(check(permission, HOST_H, kind=worker, hosts=hosts)) is DenyReason.PERMISSION_MISSING


def test_row_6a_applies_to_worker_principals_only() -> None:
    hosts = frozenset({HOST_H.id})
    for kind in (PrincipalKind.HUMAN, PrincipalKind.SERVICE):
        assert reason(check("runtime.manage", HOST_H, kind=kind, hosts=hosts)) is DenyReason.NO_MEMBERSHIP


def test_row_6a_host_ids_do_not_open_ordinary_scopes() -> None:
    hosts = frozenset({HOST_H.id, WS1.id})
    assert (
        reason(check("config.read", WS1, kind=PrincipalKind.WORKER, hosts=hosts)) is DenyReason.NO_MEMBERSHIP
    )


@pytest.mark.parametrize("kind", [PrincipalKind.HUMAN, PrincipalKind.SERVICE])
def test_row_6b_workspace_participants_read_every_host(kind: PrincipalKind) -> None:
    for host in (HOST_H, HOST_H2):
        for permission in ("config.read", "workspace.read", "runtime.read"):
            decision = check(permission, host, kind=kind, workspace_member=True)
            assert decision == Allowed({"via": "host_member", "via_scope": str(host.id)})


@pytest.mark.parametrize("kind", [PrincipalKind.HUMAN, PrincipalKind.SERVICE])
def test_row_6b_never_writes_to_a_host(kind: PrincipalKind) -> None:
    for permission in (
        "config.write_shared",
        "config.write",
        "runtime.manage",
        "host.manage",
        "worker.claim",
    ):
        assert (
            reason(check(permission, HOST_H, kind=kind, workspace_member=True))
            is DenyReason.PERMISSION_MISSING
        )


@pytest.mark.parametrize("kind", [PrincipalKind.HUMAN, PrincipalKind.SERVICE])
def test_row_6b_needs_a_workspace_membership(kind: PrincipalKind) -> None:
    assert reason(check("config.read", HOST_H, kind=kind, workspace_member=False)) is DenyReason.NO_MEMBERSHIP


def test_row_6b_does_not_open_ordinary_scopes() -> None:
    assert reason(check("config.read", WS1, workspace_member=True)) is DenyReason.NO_MEMBERSHIP


def test_host_writes_follow_an_instance_membership() -> None:
    owner = (member(INSTANCE, Role.OWNER),)
    assert allowed(check("config.write_shared", HOST_H, memberships=owner, workspace_member=True))
    assert allowed(check("runtime.manage", HOST_H2, memberships=owner))
    assert allowed(check("host.manage", HOST_H, memberships=owner))
    maintainer = (member(INSTANCE, Role.MAINTAINER),)
    assert allowed(check("config.write_shared", HOST_H, memberships=maintainer))
    assert reason(check("host.manage", HOST_H, memberships=maintainer)) is DenyReason.PERMISSION_MISSING


def test_workspace_memberships_do_not_reach_hosts_through_the_tree() -> None:
    # host is a separate branch under the instance: a workspace owner is a plain host reader (6b), no admin
    owner = (member(WS1, Role.OWNER),)
    assert reason(check("config.write_shared", HOST_H, memberships=owner, workspace_member=True)) is (
        DenyReason.PERMISSION_MISSING
    )
    assert allowed(check("config.read", HOST_H, memberships=owner, workspace_member=True))


# --- row 7-9: roles, inheritance, restrictions ---


def test_row_8_allowed_names_the_granting_role_and_scope() -> None:
    decision = check("plan.edit", PLAN_1, memberships=(member(WS1, Role.MEMBER),))
    assert decision == Allowed({"via": "role", "via_role": "member", "via_scope": str(WS1.id)})


def test_rights_are_inherited_downward() -> None:
    for role in (Role.OWNER, Role.MAINTAINER, Role.MEMBER, Role.VIEWER):
        granted = (member(WS1, role),)
        for target in (WS1, PROJECT_A, PROJECT_B, PLAN_1, RUN_1):
            assert allowed(check("plan.read", target, memberships=granted)), (role, target)


def test_rights_do_not_flow_upward_or_sideways() -> None:
    granted = (member(PROJECT_A, Role.OWNER),)
    for target in (INSTANCE, WS1, PROJECT_B, OTHER_WS_PROJECT, HOST_H):
        assert reason(check("plan.read", target, memberships=granted)) is DenyReason.NO_MEMBERSHIP
    assert allowed(check("plan.read", RUN_1, memberships=granted))
    assert allowed(check("plan.read", PROJECT_A, memberships=granted))


def test_memberships_on_the_chain_are_united() -> None:
    granted = (member(WS1, Role.VIEWER), member(PROJECT_A, Role.MEMBER))
    assert allowed(check("plan.edit", PLAN_1, memberships=granted))
    assert allowed(check("plan.read", PLAN_1, memberships=granted))
    assert reason(check("plan.edit", PROJECT_B, memberships=granted)) is DenyReason.PERMISSION_MISSING


def test_a_lower_role_never_removes_the_rights_of_a_higher_scope() -> None:
    granted = (member(WS1, Role.OWNER), member(PROJECT_A, Role.VIEWER))
    assert allowed(check("plan.archive", PLAN_1, memberships=granted))
    assert allowed(check("config.lock", PROJECT_A, memberships=granted))


def test_the_highest_role_is_cited_when_several_grant() -> None:
    granted = (member(WS1, Role.VIEWER), member(PROJECT_A, Role.OWNER), member(PLAN_1, Role.MEMBER))
    decision = check("plan.read", PLAN_1, memberships=granted)
    assert decision == Allowed({"via": "role", "via_role": "owner", "via_scope": str(PROJECT_A.id)})
    # equal ranks: the deepest scope is cited, whatever order memberships arrive in
    equal = (member(PLAN_1, Role.MEMBER), member(WS1, Role.MEMBER))
    assert check("plan.edit", PLAN_1, memberships=equal) == check(
        "plan.edit", PLAN_1, memberships=equal[::-1]
    )


def test_row_9_missing_permission() -> None:
    assert (
        reason(check("plan.edit", PLAN_1, memberships=(member(WS1, Role.VIEWER),)))
        is DenyReason.PERMISSION_MISSING
    )
    assert reason(check("unknown.permission", PLAN_1, memberships=(member(WS1, Role.OWNER),))) is (
        DenyReason.PERMISSION_MISSING
    )


def test_member_config_write_needs_project_plan_or_run() -> None:
    for target, scope in ((WS1, WS1), (INSTANCE, INSTANCE), (HOST_H, INSTANCE)):
        decision = check("config.write", target, memberships=(member(scope, Role.MEMBER),))
        assert reason(decision) is DenyReason.ROLE_LEVEL_RESTRICTED, target
    for target in (PROJECT_A, PLAN_1, RUN_1):
        assert allowed(check("config.write", target, memberships=(member(WS1, Role.MEMBER),))), target


def test_member_config_write_restriction_does_not_touch_other_roles() -> None:
    for role in (Role.OWNER, Role.MAINTAINER):
        assert allowed(check("config.write", WS1, memberships=(member(WS1, role),)))


def test_a_stronger_membership_lifts_the_member_restriction() -> None:
    granted = (member(INSTANCE, Role.MAINTAINER), member(WS1, Role.MEMBER))
    assert allowed(check("config.write", WS1, memberships=granted))


def test_viewer_config_write_is_a_plain_missing_permission() -> None:
    assert reason(check("config.write", PROJECT_A, memberships=(member(WS1, Role.VIEWER),))) is (
        DenyReason.PERMISSION_MISSING
    )


def test_worker_role_on_the_instance_grants_nothing() -> None:
    worker = PrincipalKind.WORKER
    granted = (member(INSTANCE, Role.WORKER, worker),)
    for target in CHAINS:
        for permission in ("worker.claim", "plan.read", "workspace.read", "config.read"):
            assert not allowed(check(permission, target, kind=worker, memberships=granted)), (
                target,
                permission,
            )
    assert (
        reason(check("worker.claim", WS1, kind=worker, memberships=granted))
        is DenyReason.ROLE_LEVEL_RESTRICTED
    )


def test_worker_role_on_a_host_scope_grants_nothing() -> None:
    worker = PrincipalKind.WORKER
    granted = (member(HOST_H, Role.WORKER, worker),)
    assert not allowed(check("runtime.manage", HOST_H, kind=worker, memberships=granted))


def test_worker_role_at_workspace_level_has_its_catalogue_rights_only() -> None:
    worker = PrincipalKind.WORKER
    granted = (member(WS1, Role.WORKER, worker),)
    for permission in ROLE_PERMISSIONS[Role.WORKER] - {"token.own"}:
        assert allowed(check(permission, PROJECT_A, kind=worker, memberships=granted)), permission
    for permission in ("plan.edit", "run.start", "config.write", "membership.manage", "inbox.read"):
        assert (
            reason(check(permission, PROJECT_A, kind=worker, memberships=granted))
            is DenyReason.PERMISSION_MISSING
        )


def test_viewer_of_a_workspace_reads_all_its_projects_but_not_another_workspace() -> None:
    # isolation boundary is the workspace (access §1)
    granted = (member(WS1, Role.VIEWER),)
    for target in (PROJECT_A, PROJECT_B, PLAN_1, PLAN_2, RUN_1, RUN_2):
        for permission in ("project.read", "plan.read", "run.read", "file.read"):
            assert allowed(check(permission, target, memberships=granted)), (target, permission)
    assert reason(check("project.read", OTHER_WS_PROJECT, memberships=granted)) is DenyReason.NO_MEMBERSHIP


def test_a_project_membership_only_adds_it_does_not_replace_the_workspace() -> None:
    project_only = (member(PROJECT_A, Role.MEMBER),)
    assert allowed(check("plan.edit", PLAN_1, memberships=project_only))
    assert reason(check("project.read", PROJECT_B, memberships=project_only)) is DenyReason.NO_MEMBERSHIP


# --- rows 4a / 5a: assignment tokens ---


WORKER = PrincipalKind.WORKER
WORKER_ON_WS1 = (member(WS1, Role.WORKER, WORKER),)


def assignment_check(permission: str, target: ScopeRef, grant: TokenGrant | None = None) -> AuthzDecision:
    return check(
        permission, target, kind=WORKER, memberships=WORKER_ON_WS1, grant=grant or assignment_grant()
    )


def test_row_4a_assignment_reads_the_ancestors_of_its_run() -> None:
    for target in (PLAN_1, PROJECT_A, WS1, RUN_1):
        assert allowed(assignment_check("plan.read", target)), target
        assert allowed(assignment_check("project.read", target)), target


def test_row_4a_the_read_exception_does_not_cover_the_instance_without_membership() -> None:
    assert reason(assignment_check("plan.read", INSTANCE)) is DenyReason.NO_MEMBERSHIP


def test_row_4b_assignment_reads_no_other_plan_of_the_same_project() -> None:
    assert reason(assignment_check("plan.read", PLAN_2)) is DenyReason.TOKEN_SCOPE_MISMATCH
    assert reason(assignment_check("run.read", RUN_2)) is DenyReason.TOKEN_SCOPE_MISMATCH
    assert reason(assignment_check("plan.read", PROJECT_B)) is DenyReason.TOKEN_SCOPE_MISMATCH
    assert reason(assignment_check("plan.read", OTHER_WS_PROJECT)) is DenyReason.TOKEN_SCOPE_MISMATCH


def test_row_4b_assignment_writes_only_in_its_run() -> None:
    assert allowed(assignment_check("memory.write", RUN_1))
    assert allowed(assignment_check("step.note", RUN_1))
    for target in (PROJECT_A, PLAN_1, WS1):
        assert reason(assignment_check("memory.write", target)) is DenyReason.TOKEN_SCOPE_MISMATCH, target
        assert reason(assignment_check("step.note", target)) is DenyReason.TOKEN_SCOPE_MISMATCH, target


def test_row_4a_only_permissions_ending_in_read_pass() -> None:
    wide = assignment_grant(frozenset({"checkout.read_locator", "file.write", "config.read", "file.read"}))
    assert (
        reason(assignment_check("checkout.read_locator", PROJECT_A, wide)) is DenyReason.TOKEN_SCOPE_MISMATCH
    )
    assert reason(assignment_check("file.write", PROJECT_A, wide)) is DenyReason.TOKEN_SCOPE_MISMATCH
    assert allowed(assignment_check("config.read", PROJECT_A, wide))
    assert allowed(assignment_check("file.read", PROJECT_A, wide))


def test_row_4a_still_obeys_the_token_permission_ceiling() -> None:
    narrow = assignment_grant(frozenset({"plan.read"}))
    assert allowed(assignment_check("plan.read", PROJECT_A, narrow))
    assert reason(assignment_check("project.read", PROJECT_A, narrow)) is DenyReason.TOKEN_PERMISSION_MISSING


def test_row_4a_needs_the_listed_ancestors_from_authentication() -> None:
    # scope_ancestors comes from trusted authentication; without it the token is just a run-scoped token
    bare = assignment_grant(ancestors=())
    assert reason(assignment_check("plan.read", PLAN_1, bare)) is DenyReason.TOKEN_SCOPE_MISMATCH
    assert allowed(assignment_check("plan.read", RUN_1, bare))


def test_row_4a_a_worker_kind_token_gets_no_ancestor_exception() -> None:
    decision = check("plan.read", PLAN_1, kind=WORKER, memberships=WORKER_ON_WS1, grant=worker_grant(RUN_1))
    assert reason(decision) is DenyReason.TOKEN_SCOPE_MISMATCH


@pytest.mark.parametrize("target", [RUN_1, PLAN_1, PROJECT_A, WS1, INSTANCE, HOST_H, RUN_2])
def test_row_5a_assignment_token_never_claims(target: ScopeRef) -> None:
    # even when the token lists the right and the worker role has it
    decision = assignment_check("worker.claim", target)
    assert not allowed(decision)
    if target in CHAINS and RUN_1 in CHAINS[target]:
        assert reason(decision) is DenyReason.TOKEN_PERMISSION_MISSING


def test_row_5a_denial_is_independent_of_the_membership() -> None:
    strong = (member(INSTANCE, Role.OWNER, WORKER),)
    decision = check(
        "worker.claim", RUN_1, kind=WORKER, memberships=strong + WORKER_ON_WS1, grant=assignment_grant()
    )
    assert reason(decision) is DenyReason.TOKEN_PERMISSION_MISSING


def test_row_5a_a_worker_token_claims_and_an_assignment_token_does_not() -> None:
    assert allowed(check("worker.claim", RUN_1, kind=WORKER, memberships=WORKER_ON_WS1, grant=worker_grant()))
    assert allowed(check("worker.claim", WS1, kind=WORKER, memberships=WORKER_ON_WS1))
    assert not allowed(assignment_check("worker.claim", RUN_1))


def test_assignment_token_cannot_exceed_the_worker_role() -> None:
    broad = assignment_grant(frozenset(PERMISSIONS))
    for permission in ("plan.edit", "run.start", "config.write", "membership.manage", "principal.manage"):
        decision = assignment_check(permission, RUN_1, broad)
        assert reason(decision) in (DenyReason.PERMISSION_MISSING, DenyReason.NO_MEMBERSHIP), permission


def test_assignment_token_own_token_right_follows_the_ceiling() -> None:
    assert allowed(assignment_check("token.own", INSTANCE, assignment_grant(frozenset({"token.own"}))))
    assert reason(assignment_check("token.own", INSTANCE, assignment_grant(frozenset({"plan.read"})))) is (
        DenyReason.TOKEN_PERMISSION_MISSING
    )


# --- effective permissions ---


def effective(
    target: ScopeRef,
    *,
    kind: PrincipalKind = PrincipalKind.HUMAN,
    grant: TokenGrant | None = None,
    memberships: tuple[Membership, ...] = (),
    hosts: frozenset[ScopeId] = frozenset(),
    workspace_member: bool = False,
) -> frozenset[str]:
    return effective_permissions(
        actor_of(kind, grant),
        CHAINS[target],
        principal_of(kind),
        memberships,
        worker_host_ids=hosts,
        has_workspace_membership=workspace_member,
    )


def test_effective_permissions_of_a_viewer_are_the_role_plus_own_tokens() -> None:
    assert effective(PLAN_1, memberships=(member(WS1, Role.VIEWER),)) == ROLE_PERMISSIONS[Role.VIEWER]


def test_effective_permissions_without_membership_are_own_tokens_only() -> None:
    assert effective(WS2, memberships=(member(WS1, Role.OWNER),)) == {"token.own"}


def test_effective_permissions_apply_the_token_ceiling_and_the_level_rule() -> None:
    granted = (member(WS1, Role.MEMBER),)
    assert "config.write" not in effective(WS1, memberships=granted)
    assert "config.write" in effective(PROJECT_A, memberships=granted)
    ceiling = personal_grant(
        permissions=frozenset({"plan.read", "plan.edit", "token.own", "membership.manage"})
    )
    assert effective(PLAN_1, memberships=granted, grant=ceiling) == {"plan.read", "plan.edit", "token.own"}


def test_effective_permissions_never_include_system_rights_for_ordinary_actors() -> None:
    assert not effective(INSTANCE, memberships=(member(INSTANCE, Role.OWNER),)) & SYSTEM_PERMISSIONS


def test_effective_permissions_on_a_host() -> None:
    assert effective(HOST_H, kind=WORKER, hosts=frozenset({HOST_H.id})) == {
        "token.own",
        "workspace.read",
        "config.read",
        "runtime.read",
        "runtime.manage",
        "worker.claim",
    }
    assert effective(HOST_H, workspace_member=True) == {
        "token.own",
        "workspace.read",
        "config.read",
        "runtime.read",
    }


# --- input hygiene ---


def test_an_empty_or_rootless_chain_is_a_programming_error() -> None:
    args = (actor_of(PrincipalKind.HUMAN), "plan.read")
    with pytest.raises(ValueError, match="instance"):
        decide(*args, (), principal_of(PrincipalKind.HUMAN), ())
    with pytest.raises(ValueError, match="instance"):
        decide(*args, (WS1, PROJECT_A), principal_of(PrincipalKind.HUMAN), ())


def test_decisions_are_frozen_values() -> None:
    decision = check("plan.read", WS1, memberships=(member(WS1, Role.VIEWER),))
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.details = {}  # type: ignore[misc]


def test_denials_carry_the_request_in_details() -> None:
    decision = check("plan.edit", PLAN_1, memberships=(member(WS1, Role.VIEWER),))
    assert isinstance(decision, Denied)
    assert decision.details == {"permission": "plan.edit", "scope_id": str(PLAN_1.id), "scope_kind": "plan"}


def test_every_deny_reason_is_reachable() -> None:
    reached = {
        reason(check("system.bootstrap", INSTANCE)),
        reason(check("plan.read", WS1, state=PrincipalState.DISABLED)),
        reason(check("plan.read", WS1)),
        reason(check("plan.edit", WS1, memberships=(member(WS1, Role.VIEWER),))),
        reason(check("config.write", WS1, memberships=(member(WS1, Role.MEMBER),))),
        reason(
            check(
                "plan.read", WS1, memberships=(member(INSTANCE, Role.OWNER),), grant=personal_grant(PROJECT_A)
            )
        ),
        reason(
            check(
                "plan.edit",
                WS1,
                memberships=(member(INSTANCE, Role.OWNER),),
                grant=personal_grant(permissions=frozenset()),
            )
        ),
    }
    assert reached == set(DenyReason)
