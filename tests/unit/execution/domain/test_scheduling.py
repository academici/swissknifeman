"""Pure position, batch, scope, target pin and distinct-unit admission scenarios."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from skm.kernel.ids import EntityId, RunId, TaskId, WorkspaceId
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.scheduling import (
    SchedulingInput,
    globs_overlap,
    refusal,
    required_host,
    select_assignable,
)
from skm.modules.execution.domain.task import PathPattern, ReviewMode, Task, TaskKind, TaskStatus
from skm.modules.execution.domain.task_graph import EdgeKind, TaskEdge


def task(number, *, scope=None, status=TaskStatus.READY, work_kind="code"):
    return Task(
        id=TaskId(UUID(int=number)),
        run_id=RunId(UUID(int=100)),
        workspace_id=WorkspaceId(UUID(int=101)),
        kind=TaskKind.UNIT,
        spec_entity_id=EntityId(UUID(int=1000 + number)),
        display_key=f"U{number}",
        origin=None,
        position=number,
        status=status,
        work_kind=work_kind,
        review_mode=ReviewMode.SELF,
        review_profile=None,
        declared_write_scope=(PathPattern("repo", f"src/u{number}/**"),) if scope is None else scope,
        required_host_id=None,
        current_attempt_id=None,
        accepted_attempt_id=None,
        accepted_output_id=None,
        check_fix_rounds=0,
        review_rounds=0,
        attempt_count=0,
        blocking_reason=None,
        row_version=1,
    )


def inputs(*tasks, **changes):
    defaults = {
        "run": SimpleNamespace(status=RunStatus.RUNNING),
        "tasks": tuple(tasks),
        "edges": (),
        "in_flight": (),
        "pending_scopes": (),
        "max_units": 2,
        "batch_groups": {},
        "existing_checkout_repos_busy": frozenset(),
        "integration_hosts": {},
        "integration_targets": {},
        "target_hosts": {},
        "mount_repositories": {},
    }
    return SchedulingInput(**(defaults | changes))


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("src/**", "docs/**", False),
        ("src", "src/main.py", True),
        ("src/a*", "src/b*", False),
        ("src/*/a", "src/b/*", True),
        ("src/**/a", "src/a", True),
        ("src/[ab]", "src/a", True),
        ("../escape", "docs/a", True),
        ("/absolute", "other", True),
        (".", "anything", True),
        ("src/?", "src/ab", False),
    ],
)
def test_conservative_glob_language(left, right, expected):
    assert globs_overlap(left, right) is expected
    assert globs_overlap(right, left) is expected


def test_deterministic_positions_and_dependencies():
    first, second, last = task(1), task(2), task(3)
    edge = TaskEdge(first.run_id, second.id, first.id, EdgeKind.BLOCKS, frozenset())
    assert select_assignable(inputs(last, second, first, edges=(edge,))) == (first.id, last.id)
    accepted = replace(first, status=TaskStatus.ACCEPTED)
    assert select_assignable(inputs(last, second, accepted, edges=(edge,))) == (second.id, last.id)


def test_required_batch_reserves_released_slots_before_younger_tasks():
    first, second, younger, running = task(1), task(2), task(3), task(4)
    groups = {first.id: "required", second.id: "required"}
    assert select_assignable(inputs(first, second, younger, in_flight=(running,), batch_groups=groups)) == ()
    assert select_assignable(inputs(first, second, younger, batch_groups=groups)) == (first.id, second.id)


def test_ineligible_batch_does_not_block_eligible_later_work():
    first, second, younger = task(1), task(2), task(3)
    edge = TaskEdge(first.run_id, first.id, second.id, EdgeKind.BLOCKS, frozenset())
    assert select_assignable(
        inputs(
            first, second, younger, edges=(edge,), batch_groups={first.id: "required", second.id: "required"}
        )
    ) == (younger.id,)


def test_pending_scope_protects_writes_without_consuming_a_slot_and_excludes_self():
    first = task(1, scope=(PathPattern("repo", "src/**"),))
    overlap = task(2, scope=(PathPattern("repo", "src/foo.py"),))
    disjoint = task(3, scope=(PathPattern("repo", "docs/**"),))
    assert select_assignable(inputs(first, overlap, disjoint, pending_scopes=(first,))) == (
        first.id,
        disjoint.id,
    )


@pytest.mark.parametrize("work_kind", ["research", "review"])
def test_non_writing_work_has_no_scope_conflicts(work_kind):
    unknown = replace(task(1), declared_write_scope=None)
    reader = task(2, work_kind=work_kind)
    assert select_assignable(inputs(unknown, reader)) == (unknown.id, reader.id)


def test_unknown_scope_and_gate_scope():
    unknown = replace(task(1), declared_write_scope=None)
    gate = replace(task(2, scope=()), kind=TaskKind.ITEM_GATE)
    assert select_assignable(inputs(unknown, task(3), gate)) == (unknown.id, gate.id)


def test_active_capacity_counts_distinct_attempts_not_statuses():
    first, second = task(1), task(2)
    assert select_assignable(inputs(first, second, max_units=1, pending_scopes=(first, second))) == (
        first.id,
    )
    active = replace(first, current_attempt_id=UUID(int=200), status=TaskStatus.REVIEWING)
    assert select_assignable(inputs(second, in_flight=(active, active), max_units=2)) == (second.id,)
    assert select_assignable(inputs(second, in_flight=(active,), max_units=1)) == ()


def test_existing_checkout_is_busy_for_the_project():
    repo = UUID(int=300)
    first = task(1)
    data = inputs(first, existing_checkout_repos_busy=frozenset({repo}), mount_repositories={"repo": repo})
    assert refusal(first, data) == "CHECKOUT_BUSY"
    assert select_assignable(data) == ()


def test_target_pin_survives_slot_absence_and_merges_with_run_pin():
    repo, host, foreign = UUID(int=300), UUID(int=301), UUID(int=302)
    first = task(1)
    data = inputs(
        first,
        integration_targets={repo: "main"},
        target_hosts={(repo, "main"): host},
        mount_repositories={"repo": repo},
    )
    assert required_host(first, data) == (host, None)
    conflict = replace(data, integration_hosts={repo: foreign})
    assert refusal(first, conflict) == "INTEGRATION_HOST_MISMATCH"
    assert select_assignable(conflict) == ()


def test_multiple_mount_pins_must_agree():
    a, b, h1, h2 = (UUID(int=i) for i in (300, 301, 302, 303))
    writer = task(1, scope=(PathPattern("a", "src/**"), PathPattern("b", "src/**")))
    data = inputs(
        writer,
        mount_repositories={"a": a, "b": b},
        integration_targets={a: "main", b: "main"},
        target_hosts={(a, "main"): h1, (b, "main"): h2},
    )
    assert required_host(writer, data) == (None, "INTEGRATION_HOST_MISMATCH")


@pytest.mark.parametrize("status", [TaskStatus.CHECKING, TaskStatus.REVIEWING, TaskStatus.INTEGRATING])
def test_eligible_continuations_do_not_depend_on_historical_task_status(status):
    candidate = task(1, status=status)
    assert select_assignable(inputs(candidate)) == (candidate.id,)


def test_required_batch_is_atomic_under_a_smaller_tick_limit():
    first, second, younger = task(1), task(2), task(3)
    data = inputs(first, second, younger, batch_groups={first.id: "required", second.id: "required"})
    assert select_assignable(data, limit=1) == ()
    assert select_assignable(data, limit=2) == (first.id, second.id)


def test_checkout_owner_continues_but_a_foreign_writer_keeps_the_repository_busy():
    repo, attempt_id = UUID(int=300), UUID(int=400)
    owner = replace(task(1), current_attempt_id=attempt_id)
    foreign = task(2)
    data = inputs(
        owner,
        foreign,
        existing_checkout_repos_busy=frozenset({repo}),
        mount_repositories={"repo": repo},
        existing_checkout_repos_busy_by_attempt={attempt_id: frozenset()},
    )
    assert refusal(owner, data) is None
    assert refusal(foreign, data) == "CHECKOUT_BUSY"
    assert select_assignable(data) == (owner.id,)
    data = replace(data, existing_checkout_repos_busy_by_attempt={attempt_id: frozenset({repo})})
    assert refusal(owner, data) == "CHECKOUT_BUSY"
    assert select_assignable(data) == ()
