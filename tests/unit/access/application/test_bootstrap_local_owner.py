"""``access.bootstrap_local_owner`` and the administration commands around it (access §7.1, §7.2, §7.5-§7.7).

Bootstrap is internal and runs once as ``SYSTEM_ACTOR``: it creates the human owner, the ``local/owner``
identity, the instance owner membership and a token whose secret exists only in that result. The commands that
follow keep the instance owned: no escalation when granting, never removing the last active owner, disabling a
principal revokes its tokens.

The ``skm init`` default workspace (§7.7 G38) is composed by ``bootstrap/instance.py`` and ``workspace``;
its cases are tested in ``tests/integration/bootstrap``.
"""

from pathlib import Path
from runpy import run_path
from typing import Any

import pytest

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, Unauthenticated
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import TokenKind, parse_secret
from skm.modules.access.public import SYSTEM_ACTOR, authenticate_local_owner_password, role_permissions

h = run_path(str(Path(__file__).with_name("test_create_token.py")))
harness, world, refused, create = h["harness"], h["world"], h["refused"], h["create"]
commands, queries, access_state = h["commands"], h["queries"], h["access_state"]
INSTANCE, WS, P1, SECRET_FORMAT = (h[n] for n in ("INSTANCE", "WS", "P1", "SECRET_FORMAT"))


def bootstrap(**fields: Any) -> Any:
    return commands.BootstrapLocalOwner(display_name="Dmitry", **fields)


def types(made: Any) -> list[str]:
    return [e.type.split(":")[-2] for e in made.events]


# ---------------------------------------------------------------------------------------------------------
# bootstrap_local_owner


def test_the_first_call_creates_owner_membership_and_a_token_shown_once() -> None:
    made = harness()
    result = made.run(bootstrap(), SYSTEM_ACTOR)
    assert result.created is True
    assert SECRET_FORMAT.fullmatch(result.token_secret)
    tables = access_state(made.backend.committed)
    principal = tables.principals[result.principal_id]
    assert (principal.kind, principal.display_name, principal.created_by) == (
        PrincipalKind.HUMAN,
        "Dmitry",
        None,
    )
    identity = tables.identities[("local", "owner")]
    assert identity.principal_id == principal.id
    membership = tables.memberships[(INSTANCE, principal.id)]
    assert (membership.role, membership.granted_by) == (Role.OWNER, None)
    [token] = tables.tokens.values()
    assert (token.name, token.kind, token.scope_id, token.permissions, token.expires_at) == (
        "local-owner",
        TokenKind.PERSONAL,
        INSTANCE,
        role_permissions(Role.OWNER),
        None,
    )
    assert types(made) == ["principal-created", "membership-granted", "token-created"]
    assert parse_secret(result.token_secret).random not in made.stored_text()
    assert made.receipts == []
    owner = made.actor(result.token_secret)  # the secret is the credential of the new owner
    assert owner.principal_id == principal.id
    assert "principal.manage" in made.ask(queries.WhoAmI(scope_id=INSTANCE), owner).effective_permissions
    assert made.ask(queries.WhoAmI(scope_id=INSTANCE), owner).token.name == "local-owner"


def test_a_second_call_creates_nothing_and_never_repeats_the_secret() -> None:
    made = harness()
    first = made.run(bootstrap(), SYSTEM_ACTOR)
    snapshot = made.snapshot()
    again = made.run(
        commands.BootstrapLocalOwner(display_name="Someone else", token_name="another"), SYSTEM_ACTOR
    )
    assert (again.created, again.token_secret, again.principal_id) == (False, None, first.principal_id)
    assert made.snapshot() == snapshot


def test_first_admin_password_is_hashed_and_never_replaced_by_bootstrap() -> None:
    made = harness()
    owner = made.run(bootstrap(), SYSTEM_ACTOR)
    password = "valid-first-admin-password"
    assert made.run(bootstrap(password=password), SYSTEM_ACTOR).token_secret is None
    made.run(bootstrap(password="different-password"), SYSTEM_ACTOR)
    assert password not in made.stored_text()
    with made.uow(readonly=True) as uow:
        assert authenticate_local_owner_password(uow, password).principal_id == owner.principal_id
        with pytest.raises(Unauthenticated):
            authenticate_local_owner_password(uow, "different-password")


def test_the_token_name_is_chosen_by_the_caller() -> None:
    made = harness()
    made.run(bootstrap(token_name="my-laptop"), SYSTEM_ACTOR)
    [token] = access_state(made.backend.committed).tokens.values()
    assert token.name == "my-laptop"


def test_an_idempotency_key_is_refused_and_the_result_is_never_stored() -> None:
    made = harness()
    with pytest.raises(SkmError) as caught:
        made.run(bootstrap(), SYSTEM_ACTOR, key="init-1")
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["reason"] == "not_idempotent"
    assert not access_state(made.backend.committed).principals
    made.run(bootstrap(), SYSTEM_ACTOR)
    assert made.receipts == []


def test_only_the_system_actor_may_bootstrap() -> None:
    w = world()
    made = w["h"]
    service = made.principal(
        "svc", PrincipalKind.SERVICE, {INSTANCE: Role.OWNER}
    )  # a service is not SYSTEM_ACTOR
    made.token("svc", service)
    before = made.snapshot()
    with pytest.raises(SkmError) as human:  # internal operations refuse humans before any work
        made.run(bootstrap(), made.actor("owner"))
    assert human.value.code is ErrorCode.FORBIDDEN
    with pytest.raises(SkmError) as other:
        made.run(bootstrap(), made.actor("svc"))
    assert other.value.code is ErrorCode.FORBIDDEN
    assert made.snapshot() == before
    assert not made.receipts


def test_a_blank_display_name_is_refused_and_writes_nothing() -> None:
    made = harness()
    refused(made, commands.BootstrapLocalOwner(display_name="   "), SYSTEM_ACTOR, ErrorCode.SCHEMA_INVALID)
    assert made.events == []


# ---------------------------------------------------------------------------------------------------------
# create_principal


def test_create_principal_with_an_identity_and_the_stored_events() -> None:
    w = world()
    made = w["h"]
    dto = commands.CreatePrincipal(
        kind=commands.PrincipalKind.SERVICE,
        display_name="  ci bot  ",
        identity=commands.CreatePrincipalIdentityVariant1(issuer="service", subject="ci"),
    )
    result = made.run(dto, made.actor("owner"))
    assert result.row_version == 1
    view = made.ask(queries.GetPrincipal(principal_id=result.principal_id), made.actor("owner"))
    assert (view.display_name, view.kind.value, view.state) == ("ci bot", "service", "active")
    assert [(i.issuer, i.subject) for i in view.identities] == [("service", "ci")]
    [event] = [e for e in made.events if e.type.endswith("principal-created:v1")]
    assert event.payload["display_name"] == "ci bot"
    assert event.stream_id == result.principal_id
    refused(made, dto, made.actor("owner"), ErrorCode.ALREADY_EXISTS)  # the identity is taken
    refused(made, dto, made.actor("alice"), ErrorCode.FORBIDDEN)  # members do not manage principals


def test_create_principal_replays_with_the_same_idempotency_key() -> None:
    w = world()
    made = w["h"]
    dto = commands.CreatePrincipal(kind=commands.PrincipalKind.HUMAN, display_name="Carol")
    first = made.run(dto, made.actor("owner"), key="k1")
    again = made.run(dto, made.actor("owner"), key="k1")
    assert again.principal_id == first.principal_id
    assert (
        len(
            [p for p in access_state(made.backend.committed).principals.values() if p.display_name == "Carol"]
        )
        == 1
    )


# ---------------------------------------------------------------------------------------------------------
# disable_principal


def disable(principal_id: Any, version: int = 1, reason: str = "left") -> Any:
    return commands.DisablePrincipal(principal_id=principal_id, expected_row_version=version, reason=reason)


def test_disabling_revokes_every_token_and_records_both_events() -> None:
    w = world()
    made = w["h"]
    made.run(create("second"), made.actor("bob"))
    result = made.run(disable(w["bob"]), made.actor("owner"))
    assert result.row_version == 2
    bobs = [t for t in made.tokens.values() if t.principal_id == w["bob"]]
    assert len(bobs) == 2
    assert all(t.revoked_by == w["owner"] for t in bobs)
    assert types(made).count("token-revoked") == 2
    assert types(made)[-1] == "principal-disabled"
    with pytest.raises(SkmError) as caught:
        made.actor("bob")
    assert caught.value.code is ErrorCode.UNAUTHENTICATED
    events = len(made.events)
    again = made.run(disable(w["bob"], version=2), made.actor("owner"))  # already disabled: a no-op
    assert again.row_version == 2
    assert len(made.events) == events


def test_disable_checks_the_version_and_refuses_oneself() -> None:
    w = world()
    made = w["h"]
    error = refused(made, disable(w["bob"], version=7), made.actor("owner"), ErrorCode.VERSION_CONFLICT)
    assert error.details["actual"] == 1
    error = refused(made, disable(w["owner"]), made.actor("owner"), ErrorCode.INVALID_TRANSITION)
    assert error.details["reason"] == "self"
    refused(made, disable(w["bob"]), made.actor("alice"), ErrorCode.FORBIDDEN)


# ---------------------------------------------------------------------------------------------------------
# grant_membership / revoke_membership


def grant(scope_id: Any, principal_id: Any, role: Role) -> Any:
    return commands.GrantMembership(
        scope_id=scope_id, principal_id=principal_id, role=commands.Role(role.value)
    )


def revoke(scope_id: Any, principal_id: Any) -> Any:
    return commands.RevokeMembership(scope_id=scope_id, principal_id=principal_id)


def test_grant_changes_a_role_once_and_reports_the_previous_one() -> None:
    w = world()
    made = w["h"]
    carol = made.principal("carol")
    owner = made.actor("owner")
    made.run(grant(WS, carol, Role.VIEWER), owner)
    made.run(grant(WS, carol, Role.MEMBER), owner)
    events = [e.payload for e in made.events if e.type.endswith("membership-granted:v1")]
    assert [(p["role"], p["previous_role"]) for p in events] == [("viewer", None), ("member", "viewer")]
    count = len(made.events)
    made.run(grant(WS, carol, Role.MEMBER), owner)  # the same role: nothing is written
    assert len(made.events) == count
    held = access_state(made.backend.committed).memberships[(WS, carol)]
    assert (held.role, held.granted_by) == (Role.MEMBER, w["owner"])
    assert [e.workspace_id for e in made.events if e.type.endswith("membership-granted:v1")] == [WS, WS]


def test_grant_never_escalates_beyond_the_granter() -> None:
    w = world()
    made = w["h"]
    maintainer = made.principal("maint", roles={WS: Role.MAINTAINER})
    made.token("maint", maintainer)
    carol = made.principal("carol")
    actor = made.actor("maint")
    made.run(grant(WS, carol, Role.MEMBER), actor)  # within its own rights
    error = refused(made, grant(WS, carol, Role.OWNER), actor, ErrorCode.FORBIDDEN)
    assert error.details["reason"] == "role_escalation"
    refused(
        made, grant(WS, carol, Role.MEMBER), made.actor("alice"), ErrorCode.FORBIDDEN
    )  # a member manages nothing
    refused(made, grant(INSTANCE, carol, Role.WORKER), made.actor("owner"), ErrorCode.FORBIDDEN)
    assert made.run(grant(WS, carol, Role.OWNER), made.actor("owner")).role.value == "owner"


def test_grant_needs_an_active_principal_a_known_scope_and_a_workspace_first() -> None:
    w = world()
    made = w["h"]
    owner, carol = made.actor("owner"), made.principal("carol")
    error = refused(made, grant(P1, carol, Role.MEMBER), owner, ErrorCode.INVALID_TRANSITION)
    assert error.details["reason"] == "workspace_membership_required"
    made.run(grant(WS, carol, Role.VIEWER), owner)
    assert made.run(grant(P1, carol, Role.MEMBER), owner).scope_id == P1
    refused(made, grant(made.ids.new_id(), carol, Role.MEMBER), owner, ErrorCode.NOT_FOUND)
    made.run(disable(w["bob"]), owner)
    error = refused(made, grant(WS, w["bob"], Role.MEMBER), owner, ErrorCode.INVALID_TRANSITION)
    assert error.details["reason"] == "principal_disabled"


def test_revoking_a_membership_removes_it_once() -> None:
    w = world()
    made = w["h"]
    owner = made.actor("owner")
    done = made.run(revoke(WS, w["bob"]), owner)
    assert done.removed is True
    [event] = [e for e in made.events if e.type.endswith("membership-revoked:v1")]
    assert event.payload["role"] == "viewer"
    assert event.workspace_id == WS
    count = len(made.events)
    again = made.run(revoke(WS, w["bob"]), owner)
    assert again.removed is False
    assert len(made.events) == count
    refused(made, revoke(WS, w["alice"]), made.actor("alice"), ErrorCode.FORBIDDEN)


def test_a_maintainer_cannot_remove_an_owner() -> None:
    w = world()
    made = w["h"]
    maintainer = made.principal("maint", roles={WS: Role.MAINTAINER})
    made.token("maint", maintainer)
    made.run(grant(WS, w["bob"], Role.OWNER), made.actor("owner"))
    error = refused(made, revoke(WS, w["bob"]), made.actor("maint"), ErrorCode.FORBIDDEN)
    assert error.details["reason"] == "role_escalation"


def test_the_instance_always_keeps_an_active_owner() -> None:
    w = world()
    made = w["h"]
    owner = made.actor("owner")
    error = refused(made, revoke(INSTANCE, w["owner"]), owner, ErrorCode.LAST_OWNER_REQUIRED)
    assert error.details["scope_id"] == str(INSTANCE)
    refused(
        made, grant(INSTANCE, w["owner"], Role.MAINTAINER), owner, ErrorCode.LAST_OWNER_REQUIRED
    )  # demotion
    second = made.principal("second", roles={INSTANCE: Role.OWNER})
    made.token("second", second)
    made.run(revoke(INSTANCE, w["owner"]), owner)  # now another active owner remains
    refused(made, revoke(INSTANCE, second), made.actor("second"), ErrorCode.LAST_OWNER_REQUIRED)


def test_a_disabled_owner_does_not_count_as_the_remaining_one() -> None:
    w = world()
    made = w["h"]
    second = made.principal("second", roles={INSTANCE: Role.OWNER})
    made.token("second", second)
    made.run(disable(second), made.actor("owner"))
    refused(made, revoke(INSTANCE, w["owner"]), made.actor("owner"), ErrorCode.LAST_OWNER_REQUIRED)
