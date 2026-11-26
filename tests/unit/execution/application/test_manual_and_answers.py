"""Human inputs require the committed wait and retain independent corrections while paused."""

from typing import Any

import pytest

from skm.kernel.errors import SkmError
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.generated.commands import (
    AnswerDecisionRequest,
    AnswerDecisionRequestAnswer,
    RecordManualVerdict,
)
from skm.modules.execution.ports import AttemptRepository, CheckRepository, DecisionRepository

from ._support import _shared_side as _shared_side
from ._support import decision_case, manual_case
from ._support import side as side


def test_manual_pass_then_fail_is_append_only_and_deferred_during_pause(side: Any) -> None:
    _run, _task, attempt, check = manual_case(side)
    first = side.client.dispatch(RecordManualVerdict(check.id, "pass", "verified"))
    second = side.client.dispatch(RecordManualVerdict(check.id, "fail", "correction", first.verdict_id))
    with side.uow(readonly=True) as uow:
        assert len(uow.repo(CheckRepository).verdicts(check.id)) == 2
        assert uow.repo(CheckRepository).get(check.id).state.value == "failed"
        cursor = uow.repo(AttemptRepository).get(attempt.id).continuation
        assert cursor.kind == "advance"
        assert len(cursor.triggers) == 2
        assert first.next_action_kind == second.next_action_kind == "deferred"


def test_premature_manual_pass_and_wrong_supersedes_are_rejected_before_mutation(side: Any) -> None:
    _, _, _, check = manual_case(side, status=TaskStatus.CHECKING)
    with pytest.raises(SkmError):
        side.client.dispatch(RecordManualVerdict(check.id, "pass", "premature"))
    with side.uow(readonly=True) as uow:
        assert not uow.repo(CheckRepository).verdicts(check.id)


def test_foreign_verifier_and_nonhuman_owner_answer_are_rejected(side: Any) -> None:
    _, _, _, check = manual_case(side)
    with pytest.raises(SkmError):
        side.viewer_client.dispatch(RecordManualVerdict(check.id, "pass", "foreign"))
    _, _, _, request = decision_case(side)
    with pytest.raises(SkmError):
        side.worker1_client.dispatch(
            AnswerDecisionRequest(request.id, AnswerDecisionRequestAnswer(option_id="continue"), 1)
        )


def test_owner_answer_closes_current_request_and_preserves_advance_source_while_paused(side: Any) -> None:
    _, _, attempt, request = decision_case(side)
    answer = side.client.dispatch(
        AnswerDecisionRequest(
            request.id, AnswerDecisionRequestAnswer(option_id="continue"), 1, "owner rationale"
        )
    )
    with side.uow(readonly=True) as uow:
        assert uow.repo(DecisionRepository).get(request.id).state.value == "applied"
        assert answer.decision_record_id is not None
        cursor = uow.repo(AttemptRepository).get(attempt.id).continuation
        assert cursor.kind == "advance"
        assert any(ref.id == request.id for ref in cursor.triggers[0].cause.refs)


@pytest.mark.parametrize("revision", [0, 2])
def test_wrong_request_revision_is_not_answered(side: Any, revision: int) -> None:
    _, _, attempt, request = decision_case(side)
    with pytest.raises(SkmError):
        side.client.dispatch(
            AnswerDecisionRequest(request.id, AnswerDecisionRequestAnswer(option_id="continue"), revision)
        )
    with side.uow(readonly=True) as uow:
        assert uow.repo(DecisionRepository).get(request.id).state.value == "open"
        assert uow.repo(AttemptRepository).get(attempt.id).continuation is None


def test_question_before_c2_wait_boundary_cannot_be_answered(side: Any) -> None:
    _, _, _, request = decision_case(side, status=TaskStatus.EXECUTING)
    with pytest.raises(SkmError):
        side.client.dispatch(
            AnswerDecisionRequest(request.id, AnswerDecisionRequestAnswer(option_id="continue"), 1)
        )


def test_129th_trigger_is_rejected_before_verdict_or_check_mutation(side: Any) -> None:
    from skm.modules.execution.application._events import cause
    from skm.modules.execution.application._primitives import save_attempt
    from skm.modules.execution.application.apply_action import prepare_trigger

    from ._support import context

    run, _task, attempt, check = manual_case(side)
    with side.uow() as uow:
        ctx = context(side, uow, run)
        for _ in range(128):
            attempt = prepare_trigger(uow, ctx, attempt, side.new_id(), cause("manual_verdict"))
        save_attempt(uow, attempt)
        uow.commit()
    with pytest.raises(SkmError):
        side.client.dispatch(RecordManualVerdict(check.id, "pass", "overflow"))
    with side.uow(readonly=True) as uow:
        assert not uow.repo(CheckRepository).verdicts(check.id)
        assert uow.repo(CheckRepository).get(check.id).state.value == "manual_pending"
        assert len(uow.repo(AttemptRepository).get(attempt.id).continuation.triggers) == 128


@pytest.mark.parametrize("selected", [False, True])
def test_manual_amendment_cannot_change_active_or_selected_stage(side: Any, selected: bool) -> None:
    from dataclasses import replace

    from skm.modules.execution.application._primitives import save_attempt
    from skm.modules.execution.domain.stage_record import StageState

    from ._support import seed_stage, seeded

    _run, _task, attempt, check = manual_case(side)
    other = seeded(side, cursor=True)[2] if selected else None
    with side.uow() as uow:
        if selected:
            assert other is not None
            save_attempt(uow, replace(attempt, continuation=other.continuation))
        else:
            seed_stage(side, uow, attempt, state=StageState.RUNNING)
        uow.commit()
    with pytest.raises(SkmError):
        side.client.dispatch(RecordManualVerdict(check.id, "pass", "cannot amend"))
    with side.uow(readonly=True) as uow:
        assert not uow.repo(CheckRepository).verdicts(check.id)


def test_owner_answer_rejects_changed_stage_digest(side: Any) -> None:
    from skm.modules.execution.domain.stage_record import StageState

    from ._support import seed_stage

    _run, _task, attempt, request = decision_case(side)
    with side.uow() as uow:
        seed_stage(side, uow, attempt, state=StageState.COMPLETED)
        uow.commit()
    with pytest.raises(SkmError):
        side.client.dispatch(
            AnswerDecisionRequest(request.id, AnswerDecisionRequestAnswer(option_id="continue"), 1)
        )
    with side.uow(readonly=True) as uow:
        assert not uow.repo(DecisionRepository).answers_for(request.id)


def test_human_gate_creates_one_bound_request_and_never_answers_it(side: Any) -> None:
    from skm.modules.execution.application._state import load_state
    from skm.modules.execution.application.stages.human_gate import decide

    from ._support import context

    run, task, _attempt, check = manual_case(side)
    with side.uow() as uow:
        state, _ = load_state(uow, task.id)
        for _ in range(2):
            assert decide(state, context(side, uow, run), uow).kind.value == "manual_pending"
        requests = uow.repo(DecisionRepository).open_for_task(task.id)
        assert len(requests) == 1
        assert requests[0].payload["check_execution_id"] == str(check.id)
        assert not uow.repo(DecisionRepository).answers_for(requests[0].id)
        uow.commit()


def prepare_manual_rework(side: Any):
    from skm.modules.execution.application._state import load_state
    from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageState

    from ._support import seed_stage

    run, task, attempt, check = manual_case(side)
    with side.uow() as uow:
        _, workflow = load_state(uow, task.id)
        definition = next(stage for stage in workflow.stages if stage.type.value == "run_checks")
        seed_stage(
            side,
            uow,
            attempt,
            stage_id=definition.id,
            stage_type="run_checks",
            state=StageState.COMPLETED,
            outcome_kind=StageOutcomeKind.MANUAL_PENDING,
        )
        uow.commit()
    return run, task, attempt, check


@pytest.mark.parametrize("paused", [False, True])
@pytest.mark.parametrize("long_note", [False, True])
def test_manual_failure_retains_real_fix_brief_artifact_and_selects_rework(
    side: Any, paused: bool, long_note: bool, monkeypatch: pytest.MonkeyPatch
) -> None:

    from skm.modules.artifacts import public as artifacts
    from skm.modules.execution.domain.workflow.stage_inputs import StageMode
    from skm.modules.execution.generated.commands import ResumeRun
    from skm.modules.execution.ports import (
        EvidenceBindingRepository,
        ExecutionQueries,
        ReviewRepository,
        TaskRepository,
    )

    run, task, attempt, check = prepare_manual_rework(side)
    recorded_stages = []
    native_record = artifacts.record_staged_blob

    def record(*args, **kwargs):
        from datetime import timedelta

        side.clock.advance(timedelta(microseconds=1))
        result = native_record(*args, **kwargs)
        recorded_stages.append(result)
        return result

    monkeypatch.setattr(artifacts, "record_staged_blob", record)
    note = "Expected response 200; the manual verifier observed response 500."
    if long_note:
        note = "\n".join(f"Observation {i}: the documented response is incorrect." for i in range(60))
    if not paused:
        side.client.dispatch(ResumeRun(run.id))
    command = RecordManualVerdict(check.id, "fail", note)
    key = side.client.new_idempotency_key()
    verdict = side.client.dispatch(command, idempotency_key=key)
    if paused:
        with side.uow(readonly=True) as uow:
            assert uow.repo(TaskRepository).get(task.id).status is TaskStatus.MANUAL_PENDING
            assert not uow.repo(EvidenceBindingRepository).for_owner("check_execution", check.id)
        assert not recorded_stages
        side.client.dispatch(ResumeRun(run.id))
    else:
        assert verdict.task_status == "rework_required"
    assert side.client.dispatch(command, idempotency_key=key) == verdict
    assert len(recorded_stages) == 1
    with side.uow() as uow:
        current = uow.repo(TaskRepository).get(task.id)
        assert current.status is TaskStatus.REWORK_REQUIRED
        assert current.current_attempt_id == attempt.id
        assert current.check_fix_rounds == 1
        selected = uow.repo(AttemptRepository).get(attempt.id).continuation
        assert selected.kind == "stage"
        assert selected.stage.mode is StageMode.REWORK
        brief = uow.repo(ReviewRepository).get_fix_brief(selected.stage.feedback_refs.fix_brief_id)
        assert brief.source_review_id is None
        assert brief.source_check_round == check.round_no
        assert len(brief.checks) == 1
        assert brief.checks[0].check_key == check.check_key
        report_id = brief.full_report_file_version_id
        assert report_id is not None
        binding = uow.repo(EvidenceBindingRepository).for_owner("check_execution", check.id)
        assert binding == ((report_id, artifacts.BindingRole.REPORT),)
        assert (report_id, artifacts.BindingRole.EVIDENCE) in uow.repo(EvidenceBindingRepository).for_owner(
            "attempt", attempt.id
        )
        assert_manual_report_artifact(
            uow,
            brief,
            {
                "workspace_id": side.ws,
                "verdict_id": verdict.verdict_id,
                "check_id": check.id,
                "note": note,
            },
            recorded_stages[0],
        )
        assert brief.truncated is long_note
        if long_note:
            assert f"file_version:{report_id}" in brief.checks[0].tail
        else:
            assert brief.checks[0].tail == note
        query = uow.repo(ExecutionQueries)
        events = query.run_events(run.id, 0, query.head_run_seq(run.id), 100)
        rework = [
            e["payload"]
            for e in events
            if e["event_type"] == "urn:skm:execution:event:task-rework-required:v1"
        ]
        assert len(rework) == 1
        assert rework[0]["fix_brief_id"] == str(brief.id)


def test_manual_report_registration_failure_rolls_back_verdict_and_bindings(
    side: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skm.kernel.error_codes import ErrorCode
    from skm.kernel.errors import error_for
    from skm.modules.artifacts import public as artifacts
    from skm.modules.execution.generated.commands import ResumeRun
    from skm.modules.execution.ports import EvidenceBindingRepository, TaskRepository

    run, task, _attempt, check = prepare_manual_rework(side)
    side.client.dispatch(ResumeRun(run.id))
    before = side.client.ask(artifacts.ListFiles.from_json({"workspace_id": str(side.ws)}))
    register = artifacts.register_file_version

    def fail(*args, **kwargs):
        register(*args, **kwargs)
        raise error_for(ErrorCode.BACKEND_UNAVAILABLE, "injected registration failure")

    monkeypatch.setattr(artifacts, "register_file_version", fail)
    with pytest.raises(SkmError):
        side.client.dispatch(RecordManualVerdict(check.id, "fail", "must roll back with the report"))
    assert side.client.ask(artifacts.ListFiles.from_json({"workspace_id": str(side.ws)})) == before
    with side.uow(readonly=True) as uow:
        assert not uow.repo(CheckRepository).verdicts(check.id)
        assert not uow.repo(EvidenceBindingRepository).for_owner("check_execution", check.id)
        assert uow.repo(CheckRepository).get(check.id).state.value == "manual_pending"
        assert uow.repo(TaskRepository).get(task.id).status is TaskStatus.MANUAL_PENDING


def assert_manual_report_artifact(uow: Any, brief: Any, expected: Any, staged_result: Any) -> None:
    import json

    from skm.modules.artifacts import public as artifacts
    from skm.modules.artifacts.ports import FileVersionRepository, StagedBlobRepository

    report_id = brief.full_report_file_version_id
    ready = artifacts.require_ready_versions(uow, expected["workspace_id"], (report_id,))[0]
    assert ready.detected_media_type == "application/json"
    raw = artifacts.read_text_content(uow, report_id, max_bytes=100000)
    assert raw is not None
    document = json.loads(raw)
    assert document["kind"] == "fix_brief"
    assert document["fix_brief_id"] == str(brief.id)
    assert document["checks"][0]["manual_verdict"]["id"] == str(expected["verdict_id"])
    assert document["checks"][0]["manual_verdict"]["comment"] == expected["note"]
    assert document["checks"][0]["check"]["id"] == str(expected["check_id"])
    file_version = uow.repo(FileVersionRepository).get(report_id)
    assert file_version.source.kind == "generated"
    assert file_version.source.ref == f"fix_brief:{brief.id}"
    staged = uow.repo(StagedBlobRepository).get_for_update(staged_result.staged_blob_id)
    assert staged.consumed_at is not None
    assert staged.consumed_at >= staged.created_at
    assert staged.workspace_id == expected["workspace_id"]
    assert staged.digest.value == ready.digest
    assert staged.size_bytes == len(raw.encode("utf-8"))
