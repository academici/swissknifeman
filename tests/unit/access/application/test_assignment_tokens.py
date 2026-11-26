"""Assignment tokens through ``access.public`` (access §13, §4.4 rows 4a/4b/5a, §15).

The facade functions run in the caller's unit of work, as ``execution`` calls them. Invariants:
scope = the run,
permissions never include ``worker.claim``; one secret per step and an issued secret never moves to another
step or assignment; a repeat of the same binding and hash is a no-op; revoked and expired tokens are not
revived; a step revoke leaves the neighbouring steps alone; only hashes are stored.
"""

from datetime import timedelta
from pathlib import Path
from runpy import run_path
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, PreconditionFailed, Unauthenticated, ValidationFailed
from skm.modules.access import public
from skm.modules.access.application import authz
from skm.modules.access.domain.authorization import Allowed, Denied, DenyReason
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import TokenId, TokenKind, TokenSecret, parse_secret

h = run_path(str(Path(__file__).with_name("test_create_token.py")))
world, create = h["world"], h["create"]
commands, queries = h["commands"], h["queries"]
WS, WS2, P1, PLAN1, RUN1, PEPPER, NOW = (h[n] for n in ("WS", "WS2", "P1", "PLAN1", "RUN1", "PEPPER", "NOW"))
SECRET_RANDOM = "A" * 43

READS = frozenset({"project.read", "plan.read", "run.read", "context.read", "token.own", "step.note"})


def ids(made: Any, count: int) -> list[UUID]:
    return [made.ids.new_id() for _ in range(count)]


def setup() -> dict[str, Any]:
    w = world()
    made = w["h"]
    worker = made.principal("w1", PrincipalKind.WORKER, {WS: Role.WORKER})
    worker_token = made.token("worker", worker, kind=TokenKind.WORKER, expires_in=timedelta(hours=100))
    return {**w, "worker": worker, "worker_token": worker_token, "actor": made.actor("worker")}


def issue(made: Any, actor: Any, secret: TokenSecret, *, assignment: UUID, step: UUID, **fields: Any) -> Any:
    arguments: dict[str, Any] = {
        "run_scope_id": RUN1,
        "expires_at": made.clock.now() + timedelta(hours=2),
        "permissions": READS,
        **fields,
    }
    with made.uow() as uow:
        view = public.issue_assignment_token(
            uow,
            worker=actor,
            secret=secret,
            assignment_id=assignment,
            step_id=step,
            pepper=PEPPER,
            now=made.clock.now(),
            **arguments,
        )
        uow.commit()
    return view


def fresh(made: Any) -> TokenSecret:
    return public.generate_secret(made.entropy.bytes)


def created_events(made: Any) -> list[Any]:
    return [e for e in made.events if e.type.endswith("token-created:v1")]


def in_uow(made: Any, call: Any) -> Any:
    with made.uow() as uow:
        result = call(uow)
        uow.commit()
    return result


# ---------------------------------------------------------------------------------------------------------
# issuing


def test_an_assignment_token_is_bound_to_the_run_and_cut_to_the_worker_role() -> None:
    s = setup()
    made = s["h"]
    assignment, step = ids(made, 2)
    secret = fresh(made)
    wide = READS | {"worker.claim", "workspace.manage", "principal.manage"}
    view = issue(made, s["actor"], secret, assignment=assignment, step=step, permissions=wide)
    assert (view.kind.value, view.scope_id, view.assignment_id, view.step_id) == (
        "assignment",
        RUN1,
        assignment,
        step,
    )
    assert view.state == "active"
    assert view.name == f"assignment-{assignment}-step-{step}"
    token = made.tokens[TokenId(view.token_id)]
    assert token.permissions == READS  # no worker.claim, nothing outside the worker role
    assert token.principal_id == s["worker"]
    assert secret.random not in made.stored_text()  # only the peppered hash is stored
    [event] = created_events(made)
    assert event.payload["kind"] == "assignment"
    assert event.payload["scope_id"] == str(RUN1)
    assert event.workspace_id == WS
    assert "secret" not in str(event.payload)


def test_the_term_never_outlives_the_worker_token() -> None:
    s = setup()
    made = s["h"]
    assignment, step = ids(made, 2)
    view = issue(
        made, s["actor"], fresh(made), assignment=assignment, step=step,
        expires_at=NOW + timedelta(hours=1000),
    )  # fmt: skip
    assert view.expires_at == NOW + timedelta(hours=100)
    short = issue(
        made, s["actor"], fresh(made), assignment=assignment, step=ids(made, 1)[0],
        expires_at=NOW + timedelta(hours=1),
    )  # fmt: skip
    assert short.expires_at == NOW + timedelta(hours=1)


def test_whoami_of_an_assignment_token_carries_assignment_and_step() -> None:
    s = setup()
    made = s["h"]
    assignment, step = ids(made, 2)
    secret = fresh(made)
    issue(made, s["actor"], secret, assignment=assignment, step=step)
    actor = made.actor(str(secret))
    assert (actor.grant.assignment_id, actor.grant.step_id, actor.grant.scope_id) == (assignment, step, RUN1)
    assert WS in actor.grant.scope_ancestors
    assert RUN1 not in actor.grant.scope_ancestors
    view = made.ask(queries.WhoAmI(), actor)
    assert (view.token.assignment_id, view.token.step_id, view.token.kind.value) == (
        assignment,
        step,
        "assignment",
    )
    assert view.principal.kind.value == "worker"


def test_a_repeat_of_the_same_binding_and_secret_is_a_no_op() -> None:
    s = setup()
    made = s["h"]
    assignment, step = ids(made, 2)
    secret = fresh(made)
    first = issue(made, s["actor"], secret, assignment=assignment, step=step)
    again = issue(made, s["actor"], secret, assignment=assignment, step=step)
    assert again.token_id == first.token_id
    assert len(created_events(made)) == 1
    assert len([t for t in made.tokens.values() if t.kind is TokenKind.ASSIGNMENT]) == 1


def test_an_issued_secret_never_moves_to_another_step_or_assignment() -> None:
    s = setup()
    made = s["h"]
    assignment, step, other_step, other_assignment = ids(made, 4)
    secret = fresh(made)
    issue(made, s["actor"], secret, assignment=assignment, step=step)
    before = made.snapshot()
    for kwargs in (
        {"step": other_step, "assignment": assignment},
        {"step": step, "assignment": other_assignment},
    ):
        with pytest.raises(Forbidden) as caught:
            issue(made, s["actor"], secret, **kwargs)
        assert caught.value.details["reason"] == "assignment_binding_mismatch"
    assert made.snapshot() == before
    new = issue(
        made, s["actor"], fresh(made), assignment=assignment, step=other_step
    )  # a new step: a new secret
    assert new.step_id == other_step
    assert new.token_id != made.actor(str(secret)).grant.token_id


def test_the_same_prefix_with_another_hash_and_a_second_secret_for_a_step_conflict() -> None:
    s = setup()
    made = s["h"]
    assignment, step = ids(made, 2)
    secret = fresh(made)
    issue(made, s["actor"], secret, assignment=assignment, step=step)
    forged = TokenSecret(prefix=secret.prefix, random=SECRET_RANDOM)
    with pytest.raises(Conflict) as caught:
        issue(made, s["actor"], forged, assignment=assignment, step=step)
    assert caught.value.code is ErrorCode.ALREADY_EXISTS
    with pytest.raises(Conflict) as second:
        issue(made, s["actor"], fresh(made), assignment=assignment, step=step)
    assert second.value.code is ErrorCode.ALREADY_EXISTS
    assert len(created_events(made)) == 1


def test_only_a_live_worker_token_with_a_run_in_its_workspace_issues() -> None:
    s = setup()
    made = s["h"]
    assignment, step = ids(made, 2)
    human = made.actor("alice")
    with pytest.raises(Forbidden) as caught:
        issue(made, human, fresh(made), assignment=assignment, step=step)
    assert caught.value.details["reason"] == "not_worker_token"
    with pytest.raises(ValidationFailed) as kind:
        issue(made, s["actor"], fresh(made), assignment=assignment, step=step, run_scope_id=PLAN1)
    assert kind.value.code is ErrorCode.INVALID_REFERENCE
    foreign = made.principal("w2", PrincipalKind.WORKER, {WS2: Role.WORKER})
    made.token("foreign", foreign, kind=TokenKind.WORKER, expires_in=timedelta(hours=10))
    with pytest.raises(Forbidden):  # its worker role does not reach the run of another workspace
        issue(made, made.actor("foreign"), fresh(made), assignment=assignment, step=step)
    assert made.tokens
    assert not [t for t in made.tokens.values() if t.kind is TokenKind.ASSIGNMENT]
    made.run(commands.RevokeToken(token_id=s["worker_token"]), s["actor"])
    with pytest.raises(Unauthenticated):  # a revoked worker credential issues nothing
        issue(made, s["actor"], fresh(made), assignment=assignment, step=step)


# ---------------------------------------------------------------------------------------------------------
# revoking and extending


def test_a_step_revoke_leaves_the_other_bindings_of_the_assignment_alone() -> None:
    s = setup()
    made = s["h"]
    assignment, step_a, step_b = ids(made, 3)
    secret_a, secret_b = fresh(made), fresh(made)
    issue(made, s["actor"], secret_a, assignment=assignment, step=step_a)
    issue(made, s["actor"], secret_b, assignment=assignment, step=step_b)
    count = in_uow(
        made,
        lambda uow: public.revoke_assignment_tokens(
            uow, assignment_id=assignment, by=s["worker"], now=made.clock.now(), step_id=step_a
        ),
    )
    assert count == 1
    with pytest.raises(Unauthenticated):
        made.actor(str(secret_a))
    assert made.actor(str(secret_b)).grant.step_id == step_b
    again = in_uow(
        made,
        lambda uow: public.revoke_assignment_tokens(
            uow, assignment_id=assignment, by=s["worker"], now=made.clock.now(), step_id=step_a
        ),
    )
    assert again == 0  # a repeat is a no-op
    revoked = [e for e in made.events if e.type.endswith("token-revoked:v1")]
    assert len(revoked) == 1


def test_a_new_fence_revokes_the_whole_assignment_and_the_old_secret_stays_dead() -> None:
    s = setup()
    made = s["h"]
    assignment, step = ids(made, 2)
    old = fresh(made)
    issue(made, s["actor"], old, assignment=assignment, step=step)
    revoked = in_uow(
        made,
        lambda uow: public.revoke_assignment_tokens(
            uow, assignment_id=assignment, by=s["worker"], now=made.clock.now()
        ),
    )
    assert revoked == 1
    with pytest.raises(Unauthenticated):
        made.actor(str(old))
    with pytest.raises(PreconditionFailed) as caught:  # the same secret is not revived by a repeat issue
        issue(made, s["actor"], old, assignment=assignment, step=step)
    assert caught.value.details["reason"] == "token_not_active"
    new = fresh(made)
    issue(made, s["actor"], new, assignment=assignment, step=step)  # the new epoch brings a new secret
    assert made.actor(str(new)).grant.step_id == step
    assert old.random not in made.stored_text()
    assert new.random not in made.stored_text()


def test_extend_lengthens_live_tokens_within_the_worker_token_and_revives_nothing() -> None:
    s = setup()
    made = s["h"]
    assignment, step, step_dead = ids(made, 3)
    live, dead = fresh(made), fresh(made)
    issue(made, s["actor"], live, assignment=assignment, step=step, expires_at=NOW + timedelta(hours=1))
    issue(made, s["actor"], dead, assignment=assignment, step=step_dead, expires_at=NOW + timedelta(hours=1))
    in_uow(
        made,
        lambda uow: public.revoke_assignment_tokens(
            uow, assignment_id=assignment, by=s["worker"], now=NOW, step_id=step_dead
        ),
    )

    def extend(expires_at: Any) -> int:
        return in_uow(
            made,
            lambda uow: public.extend_assignment_tokens(
                uow, assignment_id=assignment, expires_at=expires_at, now=made.clock.now()
            ),
        )

    assert extend(NOW + timedelta(hours=3)) == 1  # the revoked token is not touched
    assert made.tokens[made.actor(str(live)).grant.token_id].expires_at == NOW + timedelta(hours=3)
    assert extend(NOW + timedelta(hours=3)) == 0  # nothing left to lengthen
    assert extend(NOW + timedelta(hours=1000)) == 1
    assert made.tokens[made.actor(str(live)).grant.token_id].expires_at == NOW + timedelta(hours=100)
    with pytest.raises(Unauthenticated):
        made.actor(str(dead))
    made.clock.advance(timedelta(hours=101))  # past the worker token as well
    assert extend(made.clock.now() + timedelta(hours=1)) == 0  # an expired token is not revived
    with pytest.raises(Unauthenticated):
        made.actor(str(live))


def test_extending_an_assignment_without_a_runtime_token_is_a_normal_no_op() -> None:
    s = setup()
    made = s["h"]
    assert (
        in_uow(
            made,
            lambda uow: public.extend_assignment_tokens(
                uow, assignment_id=made.ids.new_id(), expires_at=NOW + timedelta(hours=1), now=NOW
            ),
        )
        == 0
    )


# ---------------------------------------------------------------------------------------------------------
# what an assignment token may do (access §4.4)


def decision(made: Any, actor: Any, permission: str, scope: Any) -> Any:
    with made.uow(readonly=True) as uow:
        return authz.decision(uow, actor, permission, authz.chain_of(uow, scope))


def test_an_assignment_token_never_authorizes_the_worker_protocol() -> None:
    s = setup()
    made = s["h"]
    assignment, step = ids(made, 2)
    secret = fresh(made)
    issue(made, s["actor"], secret, assignment=assignment, step=step)
    actor = made.actor(str(secret))
    verdict = decision(made, actor, "worker.claim", RUN1)
    assert isinstance(verdict, Denied)
    assert verdict.reason is DenyReason.TOKEN_PERMISSION_MISSING
    assert isinstance(decision(made, s["actor"], "worker.claim", RUN1), Allowed)  # the worker credential does


def test_writes_stay_inside_the_run_and_reads_reach_its_ancestors() -> None:
    s = setup()
    made = s["h"]
    assignment, step = ids(made, 2)
    secret = fresh(made)
    issue(made, s["actor"], secret, assignment=assignment, step=step)
    actor = made.actor(str(secret))
    assert isinstance(decision(made, actor, "step.note", RUN1), Allowed)
    assert isinstance(decision(made, actor, "plan.read", PLAN1), Allowed)  # ancestors of the run: reads
    assert isinstance(decision(made, actor, "project.read", P1), Allowed)
    verdict = decision(made, actor, "step.note", PLAN1)  # a write outside the run
    assert isinstance(verdict, Denied)
    assert verdict.reason is DenyReason.TOKEN_SCOPE_MISMATCH
    verdict = decision(made, actor, "memory.write", P1)
    assert isinstance(verdict, Denied)
    assert verdict.reason is DenyReason.TOKEN_SCOPE_MISMATCH


def test_a_worker_cannot_create_a_token_for_itself_through_the_bus() -> None:
    s = setup()
    made = s["h"]
    with pytest.raises(Forbidden) as caught:
        made.run(create("self"), s["actor"])
    assert caught.value.details["reason"] == "worker_tokens_are_rotated"
    assert not [t for t in made.tokens.values() if t.name == "self"]


def test_a_worker_and_a_workspace_member_rotate_and_revoke_their_own_token_without_instance_membership() -> (
    None
):
    s = setup()
    made = s["h"]
    made.bind_worker(s["worker"], WS)
    rotated = made.run(commands.RotateToken(token_id=s["worker_token"]), s["actor"])
    new_actor = made.actor(rotated.secret)
    assert new_actor.kind is PrincipalKind.WORKER
    made.run(commands.RevokeToken(token_id=rotated.token_id), new_actor)
    assert made.tokens[TokenId(rotated.token_id)].revoked_at is not None


# ---------------------------------------------------------------------------------------------------------
# the other facade functions the worker and workspace flows call


def test_create_worker_principal_makes_principal_membership_and_a_worker_token() -> None:
    w = world()
    made = w["h"]
    owner_actor = made.actor("owner")
    principal_id, token_id, secret = in_uow(
        made,
        lambda uow: public.create_worker_principal(
            uow,
            display_name="build host",
            workspace_scope_id=WS,
            issuer=owner_actor,
            worker_id=made.ids.new_id(),
            token_name="worker-1",
            pepper=PEPPER,
            entropy=made.entropy.bytes,
            now=made.clock.now(),
        ),
    )
    actor = made.actor(secret)
    assert (actor.principal_id, actor.kind, actor.grant.kind) == (
        principal_id,
        PrincipalKind.WORKER,
        "worker",
    )
    token = made.tokens[token_id]
    assert token.expires_at == NOW + timedelta(hours=168)  # access.tokens.worker_ttl_hours
    assert (token.name, token.scope_id, token.permissions, token.created_by) == (
        "worker-1",
        None,
        None,
        w["owner"],
    )
    assert [e.type.split(":")[-2] for e in made.events] == [
        "principal-created",
        "membership-granted",
        "token-created",
    ]
    assert made.events[1].workspace_id == WS
    assert made.events[1].payload["role"] == "worker"
    assert parse_secret(secret).random not in made.stored_text()
    with pytest.raises(ValidationFailed):
        in_uow(
            made,
            lambda uow: public.create_worker_principal(
                uow,
                display_name="bad",
                workspace_scope_id=P1,  # a worker is registered on a workspace
                issuer=owner_actor,
                worker_id=made.ids.new_id(),
                token_name="worker-2",
                pepper=PEPPER,
                entropy=made.entropy.bytes,
                now=made.clock.now(),
            ),
        )


def test_grant_initial_membership_gives_the_creator_a_role_without_a_granter() -> None:
    w = world()
    made = w["h"]
    carol = made.principal("carol")
    in_uow(
        made,
        lambda uow: public.grant_initial_membership(
            uow, scope_id=P1, principal_id=carol, role=Role.OWNER, now=made.clock.now()
        ),
    )
    assert public.role_permissions(Role.OWNER) >= {"membership.manage"}
    owner, bob = made.actor("owner"), made.actor("bob")
    with made.uow(readonly=True) as uow:
        assert "plan.edit" in public.effective_permissions(uow, owner, P1)
        assert public.effective_permissions(uow, bob, P1) >= {"plan.read"}
    [event] = [e for e in made.events if e.type.endswith("membership-granted:v1")]
    assert (event.payload["role"], event.payload["previous_role"], event.workspace_id) == ("owner", None, WS)


def test_revoke_principal_tokens_revokes_every_usable_token_and_can_disable() -> None:
    w = world()
    made = w["h"]
    made.run(create("second"), made.actor("bob"))
    count = in_uow(
        made,
        lambda uow: public.revoke_principal_tokens(
            uow, w["bob"], by=w["owner"], now=made.clock.now(), disable=True
        ),
    )
    assert count == 2
    kinds = [e.type.split(":")[-2] for e in made.events[-3:]]
    assert kinds == ["token-revoked", "token-revoked", "principal-disabled"]
    again = in_uow(
        made,
        lambda uow: public.revoke_principal_tokens(
            uow, w["bob"], by=w["owner"], now=made.clock.now(), disable=True
        ),
    )
    assert again == 0
    assert made.events[-1].type.endswith("principal-disabled:v1")
    assert len([e for e in made.events if e.type.endswith("principal-disabled:v1")]) == 1
