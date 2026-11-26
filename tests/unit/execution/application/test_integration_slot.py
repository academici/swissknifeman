"""Slot commands through the bus against both memory and PostgreSQL transactions."""

from datetime import timedelta
from typing import Any

import pytest

from contracts.execution._worker_protocol_support import claim, make_case, worker_claim
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.seed_helpers import seed_attempt, seed_run, seed_task
from skm.kernel.errors import SkmError
from skm.modules.execution.application.commands.acquire_integration_slot import AcquireIntegrationSlot
from skm.modules.execution.application.commands.release_integration_slot import ReleaseIntegrationSlot
from skm.modules.execution.ports import IntegrationSlotRepository, RunRepository
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database


def acquire(side, claimed, *, branch="integration", key=None, **overrides):
    return side.worker1_client.dispatch(
        AcquireIntegrationSlot(
            claim=worker_claim(side, claimed),
            repository_id=str(side.repo_id),
            target_branch=branch,
            **overrides,
        ),
        idempotency_key=key or f"slot:{side.new_id()}",
    )


def release(side, claimed, slot, *, token=None):
    return side.worker1_client.dispatch(
        ReleaseIntegrationSlot(
            claim=worker_claim(side, claimed),
            slot_id=slot["slot_id"],
            fencing_token=slot["fencing_token"] if token is None else token,
        ),
        idempotency_key=f"release-slot:{side.new_id()}",
    )


def test_slot_lease_tracks_assignment_and_release_preserves_both_pins(exec_side: Any):
    side = exec_side
    run, _, _attempt, _ = make_case(side, env=True)
    claimed = claim(side)
    slot = acquire(side, claimed)
    assert slot["fencing_token"] >= 1
    assert slot["expires_at"] == claimed["lease_expires_at"]
    assert release(side, claimed, slot) == {"released": True}
    with side.uow(readonly=True) as uow:
        slots = uow.repo(IntegrationSlotRepository)
        assert (
            slots.target_hosts(((side.repo_id, "integration"),))[(side.repo_id, "integration")] == side.host1
        )
        assert slots.hosts_for_run(run.id)[side.repo_id] == side.host1
    next_slot = acquire(side, claimed)
    assert next_slot["slot_id"] == slot["slot_id"]
    assert next_slot["fencing_token"] > slot["fencing_token"]
    assert release(side, claimed, slot) == {"released": False, "diagnostic": "LEASE_LOST"}
    assert release(side, claimed, next_slot)["released"]


def test_stale_claim_is_rejected_before_slot_mutation(exec_side: Any):
    side = exec_side
    make_case(side, env=True)
    claimed = claim(side)
    raw = worker_claim(side, claimed)
    raw["fencing_token"] += 1
    with pytest.raises(SkmError) as caught:
        side.worker1_client.dispatch(
            AcquireIntegrationSlot(claim=raw, repository_id=str(side.repo_id), target_branch="integration"),
            idempotency_key=f"bad-slot:{side.new_id()}",
        )
    assert caught.value.code.value == "LEASE_LOST"
    with side.uow(readonly=True) as uow:
        assert not uow.repo(IntegrationSlotRepository).target_hosts(((side.repo_id, "integration"),))


def test_foreign_target_pin_fails_closed_even_after_release_and_expiry(exec_side: Any):
    side = exec_side
    make_case(side, env=True)
    claimed = claim(side)
    with side.uow() as uow:
        slots = uow.repo(IntegrationSlotRepository)
        slots.pin_target_host(side.repo_id, "foreign", side.host2, side.clock.now())
        uow.commit()
    with pytest.raises(SkmError) as caught:
        acquire(side, claimed, branch="foreign")
    assert caught.value.code.value == "INTEGRATION_HOST_MISMATCH"


def test_busy_slot_returns_waiting_code_without_stealing_holder(exec_side: Any):
    side = exec_side
    make_case(side, env=True)
    claimed = claim(side)
    with side.uow() as uow:
        other_run = seed_run(side, uow)
        task = seed_task(side, uow, other_run.id)
        other = seed_attempt(side, uow, other_run.id, task.id)
        slots = uow.repo(IntegrationSlotRepository)
        server_now = uow.repo(RunRepository).now()
        existing = slots.acquire(
            side.repo_id,
            "integration",
            other.id,
            side.host1,
            server_now,
            server_now + timedelta(minutes=5),
        )
        uow.commit()
    key = f"waiting-slot:{side.new_id()}"
    waiting = acquire(side, claimed, key=key)
    assert waiting["outcome"] == "waiting"
    assert waiting["code"] == "SLOT_BUSY"
    assert "slot_id" not in waiting
    with side.uow() as uow:
        uow.repo(IntegrationSlotRepository).release(existing.id, other.id, existing.fencing_token)
        uow.commit()
    assert acquire(side, claimed, key=key)["slot_id"] == str(existing.id)


@pytest.mark.parametrize("branch", ["../bad", "-bad", "x\nupdate refs/heads/main", "bad:ref"])
def test_unsafe_branch_rejected_by_command(exec_side: Any, branch):
    side = exec_side
    make_case(side, env=True)
    claimed = claim(side)
    with pytest.raises(SkmError) as caught:
        acquire(side, claimed, branch=branch)
    assert caught.value.code.value == "SCHEMA_INVALID"


def test_begin_integration_pins_accepted_inputs_and_replays_without_moving_them(exec_side: Any):
    from contracts.execution._worker_protocol_support import begin
    from skm.modules.artifacts import public as artifacts
    from unit.execution.application._integration_case import integrated_case

    side = exec_side
    claimed, ready, output, decision = integrated_case(side)
    assert ready["integrate"]["accepted_output_id"] == str(output.id)
    assert ready["integrate"]["acceptance_decision_id"] == str(decision.id)
    target = ready["integrate"]["integration_targets"][0]
    assert target["outputs"][0]["head_sha"] == output.manifest.mounts[0].head_commit
    assert target["baseline_sha"] == output.manifest.mounts[0].base_commit
    with side.uow(readonly=True) as uow:
        assert artifacts.get_file_version(uow, side.fv1).digest in ready["integrate"]["artifact_digests"]
    repeated = begin(side, claimed)
    assert repeated["integrate"] == ready["integrate"]


def test_begin_without_acceptance_does_not_authorize_integration(exec_side: Any):
    from contracts.execution._worker_protocol_support import begin

    make_case(exec_side, stage_id="integrate", stage_type="integrate", env=True)
    claimed = claim(exec_side)
    with pytest.raises(SkmError) as caught:
        begin(exec_side, claimed)
    assert caught.value.code.value == "INVALID_TRANSITION"


def test_local_effect_admissions_are_fresh_and_slot_fenced(exec_side: Any):
    from datetime import datetime

    from unit.execution.application._integration_case import integrated_case, local_request, record

    side = exec_side
    claimed, ready, _, _ = integrated_case(side)
    target, _, request, envelope = local_request(side, claimed, ready)
    record(side, claimed, envelope, "intended", request=request)
    first = record(side, claimed, envelope, "executing")["admission"]
    second = record(side, claimed, envelope, "executing")["admission"]
    assert first["admission_id"] != second["admission_id"]
    with pytest.raises(SkmError) as unsupported:
        record(side, claimed, {**envelope, "kind": "git_push"}, "executing")
    assert unsupported.value.code.value == "CAPABILITY_UNAVAILABLE"
    assert (
        0
        < (
            datetime.fromisoformat(second["admit_until"]) - datetime.fromisoformat(second["server_now"])
        ).total_seconds()
        <= 5
    )
    acquire(side, claimed, branch=target["target_branch"])
    with pytest.raises(SkmError) as caught:
        record(side, claimed, envelope, "executing")
    assert caught.value.code.value == "LEASE_LOST"


def test_local_receipt_and_stage_result_preserve_acceptance(exec_side: Any):
    from skm.modules.execution import public as execution
    from unit.execution.application._integration_case import (
        decision_for,
        integrated_case,
        local_request,
        record,
    )

    side = exec_side
    claimed, ready, output, decision = integrated_case(side)
    _, _, request, envelope = local_request(side, claimed, ready)
    record(side, claimed, envelope, "intended", request=request)
    record(side, claimed, envelope, "executing")
    receipt = {
        key: request[key]
        for key in (
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
    result = side.worker1_client.dispatch(
        execution.RecordStageResult(
            claim=worker_claim(side, claimed),
            stage_record_id=ready["stage_record_id"],
            outcome_kind="success",
            outcome={"integration_receipts": [receipt], "commit_shas": request["commit_shas"]},
        ),
        idempotency_key=f"integration-result:{side.new_id()}",
    )
    assert result["task_status"] == "accepted"
    assert decision_for(side, output) == (decision,)


def test_bound_stage_client_releases_with_real_slot_fence_through_bus(exec_side: Any):
    from threading import RLock
    from types import SimpleNamespace
    from uuid import UUID

    from skm.bootstrap.host_services import worker_command_factories
    from skm.kernel.cancel import CancelSource
    from skm.modules.execution.domain.lease import WorkerClaim
    from skm.modules.execution.host.stage_client import BoundStageClient

    side = exec_side
    make_case(side, env=True)
    claimed = claim(side)
    raw: Any = {k: UUID(v) if k != "fencing_token" else v for k, v in worker_claim(side, claimed).items()}
    binding = WorkerClaim(**raw)
    concurrency: Any = SimpleNamespace(lock=RLock)
    client = BoundStageClient(
        side.worker1_client,
        binding,
        worker_command_factories(),
        CancelSource().token,
        concurrency=concurrency,
    )
    slot = client.acquire_integration_slot(side.repo_id, "integration")
    client.release_integration_slot(slot)
    successor = client.acquire_integration_slot(side.repo_id, "integration")
    old_token, new_token = slot["fencing_token"], successor["fencing_token"]
    assert isinstance(old_token, int)
    assert isinstance(new_token, int)
    assert new_token > old_token
    client.release_integration_slot(slot)
    with side.uow(readonly=True) as uow:
        current = uow.repo(IntegrationSlotRepository).current(side.repo_id, "integration")
        assert current is not None
        assert current.fencing_token == successor["fencing_token"]
        assert current.holder_attempt_id == binding.attempt_id
    client.release_integration_slot(successor)
    with side.uow(readonly=True) as uow:
        current = uow.repo(IntegrationSlotRepository).current(side.repo_id, "integration")
        assert current is not None
        assert current.holder_attempt_id is None


@pytest.mark.parametrize("mode", ["reconcile", "retry"])
def test_begin_later_integrate_preserves_original_multitarget_effects(exec_side: Any, mode):
    from dataclasses import replace
    from uuid import UUID

    from contracts.execution._worker_protocol_support import begin
    from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageState
    from skm.modules.execution.domain.workflow.stage_inputs import StageMode
    from skm.modules.execution.ports import StageRepository
    from unit.execution.application._integration_case import integrated_case

    side = exec_side
    claimed, ready, _, _ = integrated_case(side)
    original = ready["integrate"]
    original["integration_targets"].append(
        {
            **original["integration_targets"][0],
            "target_branch": "second-target",
            "effect_id": str(side.new_id()),
        }
    )
    original["integration_targets"].sort(
        key=lambda target: (target["repository_id"], target["target_branch"])
    )
    with side.uow() as uow:
        stages = uow.repo(StageRepository)
        prior = stages.get(UUID(ready["stage_record_id"]))
        stages.save(
            replace(
                prior,
                state=StageState.INTERRUPTED,
                finished_at=prior.started_at,
                outcome_kind=StageOutcomeKind.OUTCOME_UNKNOWN,
                outcome={
                    "integration_inputs": original,
                    "effects": [{"state": "succeeded"}, {"state": "outcome_unknown"}],
                },
            )
        )
        later = replace(
            prior,
            id=side.new_id(),
            seq=prior.seq + 1,
            round_no=prior.round_no + 1,
            input_digest="sha256:" + "e" * 64,
            mode=StageMode(mode),
            outcome=None,
            retry_of_id=prior.id if mode == "retry" else None,
        )
        stages.add(later)
        uow.commit()
    repeat = begin(
        side,
        {
            **claimed,
            "instruction": {
                "stage_id": later.stage_id,
                "round_no": later.round_no,
                "input_digest": later.input_digest,
            },
        },
    )
    assert repeat["integrate"] == original
    assert repeat["stage_record_id"] != ready["stage_record_id"]
