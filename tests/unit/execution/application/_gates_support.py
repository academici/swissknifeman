"""Product gate decisions, persisted coverage and immutable re-review rounds in real UoWs."""

from dataclasses import replace
from typing import Any

from contracts.execution.seed_helpers import seed_attempt
from skm.modules.execution.application._events import cause
from skm.modules.execution.application._primitives import save_attempt
from skm.modules.execution.domain.attempt import AttemptEndReason, AttemptState
from skm.modules.execution.domain.check_execution import CheckExecution, CheckKind, CheckState
from skm.modules.execution.domain.task import ReviewMode, TaskKind, TaskStatus
from skm.modules.execution.domain.task_graph import EdgeKind, TaskEdge
from skm.modules.execution.ports import (
    CheckRepository,
    EffectRepository,
    TaskRepository,
)
from skm.modules.planning import public as planning
from unit.execution.domain.test_gates import integration_effect

from ._support import context, seed_output, seeded


def gate_case(
    side: Any,
    *,
    kind: TaskKind = TaskKind.PHASE_GATE,
    receipt: bool = True,
    review_mode: ReviewMode = ReviewMode.WAIVED,
) -> tuple[Any, ...]:
    run, member, ma = seeded(side, task_status=TaskStatus.CHECKING)
    with side.uow() as uow:
        spec = planning.get_revision_specification(uow, run.revision_id)
        mo = seed_output(side, uow, ma)
        member = replace(
            member,
            status=TaskStatus.ACCEPTED,
            accepted_attempt_id=ma.id,
            accepted_output_id=mo.id,
            row_version=member.row_version + 1,
        )
        uow.repo(TaskRepository).save(member, expected_version=member.row_version - 1)
        save_attempt(
            uow,
            replace(
                ma,
                state=AttemptState.COMPLETED,
                current_output_id=mo.id,
                finished_at=side.clock.now(),
                end_reason=AttemptEndReason.ACCEPTED,
            ),
        )
        task = replace(
            member,
            id=side.new_id(),
            kind=kind,
            display_key="PLAN#accept" if kind is TaskKind.PLAN_ACCEPTANCE else "P1#gate",
            spec_entity_id=None if kind is TaskKind.PLAN_ACCEPTANCE else spec.phases[0].id,
            declared_write_scope=(),
            review_mode=review_mode,
            status=TaskStatus.CHECKING,
            current_attempt_id=None,
            accepted_attempt_id=None,
            accepted_output_id=None,
            row_version=1,
        )
        uow.repo(TaskRepository).add_many((task,), ())
        attempt = seed_attempt(side, uow, run.id, task.id)
        task = replace(task, current_attempt_id=attempt.id, row_version=2)
        uow.repo(TaskRepository).save(task, expected_version=1)
        effect = integration_effect(
            member, mo, before=mo.manifest.mounts[0].base_commit, after=mo.manifest.mounts[0].head_commit
        )
        assert effect.receipt is not None
        receipt_fields = {**effect.receipt, "tree_sha": mo.manifest.mounts[0].tree_sha}
        effect = replace(
            effect,
            request={**effect.request, "tree_sha": mo.manifest.mounts[0].tree_sha},
            receipt=receipt_fields,
        )
        from skm.modules.execution.domain.readiness import canonical_digest

        digest = canonical_digest(
            {"effect_id": str(effect.id), "kind": effect.kind.value, "request": effect.request}
        )
        effect = replace(effect, request_digest=digest, receipt={**receipt_fields, "request_digest": digest})
        if receipt:
            uow.repo(EffectRepository).add(effect)
        uow.repo(TaskRepository).add_many(
            (), (TaskEdge(run.id, task.id, member.id, EdgeKind.GATE_MEMBER, frozenset()),)
        )
        output = seed_output(side, uow, attempt)
        save_attempt(uow, replace(attempt, current_output_id=output.id))
        uow.commit()
    return run, task, attempt, member, output, effect


def check(
    side: Any,
    uow: Any,
    state: Any,
    *,
    passed: bool = True,
    kind: CheckKind = CheckKind.COMMAND,
    check_state: CheckState | None = None,
) -> Any:
    spec = planning.get_revision_specification(uow, state.run.revision_id)
    cid = side.new_id()
    record = CheckExecution(
        cid,
        side.ws,
        state.run.id,
        state.task.id,
        state.attempt.id,
        state.output.id,
        spec.checks[0].id,
        "P1.1:V1",
        kind,
        True,
        check_state or (CheckState.PASSED if passed else CheckState.FAILED),
        None if kind is CheckKind.MANUAL else 0 if passed else 1,
        "observed check",
        None,
        None,
        "sha256:" + "1" * 64,
        side.clock.now(),
        side.clock.now(),
        1,
    )
    uow.repo(CheckRepository).add_many((record,))
    return record


def followup_case(side: Any, uow: Any, run: Any, gate: Any) -> tuple[Any, ...]:
    from skm.modules.execution.application._state import load_state
    from skm.modules.execution.application.stages.gate_lifecycle import followups
    from skm.modules.execution.domain.workflow.actions import CreateFollowups

    state, _ = load_state(uow, gate.id)
    followups(
        uow, context(side, uow, run), state, CreateFollowups("checks_failed", (), ()), cause("check_failed")
    )
    task = next(t for t in uow.repo(TaskRepository).list_for_run(run.id) if t.kind is TaskKind.FOLLOWUP)
    attempt = seed_attempt(side, uow, run.id, task.id)
    output = seed_output(side, uow, attempt)
    save_attempt(uow, replace(attempt, current_output_id=output.id))
    changed = replace(task, current_attempt_id=attempt.id, row_version=task.row_version + 1)
    uow.repo(TaskRepository).save(changed, expected_version=task.row_version)
    return changed, attempt, output


def ready_gate(side: Any, uow: Any, run: Any, gate: Any, member: Any) -> Any:
    task = replace(
        gate,
        id=side.new_id(),
        display_key="P1.2#gate",
        status=TaskStatus.READY,
        current_attempt_id=None,
        attempt_count=0,
        row_version=1,
    )
    uow.repo(TaskRepository).add_many(
        (task,), (TaskEdge(run.id, task.id, member.id, EdgeKind.GATE_MEMBER, frozenset()),)
    )
    return task


def manual_gate_case(side: Any) -> tuple[Any, ...]:
    from skm.modules.execution.application._primitives import move
    from skm.modules.execution.application._state import load_state
    from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
    from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageState

    from ._support import seed_stage

    run, task, attempt, member, output, _ = gate_case(side)
    with side.uow() as uow:
        state, _ = load_state(uow, task.id)
        manual = check(side, uow, state, kind=CheckKind.MANUAL, check_state=CheckState.MANUAL_PENDING)
        wait = blocking_reason(
            BlockingCode.WAITING_MANUAL_CHECK,
            task_id=task.id,
            refs={"check_execution_id": str(manual.id), "check_key": manual.check_key},
            now=side.clock.now(),
            message="manual verdict pending",
        )
        task = move(
            uow,
            context(side, uow, run),
            run,
            task,
            TaskStatus.MANUAL_PENDING,
            cause("wait_changed"),
            blocking=wait,
        )
        seed_stage(
            side,
            uow,
            attempt,
            stage_id="gate_checks",
            stage_type="run_checks",
            state=StageState.COMPLETED,
            outcome_kind=StageOutcomeKind.MANUAL_PENDING,
        )
        uow.commit()
    return run, task, member, output, manual
