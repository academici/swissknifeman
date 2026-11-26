"""Actor, the single TokenGrant contract and SYSTEM_PRINCIPAL_ID (kernel-platform §2.4, access §4.2/§18)."""

import dataclasses
from uuid import UUID

import pytest

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind, TokenGrant
from skm.kernel.ids import PrincipalId, ScopeId, uuid7, uuid7_timestamp_ms

TOKEN_ID = uuid7(1_700_000_000_000, 1, 1)
RUN_SCOPE = ScopeId(uuid7(1_700_000_000_001, 2, 2))
ASSIGNMENT_ID = uuid7(1_700_000_000_002, 3, 3)
STEP_ID = uuid7(1_700_000_000_003, 4, 4)


def assignment_grant(**overrides: object) -> TokenGrant:
    fields: dict[str, object] = {
        "token_id": TOKEN_ID,
        "kind": "assignment",
        "scope_id": RUN_SCOPE,
        "permissions": frozenset({"step.note"}),
        "assignment_id": ASSIGNMENT_ID,
        "step_id": STEP_ID,
    }
    fields.update(overrides)
    return TokenGrant(**fields)  # type: ignore[arg-type]


def test_system_principal_id_is_the_fixed_uuid7() -> None:
    assert UUID("00000000-0000-7000-8000-000000000001") == SYSTEM_PRINCIPAL_ID
    assert SYSTEM_PRINCIPAL_ID.version == 7
    assert uuid7_timestamp_ms(SYSTEM_PRINCIPAL_ID) == 0


def test_principal_kind_values() -> None:
    assert [kind.value for kind in PrincipalKind] == ["human", "service", "worker"]


def test_actor_without_grant() -> None:
    actor = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")

    assert actor.grant is None


def test_actor_carries_exactly_one_grant_object() -> None:
    fields = {field.name for field in dataclasses.fields(Actor)}

    assert fields == {"principal_id", "kind", "display_name", "grant"}


def test_personal_grant_for_human_and_service() -> None:
    grant = TokenGrant(TOKEN_ID, "personal", None, None)

    for kind in (PrincipalKind.HUMAN, PrincipalKind.SERVICE):
        assert Actor(PrincipalId(uuid7(1, 1, 1)), kind, "who", grant).grant is grant


@pytest.mark.parametrize("grant_kind", ["worker", "assignment"])
def test_worker_grants_belong_to_worker_principals(grant_kind: str) -> None:
    grant = (
        assignment_grant()
        if grant_kind == "assignment"
        else TokenGrant(TOKEN_ID, "worker", None, frozenset({"worker.claim"}))
    )
    principal = PrincipalId(uuid7(1, 1, 1))

    assert Actor(principal, PrincipalKind.WORKER, "w", grant).grant is grant
    for kind in (PrincipalKind.HUMAN, PrincipalKind.SERVICE):
        with pytest.raises(ValueError, match="cannot hold"):
            Actor(principal, kind, "x", grant)


def test_worker_principal_rejects_personal_grant() -> None:
    with pytest.raises(ValueError, match="cannot hold"):
        Actor(
            PrincipalId(uuid7(1, 1, 1)),
            PrincipalKind.WORKER,
            "w",
            TokenGrant(TOKEN_ID, "personal", None, None),
        )


def test_grant_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown token grant kind"):
        TokenGrant(TOKEN_ID, "admin", None, None)  # type: ignore[arg-type]


@pytest.mark.parametrize("missing", ["assignment_id", "step_id", "scope_id"])
def test_assignment_grant_needs_binding(missing: str) -> None:
    with pytest.raises(ValueError, match="needs assignment_id, step_id and scope_id"):
        assignment_grant(**{missing: None})


@pytest.mark.parametrize("kind", ["personal", "worker"])
@pytest.mark.parametrize("extra", [{"assignment_id": ASSIGNMENT_ID}, {"step_id": STEP_ID}])
def test_only_assignment_grant_has_assignment_binding(kind: str, extra: dict[str, UUID]) -> None:
    with pytest.raises(ValueError, match="only for an assignment grant"):
        TokenGrant(TOKEN_ID, kind, None, None, **extra)  # type: ignore[arg-type]


def test_grant_permissions_must_be_frozenset_or_none() -> None:
    assert TokenGrant(TOKEN_ID, "personal", None, frozenset()).permissions == frozenset()
    with pytest.raises(TypeError):
        TokenGrant(TOKEN_ID, "personal", None, {"plan.read"})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        TokenGrant(TOKEN_ID, "personal", None, ["plan.read"])  # type: ignore[arg-type]


def test_scope_ancestors_is_a_tuple() -> None:
    parent = ScopeId(uuid7(5, 5, 5))

    assert assignment_grant(scope_ancestors=(parent,)).scope_ancestors == (parent,)
    assert TokenGrant(TOKEN_ID, "personal", None, None).scope_ancestors == ()
    with pytest.raises(TypeError):
        assignment_grant(scope_ancestors=[parent])


def test_actor_and_grant_are_immutable() -> None:
    actor = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")

    with pytest.raises(dataclasses.FrozenInstanceError):
        actor.display_name = "other"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        assignment_grant().permissions = None  # type: ignore[misc]
