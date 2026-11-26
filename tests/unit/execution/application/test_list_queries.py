"""``execution.list_runs`` and ``execution.list_decision_requests``: filters, newest-first pages, cursors."""

from datetime import timedelta
from typing import Any

import pytest

from contracts.execution.harness import exec_side as exec_side
from contracts.execution.seed_helpers import seed_run
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionRequest,
    DecisionState,
)
from skm.modules.execution.domain.run import Run, RunStatus
from skm.modules.execution.generated.queries import ListDecisionRequests, ListRuns
from skm.modules.execution.ports import DecisionRepository
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database


def runs(side: Any, *specs: tuple[bool, RunStatus]) -> list[Run]:
    """One run per (first plan?, status), a second apart: the listing order is creation order reversed."""
    start = side.clock.now()
    with side.uow() as uow:
        made = [
            seed_run(
                side,
                uow,
                plan_id=side.plan1 if first_plan else side.plan2,
                rev_id=side.rev1 if first_plan else side.rev_p2,
                status=status,
                created_at=start + timedelta(seconds=index),
            )
            for index, (first_plan, status) in enumerate(specs)
        ]
        uow.commit()
    return made


def ask(side: Any, query: object) -> dict[str, Any]:
    return side.client.ask(query).to_json()


def run_ids(view: dict[str, Any]) -> list[str]:
    return [item["run_id"] for item in view["items"]]


def refused(side: Any, query: object, client: Any = None) -> SkmError:
    with pytest.raises(SkmError) as caught:
        (client or side.client).ask(query)
    return caught.value


def test_runs_are_newest_first_and_filtered_by_status_kind_and_plan(exec_side: Any) -> None:
    side = exec_side
    made = runs(side, (True, RunStatus.SUCCEEDED), (False, RunStatus.RUNNING), (True, RunStatus.RUNNING))
    listed = ask(side, ListRuns(project_id=side.proj))
    assert run_ids(listed) == [str(run.id) for run in reversed(made)]
    assert listed["next_after"] is None
    running = ask(side, ListRuns(project_id=side.proj, statuses=("running",)))
    assert run_ids(running) == [str(made[2].id), str(made[1].id)]
    first_plan = ask(side, ListRuns(project_id=side.proj, plan_id=side.plan1))
    assert run_ids(first_plan) == [str(made[2].id), str(made[0].id)]
    # Only plan runs are listed unless other kinds are asked for.
    assert ask(side, ListRuns(project_id=side.proj, kinds=("review_request",)))["items"] == []


def test_run_pages_cover_every_match_once_and_end_without_a_cursor(exec_side: Any) -> None:
    side = exec_side
    # The plan filter is applied by the handler, so pages must skip the other plan's runs.
    made = runs(side, *[(True, RunStatus.RUNNING), (False, RunStatus.RUNNING)] * 3)
    expected = [str(run.id) for run in reversed(made) if run.plan_id == side.plan1]
    seen: list[str] = []
    after: str | None = None
    for _ in range(len(expected)):
        page = ask(side, ListRuns(project_id=side.proj, plan_id=side.plan1, limit=2, after=after))
        seen.extend(run_ids(page))
        after = page["next_after"]
        if after is None:
            break
    assert seen == expected
    assert after is None


def test_a_run_cursor_is_bound_to_its_filters_and_reader(exec_side: Any) -> None:
    side = exec_side
    runs(side, *[(True, RunStatus.RUNNING)] * 3)
    after = ask(side, ListRuns(project_id=side.proj, limit=1))["next_after"]
    assert after is not None
    for query, client in (
        (ListRuns(project_id=side.proj, limit=1, after=after, statuses=("running",)), None),
        (ListRuns(project_id=side.proj, limit=1, after=after, plan_id=side.plan1), None),
        (ListRuns(project_id=side.proj, limit=1, after=after), side.viewer_client),
    ):
        error = refused(side, query, client)
        assert error.code.value == "SCHEMA_INVALID"
        assert error.details.get("field") == "after"


def decision(side: Any, run: Run, state: DecisionState, seconds: int) -> DecisionRequest:
    return DecisionRequest(
        side.new_id(),
        side.ws,
        run.id,
        None,
        DecisionKind.ESCALATION,
        Audience.OWNER,
        None,
        frozenset(),
        None,
        None,
        1,
        {"code": "budget_exhausted", "options": ["resume_run", "fail"]},
        None,
        {},
        state,
        None,
        None,
        side.clock.now() + timedelta(seconds=seconds),
    )


def test_decision_requests_default_to_open_and_page_newest_first(exec_side: Any) -> None:
    side = exec_side
    [run] = runs(side, (True, RunStatus.PAUSED))
    with side.uow() as uow:
        made = [
            decision(side, run, state, index)
            for index, state in enumerate(
                (DecisionState.OPEN, DecisionState.CANCELLED, DecisionState.OPEN, DecisionState.OPEN)
            )
        ]
        for request in made:
            uow.repo(DecisionRepository).add(request)
        uow.commit()
    open_newest_first = [str(made[i].id) for i in (3, 2, 0)]
    for scope in ({"kind": "run", "id": str(run.id)}, {"project_id": str(side.proj)}):
        first = ask(side, ListDecisionRequests(scope=scope, limit=2))
        assert [item["request_id"] for item in first["items"]] == open_newest_first[:2]
        assert first["next_after"] is not None
        rest = ask(side, ListDecisionRequests(scope=scope, limit=2, after=first["next_after"]))
        assert [item["request_id"] for item in rest["items"]] == open_newest_first[2:]
        assert rest["next_after"] is None
    cancelled = ask(side, ListDecisionRequests(scope={"run_id": str(run.id)}, states=("cancelled",)))
    assert [item["request_id"] for item in cancelled["items"]] == [str(made[1].id)]
    after = ask(side, ListDecisionRequests(scope={"run_id": str(run.id)}, limit=1))["next_after"]
    error = refused(
        side, ListDecisionRequests(scope={"run_id": str(run.id)}, limit=1, after=after, kinds=("budget",))
    )
    assert (error.code.value, error.details.get("field")) == ("SCHEMA_INVALID", "after")
