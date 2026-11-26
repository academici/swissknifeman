"""``access.rotate_token`` (access §7.3a, §4.5, §15): one secret out, a bounded overlap, no widening.

Invariants: the new secret is in the one result only; the old token lives out its grace and then answers
``UNAUTHENTICATED`` (also an old personal token without any expiry); a superseded id is never rotated again; a
refused rotation changes nothing and issues no secret, also for another token of the same principal.
"""

from datetime import timedelta
from pathlib import Path
from runpy import run_path
from typing import Any

import pytest

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, Unauthenticated
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import TokenId, TokenKind, parse_secret

h = run_path(str(Path(__file__).with_name("test_create_token.py")))
Harness = h["Harness"]
world, refused, create, restricted = h["world"], h["refused"], h["create"], h["restricted"]
commands, queries = h["commands"], h["queries"]
WS, P1, P2, PLAN1, RUN1, INSTANCE = (h[n] for n in ("WS", "P1", "P2", "PLAN1", "RUN1", "INSTANCE"))
NOW, PEPPER = h["NOW"], h["PEPPER"]


def rotate(token_id: Any, **fields: Any) -> Any:
    return commands.RotateToken(token_id=token_id, **fields)


def dead(made: Any, label_or_secret: str) -> None:
    """The credential no longer authenticates, and says nothing about why."""
    with pytest.raises(Unauthenticated) as caught:
        made.actor(label_or_secret)
    assert caught.value.code is ErrorCode.UNAUTHENTICATED


# ---------------------------------------------------------------------------------------------------------
# the happy path


def test_rotation_issues_one_new_secret_and_keeps_the_name() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("laptop"), made.actor("alice"))
    result = made.run(rotate(first.token_id), made.actor(first.secret))
    assert result.token_id != first.token_id
    assert result.previous_token_id == first.token_id
    assert result.secret != first.secret
    old, new = made.tokens[TokenId(first.token_id)], made.tokens[TokenId(result.token_id)]
    assert old.superseded_by == new.id
    assert (new.name, new.kind, new.principal_id, new.scope_id) == (
        "laptop",
        TokenKind.PERSONAL,
        w["alice"],
        None,
    )
    assert new.created_by == w["alice"]
    assert old.expires_at == NOW + timedelta(minutes=10)  # access.tokens.rotation_grace_minutes
    assert result.previous_expires_at == old.expires_at
    assert result.expires_at == NOW + timedelta(days=90)
    assert made.actor(result.secret).grant.token_id == new.id
    assert parse_secret(result.secret).random not in made.stored_text()
    [event] = [e for e in made.events if e.type.endswith("token-rotated:v1")]
    assert event.payload["token_id"] == str(new.id)
    assert event.payload["previous_token_id"] == str(old.id)
    assert "secret" not in event.payload
    assert made.receipts == []


def test_the_old_token_works_until_the_grace_ends_and_then_not() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("laptop"), made.actor("alice"))
    made.run(rotate(first.token_id, grace_minutes=5), made.actor("alice"))
    made.clock.advance(timedelta(minutes=4))
    assert made.actor(first.secret).principal_id == w["alice"]
    made.clock.advance(timedelta(minutes=1))
    dead(made, first.secret)


def test_an_old_token_without_any_expiry_gets_one_by_rotation() -> None:
    w = world()
    made = w["h"]
    made.token("local-owner", w["owner"], expires_in=None, name="local-owner")
    old_id = made.actor("local-owner").grant.token_id
    result = made.run(rotate(old_id), made.actor("local-owner"))
    assert made.tokens[TokenId(old_id)].expires_at == NOW + timedelta(minutes=10)
    made.clock.advance(timedelta(minutes=10))
    dead(made, "local-owner")
    assert made.actor(result.secret).principal_id == w["owner"]


def test_grace_zero_ends_the_old_token_at_once() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("x"), made.actor("alice"))
    made.run(rotate(first.token_id, grace_minutes=0), made.actor("alice"))
    dead(made, first.secret)


def test_a_superseded_id_is_not_rotated_again_and_no_second_successor_appears() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("x"), made.actor("alice"))
    made.run(rotate(first.token_id), made.actor("alice"))
    count = len(made.tokens)
    error = refused(made, rotate(first.token_id), made.actor("alice"), ErrorCode.INVALID_TRANSITION)
    assert error.details["reason"] == "token_not_rotatable"
    assert len(made.tokens) == count


def test_a_member_of_only_a_workspace_rotates_and_revokes_its_own_token() -> None:
    """``token.own`` needs no membership beyond the workspace one (access §4.4 row 5c)."""
    w = world()
    made = w["h"]
    first = made.run(create("x"), made.actor("alice"))
    second = made.run(rotate(first.token_id), made.actor("alice"))
    made.run(commands.RevokeToken(token_id=second.token_id), made.actor("alice"))
    assert made.tokens[TokenId(second.token_id)].revoked_at == NOW


def test_a_worker_rotates_only_the_token_it_holds_and_keeps_its_kind() -> None:
    w = world()
    made = w["h"]
    worker = made.principal("w1", PrincipalKind.WORKER, {WS: Role.WORKER})
    made.bind_worker(worker, WS)
    current = made.token("w-current", worker, kind=TokenKind.WORKER, expires_in=timedelta(hours=100))
    other = made.token("w-other", worker, kind=TokenKind.WORKER, expires_in=timedelta(hours=100))
    actor = made.actor("w-current")
    error = refused(made, rotate(other), actor, ErrorCode.FORBIDDEN)
    assert error.details["reason"] == "not_current_token"
    result = made.run(rotate(current), actor)
    successor = made.tokens[TokenId(result.token_id)]
    assert successor.kind is TokenKind.WORKER
    assert result.expires_at == NOW + timedelta(hours=168)  # access.tokens.worker_ttl_hours
    assert made.actor(result.secret).kind is PrincipalKind.WORKER


def test_an_assignment_token_is_not_rotatable() -> None:
    w = world()
    made = w["h"]
    worker = made.principal("w1", PrincipalKind.WORKER, {WS: Role.WORKER})
    assignment = made.token(
        "run-token",
        worker,
        kind=TokenKind.ASSIGNMENT,
        scope_id=RUN1,
        permissions={"plan.read"},
        expires_in=timedelta(hours=1),
        assignment_id=made.ids.new_id(),
        step_id=made.ids.new_id(),
    )
    error = refused(made, rotate(assignment), made.actor("owner"), ErrorCode.INVALID_TRANSITION)
    assert error.details["reason"] == "token_not_rotatable"


# ---------------------------------------------------------------------------------------------------------
# who may rotate


def test_someone_elses_token_needs_token_any_and_stays_unchanged_otherwise() -> None:
    w = world()
    made = w["h"]
    bobs = made.run(create("b"), made.actor("bob"))
    error = refused(made, rotate(bobs.token_id), made.actor("alice"), ErrorCode.FORBIDDEN)
    assert error.details["permission"] == "token.any"
    assert made.tokens[TokenId(bobs.token_id)].superseded_by is None
    result = made.run(rotate(bobs.token_id), made.actor("owner"))  # an operator with token.any
    assert made.tokens[TokenId(result.token_id)].principal_id == w["bob"]
    assert made.tokens[TokenId(result.token_id)].created_by == w["owner"]


def test_a_missing_token_is_not_found() -> None:
    w = world()
    made = w["h"]
    refused(made, rotate(made.ids.new_id()), made.actor("alice"), ErrorCode.NOT_FOUND)


def test_a_disabled_principal_is_not_rotated() -> None:
    w = world()
    made = w["h"]
    bobs = made.run(create("b"), made.actor("bob"))
    made.run(
        commands.DisablePrincipal(principal_id=w["bob"], expected_row_version=1, reason="left"),
        made.actor("owner"),
    )
    error = refused(made, rotate(bobs.token_id), made.actor("owner"), ErrorCode.INVALID_TRANSITION)
    assert error.details["reason"] == "principal_disabled"


def test_an_idempotency_key_is_refused() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("x"), made.actor("alice"))
    with pytest.raises(SkmError) as caught:
        made.run(rotate(first.token_id), made.actor("alice"), key="again")
    assert caught.value.details["reason"] == "not_idempotent"
    assert made.tokens[TokenId(first.token_id)].superseded_by is None


# ---------------------------------------------------------------------------------------------------------
# rotation never widens a credential (access §4.5, ench3)


def test_a_restricted_bearer_keeps_its_ceiling_when_it_rotates_itself() -> None:
    w = world()
    made = w["h"]
    bearer = restricted(made, w["alice"], scope=P1, permissions={"token.own", "plan.read"})
    result = made.run(rotate(bearer.grant.token_id), bearer)
    successor = made.tokens[TokenId(result.token_id)]
    assert (successor.scope_id, successor.permissions) == (P1, frozenset({"token.own", "plan.read"}))


@pytest.mark.parametrize(
    ("target", "reason"),
    [
        ({"scope_id": None, "permissions": None}, "token_scope_mismatch"),  # wider: the instance
        ({"scope_id": h["P2"], "permissions": None}, "token_scope_mismatch"),  # sibling scope
        ({"scope_id": h["WS"], "permissions": None}, "token_scope_mismatch"),  # parent scope
        ({"scope_id": h["P1"], "permissions": None}, "token_permission_missing"),  # permissions=null
        ({"scope_id": h["P1"], "permissions": {"token.own", "plan.edit"}}, "token_permission_missing"),
    ],
)
def test_a_restricted_bearer_cannot_rotate_another_own_token_beyond_its_grant(
    target: dict[str, Any], reason: str
) -> None:
    w = world()
    made = w["h"]
    bearer = restricted(made, w["alice"], scope=P1, permissions={"token.own", "plan.read"})
    broader = made.token("broad", w["alice"], **target)  # same principal_id as the bearer
    before_secret_draws = len(made.entropy.requested)
    error = refused(made, rotate(broader), bearer, ErrorCode.FORBIDDEN)
    assert error.details["reason"] == reason
    assert made.tokens[broader].superseded_by is None
    assert len(made.entropy.requested) == before_secret_draws  # no secret was ever drawn


def test_a_narrower_own_token_may_be_rotated_by_a_wider_bearer() -> None:
    w = world()
    made = w["h"]
    bearer = restricted(made, w["alice"], scope=P1, permissions={"token.own", "plan.read", "plan.edit"})
    narrower = made.token("narrow", w["alice"], scope_id=PLAN1, permissions={"plan.read"})
    result = made.run(rotate(narrower), bearer)
    successor = made.tokens[TokenId(result.token_id)]
    assert (successor.scope_id, successor.permissions) == (PLAN1, frozenset({"plan.read"}))


def test_list_tokens_shows_the_chain_but_never_a_secret() -> None:
    w = world()
    made = w["h"]
    first = made.run(create("x"), made.actor("alice"))
    second = made.run(rotate(first.token_id), made.actor("alice"))
    page = made.ask(queries.ListTokens(include_inactive=True), made.actor("alice"))
    by_id = {item.token_id: item for item in page.items}
    assert by_id[first.token_id].superseded_by == second.token_id
    assert by_id[second.token_id].superseded_by is None
    assert first.secret not in str(page)
    assert second.secret not in str(page)
