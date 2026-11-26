"""Crashes, stale fences and read-only administrative recovery never repeat the original IO."""

from dataclasses import dataclass, replace
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from contracts.execution._worker_protocol_support import begin, claim, worker_claim
from integration.git.test_integration import ownership
from integration.git.test_push_receipts import push_case
from recovery._recovery_helpers import expire, inspect_push, worker_result_path
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject
from skm.modules.execution import public as execution
from skm.modules.execution.application.commands import report_attempt_failure
from skm.modules.execution.domain.assignment import AssignmentState, retry_later
from skm.modules.execution.domain.external_effect import EffectState
from skm.modules.execution.generated.commands import CancelRun, PauseRun, RestartTask
from skm.modules.execution.host import worker_loop
from skm.modules.execution.host.stages.base import CleanupUnconfirmed
from skm.modules.execution.host.stages.integrate import IntegrateStage
from skm.modules.execution.ports import (
    AssignmentRepository,
    DecisionRepository,
    ExecutionQueries,
    RunRepository,
    StageDeps,
    StageRepository,
)
from skm.modules.policy.ports import ToolIntentRepository
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from unit.execution.application._integration_case import record
from unit.execution.application.test_external_effects import _shared_side as _shared_side
from unit.execution.application.test_external_effects import (
    admin_case,
    admin_result,
    cancel_case,
    dispatch,
    effect_case,
    effect_record,
    observation,
    reconcile,
    saved_effect,
    snapshot,
)
from unit.execution.application.test_external_effects import configured_memory as configured_memory
from unit.execution.application.test_external_effects import exec_side as exec_side
from unit.execution.application.test_external_effects import memory_side as memory_side


def failure(side, claimed, ready, *, key=None):
    return dispatch(
        side,
        execution.ReportAttemptFailure(
            claim=worker_claim(side, claimed),
            stage_record_id=ready["stage_record_id"],
            error_class="unknown_outcome",
            detail="receipt lost",
            worktree_dirty=False,
        ),
        key=key,
    )


def ready_after_backoff(side, case):
    side.clock.advance(timedelta(seconds=31))
    if side.kind == "postgres":
        with side.uow() as uow:
            repo = uow.repo(AssignmentRepository)
            for row in repo.for_attempt(case.attempt_id):
                if row.reconcile_effect_id == case.effect.id and row.state is AssignmentState.AVAILABLE:
                    repo.save(
                        replace(row, available_at=uow.repo(RunRepository).now()),
                        expected_version=row.row_version,
                    )
            uow.commit()


def test_real_push_receipt_loss_and_failure_rollback_then_reconcile_once(exec_side, tmp_path, monkeypatch):
    side = exec_side
    gitcase = push_case(tmp_path)
    case = effect_case(
        side,
        kind="git_push",
        locator=str(gitcase.repo),
        after=gitcase.after,
        before=gitcase.before,
        endpoint=gitcase.request["endpoint"],
    )
    gitcase.request = case.request
    gitcase.writer.repositories = {str(side.repo_id): gitcase.repo}

    def report(raw):
        if raw["phase"] == "result":
            raise ConnectionError("lost DB receipt after real push")
        return record(
            side, case.claimed, {k: raw[k] for k in ("effect_id", "kind", "request_digest")}, raw["phase"]
        )

    own = ownership(case.effect.id, str(case.attempt_id), tmp_path)
    with pytest.raises(ConnectionError):
        gitcase.writer.push_external(
            gitcase.repo,
            str(case.effect.id),
            case.request,
            case.effect.request_digest,
            SimpleNamespace(record_effect=report),
            own,
        )
    assert gitcase.tip() == gitcase.after
    assert saved_effect(side, case.effect.id).state is EffectState.EXECUTING
    real_record = report_attempt_failure.record_outcome

    def crash_after_policy(*args, **kwargs):
        real_record(*args, **kwargs)
        raise ConnectionError("rollback both policy and execution")

    key = f"lost-receipt:{side.new_id()}"
    with monkeypatch.context() as patch:
        patch.setattr(report_attempt_failure, "record_outcome", crash_after_policy)
        with pytest.raises(SkmError) as caught:
            failure(side, case.claimed, case.ready, key=key)
        assert isinstance(caught.value.__cause__, ConnectionError)
    assert saved_effect(side, case.effect.id).state is EffectState.EXECUTING
    with side.uow(readonly=True) as uow:
        assert uow.repo(ToolIntentRepository).get(case.effect.intent_id).state.value == "executing"
    failure(side, case.claimed, case.ready, key=key)
    assert saved_effect(side, case.effect.id).state is EffectState.OUTCOME_UNKNOWN
    cancel_case(side, case)
    baseline = snapshot(side, case)
    claimed, ready = admin_case(side, case)
    # Any accidental publication in the admin host path is an immediate test failure.
    monkeypatch.setattr(gitcase.writer, "push_external", lambda *a, **k: pytest.fail("second push"))
    value, progress = inspect_push(side, gitcase, case, claimed, ready, tmp_path)
    assert len(progress) >= 6
    with side.uow(readonly=True) as uow:
        identities = uow.repo(StageRepository).get(UUID(ready["stage_record_id"])).process_identities
        assert len(identities) == len(progress)
        assert {i.ownership["owner"]["stage_record_id"] for i in identities} == {ready["stage_record_id"]}
    admin_result(side, claimed, ready, value)
    assert admin_result(side, claimed, ready, value)["next"]["kind"] == "release"
    assert snapshot(side, case) == baseline
    assert gitcase.tip() == gitcase.after
    with side.uow(readonly=True) as uow:
        assert uow.repo(ToolIntentRepository).get(case.effect.intent_id).state.value == "succeeded"
        assert len(uow.repo(ExecutionQueries).attempt_view(case.attempt_id)["effects"]) == 2


@pytest.mark.parametrize("close", ["failure", "release", "expiry"])
def test_interrupted_admin_read_reissues_only_bound_assignment(exec_side, close):
    side = exec_side
    case = effect_case(side)
    effect_record(side, case)
    cancel_case(side, case)
    baseline = snapshot(side, case)
    claimed, ready = admin_case(side, case)
    dispatch(
        side,
        execution.RenewLease(
            claim=worker_claim(side, claimed), progress={"stage_record_id": ready["stage_record_id"]}
        ),
    )
    if close == "failure":
        failure(side, claimed, ready)
        dispatch(
            side,
            execution.ReleaseAssignment(
                claim=worker_claim(side, claimed), reason="waiting", retain_environment=True
            ),
        )
    elif close == "release":
        dispatch(
            side,
            execution.ReleaseAssignment(
                claim=worker_claim(side, claimed), reason="waiting", retain_environment=True
            ),
        )
    else:
        side.clock.advance(timedelta(seconds=121))
        assert expire(side, claimed)["expired"] == 1
    assert saved_effect(side, case.effect.id).state is EffectState.OUTCOME_UNKNOWN
    assert snapshot(side, case) == baseline
    reconcile(side, case)
    ready_after_backoff(side, case)
    newer = claim(side)
    assert newer["assignment_id"] != claimed["assignment_id"]
    assert newer["fencing_token"] > claimed["fencing_token"]
    with pytest.raises(SkmError):
        dispatch(side, execution.RenewLease(claim=worker_claim(side, claimed)))
    with pytest.raises(SkmError):
        admin_result(side, claimed, ready, observation(side, case))
    completed = begin(side, newer)
    admin_result(side, newer, completed, observation(side, case, state="failed", reason="EFFECT_ABSENT"))
    assert saved_effect(side, case.effect.id).state is EffectState.FAILED
    assert snapshot(side, case) == baseline


def test_unknown_observation_escalates_without_duplicate_effect_or_decision(exec_side):
    side = exec_side
    case = effect_case(side)
    effect_record(side, case)
    cancel_case(side, case)
    claimed, ready = admin_case(side, case)
    value = observation(side, case, state="outcome_unknown", reason="LOOKUP_UNAVAILABLE")
    key = f"completed-administrative-observation:{side.new_id()}"
    first = admin_result(side, claimed, ready, value, key=key)
    assert admin_result(side, claimed, ready, value, key=key) == first
    with side.uow(readonly=True) as uow:
        seq = uow.repo(ExecutionQueries).head_run_seq(case.run.id)
        assert len(uow.repo(DecisionRepository).open_for_task(case.task_id)) == 1
    reconcile(side, case)
    assert claim(side) == {"outcome": "nothing_to_claim"}
    ready_after_backoff(side, case)
    next_claim = claim(side)
    next_ready = begin(side, next_claim)
    admin_result(side, next_claim, next_ready, value)
    with side.uow(readonly=True) as uow:
        assert uow.repo(ExecutionQueries).head_run_seq(case.run.id) == seq
        assert len(uow.repo(DecisionRepository).open_for_task(case.task_id)) == 1
        assert uow.repo(ToolIntentRepository).get(case.effect.intent_id).state.value == "outcome_unknown"


def test_cancel_and_pause_preserve_pending_and_running_admin_reads(exec_side):
    side = exec_side
    case = effect_case(side)
    effect_record(side, case)
    cancel_case(side, case)
    issued = reconcile(side, case)
    side.client.dispatch(CancelRun(case.run.id, "again"))
    with side.uow() as uow:
        run = uow.repo(RunRepository).get(case.run.id)
        from skm.modules.execution.domain.run import RunStatus

        uow.repo(RunRepository).save(
            replace(run, status=RunStatus.RUNNING, finished_at=None, row_version=run.row_version + 1),
            expected_version=run.row_version,
        )
        uow.commit()
    with side.uow(readonly=True) as uow:
        run = uow.repo(RunRepository).get(case.run.id)
    side.client.dispatch(PauseRun(run.id, "pause read", run.row_version))
    claimed = claim(side)
    assert claimed["assignment_id"] == issued["assignment_id"]
    ready = begin(side, claimed)
    side.client.dispatch(CancelRun(case.run.id, "cancel during read"))
    assert (
        dispatch(side, execution.RenewLease(claim=worker_claim(side, claimed)))["cancel_requested"] is False
    )
    admin_result(side, claimed, ready, observation(side, case))


def test_unavailable_pin_and_retired_host_do_not_migrate_or_read(exec_side):
    side = exec_side
    case = effect_case(side)
    effect_record(side, case)
    cancel_case(side, case)
    from skm.modules.workspace.domain.host import HostState
    from skm.modules.workspace.ports import HostRepository

    with side.uow() as uow:
        hosts = uow.repo(HostRepository)
        host = hosts.get(side.host1)
        hosts.save(
            replace(host, state=HostState.RETIRED, row_version=host.row_version + 1),
            expected_version=host.row_version,
        )
        uow.commit()
    result = reconcile(side, case)
    assert "assignment_id" not in result
    assert claim(side) == {"outcome": "nothing_to_claim"}
    assert saved_effect(side, case.effect.id).state is EffectState.OUTCOME_UNKNOWN


def test_failed_required_message_cannot_complete_successful_local_commit(exec_side):
    side = exec_side
    case = effect_case(side)
    effect_record(side, case)
    proof = observation(side, case, state="failed", reason="EFFECT_ABSENT")
    effect_record(
        side,
        case,
        "result",
        result={
            "succeeded": False,
            "ref": proof["receipt"]["ref"],
            "response_digest": proof["receipt"]["response_digest"],
            "error": "EFFECT_ABSENT",
        },
    )
    assert saved_effect(side, case.effect.id).state is EffectState.FAILED
    baseline = snapshot(side, case)
    with side.uow(readonly=True) as uow:
        seq = uow.repo(ExecutionQueries).head_run_seq(case.run.id)
        effects = uow.repo(ExecutionQueries).attempt_view(case.attempt_id)["effects"]
        assert any(e["kind"] == "git_commit" and e["state"] == "succeeded" for e in effects)
    with pytest.raises(SkmError) as caught:
        dispatch(
            side,
            execution.RecordStageResult(
                claim=worker_claim(side, case.claimed),
                stage_record_id=case.ready["stage_record_id"],
                outcome_kind="success",
                outcome={"pushed": False},
            ),
        )
    assert caught.value.code is ErrorCode.OUTCOME_UNKNOWN
    assert snapshot(side, case) == baseline
    with side.uow(readonly=True) as uow:
        assert uow.repo(ExecutionQueries).head_run_seq(case.run.id) == seq


def test_cached_admin_heartbeat_cannot_replay_after_same_assignment_is_refenced(exec_side):
    side = exec_side
    case = effect_case(side)
    effect_record(side, case)
    cancel_case(side, case)
    reconcile(side, case)
    claimed = claim(side)
    cmd = execution.RenewLease(claim=worker_claim(side, claimed))
    key = f"admin-renew:{side.new_id()}"
    first = dispatch(side, cmd, key=key)
    assert first["cancel_requested"] is False
    assert dispatch(side, cmd, key=key) == first
    with side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        row = repo.get(UUID(claimed["assignment_id"]), for_update=True)
        repo.save(
            retry_later(row, available_at=uow.repo(RunRepository).now()), expected_version=row.row_version
        )
        repo.drop_lease(row.id)
        uow.commit()
    newer = claim(side)
    assert newer["assignment_id"] == claimed["assignment_id"]
    assert newer["fencing_token"] > claimed["fencing_token"]
    with pytest.raises(SkmError) as caught:
        dispatch(side, cmd, key=key)
    assert caught.value.code is ErrorCode.LEASE_LOST
    assert dispatch(side, execution.RenewLease(claim=worker_claim(side, newer)))["cancel_requested"] is False


def test_restart_diagnostics_leave_receipt_free_for_real_reconciliation(exec_side):
    side = exec_side
    case = effect_case(side)
    effect_record(side, case)
    side.client.dispatch(RestartTask(task_id=case.task_id, reason="retry after lost receipt"))
    assert saved_effect(side, case.effect.id).state is EffectState.OUTCOME_UNKNOWN
    assert saved_effect(side, case.effect.id).receipt is None
    with side.uow(readonly=True) as uow:
        intent = uow.repo(ToolIntentRepository).get(case.effect.intent_id)
        assert intent.receipt["reason_code"] == "TASK_RESTARTED"
    baseline = snapshot(side, case)
    claimed, ready = admin_case(side, case)
    value = observation(side, case)
    admin_result(side, claimed, ready, value)
    assert dict(saved_effect(side, case.effect.id).receipt) == value["receipt"]
    assert saved_effect(side, case.effect.id).state is EffectState.SUCCEEDED
    assert snapshot(side, case) == baseline
    with side.uow(readonly=True) as uow:
        assert uow.repo(ToolIntentRepository).get(case.effect.intent_id).state.value == "succeeded"


@dataclass
class _LookupProvider:
    found: JsonObject

    def lookup_effect(self, effect: JsonObject) -> JsonObject:
        return self.found

    def execute_effect(self, effect: JsonObject, *, client: Any, ownership: JsonObject) -> JsonObject:
        pytest.fail("administrative reconciliation must never execute the original effect")


@pytest.mark.parametrize("lookup", ["unavailable", "completed", "unconfirmed_cleanup"])
def test_worker_records_clean_unknown_admin_lookup_and_escalates(exec_side, monkeypatch, lookup):
    side = exec_side
    case = effect_case(side)
    effect_record(side, case)
    cancel_case(side, case)
    baseline = snapshot(side, case)
    claimed, ready = admin_case(side, case)
    ctx, services, owned, worker, request, deps = worker_result_path(side, claimed, ready, monkeypatch)
    found: JsonObject = {"state": "outcome_unknown", "reason_code": "LOOKUP_UNAVAILABLE"}
    if lookup == "unconfirmed_cleanup":
        found["reaped"] = False
    provider = None if lookup == "unavailable" else _LookupProvider(found)
    outcome = IntegrateStage(provider=provider).run(request, cast("StageDeps", deps))
    assert outcome.kind.value == "outcome_unknown"
    if lookup == "unconfirmed_cleanup":
        with pytest.raises(CleanupUnconfirmed):
            worker_loop._record(ctx, services, worker, owned, request, outcome)
    else:
        # Exercise the actual worker cleanup gate and result dispatch, not admin_result directly.
        result = worker_loop._record(ctx, services, worker, owned, request, outcome)
        assert result["next"] == {"kind": "release", "release_reason": "waiting"}
        assert worker.progress() == {}
    assert snapshot(side, case) == baseline
    assert saved_effect(side, case.effect.id).state is EffectState.OUTCOME_UNKNOWN
    with side.uow(readonly=True) as uow:
        assignments = uow.repo(AssignmentRepository)
        assignment = assignments.get(owned.assignment_id)
        stage = uow.repo(StageRepository).get(UUID(ready["stage_record_id"]))
        decisions = uow.repo(DecisionRepository).open_for_task(case.task_id)
        if lookup == "unconfirmed_cleanup":
            assert assignment.state is AssignmentState.LEASED
            assert stage.state.value == "started"
            assert not decisions
        else:
            assert assignment.state is AssignmentState.COMPLETED
            assert assignments.lease(assignment.id) is None
            assert stage.state.value == "completed"
            assert stage.outcome["reconciled_effect"]["state"] == "outcome_unknown"
            assert len(decisions) == 1
            assert decisions[0].kind.value == "escalation"
            assert decisions[0].payload["refs"]["effect_id"] == str(case.effect.id)


@pytest.mark.parametrize("fault", ["registered_helper", "clean_unknown"])
def test_real_git_unknown_preserves_actual_helper_cleanup_at_worker_gate(
    exec_side, tmp_path, monkeypatch, fault
):
    side = exec_side
    gitcase = push_case(tmp_path)
    case = effect_case(
        side,
        kind="git_push",
        locator=str(gitcase.repo),
        after=gitcase.after,
        before=gitcase.before,
        endpoint=gitcase.request["endpoint"],
    )
    gitcase.writer.repositories = {str(side.repo_id): gitcase.repo}

    def report(raw):
        if raw["phase"] == "result":
            raise ConnectionError("lost push receipt")
        return effect_record(side, case)

    own = ownership(case.effect.id, str(case.attempt_id), tmp_path)
    with pytest.raises(ConnectionError):
        gitcase.writer.push_external(
            gitcase.repo,
            str(case.effect.id),
            case.request,
            case.effect.request_digest,
            SimpleNamespace(record_effect=report),
            own,
        )
    failure(side, case.claimed, case.ready)
    cancel_case(side, case)
    baseline = snapshot(side, case)
    claimed, ready = admin_case(side, case)
    # The completed lookup cannot prove historical absence after a remote rewind.
    gitcase.git.run(gitcase.bare, ["update-ref", "refs/heads/main", gitcase.before, gitcase.after])
    ctx, services, owned, worker, request, deps = worker_result_path(side, claimed, ready, monkeypatch)

    def heartbeat(value):
        reply = worker.report_progress(value)
        if fault == "registered_helper":
            raise ConnectionError("lost reply after durable helper registration")
        return reply

    deps.vcs, deps.worker = gitcase.writer, SimpleNamespace(report_progress=heartbeat)
    own["owner"].update(
        host_id=str(side.host1), worker_id=str(side.worker1), stage_record_id=ready["stage_record_id"]
    )
    outcome = IntegrateStage(ownership=lambda *a: own).run(request, cast("StageDeps", deps))
    assert outcome.kind.value == "outcome_unknown"
    folder = gitcase.writer.root / "_inspection" / str(case.effect.id)
    journals = [gitcase.writer._load(path) for path in folder.glob("*.json")]
    with side.uow(readonly=True) as uow:
        stage = uow.repo(StageRepository).get(UUID(ready["stage_record_id"]))
        assert len(stage.process_identities) == len(journals)
    if fault == "registered_helper":
        assert len(journals) == 1
        assert journals[0]["reaped"] is False
        assert outcome.reaped is False
        with pytest.raises(CleanupUnconfirmed):
            worker_loop._record(ctx, services, worker, owned, request, outcome)
    else:
        assert len(journals) >= 6
        assert all(journal["reaped"] for journal in journals)
        assert outcome.reaped is True
        instruction = worker_loop._record(ctx, services, worker, owned, request, outcome)["next"]
        assert isinstance(instruction, dict)
        assert instruction["kind"] == "release"
    with side.uow(readonly=True) as uow:
        assignment = uow.repo(AssignmentRepository).get(owned.assignment_id)
        decisions = uow.repo(DecisionRepository).open_for_task(case.task_id)
        if fault == "registered_helper":
            assert assignment.state is AssignmentState.LEASED
            assert uow.repo(StageRepository).get(stage.id) == stage
            assert not decisions
        else:
            assert assignment.state is AssignmentState.COMPLETED
            assert uow.repo(AssignmentRepository).lease(assignment.id) is None
            assert len(decisions) == 1
            assert decisions[0].kind.value == "escalation"
    assert saved_effect(side, case.effect.id).state is EffectState.OUTCOME_UNKNOWN
    assert snapshot(side, case) == baseline
