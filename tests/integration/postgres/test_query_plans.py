"""Hot adapter statements are served by an index, not by a scan of the whole table.

Each statement is planned generically (``EXPLAIN (GENERIC_PLAN)``) on a fresh migrated database with
sequential scans disabled. A ``Seq Scan`` or an index scan without a condition over a full index visits
the whole relation, so we require plans that constrain each lookup. A scan without a condition can
use a partial index because it already holds only the rows its predicate selects.
"""

import os
import re
from collections.abc import Iterator, Mapping
from typing import Any

import psycopg
import pytest

from skm.adapters.postgres.access import repositories as access_repositories
from skm.adapters.postgres.execution import (
    attempts_stages,
    budgets,
    decisions_effects,
    integration_slots,
    queries,
    queries_events_outcomes,
    runs_tasks,
)
from skm.adapters.postgres.workspace import mounts
from support.pg import PgSession, TestDatabase

pytestmark = pytest.mark.pg

_PLACEHOLDER = re.compile(r"%%|%s")
_INDEX_SCANS = frozenset({"Index Scan", "Index Only Scan"})
# the lateral lookup the decision inbox runs once per listed request
_LATEST_RECORD_OF_REQUEST = """
SELECT id, status FROM skm_execution.decision_records
 WHERE request_id = %s
 ORDER BY created_at DESC, id DESC
 LIMIT 1
"""


@pytest.fixture(scope="module")
def _plan_session() -> Iterator[PgSession]:
    # The shared worker database retains planner statistics after functional tests delete their rows.
    # A dedicated clone gives the generic plans the same data and statistics in every test order.
    session = PgSession(worker="queryplans", pid=os.getpid())
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def plan_database(_plan_session: PgSession, pg_dsn: str) -> TestDatabase:
    return _plan_session.open(pg_dsn)


def _numbered(statement: str) -> str:
    """The client-side ``%s`` placeholders as the server-side ``$n`` parameters a generic plan takes."""
    counter = iter(range(1, statement.count("%s") + 1))
    return _PLACEHOLDER.sub(lambda match: "%" if match.group() == "%%" else f"${next(counter)}", statement)


def _nodes(plan: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    yield plan
    for child in plan.get("Plans", ()):
        yield from _nodes(child)


def _full_scans(dsn: str, statement: str) -> list[str]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET enable_seqscan = off")
        row = conn.execute(
            b"EXPLAIN (GENERIC_PLAN, VERBOSE, FORMAT JSON) " + _numbered(statement).encode()
        ).fetchone()
        assert row is not None
        return [
            f"{node['Schema']}.{node['Relation Name']}"
            for node in _nodes(row[0][0]["Plan"])
            if node["Node Type"] == "Seq Scan"
            or (
                node["Node Type"] in _INDEX_SCANS
                and "Index Cond" not in node
                and not _is_partial(conn, f"{node['Schema']}.{node['Index Name']}")
            )
        ]


def _is_partial(conn: psycopg.Connection[Any], index: str) -> bool:
    row = conn.execute(
        "SELECT indpred IS NOT NULL FROM pg_index WHERE indexrelid = %s::regclass", (index,)
    ).fetchone()
    assert row is not None
    return bool(row[0])


@pytest.mark.parametrize(
    "statement",
    [
        pytest.param(budgets._ACCOUNTS_RUN_ONLY, id="budget-accounts-of-run"),
        pytest.param(budgets._ACCOUNTS_RUN_AND_TASK, id="budget-accounts-of-run-and-task"),
        pytest.param(budgets._RAISE_RUN_LIMIT, id="raise-run-budget-limit"),
        pytest.param(budgets._RAISE_TASK_LIMIT, id="raise-task-budget-limit"),
        pytest.param(queries_events_outcomes._BUDGET_ACCOUNTS_FOR_RUN, id="budget-view-of-run"),
        pytest.param(queries_events_outcomes._LATEST_REVIEW_FOR_RUN, id="latest-review-of-run"),
        pytest.param(queries._CHECKS_FOR_ATTEMPT, id="checks-of-attempt"),
        pytest.param(queries._REVIEWS_FOR_ATTEMPT, id="reviews-of-attempt"),
        pytest.param(queries._RECOVERIES_FOR_ATTEMPT, id="recoveries-of-attempt"),
        pytest.param(_LATEST_RECORD_OF_REQUEST, id="latest-decision-record-of-request"),
        pytest.param(runs_tasks._STAGE_INTERVALS, id="stage-intervals-of-run"),
        pytest.param(attempts_stages._REAP_CONFIRMED, id="reap-receipt-of-stage"),
        pytest.param(decisions_effects._UNRESOLVED_EFFECTS, id="unresolved-effects"),
        pytest.param(decisions_effects._COUNT_DECISIONS_FOR_TASK, id="decision-count-of-task"),
    ],
)
def test_statement_reaches_an_index(plan_database: TestDatabase, statement: str) -> None:
    assert _full_scans(plan_database.dsn, statement) == []


def _lock_inputs(dsn: str, statement: str) -> list[str]:
    """The node feeding each row lock, planned with index scans off so no index order hides a missing sort."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET enable_indexscan = off")
        conn.execute("SET enable_indexonlyscan = off")
        row = conn.execute(b"EXPLAIN (GENERIC_PLAN, FORMAT JSON) " + _numbered(statement).encode()).fetchone()
    assert row is not None
    return [
        node["Plans"][0]["Node Type"] for node in _nodes(row[0][0]["Plan"]) if node["Node Type"] == "LockRows"
    ]


@pytest.mark.parametrize(
    "statement",
    [
        pytest.param(access_repositories._ACTIVE_OWNERS, id="active-owners-of-scope"),
        pytest.param(mounts._LOCK_PROJECT, id="mounts-of-project"),
    ],
)
def test_multi_row_locks_follow_a_fixed_order(plan_database: TestDatabase, statement: str) -> None:
    """Rows locked in plan order can be taken in opposite orders by two writers, which deadlocks them."""
    assert _lock_inputs(plan_database.dsn, statement) == ["Sort"]


def test_a_review_receipt_reaches_the_run_reviews_through_an_index(plan_database: TestDatabase) -> None:
    """The lookup filters runs by request or project; only its per-run review probes are pinned."""
    assert "skm_execution.reviews" not in _full_scans(plan_database.dsn, integration_slots._RUN_FOR_RECEIPT)
