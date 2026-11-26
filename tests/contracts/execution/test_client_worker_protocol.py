"""Fencing and worker receipts through authenticated embedded and HTTP clients."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from threading import Barrier
from typing import Any, cast
from uuid import UUID

import pytest

from contracts.execution._client_execution import (
    ClientWorker,
    begin_command,
    configure_execution,
    manual_check,
    model_snapshot,
    prepare_agent_request,
    prepare_success,
    register_worker,
    schedule,
    start_run_command,
)
from contracts.planning.test_client_planning import preview, publication
from integration.artifacts.test_upload_flow import dispatch_new
from skm.adapters.postgres.execution.runs_tasks import PostgresRunRepository
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import AttemptId, ContextManifestId, HostId, WorkerId
from skm.modules.access.public import (
    RevokeMembership,
    RevokeToken,
    RotateToken,
    RotateTokenResult,
    WhoAmI,
    WhoAmIView,
    generate_secret,
)
from skm.modules.context.public import get_manifest
from skm.modules.execution import public as execution
from skm.modules.execution.domain.ids import AssignmentId, StageRecordId
from skm.modules.execution.ports import AssignmentRepository, RunRepository, StageRepository, TaskRepository
from skm.modules.planning import public as planning
from skm.modules.runtimes.ports import HostModelAvailabilityRepository
from skm.modules.runtimes.public import Effort, ListModels, ModelsView, RouteKey, host_route_is_fresh
from skm.modules.settings import public as settings
from skm.platform.config import ConfigStore, ScopeTree
from support.backend import ClientBackend, client_backend
from support.pg import clean_test_database, pg_session, test_database
from support.service_runner import Instance

__all__ = ["clean_test_database", "client_backend", "pg_session", "test_database"]


def worker_plan(side: ClientBackend) -> tuple[UUID, UUID]:
    owner = side.client()
    plan = dispatch_new(owner, planning.CreatePlan(side.seed.project_id, "Worker protocol"))
    draft = dispatch_new(owner, planning.OpenDraft(plan.plan_id, base="empty"))
    saved: Any = owner.dispatch(
        planning.SaveDraft(
            plan.plan_id,
            draft.draft_id,
            draft.edit_version,
            merge_patch={
                "phases": [
                    {"key": "P1", "title": "Build", "goal": "Build a fixture", "design_state": "detailed"}
                ],
                "checks": [manual_check("P1.1", "Fixture exists")],
                "items": [
                    {
                        "key": "P1.1",
                        "phase": "P1",
                        "title": "Build the fixture",
                        "summary": "Change target.py",
                        "why": "Exercise the worker lifecycle",
                        "scope": {"include": ["repo:src/**"], "exclude": []},
                        "deliverables": ["Fixture"],
                        "guidance_md": "Keep the fixture self-contained.",
                        "route": {"runtime": "fake", "class": "implementation", "effort": "high"},
                        "review": {"mode": "self", "reason": "Synthetic worker protocol"},
                    }
                ],
            },
        )
    )
    candidate = preview(owner, plan.plan_id, saved)
    assert candidate.publishable, candidate.validation.to_json()
    published = dispatch_new(owner, publication(plan.plan_id, saved, candidate))
    return plan.plan_id, published.revision_id


def test_worker_claim_renew_stage_and_replay_with_live_fence(
    client_backend: ClientBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    side = client_backend
    owner = side.client()
    repo_id = configure_execution(side, owner)
    worker = register_worker(side, owner, "stage-worker")
    foreign = register_worker(side, owner, "other-worker")
    plan_id, revision = worker_plan(side)
    command = start_run_command(plan_id, revision, "P1.1")
    with side.lose_response(owner) as interrupted:
        interrupted.dispatch(command, idempotency_key="start-worker-run")
    run: Any = owner.dispatch(command, idempotency_key="start-worker-run")
    assert owner.dispatch(command, idempotency_key="start-worker-run") == run
    current: Any = owner.ask(execution.GetRun(run.run_id))
    assert current.status == "running"
    schedule(side)
    key = "claim-worker-run"
    claimed: Any = worker.client.dispatch(worker.claim(), idempotency_key=key)
    assert claimed["instruction"]["stage_id"] == "prepare"
    assert claimed["run_id"] == str(run.run_id)
    assert worker.client.dispatch(worker.claim(), idempotency_key=key) == claimed

    renew = execution.RenewLease(claim=worker.fence(claimed))
    with pytest.raises(SkmError) as denied:
        foreign.client.dispatch(renew, idempotency_key="other-worker-renew")
    assert denied.value.code is ErrorCode.FORBIDDEN

    side.clock.advance(timedelta(seconds=1))
    heartbeat: Any = worker.client.dispatch(renew, idempotency_key="renew-worker-run")
    assert datetime.fromisoformat(heartbeat["lease_expires_at"]) > datetime.fromisoformat(
        claimed["lease_expires_at"]
    )
    begin = begin_command(worker, claimed)
    fenced = execution.BeginStage(
        **{
            **begin,
            "claim": {
                **worker.fence(claimed),
                "fencing_token": claimed["fencing_token"] + 1,
            },
        }
    )
    with pytest.raises(SkmError) as stale:
        dispatch_new(worker.client, fenced)
    assert stale.value.code is ErrorCode.LEASE_LOST
    ready: Any = worker.client.dispatch(begin, idempotency_key="begin-prepare")
    assert ready["outcome"] == "ready"
    assert worker.client.dispatch(begin, idempotency_key="begin-prepare") == ready

    result = prepare_success(side, worker, claimed, ready, repo_id)
    with side.lose_response(worker.client) as interrupted:
        interrupted.dispatch(result, idempotency_key="report-prepare")
    recorded = worker.client.dispatch(result, idempotency_key="report-prepare")
    assert worker.client.dispatch(result, idempotency_key="report-prepare") == recorded
    with side.uow() as uow:
        history = uow.repo(StageRepository).history(AttemptId(UUID(claimed["attempt_id"])))
        assert len(history.entries) == 1
        assert history.entries[0].record.outcome_kind == "success"

    side.clock.set(datetime.fromisoformat(heartbeat["lease_expires_at"]) + timedelta(seconds=1))
    if side.dsn is not None:
        # The PG fence also consults an independent SQL clock after taking locks.
        # Drive the execution time port for logical expiry while retaining the real repositories and locks.
        monkeypatch.setattr(PostgresRunRepository, "now", lambda _: side.clock.now())
    with pytest.raises(SkmError) as expired_replay:
        worker.client.dispatch(renew, idempotency_key="renew-worker-run")
    assert expired_replay.value.code is ErrorCode.LEASE_LOST
    with pytest.raises(SkmError) as expired_result:
        worker.client.dispatch(result, idempotency_key="report-after-expiry")
    assert expired_result.value.code is ErrorCode.LEASE_LOST
    with pytest.raises(SkmError) as expired_result_replay:
        worker.client.dispatch(result, idempotency_key="report-prepare")
    assert expired_result_replay.value.code is ErrorCode.LEASE_LOST
    with pytest.raises(SkmError) as expired_claim_replay:
        worker.client.dispatch(worker.claim(), idempotency_key=key)
    assert expired_claim_replay.value.code is ErrorCode.LEASE_LOST


def test_release_live_claim_fences_old_worker_and_permits_reclaim(client_backend: ClientBackend) -> None:
    side = client_backend
    owner = side.client()
    configure_execution(side, owner)
    worker = register_worker(side, owner, "releasing-worker")
    plan, revision = worker_plan(side)
    dispatch_new(owner, start_run_command(plan, revision, "P1.1"))
    schedule(side)
    claimed = dispatch_new(worker.client, worker.claim())
    assignment = AssignmentId(UUID(claimed["assignment_id"]))
    renew = execution.RenewLease(claim=worker.fence(claimed))
    dispatch_new(worker.client, renew)
    release = execution.ReleaseAssignment(
        claim=worker.fence(claimed), reason="retry_later", retain_environment=True
    )
    assert dispatch_new(worker.client, release)["released"]
    with side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        assert repo.lease(assignment) is None
        available_at = repo.get(assignment).available_at
    with pytest.raises(SkmError) as lost:
        dispatch_new(worker.client, renew)
    assert lost.value.code is ErrorCode.LEASE_LOST
    side.clock.set(available_at)
    # PostgreSQL also checks its own clock after acquiring the assignment lock.
    with side.uow() as uow:
        Instance.wait_until(
            lambda: uow.repo(RunRepository).now() >= available_at, description="retry backoff"
        )
    fresh = dispatch_new(worker.client, worker.claim())
    assert (fresh["assignment_id"], fresh["attempt_id"]) == (str(assignment), claimed["attempt_id"])
    assert fresh["fencing_token"] > claimed["fencing_token"]
    with pytest.raises(SkmError) as stale:
        dispatch_new(worker.client, begin_command(worker, claimed))
    assert stale.value.code is ErrorCode.LEASE_LOST
    assert dispatch_new(worker.client, begin_command(worker, fresh))["outcome"] == "ready"


def test_cancel_racing_with_stage_result_preserves_terminal_run(client_backend: ClientBackend) -> None:
    side = client_backend
    owner = side.client()
    repo_id = configure_execution(side, owner)
    worker = register_worker(side, owner, "cancellation-worker")
    plan_id, revision = worker_plan(side)
    run = dispatch_new(owner, start_run_command(plan_id, revision, "P1.1"))
    schedule(side)
    claimed = dispatch_new(worker.client, worker.claim())
    ready = dispatch_new(worker.client, begin_command(worker, claimed))
    report = prepare_success(side, worker, claimed, ready, repo_id)
    barrier = Barrier(2, timeout=10)

    def deliver() -> ErrorCode | None:
        barrier.wait()
        try:
            dispatch_new(worker.client, report)
        except SkmError as error:
            return error.code
        return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = pool.submit(deliver)
        barrier.wait()
        cancellation: Any = owner.dispatch(execution.CancelRun(run.run_id, "Concurrent cancellation"))
        outcome = result.result(timeout=15)
    assert outcome in (None, ErrorCode.LEASE_LOST)

    terminal: Any = owner.ask(execution.GetRun(run.run_id))
    assert terminal.status == cancellation.status == "cancelled"
    with side.uow() as uow:
        history = uow.repo(StageRepository).history(AttemptId(UUID(claimed["attempt_id"])))
        (stage,) = history.of_stage("prepare")
        assert (stage.record.outcome_kind == "success") == (outcome is None)
    with pytest.raises(SkmError) as stale:
        dispatch_new(worker.client, report)
    assert stale.value.code is ErrorCode.LEASE_LOST


def test_host_substitution_creates_a_selected_route_manifest(client_backend: ClientBackend) -> None:
    side = client_backend
    owner = side.client()
    repo_id = configure_execution(side, owner)
    worker = register_worker(side, owner, "substitution-worker")
    plan, revision = worker_plan(side)
    requested = {"runtime_id": "fake", "model_id": "fake-b", "effort": "high"}
    selected = {"runtime_id": "fake", "model_id": "fake-a", "effort": "high"}

    def host_setting(key: str, value: Any) -> None:
        owner.dispatch(
            settings.SetValue.from_json(
                {
                    "scope": {"level": "host", "scope_id": str(worker.host_id)},
                    "key": "runtimes.host." + key,
                    "value": value,
                    "expected_row_version": 0,
                }
            )
        )

    host_setting("enabled_models", {"fake": ["fake-a"]})
    run = dispatch_new(owner, start_run_command(plan, revision, "P1.1"))
    schedule(side)
    assert dispatch_new(worker.client, worker.claim())["outcome"] == "nothing_to_claim"
    if side.dsn is None:
        side.clock.advance(timedelta(seconds=121))
        schedule(side)
        with side.uow() as uow:
            tasks = uow.repo(TaskRepository).list_for_run(run.run_id)
        assert any(
            task.blocking_reason is not None and task.blocking_reason.code.value == "BLOCKED_BY_CAPABILITY"
            for task in tasks
        )

    host_setting("route_substitutions", [{"requested": requested, "selected": selected}])
    claimed = dispatch_new(worker.client, worker.claim())
    prepared = dispatch_new(worker.client, begin_command(worker, claimed))
    recorded = dispatch_new(worker.client, prepare_success(side, worker, claimed, prepared, repo_id))
    ready = dispatch_new(
        worker.client,
        begin_command(
            worker,
            {**claimed, "instruction": recorded["next"]},
            runtime_token_secret=str(generate_secret(lambda n: b"P" * n)),
        ),
    )

    step = ready["step"]
    snapshot = step["route_snapshot"]
    assert snapshot["requested_route"] == {"runtime_id": "fake", "model": "fake-b", "effort": "high"}
    assert snapshot["selected_route"] == {"runtime_id": "fake", "model": "fake-a", "effort": "high"}
    assert snapshot["route_source"] == "host_substitution"
    with side.uow() as uow:
        manifest = get_manifest(uow, ContextManifestId(UUID(step["context"]["manifest_id"])))
    assert manifest.owner_ref == f"step:{step['step_id']}"
    assert manifest.state.value == "draft"
    assert manifest.model == "fake-a"
    assert manifest.route["route_source"] == "host_substitution"


def test_pending_operator_adjustments_are_applied_in_next_step_context(client_backend: ClientBackend) -> None:
    side = client_backend
    owner = side.client()
    repo_id = configure_execution(side, owner)
    worker = register_worker(side, owner, "live-control-worker")
    plan_id, revision = worker_plan(side)
    run = dispatch_new(owner, start_run_command(plan_id, revision, "P1.1"))
    schedule(side)
    claimed = dispatch_new(worker.client, worker.claim())
    task_id = UUID(claimed["task_id"])
    prepared = dispatch_new(worker.client, begin_command(worker, claimed))
    prompt = "Check the local fixture before writing any changes."
    for dto, args in (
        (execution.RerouteTask, ("fake", "fake-a")),
        (execution.OverrideActor, ("executor",)),
        (execution.SteerTask, (prompt,)),
    ):
        snapshot: Any = owner.ask(execution.GetTaskLiveControl(run.run_id, task_id))
        assert snapshot.active_step_id is None
        result = dispatch_new(
            owner,
            dto(
                run.run_id,
                task_id,
                snapshot.row_version,
                snapshot.assignment_id,
                snapshot.fencing_token,
                snapshot.active_step_id,
                "Update the next agent step",
                *args,
            ),
        )
        assert result.effective == "next_step"
    pending: Any = owner.ask(execution.GetTaskLiveControl(run.run_id, task_id))
    assert set(pending.pending_controls) == {"reroute_task", "override_actor", "steer_task"}
    recorded = dispatch_new(worker.client, prepare_success(side, worker, claimed, prepared, repo_id))
    ready = dispatch_new(
        worker.client,
        begin_command(
            worker,
            {**claimed, "instruction": recorded["next"]},
            runtime_token_secret=str(generate_secret(lambda n: b"C" * n)),
        ),
    )
    step = ready["step"]
    assert step["route_snapshot"]["requested"]["model"] == "fake-a"
    assert step["route_snapshot"]["resolved"]["model"] == "fake-a"
    assert step["admission"]["live_actor_profile"] == "executor"
    assert step["session"]["mode"] == "new"
    assert step["session"]["fresh_reason"] == "OPERATOR_LIVE_CONTROL"
    with side.uow() as uow:
        manifest = get_manifest(uow, ContextManifestId(UUID(step["context"]["manifest_id"])))
        assert manifest.owner_ref == f"step:{step['step_id']}"
        assert any(block.block_type.value == "steering" and block.mandatory for block in manifest.blocks)
    applied: Any = owner.ask(execution.GetTaskLiveControl(run.run_id, task_id))
    assert applied.pending_controls == ()
    assert applied.active_step_id == UUID(step["step_id"])


def test_worker_model_snapshots_are_isolated_current_and_ordered(client_backend: ClientBackend) -> None:  # noqa: PLR0915
    side = client_backend
    owner = side.client()
    repo_id = configure_execution(side, owner)
    left = register_worker(side, owner, "left-model-worker", models=("fake-a",))
    right = register_worker(side, owner, "right-model-worker", host_id=left.host_id, models=("fake-b",))
    foreign = register_worker(side, owner, "foreign-model-worker", models=())
    catalog = cast("ModelsView", right.client.ask(ListModels(host_id=right.host_id)))
    assert {item["id"] for item in catalog.models} == {"fake-a", "fake-b"}

    def current(worker: ClientWorker, model: str) -> bool:
        with side.uow() as uow:
            config = side.app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), None)
            return host_route_is_fresh(
                uow,
                config,
                HostId(worker.host_id),
                RouteKey("fake", model, Effort.HIGH),
                as_of=side.clock.now(),
                worker_id=WorkerId(worker.worker_id),
                runtime_version="0.1.0",
                binary_sha256="sha256:" + "a" * 64,
            )

    assert current(left, "fake-a")
    assert not current(left, "fake-b")
    assert current(right, "fake-b")
    assert not current(right, "fake-a")

    plan, revision = worker_plan(side)
    dispatch_new(owner, start_run_command(plan, revision, "P1.1"))
    schedule(side)
    assert dispatch_new(left.client, left.claim())["outcome"] == "nothing_to_claim"
    claimed = dispatch_new(right.client, right.claim())
    assert claimed.get("outcome") is None, claimed
    assert claimed["assignment_id"]
    prepared = dispatch_new(right.client, begin_command(right, claimed))
    prepared_result = dispatch_new(right.client, prepare_success(side, right, claimed, prepared, repo_id))
    ready = dispatch_new(
        right.client,
        begin_command(
            right,
            {**claimed, "instruction": prepared_result["next"]},
            runtime_token_secret=str(generate_secret(lambda n: b"W" * n)),
        ),
    )
    pinned = ready["step"]["route_snapshot"]
    assert pinned["selected_route"]["model"] == "fake-b"
    assert pinned["catalog_digest"].startswith("sha256:")
    assert UUID(pinned["profile_version_id"])

    original = model_snapshot(right, side.clock.now(), ("fake-b",))
    side.clock.advance(timedelta(seconds=1))
    new = side.clock.now()
    for invalid, expected in (
        (model_snapshot(right, new, ("fake-b",), ttl=timedelta(hours=1)), ErrorCode.SCHEMA_INVALID),
        (model_snapshot(right, new + timedelta(seconds=1), ()), ErrorCode.SCHEMA_INVALID),
        (model_snapshot(foreign, new, ()), ErrorCode.FORBIDDEN),
    ):
        with pytest.raises(SkmError) as denied:
            dispatch_new(right.client, invalid)
        assert denied.value.code is expected
    assert current(right, "fake-b")
    dispatch_new(right.client, model_snapshot(right, new, ()))
    assert not current(right, "fake-b")
    assert current(left, "fake-a")
    with pytest.raises(SkmError) as stale:
        dispatch_new(right.client, original)
    assert stale.value.code is ErrorCode.INVALID_TRANSITION
    with side.uow() as uow:
        snapshot = uow.repo(HostModelAvailabilityRepository).worker_snapshot(WorkerId(right.worker_id))
        assert snapshot is not None
        assert snapshot.offers == ()

    token = cast("WhoAmIView", right.client.ask(WhoAmI())).token
    assert token is not None
    rotation = cast("RotateTokenResult", right.client.dispatch(RotateToken(token.token_id, grace_minutes=1)))
    rotated = replace(right, client=side.client(token=rotation.secret), token=rotation.secret)
    side.clock.advance(timedelta(seconds=1))
    next_snapshot = model_snapshot(rotated, side.clock.now(), ("fake-b",), ttl=timedelta(seconds=3))
    dispatch_new(rotated.client, next_snapshot)
    assert current(rotated, "fake-b")
    assert cast("WhoAmIView", right.client.ask(WhoAmI())).token is not None
    with pytest.raises(SkmError) as inactive_claim:
        dispatch_new(right.client, right.claim())
    assert inactive_claim.value.code is ErrorCode.FORBIDDEN
    assert dispatch_new(rotated.client, rotated.claim())["outcome"] == "nothing_to_claim"
    with pytest.raises(SkmError) as superseded:
        dispatch_new(right.client, model_snapshot(right, side.clock.now(), ()))
    assert superseded.value.code is ErrorCode.FORBIDDEN
    side.clock.advance(timedelta(seconds=3))
    assert not current(rotated, "fake-b")


@pytest.mark.parametrize("invalidated_by", ["withdrawal", "rotation"])
def test_stage_tool_authority_and_replayed_handoff_require_the_current_fence(
    client_backend: ClientBackend,
    invalidated_by: str,
) -> None:
    side = client_backend
    owner = side.client()
    repo_id = configure_execution(side, owner)
    worker = register_worker(side, owner, "stage-tool-worker")
    plan, revision = worker_plan(side)
    dispatch_new(owner, start_run_command(plan, revision, "P1.1"))
    schedule(side)
    claimed = dispatch_new(worker.client, worker.claim())
    prepared = dispatch_new(worker.client, begin_command(worker, claimed))
    secret = str(generate_secret(lambda n: b"T" * n))
    agent = prepare_agent_request(side, worker, claimed, prepared, repo_id, runtime_token_secret=secret)
    assert agent.request.secret_env == {}
    ready = agent.stage.begin
    stage_id = UUID(str(ready["stage_record_id"]))
    step_id = UUID(agent.request.request_id)
    gate = execution.VerifyStageAccess(
        assignment_id=UUID(claimed["assignment_id"]),
        attempt_id=UUID(claimed["attempt_id"]),
        worker_id=worker.worker_id,
        fencing_token=claimed["fencing_token"],
        stage_record_id=stage_id,
        step_id=step_id,
    )
    scoped = side.client(token=secret)
    with pytest.raises(SkmError) as pending:
        scoped.ask(gate)
    assert pending.value.code is ErrorCode.LEASE_LOST

    handoff = execution.RenewLease(
        claim=worker.fence(claimed),
        progress={"stage_record_id": str(stage_id), "step_id": str(step_id), "phase": "runtime_started"},
    )
    with side.lose_response(worker.client) as interrupted:
        interrupted.dispatch(handoff, idempotency_key="stage-runtime-handoff")
    resumed: Any = worker.client.dispatch(handoff, idempotency_key="stage-runtime-handoff")
    assert resumed["cancel_requested"] is False
    assert scoped.ask(gate) == execution.StageAccessView(active=True)
    with pytest.raises(SkmError) as wrong_stage:
        worker.client.ask(gate)
    assert wrong_stage.value.code is ErrorCode.FORBIDDEN
    with pytest.raises(SkmError) as wrong_fence:
        scoped.ask(replace(gate, fencing_token=gate.fencing_token + 1))
    assert wrong_fence.value.code is ErrorCode.LEASE_LOST

    side.clock.advance(timedelta(seconds=1))
    if invalidated_by == "withdrawal":
        dispatch_new(worker.client, model_snapshot(worker, side.clock.now(), ()))
        expected_replay, expected_new = ErrorCode.CAPABILITY_UNAVAILABLE, ErrorCode.INVALID_TRANSITION
    else:
        current = cast("WhoAmIView", worker.client.ask(WhoAmI())).token
        assert current is not None
        rotated = cast(
            "RotateTokenResult", worker.client.dispatch(RotateToken(current.token_id, grace_minutes=1))
        )
        successor = replace(worker, client=side.client(token=rotated.secret), token=rotated.secret)
        dispatch_new(successor.client, model_snapshot(successor, side.clock.now(), ("fake-a", "fake-b")))
        # Rotation keeps proven in-flight heartbeats alive during grace.
        progress = execution.RenewLease(
            claim=worker.fence(claimed), progress={"stage_record_id": str(stage_id)}
        )
        assert not dispatch_new(worker.client, progress)["cancel_requested"]
        expected_replay = expected_new = ErrorCode.FORBIDDEN
    with pytest.raises(SkmError) as withdrawn:
        worker.client.dispatch(handoff, idempotency_key="stage-runtime-handoff")
    assert withdrawn.value.code is expected_replay
    with pytest.raises(SkmError) as changed_key:
        worker.client.dispatch(handoff, idempotency_key="second-stage-runtime-handoff")
    assert changed_key.value.code is expected_new

    token = cast("WhoAmIView", scoped.ask(WhoAmI())).token
    assert token is not None
    owner.dispatch(RevokeToken(token.token_id))
    with pytest.raises(SkmError) as revoked:
        scoped.ask(gate)
    assert revoked.value.code is ErrorCode.UNAUTHENTICATED


def test_committed_runtime_refusal_can_replay_without_reopening_the_stage(
    client_backend: ClientBackend,
) -> None:
    side = client_backend
    owner = side.client()
    repo_id = configure_execution(side, owner)
    worker = register_worker(side, owner, "refusal-worker")
    plan, revision = worker_plan(side)
    dispatch_new(owner, start_run_command(plan, revision, "P1.1"))
    schedule(side)
    claimed = dispatch_new(worker.client, worker.claim())
    prepared = dispatch_new(worker.client, begin_command(worker, claimed))
    secret = str(generate_secret(lambda n: b"R" * n))
    agent = prepare_agent_request(side, worker, claimed, prepared, repo_id, runtime_token_secret=secret)
    stage_id = agent.stage.begin["stage_record_id"]
    handoff = execution.RenewLease(
        claim=worker.fence(claimed),
        progress={
            "stage_record_id": stage_id,
            "step_id": agent.request.request_id,
            "phase": "runtime_started",
        },
    )
    side.clock.advance(timedelta(seconds=1))
    dispatch_new(worker.client, model_snapshot(worker, side.clock.now(), ()))
    key = "closed-runtime-refusal"
    with side.lose_response(worker.client) as interrupted:
        interrupted.dispatch(handoff, idempotency_key=key)
    replay: Any = worker.client.dispatch(handoff, idempotency_key=key)
    assert replay["refusal"]["code"] == ErrorCode.CAPABILITY_UNAVAILABLE
    assert replay["next"]["kind"] == "release"
    with side.uow() as uow:
        saved = uow.repo(StageRepository).get(StageRecordId(UUID(str(stage_id))))
        assert saved.runtime_started_at is None
        assert saved.error_code == ErrorCode.CAPABILITY_UNAVAILABLE


def test_worker_rotation_is_scoped_to_its_live_registration(client_backend: ClientBackend) -> None:
    side = client_backend
    owner = side.client()
    configure_execution(side, owner)
    worker = register_worker(side, owner, "rotation-scope-worker")
    identity = cast("WhoAmIView", worker.client.ask(WhoAmI()))
    assert identity.token is not None
    for key, value in (("worker_rotate_before_hours", 1), ("worker_ttl_hours", 6)):
        owner.dispatch(
            settings.SetValue.from_json(
                {"scope": {"level": "instance"}, "key": f"access.tokens.{key}", "value": value}
            )
        )
    rotated = cast("RotateTokenResult", worker.client.dispatch(RotateToken(identity.token.token_id)))
    assert rotated.expires_at == side.clock.now() + timedelta(hours=6)
    with pytest.raises(SkmError) as superseded:
        dispatch_new(worker.client, worker.claim())
    assert superseded.value.code is ErrorCode.FORBIDDEN

    current = side.client(token=rotated.secret)
    owner.dispatch(RevokeMembership(worker.workspace_id, identity.principal.principal_id))
    with pytest.raises(SkmError) as membership_gone:
        current.dispatch(RotateToken(rotated.token_id))
    assert membership_gone.value.code is ErrorCode.FORBIDDEN
    side.clock.advance(timedelta(hours=6))
    with pytest.raises(SkmError) as expired:
        current.ask(WhoAmI())
    assert expired.value.code is ErrorCode.UNAUTHENTICATED
