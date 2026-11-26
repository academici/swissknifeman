"""Reconstruct advance inputs exclusively from a run's frozen contract and overlays."""

from __future__ import annotations

from typing import Any, cast

from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._adhoc_spec import load_run_workflow
from skm.modules.execution.application._json_reads import optional_text
from skm.modules.execution.application._plain import plain
from skm.modules.execution.application._primitives import attempts_for_run
from skm.modules.execution.application._start_inputs import policy_from_values
from skm.modules.execution.application.loaders import load_effective_bundle
from skm.modules.execution.application.stages.gate_facts import check_definitions, enrich
from skm.modules.execution.domain.budget import BudgetDimension
from skm.modules.execution.domain.ids import DecisionRequestId
from skm.modules.execution.domain.manual_verdict import current_verdict
from skm.modules.execution.domain.task import TaskKind
from skm.modules.execution.domain.workflow.actions import DecisionFact, TaskState
from skm.modules.execution.domain.workflow.history import StageHistory
from skm.modules.execution.ports import (
    AttemptRepository,
    BudgetRepository,
    CheckRepository,
    DecisionRepository,
    OutputRepository,
    ReviewRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)
from skm.modules.planning import public as planning


def effective_values(uow: UnitOfWork, run_id: Any) -> tuple[Any, dict[str, Any]]:
    loaded = load_effective_bundle(uow, run_id)
    snapshot: Any = loaded.effective_snapshot
    values: dict[str, Any] = dict(snapshot.get("values", snapshot))
    for overlay in loaded.reconfigurations:
        values.update(overlay.changes)
    return loaded, values


def _research_flags(uow: UnitOfWork, run: Any, task: Any, policy: dict[str, Any]) -> frozenset[str]:
    if policy.get("research_policy", "conditional") != "conditional" or task.kind not in {
        TaskKind.ITEM,
        TaskKind.ITEM_GATE,
        TaskKind.UNIT,
    }:
        return frozenset()
    spec = planning.get_revision_specification(uow, run.revision_id)
    if task.kind is TaskKind.UNIT:
        item_key = task.display_key.partition("/")[0]
        item = next((item for item in spec.items if item.key == item_key), None)
    else:
        item = next((item for item in spec.items if item.id == task.spec_entity_id), None)
    if item is not None and item.research is not None and item.research.need in {"required", "optional"}:
        return frozenset({"research"})
    return frozenset()


def load_state(uow: UnitOfWork, task_id: Any) -> tuple[Any, Any]:
    task = uow.repo(TaskRepository).get(task_id)
    run = uow.repo(RunRepository).get(task.run_id)
    attempt = (
        None if task.current_attempt_id is None else uow.repo(AttemptRepository).get(task.current_attempt_id)
    )
    _loaded, values = effective_values(uow, run.id)
    policy = policy_from_values(values)
    checks = ()
    output = (
        None
        if attempt is None or attempt.current_output_id is None
        else uow.repo(OutputRepository).get(attempt.current_output_id)
    )
    if output is not None:
        checks = uow.repo(CheckRepository).for_output(output.id)
    manual = {
        c.id: head
        for c in checks
        if (head := current_verdict(uow.repo(CheckRepository).verdicts(c.id))) is not None
    }
    requests = uow.repo(DecisionRepository).open_for_task(task.id)
    facts: list[Any] = []
    cursor = None if attempt is None else attempt.continuation
    refs = (
        []
        if cursor is None
        else [ref for trigger in cursor.triggers for ref in trigger.cause.refs]
        if cursor.kind == "advance"
        else list(cursor.cause.refs)
    )
    history = uow.repo(StageRepository).history(attempt.id) if attempt else StageHistory(())
    for ref in refs:
        if ref.kind != "decision_request":
            continue
        request = uow.repo(DecisionRepository).get(DecisionRequestId(ref.id))
        answers = uow.repo(DecisionRepository).answers_for(request.id)
        answer = next((a for a in answers if a.id == request.answer_id), None)
        if answer is None and request.state.value == "applied" and request.payload.get("deviation_id"):
            facts.append(
                DecisionFact(
                    request.id,
                    "accept_deviation",
                    None,
                    optional_text(request.payload.get("code"), "payload.code"),
                    deviation_recorded=True,
                )
            )
        if answer is not None:
            answer_value: Any = plain(answer.value)
            option = answer_value.get("option_id", "answer")
            if request.kind.value == "question" and option not in {
                "retry_stage",
                "new_attempt",
                "accept_deviation",
                "accept_rejection",
                "skip",
                "fail",
                "raise_budget",
            }:
                option = "answer"
            facts.append(
                DecisionFact(
                    request.id,
                    option,
                    answer_value.get("value"),
                    optional_text(request.payload.get("code"), "payload.code"),
                    raise_limit=option == "raise_budget",
                    deviation_recorded=option in {"accept_deviation", "accept_rejection"},
                    reconfigured=option == "raise_budget",
                )
            )
    budget_accounts = [
        account
        for dim in BudgetDimension
        for account in uow.repo(BudgetRepository).accounts_for(run.id, task.id, dim)
    ]
    budget = {
        "unmetered": run.unmetered_at is not None,
        "accounts": [
            {
                "scope": a.scope,
                "dimension": a.dimension.value,
                "limit": None if a.limit_value is None else str(a.limit_value),
                "spent": str(a.spent),
                "reserved": str(a.reserved),
            }
            for a in budget_accounts
        ],
    }

    state = TaskState(
        run,
        task,
        attempt,
        policy,
        history,
        output,
        checks,
        manual,
        uow.repo(ReviewRepository).for_task(task.id),
        uow.repo(ReviewRepository).findings_for_task(task.id),
        requests,
        cast("Any", budget),
        None,
        0,
        None,
        route_flags=_research_flags(uow, run, task, policy),
        decisions=tuple(facts),
        run_retries_used=sum(
            entry.record.mode.value == "retry"
            for owner in attempts_for_run(uow, run.id)
            for entry in uow.repo(StageRepository).history(owner.id).entries
        ),
        rerun_checks_declared=any(
            check.rerun_after_integration for check in check_definitions(uow, run, task)
        ),
    )
    return enrich(uow, state), load_run_workflow(uow, run, task)
