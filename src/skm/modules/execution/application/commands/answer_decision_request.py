"""Bind an owner's answer to the exact committed request revision and output."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.execution.application._control import current_binding_digest, lock_task, require_permission
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._json_reads import obj, texts
from skm.modules.execution.application._plain import plain
from skm.modules.execution.application.apply_action import commit_trigger, prepare_trigger
from skm.modules.execution.application.commands.cancel_run import handle as cancel
from skm.modules.execution.application.commands.reconfigure_run import handle as reconfigure
from skm.modules.execution.application.commands.skip_task import handle as skip
from skm.modules.execution.domain.autonomy import AuthorityEnvelope
from skm.modules.execution.domain.decision_record import make_decision_record
from skm.modules.execution.domain.decision_request import (
    DecisionKind,
    DecisionState,
    answer_request,
    apply_answer,
)
from skm.modules.execution.domain.deviation import accept_deviation
from skm.modules.execution.domain.ids import DecisionRequestId
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.generated.commands import (
    AnswerDecisionRequest,
    CancelRun,
    ReconfigureRun,
    SkipTask,
)
from skm.modules.execution.generated.results import AnswerDecisionRequestResult
from skm.modules.execution.ports import (
    AcceptanceRepository,
    DecisionRepository,
    RunRepository,
    TaskRepository,
)
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import SchemaValidator


def scope(cmd: AnswerDecisionRequest, uow: UnitOfWork) -> ScopeRef | None:
    try:
        request = uow.repo(DecisionRepository).get(DecisionRequestId(cmd.request_id))
    except NotFound:
        return None
    return ScopeRef(ScopeKind.RUN, ScopeId(request.run_id))


def handle(  # noqa: PLR0912, PLR0915 -- owner answer transaction
    cmd: AnswerDecisionRequest, ctx: Any, uow: UnitOfWork
) -> AnswerDecisionRequestResult:
    repo = uow.repo(DecisionRepository)
    observed = repo.get(DecisionRequestId(cmd.request_id))
    if observed.task_id is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "a task-bound wait is required")
    run, task, attempt = lock_task(uow, observed.task_id)
    request = repo.get(DecisionRequestId(cmd.request_id), for_update=True)
    require_permission(uow, ctx, run, "inbox.answer", human=True)
    if request.state is not DecisionState.OPEN:
        raise error_for(ErrorCode.INVALID_TRANSITION, "request is not open")
    if request.revision != cmd.expected_revision:
        raise error_for(ErrorCode.VERSION_CONFLICT, "request revision changed")
    if request.kind in {DecisionKind.APPROVAL, DecisionKind.MANUAL_CHECK}:
        raise error_for(ErrorCode.INVALID_TRANSITION, "this request uses its dedicated authority command")
    if task.status is not TaskStatus.AWAITING_DECISION or attempt is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "the question/owner wait boundary has not committed")
    if request.binding.get("attempt_id") not in (None, str(attempt.id)) or request.binding.get(
        "output_id"
    ) not in (None, str(attempt.current_output_id)):
        raise error_for(ErrorCode.INVALID_TRANSITION, "answer is bound to stale execution inputs")
    current_digest = current_binding_digest(uow, attempt)
    if request.binding.get("input_part_digest") != current_digest:
        raise error_for(ErrorCode.INVALID_TRANSITION, "answer is bound to a stale stage digest")
    answer_doc: Any = plain(cmd.answer)
    option = answer_doc.get("option_id")
    raw_options = request.payload.get("options")
    options = raw_options if isinstance(raw_options, list | tuple) else []
    option_ids = [o.get("id") if isinstance(o, Mapping) else o for o in options]
    if options and option not in option_ids:
        raise error_for(ErrorCode.SCHEMA_INVALID, "answer must select an offered option")
    raw_schema = request.payload.get("answer_schema")
    if raw_schema is not None:
        schema = obj(raw_schema, "payload.answer_schema")
        registry = SchemaRegistry.load_default()
        if not registry.is_valid_schema(schema) or SchemaValidator(schema, registry.registry).issues(
            answer_doc.get("value")
        ):
            raise error_for(ErrorCode.SCHEMA_INVALID, "answer does not satisfy the saved schema")
    if request.payload.get("code") == "INTEGRATION_RECHECK_FAILED" and option == "retry_stage":
        commits: Any = cast("Any", answer_doc.get("value") or {}).get("recheck_commits")
        mounts = texts(request.payload.get("mounts"), "payload.mounts")
        if (
            not isinstance(commits, dict)
            or set(cast("dict[str, Any]", commits)) != set(mounts)
            or not commits
        ):
            raise error_for(ErrorCode.SCHEMA_INVALID, "exact approved recheck commits are required")
    aid = ctx.ids.new_id()
    why = cause("decision_answered", refs=[{"kind": "decision_request", "id": str(request.id)}])
    pending = prepare_trigger(uow, ctx, attempt, aid, why)
    if option in {"raise_budget", "resume_run", "cancel_run", "skip", "new_attempt", "retry_stage", "fail"}:
        require_permission(uow, ctx, run, "run.control", human=True)
    if option in {"accept_deviation", "accept_rejection"}:
        require_permission(uow, ctx, run, "deviation.accept", human=True)

        deviation = accept_deviation(
            task,
            actor=ctx.actor,
            scope="attention_verdict",
            criterion_id=None,
            finding_id=None,
            reason=cmd.rationale or answer_doc.get("text") or "Owner accepted deviation",
            deviation_id=ctx.ids.new_id(),
            now=ctx.clock.now(),
        )
        uow.repo(AcceptanceRepository).add_deviation(deviation)
    if option == "raise_budget":
        payload: Any = answer_doc.get("value") or {}
        key = (
            payload.get("key")
            or f"budgets.{request.payload.get('scope', 'run')}.max_{request.payload.get('dimension', 'usd')}"
        )
        reconfigure(
            ReconfigureRun(
                run.id,
                run.row_version,
                {key: payload.get("amount")},
                cmd.rationale or "Owner budget decision",
            ),
            ctx,
            uow,
        )
        run = uow.repo(RunRepository).get(run.id)
    if option in {"raise_budget", "resume_run"} and request.payload.get("reason") == "unmetered":
        cleared = replace(run, unmetered_at=None, row_version=run.row_version + 1)
        uow.repo(RunRepository).save(cleared, expected_version=run.row_version)
        run = cleared
    answered, answer = answer_request(
        request,
        answered_by={"kind": "owner", "principal_id": str(ctx.actor.principal_id)},
        actor=ctx.actor,
        value=answer_doc,
        authority=AuthorityEnvelope("owner", tuple(request.gate_categories), None),
        expected_revision=cmd.expected_revision,
        answer_id=aid,
        now=ctx.clock.now(),
    )
    repo.add_answer(answer)
    applied = apply_answer(answered, answer, binding=dict(request.binding))
    repo.save(applied)
    record = None
    if request.kind is DecisionKind.QUESTION:
        record = make_decision_record(
            applied,
            answer,
            question_kind=str(request.payload.get("kind", "decision")),
            record_id=ctx.ids.new_id(),
            project_id=run.project_id,
            rationale=cmd.rationale or "",
            selected_option=option,
            now=ctx.clock.now(),
        )
    if record is not None:
        repo.supersede_records(run.project_id, record.question_key)
        repo.add_record(record)
    emit(
        uow,
        run,
        "decision-answered",
        {
            "request_id": str(request.id),
            "kind": request.kind.value,
            "answered_by_kind": "owner",
            "record_as_plan_decision": record is not None,
            **({"rationale": cmd.rationale} if cmd.rationale else {}),
        },
        why,
    )
    if option == "cancel_run":
        cancel(CancelRun(run.id, cmd.rationale or "Owner cancelled"), ctx, uow)
        kind = "cancelled"
    elif option == "skip":
        skip(SkipTask(task.id, cmd.rationale or "Owner skipped task"), ctx, uow)
        kind = "skipped"
    else:
        kind = commit_trigger(uow, ctx, run, pending)
    return AnswerDecisionRequestResult(
        request.id,
        applied.state.value,
        uow.repo(TaskRepository).get(task.id).status.value,
        kind,
        None if record is None else record.id,
    )


SPEC = CommandSpec(
    name="execution.answer_decision_request",
    dto=AnswerDecisionRequest,
    result=AnswerDecisionRequestResult,
    permission="inbox.answer",
    scope_of=None,
    scope_resolver=scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.HUMAN}),
)
