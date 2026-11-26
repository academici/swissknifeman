"""M3 red -> confirm -> fix -> green through real bus/persistence and fake subprocesses."""

import hashlib
import json
from dataclasses import replace
from uuid import UUID

import pytest

from contracts.execution._worker_protocol_support import begin, worker_claim
from skm.adapters.git.commit import GitOutputSealer
from skm.bootstrap.host_services import worker_concurrency, worker_schema_issues
from skm.kernel.errors import SkmError
from skm.modules.artifacts import public as artifacts
from skm.modules.execution import public as execution
from skm.modules.execution.application._worker_dtos import document
from skm.modules.execution.domain.finding import FindingState
from skm.modules.execution.domain.output import manifest_to_json
from skm.modules.execution.domain.review import Freshness, Review, ReviewerKind, ReviewState
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.generated.commands import RecordManualVerdict
from skm.modules.execution.host.stages.agent_review import AgentReviewStage
from skm.modules.execution.host.worker_loop import run
from skm.modules.execution.ports import (
    AttemptRepository,
    CheckRepository,
    EvidenceBindingRepository,
    ExecutionQueries,
    OutputRepository,
    ReviewRepository,
    StepRepository,
    TaskRepository,
)

from ._bus_support import admitted_stage as seed_admitted_stage
from ._bus_support import bus_case, claim_seeded_stage
from ._support import make_host, result_scenario
from .test_worker_loop import documents


def admitted_stage(case, role, *, admission=None):
    with case.side.uow(readonly=True) as uow:
        selected_status = uow.repo(TaskRepository).get(case.task.id).status
    stage, step, draft = seed_admitted_stage(case, role, admission=admission)
    assert step is not None
    if role in {"reviewer", "triager"}:
        # Admission preserves the workflow's reviewing status; it starts no executor work.
        with case.side.uow() as uow:
            repo = uow.repo(TaskRepository)
            task = repo.get(case.task.id)
            repo.save(
                replace(task, status=selected_status, row_version=task.row_version + 1),
                expected_version=task.row_version,
            )
            uow.commit()
    return stage, step, draft


def fake_result(case, tmp_path, monkeypatch, role, result, *, contents=None, review_id=None, seal_fix=None):
    """The subprocess runs in the same checkout later sealed by GitOutputSealer."""
    tmp_path.mkdir()
    scenario = result_scenario(tmp_path, role, result)
    if contents is not None:
        scenario.write_text(
            scenario.read_text().replace(
                "[result]",
                '[[step]]\naction = "write_file"\npath = "src/app.py"\ncontent = '
                + json.dumps(contents)
                + "\n[result]",
            )
        )
    fixture = make_host(
        tmp_path,
        monkeypatch,
        role=role,
        scenario=scenario,
        checkout_root=case.root,
        handler=AgentReviewStage(
            concurrency=worker_concurrency(), validate_result=worker_schema_issues, seal_snapshot=seal_fix
        )
        if role == "reviewer"
        else None,
    )
    if role == "reviewer":
        fixture.client.response["instruction"]["stage_type"] = "agent_review"
        fixture.client.begin["review"] = {
            "review_id": str(review_id),
            "reviewer_with_fix": seal_fix is not None,
        }
    run(fixture.ctx, fixture.request)
    payload = next(c for c, _ in fixture.client.calls if c["operation"] == "record_stage_result")
    assert payload["outcome"].get("role_result") == result, payload
    uploads = {"sha256:" + hashlib.sha256(data).hexdigest(): data for data in fixture.client.uploads}
    for evidence in payload["evidence"]:
        data = uploads[evidence["staged_blob"]["digest"]]
        evidence["staged_blob"] = case.side.client.upload_blob(
            case.side.ws, (data,), size=len(data), media_type=evidence["media_type"]
        ).to_json()
    return payload


def record(case, stage, step, payload, *, output_id=None, review_id=None):
    outcome = {**payload["outcome"], "step_id": str(step.id)}
    if output_id:
        outcome["output_id"] = output_id
    if review_id:
        outcome.update(
            review_id=str(review_id),
            verdict=outcome["role_result"]["verdict"],
            findings=outcome["role_result"]["findings"],
        )
        outcome.pop("session_ref", None)
    return case.side.worker1_client.dispatch(
        execution.RecordStageResult(
            claim=worker_claim(case.side, case.claimed),
            stage_record_id=str(stage.id),
            outcome_kind=payload["outcome_kind"],
            outcome=outcome,
            usage=payload["usage"],
            evidence=[
                {**item, "owner_id": str(step.id) if item["owner"] == "step" else str(review_id)}
                for item in payload.get("evidence", ())
            ],
        ),
        idempotency_key=f"result:{case.side.new_id()}",
    )


def execute(case, tmp_path, monkeypatch, contents):
    stage, step, _ = admitted_stage(case, "executor")
    result = fake_result(case, tmp_path, monkeypatch, "executor", documents()["executor"], contents=contents)
    side = case.side
    with side.uow(readonly=True) as uow:
        previous = uow.repo(OutputRepository).latest(case.attempt.id)
    manifest = GitOutputSealer(case.git, state_dir=tmp_path / "seal").seal(
        case.root,
        attempt_id=str(case.attempt.id),
        output_no=1 if previous is None else previous.seq + 1,
        mount="repo",
        repository_id=side.repo_id,
        baseline=case.baseline,
        write_scope=("src/**",),
        previous=None if previous is None else previous.manifest.mounts[0].head_commit,
    )
    sealed = side.worker1_client.dispatch(
        execution.SealOutput(
            claim=worker_claim(side, case.claimed),
            stage_record_id=str(stage.id),
            step_id=str(step.id),
            source="executor",
            manifest=manifest_to_json(manifest),
        ),
        idempotency_key=f"seal:{side.new_id()}",
    )
    return record(case, stage, step, result, output_id=sealed["output_id"])


def checks(case, instruction):
    side = case.side
    assert instruction["stage_id"] == "checks"
    started = begin(side, {**case.claimed, "instruction": instruction})
    results = [
        {
            **{k: c[k] for k in ("check_execution_id", "check_spec_id")},
            "state": "manual_pending",
            "exit_code": None,
            "summary": "Awaiting human check",
        }
        for c in started["checks"]
    ]
    side.worker1_client.dispatch(
        execution.RecordStageResult(
            claim=worker_claim(side, case.claimed),
            stage_record_id=started["stage_record_id"],
            outcome_kind="manual_pending",
            outcome={"results": results, "round_no": instruction["round_no"]},
        ),
        idempotency_key=f"checks:{side.new_id()}",
    )
    side.worker1_client.dispatch(
        execution.ReleaseAssignment(
            claim=worker_claim(side, case.claimed), reason="waiting", retain_environment=True
        ),
        idempotency_key=f"release:{side.new_id()}",
    )
    for check in results:
        side.client.dispatch(
            RecordManualVerdict(
                UUID(check["check_execution_id"]), "pass", "Verified the candidate before independent review"
            ),
            idempotency_key=f"verdict:{side.new_id()}",
        )
    case.claimed = claim_seeded_stage(side)
    assert case.claimed["attempt_id"] == str(case.attempt.id)
    with side.uow(readonly=True) as uow:
        assert uow.repo(AttemptRepository).get(case.attempt.id).environment_id == case.environment.id
        assert uow.repo(AttemptRepository).get(case.attempt.id).continuation.stage.stage_id == "review"
        output = uow.repo(OutputRepository).latest(case.attempt.id)
        assert all(c.state.value == "passed" for c in uow.repo(CheckRepository).for_output(output.id))


def start_review(case, *, can_fix=False):
    side = case.side
    stage, step, _ = admitted_stage(
        case, "reviewer", admission={"reviewer_with_fix": True} if can_fix else None
    )
    with side.uow() as uow:
        repo = uow.repo(ReviewRepository)
        old = repo.for_task(case.task.id)
        output = uow.repo(OutputRepository).latest(case.attempt.id)
        review = Review(
            side.new_id(),
            side.ws,
            case.run.id,
            case.task.id,
            case.attempt.id,
            output.id,
            len(old) + 1,
            ReviewerKind.AGENT,
            {"step_id": str(step.id)},
            "reviewer",
            side.workflow_rv_id,
            "full",
            ReviewState.STARTED,
            None,
            Freshness.FRESH,
            old[-1].output_id if old else None,
            "",
            None,
        )
        repo.add(review)
        uow.commit()
    return stage, step, review, output


def review(case, tmp_path, monkeypatch, result):
    stage, step, review, _ = start_review(case)
    payload = fake_result(case, tmp_path, monkeypatch, "reviewer", result, review_id=review.id)
    return record(case, stage, step, payload, review_id=review.id)


def seal_review_fix(case, stage, step, output, state_dir):
    side = case.side
    manifest = GitOutputSealer(case.git, state_dir=state_dir).seal(
        case.root,
        attempt_id=str(case.attempt.id),
        output_no=output.seq + 1,
        mount="repo",
        repository_id=side.repo_id,
        baseline=case.baseline,
        write_scope=("src/**",),
        previous=output.manifest.mounts[0].head_commit,
    )
    return side.worker1_client.dispatch(
        execution.SealOutput(
            claim=worker_claim(side, case.claimed),
            stage_record_id=str(stage.id),
            step_id=str(step.id),
            source="executor",
            manifest=manifest_to_json(manifest),
        ),
        idempotency_key=f"seal-review-fix:{side.new_id()}",
    )["output_id"]


def red_result():
    return {
        **documents()["reviewer"],
        "verdict": "red",
        "summary": "Answer is wrong",
        "findings": [
            {
                "id": "F1",
                "severity": "major",
                "confidence": "high",
                "basis": "correctness",
                "category": "correctness",
                "message": "Wrong answer",
                "failure_scenario": "Returning the answer",
                "location": {"mount": "repo", "path": "src/app.py", "line_start": 1},
            }
        ],
    }


def red_case(side, tmp_path, monkeypatch):
    if side.kind == "postgres":
        # Upload expiry must share the database clock used by fenced evidence consumption.
        with side.uow(readonly=True) as uow:
            side.clock.set(uow.connection.execute("SELECT clock_timestamp()").fetchone()[0])
    case = bus_case(side, tmp_path / "repo")
    first = execute(case, tmp_path / "execute-red", monkeypatch, "answer = 41\n")
    checks(case, first["next"])
    red = review(case, tmp_path / "review-red", monkeypatch, red_result())
    assert red["next"]["stage_id"] == "triage"
    return case


def test_fake_m3_cycle_confirms_original_finding_then_accepts_corrected_green_review(
    exec_side, tmp_path, monkeypatch
):
    case = red_case(exec_side, tmp_path, monkeypatch)
    stage, step, _ = admitted_stage(case, "triager")
    payload = fake_result(case, tmp_path / "triage", monkeypatch, "triager", documents()["triager"])
    fixed_next = record(case, stage, step, payload)
    assert fixed_next["next"]["stage_id"] == "execute"
    with exec_side.uow(readonly=True) as uow:
        finding = uow.repo(ReviewRepository).findings_for_task(case.task.id)[0]
        assert finding.state is FindingState.CONFIRMED
        assert finding.reproduction is None
        saved = uow.repo(StepRepository).get(step.id)
        assert saved.state is StepState.SUCCEEDED
        assert document(saved.result) == documents()["triager"]
        repo = uow.repo(ReviewRepository)
        red = repo.for_task(case.task.id)[-1]
        reports = [
            v
            for v, role in uow.repo(EvidenceBindingRepository).for_owner("review", red.id)
            if role.value == artifacts.BindingRole.REPORT.value
        ]
        assert len(reports) == 1
        text = artifacts.read_text_content(uow, reports[0], max_bytes=100_000)
        assert text is not None
        assert json.loads(text) == red_result()
        continuation = uow.repo(AttemptRepository).get(case.attempt.id).continuation
        brief = repo.get_fix_brief(continuation.stage.feedback_refs.fix_brief_id)
        assert brief.full_report_file_version_id == reports[0]
        cursor = uow.repo(ExecutionQueries).head_run_seq(case.run.id)
    # A response retry cannot apply confirmation or advance the workflow twice.
    assert record(case, stage, step, payload) == fixed_next
    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(ExecutionQueries).head_run_seq(case.run.id) == cursor
    fixed = execute(case, tmp_path / "execute-green", monkeypatch, "answer = 42\n")
    checks(case, fixed["next"])
    review(case, tmp_path / "review-green", monkeypatch, documents()["reviewer"])
    with exec_side.uow(readonly=True) as uow:
        repo = uow.repo(ReviewRepository)
        assert [r.verdict.value for r in repo.for_task(case.task.id)] == ["red", "green"]
        assert repo.findings_for_task(case.task.id)[0].state is FindingState.RESOLVED
        assert uow.repo(OutputRepository).latest(case.attempt.id).seq == 2
    assert (case.root / "src/app.py").read_text() == "answer = 42\n"


@pytest.mark.parametrize("can_fix", [False, True])
def test_reviewer_fix_seals_new_output_and_rechecks_before_fresh_review(
    exec_side, tmp_path, monkeypatch, can_fix
):
    if exec_side.kind == "postgres":
        with exec_side.uow(readonly=True) as uow:
            exec_side.clock.set(uow.connection.execute("SELECT clock_timestamp()").fetchone()[0])
    case = bus_case(exec_side, tmp_path / "repo")
    first = execute(case, tmp_path / "execute", monkeypatch, "answer = 41\n")
    checks(case, first["next"])
    stage, step, first_review, original_output = start_review(case, can_fix=can_fix)
    snapshots = tmp_path / "review-snapshots"
    if not can_fix:
        (case.root / "src/app.py").write_text("answer = 42\n")
        with pytest.raises(SkmError, match="active writing step"):
            seal_review_fix(case, stage, step, original_output, snapshots)
        with exec_side.uow(readonly=True) as uow:
            assert uow.repo(OutputRepository).latest(case.attempt.id).id == original_output.id
        return

    payload = fake_result(
        case,
        tmp_path / "review-fix",
        monkeypatch,
        "reviewer",
        red_result(),
        contents="answer = 42\n",
        review_id=first_review.id,
        seal_fix=lambda *_: seal_review_fix(case, stage, step, original_output, snapshots),
    )
    correction = payload["outcome"]["output_id"]
    assert correction != str(original_output.id)
    assert seal_review_fix(case, stage, step, original_output, snapshots) == correction
    next_checks = record(case, stage, step, payload, review_id=first_review.id)["next"]
    assert next_checks["stage_id"] == "checks"
    with exec_side.uow(readonly=True) as uow:
        output = uow.repo(OutputRepository).latest(case.attempt.id)
        assert str(output.id) == correction
        assert output.produced_by_step_id == step.id
        assert output.seq == original_output.seq + 1
        assert not uow.repo(CheckRepository).for_output(output.id)
        assert uow.repo(ReviewRepository).for_task(case.task.id)[0].output_id == original_output.id
    checks(case, next_checks)
    assert case.claimed["instruction"]["params"]["reviewer_with_fix"] is False
    fresh = review(case, tmp_path / "review-fresh", monkeypatch, documents()["reviewer"])
    assert fresh["next"]["stage_id"] == "integrate"
    integration = begin(exec_side, {**case.claimed, "instruction": fresh["next"]})["integrate"]
    target = integration["integration_targets"][0]
    with exec_side.uow(readonly=True) as uow:
        repo = uow.repo(ReviewRepository)
        old, new = repo.for_task(case.task.id)
        finding = repo.findings_for_task(case.task.id)[0]
        assert old.output_id == original_output.id
        assert str(new.output_id) == correction
        assert finding.state is FindingState.RESOLVED
    projected = target["outputs"][0]
    assert projected["output_id"] == correction
    assert projected["review_id"] == str(new.id)
    assert projected["review_round"] == 2
    assert projected["findings"] == [finding.finding_key]
    assert projected["producers"] == [{"plan_role": "executor"}, {"plan_role": "reviewer"}]
    assert target["task_spec_ref"] == f"skm:revision:{case.run.revision_id}#entity:{case.task.spec_entity_id}"
    assert target["task_spec_digest"].startswith("sha256:")
    assert "Wrong answer" not in json.dumps(integration)


@pytest.mark.parametrize("invalid", ["foreign", "missing", "duplicate", "rejected", "reproduction"])
def test_minimal_triage_cannot_confirm_foreign_partial_or_ambiguous_findings(
    exec_side, tmp_path, monkeypatch, invalid
):
    case = red_case(exec_side, tmp_path, monkeypatch)
    stage, step, _ = admitted_stage(case, "triager")
    result = documents()["triager"]
    if invalid == "foreign":
        result["confirmed"][0]["finding_id"] = "F99"
    elif invalid == "missing":
        result["confirmed"] = []
    elif invalid == "duplicate":
        result["confirmed"] *= 2
    elif invalid == "rejected":
        result["confirmed"] = []
        result["rejected"] = [{"finding_id": "F1", "reason": "Assumed false positive"}]
    else:
        result["confirmed"][0]["reproduction"] = {"argv": ["false"], "exit": 1, "observed": "Still wrong"}
    # Server validation is exercised directly even when the host rejects this payload first.
    payload = {
        "outcome_kind": "success",
        "outcome": {"step_id": str(step.id), "role_result": result},
        "usage": None,
    }
    record(case, stage, step, payload)
    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(ReviewRepository).findings_for_task(case.task.id)[0].state is FindingState.OPEN
        assert uow.repo(StepRepository).get(step.id).state is StepState.FAILED
