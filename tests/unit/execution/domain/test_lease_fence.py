"""Assignments, leases and the monotonic fence (execution §4.9; audit «Leases и fencing»)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from itertools import product
from typing import Any
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.assignment import (
    ASSIGNMENT_TRANSITIONS,
    TERMINAL_ASSIGNMENT_STATES,
    Assignment,
    AssignmentState,
    WorkerRequirements,
    reissue,
    retry_later,
    transition_assignment,
)
from skm.modules.execution.domain.attempt import Attempt, AttemptState, bind_executor_route
from skm.modules.execution.domain.environment import EnvironmentKind
from skm.modules.execution.domain.lease import (
    Lease,
    ProcessIdentity,
    WorkerClaim,
    issue_lease,
    next_fencing_token,
    renew_lease,
    verify_fence,
)
from skm.modules.execution.domain.session import RouteRef
from skm.modules.execution.domain.step import AttemptStep, RoleId, StepPurpose, StepState

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
TTL = timedelta(seconds=90)
WORKER: Any = UUID(int=40)
OTHER_WORKER: Any = UUID(int=41)


def uid(n: int) -> Any:
    return UUID(int=n)


def requirements(host: Any = None) -> WorkerRequirements:
    return WorkerRequirements(
        frozenset({"runtime:fake"}), host, frozenset(), EnvironmentKind.GIT_WORKTREE, frozenset()
    )


def make_assignment(state: AssignmentState = AssignmentState.AVAILABLE, **changes: Any) -> Assignment:
    values: dict[str, Any] = {
        "id": uid(10),
        "run_id": uid(1),
        "task_id": uid(100),
        "attempt_id": uid(200),
        "workspace_id": uid(2),
        "state": state,
        "available_at": NOW,
        "requirements": requirements(),
        "priority": 0,
        "last_fencing_token": 0,
        "reconcile_effect_id": None,
        "reap_stage_record_id": None,
        "reap_step_id": None,
        "created_at": NOW,
        "row_version": 1,
    }
    values.update(changes)
    return Assignment(**values)


def claimed() -> tuple[Assignment, Lease, WorkerClaim]:
    assignment, lease = issue_lease(make_assignment(), worker_id=WORKER, now=NOW, ttl=TTL)
    return assignment, lease, WorkerClaim(assignment.id, assignment.attempt_id, WORKER, lease.fencing_token)


# --- verify_fence


def test_the_holder_passes_the_fence() -> None:
    assignment, lease, claim = claimed()
    verify_fence(lease, assignment, claim, NOW + timedelta(seconds=30))


def refused(lease: Lease | None, assignment: Assignment, claim: WorkerClaim, now: datetime) -> str:
    with pytest.raises(SkmError) as caught:
        verify_fence(lease, assignment, claim, now)
    assert caught.value.code is ErrorCode.LEASE_LOST
    return str(caught.value.details["reason"])


def test_each_broken_condition_loses_the_lease() -> None:
    assignment, lease, claim = claimed()
    later = NOW + timedelta(seconds=30)
    assert refused(None, assignment, claim, later) == "no_lease"
    assert (
        refused(lease, assignment, dataclasses.replace(claim, worker_id=OTHER_WORKER), later)
        == "other_worker"
    )
    assert (
        refused(lease, assignment, dataclasses.replace(claim, fencing_token=claim.fencing_token - 1), later)
        == "stale_token"
    )
    assert (
        refused(lease, assignment, dataclasses.replace(claim, fencing_token=claim.fencing_token + 1), later)
        == "stale_token"
    )
    assert refused(lease, assignment, claim, lease.expires_at) == "expired"
    assert refused(lease, assignment, claim, lease.expires_at + timedelta(seconds=1)) == "expired"
    assert (
        refused(lease, assignment, dataclasses.replace(claim, attempt_id=uid(201)), later) == "other_attempt"
    )
    assert (
        refused(lease, dataclasses.replace(assignment, attempt_id=uid(201)), claim, later) == "other_attempt"
    )
    assert (
        refused(lease, dataclasses.replace(assignment, state=AssignmentState.COMPLETED), claim, later)
        == "not_leased"
    )
    assert (
        refused(lease, assignment, dataclasses.replace(claim, assignment_id=uid(11)), later)
        == "other_assignment"
    )
    assert (
        refused(dataclasses.replace(lease, assignment_id=uid(11)), assignment, claim, later)
        == "other_assignment"
    )


# --- monotonic tokens and reissue


def test_each_issue_of_a_row_takes_a_greater_token() -> None:
    assignment, lease, claim = claimed()
    assert (lease.fencing_token, assignment.last_fencing_token, next_fencing_token(assignment)) == (1, 1, 2)
    released = retry_later(assignment, available_at=NOW + timedelta(seconds=10))
    assert (released.state, released.id, released.available_at) == (
        AssignmentState.AVAILABLE,
        assignment.id,
        NOW + timedelta(seconds=10),
    )
    with pytest.raises(SkmError, match="not available yet"):
        issue_lease(released, worker_id=WORKER, now=NOW, ttl=TTL)
    again, second = issue_lease(released, worker_id=OTHER_WORKER, now=NOW + timedelta(seconds=10), ttl=TTL)
    assert second.fencing_token == 2
    assert refused(second, again, claim, NOW + timedelta(seconds=11)) in {"other_worker", "stale_token"}


def test_a_reissue_is_a_new_row_and_the_old_claim_is_refused() -> None:
    assignment, lease, claim = claimed()
    expired = transition_assignment(assignment, AssignmentState.EXPIRED)
    with pytest.raises(SkmError) as caught:
        transition_assignment(expired, AssignmentState.AVAILABLE)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION
    fresh = reissue(expired, new_id=uid(12), now=NOW + timedelta(minutes=2))
    assert (fresh.id, fresh.state, fresh.attempt_id, fresh.row_version) == (
        uid(12),
        AssignmentState.AVAILABLE,
        uid(200),
        1,
    )
    leased, new_lease = issue_lease(fresh, worker_id=WORKER, now=NOW + timedelta(minutes=2), ttl=TTL)
    assert new_lease.fencing_token > lease.fencing_token  # the attempt's token sequence goes on
    assert refused(new_lease, leased, claim, NOW + timedelta(minutes=2)) == "other_assignment"
    with pytest.raises(SkmError, match="only a finished assignment"):
        reissue(leased, new_id=uid(13), now=NOW)
    with pytest.raises(SkmError, match="new assignment row"):
        reissue(expired, new_id=expired.id, now=NOW)


@settings(max_examples=50, deadline=None)
@given(st.lists(st.sampled_from(["retry_later", "reissue"]), min_size=1, max_size=12))
def test_tokens_of_an_attempt_only_grow(steps: list[str]) -> None:
    assignment, lease = issue_lease(make_assignment(), worker_id=WORKER, now=NOW, ttl=TTL)
    tokens = [lease.fencing_token]
    for n, step in enumerate(steps):
        if step == "retry_later":
            assignment = retry_later(assignment, available_at=NOW)
        else:
            assignment = reissue(
                transition_assignment(assignment, AssignmentState.EXPIRED), new_id=uid(1000 + n), now=NOW
            )
        assignment, lease = issue_lease(assignment, worker_id=WORKER, now=NOW, ttl=TTL)
        tokens.append(lease.fencing_token)
    assert tokens == sorted(set(tokens))


def test_renew_keeps_the_token_and_the_first_process_identity() -> None:
    assignment, lease, claim = claimed()
    first = ProcessIdentity(10, 10, NOW, {"owner": {"unit_kind": "step", "unit_id": "s1"}})
    second = ProcessIdentity(11, 11, NOW, {"owner": {"unit_kind": "step", "unit_id": "s1"}})
    renewed = renew_lease(
        lease, assignment, claim, now=NOW + timedelta(seconds=30), ttl=TTL, process_identity=first
    )
    renewed = renew_lease(
        renewed, assignment, claim, now=NOW + timedelta(seconds=60), ttl=TTL, process_identity=second
    )
    assert (renewed.fencing_token, renewed.process_identity, renewed.expires_at) == (
        lease.fencing_token,
        first,
        NOW + timedelta(seconds=150),
    )
    with pytest.raises(SkmError) as caught:
        renew_lease(lease, assignment, dataclasses.replace(claim, fencing_token=9), now=NOW, ttl=TTL)
    assert caught.value.code is ErrorCode.LEASE_LOST


# --- assignment states


@pytest.mark.parametrize(
    ("source", "target"), list(product(AssignmentState, AssignmentState)), ids=lambda s: s.value
)
def test_assignment_table(source: AssignmentState, target: AssignmentState) -> None:
    assignment = make_assignment(source)
    if (source, target) in ASSIGNMENT_TRANSITIONS:
        assert transition_assignment(assignment, target).state is target
        assert source not in TERMINAL_ASSIGNMENT_STATES
        return
    with pytest.raises(SkmError) as caught:
        transition_assignment(assignment, target)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION


def test_leased_returns_to_available_only_by_retry_later() -> None:
    assert (AssignmentState.LEASED, AssignmentState.AVAILABLE) in ASSIGNMENT_TRANSITIONS
    assert {
        target for source, target in ASSIGNMENT_TRANSITIONS if source in TERMINAL_ASSIGNMENT_STATES
    } == set()


def test_reap_barrier_fields() -> None:
    pinned = requirements(host=uid(5))
    l2_check = make_assignment(requirements=pinned, reap_stage_record_id=uid(900))
    assert l2_check.reap_step_id is None  # a check stage has no step
    l2_agent = make_assignment(requirements=pinned, reap_stage_record_id=uid(900), reap_step_id=uid(80))
    assert l2_agent.reap_step_id == uid(80)
    with pytest.raises(SkmError, match="reap_step_id"):
        make_assignment(requirements=pinned, reap_step_id=uid(80))
    with pytest.raises(SkmError, match="pinned to the environment host"):
        make_assignment(reap_stage_record_id=uid(900))
    with pytest.raises(SkmError, match="reconcile"):
        make_assignment(reconcile_effect_id=uid(77))
    with pytest.raises(SkmError, match="reconcile"):
        make_assignment(requirements=pinned, reconcile_effect_id=uid(77), reap_stage_record_id=uid(900))
    expired = transition_assignment(
        transition_assignment(l2_agent, AssignmentState.LEASED), AssignmentState.EXPIRED
    )
    again = reissue(expired, new_id=uid(14), now=NOW, reap_stage_record_id=uid(901))
    assert (again.reap_stage_record_id, again.reap_step_id) == (uid(901), None)


# --- route binding is history


def test_a_route_change_does_not_rewrite_past_bindings() -> None:
    attempt = Attempt(
        uid(200), uid(1), uid(100), uid(2), 1, AttemptState.RUNNING, WORKER, uid(5), uid(6), uid(300),
        None, None, NOW, None, None,
    )  # fmt: skip
    first_route = RouteRef("claude_code", "m-implementation", "high")
    bound = bind_executor_route(attempt, first_route)
    rebound = bind_executor_route(bound, RouteRef("codex", "m-fallback", "medium"))
    assert rebound.executor_route == first_route
    assert rebound.current_output_id == uid(300)
    snapshot: dict[str, Any] = {
        "requested": {"class": "implementation"},
        "resolved": {"runtime_id": "claude_code", "model": "m1"},
    }
    step = AttemptStep(
        uid(80), uid(200), uid(900), None, 1, RoleId.EXECUTOR, StepPurpose.PRIMARY, "claude_code", "m1",
        "high", "new_implementation", {}, "plan_route", "ROUTE_DEFAULT", uid(81), "new", None,
        None,  # type: ignore[arg-type]
        "sha256:" + "1" * 64, None, StepState.STARTED, None, None, (), (), None, None, None, None,
        snapshot, None, None, None, None, None, NOW, None,
    )  # fmt: skip
    snapshot["resolved"]["model"] = "m2"
    assert step.route_snapshot is not None
    assert step.route_snapshot["resolved"] == {"runtime_id": "claude_code", "model": "m1"}
    with pytest.raises(TypeError):
        step.route_snapshot["resolved"] = {}  # type: ignore[index]
