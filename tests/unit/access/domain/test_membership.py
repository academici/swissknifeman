"""Membership grant rules, the last-owner guard, principals and identities (access §4.2, §5)."""

import dataclasses
from datetime import UTC, datetime
from uuid import UUID

import pytest

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.domain.identity import LOCAL_ISSUER, LOCAL_OWNER_SUBJECT, PrincipalIdentity
from skm.modules.access.domain.membership import Membership, can_grant, last_owner_guard
from skm.modules.access.domain.principal import (
    Principal,
    PrincipalState,
    disable,
    ensure_principal_update,
    new_principal,
)
from skm.modules.access.domain.roles import ROLE_PERMISSIONS, Role

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
PID = PrincipalId(UUID(int=1))
INSTANCE = ScopeRef(ScopeKind.INSTANCE, ScopeId(UUID(int=100)))

OWNER = ROLE_PERMISSIONS[Role.OWNER]
MAINTAINER = ROLE_PERMISSIONS[Role.MAINTAINER]
MEMBER = ROLE_PERMISSIONS[Role.MEMBER]


# --- can_grant ---


@pytest.mark.parametrize("role", [Role.OWNER, Role.MAINTAINER, Role.MEMBER, Role.VIEWER])
def test_owner_grants_every_hierarchical_role(role: Role) -> None:
    assert can_grant(OWNER, role, ScopeKind.WORKSPACE)


def test_only_a_holder_of_principal_manage_grants_owner() -> None:
    assert can_grant(OWNER, Role.OWNER, ScopeKind.INSTANCE)
    assert not can_grant(MAINTAINER, Role.OWNER, ScopeKind.WORKSPACE)
    # even a granter holding every owner right but principal.manage cannot create owners
    assert not can_grant(OWNER - {"principal.manage"}, Role.OWNER, ScopeKind.WORKSPACE)


def test_maintainer_grants_up_to_its_own_level_but_not_above() -> None:
    assert can_grant(MAINTAINER, Role.MAINTAINER, ScopeKind.PROJECT)
    assert can_grant(MAINTAINER, Role.MEMBER, ScopeKind.PROJECT)
    assert can_grant(MAINTAINER, Role.VIEWER, ScopeKind.PROJECT)
    assert not can_grant(MAINTAINER, Role.OWNER, ScopeKind.PROJECT)


def test_membership_manage_is_required() -> None:
    for held in (MEMBER, ROLE_PERMISSIONS[Role.VIEWER], ROLE_PERMISSIONS[Role.WORKER], frozenset[str]()):
        assert not can_grant(held, Role.VIEWER, ScopeKind.WORKSPACE)


def test_no_escalation_by_a_narrowed_granter() -> None:
    # a token ceiling or lost right makes a role grantable no more
    narrowed = MAINTAINER - {"plan.publish"}
    assert not can_grant(narrowed, Role.MAINTAINER, ScopeKind.WORKSPACE)
    assert not can_grant(narrowed, Role.MEMBER, ScopeKind.WORKSPACE)  # member holds plan.publish
    assert can_grant(narrowed, Role.VIEWER, ScopeKind.WORKSPACE)
    assert not can_grant(frozenset({"membership.manage"}), Role.VIEWER, ScopeKind.WORKSPACE)


@pytest.mark.parametrize("kind", [ScopeKind.WORKSPACE, ScopeKind.PROJECT, ScopeKind.PLAN, ScopeKind.RUN])
def test_worker_role_is_grantable_from_workspace_down(kind: ScopeKind) -> None:
    assert can_grant(OWNER, Role.WORKER, kind)
    assert can_grant(MAINTAINER, Role.WORKER, kind)


@pytest.mark.parametrize("kind", [ScopeKind.INSTANCE, ScopeKind.HOST])
def test_worker_role_is_not_grantable_on_instance_or_host(kind: ScopeKind) -> None:
    assert not can_grant(OWNER, Role.WORKER, kind)


def test_worker_role_still_needs_the_rights_it_hands_out() -> None:
    assert not can_grant(MAINTAINER - {"memory.write"}, Role.WORKER, ScopeKind.WORKSPACE)
    assert not can_grant(frozenset({"membership.manage"}), Role.WORKER, ScopeKind.WORKSPACE)


def test_can_grant_rejects_unknown_role_and_kind() -> None:
    with pytest.raises(ValueError, match="root"):
        can_grant(OWNER, "root", ScopeKind.WORKSPACE)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="galaxy"):
        can_grant(OWNER, Role.WORKER, "galaxy")  # type: ignore[arg-type]


# --- last owner ---


def test_last_owner_guard_blocks_removing_the_last_instance_owner() -> None:
    for left in (0, -1):
        with pytest.raises(PreconditionFailed) as caught:
            last_owner_guard(INSTANCE, left)
        assert caught.value.code is ErrorCode.LAST_OWNER_REQUIRED


def test_last_owner_guard_allows_when_an_owner_remains() -> None:
    last_owner_guard(INSTANCE, 1)
    last_owner_guard(INSTANCE, 5)


@pytest.mark.parametrize(
    "kind", [ScopeKind.WORKSPACE, ScopeKind.PROJECT, ScopeKind.PLAN, ScopeKind.RUN, ScopeKind.HOST]
)
def test_last_owner_guard_concerns_the_instance_only(kind: ScopeKind) -> None:
    last_owner_guard(ScopeRef(kind, ScopeId(UUID(int=7))), 0)


def test_membership_requires_aware_time() -> None:
    Membership(INSTANCE.id, PID, Role.OWNER, None, NOW)
    with pytest.raises(ValueError, match="timezone"):
        Membership(INSTANCE.id, PID, Role.OWNER, None, datetime(2026, 1, 1))  # noqa: DTZ001


# --- principals ---


def create(name: str = "Ada", kind: PrincipalKind = PrincipalKind.HUMAN) -> Principal:
    return new_principal(principal_id=PID, kind=kind, display_name=name, created_by=None, now=NOW)


def test_new_principal_defaults_and_trim() -> None:
    created = create("  Ada Lovelace \t")
    assert created.display_name == "Ada Lovelace"
    assert (created.state, created.row_version, created.created_at, created.created_by) == (
        PrincipalState.ACTIVE,
        1,
        NOW,
        None,
    )


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "\t\n",
        "x" * 201,
        "bad\x00name",
        "two\nlines",
        "bell\x07",
        "del\x7f",
        "c1\x85next",
        "csi\x9b",
    ],
)
def test_new_principal_rejects_bad_names(name: str) -> None:
    with pytest.raises(ValidationFailed) as caught:
        create(name)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["field"] == "display_name"


def test_new_principal_name_edges() -> None:
    assert create("x").display_name == "x"
    assert len(create("x" * 200).display_name) == 200
    assert create(" " + "x" * 200 + " ").display_name == "x" * 200


def test_new_principal_accepts_each_kind_and_rejects_an_unknown_one() -> None:
    for kind in PrincipalKind:
        assert create(kind=kind).kind is kind
    with pytest.raises(ValueError, match="robot"):
        create(kind="robot")  # type: ignore[arg-type]


def test_disable_moves_forward_once_and_is_a_noop_afterwards() -> None:
    created = create()
    disabled = disable(created)
    assert (disabled.state, disabled.row_version) == (PrincipalState.DISABLED, 2)
    assert disabled.kind is created.kind
    assert disable(disabled) is disabled


def test_principal_record_invariants() -> None:
    with pytest.raises(ValueError, match="row_version"):
        dataclasses.replace(create(), row_version=0)
    with pytest.raises(ValueError, match="timezone"):
        dataclasses.replace(create(), created_at=datetime(2026, 1, 1))  # noqa: DTZ001


def test_principal_kind_is_immutable_across_a_save() -> None:
    before = create(kind=PrincipalKind.SERVICE)
    ensure_principal_update(before, disable(before))
    for kind in PrincipalKind:
        if kind is before.kind:
            continue
        morphed = dataclasses.replace(before, kind=kind, row_version=2)
        with pytest.raises(ValueError, match="kind"):
            ensure_principal_update(before, morphed)


def test_principal_save_guard_pins_identity_origin_and_version_step() -> None:
    before = create()
    with pytest.raises(ValueError, match="kind"):
        ensure_principal_update(
            before, dataclasses.replace(before, id=PrincipalId(UUID(int=2)), row_version=2)
        )
    with pytest.raises(ValueError, match="kind"):
        ensure_principal_update(before, dataclasses.replace(before, created_by=PID, row_version=2))
    with pytest.raises(ValueError, match="row_version"):
        ensure_principal_update(
            before, dataclasses.replace(before, state=PrincipalState.DISABLED, row_version=3)
        )
    with pytest.raises(ValueError, match="row_version"):
        ensure_principal_update(before, before)


# --- identities ---


def test_identity_forms() -> None:
    PrincipalIdentity(PID, LOCAL_ISSUER, LOCAL_OWNER_SUBJECT, NOW)
    PrincipalIdentity(PID, "service", "ci", NOW)
    PrincipalIdentity(PID, "oidc:https://issuer.example", "x" * 300, NOW)


@pytest.mark.parametrize(
    ("issuer", "subject"),
    [
        ("", "owner"),
        ("oidc:", "owner"),
        ("ldap", "owner"),
        ("oidc:" + "x" * 196, "owner"),
        ("local", ""),
        ("local", "x" * 301),
    ],
)
def test_identity_rejects_bad_values(issuer: str, subject: str) -> None:
    with pytest.raises(ValueError, match=r"issuer|subject"):
        PrincipalIdentity(PID, issuer, subject, NOW)


def test_identity_requires_aware_time() -> None:
    with pytest.raises(ValueError, match="timezone"):
        PrincipalIdentity(PID, "local", "owner", datetime(2026, 1, 1))  # noqa: DTZ001
