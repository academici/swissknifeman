"""Live credential, principal and membership checks at every request boundary (access §4.6, ACCESS-02).

An ``Actor`` is authenticated once; every later request is admitted again from facts read in the request's
own unit of work, before any handler and before an idempotency receipt is returned. Invariants proved here:

* a token revoked, a principal disabled or a membership removed *before* the admission point refuses the
  command, the receipt replay, the query without a permission of its own (``whoami``) and the embedded client;
  a lost credential is ``UNAUTHENTICATED``, a lost right ``FORBIDDEN``;
* a revoke that commits *after* the admission does not cancel the request that was already admitted: the
  committed mutation stays committed, and the next request is refused again;
* commands are admitted in a ``READ_COMMITTED`` unit of work, queries when the ``REPEATABLE_READ`` snapshot is
  acquired; a revoke after that snapshot does not interrupt the read, the next query reads live again;
* no positive answer is cached between requests, and the trusted kind / grant of an ``Actor`` cannot be
  replaced by fields of the DTO.
"""

from collections.abc import Callable
from pathlib import Path
from runpy import run_path
from threading import Thread
from typing import Any, cast

import pytest

from skm.application_bus.client import EmbeddedClient
from skm.application_bus.ports import AuthzDecision
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ports_uow import Isolation, Surface
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import TokenId
from skm.modules.access.generated import commands, queries
from skm.modules.access.generated.views import WhoAmIView
from skm.modules.access.ports import MembershipRepository

t: dict[str, Any] = run_path(str(Path(__file__).with_name("test_authorizer.py")))
WS, INSTANCE = t["WS"], t["INSTANCE"]
refused, grant, break_principal, rbac_harness = (
    t["refused"],
    t["grant"],
    t["break_principal"],
    t["rbac_harness"],
)


class AfterAdmission:
    """Runs ``fire`` once, on another thread, right after the first allowed decision of the real authorizer.

    The memory backend holds one lock for the whole unit of work, so the thread's own request waits for the
    admitted request to finish and commits after it: a revoke that races an already admitted request.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.fire: Callable[[], object] | None = None
        self.thread: Thread | None = None

    def authorize(self, uow: Any, actor: Actor, permission: str, chain: Any) -> AuthzDecision:
        decision = self._inner.authorize(uow, actor, permission, chain)
        if decision.allowed and self.fire is not None:
            self.thread = Thread(target=self.fire)
            self.fire = None
            self.thread.start()
        return decision

    def admit(self, uow: Any, actor: Actor, permission: str | None = None) -> None:
        self._inner.admit(uow, actor, permission)
        if self.fire is not None:
            self.thread = Thread(target=self.fire)
            self.fire = None
            self.thread.start()

    def finish(self) -> None:
        if self.thread is not None:
            self.thread.join(timeout=30)
            assert not self.thread.is_alive()


class IsolationSpy:
    """Records ``(readonly, isolation)`` of each unit of work the bus opens."""

    def __init__(self, made: Any) -> None:
        self._factory = made.backend.uow_factory()
        self.opened: list[tuple[bool, Isolation]] = []

    def __call__(
        self, meta: Any, *, readonly: bool = False, isolation: Isolation = Isolation.READ_COMMITTED
    ) -> Any:
        self.opened.append((readonly, isolation))
        return self._factory(meta, readonly=readonly, isolation=isolation)


def world(**options: Any) -> dict[str, Any]:
    made = rbac_harness(**options)
    people = {
        "owner": made.principal("owner", roles={INSTANCE: Role.OWNER}),
        "alice": made.principal("alice", roles={WS: Role.MAINTAINER}),
        "bob": made.principal("bob"),
    }
    for label, principal_id in people.items():
        made.token(label, principal_id)
    made.token("alice-second", people["alice"])
    return {"h": made, **people}


def revoke_token(made: Any, label: str, by: str = "owner") -> None:
    token_id = made.actor(label).grant.token_id
    made.run(commands.RevokeToken(token_id=token_id), made.actor(by))


# ------------------------------------------------------------------------------- revoke before admission


def test_a_token_revoked_before_admission_refuses_the_command() -> None:
    w = world()
    made = w["h"]
    alice = made.actor("alice")
    made.run(grant(WS, w["bob"]), alice)  # the old Actor works while the credential lives
    revoke_token(made, "alice")
    error = refused(made, grant(WS, w["bob"], "member"), alice, ErrorCode.UNAUTHENTICATED)
    assert error.message == "invalid or expired token"  # one message for every unusable credential


def test_a_receipt_is_not_replayed_to_a_revoked_credential() -> None:
    w = world()
    made = w["h"]
    alice = made.actor("alice")
    first = made.run(grant(WS, w["bob"]), alice, key="grant-1")
    assert made.run(grant(WS, w["bob"]), alice, key="grant-1") == first  # a live credential replays
    revoke_token(made, "alice")
    refused(made, grant(WS, w["bob"]), alice, ErrorCode.UNAUTHENTICATED)
    with pytest.raises(SkmError) as caught:
        made.run(grant(WS, w["bob"]), alice, key="grant-1")
    assert caught.value.code is ErrorCode.UNAUTHENTICATED  # not the stored result


def test_a_disabled_principal_is_refused_with_and_without_a_receipt() -> None:
    w = world()
    made = w["h"]
    alice = made.actor("alice-second")
    made.run(grant(WS, w["bob"]), alice, key="grant-2")
    break_principal(made, w["alice"])
    refused(made, grant(WS, w["bob"]), alice, ErrorCode.UNAUTHENTICATED)
    with pytest.raises(SkmError) as caught:
        made.run(grant(WS, w["bob"]), alice, key="grant-2")
    assert caught.value.code is ErrorCode.UNAUTHENTICATED


def test_a_lost_membership_is_forbidden_also_for_the_receipt_replay() -> None:
    w = world()
    made = w["h"]
    alice = made.actor("alice")
    first = made.run(grant(WS, w["bob"]), alice, key="grant-3")
    made.run(commands.RevokeMembership(scope_id=WS, principal_id=w["alice"]), made.actor("owner"))
    with pytest.raises(SkmError) as caught:
        made.run(grant(WS, w["bob"]), alice, key="grant-3")
    assert caught.value.code is ErrorCode.FORBIDDEN  # the right is gone; the stored result is not shown
    assert caught.value.details["reason_code"] == "NO_MEMBERSHIP"
    assert first is not None
    assert [row.decision for row in made.audits][-1] == "denied"


def test_whoami_checks_the_credential_although_it_needs_no_permission() -> None:
    w = world()
    made = w["h"]
    alice = made.actor("alice")
    assert made.ask(queries.WhoAmI(), alice).principal.principal_id == w["alice"]
    revoke_token(made, "alice")
    refused(made, queries.WhoAmI(), alice, ErrorCode.UNAUTHENTICATED)
    # another credential of the same principal is unaffected: the check is per token row
    assert made.ask(queries.WhoAmI(), made.actor("alice-second")).principal.principal_id == w["alice"]


def test_the_embedded_client_follows_the_same_rules() -> None:
    w = world()
    made = w["h"]

    def no_events() -> Any:
        raise AssertionError("no event reader is used here")

    client = EmbeddedClient(
        made.bus,
        actor=made.actor("alice"),
        surface=Surface.TEST,
        events=no_events,
        clock=made.clock,
        ids=made.ids,
        client_label="test/memory",
    )
    assert cast("WhoAmIView", client.ask(queries.WhoAmI())).principal.principal_id == w["alice"]
    revoke_token(made, "alice")
    for call in (lambda: client.ask(queries.WhoAmI()), lambda: client.dispatch(grant(WS, w["bob"]))):
        with pytest.raises(SkmError) as caught:
            call()
        assert caught.value.code is ErrorCode.UNAUTHENTICATED


def test_nothing_positive_is_cached_between_requests() -> None:
    w = world()
    made = w["h"]
    alice = made.actor("alice")
    for _ in range(3):
        made.ask(queries.WhoAmI(), alice)
    with made.uow() as uow:  # drop the right directly in the store, no bus involved
        uow.repo(MembershipRepository).delete(WS, w["alice"])
        uow.commit()
    refused(made, grant(WS, w["bob"]), alice, ErrorCode.FORBIDDEN)


# ------------------------------------------------------------------------------ revoke after admission


def test_a_revoke_that_commits_after_admission_does_not_undo_the_admitted_mutation() -> None:
    holder: dict[str, AfterAdmission] = {}

    def wrap(inner: Any, _made: Any) -> AfterAdmission:
        holder["race"] = AfterAdmission(inner)
        return holder["race"]

    w = world(wrap=wrap)
    made, race = w["h"], holder["race"]
    alice = made.actor("alice")
    owner = made.actor("owner")
    alice_token = alice.grant.token_id
    race.fire = lambda: made.run(commands.RevokeToken(token_id=alice_token), owner)
    result = made.run(grant(WS, w["bob"]), alice, key="race-1")  # admitted first, the revoke waits for it
    race.finish()
    assert result.principal_id == w["bob"]
    assert (
        made.tokens[TokenId(alice_token)].revoked_at is not None
    )  # the revoke did commit, after the request
    stored = [e for e in made.events if e.type.endswith("membership-granted:v1")]
    assert [e.payload["principal_id"] for e in stored] == [str(w["bob"])]  # the mutation stays committed
    refused(made, grant(WS, w["bob"], "member"), alice, ErrorCode.UNAUTHENTICATED)  # the next one is refused


def test_a_query_snapshot_is_admitted_at_acquisition_and_a_later_revoke_does_not_interrupt_it() -> None:
    holder: dict[str, AfterAdmission] = {}
    spy: dict[str, IsolationSpy] = {}

    def wrap(inner: Any, _made: Any) -> AfterAdmission:
        holder["race"] = AfterAdmission(inner)
        return holder["race"]

    def factory(made: Any) -> IsolationSpy:
        spy["uow"] = IsolationSpy(made)
        return spy["uow"]

    w = world(wrap=wrap, uow_factory=factory)
    made, race = w["h"], holder["race"]
    alice, owner = made.actor("alice"), made.actor("owner")
    alice_token = alice.grant.token_id
    spy["uow"].opened.clear()
    race.fire = lambda: made.run(commands.RevokeToken(token_id=alice_token), owner)
    view = made.ask(queries.WhoAmI(), alice)  # the snapshot was acquired before the revoke committed
    race.finish()
    assert view.principal.principal_id == w["alice"]
    assert spy["uow"].opened[0] == (True, Isolation.REPEATABLE_READ)  # admission = snapshot acquisition
    refused(made, queries.WhoAmI(), alice, ErrorCode.UNAUTHENTICATED)  # the next query reads live again
    assert (True, Isolation.REPEATABLE_READ) in spy["uow"].opened[1:]


def test_a_command_is_admitted_in_a_read_committed_unit_of_work() -> None:
    spy: dict[str, IsolationSpy] = {}

    def factory(made: Any) -> IsolationSpy:
        spy["uow"] = IsolationSpy(made)
        return spy["uow"]

    w = world(uow_factory=factory)
    made = w["h"]
    spy["uow"].opened.clear()
    made.run(grant(WS, w["bob"]), made.actor("alice"))
    assert spy["uow"].opened[0] == (False, Isolation.READ_COMMITTED)


# ------------------------------------------------------------------------------- the actor is trusted data


def test_the_dto_cannot_change_the_kind_or_the_grant_the_actor_was_authenticated_with() -> None:
    w = world()
    made = w["h"]
    made.token("bob-narrow", w["bob"], permissions={"token.own"})
    narrow = made.actor("bob-narrow")
    # a DTO that *says* the caller is an owner/service changes nothing: kind and grant come from the Actor
    payload = {"kind": "service", "display_name": "elevated"}
    error = refused(made, commands.CreatePrincipal.from_json(payload), narrow, ErrorCode.FORBIDDEN)
    assert error.details["reason_code"] in {"NO_MEMBERSHIP", "TOKEN_NARROWED"}
    assert narrow.kind is PrincipalKind.HUMAN
