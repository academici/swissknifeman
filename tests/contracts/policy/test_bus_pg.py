"""The policy commands through the real bus on PostgreSQL (policy §7, §11; consistency §07).

The atomic consume of an approval, the unique open intent and the live checks are claims about transactions:
here they run against real row locks, unique indexes and triggers. Two concurrent starts admit the effect
once; two concurrent identical proposals are one intent; a revoked ceiling or a lost membership blocks the
start; an interrupted transaction spends nothing.
"""

import threading
from collections.abc import Iterator
from typing import Any

import pytest

from contracts.policy.pg_world import PgWorld, build_pg_world
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.access.generated.commands import RevokeMembership
from skm.modules.access.public import Role
from skm.modules.policy.generated.commands import StartIntentExecution
from support.pg import TestDatabase, clean_test_database, pg_session, test_database  # noqa: F401
from unit.policy.application.test_lifecycle import approve, outcome, propose, start, view

pytestmark = pytest.mark.pg


@pytest.fixture
def pg_world(clean_test_database: TestDatabase) -> Iterator[PgWorld]:  # noqa: F811 - the imported fixture
    made = build_pg_world(clean_test_database)
    try:
        yield made
    finally:
        made.close()


def race(count: int, work: Any) -> list[object]:
    gate = threading.Barrier(count)
    results: list[object] = []

    def attempt(index: int) -> None:
        gate.wait()
        try:
            results.append(work(index))
        except SkmError as error:
            results.append(error)

    threads = [threading.Thread(target=attempt, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_the_whole_life_commits_state_events_and_the_spent_approval_together(pg_world: PgWorld) -> None:
    proposed = propose(pg_world)
    assert proposed.needs_approval
    approve(pg_world, proposed.intent_id)
    assert pg_world.spent() == 0
    start(pg_world, proposed.intent_id)
    assert pg_world.spent() == 1
    assert pg_world.started_events() == 1
    assert outcome(pg_world, proposed.intent_id, "succeeded", {"sha": "c" * 40}).state == "succeeded"
    ((state, receipt),) = pg_world.sql("SELECT state, receipt FROM skm_policy.tool_intents")
    assert state == "succeeded"
    assert receipt == {"sha": "c" * 40}


@pytest.mark.parametrize("racers", [2, 6])
def test_concurrent_starts_use_the_approval_once(pg_world: PgWorld, racers: int) -> None:
    proposed = propose(pg_world)
    approve(pg_world, proposed.intent_id)
    digest = view(pg_world, proposed.intent_id).args_digest
    results = race(
        racers,
        lambda index: pg_world.run(
            StartIntentExecution(intent_id=proposed.intent_id, args_digest=digest), key=f"start-{index}"
        ),
    )
    admitted = [item for item in results if not isinstance(item, SkmError)]
    refused = [item for item in results if isinstance(item, SkmError)]
    assert len(admitted) == 1
    assert len(refused) == racers - 1
    assert {item.code for item in refused if isinstance(item, SkmError)} == {ErrorCode.APPROVAL_MISMATCH}
    assert pg_world.spent() == 1
    assert pg_world.started_events() == 1
    assert set(pg_world.states().values()) == {"executing"}


def test_concurrent_identical_proposals_are_one_intent(pg_world: PgWorld) -> None:
    results = race(4, lambda index: propose(pg_world))
    assert all(not isinstance(item, SkmError) for item in results)
    assert len({item.intent_id for item in results}) == 1  # type: ignore[union-attr]
    assert len(pg_world.states()) == 1


def test_a_revoked_kind_blocks_the_start_and_spends_nothing(pg_world: PgWorld) -> None:
    proposed = propose(pg_world)
    approve(pg_world, proposed.intent_id)
    pg_world.allow_effects("git_commit")
    with pytest.raises(SkmError) as caught:
        start(pg_world, proposed.intent_id)
    assert caught.value.details["reason"] == "revoked"
    assert pg_world.spent() == 0
    assert set(pg_world.states().values()) == {"approved"}
    pg_world.allow_effects("git_commit", "git_push")
    assert start(pg_world, proposed.intent_id).state == "executing"


def test_a_lost_membership_blocks_the_start(pg_world: PgWorld) -> None:
    mine = pg_world.person("maintainer", {pg_world.workspace_id: Role.MAINTAINER})
    proposed = propose(pg_world)
    approve(pg_world, proposed.intent_id, "maintainer")
    pg_world.run(RevokeMembership(scope_id=pg_world.workspace_id, principal_id=mine.principal_id))
    with pytest.raises(SkmError) as caught:
        start(pg_world, proposed.intent_id)
    assert caught.value.details["reason"] == "approval_authority_revoked"
    assert pg_world.spent() == 0


def test_a_system_approved_commit_starts_without_a_human(pg_world: PgWorld) -> None:
    proposed = propose(pg_world, "git_commit")
    assert proposed.state == "approved"
    assert start(pg_world, proposed.intent_id).state == "executing"
    ((approver, single_use, used),) = pg_world.sql(
        "SELECT approver_id::text, single_use, used_at IS NOT NULL FROM skm_policy.approvals"
    )
    assert (approver, single_use, used) == ("00000000-0000-7000-8000-000000000001", True, True)


def test_the_unique_open_slot_is_free_again_after_the_outcome(pg_world: PgWorld) -> None:
    first = propose(pg_world)
    approve(pg_world, first.intent_id)
    start(pg_world, first.intent_id)
    outcome(pg_world, first.intent_id, "failed")
    again = propose(pg_world)
    assert again.intent_id != first.intent_id
    assert again.state == "proposed"
