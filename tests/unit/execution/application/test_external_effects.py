"""Exact intent admissions and bound read-only recovery on both transactional backends."""

from dataclasses import dataclass, field, replace
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID

import pytest

from contracts.execution._worker_protocol_support import begin, claim, worker_claim
from contracts.execution.harness import ExecSide, make_exec_side
from skm.kernel.errors import SkmError
from skm.kernel.ids import AttemptId
from skm.modules.execution import public as execution
from skm.modules.execution.application import subscribers
from skm.modules.execution.application.commands.reconcile_external_effect import ReconcileExternalEffect
from skm.modules.execution.domain.assignment import AssignmentState
from skm.modules.execution.domain.budget import BudgetDimension
from skm.modules.execution.domain.external_effect import EffectState, observation_digest
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    BudgetRepository,
    DecisionRepository,
    EffectRepository,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.policy.generated.commands import ApproveIntent
from skm.modules.policy.ports import ApprovalRepository, ToolIntentRepository
from skm.modules.workspace.domain.checkout_binding import BindingState, CheckoutBinding
from skm.modules.workspace.ports import CheckoutBindingRepository
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from unit.execution.application import _support
from unit.execution.application._integration_case import integrated_case, local_request, record
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import set_setting
from unit.execution.application.test_subscribers import event, subctx

memory_side = _support.side


@dataclass
class _PgCase:
    side: ExecSide | None = None
    attempts: list[AttemptId] = field(default_factory=list)


_PG_CASE = _PgCase()


def configure_effect_policy(side):
    import tomllib
    from importlib.resources import files

    effects = ["git_push", "pr_create", "publish", "message"]
    profile = tomllib.loads(
        files("skm.modules.policy").joinpath("profiles/workspace-contained.toml").read_text()
    )
    profile["id"] = "external-effects-test"
    profile["effects"] = {"allow": ["git_commit", *effects], "need_approval": effects}
    for key, value in (
        ("policy.profiles", {profile["id"]: profile}),
        ("policy.default_profile", profile["id"]),
        ("policy.ceiling.external_effects", effects),
    ):
        set_setting(side, key, value)


@pytest.fixture(scope="session")
def configured_memory(_shared_side):
    configure_effect_policy(_shared_side)
    return _shared_side


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def exec_side(request, tmp_path):
    """Reuse the production app; isolate memory snapshots and fresh PG run/attempt identities."""
    if request.param == "memory":
        request.getfixturevalue("configured_memory")
        yield request.getfixturevalue("memory_side")
        return
    current = _PG_CASE.side
    if current is None:
        db = request.getfixturevalue("clean_test_database")
        generator = make_exec_side("postgres", tmp_path, dsn=db.dsn)
        current = next(generator)
        _PG_CASE.side = current
        with current.uow(readonly=True) as uow:
            now = uow.repo(RunRepository).now()
        current.clock.advance(now - current.clock.now())
        request.session.addfinalizer(lambda: next(generator, None))
        configure_effect_policy(current)
    _PG_CASE.attempts.clear()
    original_time = current.clock.now()
    from skm.modules.execution.domain.autopilot import AutopilotStateKind
    from skm.modules.execution.ports import AutopilotRepository
    from skm.modules.workspace.ports import HostRepository, ProjectRepository

    with current.uow(readonly=True) as uow:
        project = uow.repo(ProjectRepository).get(current.proj)
        host = uow.repo(HostRepository).get(current.host1)
    try:
        yield current
    finally:
        with current.uow() as uow:
            assignments = uow.repo(AssignmentRepository)
            for attempt_id in _PG_CASE.attempts:
                for assignment in assignments.for_attempt(attempt_id):
                    if assignment.state in {AssignmentState.AVAILABLE, AssignmentState.LEASED}:
                        assignments.save(
                            replace(assignment, state=AssignmentState.CANCELLED),
                            expected_version=assignment.row_version,
                        )
                    assignments.drop_lease(assignment.id)
            bindings = uow.repo(CheckoutBindingRepository)
            if (binding := bindings.find(current.host1, current.repo_id)) is not None:
                bindings.save(
                    replace(binding, state=BindingState.REMOVED, row_version=binding.row_version + 1),
                    expected_version=binding.row_version,
                )
            projects = uow.repo(ProjectRepository)
            latest_project = projects.get(project.id)
            if latest_project.state != project.state:
                projects.save(
                    replace(latest_project, state=project.state, row_version=latest_project.row_version + 1),
                    expected_version=latest_project.row_version,
                )
            hosts = uow.repo(HostRepository)
            latest_host = hosts.get(host.id)
            if latest_host.state != host.state:
                hosts.save(
                    replace(latest_host, state=host.state, row_version=latest_host.row_version + 1),
                    expected_version=latest_host.row_version,
                )
            autopilot = uow.repo(AutopilotRepository).get(current.proj)
            if autopilot is not None and autopilot.emergency:
                uow.repo(AutopilotRepository).save(
                    replace(
                        autopilot,
                        state=AutopilotStateKind.IDLE,
                        emergency=False,
                        stop_code=None,
                        stop_detail=None,
                        current_run_id=None,
                        row_version=autopilot.row_version + 1,
                    ),
                    expected_version=autopilot.row_version,
                )
            uow.commit()
        current.clock.advance(original_time - current.clock.now())
        current.app.config.clear_cache()


def dispatch(side, command, *, worker=True, key=None):
    return (side.worker1_client if worker else side.client).dispatch(
        command, idempotency_key=key or f"external:{side.new_id()}"
    )


def saved_effect(side, identity):
    with side.uow(readonly=True) as uow:
        return uow.repo(EffectRepository).get(UUID(str(identity)))


def effect_case(
    side, *, kind="message", approve=True, locator="/owned/repository", after=None, before=None, endpoint=None
):
    claimed, ready, output, _ = integrated_case(side)
    if side is _PG_CASE.side:
        _PG_CASE.attempts.append(output.attempt_id)
    _target, _, request, envelope = local_request(side, claimed, ready)
    if after is not None:
        from skm.modules.execution.application._worker_dtos import digest

        request.update(after_sha=after, commit_shas=[after])
        envelope["request_digest"] = digest(
            {"effect_id": envelope["effect_id"], "kind": "git_commit", "request": request}
        )
    record(side, claimed, envelope, "intended", request=request)
    record(side, claimed, envelope, "executing")
    receipt = {
        k: request[k]
        for k in (
            "before_sha",
            "after_sha",
            "tree_sha",
            "target_branch",
            "output_ids",
            "commit_shas",
            "writer_epoch_sha",
        )
    }
    receipt.update(
        ref=request["after_sha"],
        request_digest=envelope["request_digest"],
        receipt_ref="refs/skm/effects/" + envelope["effect_id"],
        receipt_commit_sha="6" * 40,
        at=side.clock.now().isoformat(),
    )
    record(side, claimed, envelope, "result", result={"succeeded": True, "git_receipt": receipt})
    args = {"channel": "test", "body_digest": "sha256:" + "a" * 64, "recipients": ["owner"]}
    if kind in {"git_push", "pr_create"}:
        with side.uow() as uow:
            binding = CheckoutBinding(
                side.new_id(),
                side.ws,
                side.host1,
                side.repo_id,
                locator,
                BindingState.ACTIVE,
                (),
                None,
                side.clock.now(),
                1,
                side.clock.now(),
            )
            uow.repo(CheckoutBindingRepository).add(binding)
            uow.commit()
        args = {
            "repository_id": str(side.repo_id),
            "endpoint": endpoint
            or {"transport": "file", "hostname": "", "effective_port": 1, "repository_path": "/remote.git"},
            "binding_identity": {
                "binding_id": str(binding.id),
                "host_id": str(side.host1),
                "repository_id": str(side.repo_id),
                "locator_digest": "sha256:" + sha256(locator.encode()).hexdigest(),
            },
        }
        if kind == "git_push":
            args.update(
                remote="origin",
                target_ref="refs/heads/main",
                before_sha=before or "1" * 40,
                after_sha=request["after_sha"],
                refspecs=["refs/heads/main:refs/heads/main"],
                force=False,
            )
        else:
            args.update(
                base="main", head="topic", title_digest="sha256:" + "b" * 64, body_digest="sha256:" + "c" * 64
            )
    if kind == "publish":
        args = {"target": "test", "artifact_digest": "sha256:" + "a" * 64, "version": "1.0"}
    command = execution.RecordStageResult(
        claim=worker_claim(side, claimed),
        stage_record_id=ready["stage_record_id"],
        outcome_kind="approval_required",
        outcome={"effect_request": {"kind": kind, "args": args}, "integration_receipts": [receipt]},
    )
    key = f"proposal:{side.new_id()}"
    first = dispatch(side, command, key=key)
    assert dispatch(side, command, key=key) == first
    with side.uow(readonly=True) as uow:
        effect = next(
            e
            for e in uow.repo(EffectRepository).unresolved(limit=100)
            if e.kind.value == kind and e.attempt_id == output.attempt_id
        )
        run = uow.repo(RunRepository).get(output.run_id)
        assert uow.repo(DecisionRepository).open_for_task(output.task_id)
    dispatch(
        side,
        execution.ReleaseAssignment(
            claim=worker_claim(side, claimed), reason="waiting", retain_environment=True
        ),
    )
    case = SimpleNamespace(
        effect=effect,
        request=effect.request,
        run=run,
        output=output,
        task_id=output.task_id,
        attempt_id=output.attempt_id,
        claimed=claimed,
        ready=ready,
    )
    if approve:
        resume_effect(side, case)
    return case


def resume_effect(side, case):
    dispatch(
        side,
        ApproveIntent(
            intent_id=case.effect.intent_id, args_digest=case.effect.request_digest, expected_row_version=1
        ),
        worker=False,
    )
    received = event(side, case.run, intent_id=str(case.effect.intent_id))
    received.type = "urn:skm:policy:event:intent-approved:v1"
    with side.uow() as uow:
        subscribers.intent_resolved_resume(received, subctx(side, uow, case.run), uow)
        uow.commit()
    case.claimed = claim(side)
    assert case.claimed["instruction"]["params"]["effect_id"] == str(case.effect.id)
    case.ready = begin(side, case.claimed)
    return case


def effect_record(side, case, phase="executing", **extra):
    return record(
        side,
        case.claimed,
        {
            "effect_id": str(case.effect.id),
            "kind": case.effect.kind.value,
            "request_digest": case.effect.request_digest,
        },
        phase,
        **extra,
    )


def cancel_case(side, case):
    from skm.modules.execution.generated.commands import CancelRun

    side.client.dispatch(CancelRun(case.run.id, "stop"))
    assert saved_effect(side, case.effect.id).state is EffectState.OUTCOME_UNKNOWN


def reconcile(side, case):
    return dispatch(side, ReconcileExternalEffect(effect_id=str(case.effect.id)), worker=False)


def admin_case(side, case):
    issued = reconcile(side, case)
    assert reconcile(side, case)["assignment_id"] == issued["assignment_id"]
    claimed = claim(side)
    assert claimed["assignment_id"] == issued["assignment_id"]
    assert claimed["instruction"]["mode"] == "reconcile"
    assert claimed["instruction"]["params"] == {
        "effect_id": str(case.effect.id),
        "request_digest": case.effect.request_digest,
    }
    return claimed, begin(side, claimed)


def snapshot(side, case):
    with side.uow(readonly=True) as uow:
        attempt = uow.repo(AttemptRepository).get(case.attempt_id)
        return (
            uow.repo(RunRepository).get(case.run.id),
            uow.repo(TaskRepository).get(case.task_id),
            attempt,
            tuple(
                uow.repo(BudgetRepository).accounts_for(case.run.id, case.task_id, dim)
                for dim in BudgetDimension
            ),
            tuple(
                s
                for e in uow.repo(StageRepository).history(case.attempt_id).entries
                for s in uow.repo(StepRepository).for_stage(e.record.id)
            ),
        )


def observation(side, case, *, state="succeeded", reason=None, ref=None):
    ref = ref or (
        case.request.get("after_sha", "provider:receipt")
        if state == "succeeded"
        else case.request.get("before_sha", "absent:" + str(case.effect.id))
    )
    result = {"effect_id": str(case.effect.id), "request_digest": case.effect.request_digest, "state": state}
    if state != "outcome_unknown":
        result["receipt"] = {
            "ref": ref,
            "at": side.clock.now().isoformat(),
            "response_digest": observation_digest(
                str(case.effect.id), case.effect.request_digest, state, ref, reason
            ),
        }
    if reason is not None:
        result["reason_code"] = reason
    return result


def admin_result(side, claimed, ready, value, *, key=None):
    return dispatch(
        side,
        execution.RecordStageResult(
            claim=worker_claim(side, claimed),
            stage_record_id=ready["stage_record_id"],
            outcome_kind="outcome_unknown" if value["state"] == "outcome_unknown" else "success",
            outcome={"reconciled_effect": value},
        ),
        key=key,
    )


def test_approval_consumed_once_and_exact_result_closes_policy(exec_side):
    side = exec_side
    case = effect_case(side)
    assert saved_effect(side, case.effect.id).state is EffectState.INTENDED
    effect_record(side, case)
    with side.uow(readonly=True) as uow:
        assert uow.repo(ToolIntentRepository).get(case.effect.intent_id).state.value == "executing"
        assert uow.repo(ApprovalRepository).for_intent(case.effect.intent_id)[0].used_at is not None
    with pytest.raises(SkmError):
        effect_record(side, case)
    receipt = observation(side, case)["receipt"]
    effect_record(
        side,
        case,
        "result",
        result={"succeeded": True, "ref": receipt["ref"], "response_digest": receipt["response_digest"]},
    )
    with side.uow(readonly=True) as uow:
        assert uow.repo(ToolIntentRepository).get(case.effect.intent_id).state.value == "succeeded"
    result = dispatch(
        side,
        execution.RecordStageResult(
            claim=worker_claim(side, case.claimed),
            stage_record_id=case.ready["stage_record_id"],
            outcome_kind="success",
            outcome={"pushed": False},
        ),
    )
    assert result["task_status"] == "accepted"


@pytest.mark.parametrize("change", ["digest", "request", "kind"])
def test_changed_approved_request_never_consumes_approval(exec_side, change):
    side = exec_side
    case = effect_case(side)
    envelope = {
        "effect_id": str(case.effect.id),
        "kind": case.effect.kind.value,
        "request_digest": case.effect.request_digest,
    }
    extra = {}
    if change == "digest":
        envelope["request_digest"] = "sha256:" + "0" * 64
    elif change == "kind":
        envelope["kind"] = "publish"
    else:
        extra["request"] = {**case.request, "channel": "other"}
    with pytest.raises(SkmError):
        record(side, case.claimed, envelope, "executing", **extra)
    assert saved_effect(side, case.effect.id).state is EffectState.INTENDED
    with side.uow(readonly=True) as uow:
        assert uow.repo(ApprovalRepository).for_intent(case.effect.intent_id)[0].used_at is None


@pytest.mark.parametrize(
    "state", ["cancelled", "owner_paused", "budget_paused", "failed", "emergency", "archive"]
)
def test_bound_read_on_stopped_run_preserves_workflow_and_spend(exec_side, state):
    side = exec_side
    case = effect_case(side)
    effect_record(side, case)
    cancel_case(side, case)
    if state != "cancelled":
        from skm.modules.execution.domain.autopilot import AutopilotState, AutopilotStateKind
        from skm.modules.execution.ports import AutopilotRepository

        with side.uow() as uow:
            run = uow.repo(RunRepository).get(case.run.id)
            status = RunStatus.FAILED if state == "failed" else RunStatus.PAUSED
            changed = replace(
                run,
                status=status,
                finished_at=run.finished_at if state == "failed" else None,
                pause_source=None if state == "failed" else "system" if state == "budget_paused" else "owner",
                stop_code="BUDGET_EXHAUSTED" if state == "budget_paused" else run.stop_code,
                row_version=run.row_version + 1,
            )
            uow.repo(RunRepository).save(changed, expected_version=run.row_version)
            if state == "emergency":
                # Existing autopilot emergency flag, no new policy bypass.
                uow.repo(AutopilotRepository).save(
                    AutopilotState(
                        case.run.project_id,
                        side.ws,
                        AutopilotStateKind.STOPPED,
                        True,
                        case.run.id,
                        None,
                        {},
                        {},
                        "AUTOPILOT_STOPPED",
                        "owner stop",
                        side.owner.principal_id,
                        side.clock.now(),
                        1,
                    ),
                    expected_version=None,
                )
            if state == "archive":
                from skm.modules.workspace.domain.project import ProjectState
                from skm.modules.workspace.ports import ProjectRepository

                projects = uow.repo(ProjectRepository)
                project = projects.get(case.run.project_id)
                projects.save(
                    replace(project, state=ProjectState.ARCHIVED, row_version=project.row_version + 1),
                    expected_version=project.row_version,
                )
            uow.commit()
    baseline = snapshot(side, case)
    claimed, ready = admin_case(side, case)
    renewed = dispatch(
        side,
        execution.RenewLease(
            claim=worker_claim(side, claimed),
            progress={"stage_record_id": ready["stage_record_id"]},
        ),
    )
    assert renewed["cancel_requested"] is False
    value = observation(side, case)
    key = f"closed-bound-read:{side.new_id()}"
    result = admin_result(side, claimed, ready, value, key=key)
    assert result["next"]["kind"] == "release"
    assert admin_result(side, claimed, ready, value, key=key) == result
    dispatch(
        side,
        execution.ReleaseAssignment(
            claim=worker_claim(side, claimed), reason="waiting", retain_environment=True
        ),
    )
    assert snapshot(side, case) == baseline
    assert saved_effect(side, case.effect.id).state is EffectState.SUCCEEDED
    with side.uow(readonly=True) as uow:
        assert uow.repo(ToolIntentRepository).get(case.effect.intent_id).state.value == "succeeded"
        assert all(
            a.state not in {AssignmentState.AVAILABLE, AssignmentState.LEASED}
            for a in uow.repo(AssignmentRepository).for_attempt(case.attempt_id)
        )
    assert reconcile(side, case)["state"] == "succeeded"


@pytest.mark.parametrize(
    "tamper", ["effect_id", "request_digest", "missing_receipt", "failed_without_proof", "wrong_digest"]
)
def test_admin_rejects_foreign_or_unproven_facts(exec_side, tamper):
    side = exec_side
    case = effect_case(side)
    effect_record(side, case)
    cancel_case(side, case)
    claimed, ready = admin_case(side, case)
    value = observation(side, case)
    if tamper == "effect_id":
        value["effect_id"] = str(side.new_id())
    elif tamper == "request_digest":
        value["request_digest"] = "sha256:" + "0" * 64
    elif tamper == "missing_receipt":
        value.pop("receipt")
    elif tamper == "failed_without_proof":
        value["state"] = "failed"
    else:
        value["receipt"]["response_digest"] = "sha256:" + "0" * 64
    with pytest.raises(SkmError):
        admin_result(side, claimed, ready, value)
    assert saved_effect(side, case.effect.id).state is EffectState.OUTCOME_UNKNOWN


def test_negative_result_without_absence_proof_remains_executing(exec_side):
    side = exec_side
    case = effect_case(side)
    effect_record(side, case)
    with pytest.raises(SkmError):
        effect_record(side, case, "result", result={"succeeded": False, "error": "network timeout"})
    assert saved_effect(side, case.effect.id).state is EffectState.EXECUTING


def test_ordinary_assignment_cannot_submit_admin_result(exec_side):
    side = exec_side
    case = effect_case(side)
    with pytest.raises(SkmError):
        admin_result(side, case.claimed, case.ready, observation(side, case))
    assert saved_effect(side, case.effect.id).state is EffectState.INTENDED


def test_partial_vector_cannot_accept_and_retired_host_cannot_finish_bound_read(exec_side):
    side = exec_side
    case = effect_case(side)
    with pytest.raises(SkmError):
        dispatch(
            side,
            execution.RecordStageResult(
                claim=worker_claim(side, case.claimed),
                stage_record_id=case.ready["stage_record_id"],
                outcome_kind="success",
                outcome={},
            ),
        )
    effect_record(side, case)
    cancel_case(side, case)
    claimed, ready = admin_case(side, case)
    from skm.modules.workspace.domain.host import HostState
    from skm.modules.workspace.ports import HostRepository

    with side.uow() as uow:
        repo = uow.repo(HostRepository)
        host = repo.get(side.host1)
        repo.save(
            replace(host, state=HostState.RETIRED, row_version=host.row_version + 1),
            expected_version=host.row_version,
        )
        uow.commit()
    with pytest.raises(SkmError):
        dispatch(side, execution.RenewLease(claim=worker_claim(side, claimed)))
    with pytest.raises(SkmError):
        admin_result(side, claimed, ready, observation(side, case))
    assert saved_effect(side, case.effect.id).state is EffectState.OUTCOME_UNKNOWN
