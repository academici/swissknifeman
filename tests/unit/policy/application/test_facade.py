"""The facade ``propose_intent``, ``require_approved``, ``record_outcome`` in the caller's transaction (§13).

Execution drives push and PR in its own transactions; the facade functions run inside them, admit the acting
principal afresh, and leave the commit to the caller. A transaction that does not commit spends nothing.
"""

from typing import Any
from uuid import UUID

import pytest

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, SkmError, Unauthenticated
from skm.kernel.ids import PrincipalId, ToolIntentId
from skm.modules.policy import public
from skm.modules.policy.domain.approval import ApprovalRequired
from skm.modules.policy.domain.tool_intent import EffectKind
from unit.policy.application.harness import World, push_args
from unit.policy.application.test_lifecycle import approve, view


def facade_propose(world: World, uow: Any, who: str = "owner", **changes: Any) -> Any:
    ctx = world.context(uow, who)
    perms = public.effective_permissions(
        uow,
        scope_chain=(),
        config=ctx.config,
        profile_id=None,
        role_layer=None,
        task_layer=None,
        allow_unconfined=False,
    )
    values: dict[str, Any] = {
        "scope_id": world.scope_id,
        "subject_ref": "run:1/attempt:1",
        "kind": EffectKind.GIT_PUSH,
        "args": push_args(),
        "reason": "integrate",
        "perms": perms,
    }
    values.update(changes)
    return public.propose_intent(uow, ctx, **values)


def test_the_whole_life_runs_in_the_callers_transactions(world: World) -> None:
    with world.uow() as uow:
        proposed = facade_propose(world, uow)
        uow.commit()
    assert proposed.state == "proposed"
    assert proposed.approvals == ()
    approve(world, proposed.intent_id)
    with world.uow() as uow:
        started = public.require_approved(
            uow, world.context(uow), intent_id=proposed.intent_id, args_digest=proposed.args_digest
        )
        uow.commit()
    assert started.state == "executing"
    assert started.approvals[0].used_at == world.clock.now()
    with world.uow() as uow:
        done = public.record_outcome(
            uow,
            world.context(uow),
            intent_id=proposed.intent_id,
            outcome="succeeded",
            receipt={"sha": "c" * 40},
        )
        uow.commit()
    assert done.state == "succeeded"
    assert [e.type.split(":")[-2] for e in world.events()] == [
        "intent-proposed",
        "intent-approved",
        "intent-execution-started",
        "intent-resolved",
    ]


def test_a_transaction_that_does_not_commit_spends_nothing(world: World) -> None:
    with world.uow() as uow:
        proposed = facade_propose(world, uow)
        uow.commit()
    approve(world, proposed.intent_id)
    before = world.snapshot()

    def fails_after_admission() -> None:
        with world.uow() as uow:
            public.require_approved(
                uow, world.context(uow), intent_id=proposed.intent_id, args_digest=proposed.args_digest
            )
            raise RuntimeError("the caller failed before its commit")

    with pytest.raises(RuntimeError):
        fails_after_admission()
    assert world.snapshot() == before
    assert view(world, proposed.intent_id).state == "approved"
    with world.uow() as uow:  # the approval is still there to be spent
        assert (
            public.require_approved(
                uow, world.context(uow), intent_id=proposed.intent_id, args_digest=proposed.args_digest
            ).state
            == "executing"
        )
        uow.commit()


def test_the_facade_admits_the_acting_principal_afresh(world: World) -> None:
    ghost = Actor(principal_id=PrincipalId(UUID(int=424242)), kind=PrincipalKind.HUMAN, display_name="ghost")
    with world.uow() as uow, pytest.raises(Unauthenticated):
        public.require_approved(
            uow,
            world.context(uow, ghost),
            intent_id=ToolIntentId(UUID(int=1)),
            args_digest="sha256:" + "0" * 64,
        )


def test_start_through_the_facade_waits_for_an_approval_and_is_live_checked(world: World) -> None:
    with world.uow() as uow:
        proposed = facade_propose(world, uow)
        uow.commit()
    with world.uow() as uow, pytest.raises(ApprovalRequired):
        public.require_approved(
            uow, world.context(uow), intent_id=proposed.intent_id, args_digest=proposed.args_digest
        )
    approve(world, proposed.intent_id)
    world.allow_effects("git_commit")  # revoked between approve and start
    with world.uow() as uow, pytest.raises(Forbidden) as caught:
        public.require_approved(
            uow, world.context(uow), intent_id=proposed.intent_id, args_digest=proposed.args_digest
        )
    assert caught.value.details["reason"] == "revoked"
    assert world.intents()[proposed.intent_id].state.value == "approved"


def test_an_open_intent_is_returned_not_duplicated(world: World) -> None:
    with world.uow() as uow:
        first = facade_propose(world, uow)
        uow.commit()
    with world.uow() as uow:
        again = facade_propose(world, uow)
        uow.commit()
    assert again.intent_id == first.intent_id
    assert len(world.intents()) == 1


def test_a_kind_outside_the_perms_the_caller_composed_is_a_denied_intent(world: World) -> None:
    with world.uow() as uow:
        ctx = world.context(uow)
        perms = public.effective_permissions(
            uow,
            scope_chain=(),
            config=ctx.config,
            profile_id=None,
            role_layer=None,
            task_layer=None,
            allow_unconfined=False,
        )
        narrowed = public.narrow(perms, public.PermissionLayer(source="step", external_effects=frozenset()))
        denied = facade_propose(world, uow, perms=narrowed)
        uow.commit()
    assert (denied.state, denied.denied_reason) == ("denied", "not_permitted")


def test_a_failure_of_the_facade_is_a_domain_error_with_the_expected_code(world: World) -> None:
    with world.uow() as uow, pytest.raises(SkmError) as caught:
        facade_propose(world, uow, args=push_args(before_sha="x"))
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
