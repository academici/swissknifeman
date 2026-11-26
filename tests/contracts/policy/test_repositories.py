"""Intent, approval and decision-audit repositories: one contract over memory ∥ PostgreSQL (§6, §11).

memory ∥ pg: intents round trip with their arguments and receipt; compare-and-set ``save`` that never rewrites
identity or arguments; one open intent per ``(scope, kind, digest)`` (``proposed|approved|executing``), freed
by every other state; keyset pages by ``(created_at, id)`` per workspace, scope and state; ``expired`` finds
undecided proposals and approved intents without a usable approval; approvals ordered by creation, spent once
(``mark_used`` twice is ``APPROVAL_MISMATCH``, also from two threads); the decision audit appends and reads
back by scope and operation. PostgreSQL only: the triggers and constraints of ``0012`` -- approvals are
append-only apart from one ``used_at``, the vocabulary checks, the receipt size, row locks that
``get_for_update`` takes and ``expired`` skips.
"""

import threading
from dataclasses import replace
from datetime import timedelta
from typing import Any
from uuid import UUID

import psycopg
import pytest

from contracts.policy.harness import ACTORS, APPROVER, OTHER_WORKSPACE, WORKSPACE, Side
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, NotFound, SkmError, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId, ToolIntentId
from skm.modules.policy.domain.approval import ApprovalDecision, ApprovalId
from skm.modules.policy.domain.tool_intent import (
    DecisionSource,
    EffectKind,
    IntentState,
    ToolDecisionRecord,
    transition_intent,
)
from skm.modules.policy.ports import ApprovalRepository, DecisionAuditRepository, ToolIntentRepository


def intents(uow: Any) -> ToolIntentRepository:
    return uow.repo(ToolIntentRepository)


# ------------------------------------------------------------------------------------------ intents
def test_intents_round_trip_with_arguments_and_receipt(side: Side) -> None:
    made = side.intent(normalized_args={"nested": {"a": [1, "é", True, None]}, "z": 1}, receipt=None)
    side.store(made)
    with side.uow() as uow:
        stored = intents(uow).get(made.id)
        assert stored == made
        assert intents(uow).get_for_update(made.id) == made
        with pytest.raises(NotFound) as missing:
            intents(uow).get(ToolIntentId(side.ids.new_id()))
        assert missing.value.details["kind"] == "tool_intent"
    executing = replace(made, state=IntentState.EXECUTING, row_version=2)
    with side.uow() as uow:
        intents(uow).save(executing, expected_version=1)
        uow.commit()
    done = replace(
        executing, state=IntentState.SUCCEEDED, row_version=3, receipt={"sha": "c" * 40, "n": [1, 2]}
    )
    with side.uow() as uow:
        intents(uow).save(done, expected_version=2)
        uow.commit()
    with side.uow(readonly=True) as uow:
        assert intents(uow).get(made.id) == done


def test_save_is_compare_and_set_and_keeps_identity_and_arguments(side: Side) -> None:
    made = side.intent()
    side.store(made)
    approved = transition_intent(made, IntentState.APPROVED)
    with side.uow() as uow:
        intents(uow).save(approved, expected_version=1)
        uow.commit()
    with side.uow() as uow:
        with pytest.raises(Conflict) as stale:
            intents(uow).save(replace(approved, row_version=3), expected_version=1)
        assert stale.value.code is ErrorCode.VERSION_CONFLICT
        assert stale.value.details == {"kind": "tool_intent", "expected": 1, "actual": 2}
        for field_name, value in (
            ("normalized_args", {"x": 1}),
            ("args_digest", "sha256:" + "9" * 64),
            ("scope_id", ScopeId(OTHER_WORKSPACE)),
            ("actor_id", ACTORS[2]),
            ("kind", EffectKind.PUBLISH),
            ("expires_at", approved.expires_at + timedelta(days=1)),
        ):
            with pytest.raises(ValueError, match="keeps its"):
                intents(uow).save(replace(approved, row_version=3, **{field_name: value}), expected_version=2)
        with pytest.raises(NotFound):
            intents(uow).save(replace(approved, id=ToolIntentId(side.ids.new_id())), expected_version=1)


def test_one_open_intent_per_scope_kind_and_digest(side: Side) -> None:
    first = side.intent()
    side.store(first)
    twin = side.intent(args_digest=first.args_digest, normalized_args=first.normalized_args)
    with side.uow() as uow:
        with pytest.raises(Conflict) as taken:
            intents(uow).add(twin)
        assert taken.value.code is ErrorCode.ALREADY_EXISTS
        assert taken.value.details == {"kind": "tool_intent"}
        with pytest.raises(Conflict):
            intents(uow).add(first)  # a taken id
        assert intents(uow).find_active(first.scope_id, first.kind, first.args_digest) == first
    other_scope = replace(
        twin,
        id=ToolIntentId(side.ids.new_id()),
        scope_id=ScopeId(OTHER_WORKSPACE),
        workspace_id=OTHER_WORKSPACE,
    )
    other_kind = replace(twin, id=ToolIntentId(side.ids.new_id()), kind=EffectKind.PUBLISH)
    side.store(other_scope, other_kind)  # another scope or another kind is another effect


@pytest.mark.parametrize("state", [IntentState.APPROVED, IntentState.EXECUTING])
def test_every_open_state_holds_the_slot_and_every_other_state_frees_it(
    side: Side, state: IntentState
) -> None:
    first = side.intent(state=state)
    side.store(first)
    twin = side.intent(args_digest=first.args_digest, normalized_args=first.normalized_args)
    with side.uow() as uow, pytest.raises(Conflict):
        intents(uow).add(twin)


@pytest.mark.parametrize(
    "state",
    [
        IntentState.DENIED,
        IntentState.EXPIRED,
        IntentState.SUCCEEDED,
        IntentState.FAILED,
        IntentState.OUTCOME_UNKNOWN,
    ],
)
def test_a_closed_intent_does_not_hold_the_slot(side: Side, state: IntentState) -> None:
    reason = "not_permitted" if state is IntentState.DENIED else None
    closed = side.intent(state=state, denied_reason=reason)
    side.store(closed)
    with side.uow(readonly=True) as uow:
        assert intents(uow).find_active(closed.scope_id, closed.kind, closed.args_digest) is None
    again = side.intent(args_digest=closed.args_digest, normalized_args=closed.normalized_args)
    side.store(again)  # the same effect may be proposed again


def test_a_closing_save_frees_the_slot_for_the_same_effect(side: Side) -> None:
    first = side.intent()
    side.store(first)
    denied = transition_intent(first, IntentState.DENIED, denied_reason="by_approver")  # type: ignore[arg-type]
    with side.uow() as uow:
        intents(uow).save(denied, expected_version=1)
        uow.commit()
    side.store(side.intent(args_digest=first.args_digest, normalized_args=first.normalized_args))


def test_pages_ascend_by_creation_and_filter_by_workspace_scope_and_state(side: Side) -> None:
    made = []
    for _ in range(5):
        side.tick()
        made.append(side.intent(scope_id=ScopeId(WORKSPACE)))
    other = side.intent(scope_id=ScopeId(OTHER_WORKSPACE), workspace_id=OTHER_WORKSPACE)
    approved = replace(side.intent(), state=IntentState.APPROVED)
    side.store(*made, other, approved)
    ordered = [*made, approved]
    with side.uow(readonly=True) as uow:
        repo = intents(uow)
        first = repo.list(workspace_id=WORKSPACE, scope_id=None, state=None, after=None, limit=4)
        assert [item.id for item in first.items] == [item.id for item in ordered[:4]]
        assert first.next is not None
        rest = repo.list(workspace_id=WORKSPACE, scope_id=None, state=None, after=first.next, limit=4)
        assert [item.id for item in rest.items] == [item.id for item in ordered[4:]]
        assert rest.next is None
        only = repo.list(
            workspace_id=WORKSPACE, scope_id=None, state=IntentState.APPROVED, after=None, limit=10
        )
        assert [item.id for item in only.items] == [approved.id]
        scoped = repo.list(
            workspace_id=OTHER_WORKSPACE, scope_id=ScopeId(OTHER_WORKSPACE), state=None, after=None, limit=10
        )
        assert [item.id for item in scoped.items] == [other.id]
        assert (
            repo.list(
                workspace_id=OTHER_WORKSPACE, scope_id=ScopeId(WORKSPACE), state=None, after=None, limit=10
            ).items
            == ()
        )
        with pytest.raises(ValidationFailed) as bad:
            repo.list(workspace_id=WORKSPACE, scope_id=None, state=None, after="not-a-cursor", limit=4)
        assert bad.value.details["field"] == "after"
        with pytest.raises(ValueError, match="page limit"):
            repo.list(workspace_id=WORKSPACE, scope_id=None, state=None, after=None, limit=0)


def test_pages_with_equal_times_keep_a_total_order(side: Side) -> None:
    same = [side.intent() for _ in range(5)]
    side.store(*same)
    seen: list[ToolIntentId] = []
    cursor = None
    with side.uow(readonly=True) as uow:
        while True:
            page = intents(uow).list(workspace_id=WORKSPACE, scope_id=None, state=None, after=cursor, limit=2)
            seen.extend(item.id for item in page.items)
            cursor = page.next
            if cursor is None:
                break
    assert len(seen) == 5
    assert set(seen) == {item.id for item in same}


def test_expired_finds_undecided_proposals_and_approved_intents_without_a_usable_approval(side: Side) -> None:
    stale = side.intent(expires_at=side.clock.now() + timedelta(minutes=1))
    young = side.intent()
    unused = replace(side.intent(), state=IntentState.APPROVED)
    kept = replace(side.intent(), state=IntentState.APPROVED)
    running = replace(side.intent(), state=IntentState.EXECUTING)
    side.store(stale, young, unused, kept, running)
    with side.uow() as uow:
        approvals = uow.repo(ApprovalRepository)
        approvals.add(side.approval(unused, expires_at=side.clock.now() + timedelta(seconds=30)))
        approvals.add(side.approval(kept, expires_at=side.clock.now() + timedelta(hours=2)))
        approvals.add(side.approval(running, expires_at=side.clock.now() + timedelta(seconds=30)))
        uow.commit()
    with side.uow() as uow:  # the sweep locks what it returns: a writable unit of work
        assert intents(uow).expired(side.clock.now(), limit=10) == ()
    side.tick(120)
    with side.uow() as uow:
        found = intents(uow).expired(side.clock.now(), limit=10)
        assert [item.id for item in found] == [
            item.id for item in sorted((stale, unused), key=lambda item: (item.expires_at, str(item.id)))
        ] or {item.id for item in found} == {stale.id, unused.id}
        assert intents(uow).expired(side.clock.now(), limit=1)[0].id in {stale.id, unused.id}
    side.tick(3 * 86400)
    with side.uow() as uow:
        assert {item.id for item in intents(uow).expired(side.clock.now(), limit=10)} == {
            stale.id,
            young.id,
            unused.id,
            kept.id,
        }  # an executing intent is never swept


def test_a_denial_record_does_not_keep_an_approved_intent_alive(side: Side) -> None:
    approved = replace(side.intent(), state=IntentState.APPROVED)
    side.store(approved)
    with side.uow() as uow:
        uow.repo(ApprovalRepository).add(
            side.approval(
                approved, decision=ApprovalDecision.DENY, expires_at=side.clock.now() + timedelta(days=1)
            )
        )
        uow.commit()
    side.tick(1)
    with side.uow() as uow:
        assert [item.id for item in intents(uow).expired(side.clock.now(), limit=5)] == [approved.id]


# ------------------------------------------------------------------------------------------ approvals
def test_approvals_come_back_in_creation_order_and_round_trip(side: Side) -> None:
    made = replace(side.intent(), state=IntentState.APPROVED)
    side.store(made)
    first = side.approval(made, reason="é")
    side.tick(1)
    second = side.approval(made, single_use=False, approver_id=ACTORS[2])
    side.tick(1)
    third = side.approval(made, decision=ApprovalDecision.DENY, reason="")
    with side.uow() as uow:
        repo = uow.repo(ApprovalRepository)
        for item in (third, first, second):
            repo.add(item)
        uow.commit()
    with side.uow(readonly=True) as uow:
        assert uow.repo(ApprovalRepository).for_intent(made.id) == (first, second, third)
        assert uow.repo(ApprovalRepository).for_intent(ToolIntentId(side.ids.new_id())) == ()


def test_adding_an_approval_twice_is_already_exists(side: Side) -> None:
    made = side.intent()
    side.store(made)
    item = side.approval(made)
    with side.uow() as uow:
        uow.repo(ApprovalRepository).add(item)
        uow.commit()
    with side.uow() as uow, pytest.raises(Conflict) as taken:
        uow.repo(ApprovalRepository).add(item)
    assert taken.value.code is ErrorCode.ALREADY_EXISTS


def test_an_approval_is_spent_once(side: Side) -> None:
    made = replace(side.intent(), state=IntentState.APPROVED)
    side.store(made)
    item = side.approval(made)
    with side.uow() as uow:
        uow.repo(ApprovalRepository).add(item)
        uow.commit()
    with side.uow() as uow:
        uow.repo(ApprovalRepository).mark_used(item.id, side.clock.now())
        uow.commit()
    with side.uow() as uow:
        with pytest.raises(Forbidden) as again:
            uow.repo(ApprovalRepository).mark_used(item.id, side.clock.now())
        assert again.value.code is ErrorCode.APPROVAL_MISMATCH
        assert again.value.details["reason"] == "already_used"
        (stored,) = uow.repo(ApprovalRepository).for_intent(made.id)
        assert stored.used_at == side.clock.now()
        assert stored == replace(item, used_at=side.clock.now())
        with pytest.raises(Forbidden):
            uow.repo(ApprovalRepository).mark_used(ApprovalId(side.ids.new_id()), side.clock.now())  # unknown


def test_a_refusal_row_is_never_spendable(side: Side) -> None:
    made = side.intent()
    side.store(made)
    refusal = side.approval(made, decision=ApprovalDecision.DENY)
    with side.uow() as uow:
        uow.repo(ApprovalRepository).add(refusal)
        uow.commit()
    with side.uow() as uow, pytest.raises(Forbidden):
        uow.repo(ApprovalRepository).mark_used(refusal.id, side.clock.now())


def test_two_threads_spend_an_approval_exactly_once(side: Side) -> None:
    made = replace(side.intent(), state=IntentState.APPROVED)
    side.store(made)
    item = side.approval(made)
    with side.uow() as uow:
        uow.repo(ApprovalRepository).add(item)
        uow.commit()
    gate = threading.Barrier(2)
    outcomes: list[object] = []

    def spend() -> None:
        gate.wait()
        try:
            with side.uow() as uow:
                uow.repo(ApprovalRepository).mark_used(item.id, side.clock.now())
                uow.commit()
            outcomes.append("spent")
        except SkmError as error:
            outcomes.append(error.code)

    threads = [threading.Thread(target=spend) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(map(str, outcomes)) == sorted(["spent", str(ErrorCode.APPROVAL_MISMATCH)])


def test_two_threads_start_one_intent_and_only_one_gets_the_lock_first(side: Side) -> None:
    """The shape of ``start_intent_execution``: lock, check ``approved``, spend, ``executing``, commit."""
    made = replace(side.intent(), state=IntentState.APPROVED)
    side.store(made)
    item = side.approval(made)
    with side.uow() as uow:
        uow.repo(ApprovalRepository).add(item)
        uow.commit()
    gate = threading.Barrier(2)
    admitted: list[bool] = []

    def start() -> None:
        gate.wait()
        with side.uow() as uow:
            locked = intents(uow).get_for_update(made.id)
            if locked.state is not IntentState.APPROVED:
                admitted.append(False)
                return
            uow.repo(ApprovalRepository).mark_used(item.id, side.clock.now())
            intents(uow).save(
                transition_intent(locked, IntentState.EXECUTING), expected_version=locked.row_version
            )
            uow.commit()
            admitted.append(True)

    threads = [threading.Thread(target=start) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(admitted) == [False, True]
    with side.uow(readonly=True) as uow:
        assert intents(uow).get(made.id).state is IntentState.EXECUTING


# ------------------------------------------------------------------------------------------ decision audit
def record(side: Side, scope: ScopeId, at_offset: int, **changes: Any) -> ToolDecisionRecord:
    values: dict[str, Any] = {
        "id": side.ids.new_id(),
        "workspace_id": WORKSPACE,
        "scope_id": scope,
        "principal_id": ACTORS[0],
        "source": DecisionSource.HOOK,
        "at": side.clock.now() + timedelta(seconds=at_offset),
        "tool": "fs.write",
        "call_summary": "write a.py",
        "outcome": "allow",
        "code": None,
        "rule": None,
        "operation": "modify_write_set",
        "recorded_at": side.clock.now(),
    }
    values.update(changes)
    return ToolDecisionRecord(**values)


def test_the_audit_appends_and_reads_back_by_scope_and_operation(side: Side) -> None:
    scope = ScopeId(WORKSPACE)
    rows = [
        record(side, scope, 3),
        record(side, scope, 1, outcome="warn", operation="modify_outside_write_set", rule="outside"),
        record(
            side, scope, 2, outcome="deny", code="path_denied", operation=None, source=DecisionSource.WORKER
        ),
        record(side, ScopeId(OTHER_WORKSPACE), 0, workspace_id=OTHER_WORKSPACE),
        record(side, scope, 4, workspace_id=None),
    ]
    with side.uow() as uow:
        uow.repo(DecisionAuditRepository).add_many(rows[:3])
        uow.repo(DecisionAuditRepository).add_many([])
        uow.repo(DecisionAuditRepository).add_many(rows[3:])
        uow.commit()
    with side.uow(readonly=True) as uow:
        repo = uow.repo(DecisionAuditRepository)
        assert repo.for_scope(scope) == (rows[1], rows[2], rows[0], rows[4])
        assert repo.for_scope(scope, operation="modify_outside_write_set") == (rows[1],)
        assert repo.for_scope(scope, limit=2) == (rows[1], rows[2])
        assert repo.for_scope(ScopeId(OTHER_WORKSPACE)) == (rows[3],)
        assert repo.for_scope(ScopeId(UUID(int=77))) == ()


# ------------------------------------------------------------------------------------------ PostgreSQL only
pg = pytest.mark.pg


@pg
def test_an_approval_row_for_an_unknown_intent_is_not_found(pg_side: Side) -> None:
    ghost = replace(pg_side.intent(), id=ToolIntentId(pg_side.ids.new_id()))
    with pg_side.uow() as uow, pytest.raises(NotFound) as missing:
        uow.repo(ApprovalRepository).add(pg_side.approval(ghost))
    assert missing.value.details["kind"] == "tool_intent"


@pg
def test_the_approvals_table_is_append_only_apart_from_one_used_at(pg_side: Side) -> None:
    made = replace(pg_side.intent(), state=IntentState.APPROVED)
    pg_side.store(made)
    item = pg_side.approval(made)
    with pg_side.uow() as uow:
        uow.repo(ApprovalRepository).add(item)
        uow.commit()
    for statement in (
        "UPDATE skm_policy.approvals SET reason = 'changed' WHERE id = %s",
        "UPDATE skm_policy.approvals SET args_digest = 'sha256:' || repeat('1', 64) WHERE id = %s",
        "UPDATE skm_policy.approvals SET expires_at = expires_at + interval '1 day' WHERE id = %s",
        "UPDATE skm_policy.approvals SET used_at = NULL WHERE id = %s",
        "DELETE FROM skm_policy.approvals WHERE id = %s",
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            pg_side.sql(statement, (item.id,))
    pg_side.sql("UPDATE skm_policy.approvals SET used_at = %s WHERE id = %s", (pg_side.clock.now(), item.id))
    with pytest.raises(psycopg.errors.CheckViolation):  # once
        pg_side.sql(
            "UPDATE skm_policy.approvals SET used_at = %s WHERE id = %s", (pg_side.clock.now(), item.id)
        )


@pg
@pytest.mark.parametrize(
    "assignment",
    [
        "state = 'denied'",  # a denial needs its reason
        "denied_reason = 'revoked'",  # and only a denial has one
        "state = 'nonsense'",
        "risk = 'severe'",
        "kind = 'rm_rf'",
        "args_digest = 'sha256:abc'",
        "receipt = '[]'::jsonb",
        "receipt = jsonb_build_object('x', repeat('x', 17000))",
        "expires_at = created_at",
        "row_version = 0",
    ],
)
def test_the_intent_table_refuses_what_the_domain_never_writes(pg_side: Side, assignment: str) -> None:
    made = pg_side.intent()
    pg_side.store(made)
    with pytest.raises(psycopg.errors.CheckViolation):
        pg_side.sql(f"UPDATE skm_policy.tool_intents SET {assignment} WHERE id = %s", (made.id,))  # noqa: S608


@pg
@pytest.mark.parametrize(
    "bad",
    [
        {"outcome": "deny", "code": None},
        {"outcome": "allow", "code": "path_denied"},
        {"outcome": "deny", "code": "made_up"},
        {"operation": "format_disk"},
        {"call_summary": "x" * 501},
    ],
)
def test_the_audit_table_enforces_the_vocabulary(pg_side: Side, bad: dict[str, Any]) -> None:
    with pg_side.uow() as uow, pytest.raises(SkmError):
        uow.repo(DecisionAuditRepository).add_many([record(pg_side, ScopeId(WORKSPACE), 0, **bad)])
    assert pg_side.sql("SELECT count(*) FROM skm_policy.decision_audit")[0][0] == 0


@pg
def test_get_for_update_holds_the_row_and_expired_skips_it(pg_side: Side) -> None:
    held = replace(pg_side.intent(expires_at=pg_side.clock.now() + timedelta(minutes=1)))
    free = replace(pg_side.intent(expires_at=pg_side.clock.now() + timedelta(minutes=1)))
    pg_side.store(held, free)
    pg_side.tick(120)
    with pg_side.uow() as locking:
        intents(locking).get_for_update(held.id)
        with pg_side.uow() as sweeper:
            assert [item.id for item in intents(sweeper).expired(pg_side.clock.now(), limit=10)] == [free.id]
        locking.rollback()


@pg
def test_a_second_writer_waits_for_the_lock_and_then_sees_the_new_state(pg_side: Side) -> None:
    made = pg_side.intent()
    pg_side.store(made)
    entered = threading.Event()
    release = threading.Event()
    seen: list[IntentState] = []

    def holder() -> None:
        with pg_side.uow() as uow:
            locked = intents(uow).get_for_update(made.id)
            entered.set()
            release.wait(5)
            intents(uow).save(transition_intent(locked, IntentState.APPROVED), expected_version=1)
            uow.commit()

    def waiter() -> None:
        entered.wait(5)
        with pg_side.uow() as uow:
            seen.append(intents(uow).get_for_update(made.id).state)  # blocks until the holder commits

    first, second = threading.Thread(target=holder), threading.Thread(target=waiter)
    first.start()
    second.start()
    entered.wait(5)
    release.set()
    first.join()
    second.join()
    assert seen == [IntentState.APPROVED]


@pg
def test_the_rows_are_in_the_policy_schema_with_the_workspace_of_the_intent(pg_side: Side) -> None:
    made = replace(pg_side.intent(), state=IntentState.APPROVED)
    pg_side.store(made)
    item = pg_side.approval(made)
    with pg_side.uow() as uow:
        uow.repo(ApprovalRepository).add(item)
        uow.commit()
    ((workspace,),) = pg_side.sql("SELECT workspace_id FROM skm_policy.approvals WHERE id = %s", (item.id,))
    assert workspace == made.workspace_id
    assert PrincipalId(APPROVER) == item.approver_id
