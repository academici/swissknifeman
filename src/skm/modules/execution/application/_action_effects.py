"""Bounded control-plane chains, immutable acceptance, scout reuse and repair artifacts."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._manual_report import register_manual_report
from skm.modules.execution.application._plain import plain
from skm.modules.execution.application._primitives import budget_accounts, clear_advance, move
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application.stages import acceptance_gate, human_gate
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.check_execution import CheckKind
from skm.modules.execution.domain.contracts import EvidenceOwnerKind
from skm.modules.execution.domain.decision_record import QuestionCategory
from skm.modules.execution.domain.decision_request import question_digest, question_key
from skm.modules.execution.domain.fix_brief import CheckLog, TriageNote, build_fix_brief
from skm.modules.execution.domain.readiness import ReadinessFinding, canonical_digest, readiness_status
from skm.modules.execution.domain.review import ReviewClearance
from skm.modules.execution.domain.run import RunKind, RunStatus, finish
from skm.modules.execution.domain.stage_record import (
    StageOutcomeKind,
    StageState,
    control_plane_record,
    skipped_record,
)
from skm.modules.execution.domain.step import RoleId, StepState
from skm.modules.execution.domain.task import (
    GATE_KINDS,
    TERMINAL_TASK_STATUSES,
    TaskKind,
    TaskOrigin,
    TaskStatus,
)
from skm.modules.execution.domain.task_graph import EdgeKind, TaskEdge, gate_members
from skm.modules.execution.domain.workflow import actions as act
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.ports import (
    AcceptanceRepository,
    BudgetRepository,
    BundleRepository,
    EnvironmentRepository,
    EvidenceBindingRepository,
    ReadinessRepository,
    ReviewRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.execution.public import StageOutcome
from skm.modules.planning import public as planning

from ._control import stage_completed
from ._events import emit, event_class, save_task, task_created


def control_stage(uow: UnitOfWork, ctx: Any, state: Any, action: Any, why: Any) -> Any:
    if action.stage_type.value == "human_gate":
        return human_gate.decide(state, ctx, uow, why)
    if action.stage_type.value == "acceptance_gate":
        clearance = state.reviews[-1].clearance if state.reviews else None

        if clearance is None:
            mode = state.task.review_mode.value
            clearance = ReviewClearance.GREEN if mode == "required" else ReviewClearance(mode)
        return acceptance_gate.decide(state, clearance, ctx, uow, why)
    # Phase/plan gates retain their prerequisite and check facts. The graph closure
    # controls membership, so absence of membership proof cannot produce acceptance.
    edges = uow.repo(TaskRepository).edges_for_run(state.run.id)
    members = [uow.repo(TaskRepository).get(tid) for tid in gate_members(state.task, edges)]
    reasons: list[Any] = []
    if not members or any(t.status not in {TaskStatus.ACCEPTED, TaskStatus.SKIPPED} for t in members):
        reasons.append({"code": "MEMBER_NOT_DONE", "refs": {}})
    reasons.extend(
        {"code": "REQUIRED_CHECK_NOT_PASSED", "refs": {"check_execution_id": str(check.id)}}
        for check in state.checks
        if check.required and check.state.value != "passed"
    )

    spec = planning.get_revision_specification(uow, state.run.revision_id)
    graph = planning.compile_execution_graph(spec, state.run.revision_id)
    node = next((n for n in graph.tasks if n.task_key == state.task.display_key), None)
    bound: set[Any] = set() if node is None else {b.check_id for b in node.checks}
    reasons.extend(
        {"code": "REQUIRED_CHECK_NOT_PASSED", "refs": {"check_spec_id": str(check.id)}}
        for check in spec.checks
        if check.id in bound
        and check.required
        and not any(c.check_spec_id == check.id and c.state.value == "passed" for c in state.checks)
    )
    if state.task.review_mode.value == "required" and not state.reviews:
        reasons.append({"code": "REVIEW_MISSING", "refs": {}})
    return StageOutcome(
        StageOutcomeKind.NOT_ACCEPTABLE if reasons else StageOutcomeKind.ACCEPTED, {"reasons": reasons}
    )


def accept_action(
    uow: UnitOfWork, ctx: Any, state: Any, workflow: Any, action: Any, why: Any
) -> act.ActionDecision:
    """Record the acceptance gate and return the action the table applies next."""
    outcome = acceptance_gate.decide(state, action.clearance, ctx, uow, why)

    gate = next((s for s in workflow.stages if s.type.value == "acceptance_gate"), None)
    record = control_plane_record(
        tuple(e.record for e in state.history.entries),
        record_id=ctx.ids.new_id(),
        attempt_id=state.attempt.id,
        run_id=state.run.id,
        task_id=state.task.id,
        stage_id=gate.id if gate else "acceptance",
        stage_type="acceptance_gate",
        round_no=1,
        input_digest=canonical_digest(
            {"output_id": str(action.output_id), "clearance": action.clearance.value}
        ),
        outcome_kind=outcome.kind,
        outcome=outcome.payload,
        now=ctx.clock.now(),
    )
    uow.repo(StageRepository).add(record)
    stage_completed(uow, state.run, record, [], why)
    if outcome.kind is StageOutcomeKind.NOT_ACCEPTABLE:
        escalation = act.Escalate(
            act.DecisionKind.ESCALATION, "NOT_ACCEPTABLE", dict(outcome.payload), BlockingCode.WAITING_OWNER
        )
        return act.ActionDecision(escalation, why)
    integrate = next((s for s in workflow.stages if s.type.value == "integrate"), None)
    if state.output is None or state.output.source.value != "executor":
        integrate = None
    next_action = (
        act.Done()
        if integrate is None
        else act.RunStage(integrate.id, integrate.type, StageMode.NORMAL, 1, integrate.params.as_json())
    )
    return act.ActionDecision(next_action, why)


def question_request(request: Any, state: Any) -> Any:
    payload = dict(request.payload)
    category = QuestionCategory(payload.get("category", "architectural"))
    return replace(
        request,
        category=category,
        question_key=question_key(state.task.display_key, payload),
        question_digest=question_digest(state.task.display_key, payload),
        gate_categories=frozenset(payload.get("gate_categories", [])),
    )


def reuse_scout(uow: UnitOfWork, ctx: Any, state: Any, workflow: Any, action: Any, why: Any) -> bool:
    definition = next((s for s in workflow.stages if s.id == action.stage_id), None)
    if definition is None or definition.role is not RoleId.SCOUT:
        return False
    env = uow.repo(EnvironmentRepository).for_attempt(state.attempt.id)
    if env is None:
        return False

    bundle = uow.repo(BundleRepository).get(state.run.id)
    profile = next(
        (p for p in bundle.resource_pins.resources if p.kind == "agent_profile" and p.key == "scout"), None
    )
    if profile is None:
        return False
    key = canonical_digest(
        {
            "task_contract": str(state.task.spec_entity_id),
            "revision": str(state.run.revision_id),
            "baseline": plain(env.baseline),
            "profile": str(profile.resource_version_id),
            "context_policy": plain(bundle.context_policy),
        }
    )
    step = uow.repo(StepRepository).find_reusable_scout(state.run.project_id, key)
    if step is None or step.state is not StepState.SUCCEEDED:
        return False
    evidence = [v for v, _ in uow.repo(EvidenceBindingRepository).for_owner("attempt", step.attempt_id)]
    if not evidence:
        return False
    artifacts.require_ready_versions(uow, state.run.workspace_id, evidence)
    old = uow.repo(StageRepository).get(step.stage_record_id)
    record = skipped_record(
        tuple(e.record for e in state.history.entries),
        record_id=ctx.ids.new_id(),
        attempt_id=state.attempt.id,
        run_id=state.run.id,
        task_id=state.task.id,
        stage_id=action.stage_id,
        stage_type=action.stage_type.value,
        round_no=action.round_no,
        input_digest=key,
        now=ctx.clock.now(),
    )
    record = replace(
        record,
        state=StageState.COMPLETED,
        outcome_kind=old.outcome_kind,
        outcome=old.outcome,
        reused_from_step_id=step.id,
    )
    uow.repo(StageRepository).add(record)
    stage_completed(uow, state.run, record, [], why)
    return True


def create_followups(uow: UnitOfWork, ctx: Any, state: Any, action: act.CreateFollowups, why: Any) -> str:
    created: list[Any] = []
    for index, finding_id in enumerate(action.finding_ids or (None,)):
        tid = ctx.ids.new_id()
        origin = TaskOrigin(state.task.id, () if finding_id is None else (finding_id,), action.reason)
        task = replace(
            state.task,
            id=tid,
            kind=TaskKind.FOLLOWUP,
            spec_entity_id=None,
            display_key=f"@followup/{tid}",
            origin=origin,
            position=state.task.position + index + 1,
            status=TaskStatus.READY,
            current_attempt_id=None,
            accepted_attempt_id=None,
            accepted_output_id=None,
            attempt_count=0,
            check_fix_rounds=0,
            review_rounds=0,
            blocking_reason=None,
            row_version=1,
        )
        edge = TaskEdge(state.run.id, state.task.id, tid, EdgeKind.GATE_MEMBER, frozenset())
        uow.repo(TaskRepository).add_synthetic(task, (edge,))

        _, values = effective_values(uow, state.run.id)
        uow.repo(BudgetRepository).add_accounts(budget_accounts(ctx, state.run.id, (tid,), values))
        task_created(uow, state.run, task, why)
        emit(uow, state.run, "task-ready", {"task_id": str(tid), "reason": "followup"}, why)
        created.append(str(tid))
    reason = blocking_reason(
        BlockingCode.BLOCKED_BY_DEPENDENCY,
        task_id=state.task.id,
        refs={"prerequisite_task_ids": created},
        now=ctx.clock.now(),
        message="followups pending",
    )
    move(uow, ctx, state.run, state.task, TaskStatus.BLOCKED, why, blocking=reason)
    clear_advance(uow, state.attempt)
    return "followups"


def rework_action(
    uow: UnitOfWork, ctx: Any, state: Any, workflow: Any, action: act.Rework, why: Any
) -> act.ActionDecision:
    """Persist the fix brief and return the executor rework stage the table applies next."""
    manual = action.reason == "manual_failed"
    checks = tuple(c for c in state.checks if c.kind is CheckKind.MANUAL) if manual else state.checks
    findings = () if manual else state.findings
    review = state.reviews[-1] if state.reviews and not manual else None
    owners: list[tuple[EvidenceOwnerKind, UUID]] = [] if review is None else [("review", review.id)]
    owners.extend(("check_execution", c.id) for c in checks)
    files = [v for kind, oid in owners for v, _ in uow.repo(EvidenceBindingRepository).for_owner(kind, oid)]
    brief_id = ctx.ids.new_id()
    if not files and manual:
        files = [register_manual_report(uow, ctx, state, checks, brief_id)]
    if not files:
        raise error_for(ErrorCode.NOT_ACCEPTABLE, "repair requires retained full report evidence")
    logs = {
        check.id: CheckLog(state.manual[check.id].comment or check.summary, files[0])
        for check in checks
        if manual and check.id in state.manual
    }
    brief = build_fix_brief(
        findings,
        checks,
        {},
        brief_id=brief_id,
        task_id=state.task.id,
        attempt_id=state.attempt.id,
        source_review_id=None if review is None else review.id,
        source_check_round=max((c.round_no for c in checks), default=1) if review is None else None,
        full_report_file_version_id=files[0],
        triage={f.finding_key: TriageNote("fix_now") for f in findings},
        logs=logs,
    )
    uow.repo(ReviewRepository).add_fix_brief(brief)
    task = move(uow, ctx, state.run, state.task, TaskStatus.REWORK_REQUIRED, why)
    if action.reason in {"checks_failed", "manual_failed"}:
        updated = replace(task, check_fix_rounds=task.check_fix_rounds + 1, row_version=task.row_version + 1)
        save_task(uow, state.run, task, updated, why, ctx.clock.now())
        task = updated
    emit(
        uow,
        state.run,
        "task-rework-required",
        {
            "task_id": str(task.id),
            "attempt_id": str(state.attempt.id),
            "reason": action.reason,
            "round": task.check_fix_rounds
            if action.reason in {"checks_failed", "manual_failed"}
            else task.review_rounds,
            "fix_brief_id": str(brief.id),
            "input_output_id": str(state.attempt.current_output_id),
            "check_execution_ids": [str(c.id) for c in checks],
            "review_id": None if review is None else str(review.id),
        },
        why,
    )
    stage = next(s for s in workflow.stages if s.role is RoleId.EXECUTOR)
    follow = act.RunStage(
        stage.id,
        stage.type,
        StageMode.REWORK,
        1,
        stage.params.as_json(),
        feedback=FeedbackRefs(fix_brief_id=brief.id),
    )
    return act.ActionDecision(follow, why)


def finish_run(uow: UnitOfWork, ctx: Any, run: Any, why: Any) -> None:
    tasks = uow.repo(TaskRepository).list_for_run(run.id)
    if any(t.status not in TERMINAL_TASK_STATUSES for t in tasks):
        return
    if run.kind is RunKind.READINESS_AUDIT:
        original = uow.repo(ReadinessRepository).get(run.audited_report_id)
        task = tasks[0]
        # A skipped or failed audit task may never have started an attempt; it has no auditor result.
        entries = (
            ()
            if task.current_attempt_id is None
            else uow.repo(StageRepository).history(task.current_attempt_id).entries
        )
        auditor = next(
            (
                entry
                for entry in reversed(entries)
                if any(
                    step.role.value == "advisor" and step.state is StepState.SUCCEEDED for step in entry.steps
                )
            ),
            None,
        )
        if auditor is None:
            raise error_for(ErrorCode.NOT_ACCEPTABLE, "completed audit requires a retained auditor result")
        auditor_step = next(
            step
            for step in auditor.steps
            if step.role.value == "advisor" and step.state is StepState.SUCCEEDED
        )
        audit = dict(plain(auditor_step.result or auditor.record.outcome or {}))
        findings = list(original.findings)
        if audit.get("verdict") in {"red", "attention"}:
            findings.append(
                ReadinessFinding(
                    "SEMANTIC_AUDIT_" + audit["verdict"].upper(),
                    "error" if audit["verdict"] == "red" else "advisory",
                    None,
                    str(audit.get("summary", "")),
                    "R12_semantic",
                )
            )
        report = replace(
            original,
            id=ctx.ids.new_id(),
            findings=tuple(findings),
            status=readiness_status(tuple(findings)),
            audit={"run_id": str(run.id), "step_id": str(auditor_step.id), **audit},
            supersedes_report_id=original.id,
            created_at=ctx.clock.now(),
        )
        uow.repo(ReadinessRepository).add(report)
        uow.record(
            event_class("urn:skm:execution:event:readiness-reported:v1")(
                run.plan_id,
                run.workspace_id,
                {
                    "workspace_id": str(report.workspace_id),
                    "project_id": str(report.project_id),
                    "report_id": str(report.id),
                    "plan_id": str(run.plan_id),
                    "revision_id": str(run.revision_id),
                    "status": report.status.value,
                    "finding_counts": {
                        "error": sum(f.severity == "error" for f in findings),
                        "advisory": sum(f.severity == "advisory" for f in findings),
                    },
                    "supersedes_report_id": str(original.id),
                },
            )
        )
    success = all(t.status in {TaskStatus.ACCEPTED, TaskStatus.SKIPPED} for t in tasks)
    closed = finish(run, outcome=RunStatus.SUCCEEDED if success else RunStatus.FAILED, now=ctx.clock.now())
    uow.repo(RunRepository).save(closed, expected_version=run.row_version)
    emit(
        uow,
        run,
        "run-finished",
        {
            "outcome": closed.status.value,
            "counts_by_status": {
                status.value: sum(t.status is status for t in tasks) for status in TaskStatus
            },
        },
        why,
    )


def done_clearance(uow: UnitOfWork, state: Any) -> str:
    decisions = uow.repo(AcceptanceRepository).decisions_for_task(state.task.id)
    if decisions:
        decision = decisions[-1]
        if decision.decision != "accepted" or decision.output_id != state.attempt.current_output_id:
            raise error_for(ErrorCode.NOT_ACCEPTABLE, "Done requires acceptance of the current output")
        return decision.basis.clearance.value
    last = state.history.last()
    if (
        state.task.kind not in GATE_KINDS
        or last is None
        or last.record.outcome_kind
        not in {
            StageOutcomeKind.SUCCESS,
            StageOutcomeKind.ACCEPTED,
            StageOutcomeKind.VERDICT_GREEN,
            StageOutcomeKind.VERDICT_ATTENTION,
            StageOutcomeKind.VERDICT_RED,
        }
    ):
        raise error_for(ErrorCode.NOT_ACCEPTABLE, "Done requires a completed gate or acceptance decision")
    return "report" if state.run.kind is RunKind.READINESS_AUDIT else "green"
