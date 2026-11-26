"""Invalid results, replay, bounded observations and question notes use one advance."""

from typing import Any

import pytest

from contracts.execution.test_step_notes import owned_agent
from contracts.execution.test_worker_protocol import worker_claim
from skm.kernel.errors import SkmError
from skm.modules.execution import public as execution
from skm.modules.execution.ports import (
    AttemptRepository,
    DecisionRepository,
    ExecutionQueries,
    StageRepository,
    StepRepository,
)
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import side as side


def report(
    side: Any,
    claimed: Any,
    stage: Any,
    step: Any,
    result: Any,
    *,
    key: str | None = None,
    observations: Any = None,
) -> Any:
    command = execution.RecordStageResult(
        claim=worker_claim(side, claimed),
        stage_record_id=str(stage.id),
        outcome_kind="success",
        outcome={"step_id": str(step.id), "role_result": result, "session_ref": "session-1"},
    )
    if observations is not None:
        command["observations"] = observations
    return side.worker1_client.dispatch(command, idempotency_key=key or f"result:{side.new_id()}")


def valid_result() -> dict[str, Any]:
    return {
        "schema": "urn:skm:execution:role-result:executor:v1",
        "status": "done",
        "summary": "Need an answer",
        "changed_paths": [],
        "checks_run": [],
        "open_issues": [],
        "self_check": {"performed": False, "notes": "Awaiting checks"},
    }


@pytest.mark.parametrize(
    ("error_class", "code"),
    [
        ("timeout", "RUNTIME_TIMEOUT"),
        ("transport", "RUNTIME_TRANSPORT"),
        ("authentication", "RUNTIME_AUTH_EXPIRED"),
        ("provider_internal", "RUNTIME_OVERLOADED"),
        ("unrecognised_host_failure", "RUNTIME_FAILURE_UNCLASSIFIED"),
    ],
)
def test_failure_records_canonical_codes_and_retries_transient_errors(
    side: Any, error_class: str, code: str
) -> None:
    from contracts.execution.test_worker_protocol import begin, claim, make_case
    from skm.modules.execution.domain.retry import class_for_code

    make_case(side)
    claimed = claim(side)
    ready = begin(side, claimed)
    result = side.worker1_client.dispatch(
        execution.ReportAttemptFailure(
            claim=worker_claim(side, claimed),
            stage_record_id=ready["stage_record_id"],
            error_class=error_class,
            detail="host failure",
            worktree_dirty=False,
        ),
        idempotency_key=f"failure:{side.new_id()}",
    )
    from uuid import UUID

    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(UUID(ready["stage_record_id"])).error_code == code
    assert class_for_code(code) == ("unknown" if error_class == "unrecognised_host_failure" else error_class)
    if error_class in {"timeout", "transport"}:
        assert result["next"]["kind"] == "run_stage"
        assert result["next"]["mode"] == "retry"


def test_environment_lost_abandons_attempt_and_requests_new_attempt(side: Any) -> None:
    from contracts.execution.test_worker_protocol import begin, claim, make_case
    from skm.modules.execution.ports import AssignmentRepository, TaskRepository

    _, task, attempt, assignment = make_case(side, env=True)
    claimed = claim(side)
    ready = begin(side, claimed)
    result = side.worker1_client.dispatch(
        execution.ReportAttemptFailure(
            claim=worker_claim(side, claimed),
            stage_record_id=ready["stage_record_id"],
            error_class="environment_lost",
            detail="worktree was removed",
            worktree_dirty=False,
        ),
        idempotency_key=f"failure:{side.new_id()}",
    )
    assert result["task_status"] == "ready"
    assert result["next"]["kind"] == "release"
    with side.uow(readonly=True) as uow:
        old = uow.repo(AttemptRepository).get(attempt.id)
        assert old.state.value == "abandoned"
        assert old.continuation is None
        saved = uow.repo(TaskRepository).get(task.id)
        assert saved.current_attempt_id is None
        assert saved.attempt_count == 1  # only the scheduler charges/creates the next attempt
        assert uow.repo(AssignmentRepository).lease(assignment.id) is None


def test_paused_transport_failure_selects_retry_after_release_and_resume(side: Any) -> None:
    from contracts.execution.test_worker_protocol import begin, claim, make_case
    from skm.modules.execution.generated.commands import PauseRun, ResumeRun

    run, _, attempt, _ = make_case(side)
    claimed = claim(side)
    ready = begin(side, claimed)
    side.client.dispatch(PauseRun(run.id, "pause during transport failure"))
    side.worker1_client.dispatch(
        execution.ReportAttemptFailure(
            claim=worker_claim(side, claimed),
            stage_record_id=ready["stage_record_id"],
            error_class="transport",
            detail="connection lost",
            worktree_dirty=False,
        ),
        idempotency_key=f"failure:{side.new_id()}",
    )
    side.worker1_client.dispatch(
        execution.ReleaseAssignment(
            claim=worker_claim(side, claimed), reason="paused", retain_environment=True
        ),
        idempotency_key=f"release:{side.new_id()}",
    )
    side.client.dispatch(ResumeRun(run.id))
    with side.uow(readonly=True) as uow:
        cursor = uow.repo(AttemptRepository).get(attempt.id).continuation
        assert cursor.kind == "stage"
        assert cursor.stage.mode.value == "retry"
        assert cursor.cause.advance_rule == "A4"


def accepted_integration(side: Any) -> Any:
    from dataclasses import replace

    from contracts.execution.seed_helpers import seed_output
    from contracts.execution.test_worker_protocol import make_case
    from skm.modules.execution.domain.acceptance import AcceptanceBasis, AcceptanceDecision
    from skm.modules.execution.domain.review import ReviewClearance
    from skm.modules.execution.ports import AcceptanceRepository

    run, task, attempt, _ = make_case(side, stage_id="integrate", stage_type="integrate", env=True)
    with side.uow() as uow:
        output = seed_output(side, uow, attempt)
        repo = uow.repo(AttemptRepository)
        repo.save(replace(attempt, current_output_id=output.id), expected_version=repo.version(attempt.id))
        uow.repo(AcceptanceRepository).add_decision(
            AcceptanceDecision(
                side.new_id(),
                side.ws,
                run.id,
                task.id,
                attempt.id,
                output.id,
                "accepted",
                side.owner.principal_id,
                AcceptanceBasis.empty(ReviewClearance.WAIVED),
                side.clock.now(),
            )
        )
        uow.commit()
    return run, task, attempt, output


def integration_case(side: Any) -> Any:
    from contracts.execution.test_worker_protocol import begin, claim
    from skm.modules.execution.application._worker_dtos import digest
    from skm.modules.execution.domain.external_effect import EffectKind, EffectState, ExternalEffect
    from skm.modules.execution.ports import EffectRepository

    run, task, attempt, output = accepted_integration(side)
    claimed = claim(side)
    ready = begin(side, claimed)
    request = {
        "repository_id": str(side.repo_id),
        "target_branch": f"skm/integration/{run.id}",
        "before_sha": "1" * 40,
        "after_sha": "2" * 40,
        "tree_sha": "3" * 40,
        "baseline_sha": "1" * 40,
        "output_ids": [str(output.id)],
        "output_digests": [output.manifest_digest],
        "commit_shas": ["2" * 40],
        "assignment_fencing_token": claimed["fencing_token"],
        "slot_fencing_token": 1,
        "writer_epoch_sha": "4" * 40,
    }
    effect_id = side.new_id()
    effect = ExternalEffect(
        effect_id,
        side.ws,
        run.id,
        attempt.id,
        task.id,
        EffectKind.GIT_COMMIT,
        None,
        digest({"effect_id": str(effect_id), "kind": "git_commit", "request": request}),
        request,
        EffectState.EXECUTING,
        None,
        side.clock.now(),
        side.clock.now(),
    )
    with side.uow() as uow:
        uow.repo(EffectRepository).add(effect)
        uow.commit()
    receipt = {
        "ref": "2" * 40,
        "before_sha": request["before_sha"],
        "after_sha": request["after_sha"],
        "tree_sha": request["tree_sha"],
        "commit_shas": request["commit_shas"],
        "target_branch": request["target_branch"],
        "output_ids": request["output_ids"],
        "request_digest": effect.request_digest,
        "writer_epoch_sha": request["writer_epoch_sha"],
        "receipt_ref": f"refs/skm/effects/{effect.id}",
        "receipt_commit_sha": "5" * 40,
        "at": side.clock.now().isoformat(),
    }
    return run, task, attempt, claimed, ready, effect, receipt


@pytest.mark.parametrize(
    "invalid", ["missing", "unknown_effect", "foreign_output", "changed_tree", "changed_ref", "truncated"]
)
def test_integration_success_without_verified_receipt_is_atomic(side: Any, invalid: str) -> None:
    from uuid import UUID

    from skm.modules.execution.ports import AcceptanceRepository, EffectRepository

    _, task, _, claimed, ready, effect, receipt = integration_case(side)
    with side.uow(readonly=True) as uow:
        decisions = uow.repo(AcceptanceRepository).decisions_for_task(task.id)
    if invalid == "unknown_effect":
        receipt["request_digest"] = "sha256:" + "0" * 64
    elif invalid == "foreign_output":
        receipt["output_ids"] = [str(side.new_id())]
    elif invalid == "changed_tree":
        receipt["tree_sha"] = "6" * 40
    elif invalid == "changed_ref":
        receipt["ref"] = "6" * 40
    elif invalid == "truncated":
        del receipt["receipt_commit_sha"]
    with pytest.raises(SkmError) as caught:
        side.worker1_client.dispatch(
            execution.RecordStageResult(
                claim=worker_claim(side, claimed),
                stage_record_id=ready["stage_record_id"],
                outcome_kind="success",
                outcome={"integration_receipts": [] if invalid == "missing" else [receipt]},
            ),
            idempotency_key=f"result:{side.new_id()}",
        )
    if invalid == "changed_ref":
        assert caught.value.code.value == "INVALID_REFERENCE"
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(UUID(ready["stage_record_id"])).finished_at is None
        assert uow.repo(EffectRepository).get(effect.id).receipt is None
        assert uow.repo(AcceptanceRepository).decisions_for_task(task.id) == decisions


def test_integration_saves_complete_receipt_and_emits_once(side: Any) -> None:
    from skm.modules.execution.generated.commands import PauseRun
    from skm.modules.execution.ports import EffectRepository

    run, _, _, claimed, ready, effect, receipt = integration_case(side)
    side.client.dispatch(PauseRun(run.id, "pause before next stage"))
    command = execution.RecordStageResult(
        claim=worker_claim(side, claimed),
        stage_record_id=ready["stage_record_id"],
        outcome_kind="success",
        outcome={"integration_receipts": [receipt]},
    )
    key = f"result:{side.new_id()}"
    first = side.worker1_client.dispatch(command, idempotency_key=key)
    assert side.worker1_client.dispatch(command, idempotency_key=key) == first
    with side.uow(readonly=True) as uow:
        saved = uow.repo(EffectRepository).get(effect.id)
        assert saved.state.value == "succeeded"
        assert saved.receipt == receipt
        queries = uow.repo(ExecutionQueries)
        events = queries.run_events(run.id, 0, queries.head_run_seq(run.id), 500)
        completed = [e for e in events if e["event_type"].endswith("integration-completed:v1")]
        assert len(completed) == 1
        assert completed[0]["payload"]["integration_receipts"] == [receipt]


@pytest.mark.parametrize("unknown", [False, True])
def test_terminal_budget_overrun_or_unknown_usage_commits_pause(side: Any, unknown: bool) -> None:
    from decimal import Decimal

    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension, BudgetReservation
    from skm.modules.execution.domain.stage_record import mark_runtime_started
    from skm.modules.execution.ports import BudgetRepository, RunRepository
    from unit.execution.application._support import set_setting

    if unknown:
        set_setting(side, "budgets.unknown_usage_policy", "block")
    run, task, _, claimed, stage, step, _, _, _ = owned_agent(side)
    with side.uow() as uow:
        budget = uow.repo(BudgetRepository)
        account = BudgetAccount(
            side.new_id(), run.id, "run", None, BudgetDimension.TOKENS, Decimal(10), Decimal(0), Decimal(0), 1
        )
        budget.add_accounts((account,))
        assert budget.reserve((account.id,), Decimal(5))
        budget.add_reservation(
            BudgetReservation(
                side.new_id(),
                (account.id,),
                BudgetDimension.TOKENS,
                step.id,
                Decimal(5),
                "reserved",
                None,
                side.clock.now(),
                None,
            )
        )
        uow.repo(StageRepository).save(mark_runtime_started(stage, now=side.clock.now()))
        uow.commit()
    command = execution.RecordStageResult(
        claim=worker_claim(side, claimed),
        stage_record_id=str(stage.id),
        outcome_kind="result_invalid",
        outcome={"error_code": "RESULT_INVALID"},
    )
    if not unknown:
        command["usage"] = {
            "input_tokens": 20,
            "output_tokens": 1,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
            "cost_usd_micros": 0,
            "status": "reported",
            "source": "stream:result",
            "subagents": {"used": False, "disclosed": True},
        }
    key = f"result:{side.new_id()}"
    first = side.worker1_client.dispatch(command, idempotency_key=key)
    assert side.worker1_client.dispatch(command, idempotency_key=key) == first
    with side.uow(readonly=True) as uow:
        saved = uow.repo(BudgetRepository).accounts_for(run.id, task.id, BudgetDimension.TOKENS)[0]
        assert saved.reserved == 0
        assert saved.spent == (5 if unknown else 21)
        run = uow.repo(RunRepository).get(run.id)
        assert run.status.value == "paused"
        assert (run.unmetered_at is not None) is unknown
        assert uow.repo(DecisionRepository).open_for_task(task.id)
        assert uow.repo(AttemptRepository).get(step.attempt_id).continuation is not None


def test_integration_approval_creates_normalized_intended_effect_once(side: Any) -> None:
    from uuid import UUID

    from skm.modules.execution.ports import EffectRepository
    from skm.modules.policy.ports import ToolIntentRepository
    from unit.execution.application.test_external_effects import configure_effect_policy, effect_case

    configure_effect_policy(side)
    # Real local writer admission/receipt, checkout binding, proposal and receipt replay.
    case = effect_case(side, kind="git_push", approve=False)
    with side.uow(readonly=True) as uow:
        stage = uow.repo(StageRepository).get(UUID(case.ready["stage_record_id"]))
        effect = uow.repo(EffectRepository).get(UUID(stage.outcome["effect_id"]))
        assert effect.state.value == "intended"
        assert effect.attempt_id == case.attempt_id
        assert effect.receipt is None
        assert effect.intent_id is not None
        intent = uow.repo(ToolIntentRepository).get(effect.intent_id)
        assert effect.request_digest == intent.args_digest
        assert effect.request == intent.normalized_args
        assert uow.repo(DecisionRepository).open_for_task(case.task_id)


def test_result_invalid_selects_same_role_retry_and_receipt_is_once_only(side: Any) -> None:
    run, _, attempt, claimed, stage, step, _, _, _ = owned_agent(side)
    key = f"result:{side.new_id()}"
    first = report(side, claimed, stage, step, {}, key=key)
    assert first["next"]["kind"] == "run_stage"
    assert first["next"]["mode"] == "retry"
    assert report(side, claimed, stage, step, {}, key=key) == first
    with side.uow(readonly=True) as uow:
        saved = uow.repo(StepRepository).get(step.id)
        assert saved.state.value == "failed"
        assert saved.error_code == "RESULT_INVALID"
        assert saved.schema_errors
        cursor = uow.repo(AttemptRepository).get(attempt.id).continuation
        assert cursor.stage.feedback_refs.schema_errors_step_id == step.id
        events = uow.repo(ExecutionQueries).run_events(
            run.id, 0, uow.repo(ExecutionQueries).head_run_seq(run.id), 500
        )
        assert sum(e.get("event_type", "").endswith("stage-completed:v1") for e in events) == 1


@pytest.mark.parametrize("target", ["foreign", "duplicate", "oversize"])
def test_observation_precheck_rolls_back_all_terminal_writes(side: Any, target: str) -> None:
    _, _, _, _claimed, stage, step, _, _, _ = owned_agent(side)
    step_id = str(side.new_id()) if target == "foreign" else str(step.id)
    import json
    from pathlib import Path

    observation = json.loads(
        (
            Path(__file__).resolve().parents[4]
            / "tests/fixtures/corpus/examples/runtimes/observation-minimal.json"
        ).read_text()
    )
    observation["request_id"] = step_id
    if target == "oversize":
        observation["padding"] = "x" * 17000
    items = [{"step_id": step_id, "observation": observation}]
    if target == "duplicate":
        items *= 2
    # Direct handler precheck isolates membership/cap behavior from wire schema rejection.
    from skm.modules.execution.application._worker_events import precheck_observations

    with pytest.raises(SkmError):
        precheck_observations((step,), items)
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id).finished_at is None
        assert uow.repo(StepRepository).get(step.id).finished_at is None


def test_question_note_is_deferred_until_terminal_advance(side: Any) -> None:
    _, task, _, claimed, stage, step, runtime, _, _ = owned_agent(side)
    runtime.dispatch(
        execution.RecordStepNote(
            step_id=str(step.id),
            kind="question",
            text="Which API contract should be used?",
            options=[{"id": "safe", "text": "Use the documented API"}],
            urgency="blocking",
        ),
        idempotency_key=f"note:{side.new_id()}",
    )
    with side.uow(readonly=True) as uow:
        assert not uow.repo(DecisionRepository).open_for_task(task.id)
    result = valid_result()
    result["self_check"] = {"performed": False, "notes": "Blocked by the contract question"}
    report(side, claimed, stage, step, result)
    with side.uow(readonly=True) as uow:
        assert uow.repo(DecisionRepository).open_for_task(task.id)


def test_raw_result_semantic_upgrade_rolls_back_evidence_and_terminal_state(side: Any) -> None:
    import json

    _, _, _, claimed, stage, step, _, _, _ = owned_agent(side)
    repaired = valid_result()
    raw = {**repaired, "status": "blocked"}
    data = json.dumps(raw).encode()
    staged = side.client.upload_blob(side.ws, (data,), size=len(data), media_type="application/json")
    command = execution.RecordStageResult(
        claim=worker_claim(side, claimed),
        stage_record_id=str(stage.id),
        outcome_kind="success",
        outcome={"step_id": str(step.id), "role_result": repaired, "repairs": ["status changed"]},
        evidence=[
            {
                "owner": "step",
                "owner_id": str(step.id),
                "role": "raw_result",
                "staged_blob": staged.to_json(),
                "filename": "raw-result.json",
                "media_type": "application/json",
            }
        ],
    )
    with pytest.raises(SkmError) as caught:
        side.worker1_client.dispatch(command, idempotency_key=f"result:{side.new_id()}")
    assert caught.value.code.value == "REPAIR_SEMANTIC_DRIFT", repr(caught.value.__cause__)
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id).finished_at is None
        assert uow.repo(StepRepository).get(step.id).raw_result_file_version_id is None


def test_observation_is_neutral_and_replay_never_emits_again(side: Any) -> None:
    import json
    from pathlib import Path

    run, _, _, claimed, stage, step, _, _, _ = owned_agent(side)
    observation = json.loads(
        (
            Path(__file__).resolve().parents[4]
            / "tests/fixtures/corpus/examples/runtimes/observation-minimal.json"
        ).read_text()
    )
    observation["request_id"] = str(step.id)
    observation["binding"]["provider_reported_model"] = "provider-claim"
    observation["binding"]["model_source"] = "provider_stream"
    command = execution.RecordStageResult(
        claim=worker_claim(side, claimed),
        stage_record_id=str(stage.id),
        outcome_kind="result_invalid",
        outcome={"error_code": "RESULT_INVALID"},
        observations=[{"step_id": str(step.id), "observation": observation}],
    )
    key = f"result:{side.new_id()}"
    first = side.worker1_client.dispatch(command, idempotency_key=key)
    assert side.worker1_client.dispatch(command, idempotency_key=key) == first
    with side.uow(readonly=True) as uow:
        saved = uow.repo(StepRepository).get(step.id)
        assert saved.model == "gpt-5"
        assert saved.runtime_observation["binding"]["provider_reported_model"] == "provider-claim"
        head = uow.repo(ExecutionQueries).head_run_seq(run.id)
        events = uow.repo(ExecutionQueries).run_events(run.id, 0, head, 500)
        assert sum(e["event_type"].endswith("step-observation-recorded:v1") for e in events) == 1
    with pytest.raises(SkmError):
        side.worker1_client.dispatch(command, idempotency_key=f"late:{side.new_id()}")
    with side.uow(readonly=True) as uow:
        assert uow.repo(ExecutionQueries).head_run_seq(run.id) == head
