"""``authenticate_token`` and the identity queries (access §13, §8, §15).

Every way a bearer secret can fail is one ``UNAUTHENTICATED`` with one message. The queries are read
through the bus on live state: ``whoami`` of a credential revoked after the ``Actor`` was built no longer
answers.
"""

from datetime import timedelta
from pathlib import Path
from runpy import run_path
from typing import Any

import pytest

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, SkmError, Unauthenticated, ValidationFailed
from skm.modules.access.domain.roles import ROLE_PERMISSIONS, Role
from skm.modules.access.domain.token import TokenKind, generate_secret
from skm.modules.access.public import authenticate_token

h = run_path(str(Path(__file__).with_name("test_create_token.py")))
world, create = h["world"], h["create"]
commands, queries = h["commands"], h["queries"]
WS, WS2, P1, PLAN1, RUN1, INSTANCE, PEPPER, NOW = (
    h[n] for n in ("WS", "WS2", "P1", "PLAN1", "RUN1", "INSTANCE", "PEPPER", "NOW")
)


def failure(made: Any, text: str, *, pepper: bytes = PEPPER) -> Unauthenticated:
    with made.uow(readonly=True) as uow, pytest.raises(Unauthenticated) as caught:
        authenticate_token(uow, text, pepper=pepper, now=made.clock.now())
    return caught.value


# ---------------------------------------------------------------------------------------------------------
# authenticate_token


def test_a_valid_secret_gives_the_actor_of_the_principal_record_with_its_grant() -> None:
    w = world()
    made = w["h"]
    made.token("scoped", w["alice"], scope_id=PLAN1, permissions={"plan.read", "token.own"}, name="scoped")
    actor = made.actor("scoped")
    assert (actor.principal_id, actor.kind, actor.display_name) == (w["alice"], PrincipalKind.HUMAN, "alice")
    grant = actor.grant
    assert grant is not None
    assert (grant.kind, grant.scope_id, grant.permissions) == ("personal", PLAN1, {"plan.read", "token.own"})
    assert grant.scope_ancestors == (INSTANCE, WS, P1)  # the ancestors of the scope, instance first
    assert (grant.assignment_id, grant.step_id) == (None, None)
    plain = made.actor("alice").grant
    assert plain is not None
    assert plain.scope_id is None
    assert plain.scope_ancestors == ()


def test_every_failure_is_the_same_unauthenticated() -> None:
    w = world()
    made = w["h"]
    good = made.secrets["alice"]
    prefix, random = good[: len("skm_") + 8], good[len("skm_") + 8 + 1 :]
    made.token("revoked", w["alice"], name="revoked")
    made.token("expired", w["alice"], expires_in=timedelta(minutes=5), name="expired")
    made.token("bobs", w["bob"], name="bobs")
    made.run(commands.RevokeToken(token_id=made.actor("revoked").grant.token_id), made.actor("revoked"))
    made.run(
        commands.DisablePrincipal(principal_id=w["bob"], expected_row_version=1, reason="left"),
        made.actor("owner"),
    )
    made.clock.advance(timedelta(minutes=5))
    unknown = str(generate_secret(made.entropy.bytes))
    cases = {
        "empty": "",
        "garbage": "not a token",
        "no prefix": random,
        "short random": f"{prefix}_{random[:10]}",
        "unknown prefix": unknown,
        "wrong random": f"{prefix}_{'B' * 43}",
        "revoked": made.secrets["revoked"],
        "expired": made.secrets["expired"],
        "disabled principal": made.secrets["bobs"],
    }
    errors = {name: failure(made, text) for name, text in cases.items()}
    errors["wrong pepper"] = failure(made, good, pepper=bytes(range(1, 33)))
    shapes = {(e.code, e.message, tuple(e.details.items())) for e in errors.values()}
    assert shapes == {(ErrorCode.UNAUTHENTICATED, "invalid or expired token", ())}
    for text in (*cases.values(), good):
        assert all(text not in str(e) or text == "" for e in errors.values())
    assert made.actor("alice").principal_id == w["alice"]  # the good secret still works


def test_a_secret_of_a_token_whose_scope_disappeared_is_unauthenticated() -> None:
    w = world()
    made = w["h"]
    made.token("lost", w["alice"], scope_id=PLAN1, name="lost")
    del made.backend.committed.core.scopes[PLAN1]  # the scope row is gone: the credential cannot be placed
    assert failure(made, made.secrets["lost"]).code is ErrorCode.UNAUTHENTICATED


def test_the_actor_kind_comes_from_the_record_and_a_kind_mismatch_is_unauthenticated() -> None:
    w = world()
    made = w["h"]
    worker = made.principal("w1", PrincipalKind.WORKER, {WS: Role.WORKER})
    made.token("worker", worker, kind=TokenKind.WORKER, expires_in=timedelta(hours=1), name="worker")
    assert made.actor("worker").kind is PrincipalKind.WORKER
    made.token("mismatch", worker, kind=TokenKind.PERSONAL, name="mismatch")  # a personal token on a worker
    assert failure(made, made.secrets["mismatch"]).code is ErrorCode.UNAUTHENTICATED


# ---------------------------------------------------------------------------------------------------------
# whoami


def test_whoami_reports_principal_token_memberships_and_effective_permissions() -> None:
    w = world()
    made = w["h"]
    view = made.ask(queries.WhoAmI(), made.actor("alice"))
    assert (view.principal.principal_id, view.principal.state, view.principal.kind.value) == (
        w["alice"],
        "active",
        "human",
    )
    assert view.token is not None
    assert view.token.name == "alice"
    assert view.token.state == "active"
    assert [(m.scope_id, m.scope_kind, m.role.value) for m in view.memberships] == [
        (WS, "workspace", "member")
    ]
    assert view.effective_permissions == ("token.own",)  # on the instance she holds only the self right
    in_workspace = made.ask(queries.WhoAmI(scope_id=WS), made.actor("alice"))
    assert set(in_workspace.effective_permissions) == ROLE_PERMISSIONS[Role.MEMBER] - {"config.write"}
    assert set(in_workspace.permissions_by_scope[str(WS)]) == set(in_workspace.effective_permissions)
    assert in_workspace.events_cursor is not None
    assert view.events_cursor is None
    assert set(in_workspace.modules) == {"knowledge", "learning", "exports"}


def test_whoami_applies_the_token_ceiling_to_the_permissions_it_reports() -> None:
    w = world()
    made = w["h"]
    made.token("narrow", w["alice"], scope_id=P1, permissions={"plan.read", "token.own"}, name="narrow")
    view = made.ask(queries.WhoAmI(scope_id=P1), made.actor("narrow"))
    assert set(view.effective_permissions) == {"plan.read", "token.own"}
    assert view.token is not None
    assert view.token.scope_id == P1
    assert view.token.permissions == (
        "plan.read",
        "token.own",
    )


def test_whoami_checks_the_credential_live_not_the_actor_in_hand() -> None:
    w = world()
    made = w["h"]
    made.run(create("other"), made.actor("alice"))
    alice = made.actor("alice")
    made.run(commands.RevokeToken(token_id=alice.grant.token_id), made.actor("owner"))
    with pytest.raises(Unauthenticated):
        made.ask(queries.WhoAmI(), alice)


# ---------------------------------------------------------------------------------------------------------
# the other queries


def test_get_principal_is_open_to_oneself_and_to_principal_manage() -> None:
    w = world()
    made = w["h"]
    own = made.ask(queries.GetPrincipal(principal_id=w["alice"]), made.actor("alice"))
    assert (own.display_name, own.row_version, own.identities) == ("alice", 1, ())
    with pytest.raises(Forbidden) as caught:
        made.ask(queries.GetPrincipal(principal_id=w["bob"]), made.actor("alice"))
    assert caught.value.details["permission"] == "principal.manage"
    assert made.ask(queries.GetPrincipal(principal_id=w["bob"]), made.actor("owner")).display_name == "bob"
    with pytest.raises(SkmError) as missing:
        made.ask(queries.GetPrincipal(principal_id=made.ids.new_id()), made.actor("owner"))
    assert missing.value.code is ErrorCode.NOT_FOUND


def test_list_principals_pages_by_keyset_and_needs_principal_manage() -> None:
    w = world()
    made = w["h"]
    with pytest.raises(Forbidden):
        made.ask(queries.ListPrincipals(), made.actor("alice"))
    first = made.ask(queries.ListPrincipals(limit=2), made.actor("owner"))
    assert len(first.items) == 2
    assert first.next is not None
    rest = made.ask(queries.ListPrincipals(limit=2, after=first.next), made.actor("owner"))
    names = [p.display_name for p in (*first.items, *rest.items)]
    assert names == ["owner", "alice", "bob"]
    assert rest.next is None
    humans = made.ask(queries.ListPrincipals(kind=queries.PrincipalKind.HUMAN), made.actor("owner"))
    assert len(humans.items) == 3
    with pytest.raises(ValidationFailed):
        made.ask(queries.ListPrincipals(after="!!not-a-cursor!!"), made.actor("owner"))


def test_list_tokens_are_own_by_default_and_another_principals_need_token_any() -> None:
    w = world()
    made = w["h"]
    mine = made.ask(queries.ListTokens(), made.actor("alice"))
    assert [t.name for t in mine.items] == ["alice"]
    with pytest.raises(Forbidden) as caught:
        made.ask(queries.ListTokens(principal_id=w["bob"]), made.actor("alice"))
    assert caught.value.details["permission"] == "token.any"
    assert [
        t.name for t in made.ask(queries.ListTokens(principal_id=w["bob"]), made.actor("owner")).items
    ] == ["bob"]
    made.token("expired", w["alice"], expires_in=timedelta(minutes=1), name="expired")
    made.clock.advance(timedelta(minutes=2))
    active = made.ask(queries.ListTokens(), made.actor("alice"))
    everything = made.ask(queries.ListTokens(include_inactive=True), made.actor("alice"))
    assert {t.name for t in active.items} == {"alice"}
    assert {t.name: t.state for t in everything.items} == {"alice": "active", "expired": "expired"}
    only_workers = made.ask(queries.ListTokens(kind=queries.TokenKind.WORKER), made.actor("alice"))
    assert only_workers.items == ()


def test_list_memberships_by_scope_or_principal() -> None:
    w = world()
    made = w["h"]
    members = made.ask(queries.ListMemberships(scope_id=WS), made.actor("bob"))  # a viewer reads the roster
    assert {(m.display_name, m.role.value) for m in members.items} == {("alice", "member"), ("bob", "viewer")}
    own = made.ask(queries.ListMemberships(principal_id=w["bob"]), made.actor("bob"))
    assert [m.scope_kind for m in own.items] == ["workspace"]
    with pytest.raises(Forbidden):  # another workspace's roster is not for a member of this one
        made.ask(queries.ListMemberships(scope_id=WS2), made.actor("bob"))
    with pytest.raises(Forbidden):
        made.ask(queries.ListMemberships(principal_id=w["alice"]), made.actor("bob"))
    assert len(made.ask(queries.ListMemberships(principal_id=w["alice"]), made.actor("owner")).items) == 1
    with pytest.raises(ValidationFailed):
        made.ask(queries.ListMemberships(), made.actor("owner"))
