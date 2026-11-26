"""Readiness audit authorization and fresh persisted prospective requests."""

from typing import Any, cast

import pytest

from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject
from skm.modules.execution.generated.commands import (
    ValidateForExecution,
    ValidateForExecutionSelectionVariant1,
)
from skm.modules.execution.generated.queries import GetReadinessReport
from skm.modules.execution.ports import ReadinessRepository

from ._support import _shared_side as _shared_side
from ._support import side as side


def test_semantic_audit_disabled_is_an_explicit_refusal(side: Any) -> None:
    with pytest.raises(SkmError) as caught:
        side.client.dispatch(ValidateForExecution(side.plan1, side.rev2, semantic_audit=True))
    assert caught.value.details.get("reason_code") == "SEMANTIC_AUDIT_NOT_ALLOWED"


def test_query_recomputes_saved_request_freshness(side: Any) -> None:
    result = side.client.dispatch(
        ValidateForExecution(side.plan1, side.rev2, overrides={"budgets.task.max_attempts": 1})
    )
    with side.uow(readonly=True) as uow:
        report = uow.repo(ReadinessRepository).get(result.report_id)
        assert report.start_request["overrides"] == {"budgets.task.max_attempts": 1}
        assert report.work_policies is not None
    queried = side.client.ask(GetReadinessReport(report_id=result.report_id))
    assert queried.effective_status != "stale"


def test_enabled_semantic_audit_creates_pinned_read_only_audit_run(side: Any) -> None:
    from skm.modules.execution.ports import BundleRepository, RunRepository, TaskRepository

    from ._support import set_setting

    set_setting(side, "execution.readiness.semantic_audit_allowed", True)
    result = side.client.dispatch(ValidateForExecution(side.plan1, side.rev2, semantic_audit=True))
    assert result.audit_run_id is not None
    with side.uow(readonly=True) as uow:
        run = uow.repo(RunRepository).get(result.audit_run_id)
        tasks = uow.repo(TaskRepository).list_for_run(run.id)
        assert run.kind.value == "readiness_audit"
        assert run.audited_report_id == result.report_id
        assert len(tasks) == 1
        assert tasks[0].kind.value == "plan_audit"
        assert tasks[0].declared_write_scope == ()
        assert uow.repo(BundleRepository).get(run.id).work_policies is not None


@pytest.mark.parametrize(
    ("verdict", "status"),
    [("green", "ready_with_advisories"), ("attention", "ready_with_advisories"), ("red", "not_ready")],
)
def test_completed_audit_appends_superseding_report_and_preserves_original(
    side: Any, verdict: str, status: str
) -> None:
    from dataclasses import replace

    from contracts.execution.seed_helpers import seed_attempt
    from skm.modules.execution.application.apply_action import apply_action
    from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageState
    from skm.modules.execution.domain.step import RoleId, StepState
    from skm.modules.execution.domain.task import TaskStatus
    from skm.modules.execution.domain.workflow.actions import ActionDecision, Done
    from skm.modules.execution.ports import RunRepository, TaskRepository

    from ._support import context, seed_stage, seed_step, set_setting

    set_setting(side, "execution.readiness.semantic_audit_allowed", True)
    result = side.client.dispatch(ValidateForExecution(side.plan1, side.rev2, semantic_audit=True))
    from datetime import timedelta

    side.clock.advance(timedelta(seconds=1))
    manifest_id = side.make_final_manifest()
    with side.uow() as uow:
        original = uow.repo(ReadinessRepository).get(result.report_id)
        run = uow.repo(RunRepository).get(result.audit_run_id)
        task = uow.repo(TaskRepository).list_for_run(run.id)[0]
        attempt = seed_attempt(side, uow, run.id, task.id)
        uow.repo(TaskRepository).save(
            replace(
                task,
                status=TaskStatus.INTEGRATING,
                current_attempt_id=attempt.id,
                attempt_count=1,
                blocking_reason=None,
                row_version=task.row_version + 1,
            ),
            expected_version=task.row_version,
        )
        stage = seed_stage(
            side,
            uow,
            attempt,
            stage_id="audit",
            stage_type="advisor_consult",
            state=StageState.COMPLETED,
            outcome_kind=StageOutcomeKind("verdict_" + verdict),
        )
        step = seed_step(
            side,
            uow,
            attempt,
            stage,
            manifest_id=manifest_id,
            role=RoleId.ADVISOR,
            state=StepState.SUCCEEDED,
            result={"verdict": verdict, "summary": "Audit result"},
        )
        why = {"trigger_kind": "stage_outcome", "advance_rule": "I6", "reason_codes": [], "refs": []}
        apply_action(ActionDecision(Done(), why), context(side, uow, run), uow, task_id=task.id)
        uow.commit()
    with side.uow(readonly=True) as uow:
        updated = uow.repo(ReadinessRepository).latest_for(side.rev2)
        assert uow.repo(ReadinessRepository).get(original.id) == original
        assert updated.supersedes_report_id == original.id
        assert updated.inputs_digest == original.inputs_digest
        assert updated.audit["step_id"] == str(step.id)
        assert updated.status.value == status


def test_audit_run_without_an_attempt_refuses_to_finish_instead_of_reading_no_history(
    side: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from skm.modules.execution.application._action_effects import finish_run
    from skm.modules.execution.domain.task import TaskStatus
    from skm.modules.execution.ports import RunRepository, StageRepository, TaskRepository

    from ._support import context, set_setting

    set_setting(side, "execution.readiness.semantic_audit_allowed", True)
    result = side.client.dispatch(ValidateForExecution(side.plan1, side.rev2, semantic_audit=True))
    with side.uow() as uow:
        run = uow.repo(RunRepository).get(result.audit_run_id)
        task = uow.repo(TaskRepository).list_for_run(run.id)[0]
        assert task.current_attempt_id is None
        uow.repo(TaskRepository).save(
            replace(task, status=TaskStatus.SKIPPED, row_version=task.row_version + 1),
            expected_version=task.row_version,
        )
        stages = type(uow.repo(StageRepository))
        unbounded = stages.history

        def history(self: Any, attempt_id: Any) -> Any:
            if attempt_id is None:  # the Postgres adapter cannot read history for no attempt
                raise ValueError("history needs an attempt")
            return unbounded(self, attempt_id)

        monkeypatch.setattr(stages, "history", history)
        why = {"trigger_kind": "operator", "advance_rule": "I6", "reason_codes": [], "refs": []}
        with pytest.raises(SkmError) as caught:
            finish_run(uow, context(side, uow, run), run, why)
    assert caught.value.code.value == "NOT_ACCEPTABLE"


def test_independent_tasks_with_overlapping_write_scopes_are_an_advisory(side: Any) -> None:
    from contracts.execution.harness import _publish_revision
    from skm.modules.planning import public as planning
    from skm.modules.planning.domain.specification import to_document

    with side.uow(readonly=True) as uow:
        doc = to_document(planning.get_revision_specification(uow, side.rev2))
    items = cast("list[JsonObject]", doc["items"])
    units = cast("list[JsonObject]", doc["units"])
    checks = cast("list[JsonObject]", doc["checks"])
    criteria = cast("list[JsonObject]", doc["criteria"])
    item = {k: v for k, v in items[0].items() if k != "id"}
    unit = {k: v for k, v in units[0].items() if k != "id"}
    check = {k: v for k, v in checks[0].items() if k != "id"}
    criterion = {k: v for k, v in criteria[0].items() if k != "id"}
    revision = _publish_revision(
        side.app,
        side.client,
        side.owner,
        side.clock,
        side.plan1,
        {
            "items": [*items, {**item, "key": "P1.2", "title": "Second context item"}],
            "units": [
                *units,
                {**unit, "key": "P1.2/U1", "write_scope": [{"mount": "repo", "pattern": "src/context/**"}]},
            ],
            "checks": [*checks, {**check, "owner": "P1.2"}],
            "criteria": [
                *criteria,
                {**criterion, "key": "AC2", "owner": "P1.2", "checks": ["P1.2:V1"]},
            ],
        },
        "current",
    )
    result = side.client.dispatch(ValidateForExecution(side.plan1, revision))
    with side.uow(readonly=True) as uow:
        report = uow.repo(ReadinessRepository).get(result.report_id)
    overlaps = [f for f in report.findings if f.code == "WRITE_SCOPE_OVERLAP"]
    assert [(f.rule_id, f.severity) for f in overlaps] == [("R08_write_scopes", "advisory")]
    assert "P1.1/U1 and P1.2/U1" in overlaps[0].message

    selected = side.client.dispatch(
        ValidateForExecution(
            side.plan1, revision, selection=ValidateForExecutionSelectionVariant1(task_keys=("P1.1/U1",))
        )
    )
    with side.uow(readonly=True) as uow:
        selected_report = uow.repo(ReadinessRepository).get(selected.report_id)
    assert not any(f.code == "WRITE_SCOPE_OVERLAP" for f in selected_report.findings)


def test_start_waits_for_concurrent_audit_transaction(side: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from skm.adapters.memory.execution.runs_tasks import MemoryRunRepository
    from skm.kernel.error_codes import ErrorCode
    from skm.modules.execution.generated.commands import StartRun

    from ._support import set_setting

    set_setting(side, "execution.readiness.semantic_audit_allowed", True)
    set_setting(side, "execution.readiness.required", False)
    acquired, contender = Event(), Event()
    locked = []
    lock = MemoryRunRepository.lock_revision_start

    def capture_lock(repo: Any, revision_id: Any, *, audit: bool = False) -> None:
        lock(repo, revision_id, audit=audit)
        locked.append((revision_id, audit))
        if len(locked) == 1:
            acquired.set()
            assert contender.wait(5)

    def start() -> None:
        contender.set()
        side.client.dispatch(StartRun(side.plan1, side.rev2, None, {}, "Race audit"))

    monkeypatch.setattr(MemoryRunRepository, "lock_revision_start", capture_lock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        audit = pool.submit(
            side.client.dispatch, ValidateForExecution(side.plan1, side.rev2, semantic_audit=True)
        )
        assert acquired.wait(5)
        run = pool.submit(start)
        assert audit.result(timeout=10).audit_run_id is not None
        with pytest.raises(SkmError, match="audit is active") as refused:
            run.result(timeout=10)
        assert refused.value.code is ErrorCode.READINESS_REQUIRED
    assert locked == [(side.rev2, True), (side.rev2, False)]
