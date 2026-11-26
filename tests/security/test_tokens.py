"""Token secrets and token lifetimes on memory and PostgreSQL (access §4.2, §5, §7.3, §7.3a, §11, §15).

A plaintext secret leaves the system once, in the result of ``create_token`` or ``rotate_token``. It is never
in a stored row of any ``skm_*`` table (tokens, events, audit, idempotency receipts, outbox), in the process
logs or in an error, and the token row holds only the 32-byte peppered hash. An expired, revoked, superseded
past its grace, unknown or mistyped secret and the secret of a disabled principal all fail authentication
with one code and one message. The backends are those of ``tests/contracts/access/test_repositories.py``;
the concurrent owner, rotation and revoke cases live there as well.
"""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from runpy import run_path
from typing import Any

import pytest

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, Unauthenticated
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access.domain.principal import disable
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import TokenId, parse_secret
from skm.modules.access.ports import PrincipalRepository, TokenRepository
from skm.modules.access.public import authenticate_token
from support.pg import clean_test_database, pg_session, test_database  # noqa: F401

r = run_path(str(Path(__file__).parents[1] / "contracts" / "access" / "test_repositories.py"))
side = r["side"]
Side, commands, PEPPER, WS = r["Side"], r["commands"], r["PEPPER"], r["WS"]


def human(principal_id: Any) -> Actor:
    return Actor(principal_id=principal_id, kind=PrincipalKind.HUMAN, display_name="tester")


def authenticate(made: Any, secret: str) -> Actor:
    with made.uow(readonly=True) as uow:
        return authenticate_token(uow, secret, pepper=PEPPER, now=made.clock.now())


def refused(made: Any, secret: str) -> Unauthenticated:
    with pytest.raises(Unauthenticated) as caught:
        authenticate(made, secret)
    assert caught.value.code is ErrorCode.UNAUTHENTICATED
    return caught.value


def leaks(secret: str) -> tuple[str, str]:
    """The whole secret and its random part: neither may appear anywhere."""
    return secret, parse_secret(secret).random


def test_a_secret_is_returned_once_and_stored_logged_or_echoed_nowhere(
    side: Any, capfd: pytest.CaptureFixture[str]
) -> None:
    ann = side.principal("ann", roles={WS: Role.MEMBER})
    actor = human(ann)
    created = side.run(commands.CreateToken(name="laptop"), actor)
    side.clock.advance(timedelta(minutes=1))
    rotated = side.run(commands.RotateToken(token_id=created.token_id, grace_minutes=5), actor)
    seeded, seeded_secret = side.token(ann, "seeded")
    errors: list[SkmError] = []
    keyed = RequestMeta("req_KEYED_CREATE", Surface.TEST, "key-1", side.clock.now())
    with pytest.raises(SkmError) as not_idempotent:  # a secret-bearing command refuses an Idempotency-Key
        side.bus().dispatch(commands.CreateToken(name="again"), actor=actor, meta=keyed)
    assert not_idempotent.value.code is ErrorCode.SCHEMA_INVALID
    errors.append(not_idempotent.value)
    receipt = RequestMeta("req_KEYED_REVOKE", Surface.TEST, "key-2", side.clock.now())
    side.bus().dispatch(commands.RevokeToken(token_id=seeded.id), actor=actor, meta=receipt)  # a receipt
    mistyped = seeded_secret[:-1] + ("A" if seeded_secret[-1] != "A" else "B")
    errors.extend(refused(side, secret) for secret in (seeded_secret, mistyped))
    with pytest.raises(SkmError) as malformed:
        authenticate(side, created.secret + "x")
    errors.append(malformed.value)
    secrets = [created.secret, rotated.secret, seeded_secret]
    assert len(set(secrets)) == 3
    stored = side.stored_text()
    logged = "".join(capfd.readouterr())
    echoed = "\n".join(f"{e}\n{e!r}\n{e.details}\n{e.__cause__!r}" for e in errors)
    for secret in secrets:
        for fragment in leaks(secret):
            assert fragment not in stored
            assert fragment not in logged
            assert fragment not in echoed
    assert parse_secret(created.secret).prefix in stored  # the public prefix is the lookup key
    with side.uow(readonly=True) as uow:
        token = uow.repo(TokenRepository).get(TokenId(rotated.token_id))
    assert len(token.secret_hash) == 32
    assert token.secret_hash not in rotated.secret.encode()


def test_every_dead_credential_fails_alike(side: Any) -> None:
    ann = side.principal("ann", roles={WS: Role.MEMBER})
    bob = side.principal("bob", roles={WS: Role.MEMBER})
    _, live = side.token(ann, "live", expires_in=None)
    _, expiring = side.token(ann, "expiring", expires_in=timedelta(hours=1))
    revoked, revoked_secret = side.token(ann, "revoked")
    _, disabled_secret = side.token(bob, "bob")
    side.run(commands.RevokeToken(token_id=revoked.id), human(ann))
    with side.uow() as uow:
        principals = uow.repo(PrincipalRepository)
        principals.save(disable(principals.get(bob)), expected_version=1)
        uow.commit()
    assert authenticate(side, live).principal_id == ann
    assert authenticate(side, expiring).principal_id == ann
    side.clock.advance(timedelta(hours=1))  # expires_at <= now: expired
    unknown = "skm_aaaaaaaa_" + parse_secret(live).random
    wrong = live[:-1] + ("A" if live[-1] != "A" else "B")
    failures = [refused(side, s) for s in (expiring, revoked_secret, disabled_secret, unknown, wrong)]
    assert len({(str(f), repr(f.details)) for f in failures}) == 1  # nothing tells which check failed
    assert authenticate(side, live).principal_id == ann


@pytest.mark.parametrize("grace", [10, 0])
def test_a_rotated_secret_lives_only_through_its_grace(side: Any, grace: int) -> None:
    ann = side.principal("ann", roles={WS: Role.MEMBER})
    _, endless = side.token(ann, "desk", expires_in=None)  # an old token without expiry gets one too
    actor = human(ann)
    first = side.run(commands.CreateToken(name="laptop"), actor)
    side.clock.advance(timedelta(minutes=1))
    for old in (first.secret, endless):
        grant = authenticate(side, old).grant
        assert grant is not None
        token_id = grant.token_id
        rotated = side.run(commands.RotateToken(token_id=token_id, grace_minutes=grace), actor)
        assert rotated.previous_expires_at == side.clock.now() + timedelta(minutes=grace)
        if grace:
            side.clock.advance(timedelta(minutes=grace) - timedelta(seconds=1))
            assert authenticate(side, old).principal_id == ann
            side.clock.advance(timedelta(seconds=1))
        refused(side, old)
        assert authenticate(side, rotated.secret).principal_id == ann
        with pytest.raises(SkmError) as again:  # the superseded id never gets a second successor
            side.run(commands.RotateToken(token_id=token_id, grace_minutes=grace), actor)
        assert again.value.code is ErrorCode.INVALID_TRANSITION
        side.clock.advance(timedelta(minutes=1))
    names = sorted(t.name for t in side.tokens_of(ann) if t.superseded_by is None and t.revoked_at is None)
    assert names == ["desk", "laptop"]


def test_a_revoked_token_cannot_be_rotated_or_revived(side: Any) -> None:
    ann = side.principal("ann", roles={WS: Role.MEMBER})
    token, secret = side.token(ann, "laptop")
    side.clock.advance(timedelta(minutes=1))
    side.run(commands.RevokeToken(token_id=token.id), human(ann))
    with pytest.raises(SkmError) as rotation:
        side.run(commands.RotateToken(token_id=token.id, grace_minutes=5), human(ann))
    assert rotation.value.code is ErrorCode.INVALID_TRANSITION
    stale = replace(token, expires_at=token.created_at + timedelta(days=90))
    with side.uow() as uow, pytest.raises(SkmError) as revival:
        uow.repo(TokenRepository).save(stale)
    assert revival.value.code is ErrorCode.INVALID_TRANSITION
    refused(side, secret)
    assert [t.id for t in side.tokens_of(ann)] == [token.id]
