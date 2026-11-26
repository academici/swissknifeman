"""Terminal stage trigger, committed refusals, schema and semantic checks."""

from dataclasses import replace
from typing import Any

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._control import current_binding_digest
from skm.modules.execution.application._events import emit
from skm.modules.execution.application._incident_gate import gate_action
from skm.modules.execution.application._primitives import (
    clear_advance,
    move,
    save_attempt,
    schemas,
    server_context,
)
from skm.modules.execution.application._state import load_state
from skm.modules.execution.application._worker_budget import close_budgets, pause_budget
from skm.modules.execution.application._worker_events import close_steps, stage_completed
from skm.modules.execution.application._worker_protocol import revoke_authority
from skm.modules.execution.application.apply_action import apply_action
from skm.modules.execution.domain.attempt import ContinuationCause, DeferredTrigger, EntityRef, defer_trigger
from skm.modules.execution.domain.blocking_reason import blocking_reason
from skm.modules.execution.domain.decision_record import QuestionCategory
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionRequest,
    DecisionState,
    question_digest,
    question_key,
)
from skm.modules.execution.domain.finding import FindingState
from skm.modules.execution.domain.finding_resolution import FindingResolution, ResolutionKind
from skm.modules.execution.domain.review import ReviewState, Verdict
from skm.modules.execution.domain.role_contracts import ROLE_CONTRACTS
from skm.modules.execution.domain.semantics import drift
from skm.modules.execution.domain.stage_record import (
    StageOutcomeKind,
    complete_stage,
    fail_stage,
    interrupt_stage,
)
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.domain.workflow.actions import Escalate
from skm.modules.execution.domain.workflow.engine import decide_advance
from skm.modules.execution.ports import (
    AttemptRepository,
    DecisionRepository,
    OutputRepository,
    ReviewRepository,
    StageRepository,
    StepRepository,
)


def validate_agent_result(uow: UnitOfWork, fenced: Any, step: Any, outcome: Any, bindings: Any) -> Any:
    result = outcome.get("role_result")
    schemas().require_valid(ROLE_CONTRACTS[step.role].result_schema_urn, result)
    raw_id = bindings.get((step.id, "raw_result"))
    if raw_id is not None:
        import json

        text = artifacts.read_text_content(uow, raw_id, max_bytes=2_000_000)
        if text is None:
            raise error_for(ErrorCode.RESULT_INVALID, "raw result evidence is unavailable")
        try:
            raw = json.loads(text)
        except (ValueError, TypeError) as exc:
            raise error_for(ErrorCode.RESULT_INVALID, "raw result evidence is not JSON") from exc
        if drift(ROLE_CONTRACTS[step.role].result_kind.value, raw, result):
            raise error_for(ErrorCode.REPAIR_SEMANTIC_DRIFT, "repaired result changes raw semantics")
    elif outcome.get("repairs"):
        raise error_for(ErrorCode.REPAIR_SEMANTIC_DRIFT, "repair requires raw evidence")
    if step.role.value == "triager":
        minimal_triage_targets(uow, fenced, result)
    return result


def minimal_triage_targets(uow: UnitOfWork, fenced: Any, result: Any) -> dict[str, Any]:
    """Findings a minimal triage must confirm: each open finding of the current reviewed output, exactly once.

    Rejections and reproductions are refused; this triage only confirms.
    """
    repo = uow.repo(ReviewRepository)
    review = max(
        (r for r in repo.for_task(fenced.task.id) if r.state is ReviewState.COMPLETED),
        key=lambda r: r.round_no,
        default=None,
    )
    if (
        review is None
        or review.attempt_id != fenced.attempt.id
        or review.output_id != fenced.attempt.current_output_id
        or review.verdict is None
        or review.verdict.value not in {"red", "attention"}
    ):
        raise error_for(ErrorCode.RESULT_INVALID, "triage requires the current attempt's reviewed output")
    findings = [
        f
        for f in repo.findings_for_task(fenced.task.id)
        if f.review_id == review.id
        and f.state in {FindingState.OPEN, FindingState.CONFIRMED, FindingState.DEFERRED}
    ]
    targets = {f.local_id: f for f in findings}
    if not targets or len(targets) != len(findings):
        raise error_for(ErrorCode.RESULT_INVALID, "triage requires unambiguous primary finding IDs")
    rows = result["confirmed"]
    names = [row["finding_id"] for row in rows]
    if (
        result["rejected"]
        or any("reproduction" in row for row in rows)
        or len(names) != len(set(names))
        or set(names) != set(targets)
    ):
        raise error_for(
            ErrorCode.RESULT_INVALID, "minimal triage must confirm every current finding exactly once"
        )
    return targets


def record_minimal_triage(uow: UnitOfWork, fenced: Any, result: Any) -> None:
    targets = minimal_triage_targets(uow, fenced, result)
    for row in result["confirmed"]:
        finding = targets[row["finding_id"]]
        state = FindingState.CONFIRMED if row["decision"] == "fix_now" else FindingState.DEFERRED
        uow.repo(ReviewRepository).save_finding(replace(finding, state=state))


def resolve_review_findings(
    uow: UnitOfWork, ctx: Any, fenced: Any, review: Any, old: Any, present: Any
) -> None:
    """An independent later review resolves only absent findings whose candidate bytes changed."""
    repo = uow.repo(ReviewRepository)
    reviews = {r.id: r for r in repo.for_task(fenced.task.id)}
    output = uow.repo(OutputRepository).get(review.output_id)

    def marks(candidate: Any) -> dict[tuple[str, str], str]:
        result = {(p.mount, p.path): p.fingerprint for p in candidate.manifest.changed_paths}
        result.update(
            {(p.mount, p.old_path): "absent" for p in candidate.manifest.changed_paths if p.old_path}
        )
        return result

    after = marks(output)
    for key, finding in old.items():
        previous = reviews[finding.review_id]
        from_review_fix = (
            finding.state is FindingState.OPEN
            and output.produced_by_step_id is not None
            and previous.reviewer_ref.get("step_id") == str(output.produced_by_step_id)
            and review.reviewer_ref.get("step_id") != str(output.produced_by_step_id)
            and review.verdict is Verdict.GREEN
        )
        if (
            key in present
            or (finding.state is not FindingState.CONFIRMED and not from_review_fix)
            or previous.attempt_id != fenced.attempt.id
            or previous.output_id == review.output_id
        ):
            continue
        before = marks(uow.repo(OutputRepository).get(previous.output_id))
        location = (finding.location.get("mount"), finding.location.get("path"))
        if before.get(location) == after.get(location):
            continue
        repo.save_finding(replace(finding, state=FindingState.RESOLVED))
        repo.add_resolution(
            FindingResolution(
                ctx.ids.new_id(),
                finding.id,
                ResolutionKind.FIXED,
                review.output_id,
                "Absent from review of corrected candidate",
                ctx.actor.principal_id,
                fenced.now,
            )
        )


def advance_terminal(uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any) -> None:
    ctx = server_context(ctx, uow)
    attempt = uow.repo(AttemptRepository).get(fenced.attempt.id)
    event_id = ctx.ids.new_id()
    pending = defer_trigger(
        attempt,
        DeferredTrigger(
            event_id,
            ContinuationCause(
                "stage_outcome", None, refs=(EntityRef("stage", stage.id),), source_event_id=event_id
            ),
        ),
        continuation_id=ctx.ids.new_id(),
    )
    save_attempt(uow, pending)
    if fenced.run.status.value == "running":
        state, workflow = load_state(uow, fenced.task.id)
        decision = decide_advance(state, workflow, state.effective_policy, fenced.now)

        if isinstance(decision.action, Escalate) and decision.action.kind is DecisionKind.QUESTION:
            gate_action(uow, ctx, state, decision.action)
            apply_question(uow, ctx, fenced, stage, pending, decision)
            return
        apply_action(
            decision,
            ctx,
            uow,
            task_id=fenced.task.id,
            why=dict(decision.cause),
        )


def committed_refusal(uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any, *, code: str) -> None:
    steps = uow.repo(StepRepository).for_stage(stage.id)
    closed = close_steps(uow, fenced, stage, steps, successful=False, code=code)
    budget_refusal = close_budgets(uow, fenced, stage, closed)
    stage = replace(
        fail_stage(stage, error_code=code, now=fenced.now),
        outcome_kind=StageOutcomeKind.RUNTIME_ERROR,
        outcome={"error_code": code, "error_class": "invalid_request"},
    )
    uow.repo(StageRepository).save(stage)
    revoke_authority(uow, ctx, fenced)
    stage_completed(uow, fenced, stage, closed)
    if code == "BUDGET_EXHAUSTED" or budget_refusal is not None:
        pause_budget(
            uow,
            ctx,
            fenced,
            budget_refusal or {"scope": "task", "dimension": "tokens", "limit": 0, "spent": 0},
        )
    advance_terminal(uow, ctx, fenced, stage)


def interrupt_paused_handoff(uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any) -> None:
    steps = uow.repo(StepRepository).for_stage(stage.id)
    closed = close_steps(uow, fenced, stage, steps, successful=False, code="RUN_NOT_ACTIVE")
    budget_refusal = close_budgets(uow, fenced, stage, closed)
    stage = interrupt_stage(stage, now=fenced.now)
    uow.repo(StageRepository).save(stage)
    revoke_authority(uow, ctx, fenced)
    stage_completed(uow, fenced, stage, closed)
    if budget_refusal is not None:
        pause_budget(uow, ctx, fenced, budget_refusal)
    advance_terminal(uow, ctx, fenced, stage)


def terminal_stage(stage: Any, outcome_kind: Any, outcome: Any, now: Any) -> Any:
    kind = StageOutcomeKind(outcome_kind)
    if kind in {StageOutcomeKind.RESULT_INVALID, StageOutcomeKind.RUNTIME_ERROR}:
        return replace(
            fail_stage(
                stage, error_code=outcome.get("error_code", kind.value.upper()), now=now, outcome_kind=kind
            ),
            outcome=outcome,
        )
    return complete_stage(stage, outcome_kind=kind, outcome=outcome, now=now)


def apply_question(uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any, pending: Any, decision: Any) -> None:
    """Reduce the evaluator's question action with category present at construction."""
    action = decision.action
    stage_outcome: Any = stage.outcome or {}
    questions: Any = stage_outcome.get("questions", [])
    payload: dict[str, Any] = {**(questions[0] if questions else {}), **dict(action.payload)}
    category = QuestionCategory(payload["category"])
    request = DecisionRequest(
        ctx.ids.new_id(),
        fenced.run.workspace_id,
        fenced.run.id,
        fenced.task.id,
        DecisionKind.QUESTION,
        Audience.OWNER,
        category,
        frozenset(payload.get("gate_categories", ())),
        question_key(fenced.task.display_key, payload),
        question_digest(fenced.task.display_key, payload),
        1,
        payload,
        None,
        {
            "attempt_id": str(pending.id),
            "stage_record_id": str(stage.id),
            "input_part_digest": current_binding_digest(uow, pending),
        },
        DecisionState.OPEN,
        None,
        None,
        fenced.now,
    )
    uow.repo(DecisionRepository).add(request)
    reason = blocking_reason(
        action.blocking_code,
        task_id=fenced.task.id,
        refs={
            "decision_request_id": str(request.id),
            "question_key": request.question_key,
        },
        now=fenced.now,
        message=action.code,
    )
    move(uow, ctx, fenced.run, fenced.task, TaskStatus.AWAITING_DECISION, decision.cause, blocking=reason)
    clear_advance(uow, pending)
    emit(
        uow,
        fenced.run,
        "decision-requested",
        {
            "request_id": str(request.id),
            "task_id": str(fenced.task.id),
            "kind": "question",
            "audience": "owner",
            "blocking_code": action.blocking_code.value,
        },
        decision.cause,
    )
