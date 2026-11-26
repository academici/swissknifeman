"""propose -> approve/deny -> start -> outcome through the real bus (policy §7, §15).

The slice here is the path of an intent and its direct refusals; who may approve is in
``test_approval_authority.py``, replay and revocation in ``tests/security/test_approval_reuse.py``.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, SkmError
from skm.modules.access.public import SYSTEM_ACTOR, Role
from skm.modules.policy.domain.approval import ApprovalRequired
from skm.modules.policy.domain.tool_intent import IntentState
from skm.modules.policy.generated.commands import (
    ApproveIntent,
    DenyIntent,
    EffectKind,
    ExpireIntents,
    ProposeIntent,
    RecordIntentOutcome,
    StartIntentExecution,
)
from skm.modules.policy.generated.queries import GetIntent, ListIntents
from skm.modules.workspace.public import ArchiveProject
from unit.policy.application.harness import World, commit_args, push_args

KINDS = {"git_push": EffectKind.GIT_PUSH, "git_commit": EffectKind.GIT_COMMIT}


def propose(world: World, kind: str = "git_push", args: dict[str, Any] | None = None, **fields: Any) -> Any:
    document = (push_args() if kind == "git_push" else commit_args()) if args is None else args
    return world.run(
        ProposeIntent(
            scope_id=world.scope_id,
            subject_ref="run:1/attempt:1",
            kind=KINDS[kind],
            args=document,
            reason="integrate the attempt",
            **fields,
        ),
    )


def view(world: World, intent_id: UUID) -> Any:
    return world.ask(GetIntent(intent_id=intent_id))


def approve(world: World, intent_id: UUID, who: str = "owner", **fields: Any) -> Any:
    seen = view(world, intent_id)
    return world.run(
        ApproveIntent(
            intent_id=intent_id, expected_row_version=seen.row_version, args_digest=seen.args_digest, **fields
        ),
        who,
    )


def start(world: World, intent_id: UUID, who: str = "owner", digest: str | None = None) -> Any:
    seen = view(world, intent_id)
    return world.run(StartIntentExecution(intent_id=intent_id, args_digest=digest or seen.args_digest), who)


def outcome(world: World, intent_id: UUID, state: str, receipt: dict[str, Any] | None = None) -> Any:
    return world.run(
        RecordIntentOutcome(intent_id=intent_id, outcome=state, receipt=receipt or {"sha": "c" * 40})  # pyright: ignore[reportArgumentType]
    )


def refused(world: World, call: Any, code: ErrorCode, **details: Any) -> SkmError:
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        call()
    assert caught.value.code is code
    for key, value in details.items():
        assert caught.value.details[key] == value
    assert world.snapshot() == before  # a refused command leaves nothing behind
    return caught.value


# ------------------------------------------------------------------------------------------ propose
def test_propose_creates_one_open_intent_and_repeats_return_it(world: World) -> None:
    first = propose(world)
    assert (first.state, first.needs_approval) == ("proposed", True)
    assert propose(world).intent_id == first.intent_id
    assert len(world.intents()) == 1
    assert [e.type.split(":")[-2] for e in world.events()] == ["intent-proposed"]
    stored = view(world, first.intent_id)
    assert (stored.kind.value, stored.risk.value, stored.subject_ref) == (
        "git_push",
        "high",
        "run:1/attempt:1",
    )
    assert stored.scope_id == world.scope_id
    assert stored.workspace_id == world.workspace_id
    assert stored.args_digest == first.args_digest
    assert stored.approvals == ()
    other = propose(world, args=push_args(after_sha="d" * 40))
    assert other.intent_id != first.intent_id
    assert other.args_digest != first.args_digest


def test_the_same_effect_in_another_order_is_the_same_intent(world: World) -> None:
    pair = ["refs/heads/a:refs/heads/a", "refs/heads/b:refs/heads/b"]
    first = propose(world, args=push_args(refspecs=pair))
    again = propose(world, args=push_args(refspecs=pair[::-1]))
    assert again.intent_id == first.intent_id


def test_a_kind_without_the_need_for_a_human_is_approved_by_the_system(world: World) -> None:
    result = propose(world, "git_commit")
    assert (result.state, result.needs_approval) == ("approved", False)
    stored = view(world, result.intent_id)
    (approval,) = stored.approvals
    assert (approval.approver_id, approval.decision, approval.single_use) == (
        SYSTEM_PRINCIPAL_ID,
        "approve",
        True,
    )
    assert approval.expires_at == stored.expires_at
    assert approval.used_at is None
    approved = world.events("intent-approved")[0].payload
    assert approved["auto"] is True
    assert approved["approver_id"] == str(SYSTEM_PRINCIPAL_ID)
    assert [e.type.split(":")[-2] for e in world.events()] == ["intent-proposed", "intent-approved"]


def test_a_kind_outside_the_ceiling_is_a_denied_intent_with_its_event(world: World) -> None:
    world.allow_effects("git_commit")
    result = propose(world)
    assert (result.state, result.needs_approval) == ("denied", False)
    stored = view(world, result.intent_id)
    assert stored.denied_reason == "not_permitted"
    assert stored.approvals == ()
    denied = world.events("intent-denied")[0].payload
    assert denied["reason"] == "not_permitted"
    assert denied["by"] == str(SYSTEM_PRINCIPAL_ID)
    refused(world, lambda: start(world, result.intent_id), ErrorCode.FORBIDDEN, reason="not_permitted")


@pytest.mark.parametrize(
    "changes",
    [{"force": True}, {"refspecs": ["+refs/heads/main:refs/heads/main"]}, {"refspecs": [":refs/heads/x"]}],
)
def test_forbidden_arguments_are_denied_at_once_and_can_never_be_approved(
    world: World, changes: dict
) -> None:
    result = propose(world, args=push_args(**changes))
    assert result.state == "denied"
    assert view(world, result.intent_id).denied_reason == "forbidden_args"
    seen = view(world, result.intent_id)
    refused(
        world,
        lambda: world.run(
            ApproveIntent(
                intent_id=result.intent_id,
                expected_row_version=seen.row_version,
                args_digest=seen.args_digest,
            )
        ),
        ErrorCode.INVALID_TRANSITION,
    )
    refused(world, lambda: start(world, result.intent_id), ErrorCode.FORBIDDEN, reason="forbidden_args")


def test_a_denied_proposal_does_not_hold_the_slot_of_the_effect(world: World) -> None:
    world.allow_effects("git_commit")
    assert propose(world).state == "denied"
    world.allow_effects("git_commit", "git_push")
    fresh = propose(world)
    assert fresh.state == "proposed"


def test_malformed_arguments_are_a_schema_error_and_leave_nothing(world: World) -> None:
    refused(world, lambda: propose(world, args=push_args(before_sha="abc")), ErrorCode.SCHEMA_INVALID)
    refused(world, lambda: propose(world, args=push_args(unknown=1)), ErrorCode.SCHEMA_INVALID)


def test_the_full_access_profile_needs_the_host_flag(world: World) -> None:
    refused(
        world,
        lambda: propose(world, profile_id="trusted-full-access"),
        ErrorCode.FORBIDDEN,
        reason="unconfined_not_allowed_on_host",
    )


# ------------------------------------------------------------------------------------------ approve / deny
def test_propose_approve_start_outcome(world: World) -> None:
    proposed = propose(world)
    approved = approve(world, proposed.intent_id, reason="looked at the diff")
    assert approved.state == "approved"
    started = start(world, proposed.intent_id)
    assert (started.state, started.approval_id) == ("executing", approved.approval_id)
    resolved = outcome(world, proposed.intent_id, "succeeded", {"sha": "c" * 40, "url": "https://x/pr/1"})
    assert resolved.state == "succeeded"
    stored = view(world, proposed.intent_id)
    (approval,) = stored.approvals
    assert approval.used_at == world.clock.now()
    assert approval.reason == "looked at the diff"
    assert approval.approver_id == world.actor("owner").principal_id
    assert approval.args_digest == stored.args_digest
    assert [e.type.split(":")[-2] for e in world.events()] == [
        "intent-proposed",
        "intent-approved",
        "intent-execution-started",
        "intent-resolved",
    ]
    assert world.events("intent-approved")[0].payload["auto"] is False
    assert world.events("intent-resolved")[0].payload["outcome"] == "succeeded"
    assert stored.row_version == 4  # proposed(1) -> approved -> executing -> succeeded


def test_the_same_effect_may_be_proposed_again_after_it_resolved(world: World) -> None:
    first = propose(world)
    approve(world, first.intent_id)
    start(world, first.intent_id)
    outcome(world, first.intent_id, "failed")
    again = propose(world)
    assert again.intent_id != first.intent_id
    assert again.state == "proposed"


def test_a_stale_version_or_a_changed_digest_cannot_approve(world: World) -> None:
    proposed = propose(world)
    seen = view(world, proposed.intent_id)
    refused(
        world,
        lambda: world.run(
            ApproveIntent(
                intent_id=proposed.intent_id,
                expected_row_version=seen.row_version + 1,
                args_digest=seen.args_digest,
            )
        ),
        ErrorCode.VERSION_CONFLICT,
    )
    refused(
        world,
        lambda: world.run(
            ApproveIntent(
                intent_id=proposed.intent_id,
                expected_row_version=seen.row_version,
                args_digest="sha256:" + "0" * 64,
            )
        ),
        ErrorCode.APPROVAL_MISMATCH,
        reason="digest_changed",
    )


def test_an_expired_proposal_cannot_be_approved(world: World) -> None:
    proposed = propose(world)
    world.tick(3 * 86400)
    refused(world, lambda: approve(world, proposed.intent_id), ErrorCode.INVALID_TRANSITION, reason="expired")


def test_approving_twice_is_an_invalid_transition(world: World) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    refused(world, lambda: approve(world, proposed.intent_id), ErrorCode.INVALID_TRANSITION)
    assert len(view(world, proposed.intent_id).approvals) == 1


def test_the_approval_lives_no_longer_than_the_configuration_allows_and_is_single_use(world: World) -> None:
    world.set_config("policy.approval.ttl_seconds", 120)
    proposed = propose(world)
    approve(world, proposed.intent_id, ttl_seconds=604800, single_use=False)
    (approval,) = view(world, proposed.intent_id).approvals
    assert approval.expires_at == world.clock.now() + timedelta(seconds=120)  # an explicit ask cannot widen
    assert approval.single_use is True  # the configuration forces it


def test_an_explicit_shorter_lifetime_and_the_configured_non_single_use_are_honoured(world: World) -> None:
    world.set_config("policy.approval.single_use", False)
    proposed = propose(world)
    approve(world, proposed.intent_id, ttl_seconds=60)
    (approval,) = view(world, proposed.intent_id).approvals
    assert approval.expires_at == world.clock.now() + timedelta(seconds=60)
    assert approval.single_use is False


def test_deny_refuses_a_proposed_or_an_approved_intent_and_keeps_who_and_why(world: World) -> None:
    proposed = propose(world)
    seen = view(world, proposed.intent_id)
    denied = world.run(
        DenyIntent(intent_id=proposed.intent_id, expected_row_version=seen.row_version, reason="not now")
    )
    assert denied.state == "denied"
    stored = view(world, proposed.intent_id)
    assert stored.denied_reason == "by_approver"
    (record,) = stored.approvals
    assert (record.decision, record.reason, record.approver_id) == (
        "deny",
        "not now",
        world.actor("owner").principal_id,
    )
    assert world.events("intent-denied")[0].payload["reason"] == "not now"
    refused(world, lambda: start(world, proposed.intent_id), ErrorCode.FORBIDDEN, reason="by_approver")
    second = propose(world)
    approve(world, second.intent_id)
    seen = view(world, second.intent_id)
    world.run(
        DenyIntent(intent_id=second.intent_id, expected_row_version=seen.row_version, reason="revoked by me")
    )
    refused(world, lambda: start(world, second.intent_id), ErrorCode.FORBIDDEN, reason="by_approver")


def test_deny_after_execution_started_is_an_invalid_transition(world: World) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    start(world, proposed.intent_id)
    seen = view(world, proposed.intent_id)
    refused(
        world,
        lambda: world.run(
            DenyIntent(intent_id=proposed.intent_id, expected_row_version=seen.row_version, reason="late")
        ),
        ErrorCode.INVALID_TRANSITION,
    )


def test_a_repeated_approve_with_the_same_key_is_one_approval(world: World) -> None:
    proposed = propose(world)
    seen = view(world, proposed.intent_id)
    dto = ApproveIntent(
        intent_id=proposed.intent_id, expected_row_version=seen.row_version, args_digest=seen.args_digest
    )
    first = world.run(dto, key="approve-1")
    second = world.run(dto, key="approve-1")
    assert second == first
    assert len(world.approvals()) == 1


# ------------------------------------------------------------------------------------------ start
def test_start_without_an_approval_waits_and_changes_nothing(world: World) -> None:
    proposed = propose(world)
    error = refused(
        world, lambda: start(world, proposed.intent_id), ErrorCode.APPROVAL_REQUIRED, state="proposed"
    )
    assert isinstance(error, ApprovalRequired)
    assert view(world, proposed.intent_id).state == "proposed"


def test_start_with_the_digest_of_other_arguments_is_a_mismatch(world: World) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    other = propose(world, args=push_args(after_sha="d" * 40)).args_digest
    refused(
        world,
        lambda: start(world, proposed.intent_id, digest=other),
        ErrorCode.APPROVAL_MISMATCH,
        reason="digest_changed",
    )


def test_start_after_the_approval_expired_is_a_mismatch(world: World) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id, ttl_seconds=60)
    world.tick(61)
    refused(
        world,
        lambda: start(world, proposed.intent_id),
        ErrorCode.APPROVAL_MISMATCH,
        reason="no_valid_approval",
    )


def test_start_twice_is_refused_and_spends_nothing_more(world: World) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    start(world, proposed.intent_id)
    refused(
        world, lambda: start(world, proposed.intent_id), ErrorCode.APPROVAL_MISMATCH, reason="already_started"
    )


def test_a_replay_of_start_with_the_same_key_returns_the_receipt_and_admits_once(world: World) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    seen = view(world, proposed.intent_id)
    dto = StartIntentExecution(intent_id=proposed.intent_id, args_digest=seen.args_digest)
    first = world.run(dto, key="start-1")
    assert world.run(dto, key="start-1") == first
    assert len(world.events("intent-execution-started")) == 1


# ------------------------------------------------------------------------------------------ outcome
def executing(world: World) -> UUID:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    start(world, proposed.intent_id)
    return proposed.intent_id


@pytest.mark.parametrize("final", ["succeeded", "failed", "outcome_unknown"])
def test_each_outcome_is_recorded_with_its_receipt_and_event(world: World, final: str) -> None:
    intent_id = executing(world)
    assert outcome(world, intent_id, final, {"note": "ü"}).state == final
    assert world.events("intent-resolved")[-1].payload == {"intent_id": str(intent_id), "outcome": final}
    assert world.intents()[intent_id].receipt == {"note": "ü"}


@pytest.mark.parametrize("settled", ["succeeded", "failed"])
def test_an_unknown_outcome_is_reconciled_later(world: World, settled: str) -> None:
    intent_id = executing(world)
    outcome(world, intent_id, "outcome_unknown", {"error": "timeout"})
    assert outcome(world, intent_id, settled, {"sha": "c" * 40}).state == settled
    refused(
        world,
        lambda: outcome(world, intent_id, "failed" if settled == "succeeded" else "succeeded"),
        ErrorCode.INVALID_TRANSITION,
    )


def test_the_same_outcome_again_changes_and_records_nothing(world: World) -> None:
    intent_id = executing(world)
    outcome(world, intent_id, "succeeded", {"sha": "c" * 40})
    before = world.snapshot()
    assert outcome(world, intent_id, "succeeded", {"sha": "c" * 40}).state == "succeeded"
    assert world.snapshot() == before
    refused(
        world, lambda: outcome(world, intent_id, "succeeded", {"sha": "d" * 40}), ErrorCode.INVALID_TRANSITION
    )


def test_an_outcome_needs_an_executing_intent(world: World) -> None:
    proposed = propose(world)
    refused(world, lambda: outcome(world, proposed.intent_id, "succeeded"), ErrorCode.INVALID_TRANSITION)
    approve(world, proposed.intent_id)
    refused(world, lambda: outcome(world, proposed.intent_id, "failed"), ErrorCode.INVALID_TRANSITION)


def test_a_receipt_over_sixteen_kib_is_refused(world: World) -> None:
    intent_id = executing(world)
    refused(
        world, lambda: outcome(world, intent_id, "succeeded", {"log": "x" * 16400}), ErrorCode.SCHEMA_INVALID
    )
    assert outcome(world, intent_id, "succeeded", {"log": "x" * 16000}).state == "succeeded"


# ------------------------------------------------------------------------------------------ archive
def test_an_archived_area_admits_no_new_work_but_lets_refusal_and_recording_through(world: World) -> None:
    proposed = propose(world)
    approved = propose(world, args=push_args(after_sha="d" * 40))
    approve(world, approved.intent_id)
    running = propose(world, args=push_args(after_sha="e" * 40))
    approve(world, running.intent_id)
    start(world, running.intent_id)
    world.run(ArchiveProject(project_id=world.project_id, expected_row_version=1, reason="done"))
    refused(world, lambda: propose(world, args=push_args(after_sha="f" * 40)), ErrorCode.PROJECT_ARCHIVED)
    refused(world, lambda: approve(world, proposed.intent_id), ErrorCode.PROJECT_ARCHIVED)
    refused(world, lambda: start(world, approved.intent_id), ErrorCode.PROJECT_ARCHIVED)
    assert outcome(world, running.intent_id, "succeeded").state == "succeeded"  # the effect already ran
    seen = view(world, approved.intent_id)
    denied = world.run(
        DenyIntent(intent_id=approved.intent_id, expected_row_version=seen.row_version, reason="closing")
    )
    assert denied.state == "denied"


# ------------------------------------------------------------------------------------------ queries / expiry
def test_list_intents_pages_by_creation_and_filters(world: World) -> None:
    ids = [propose(world, args=push_args(after_sha=f"{n}" * 40)).intent_id for n in range(1, 5)]
    approve(world, ids[0])
    first = world.ask(ListIntents(workspace_id=world.workspace_id, limit=3))
    assert [item.intent_id for item in first.items] == ids[:3]
    assert first.next_cursor is not None
    rest = world.ask(ListIntents(workspace_id=world.workspace_id, limit=3, after=first.next_cursor))
    assert [item.intent_id for item in rest.items] == ids[3:]
    assert rest.next_cursor is None
    approved = world.ask(ListIntents(workspace_id=world.workspace_id, state="approved"))
    assert [item.intent_id for item in approved.items] == ids[:1]
    assert world.ask(ListIntents(workspace_id=world.workspace_id, scope_id=UUID(int=5))).items == ()
    assert {item.kind.value for item in first.items} == {"git_push"}


def test_expire_intents_closes_undecided_proposals_and_approvals_nobody_used(world: World) -> None:
    stale = propose(world, args=push_args(after_sha="1" * 40))
    unused = propose(world, args=push_args(after_sha="2" * 40))
    approve(world, unused.intent_id, ttl_seconds=60)
    live = propose(world, args=push_args(after_sha="3" * 40))
    approve(world, live.intent_id, ttl_seconds=3600)
    assert world.run(ExpireIntents(), SYSTEM_ACTOR).expired == 0  # a young proposal, fresh approvals
    world.tick(61)
    assert world.run(ExpireIntents(), SYSTEM_ACTOR).expired == 1  # the approval of `unused` ran out
    assert world.intents()[unused.intent_id].state is IntentState.EXPIRED
    assert world.intents()[live.intent_id].state is IntentState.APPROVED
    world.tick(3 * 86400)
    assert world.run(ExpireIntents(limit=1), SYSTEM_ACTOR).expired == 1  # the limit is honoured
    assert world.run(ExpireIntents(), SYSTEM_ACTOR).expired == 1
    assert {item.state for item in world.intents().values()} == {IntentState.EXPIRED}
    assert {e.payload["outcome"] for e in world.events("intent-resolved")} == {"expired"}
    assert len(world.events("intent-resolved")) == 3
    assert stale.intent_id in world.intents()
    assert world.run(ExpireIntents(), SYSTEM_ACTOR).expired == 0  # nothing left to do


def test_only_the_system_runs_the_sweep(world: World) -> None:
    with pytest.raises(Forbidden):
        world.run(ExpireIntents(), "owner")
    world.person("svc", {}, kind=PrincipalKind.SERVICE)
    with pytest.raises(Forbidden):
        world.run(ExpireIntents(), "svc")


def test_start_and_outcome_need_the_right_to_drive_the_run(world: World) -> None:
    proposed = propose(world)
    approve(world, proposed.intent_id)
    viewer = world.person("watcher", {world.workspace_id: Role.VIEWER})
    with pytest.raises(Forbidden) as caught:
        start(world, proposed.intent_id, "watcher")
    assert caught.value.details["permission"] == "run.control"
    start(world, proposed.intent_id)
    with pytest.raises(Forbidden):
        world.run(RecordIntentOutcome(intent_id=proposed.intent_id, outcome="succeeded", receipt={}), viewer)
