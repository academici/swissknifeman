"""Accepted integration stages seeded through the real dual-backend contract harness."""

from dataclasses import replace
from typing import Any
from uuid import UUID

from contracts.execution._worker_protocol_support import begin, claim, make_case, worker_claim
from contracts.execution.seed_helpers import seed_output
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._worker_dtos import digest
from skm.modules.execution.domain.acceptance import AcceptanceBasis, AcceptanceDecision
from skm.modules.execution.domain.review import ReviewClearance
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AttemptRepository,
    EvidenceBindingRepository,
    TaskRepository,
)


def integrated_case(side: Any) -> Any:
    run, task, attempt, _ = make_case(side, stage_id="integrate", stage_type="integrate", env=True)
    claimed = claim(side)
    with side.uow() as uow:
        current = uow.repo(AttemptRepository).get(attempt.id)
        output = seed_output(side, uow, current)
        uow.repo(AttemptRepository).save(
            replace(current, current_output_id=output.id),
            expected_version=uow.repo(AttemptRepository).version(current.id),
        )
        task = uow.repo(TaskRepository).get(task.id)
        uow.repo(TaskRepository).save(
            replace(
                task,
                status=TaskStatus.INTEGRATING,
                row_version=task.row_version + 1,
            ),
            expected_version=task.row_version,
        )
        decision = AcceptanceDecision(
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
        uow.repo(AcceptanceRepository).add_decision(decision)
        uow.repo(EvidenceBindingRepository).bind(
            "attempt", attempt.id, (side.fv1,), artifacts.BindingRole.EVIDENCE
        )
        uow.commit()
    ready = begin(side, claimed)
    return claimed, ready, output, decision


def local_request(side: Any, claimed: Any, ready: Any) -> Any:
    from skm.modules.execution.application.commands.acquire_integration_slot import AcquireIntegrationSlot

    target = ready["integrate"]["integration_targets"][0]
    slot = side.worker1_client.dispatch(
        AcquireIntegrationSlot(
            claim=worker_claim(side, claimed),
            repository_id=target["repository_id"],
            target_branch=target["target_branch"],
        ),
        idempotency_key=f"slot-input:{side.new_id()}",
    )
    request = {
        "repository_id": target["repository_id"],
        "target_branch": target["target_branch"],
        "before_sha": "1" * 40,
        "after_sha": "4" * 40,
        "tree_sha": "3" * 40,
        "baseline_sha": target["baseline_sha"],
        "output_ids": [o["output_id"] for o in target["outputs"]],
        "output_digests": [o["output_digest"] for o in target["outputs"]],
        "commit_shas": ["4" * 40],
        "assignment_fencing_token": claimed["fencing_token"],
        "slot_fencing_token": slot["fencing_token"],
        "writer_epoch_sha": "5" * 40,
    }
    effect_id = target["effect_id"]
    envelope = {
        "effect_id": effect_id,
        "kind": "git_commit",
        "request_digest": digest({"effect_id": effect_id, "kind": "git_commit", "request": request}),
    }
    return target, slot, request, envelope


def record(side: Any, claimed: Any, envelope: Any, phase: str, **extra: Any) -> Any:
    from skm.bootstrap.host_services import worker_command_factories

    raw = {"claim": worker_claim(side, claimed), **envelope, "phase": phase, **extra}
    return side.worker1_client.dispatch(
        worker_command_factories()["record_external_effect"](raw),
        idempotency_key=f"local-effect:{side.new_id()}",
    )


def decision_for(side: Any, output: Any) -> Any:
    with side.uow(readonly=True) as uow:
        return uow.repo(AcceptanceRepository).decisions_for_task(UUID(str(output.task_id)))
