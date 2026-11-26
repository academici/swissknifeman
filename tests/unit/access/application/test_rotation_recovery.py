"""Rotation after a lost response (access §7.3a, ACCESS-03): one successor, independent recovery.

The client never repeats a secret-bearing request after an unknown outcome. The old id answers
``INVALID_TRANSITION`` so a token has exactly one successor; an operator holding ``token.any`` finds the
active end of the ``superseded_by`` chain from metadata and rotates it with ``grace_minutes=0``. Nothing
recoverable is
kept: no plaintext in receipts, events, audit or the metadata the operator reads.
"""

from datetime import timedelta
from pathlib import Path
from runpy import run_path
from typing import Any

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, Unauthenticated
from skm.modules.access.domain.token import TokenId, parse_secret

h = run_path(str(Path(__file__).with_name("test_create_token.py")))
world, refused, create = h["world"], h["refused"], h["create"]
commands, queries = h["commands"], h["queries"]
NOW = h["NOW"]


def rotate(token_id: Any, **fields: Any) -> Any:
    return commands.RotateToken(token_id=token_id, **fields)


def active_end(made: Any, operator: Any, principal_id: Any, start: Any) -> Any:
    """From metadata alone: follow ``superseded_by`` from ``start`` to the active end of the chain."""
    page = made.ask(queries.ListTokens(principal_id=principal_id, include_inactive=True), operator)
    by_id = {item.token_id: item for item in page.items}
    current = by_id[start]
    while current.superseded_by is not None:
        current = by_id[current.superseded_by]
    return current


def lose_response(made: Any, actor: Any, token_id: Any) -> Any:
    """Commit a rotation and drop its result, as a client that never saw the reply."""
    return made.run(rotate(token_id), actor).token_id


def test_after_a_lost_response_the_old_token_is_usable_only_until_the_grace_ends() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("laptop"), made.actor("alice"))
    lose_response(made, made.actor(first.secret), first.token_id)
    made.clock.advance(timedelta(minutes=9))
    assert made.actor(first.secret).principal_id == w["alice"]
    made.clock.advance(timedelta(minutes=1))
    with pytest.raises(Unauthenticated):
        made.actor(first.secret)


def test_repeating_the_old_id_creates_no_second_successor() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("laptop"), made.actor("alice"))
    successor = lose_response(made, made.actor(first.secret), first.token_id)
    total = len(made.tokens)
    error = refused(made, rotate(first.token_id), made.actor(first.secret), ErrorCode.INVALID_TRANSITION)
    assert error.details["reason"] == "token_not_rotatable"
    refused(made, rotate(first.token_id), made.actor("owner"), ErrorCode.INVALID_TRANSITION)
    assert len(made.tokens) == total
    assert made.tokens[TokenId(first.token_id)].superseded_by == successor
    heads = [t.id for t in made.tokens.values() if t.name == "laptop" and t.superseded_by is None]
    assert heads == [successor]  # exactly one successor, still the end of the chain


def test_an_operator_follows_the_chain_and_rotates_its_active_end_with_no_grace() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("laptop"), made.actor("alice"))
    lost = lose_response(made, made.actor(first.secret), first.token_id)  # the secret of ``lost`` is unknown
    operator = made.actor("owner")  # independent credential with token.any
    end = active_end(made, operator, w["alice"], first.token_id)
    assert end.token_id == lost
    assert end.state == "active"
    recovered = made.run(rotate(end.token_id, grace_minutes=0), operator)
    assert recovered.previous_token_id == lost
    assert made.tokens[TokenId(lost)].expires_at == NOW  # the lost successor is not left usable
    assert made.tokens[TokenId(lost)].superseded_by == recovered.token_id
    assert made.actor(recovered.secret).principal_id == w["alice"]  # the new secret works for the owner
    assert active_end(made, operator, w["alice"], first.token_id).token_id == recovered.token_id
    live = [t for t in made.tokens.values() if t.principal_id == w["alice"] and t.name == "laptop"]
    assert sum(1 for t in live if t.superseded_by is None and t.revoked_at is None) == 1


def test_a_recovery_that_repeats_hits_the_same_rule_and_branches_nothing() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("laptop"), made.actor("alice"))
    lost = lose_response(made, made.actor(first.secret), first.token_id)
    operator = made.actor("owner")
    made.run(rotate(lost, grace_minutes=0), operator)
    total = len(made.tokens)
    refused(made, rotate(lost, grace_minutes=0), operator, ErrorCode.INVALID_TRANSITION)
    assert len(made.tokens) == total  # an unknown recovery outcome is reconciled from metadata, not repeated


def test_recovery_needs_an_independent_credential_with_token_any() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("laptop"), made.actor("alice"))
    lost = lose_response(made, made.actor(first.secret), first.token_id)
    before = made.snapshot()
    with pytest.raises(SkmError) as caught:  # bob is neither the owner nor an operator with token.any
        made.run(rotate(lost, grace_minutes=0), made.actor("bob"))
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert made.snapshot() == before
    made.clock.advance(timedelta(minutes=10))
    with pytest.raises(
        Unauthenticated
    ):  # a lost response and a dead grace leave nothing to authenticate with
        made.actor(first.secret)


def test_a_disabled_target_is_not_given_a_new_token() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("laptop"), made.actor("alice"))
    lost = lose_response(made, made.actor(first.secret), first.token_id)
    operator = made.actor("owner")
    made.run(
        commands.DisablePrincipal(principal_id=w["alice"], expected_row_version=1, reason="offboarded"),
        operator,
    )
    error = refused(made, rotate(lost, grace_minutes=0), operator, ErrorCode.INVALID_TRANSITION)
    assert error.details["reason"] == "principal_disabled"
    assert all(t.revoked_at is not None for t in made.tokens.values() if t.principal_id == w["alice"])


def test_no_plaintext_reaches_receipts_events_audit_or_recovery_metadata() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("laptop"), made.actor("alice"))
    secrets = [parse_secret(first.secret).random]
    second = made.run(rotate(first.token_id), made.actor(first.secret))
    secrets.append(parse_secret(second.secret).random)
    operator = made.actor("owner")
    third = made.run(rotate(second.token_id, grace_minutes=0), operator)
    secrets.append(parse_secret(third.secret).random)
    metadata = str(made.ask(queries.ListTokens(principal_id=w["alice"], include_inactive=True), operator))
    assert made.receipts == []
    for random in secrets:
        assert random not in made.stored_text()
        assert random not in metadata
    assert "secret" not in "".join(str(e.payload) for e in made.events if e.type.endswith("token-rotated:v1"))
