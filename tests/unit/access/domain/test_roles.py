"""Roles and permission catalogue (access §4.3, §15) plus the event inventory (access §9)."""

import dataclasses
import re
from pathlib import Path

import pytest

from skm.kernel.scopes import ScopeKind
from skm.modules.access.domain import events
from skm.modules.access.domain.roles import (
    ASSIGNMENT_TOKEN_DENIED,
    HOST_MEMBER_PERMISSIONS,
    HOST_WORKER_PERMISSIONS,
    KNOWN_PERMISSIONS,
    MEMBER_CONFIG_LEVELS,
    NON_GRANTABLE_BY_TOKEN,
    ROLE_PERMISSIONS,
    ROLE_RANK,
    SELF_PERMISSIONS,
    SYSTEM_PERMISSIONS,
    WORKER_SCOPE_KINDS,
    Role,
    role_permissions,
)
from skm.modules.access.generated import events as generated
from skm.modules.access.permissions import PERMISSIONS

ROOT = Path(__file__).resolve().parents[4]
PERMISSION_TABLE = ROOT / "tests/fixtures/corpus/access-permissions.md"
ROLE_COLUMNS = (Role.OWNER, Role.MAINTAINER, Role.MEMBER, Role.VIEWER, Role.WORKER)


def catalogue_table() -> dict[str, frozenset[Role]]:
    """Parse the permission table of spec/00 §5: permission -> roles that carry a check mark."""
    section = PERMISSION_TABLE.read_text(encoding="utf-8")
    table: dict[str, frozenset[Role]] = {}
    for line in section.splitlines():
        match = re.match(r"\| `([a-z_.]+)` \|", line)
        if match is None:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        marks = cells[-len(ROLE_COLUMNS) :]
        table[match.group(1)] = frozenset(
            role for role, mark in zip(ROLE_COLUMNS, marks, strict=True) if "✓" in mark
        )
    return table


def test_role_permissions_equal_the_spec_table() -> None:
    table = catalogue_table()
    assert set(table) == set(PERMISSIONS)
    for role in Role:
        from_table = frozenset(permission for permission, roles in table.items() if role in roles)
        assert ROLE_PERMISSIONS[role] == from_table, role


def test_table_parser_sees_the_marks() -> None:
    table = catalogue_table()
    assert table["worker.claim"] == {Role.WORKER}
    assert table["principal.manage"] == {Role.OWNER}
    assert table["system.bootstrap"] == frozenset()


def test_the_domain_decides_about_exactly_the_registry() -> None:
    assert KNOWN_PERMISSIONS == PERMISSIONS


def test_every_role_permission_is_in_the_registry() -> None:
    for role, permissions in ROLE_PERMISSIONS.items():
        assert permissions <= PERMISSIONS, role


def test_role_rank_order_and_worker_outside_the_hierarchy() -> None:
    assert (
        ROLE_RANK[Role.OWNER] > ROLE_RANK[Role.MAINTAINER] > ROLE_RANK[Role.MEMBER] > ROLE_RANK[Role.VIEWER]
    )
    assert ROLE_RANK[Role.VIEWER] > ROLE_RANK[Role.WORKER] == 0


def test_hierarchical_roles_are_nested_except_owner_only_rights() -> None:
    assert ROLE_PERMISSIONS[Role.VIEWER] <= ROLE_PERMISSIONS[Role.MEMBER] <= ROLE_PERMISSIONS[Role.MAINTAINER]
    assert ROLE_PERMISSIONS[Role.MAINTAINER] <= ROLE_PERMISSIONS[Role.OWNER]


def test_catalogue_is_immutable() -> None:
    with pytest.raises(TypeError):
        ROLE_PERMISSIONS[Role.VIEWER] = frozenset(PERMISSIONS)  # type: ignore[index]
    with pytest.raises(TypeError):
        ROLE_RANK[Role.VIEWER] = 99  # type: ignore[index]
    assert isinstance(role_permissions(Role.VIEWER), frozenset)


def test_role_permissions_accepts_the_string_value() -> None:
    assert role_permissions("member") == ROLE_PERMISSIONS[Role.MEMBER]  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="superuser"):
        role_permissions("superuser")  # type: ignore[arg-type]


def test_no_role_carries_system_permissions() -> None:
    assert {p for p in PERMISSIONS if p.startswith("system.")} == SYSTEM_PERMISSIONS
    for permissions in ROLE_PERMISSIONS.values():
        assert not permissions & SYSTEM_PERMISSIONS


def test_worker_claim_and_step_note_belong_to_the_worker_role_only() -> None:
    for role in Role:
        has = {"worker.claim", "step.note"} <= ROLE_PERMISSIONS[role]
        assert has is (role is Role.WORKER), role
    assert {"worker.claim"} == ASSIGNMENT_TOKEN_DENIED


def test_context_assemble_is_granted_to_project_writers() -> None:
    assert {role for role in Role if "context.assemble" in role_permissions(role)} == {
        Role.OWNER,
        Role.MAINTAINER,
        Role.MEMBER,
    }


def test_plan_approve_signer_circle() -> None:
    assert {role for role in Role if "plan.approve" in role_permissions(role)} == {
        Role.OWNER,
        Role.MAINTAINER,
    }


def test_restriction_sets() -> None:
    assert {"token.own"} == SELF_PERMISSIONS
    assert {ScopeKind.PROJECT, ScopeKind.PLAN, ScopeKind.RUN} == MEMBER_CONFIG_LEVELS
    assert {ScopeKind.WORKSPACE, ScopeKind.PROJECT, ScopeKind.PLAN, ScopeKind.RUN} == WORKER_SCOPE_KINDS
    assert {"principal.manage", "membership.manage", "token.any", "config.lock"} <= NON_GRANTABLE_BY_TOKEN
    assert NON_GRANTABLE_BY_TOKEN >= SYSTEM_PERMISSIONS
    assert NON_GRANTABLE_BY_TOKEN <= PERMISSIONS


def test_host_permission_sets_are_read_only_for_members_and_scoped_for_workers() -> None:
    assert {"workspace.read", "config.read", "runtime.read"} == HOST_MEMBER_PERMISSIONS
    assert {
        "workspace.read",
        "config.read",
        "runtime.read",
        "runtime.manage",
        "worker.claim",
    } == HOST_WORKER_PERMISSIONS
    assert HOST_WORKER_PERMISSIONS & ROLE_PERMISSIONS[Role.WORKER] == HOST_WORKER_PERMISSIONS
    assert not HOST_MEMBER_PERMISSIONS & {"config.write_shared", "runtime.manage", "host.manage"}


# --- event inventory (access §9) ---


def test_event_types_are_unique_access_urns() -> None:
    assert len(set(events.EVENT_TYPES)) == len(events.EVENT_TYPES) == 7
    assert all(re.fullmatch(r"urn:skm:access:event:[a-z-]+:v1", urn) for urn in events.EVENT_TYPES)
    assert set(events.EVENT_PAYLOAD_FIELDS) == set(events.EVENT_TYPES)
    assert events.EVENT_STREAM_KIND == "principal"


GENERATED_PAYLOADS = {
    events.PRINCIPAL_CREATED: generated.PrincipalCreated,
    events.PRINCIPAL_DISABLED: generated.PrincipalDisabled,
    events.TOKEN_CREATED: generated.TokenCreatedPayload,
    events.TOKEN_ROTATED: generated.TokenRotated,
    events.TOKEN_REVOKED: generated.TokenRevoked,
    events.MEMBERSHIP_GRANTED: generated.MembershipGranted,
    events.MEMBERSHIP_REVOKED: generated.MembershipRevoked,
}


@pytest.mark.parametrize("urn", events.EVENT_TYPES)
def test_event_payload_fields_match_the_generated_contract(urn: str) -> None:
    payload = GENERATED_PAYLOADS[urn]
    assert urn == payload.SCHEMA_URN
    assert tuple(field.name for field in dataclasses.fields(payload)) == events.EVENT_PAYLOAD_FIELDS[urn]


@pytest.mark.parametrize("urn", events.EVENT_TYPES)
def test_no_event_payload_carries_a_secret(urn: str) -> None:
    assert not set(events.EVENT_PAYLOAD_FIELDS[urn]) & events.SECRET_FIELD_NAMES
