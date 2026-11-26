"""AcceptanceDecided precedes integration; only terminal Done opens dependents."""

from dataclasses import replace
from typing import Any

from fixtures.execution.acceptance import seed_accept_ready
from skm.modules.execution.application._primitives import save_attempt
from skm.modules.execution.application.apply_action import apply_action
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.review import ReviewClearance
from skm.modules.execution.domain.task import TaskKind, TaskStatus
from skm.modules.execution.domain.task_graph import EdgeKind, TaskEdge
from skm.modules.execution.domain.workflow.actions import Accept, ActionDecision, Done
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AttemptRepository,
    TaskRepository,
)
from skm.modules.planning import public as planning

from ._support import _shared_side as _shared_side
from ._support import context, seed_task, seeded
from ._support import side as side


def test_acceptance_records_decision_then_done_unblocks_after_integration(side: Any) -> None:
    run, task, attempt = seeded(side, task_status=TaskStatus.CHECKING)
    manifest = side.make_final_manifest()
    with side.uow() as uow:
        output = seed_accept_ready(side, uow, run, task, attempt, manifest)
        spec = planning.get_revision_specification(uow, run.revision_id)
        dependent_id = side.new_id()
        reason = blocking_reason(
            BlockingCode.BLOCKED_BY_DEPENDENCY,
            task_id=dependent_id,
            refs={"prerequisite_task_ids": [str(task.id)]},
            now=side.clock.now(),
            message="dependency",
        )
        dependent = seed_task(
            side,
            uow,
            run.id,
            task_id=dependent_id,
            kind=TaskKind.ITEM,
            spec_entity_id=spec.items[0].id,
            display_key="P1.1",
            status=TaskStatus.BLOCKED,
            blocking_reason=reason,
        )
        uow.repo(TaskRepository).add_many(
            (), (TaskEdge(run.id, dependent.id, task.id, EdgeKind.BLOCKS, frozenset({"test"})),)
        )
        why = {"trigger_kind": "stage_outcome", "advance_rule": "K3", "reason_codes": [], "refs": []}
        kind = apply_action(
            ActionDecision(Accept(output.id, ReviewClearance.SELF), why),
            context(side, uow, run),
            uow,
            task_id=task.id,
        )
        assert kind == "run_stage", uow.repo(AcceptanceRepository).decisions_for_task(task.id)[-1].basis
        assert len(uow.repo(AcceptanceRepository).decisions_for_task(task.id)) == 1
        assert uow.repo(TaskRepository).get(task.id).status is TaskStatus.INTEGRATING
        assert uow.repo(TaskRepository).get(dependent.id).status is TaskStatus.BLOCKED
        # A trusted integration completion consumes the selected template before Done.
        current = uow.repo(AttemptRepository).get(attempt.id)
        save_attempt(uow, replace(current, continuation=None))
        apply_action(ActionDecision(Done(), why), context(side, uow, run), uow, task_id=task.id)
        assert uow.repo(TaskRepository).get(task.id).status is TaskStatus.ACCEPTED
        assert uow.repo(TaskRepository).get(dependent.id).status is TaskStatus.READY
        uow.commit()


def test_synthetic_followup_is_created_with_identity_and_wait_event(side: Any) -> None:
    from skm.modules.execution.domain.workflow.actions import CreateFollowups
    from skm.modules.execution.ports import ExecutionQueries

    run, task, attempt = seeded(side, task_status=TaskStatus.CHECKING)
    why = {"trigger_kind": "followup", "advance_rule": "E4", "reason_codes": [], "refs": []}
    with side.uow() as uow:
        from skm.modules.execution.application._events import cause
        from skm.modules.execution.application.apply_action import prepare_trigger

        save_attempt(
            uow, prepare_trigger(uow, context(side, uow, run), attempt, side.new_id(), cause("check_failed"))
        )
        apply_action(
            ActionDecision(CreateFollowups("checks_failed", (), ()), why),
            context(side, uow, run),
            uow,
            task_id=task.id,
        )
        uow.commit()
    with side.uow(readonly=True) as uow:
        tasks = uow.repo(TaskRepository).list_for_run(run.id)
        child = next(t for t in tasks if t.kind is TaskKind.FOLLOWUP)
        assert child.origin.source_task_id == task.id
        assert uow.repo(TaskRepository).get(task.id).status is TaskStatus.BLOCKED
        query = uow.repo(ExecutionQueries)
        events = query.run_events(run.id, 0, query.head_run_seq(run.id), 100)
        assert any("task-created" in str(e.get("type", e.get("event_type"))) for e in events)

    from skm.modules.execution.generated.commands import PauseRun, ResumeRun

    side.client.dispatch(PauseRun(run.id, "pause after followups"))
    side.client.dispatch(ResumeRun(run.id))
    with side.uow(readonly=True) as uow:
        assert (
            len([t for t in uow.repo(TaskRepository).list_for_run(run.id) if t.kind is TaskKind.FOLLOWUP])
            == 1
        )
        assert uow.repo(AttemptRepository).get(attempt.id).continuation is None
