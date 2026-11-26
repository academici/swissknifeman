"""Secret format, hashing, usability, expiry, revocation, rotation of API tokens (access §5, token-format)."""

import dataclasses
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, Unauthenticated, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId
from skm.modules.access.domain.principal import Principal, PrincipalState
from skm.modules.access.domain.token import (
    ApiToken,
    TokenId,
    TokenKind,
    TokenSecret,
    TokenState,
    ensure_binding_unchanged,
    ensure_token_usable,
    generate_secret,
    grant_of,
    hash_secret,
    parse_secret,
    revoke,
    rotate,
    token_expiry,
    token_is_usable,
    token_state,
    verify_secret,
)
from skm.modules.access.generated.settings import AccessAuditSettings, AccessSettings, AccessTokensSettings

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
PEPPER = bytes(range(32))
OTHER_PEPPER = bytes(range(1, 33))
OWNER = PrincipalId(UUID(int=1))
TOKEN_ID = TokenId(UUID(int=10))
FORMAT = re.compile(r"^skm_live_[a-z2-7]{8}_[A-Za-z0-9_-]{43}_[0-9a-f]{8}$")
EXAMPLE = "skm_k7q2mzpa_4Yb9vQe2T1nXr8LwJ0cZpH6sUaKdGfMi3oNtVyRxEqB"


def settings(**tokens: object) -> AccessSettings:
    values: dict[str, object] = {
        "default_ttl_days": 90,
        "max_ttl_days": 365,
        "worker_ttl_hours": 168,
        "worker_rotate_before_hours": 48,
        "rotation_grace_minutes": 10,
        "assignment_permissions": ("plan.read",),
        "assignment_ttl_slack_seconds": 60,
    }
    values.update(tokens)
    return AccessSettings(
        tokens=AccessTokensSettings(**values),  # type: ignore[arg-type]
        audit=AccessAuditSettings(record_allowed=True),
    )


def entropy_of(byte: int):
    return lambda n: bytes([byte]) * n


def token(**overrides: object) -> ApiToken:
    secret = generate_secret(entropy_of(7))
    fields: dict[str, object] = {
        "id": TOKEN_ID,
        "principal_id": OWNER,
        "kind": TokenKind.PERSONAL,
        "name": "laptop",
        "prefix": secret.prefix,
        "secret_hash": hash_secret(secret, PEPPER),
        "scope_id": None,
        "permissions": None,
        "expires_at": NOW + timedelta(days=30),
        "created_at": NOW - timedelta(days=1),
        "created_by": OWNER,
        "last_used_at": None,
        "revoked_at": None,
        "revoked_by": None,
        "assignment_id": None,
        "step_id": None,
        "superseded_by": None,
    }
    fields.update(overrides)
    return ApiToken(**fields)  # type: ignore[arg-type]


def principal(
    kind: PrincipalKind = PrincipalKind.HUMAN, state: PrincipalState = PrincipalState.ACTIVE
) -> Principal:
    return Principal(OWNER, kind, "Owner", state, 1, NOW, None)


# --- secret ---


def test_generated_secret_matches_the_documented_format() -> None:
    secret = generate_secret(entropy_of(0xAB))
    assert FORMAT.fullmatch(str(secret))
    assert len(str(secret)) == 70
    assert len(secret.prefix) == 13
    assert len(secret.random) == 43


def test_generate_secret_uses_five_and_thirty_two_bytes_of_entropy() -> None:
    asked: list[int] = []

    def entropy(n: int) -> bytes:
        asked.append(n)
        return bytes(range(n))

    generate_secret(entropy)
    assert asked == [5, 32]


def test_different_entropy_gives_different_secrets() -> None:
    assert str(generate_secret(entropy_of(1))) != str(generate_secret(entropy_of(2)))


def test_generate_secret_rejects_a_short_entropy_source() -> None:
    with pytest.raises(ValueError, match="entropy"):
        generate_secret(lambda n: b"\x00" * (n - 1))


def test_repr_and_str_of_a_secret() -> None:
    secret = generate_secret(entropy_of(9))
    assert str(secret).startswith(f"skm_{secret.prefix}_{secret.random}_")
    assert repr(secret) == f"TokenSecret(prefix='{secret.prefix}', random=***)"
    assert secret.random not in repr(secret)
    rendered = {"s": secret}
    assert secret.random not in f"{secret!r} {[secret]} {rendered}"


@pytest.mark.parametrize(
    ("prefix", "random"),
    [
        ("ABCDEFGH", "a" * 43),
        ("abcdefg", "a" * 43),
        ("abcdef18", "a" * 43),
        ("abcdefgh", "a" * 42),
        ("abcdefgh", "a+" * 21 + "a"),
    ],
)
def test_token_secret_rejects_malformed_parts(prefix: str, random: str) -> None:
    with pytest.raises(ValueError, match="malformed"):
        TokenSecret(prefix=prefix, random=random)


def test_parse_secret_roundtrip_and_example() -> None:
    secret = generate_secret(entropy_of(3))
    assert parse_secret(str(secret)) == secret
    assert str(parse_secret(EXAMPLE)) == EXAMPLE


@pytest.mark.parametrize(
    "text",
    [
        "",
        "skm_",
        EXAMPLE + "\n",
        " " + EXAMPLE,
        EXAMPLE[:-1],
        EXAMPLE + "x",
        EXAMPLE.replace("skm_", "SKM_"),
        EXAMPLE.replace("k7q2mzpa", "K7Q2MZPA"),
        EXAMPLE.replace("k7q2mzpa", "k7q2mzp1"),
        EXAMPLE[:-1] + "=",
        "skm_k7q2mzpa-" + EXAMPLE[13:],
    ],
)
def test_parse_secret_rejects_malformed_text(text: str) -> None:
    with pytest.raises(ValidationFailed) as caught:
        parse_secret(text)
    assert caught.value.code is ErrorCode.INVALID_REFERENCE
    assert caught.value.details == {"field": "token"}
    assert EXAMPLE[:12] not in str(caught.value.to_problem())


def test_parse_secret_rejects_non_text() -> None:
    with pytest.raises(ValidationFailed):
        parse_secret(None)  # type: ignore[arg-type]


# --- hash ---


def test_hash_is_deterministic_for_one_pepper_and_differs_for_another() -> None:
    secret = parse_secret(EXAMPLE)
    assert hash_secret(secret, PEPPER) == hash_secret(secret, PEPPER)
    assert len(hash_secret(secret, PEPPER)) == 32
    assert hash_secret(secret, PEPPER) != hash_secret(secret, OTHER_PEPPER)


def test_hash_differs_for_a_different_secret() -> None:
    assert hash_secret(generate_secret(entropy_of(1)), PEPPER) != hash_secret(
        generate_secret(entropy_of(2)), PEPPER
    )


def test_hash_matches_the_documented_hmac() -> None:
    import hashlib
    import hmac

    secret = parse_secret(EXAMPLE)
    assert hash_secret(secret, PEPPER) == hmac.new(PEPPER, EXAMPLE.encode("ascii"), hashlib.sha256).digest()


def test_short_pepper_is_a_configuration_error() -> None:
    with pytest.raises(ValueError, match="32"):
        hash_secret(parse_secret(EXAMPLE), b"x" * 31)
    hash_secret(parse_secret(EXAMPLE), b"x" * 32)


def test_verify_secret() -> None:
    secret = generate_secret(entropy_of(7))
    stored = token()
    assert verify_secret(secret, stored, PEPPER)
    assert not verify_secret(generate_secret(entropy_of(8)), stored, PEPPER)
    assert not verify_secret(secret, stored, OTHER_PEPPER)


def test_verify_secret_compares_in_constant_time(monkeypatch: pytest.MonkeyPatch) -> None:
    import hmac

    calls: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(a: bytes, b: bytes) -> bool:
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    secret = generate_secret(entropy_of(7))
    verify_secret(secret, token(), PEPPER)
    assert len(calls) == 1


# --- usability and live check ---


def test_token_is_usable_cases() -> None:
    assert token_is_usable(token(), NOW)
    assert token_is_usable(token(expires_at=None), NOW)
    assert not token_is_usable(token(expires_at=NOW), NOW)  # the expiry instant is already expired
    assert not token_is_usable(token(expires_at=NOW - timedelta(seconds=1)), NOW)
    assert not token_is_usable(token(revoked_at=NOW - timedelta(days=1), revoked_by=OWNER), NOW)
    assert not token_is_usable(token(expires_at=None, revoked_at=NOW, revoked_by=OWNER), NOW)


def test_naive_now_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        token_is_usable(token(), datetime(2026, 1, 1))  # noqa: DTZ001


def test_token_state() -> None:
    assert token_state(token(), NOW) is TokenState.ACTIVE
    assert token_state(token(expires_at=NOW), NOW) is TokenState.EXPIRED
    assert token_state(token(revoked_at=NOW, revoked_by=OWNER), NOW) is TokenState.REVOKED
    expired_and_revoked = token(expires_at=NOW - timedelta(days=1), revoked_at=NOW, revoked_by=OWNER)
    assert token_state(expired_and_revoked, NOW) is TokenState.REVOKED


def unusable_cases() -> list[tuple[ApiToken, Principal]]:
    return [
        (token(), principal(state=PrincipalState.DISABLED)),
        (token(revoked_at=NOW - timedelta(seconds=1), revoked_by=OWNER), principal()),
        (token(expires_at=NOW), principal()),
        (token(principal_id=PrincipalId(UUID(int=2))), principal()),
        (token(kind=TokenKind.WORKER), principal(PrincipalKind.HUMAN)),
    ]


def test_disabled_revoked_and_expired_fail_identically() -> None:
    problems = []
    for stored, owner in unusable_cases():
        with pytest.raises(Unauthenticated) as caught:
            ensure_token_usable(stored, owner, NOW)
        problems.append(caught.value.to_problem())
    assert problems[0]["code"] == "UNAUTHENTICATED"
    assert all(problem == problems[0] for problem in problems)
    assert problems[0]["details"] == {}


def test_a_usable_token_of_an_active_principal_passes() -> None:
    ensure_token_usable(token(), principal(), NOW)
    ensure_token_usable(token(expires_at=None), principal(), NOW)


def test_grant_of_carries_the_token_narrowing() -> None:
    scope = ScopeId(UUID(int=99))
    grant = grant_of(token(scope_id=scope, permissions=frozenset({"plan.read"})), scope_ancestors=(scope,))
    assert (grant.token_id, grant.kind, grant.scope_id) == (TOKEN_ID, "personal", scope)
    assert grant.permissions == {"plan.read"}
    assert grant.scope_ancestors == (scope,)
    assert grant.assignment_id is None


# --- expiry ---


def test_personal_expiry_default_and_requested() -> None:
    config = settings()
    assert token_expiry(TokenKind.PERSONAL, None, NOW, config) == NOW + timedelta(days=90)
    requested = NOW + timedelta(days=10)
    assert token_expiry(TokenKind.PERSONAL, requested, NOW, config) == requested
    assert token_expiry(TokenKind.PERSONAL, NOW + timedelta(days=365), NOW, config) == NOW + timedelta(
        days=365
    )


def test_personal_expiry_beyond_the_maximum_is_refused() -> None:
    with pytest.raises(ValidationFailed) as caught:
        token_expiry(TokenKind.PERSONAL, NOW + timedelta(days=365, seconds=1), NOW, settings())
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details == {"field": "expires_at", "reason": "exceeds_max_ttl"}


def test_personal_expiry_in_the_past_is_refused() -> None:
    for moment in (NOW, NOW - timedelta(days=1)):
        with pytest.raises(ValidationFailed) as caught:
            token_expiry(TokenKind.PERSONAL, moment, NOW, settings())
        assert caught.value.details["reason"] == "not_in_future"


def test_personal_without_ttl_defaults() -> None:
    unlimited = settings(default_ttl_days=0, max_ttl_days=0)
    assert token_expiry(TokenKind.PERSONAL, None, NOW, unlimited) is None
    assert token_expiry(TokenKind.PERSONAL, NOW + timedelta(days=5000), NOW, unlimited) == NOW + timedelta(
        days=5000
    )
    # a maximum with "no expiry" default would let a token live forever: refused, not silently unlimited
    inconsistent = settings(default_ttl_days=0, max_ttl_days=30)
    with pytest.raises(ValidationFailed) as caught:
        token_expiry(TokenKind.PERSONAL, None, NOW, inconsistent)
    assert caught.value.details["reason"] == "exceeds_max_ttl"


def test_naive_requested_expiry_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="timezone"):
        token_expiry(TokenKind.PERSONAL, datetime(2027, 1, 1), NOW, settings())  # noqa: DTZ001


# --- revoke ---


def test_revoke_sets_revocation_and_is_idempotent() -> None:
    revoked = revoke(token(), OWNER, NOW)
    assert (revoked.revoked_at, revoked.revoked_by) == (NOW, OWNER)
    assert not token_is_usable(revoked, NOW)
    again = revoke(revoked, PrincipalId(UUID(int=5)), NOW + timedelta(hours=1))
    assert again is revoked


# --- rotation ---

NEW_ID = TokenId(UUID(int=11))
NEW_HASH = b"\x01" * 32
GRACE = timedelta(minutes=10)


def do_rotate(old: ApiToken, grace: timedelta = GRACE, **kwargs: object) -> tuple[ApiToken, ApiToken]:
    return rotate(
        old,
        new_id=NEW_ID,
        new_secret_hash=NEW_HASH,
        new_prefix="abcdefgh",
        now=NOW,
        settings=settings(),
        grace=grace,
        **kwargs,  # type: ignore[arg-type]
    )


def test_rotation_keeps_binding_and_supersedes_the_old_token() -> None:
    scope = ScopeId(UUID(int=77))
    old = token(scope_id=scope, permissions=frozenset({"plan.read"}), expires_at=NOW + timedelta(days=30))
    superseded, new = do_rotate(old)
    assert superseded.superseded_by == NEW_ID
    assert superseded.expires_at == NOW + GRACE
    assert token_is_usable(superseded, NOW)
    assert not token_is_usable(superseded, NOW + GRACE)
    assert (new.principal_id, new.kind, new.name) == (old.principal_id, old.kind, old.name)
    assert (new.scope_id, new.permissions) == (scope, frozenset({"plan.read"}))
    assert (new.id, new.prefix, new.secret_hash) == (NEW_ID, "abcdefgh", NEW_HASH)
    assert new.expires_at == NOW + timedelta(days=90)
    assert (new.created_at, new.created_by) == (NOW, old.created_by)
    assert (new.last_used_at, new.revoked_at, new.superseded_by) == (None, None, None)


def test_rotation_records_the_rotating_principal_when_given() -> None:
    operator = PrincipalId(UUID(int=42))
    assert do_rotate(token(), created_by=operator)[1].created_by == operator


def test_old_token_never_outlives_its_own_expiry() -> None:
    soon = NOW + timedelta(minutes=3)
    assert do_rotate(token(expires_at=soon))[0].expires_at == soon


def test_old_token_without_expiry_gets_the_grace_end() -> None:
    superseded, new = do_rotate(token(expires_at=None))
    assert superseded.expires_at == NOW + GRACE
    assert new.expires_at == NOW + timedelta(days=90)


def test_grace_zero_makes_the_old_token_unusable_at_once() -> None:
    superseded, _ = do_rotate(token(), grace=timedelta(0))
    assert not token_is_usable(superseded, NOW)


def test_negative_grace_is_refused() -> None:
    with pytest.raises(ValueError, match="grace"):
        do_rotate(token(), grace=timedelta(seconds=-1))


def test_worker_rotation_uses_the_worker_lifetime() -> None:
    old = token(kind=TokenKind.WORKER, expires_at=NOW + timedelta(hours=10))
    assert do_rotate(old)[1].expires_at == NOW + timedelta(hours=168)


def rotation_refusals() -> list[ApiToken]:
    step = UUID(int=3)
    return [
        token(revoked_at=NOW - timedelta(seconds=1), revoked_by=OWNER),
        token(expires_at=NOW),
        token(superseded_by=TokenId(UUID(int=12))),
        token(
            kind=TokenKind.ASSIGNMENT,
            scope_id=ScopeId(UUID(int=7)),
            permissions=frozenset({"plan.read"}),
            assignment_id=UUID(int=2),
            step_id=step,
        ),
    ]


@pytest.mark.parametrize("old", rotation_refusals(), ids=["revoked", "expired", "superseded", "assignment"])
def test_rotation_refusals(old: ApiToken) -> None:
    with pytest.raises(PreconditionFailed) as caught:
        do_rotate(old)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION
    assert caught.value.details == {"reason": "token_not_rotatable"}


def test_rotating_a_second_time_is_refused() -> None:
    superseded, _ = do_rotate(token())
    with pytest.raises(PreconditionFailed):
        do_rotate(superseded)


def test_rotation_into_the_same_id_is_refused() -> None:
    with pytest.raises(PreconditionFailed):
        rotate(
            token(),
            new_id=TOKEN_ID,
            new_secret_hash=NEW_HASH,
            new_prefix="abcdefgh",
            now=NOW,
            settings=settings(),
            grace=GRACE,
        )


# --- record invariants and immutable binding ---


def test_api_token_rejects_a_bad_record() -> None:
    bad = [
        {"name": ""},
        {"name": "x" * 101},
        {"prefix": "SHORT"},
        {"secret_hash": b"\x00" * 31},
        {"expires_at": datetime(2030, 1, 1)},  # noqa: DTZ001
        {"kind": TokenKind.WORKER, "expires_at": None},
        {"revoked_at": NOW},
        {"revoked_by": OWNER},
        {"superseded_by": TOKEN_ID},
        {"assignment_id": UUID(int=2)},
        {"step_id": UUID(int=3)},
    ]
    for overrides in bad:
        with pytest.raises((ValueError, TypeError)):
            token(**overrides)


def test_api_token_accepts_the_edge_values() -> None:
    token(name="x" * 100)
    token(kind=TokenKind.WORKER, expires_at=NOW + timedelta(hours=1))
    token(expires_at=None)


def test_save_guard_allows_revocation_rotation_and_touch_only() -> None:
    stored = token()
    ensure_binding_unchanged(stored, revoke(stored, OWNER, NOW))
    ensure_binding_unchanged(stored, do_rotate(stored)[0])
    ensure_binding_unchanged(stored, dataclasses.replace(stored, last_used_at=NOW))
    for changed in (
        {"principal_id": PrincipalId(UUID(int=2))},
        {"prefix": "zzzzzzzz"},
        {"secret_hash": b"\x02" * 32},
        {"scope_id": ScopeId(UUID(int=4))},
        {"permissions": frozenset({"plan.read"})},
        {"kind": TokenKind.WORKER},
    ):
        with pytest.raises(ValueError, match="keeps its identity"):
            ensure_binding_unchanged(stored, dataclasses.replace(stored, **changed))


def test_live_checksum_rejects_tampering_and_its_removal() -> None:
    rendered = str(generate_secret(entropy_of(7)))
    body, checksum = rendered.rsplit("_", 1)
    assert parse_secret(rendered).prefix.startswith("live_")
    for malformed in (body, f"{body}_{'0' if checksum[0] != '0' else '1'}{checksum[1:]}"):
        with pytest.raises(ValidationFailed, match="malformed token"):
            parse_secret(malformed)
