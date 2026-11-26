"""Product gate decisions, persisted coverage and immutable re-review rounds in real UoWs."""

from dataclasses import replace
from typing import Any

import pytest

from contracts.execution.seed_helpers import seed_attempt
from skm.kernel.errors import SkmError
from skm.modules.execution.application._events import cause
from skm.modules.execution.application._primitives import save_attempt
from skm.modules.execution.application._state import load_state
from skm.modules.execution.application.apply_action import apply_action, release_dependents
from skm.modules.execution.application.stages import phase_gate, plan_acceptance
from skm.modules.execution.domain.attempt import AttemptEndReason, AttemptState
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.budget import BudgetDimension
from skm.modules.execution.domain.check_execution import CheckState
from skm.modules.execution.domain.review import ReviewClearance
from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageState
from skm.modules.execution.domain.task import PathPattern, ReviewMode, TaskKind, TaskStatus
from skm.modules.execution.domain.task_graph import EdgeKind, TaskEdge
from skm.modules.execution.domain.workflow.actions import ActionDecision, CreateFollowups, RunStage
from skm.modules.execution.domain.workflow.definition import StageType
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AttemptRepository,
    BudgetRepository,
    CheckRepository,
    EffectRepository,
    EvidenceBindingRepository,
    ExecutionQueries,
    OutputRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)
from skm.modules.planning import public as planning
from unit.execution.domain.test_gates import integration_effect

from ._gates_support import check, gate_case, manual_gate_case, ready_gate
from ._support import _shared_side as _shared_side
from ._support import context, seed_output, seed_stage, seed_task
from ._support import side as side


def test_stages_are_control_plane_and_host_calls_are_refused() -> None:
    for stage in (phase_gate.PhaseGate(), plan_acceptance.PlanAcceptance()):
        assert stage.side == "control_plane"
        with pytest.raises(SkmError):
            stage.run(None, None)


def test_phase_gate_acceptance_is_durable_and_releases_next_phase(side: Any) -> None:
    run, task, attempt, member, output, _ = gate_case(side)
    with side.uow() as uow:
        dependent_id = side.new_id()
        blocking = blocking_reason(
            BlockingCode.BLOCKED_BY_DEPENDENCY,
            task_id=dependent_id,
            refs={"prerequisite_task_ids": [str(task.id)]},
            now=side.clock.now(),
            message="phase gate",
        )
        dependent = seed_task(
            side,
            uow,
            run.id,
            task_id=dependent_id,
            display_key="P2.1/U1",
            status=TaskStatus.BLOCKED,
            blocking_reason=blocking,
        )
        uow.repo(TaskRepository).add_many(
            (), (TaskEdge(run.id, dependent.id, task.id, EdgeKind.BLOCKS, frozenset()),)
        )
        result = apply_action(
            ActionDecision(
                RunStage("phase_gate", StageType.PHASE_GATE, StageMode.NORMAL, 1, {}),
                cause("stage_outcome", rule="F1"),
            ),
            context(side, uow, run),
            uow,
            task_id=task.id,
        )
        assert result == "done"
        assert uow.repo(TaskRepository).get(task.id).accepted_output_id == output.id
        assert uow.repo(TaskRepository).get(dependent.id).status is TaskStatus.READY
        decisions = uow.repo(AcceptanceRepository).decisions_for_task(task.id)
        assert decisions[-1].decision == "accepted"
        history = uow.repo(StageRepository).history(attempt.id)
        assert history.last().record.fencing_token == 0
        assert uow.repo(TaskRepository).get(member.id) == member
        assert uow.repo(RunRepository).get(run.id).status.value == "running"
        uow.commit()


@pytest.mark.parametrize("review_mode", [ReviewMode.WAIVED, ReviewMode.SELF, ReviewMode.REQUIRED])
def test_failed_check_blocks_gate_and_followup_has_own_scope_budget_and_identity(
    side: Any,
    review_mode: ReviewMode,
) -> None:
    run, task, attempt, member, output, _ = gate_case(side, review_mode=review_mode)
    with side.uow() as uow:
        state, _ = load_state(uow, task.id)
        failed = check(side, uow, state, passed=False)
        seed_stage(
            side,
            uow,
            attempt,
            stage_id="gate_checks",
            stage_type="run_checks",
            state=StageState.COMPLETED,
            outcome_kind=StageOutcomeKind.CHECKS_FAILED,
        )
        state, _ = load_state(uow, task.id)
        outcome = phase_gate.decide(state, context(side, uow, run), uow, cause("stage_outcome"))
        assert outcome.kind is StageOutcomeKind.NOT_ACCEPTABLE
        assert "REQUIRED_CHECK_NOT_PASSED" in str(outcome.payload)
        action = CreateFollowups("checks_failed", (), (failed.id,))
        result = apply_action(
            ActionDecision(action, cause("check_failed", rule="D6g")),
            context(side, uow, run),
            uow,
            task_id=task.id,
        )
        assert result == "followups"
        (child,) = [t for t in uow.repo(TaskRepository).list_for_run(run.id) if t.kind is TaskKind.FOLLOWUP]
        assert child.id != member.id
        assert child.review_mode is ReviewMode.REQUIRED
        assert task.review_mode is review_mode
        assert child.origin.source_task_id == task.id
        assert child.declared_write_scope == (PathPattern("repo", "src/**"),)
        assert child.current_attempt_id is None
        assert child.accepted_output_id is None
        accounts = uow.repo(BudgetRepository).accounts_for(run.id, child.id, BudgetDimension.ATTEMPTS)
        assert any(a.task_id == child.id for a in accounts)
        assert uow.repo(TaskRepository).get(task.id).status is TaskStatus.BLOCKED
        assert uow.repo(OutputRepository).get(output.id) == output
        assert uow.repo(TaskRepository).get(member.id) == member
        uow.commit()
    with side.uow(readonly=True) as uow:
        query = uow.repo(ExecutionQueries)
        events = query.run_events(run.id, 0, query.head_run_seq(run.id), 100)
        assert any("followups-created" in e["event_type"] for e in events)


def test_t29_rereview_keeps_history_and_does_not_charge_attempts(side: Any, monkeypatch: Any) -> None:
    run, task, attempt, member, output, _ = gate_case(side)
    from skm.modules.execution.application import _state
    from skm.modules.execution.application.stages import gate_lifecycle
    from unit.execution.domain.test_advance_table import REVIEWED

    original_load = _state.load_state

    def gate_load(uow: Any, tid: Any) -> Any:
        state, wf = original_load(uow, tid)
        return state, REVIEWED if state.task.kind is TaskKind.PHASE_GATE else wf

    from skm.modules.execution.application.stages import phase_gate

    for module in (_state, gate_lifecycle, phase_gate):
        monkeypatch.setattr(module, "load_state", gate_load)
    with side.uow() as uow:
        original_stage = seed_stage(
            side,
            uow,
            attempt,
            stage_id="gate_checks",
            stage_type="run_checks",
            state=StageState.COMPLETED,
            outcome_kind=StageOutcomeKind.CHECKS_FAILED,
        )
        state, _ = load_state(uow, task.id)
        gate_lifecycle.followups(
            uow,
            context(side, uow, run),
            state,
            CreateFollowups("checks_failed", (), ()),
            cause("check_failed"),
        )
        child = next(t for t in uow.repo(TaskRepository).list_for_run(run.id) if t.kind is TaskKind.FOLLOWUP)
        state, _ = load_state(uow, task.id)
        assert state.gate["followups"] == [str(child.id)]
        # Integration/acceptance of the independent child is the prerequisite event for T29.
        ca = seed_attempt(side, uow, run.id, child.id, state=AttemptState.COMPLETED)
        co = seed_output(side, uow, ca)
        ce = integration_effect(
            replace(child, status=TaskStatus.ACCEPTED, accepted_attempt_id=ca.id),
            co,
            before=output.manifest.mounts[0].head_commit,
            after=output.manifest.mounts[0].head_commit,
            n=2,
        )
        uow.repo(EffectRepository).add(ce)
        done = replace(
            child,
            status=TaskStatus.ACCEPTED,
            accepted_attempt_id=ca.id,
            accepted_output_id=co.id,
            row_version=child.row_version + 1,
        )
        uow.repo(TaskRepository).save(done, expected_version=child.row_version)
        from decimal import Decimal

        from skm.modules.execution.domain.budget import BudgetAccount

        uow.repo(BudgetRepository).add_accounts(
            (
                BudgetAccount(
                    side.new_id(),
                    run.id,
                    "task",
                    task.id,
                    BudgetDimension.ATTEMPTS,
                    Decimal(1),
                    Decimal(1),
                    Decimal(0),
                    1,
                ),
            )
        )
        before = uow.repo(TaskRepository).get(task.id).attempt_count
        accounts_before = uow.repo(BudgetRepository).accounts_for(run.id, task.id, BudgetDimension.ATTEMPTS)
        release_dependents(uow, context(side, uow, run), run, cause("followup"))
        fresh_task = uow.repo(TaskRepository).get(task.id)
        assert fresh_task.attempt_count == before
        assert fresh_task.current_attempt_id != attempt.id
        old = uow.repo(AttemptRepository).get(attempt.id)
        assert old.end_reason == AttemptEndReason.GATE_REREVIEW
        assert old.current_output_id == output.id
        assert uow.repo(StageRepository).history(attempt.id).last().record == original_stage
        fresh = uow.repo(AttemptRepository).get(fresh_task.current_attempt_id)
        assert fresh.current_output_id is None
        assert fresh.environment_id is None
        assert fresh.continuation.stage.params["baseline_strategy"] == "gate_range"
        assert fresh.continuation.stage.params["gate_range"]
        assert (
            uow.repo(BudgetRepository).accounts_for(run.id, task.id, BudgetDimension.ATTEMPTS)
            == accounts_before
        )
        assert uow.repo(TaskRepository).get(member.id) == member
        uow.commit()


@pytest.mark.parametrize("advisory", [False, True])
def test_plan_coverage_is_retained_even_when_rejected_and_advisory_allows_done(
    side: Any, advisory: bool
) -> None:
    run, task, attempt, member, _output, _effect = gate_case(side, kind=TaskKind.PLAN_ACCEPTANCE)
    with side.uow() as uow:
        state, _ = load_state(uow, task.id)
        check(side, uow, state)
        state, _ = load_state(uow, task.id)
        outcome = plan_acceptance.decide(
            state,
            context(side, uow, run),
            uow,
            cause("stage_outcome"),
            coverage_mode="advisory" if advisory else "required",
        )
        decision = uow.repo(AcceptanceRepository).decisions_for_task(task.id)[-1]
        assert decision.basis.coverage_report == outcome.payload["coverage"]
        assert uow.repo(EvidenceBindingRepository).for_owner("attempt", attempt.id)
        if advisory:
            assert outcome.kind is StageOutcomeKind.ACCEPTED
            assert outcome.payload["diagnostics"] == ["COVERAGE_GAP"]
        else:
            assert outcome.kind is StageOutcomeKind.NOT_ACCEPTABLE
            assert "CRITERION_UNVERIFIED" in str(outcome.payload)
        assert uow.repo(TaskRepository).get(member.id) == member
        uow.commit()


def test_missing_receipt_rejects_range_in_application(side: Any) -> None:
    run, task, _attempt, _member, _output, _effect = gate_case(side, receipt=False)
    with side.uow() as uow:
        state, _ = load_state(uow, task.id)
        with pytest.raises(SkmError) as exc:
            phase_gate.decide(state, context(side, uow, run), uow, cause("stage_outcome"))
        assert exc.value.code.value == "CHECKOUT_MISMATCH"


def test_all_terminal_gates_finish_run_only_after_plan_acceptance(side: Any) -> None:
    run, task, _attempt, member, _output, _effect = gate_case(side, kind=TaskKind.PLAN_ACCEPTANCE)
    with side.uow() as uow:
        state, _ = load_state(uow, task.id)
        check(side, uow, state)
        action = RunStage(
            "plan_acceptance", StageType.PLAN_ACCEPTANCE, StageMode.NORMAL, 1, {"coverage": "advisory"}
        )
        assert uow.repo(RunRepository).get(run.id).status.value == "running"
        result = apply_action(
            ActionDecision(action, cause("stage_outcome", rule="K12")),
            context(side, uow, run),
            uow,
            task_id=task.id,
        )
        assert result == "done"
        assert uow.repo(RunRepository).get(run.id).status.value == "succeeded"
        assert uow.repo(TaskRepository).get(member.id) == member
        decision = uow.repo(AcceptanceRepository).decisions_for_task(task.id)[-1]
        assert decision.basis.coverage_report
        uow.commit()


def test_done_cannot_skip_required_plan_coverage(side: Any) -> None:
    from skm.modules.execution.domain.workflow.actions import Done

    run, task, _attempt, _member, _output, _effect = gate_case(side, kind=TaskKind.PLAN_ACCEPTANCE)
    with side.uow() as uow, pytest.raises(SkmError) as exc:
        apply_action(
            ActionDecision(Done(), cause("stage_outcome")), context(side, uow, run), uow, task_id=task.id
        )
    assert exc.value.code.value == "NOT_ACCEPTABLE"


def test_scheduler_empty_gate_accepts_with_waived_clearance_and_diagnostic(side: Any) -> None:
    from skm.modules.execution.application._state import effective_values
    from skm.modules.execution.application.commands.schedule_ready_tasks import create_attempt

    run, gate, _attempt, member, _output, _effect = gate_case(side)
    with side.uow() as uow:
        empty = ready_gate(side, uow, run, gate, member)
        _, values = effective_values(uow, run.id)
        assert create_attempt(uow, context(side, uow, run), run, empty, values) is None
        assert uow.repo(TaskRepository).get(empty.id).attempt_count == 0
        assert len(uow.repo(AttemptRepository).list_for_task(empty.id)) == 1
        assert uow.repo(TaskRepository).get(empty.id).status is TaskStatus.ACCEPTED
        decision = uow.repo(AcceptanceRepository).decisions_for_task(empty.id)[-1]
        assert decision.basis.clearance is ReviewClearance.WAIVED
        uow.commit()
    with side.uow(readonly=True) as uow:
        queries = uow.repo(ExecutionQueries)
        events = queries.run_events(run.id, 0, queries.head_run_seq(run.id), 100)
        assert any("GATE_EMPTY" in str(event["payload"]) for event in events)


def test_dispatch_pins_receipts_and_final_checks_without_writable_executor(side: Any) -> None:
    from skm.modules.execution.application.stages.gate_dispatch import select
    from skm.modules.execution.application.stages.gate_facts import check_definitions
    from unit.execution.domain.test_advance_table import REVIEWED

    run, task, _attempt, _member, _output, _effect = gate_case(side)
    with side.uow() as uow:
        state, _ = load_state(uow, task.id)
        assert state.gate["members"] == [{"task_id": str(_member.id), "status": "accepted"}]
        assert state.gate["required_checks"] == []
        assert state.gate["followups"] == []
        work_state, _ = load_state(uow, _member.id)
        assert work_state.gate is None
        prepared = select(
            uow,
            state,
            REVIEWED,
            RunStage("gate_prepare", StageType.PREPARE_ENVIRONMENT, StageMode.NORMAL, 1, {}),
        )
        assert prepared.params["baseline_strategy"] == "gate_range"
        assert prepared.params["gate_range"]
        checking = select(
            uow, state, REVIEWED, RunStage("gate_checks", StageType.RUN_CHECKS, StageMode.NORMAL, 1, {})
        )
        assert checking.params["scope"] == "gate"
        reviewing = select(
            uow,
            state,
            REVIEWED,
            RunStage("review", StageType.AGENT_REVIEW, StageMode.NORMAL, 1, {"audit_scope": "corrected"}),
        )
        assert reviewing.params["audit_scope"] == "range"
        plan = replace(task, kind=TaskKind.PLAN_ACCEPTANCE, spec_entity_id=None)
        definitions = check_definitions(uow, run, plan)
        spec = planning.get_revision_specification(uow, run.revision_id)
        assert {c.id for c in definitions} == {
            c.id for c in spec.checks if c.rerun_after_integration or c.owner == "plan"
        }


def test_member_item_phase_plan_chain_with_required_coverage_completes(side: Any) -> None:
    from skm.modules.execution.domain.deviation import DeviationAcceptance

    run, phase, _attempt, member, _output, _effect = gate_case(side)
    with side.uow() as uow:
        spec = planning.get_revision_specification(uow, run.revision_id)
        item = replace(
            phase,
            id=side.new_id(),
            kind=TaskKind.ITEM_GATE,
            spec_entity_id=spec.items[0].id,
            display_key=spec.items[0].key + "#gate",
            current_attempt_id=None,
            row_version=1,
        )
        plan = replace(
            phase,
            id=side.new_id(),
            kind=TaskKind.PLAN_ACCEPTANCE,
            spec_entity_id=None,
            display_key="PLAN#accept",
            current_attempt_id=None,
            row_version=1,
        )
        uow.repo(TaskRepository).add_many(
            (item, plan),
            (
                TaskEdge(run.id, item.id, member.id, EdgeKind.GATE_MEMBER, frozenset()),
                TaskEdge(run.id, phase.id, item.id, EdgeKind.GATE_MEMBER, frozenset()),
                TaskEdge(run.id, plan.id, phase.id, EdgeKind.GATE_MEMBER, frozenset()),
            ),
        )
        for task in (item, plan):
            attempt = seed_attempt(side, uow, run.id, task.id)
            changed = replace(task, current_attempt_id=attempt.id, row_version=2)
            uow.repo(TaskRepository).save(changed, expected_version=1)
            output = seed_output(side, uow, attempt)
            save_attempt(uow, replace(attempt, current_output_id=output.id))
        for task in (item, phase):
            result = apply_action(
                ActionDecision(
                    RunStage("phase_gate", StageType.PHASE_GATE, StageMode.NORMAL, 1, {}),
                    cause("stage_outcome", rule="K11"),
                ),
                context(side, uow, run),
                uow,
                task_id=task.id,
            )
            assert result == "done"
            assert uow.repo(RunRepository).get(run.id).status.value == "running"
        for criterion in spec.criteria:
            uow.repo(AcceptanceRepository).add_deviation(
                DeviationAcceptance(
                    side.new_id(),
                    run.id,
                    plan.id,
                    criterion.id,
                    None,
                    "owner coverage decision",
                    side.owner.principal_id,
                    side.clock.now(),
                    "coverage",
                )
            )
        state, _ = load_state(uow, plan.id)
        check(side, uow, state)
        result = apply_action(
            ActionDecision(
                RunStage("plan_acceptance", StageType.PLAN_ACCEPTANCE, StageMode.NORMAL, 1, {}),
                cause("stage_outcome", rule="K12"),
            ),
            context(side, uow, run),
            uow,
            task_id=plan.id,
        )
        assert result == "done"
        assert uow.repo(RunRepository).get(run.id).status.value == "succeeded"
        report = uow.repo(AcceptanceRepository).decisions_for_task(plan.id)[-1].basis.coverage_report
        assert report["counts"]["criteria"] == report["counts"]["verified"]
        assert uow.repo(TaskRepository).get(member.id) == member
        uow.commit()


@pytest.mark.parametrize(
    ("kind", "missing"),
    [
        (TaskKind.PHASE_GATE, None),
        (TaskKind.PHASE_GATE, "run_checks"),
        (TaskKind.PHASE_GATE, "agent_review"),
        (TaskKind.PHASE_GATE, "phase_gate"),
        (TaskKind.PLAN_ACCEPTANCE, None),
        (TaskKind.PLAN_ACCEPTANCE, "run_checks"),
    ],
)
def test_readiness_r13_uses_required_gate_runners(kind: TaskKind, missing: Any) -> None:
    from types import SimpleNamespace

    from skm.modules.execution.application._preview_facts import gate_facts
    from skm.modules.execution.domain.readiness import evaluate_readiness
    from unit.execution.domain.test_advance_table import REVIEWED
    from unit.execution.domain.test_gates import gate_inputs
    from unit.execution.domain.test_readiness import document

    task = gate_inputs().task
    task = replace(
        task,
        kind=kind,
        spec_entity_id=None if kind is TaskKind.PLAN_ACCEPTANCE else task.spec_entity_id,
        review_mode=ReviewMode.REQUIRED if kind is TaskKind.PHASE_GATE else ReviewMode.WAIVED,
    )
    check_id = "required-check"
    spec = SimpleNamespace(
        checks=(SimpleNamespace(id=check_id, required=True, owner="plan", rerun_after_integration=True),)
    )
    graph = {
        "tasks": []
        if kind is TaskKind.PLAN_ACCEPTANCE
        else [{"task_key": task.display_key, "checks": [{"check_id": check_id}]}]
    }
    workflow = replace(REVIEWED, stages=tuple(s for s in REVIEWED.stages if s.type.value != missing))
    facts = gate_facts(SimpleNamespace(tasks=(task,)), graph, workflow, spec)
    assert facts[0]["gate_required"] is True
    assert facts[0]["gate_supported"] is (missing is None)
    report = evaluate_readiness(document(tasks=facts))
    assert any(f.code == "GATE_UNSUPPORTED_BY_WORKFLOW" for f in report.findings) is (missing is not None)


def test_scheduler_first_gate_attempt_pins_receipt_range(side: Any, monkeypatch: Any) -> None:
    from skm.modules.execution.application import _state
    from skm.modules.execution.application.commands.schedule_ready_tasks import create_attempt
    from unit.execution.domain.test_advance_table import REVIEWED

    run, gate, _attempt, member, output, effect = gate_case(side)
    monkeypatch.setattr(_state, "load_run_workflow", lambda _uow, _run, _task: REVIEWED)
    with side.uow() as uow:
        task = ready_gate(side, uow, run, gate, member)
        _, values = _state.effective_values(uow, run.id)
        created = create_attempt(uow, context(side, uow, run), run, task, values)
        assert created.continuation.stage.stage_id == "gate_prepare"
        params = created.continuation.stage.params
        assert params["baseline_strategy"] == "gate_range"
        assert params["gate_range"][0]["head"] == output.manifest.mounts[0].head_commit
        assert params["gate_range"][0]["effects"][0]["effect_id"] == str(effect.id)
        assert created.current_output_id is None
        assert uow.repo(TaskRepository).get(task.id).attempt_count == 1


@pytest.mark.parametrize("scope", ["gate", "rerun_after_integration"])
@pytest.mark.parametrize("followup", [False, True])
def test_worker_prepares_plan_and_followup_checks_on_current_output(
    side: Any, monkeypatch: Any, scope: str, followup: bool
) -> None:
    from types import SimpleNamespace

    from skm.modules.execution.application._worker_host_stages import prepare_checks

    from ._gates_support import followup_case

    run, gate, attempt, _member, output, _effect = gate_case(side, kind=TaskKind.PLAN_ACCEPTANCE)
    with side.uow() as uow:
        spec = planning.get_revision_specification(uow, run.revision_id)
        rerun = replace(spec.checks[0], rerun_after_integration=True)
        plan_only = replace(rerun, id=side.new_id(), key="V2", owner="plan", rerun_after_integration=False)
        pinned = replace(spec, checks=(rerun, plan_only))
        monkeypatch.setattr(planning, "get_revision_specification", lambda _uow, _revision: pinned)
        task = gate
        if followup:
            task, attempt, output = followup_case(side, uow, run, gate)
        state, _ = load_state(uow, task.id)
        previous = check(side, uow, state)
        seed_stage(side, uow, attempt, stage_type="run_checks", state=StageState.COMPLETED)
        old_output = output
        output = seed_output(side, uow, attempt, seq=2)
        save_attempt(uow, replace(attempt, current_output_id=output.id))
        payload = prepare_checks(
            uow,
            context(side, uow, run),
            SimpleNamespace(run=run, task=task, attempt=attempt),
            seed_stage(side, uow, attempt, seq=2, stage_type="run_checks"),
            SimpleNamespace(params={"scope": scope}),
        )
        expected = {rerun.id} if scope == "rerun_after_integration" else {rerun.id, plan_only.id}
        records = uow.repo(CheckRepository).for_output(output.id)
        assert {c.check_spec_id for c in records} == expected
        assert len(payload) == len(expected)
        assert all(c.task_id == task.id and c.attempt_id == attempt.id and c.round_no == 2 for c in records)
        assert all(c.state is CheckState.PENDING and c.reused_from_id is None for c in records)
        assert all(p["reused"] is False for p in payload)
        assert uow.repo(CheckRepository).for_output(old_output.id) == (previous,)
        assert previous.id not in {c.id for c in records}


def test_manual_gate_failure_creates_followups_without_invalid_transition(side: Any) -> None:
    from skm.modules.execution.generated.commands import RecordManualVerdict

    run, task, member, output, manual = manual_gate_case(side)
    result = side.client.dispatch(RecordManualVerdict(manual.id, "fail", "E2 regression"))
    assert result.task_status == "blocked"
    assert result.next_action_kind == "followups"
    with side.uow(readonly=True) as uow:
        gate = uow.repo(TaskRepository).get(task.id)
        (child,) = [t for t in uow.repo(TaskRepository).list_for_run(run.id) if t.kind is TaskKind.FOLLOWUP]
        assert gate.blocking_reason.code is BlockingCode.BLOCKED_BY_DEPENDENCY
        assert gate.blocking_reason.refs["prerequisite_task_ids"] == [str(child.id)]
        assert child.origin.source_task_id == task.id
        assert child.review_mode is ReviewMode.REQUIRED
        assert uow.repo(CheckRepository).get(manual.id).state is CheckState.FAILED
        assert uow.repo(TaskRepository).get(member.id) == member
        assert uow.repo(OutputRepository).get(output.id) == output
        history = uow.repo(StageRepository).history(gate.current_attempt_id)
        assert [e.record.stage_type for e in history.entries] == ["run_checks"]
