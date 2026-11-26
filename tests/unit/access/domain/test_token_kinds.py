"""Token kinds: expiry per kind, rotation window, kind invariants, assignment tokens (access §4.2/§5/§13)."""

import dataclasses
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from skm.kernel.actor import PrincipalKind, TokenGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId
from skm.modules.access.domain.roles import ROLE_PERMISSIONS, Role
from skm.modules.access.domain.token import (
    ASSIGNMENT_PERMISSION_CEILING,
    ApiToken,
    TokenId,
    TokenKind,
    assignment_token_name,
    ensure_assignment_binding,
    ensure_binding_unchanged,
    generate_secret,
    hash_secret,
    new_assignment_token,
    rotation_due,
    token_expiry,
    token_is_usable,
    token_kind_allowed,
)
from unit.access.domain.test_token import settings

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
PEPPER = bytes(range(32))
WORKER = PrincipalId(UUID(int=20))
RUN = ScopeId(UUID(int=30))
ASSIGNMENT = UUID(int=40)
STEP = UUID(int=41)
WORKER_EXPIRES = NOW + timedelta(hours=100)


def worker_grant(**overrides: object) -> TokenGrant:
    fields: dict[str, object] = {
        "token_id": UUID(int=50),
        "kind": "worker",
        "scope_id": None,
        "permissions": None,
    }
    fields.update(overrides)
    return TokenGrant(**fields)  # type: ignore[arg-type]


def issue(**overrides: object) -> ApiToken:
    fields: dict[str, object] = {
        "token_id": TokenId(UUID(int=60)),
        "worker_token": worker_grant(),
        "worker_expires_at": WORKER_EXPIRES,
        "principal_id": WORKER,
        "secret": generate_secret(lambda n: bytes([5]) * n),
        "run_scope_id": RUN,
        "assignment_id": ASSIGNMENT,
        "step_id": STEP,
        "expires_at": NOW + timedelta(hours=1),
        "permissions": frozenset({"plan.read", "run.read", "step.note"}),
        "now": NOW,
        "pepper": PEPPER,
    }
    fields.update(overrides)
    return new_assignment_token(**fields)  # type: ignore[arg-type]


def worker_token(expires_at: datetime) -> ApiToken:
    secret = generate_secret(lambda n: bytes([6]) * n)
    return ApiToken(
        id=TokenId(UUID(int=51)),
        principal_id=WORKER,
        kind=TokenKind.WORKER,
        name="worker",
        prefix=secret.prefix,
        secret_hash=hash_secret(secret, PEPPER),
        scope_id=None,
        permissions=None,
        expires_at=expires_at,
        created_at=NOW,
        created_by=WORKER,
        last_used_at=None,
        revoked_at=None,
        revoked_by=None,
        assignment_id=None,
        step_id=None,
        superseded_by=None,
    )


# --- expiry by kind ---


def test_worker_expiry_is_always_the_worker_ttl() -> None:
    config = settings()
    assert token_expiry(TokenKind.WORKER, None, NOW, config) == NOW + timedelta(hours=168)
    ignored = NOW + timedelta(hours=1)
    assert token_expiry(TokenKind.WORKER, ignored, NOW, config) == NOW + timedelta(hours=168)


def test_worker_expiry_does_not_pass_the_instance_maximum() -> None:
    assert token_expiry(TokenKind.WORKER, None, NOW, settings(max_ttl_days=2)) == NOW + timedelta(days=2)
    assert token_expiry(TokenKind.WORKER, None, NOW, settings(max_ttl_days=0)) == NOW + timedelta(hours=168)


def test_assignment_expiry_is_required_and_future() -> None:
    config = settings()
    with pytest.raises(ValidationFailed) as caught:
        token_expiry(TokenKind.ASSIGNMENT, None, NOW, config)
    assert caught.value.details == {"field": "expires_at", "reason": "required"}
    lease_end = NOW + timedelta(minutes=30)
    assert token_expiry(TokenKind.ASSIGNMENT, lease_end, NOW, config) == lease_end
    with pytest.raises(ValidationFailed) as caught:
        token_expiry(TokenKind.ASSIGNMENT, NOW, NOW, config)
    assert caught.value.details["reason"] == "not_in_future"


def test_personal_expiry_by_kind() -> None:
    assert token_expiry(TokenKind.PERSONAL, None, NOW, settings(default_ttl_days=7)) == NOW + timedelta(
        days=7
    )


# --- rotation window ---


def test_rotation_due_boundary_is_inclusive() -> None:
    config = settings()  # ttl 168 h, rotate 48 h before expiry
    edge = worker_token(NOW + timedelta(hours=48))
    assert rotation_due(edge, NOW, config)
    assert not rotation_due(worker_token(NOW + timedelta(hours=48, seconds=1)), NOW, config)
    assert rotation_due(worker_token(NOW + timedelta(hours=48) - timedelta(seconds=1)), NOW, config)


def test_rotation_window_is_capped_at_half_the_ttl() -> None:
    config = settings(worker_ttl_hours=40, worker_rotate_before_hours=30)  # window = min(30, 20) = 20 h
    assert rotation_due(worker_token(NOW + timedelta(hours=20)), NOW, config)
    assert not rotation_due(worker_token(NOW + timedelta(hours=21)), NOW, config)


def test_an_expired_worker_token_is_due() -> None:
    assert rotation_due(worker_token(NOW - timedelta(hours=1)), NOW, settings())


def test_only_worker_tokens_rotate_by_schedule() -> None:
    assert not rotation_due(issue(), NOW, settings())
    personal = dataclasses.replace(worker_token(NOW + timedelta(hours=1)), kind=TokenKind.PERSONAL)
    assert not rotation_due(personal, NOW, settings())
    assert not rotation_due(dataclasses.replace(personal, expires_at=None), NOW, settings())


# --- kind invariants ---


def test_principal_kind_owns_only_its_token_kinds() -> None:
    allowed = {
        PrincipalKind.HUMAN: {TokenKind.PERSONAL},
        PrincipalKind.SERVICE: {TokenKind.PERSONAL},
        PrincipalKind.WORKER: {TokenKind.WORKER, TokenKind.ASSIGNMENT},
    }
    for principal_kind, kinds in allowed.items():
        for kind in TokenKind:
            assert token_kind_allowed(principal_kind, kind) is (kind in kinds), (principal_kind, kind)


def test_assignment_ceiling_is_the_worker_role_without_the_worker_protocol() -> None:
    assert ROLE_PERMISSIONS[Role.WORKER] - {"worker.claim"} == ASSIGNMENT_PERMISSION_CEILING
    assert "step.note" in ASSIGNMENT_PERMISSION_CEILING


def assignment_fields(**overrides: object) -> dict[str, object]:
    base = dataclasses.asdict(issue())
    base["permissions"] = frozenset(base["permissions"])
    base.update(overrides)
    return base


def test_assignment_record_invariants() -> None:
    ApiToken(**assignment_fields())  # type: ignore[arg-type]
    refused = [
        {"assignment_id": None},
        {"step_id": None},
        {"scope_id": None},
        {"expires_at": None},
        {"permissions": None},
        {"permissions": frozenset({"worker.claim"})},
        {"permissions": frozenset({"plan.edit"})},  # beyond the worker role
        {"kind": TokenKind.PERSONAL},  # assignment_id/step_id on a personal token
        {"kind": TokenKind.WORKER},
    ]
    for overrides in refused:
        with pytest.raises(ValueError, match=r"assignment|step_id|expires_at|permissions"):
            ApiToken(**assignment_fields(**overrides))  # type: ignore[arg-type]


# --- assignment tokens ---


def test_assignment_token_shape() -> None:
    created = issue()
    assert created.kind is TokenKind.ASSIGNMENT
    assert created.name == f"assignment-{ASSIGNMENT}-step-{STEP}"
    assert len(created.name) == 89
    assert created.name == assignment_token_name(ASSIGNMENT, STEP)
    assert (created.scope_id, created.assignment_id, created.step_id) == (RUN, ASSIGNMENT, STEP)
    assert created.principal_id == created.created_by == WORKER
    assert created.expires_at == NOW + timedelta(hours=1)
    assert created.superseded_by is None
    assert created.revoked_at is None
    assert token_is_usable(created, NOW)


def test_assignment_secret_is_hashed_with_the_pepper() -> None:
    secret = generate_secret(lambda n: bytes([5]) * n)
    created = issue(secret=secret)
    assert created.prefix == secret.prefix
    assert created.secret_hash == hash_secret(secret, PEPPER)


def test_assignment_lifetime_is_capped_by_the_worker_token() -> None:
    assert issue(expires_at=NOW + timedelta(hours=500)).expires_at == WORKER_EXPIRES
    assert issue(worker_expires_at=None, expires_at=NOW + timedelta(hours=500)).expires_at == NOW + timedelta(
        hours=500
    )


def test_assignment_lifetime_must_end_in_the_future() -> None:
    for kwargs in (
        {"expires_at": NOW},
        {"worker_expires_at": NOW},
        {"worker_expires_at": NOW - timedelta(hours=1)},
    ):
        with pytest.raises(ValidationFailed) as caught:
            issue(**kwargs)
        assert caught.value.details["reason"] == "not_in_future"


def test_assignment_permissions_never_include_the_worker_protocol() -> None:
    asked = frozenset({"plan.read", "worker.claim", "plan.edit", "memory.write", "not.a.permission"})
    assert issue(permissions=asked).permissions == {"plan.read", "memory.write"}
    assert issue(permissions=frozenset({"worker.claim"})).permissions == frozenset()
    assert issue(permissions=frozenset()).permissions == frozenset()


def test_assignment_permissions_are_narrowed_by_the_issuing_grant() -> None:
    narrowed = worker_grant(permissions=frozenset({"plan.read", "worker.claim"}))
    assert issue(worker_token=narrowed).permissions == {"plan.read"}
    assert issue(worker_token=worker_grant(permissions=frozenset())).permissions == frozenset()


@pytest.mark.parametrize("kind", ["personal", "assignment"])
def test_only_a_worker_token_issues_assignment_tokens(kind: str) -> None:
    extra: dict[str, object] = {}
    if kind == "assignment":
        extra = {"scope_id": RUN, "assignment_id": ASSIGNMENT, "step_id": STEP}
    with pytest.raises(Forbidden) as caught:
        issue(worker_token=worker_grant(kind=kind, **extra))
    assert caught.value.details == {"reason": "not_worker_token"}


def test_each_step_gets_its_own_name_and_binding() -> None:
    other_step = UUID(int=42)
    first, second = issue(), issue(step_id=other_step)
    assert first.name != second.name
    assert (first.step_id, second.step_id) == (STEP, other_step)


def binding(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "principal_id": WORKER,
        "run_scope_id": RUN,
        "assignment_id": ASSIGNMENT,
        "step_id": STEP,
    }
    fields.update(overrides)
    return fields


def test_the_same_binding_is_accepted() -> None:
    ensure_assignment_binding(issue(), **binding())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "other",
    [
        {"step_id": UUID(int=99)},
        {"assignment_id": UUID(int=99)},
        {"run_scope_id": ScopeId(UUID(int=99))},
        {"principal_id": PrincipalId(UUID(int=99))},
    ],
    ids=["step", "assignment", "run", "principal"],
)
def test_an_old_secret_is_never_rebound(other: dict[str, object]) -> None:
    with pytest.raises(Forbidden) as caught:
        ensure_assignment_binding(issue(), **binding(**other))  # type: ignore[arg-type]
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert caught.value.details == {"reason": "assignment_binding_mismatch"}


def test_a_non_assignment_token_never_matches_a_binding() -> None:
    with pytest.raises(Forbidden):
        ensure_assignment_binding(worker_token(WORKER_EXPIRES), **binding())  # type: ignore[arg-type]


def test_assignment_binding_cannot_change_in_place() -> None:
    created = issue()
    for changed in (
        {"step_id": UUID(int=99)},
        {"assignment_id": UUID(int=99)},
        {"scope_id": ScopeId(UUID(int=99)), "assignment_scope_id": ScopeId(UUID(int=99))},
    ):
        with pytest.raises(ValueError, match="keeps its identity"):
            ensure_binding_unchanged(created, dataclasses.replace(created, **changed))
    # lease extension and revocation are the allowed edits
    ensure_binding_unchanged(created, dataclasses.replace(created, expires_at=NOW + timedelta(hours=2)))
