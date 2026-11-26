"""Pre-stage pause, release and continuation binding survive reconfiguration."""

from typing import Any, cast
from uuid import UUID

import pytest

from contracts.execution.test_worker_protocol import begin, claim, make_case, worker_claim
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject
from skm.modules.execution import public as execution
from skm.modules.execution.generated.commands import PauseRun, ReconfigureRun, ResumeRun
from skm.modules.execution.ports import AttemptRepository, RunRepository, StageRepository, TaskRepository
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import side as side


def test_pause_refuses_before_stage_without_consuming_cursor_and_resume_before_release(side: Any) -> None:
    run, task, attempt, _ = make_case(side)
    claimed = claim(side)
    side.client.dispatch(PauseRun(run.id, "owner pause"))
    refused = begin(side, claimed)
    assert refused["stage_record_id"] is None
    assert refused["refusal"]["code"] == "RUN_NOT_ACTIVE"
    with side.uow(readonly=True) as uow:
        assert not uow.repo(StageRepository).history(attempt.id).entries
        cursor = uow.repo(AttemptRepository).get(attempt.id).continuation
        version = uow.repo(RunRepository).get(run.id).row_version
    with pytest.raises(SkmError):
        side.client.dispatch(ReconfigureRun(run.id, version, {"budgets.run.max_tokens": 2000}, "new budget"))
    side.client.dispatch(ResumeRun(run.id))
    side.worker1_client.dispatch(
        execution.ReleaseAssignment(
            claim=worker_claim(side, claimed), reason="paused", retain_environment=True
        ),
        idempotency_key=f"release:{side.new_id()}",
    )
    with side.uow(readonly=True) as uow:
        assert uow.repo(AttemptRepository).get(attempt.id).continuation == cursor
        assert uow.repo(TaskRepository).get(task.id).status.value == "ready"
    renewed = claim(side)
    assert renewed["attempt_id"] == str(attempt.id)
    assert begin(side, renewed)["stage_record_id"] is not None


def test_release_active_stage_and_discard_live_environment_are_atomic(side: Any) -> None:
    _, _, attempt, _ = make_case(side, env=True)
    claimed = claim(side)
    for retain in (False, True):
        if retain:
            begin(side, claimed)
        with pytest.raises(SkmError) as caught:
            side.worker1_client.dispatch(
                execution.ReleaseAssignment(
                    claim=worker_claim(side, claimed), reason="waiting", retain_environment=retain
                ),
                idempotency_key=f"release:{side.new_id()}",
            )
        assert caught.value.code.value == "INVALID_TRANSITION"
    with side.uow(readonly=True) as uow:
        assert uow.repo(AttemptRepository).get(attempt.id).environment_id is not None


def test_intrinsic_begin_replay_returns_same_stage_without_consuming_new_cursor(side: Any) -> None:
    _, _, attempt, _ = make_case(side)
    claimed = claim(side)
    first = begin(side, claimed)
    assert begin(side, claimed)["stage_record_id"] == first["stage_record_id"]
    with side.uow(readonly=True) as uow:
        assert len(uow.repo(StageRepository).history(attempt.id).entries) == 1
        assert uow.repo(StageRepository).get(UUID(first["stage_record_id"])).state.value == "started"


def test_activity_unions_exact_lesson_versions_and_keeps_lineage_unknown(side: Any, monkeypatch: Any) -> None:
    from dataclasses import replace

    from contracts.execution.test_step_notes import owned_agent
    from skm.modules.context import public as context

    _, _, attempt, _, _, step, _, _, _ = owned_agent(side)
    with side.uow(readonly=True) as uow:
        manifest = context.get_manifest(uow, step.context_manifest_id)
    base = manifest.blocks[0]
    blocks = (
        replace(
            base,
            block_type=context.BlockType.MEMORY,
            source_kind="memory",
            source_ref="knowledge:lesson-a",
            source_version="1",
            content_digest="sha256:" + "1" * 64,
            included=True,
        ),
        replace(
            base,
            block_type=context.BlockType.MEMORY,
            source_kind="memory",
            source_ref="knowledge:lesson-a",
            source_version="2",
            content_digest="sha256:" + "2" * 64,
            included=True,
        ),
        replace(
            base,
            block_type=context.BlockType.MEMORY,
            source_kind="memory",
            source_ref="memory:ordinary",
            source_version="3",
            content_digest="sha256:" + "3" * 64,
            included=True,
        ),
        replace(
            base,
            block_type=context.BlockType.HISTORY,
            source_ref="step:shared-finding",
            source_version="1",
            included=True,
        ),
    )
    monkeypatch.setattr(context, "get_manifest", lambda _uow, _id: replace(manifest, blocks=blocks))
    with side.uow(readonly=True) as uow:
        activity = execution.get_attempt_activity(uow, attempt.id)
    lesson_refs = cast("list[dict[str, str]]", activity["exposed_lesson_refs"])
    assert {x["version"] for x in lesson_refs} == {"1", "2"}
    assert all(x["id"].startswith("knowledge:") for x in lesson_refs)
    assert activity["exposure_coverage"] == "unknown"
    assert len(cast("list[JsonObject]", activity["source_refs"])) == 4


def test_context_request_contains_real_answers_rework_candidate_and_history(  # noqa: PLR0915 -- one complete context-source fixture
    side: Any, monkeypatch: Any
) -> None:
    from dataclasses import replace
    from types import SimpleNamespace

    from contracts.execution.seed_helpers import seed_output, seed_stage, seed_step
    from skm.modules.execution.application import _stage_preparation
    from skm.modules.execution.application._stage_agent_helpers import profile_and_permissions
    from skm.modules.execution.application._worker_protocol import lock_fenced_context
    from skm.modules.execution.application.loaders import require_task_work_policy
    from skm.modules.execution.domain.attempt import AttemptState
    from skm.modules.execution.domain.autonomy import AuthorityEnvelope
    from skm.modules.execution.domain.decision_record import QuestionCategory
    from skm.modules.execution.domain.decision_request import (
        Audience,
        DecisionAnswer,
        DecisionKind,
        DecisionRequest,
        DecisionState,
        question_digest,
        question_key,
    )
    from skm.modules.execution.domain.finding import Finding, FindingState, Severity
    from skm.modules.execution.domain.fix_brief import FixBrief, FixBriefItem
    from skm.modules.execution.domain.review import Freshness, Review, ReviewerKind, ReviewState, Verdict
    from skm.modules.execution.domain.session import Fresh
    from skm.modules.execution.domain.stage_record import StageState
    from skm.modules.execution.domain.step import RoleId, StepState
    from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs
    from skm.modules.execution.ports import DecisionRepository, ReviewRepository
    from skm.modules.runtimes.public import Effort, Operation
    from unit.execution.application._support import context

    run, task, attempt, _ = make_case(
        side, stage_id="execute", stage_type="agent_step", env=True, attempt_no=2
    )
    claimed = claim(side)
    step_id = side.new_id()
    manifest = side.make_final_manifest(step_ref=f"step:{step_id}")
    captured = []
    monkeypatch.setattr(
        _stage_preparation, "assemble_draft", lambda _uow, _gateways, req, **_kw: captured.append(req)
    )
    with side.uow() as uow:
        attempts = uow.repo(AttemptRepository)
        current = attempts.get(attempt.id)
        older = replace(
            current,
            id=side.new_id(),
            attempt_no=1,
            state=AttemptState.ABANDONED,
            continuation=None,
            environment_id=None,
            current_output_id=None,
            finished_at=side.clock.now(),
            end_reason="RETRY_NEW_ATTEMPT",
        )
        attempts.add(older)
        old_output = seed_output(side, uow, older)
        output = seed_output(side, uow, current)
        current = replace(current, current_output_id=output.id)
        attempts.save(current, expected_version=attempts.version(current.id))
        stage = seed_stage(side, uow, current, state=StageState.COMPLETED)
        step = seed_step(
            side,
            uow,
            current,
            stage,
            step_id=step_id,
            manifest_id=manifest,
            state=StepState.SUCCEEDED,
            result={"summary": "Previous bounded implementation"},
        )
        review_id = side.new_id()
        review = Review(
            review_id,
            side.ws,
            run.id,
            task.id,
            current.id,
            output.id,
            1,
            ReviewerKind.AGENT,
            {"step_id": str(step.id)},
            "executor",
            side.workflow_rv_id,
            "full",
            ReviewState.COMPLETED,
            Verdict.RED,
            Freshness.FRESH,
            None,
            "",
            side.clock.now(),
        )
        reviews = uow.repo(ReviewRepository)
        reviews.add(review)
        location: JsonObject = {"mount": "repo", "path": "src/target.py"}
        finding = Finding(
            side.new_id(),
            review.id,
            "F1",
            "fk-" + "2" * 16,
            Severity.MAJOR,
            "high",
            "inspection",
            "logic",
            "Wrong branch",
            "Unexpected result",
            location,
            None,
            review.id,
            FindingState.CONFIRMED,
        )
        reviews.add_findings((finding,))
        brief = FixBrief(
            side.new_id(),
            task.id,
            current.id,
            review.id,
            None,
            (
                FixBriefItem(
                    finding.finding_key,
                    "F1",
                    Severity.MAJOR,
                    "logic",
                    location,
                    "Wrong branch",
                    "Use expected branch",
                    "Unexpected result",
                    "Reproduce",
                ),
            ),
            False,
            side.fv1,
            {},
            "sha256:" + "3" * 64,
        )
        reviews.add_fix_brief(brief)
        payload = {"kind": "decision", "text": "Which branch?", "options": [{"id": "documented"}]}
        request = DecisionRequest(
            side.new_id(),
            side.ws,
            run.id,
            task.id,
            DecisionKind.QUESTION,
            Audience.OWNER,
            QuestionCategory.ARCHITECTURAL,
            frozenset(),
            question_key(task.display_key, payload),
            question_digest(task.display_key, payload),
            1,
            payload,
            None,
            {},
            DecisionState.APPLIED,
            None,
            None,
            side.clock.now(),
        )
        decisions = uow.repo(DecisionRepository)
        decisions.add(request)
        answer = DecisionAnswer(
            side.new_id(),
            request.id,
            {"kind": "owner", "principal_id": str(side.owner.principal_id)},
            {"value": "Use the documented branch"},
            AuthorityEnvelope("owner", (), None),
            side.clock.now(),
        )
        decisions.add_answer(answer)
        decisions.save(replace(request, answer_id=answer.id))
        selected = replace(
            current.continuation.stage,
            input_output_id=output.id,
            feedback_refs=FeedbackRefs(fix_brief_id=brief.id, answer_request_ids=(request.id,)),
        )
        ctx = context(side, uow, run, actor=side.worker1_client._actor)
        fenced = lock_fenced_context(uow, ctx, worker_claim(side, claimed))
        profile_view, _, perms = profile_and_permissions(uow, ctx, fenced, selected, RoleId.EXECUTOR)
        route = SimpleNamespace(
            runtime_id="codex_cli",
            model="gpt-5",
            effort=Effort.HIGH,
            context_window_tokens=128000,
            source="role_routing",
            operation=Operation.BOUNDED_FIX,
            config_mode="isolated",
            self_loads=(),
            degraded=frozenset(),
        )
        _stage_preparation.build_context(
            uow,
            ctx,
            fenced,
            selected,
            side.new_id(),
            RoleId.EXECUTOR,
            profile_view.resource_version_id,
            route,
            perms,
            Fresh("AUTHORITY_CHANGED", True),
        )
        assert (
            require_task_work_policy(uow, task.id).digest
            == captured[0].execution_blocks.work_policy["digest"]
        )
    blocks = captured[0].execution_blocks
    assert blocks.decision_answers[0].answer == answer.value
    assert blocks.decision_answers[0].request_id == str(request.id)
    assert blocks.review_feedback["fix_brief"]["id"] == str(brief.id)
    assert blocks.review_feedback["fix_brief"]["items"][0]["fix"] == "Use expected branch"
    assert blocks.previous_attempt.attempt_no == 1
    assert blocks.previous_attempt.patch_file_version_id == old_output.manifest.patch_file_version_id
    assert blocks.candidate.output_id == output.id
    assert blocks.candidate.diff_file_version_id == output.manifest.patch_file_version_id
    assert blocks.findings_under_review[0]["finding_key"] == finding.finding_key
    assert blocks.history[0].step_ref == f"step:{step.id}"
    assert blocks.history[0].summary == "Previous bounded implementation"
