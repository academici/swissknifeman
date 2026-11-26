"""Review analytics over the real query bus and repository contracts."""

from dataclasses import replace
from typing import TYPE_CHECKING

from skm.modules.execution.domain.finding import Finding, FindingState, Severity
from skm.modules.execution.domain.ids import FindingId, ReviewId
from skm.modules.execution.domain.review import Freshness, Review, ReviewerKind, ReviewState, Verdict
from skm.modules.execution.domain.step import RoleId, StepState
from skm.modules.execution.ports import ReviewRepository, StepRepository
from skm.modules.execution.public import GetReviewRoi
from skm.modules.runtimes.public import SubagentUsage, UsageReport, UsageStatus

from .event_helpers import make_runtime_obs
from .harness import ask
from .seed_helpers import seed_attempt, seed_output, seed_run, seed_stage, seed_step, seed_task

if TYPE_CHECKING:
    from .harness import ExecSide


def test_review_roi_counts_distinct_findings_and_only_measured_reviewer_steps(exec_side: "ExecSide") -> None:
    side = exec_side
    manifest = side.make_final_manifest()
    with side.uow() as uow:
        run = seed_run(side, uow)
        empty_run = seed_run(side, uow)
        task = seed_task(side, uow, run.id)
        attempt = seed_attempt(side, uow, run.id, task.id)
        stage = seed_stage(side, uow, attempt)
        step = seed_step(side, uow, attempt, stage, manifest_id=manifest, role=RoleId.REVIEWER)
        failed = seed_step(side, uow, attempt, stage, manifest_id=manifest, role=RoleId.REVIEWER, seq=2)
        executor = seed_step(side, uow, attempt, stage, manifest_id=manifest, seq=3)
        seed_step(side, uow, attempt, stage, manifest_id=manifest, role=RoleId.REVIEWER, seq=4)
        usage = UsageReport(
            1, 2, None, None, None, 1234, UsageStatus.REPORTED, "provider", SubagentUsage(None, False)
        )
        step_repo = uow.repo(StepRepository)
        now = side.clock.now()
        step_repo.save(
            replace(
                step,
                state=StepState.SUCCEEDED,
                finished_at=now,
                usage=usage,
                runtime_observation=make_runtime_obs(side, step.id),
            )
        )
        step_repo.save(
            replace(
                failed,
                state=StepState.FAILED,
                finished_at=now,
                usage=replace(usage, status=UsageStatus.ESTIMATED),
            )
        )
        step_repo.save(replace(executor, state=StepState.SUCCEEDED, finished_at=now, usage=usage))
        output = seed_output(side, uow, attempt)
        next_output = seed_output(side, uow, attempt, seq=2)
        agent = Review(
            id=ReviewId(side.new_id()),
            workspace_id=side.ws,
            run_id=run.id,
            task_id=task.id,
            attempt_id=attempt.id,
            output_id=output.id,
            round_no=1,
            reviewer_kind=ReviewerKind.AGENT,
            reviewer_ref={"step_id": str(step.id)},
            profile_key="reviewer",
            profile_version_id=side.workflow_rv_id,
            audit_scope="full",
            state=ReviewState.COMPLETED,
            verdict=Verdict.RED,
            freshness=Freshness.FRESH,
            base_output_id=None,
            residual_risk="",
            completed_at=now,
        )
        human = replace(
            agent,
            id=ReviewId(side.new_id()),
            output_id=next_output.id,
            round_no=2,
            reviewer_kind=ReviewerKind.HUMAN,
            reviewer_ref={"principal_id": str(side.owner.principal_id)},
            verdict=Verdict.GREEN,
            base_output_id=output.id,
        )
        repo = uow.repo(ReviewRepository)
        repo.add(agent)
        repo.add(human)
        finding = Finding(
            id=FindingId(side.new_id()),
            review_id=agent.id,
            local_id="F1",
            finding_key="fk-5555555555555555",
            severity=Severity.MAJOR,
            confidence="high",
            basis="correctness",
            category="correctness",
            message="private-review-message",
            failure_scenario="edge case",
            location={"path": "src/target.py"},
            reproduction=None,
            first_seen_review_id=agent.id,
            state=FindingState.OPEN,
        )
        repo.add_findings(
            (
                finding,
                replace(
                    finding,
                    id=FindingId(side.new_id()),
                    review_id=human.id,
                    state=FindingState.RESOLVED,
                ),
            )
        )
        uow.commit()

    document = ask(side.client, GetReviewRoi(run.id)).to_json()
    side.app.schemas.require_valid("urn:skm:execution:view:get-review-roi:v1", document)
    assert document == {
        "run_id": str(run.id),
        "completed_agent_reviews": 1,
        "completed_human_reviews": 1,
        "unique_findings": 1,
        "resolved_findings": 1,
        "rejected_findings": 0,
        "finished_reviewer_steps": 2,
        "priced_reviewer_steps": 1,
        "observed_cost_usd": "0.001234",
        "timed_reviewer_steps": 1,
        "observed_duration_ms": 850,
    }
    empty = ask(side.client, GetReviewRoi(empty_run.id))
    assert empty.completed_agent_reviews == empty.unique_findings == empty.finished_reviewer_steps == 0
    assert empty.observed_cost_usd is None
    assert empty.observed_duration_ms is None
