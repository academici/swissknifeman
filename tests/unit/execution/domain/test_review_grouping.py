"""Group review selection (execution §5.9; port of review strategy ``rules()``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from skm.modules.execution.domain.review_grouping import MAX_GROUP, choose_grouping
from skm.modules.execution.domain.task import PathPattern, ReviewMode, Task, TaskKind, TaskStatus

GROUPS: dict[str, Any] = {"review_grouping": "groups"}


def uid(n: int) -> Any:
    return UUID(int=n)


def task(n: int, *scope: str, mode: ReviewMode = ReviewMode.REQUIRED, key: str = "", **changes: Any) -> Task:
    values: dict[str, Any] = {
        "id": uid(100 + n),
        "run_id": uid(1),
        "workspace_id": uid(2),
        "kind": TaskKind.ITEM,
        "spec_entity_id": uid(300 + n),
        "display_key": key or f"P1.{n}",
        "origin": None,
        "position": n,
        "status": TaskStatus.READY,
        "work_kind": "code",
        "review_mode": mode,
        "review_profile": None,
        "declared_write_scope": tuple(PathPattern("app", pattern) for pattern in scope),
        "required_host_id": None,
        "current_attempt_id": None,
        "accepted_attempt_id": None,
        "accepted_output_id": None,
        "check_fix_rounds": 0,
        "review_rounds": 0,
        "attempt_count": 0,
        "blocking_reason": None,
        "row_version": 1,
    }
    values.update(changes)
    return Task(**values)


def ids(*numbers: int) -> tuple[Any, ...]:
    return tuple(uid(100 + n) for n in numbers)


def test_grouping_off_by_default() -> None:
    result = choose_grouping([task(1, "src/a/**"), task(2, "src/a/**")], {})
    assert (result.mode, result.groups) == ("none", ())


def test_neighbours_sharing_folders_are_grouped() -> None:
    tasks = [
        task(1, "src/api/auth/x.py"),
        task(2, "src/api/auth/**"),
        task(3, "docs/guide.md"),
        task(4, "docs/**"),
    ]
    result = choose_grouping(tasks, GROUPS)
    assert result.mode == "groups"
    assert result.groups == (ids(1, 2), ids(3, 4))


def test_order_is_by_position_and_neighbours_only() -> None:
    tasks = [task(3, "src/a/x.py"), task(1, "src/a/y.py"), task(2, "lib/b/z.py")]
    result = choose_grouping(tasks, GROUPS)
    assert result.groups == (ids(1), ids(2), ids(3))


def test_group_size_is_capped() -> None:
    tasks = [task(n, "src/shared/**") for n in range(1, MAX_GROUP + 3)]
    result = choose_grouping(tasks, GROUPS)
    assert [len(group) for group in result.groups] == [MAX_GROUP, 2]


def test_solo_paths_and_frontier_tasks_are_reviewed_alone() -> None:
    tasks = [task(1, "src/a/x.py"), task(2, "src/a/vault/**"), task(3, "src/a/y.py"), task(4, "src/a/z.py")]
    result = choose_grouping(tasks, GROUPS, solo_paths=["src/a/vault/**"])
    assert result.groups == (ids(1), ids(2), ids(3, 4))
    frontier = choose_grouping(tasks, GROUPS, frontier={uid(103)})
    assert frontier.groups == (ids(1, 2), ids(3), ids(4))


@pytest.mark.parametrize(
    ("scope", "solo"),
    [
        ("src/**", "src/auth/**"),
        ("src/auth/**", "src/**"),
        ("**/*.py", "src/auth/**"),
        ("src/a*/**", "src/auth/**"),
        ("src/[ab]/**", "src/auth/**"),
        ("./src/**", "src/auth/**"),
        ("src\\**", "src/auth/**"),
    ],
)
def test_scopes_that_may_overlap_solo_paths_are_never_grouped(scope: str, solo: str) -> None:
    assert choose_grouping([task(1, scope), task(2, scope)], GROUPS, solo_paths=[solo]).groups == (
        ids(1),
        ids(2),
    )


def test_provably_disjoint_scopes_still_group() -> None:
    result = choose_grouping([task(1, "src/ui/**"), task(2, "src/ui/**")], GROUPS, solo_paths=["src/auth/**"])
    assert result.groups == (ids(1, 2),)


def test_waived_tasks_are_outside_groups_and_all_waived_is_none() -> None:
    waived = [task(1, "src/a/**", mode=ReviewMode.WAIVED), task(2, "src/a/**", mode=ReviewMode.WAIVED)]
    assert choose_grouping(waived, GROUPS).mode == "none"
    mixed = [task(1, "src/a/**"), task(2, "src/a/**", mode=ReviewMode.WAIVED), task(3, "src/a/**")]
    assert choose_grouping(mixed, GROUPS).groups == (ids(1, 3),)


def test_a_single_task_is_none_and_gates_are_not_grouped() -> None:
    assert choose_grouping([task(1, "src/a/**")], GROUPS).mode == "none"
    gate = task(2, kind=TaskKind.ITEM_GATE)
    assert choose_grouping([task(1, "src/a/**"), gate], GROUPS).mode == "none"


def test_undeclared_scope_joins_no_group() -> None:
    tasks = [task(1, "src/a/**"), task(2, declared_write_scope=None), task(3, "src/a/**")]
    assert choose_grouping(tasks, GROUPS).groups == (ids(1), ids(2), ids(3))


def test_reviewer_effort_high_on_markers() -> None:
    plain = choose_grouping([task(1, "src/a/**"), task(2, "src/a/**")], GROUPS)
    assert plain.reviewer_effort == "medium"
    marked = choose_grouping([task(1, "src/a/**", key="P1.1 Token auth"), task(2, "src/a/**")], GROUPS)
    assert marked.reviewer_effort == "high"
    by_path = choose_grouping([task(1, "src/sandbox/**"), task(2, "src/sandbox/**")], GROUPS)
    assert by_path.reviewer_effort == "high"
