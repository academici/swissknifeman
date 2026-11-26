"""Restore the pinned bytes and observe actual assignment grants after a newer version exists."""

from dataclasses import replace

from fixtures.execution.harness import recovery_claim, system_dispatch
from skm.modules.artifacts.domain.blob import LocationState
from skm.modules.artifacts.ports import AccessGrantRepository, BlobRepository
from skm.modules.artifacts.public import GrantReason
from skm.modules.execution.ports import TaskRepository
from skm.modules.workspace.public import RecordWorkerHeartbeat


def restore_and_assert_pinned_grant(side, run_id, version, locations, newer_id):
    assert newer_id != version.id
    with side.uow() as uow:
        for location in locations:
            uow.repo(BlobRepository).mark_location(
                version.blob_id, location.backend_id, LocationState.PRESENT, side.clock.now()
            )
        for task in uow.repo(TaskRepository).list_for_run(run_id):
            reason = task.blocking_reason
            uow.repo(TaskRepository).save(
                replace(
                    task,
                    blocking_reason=replace(reason, next_check_at=reason.since),
                    row_version=task.row_version + 1,
                ),
                expected_version=task.row_version,
            )
        uow.commit()
    side.worker1_client.dispatch(RecordWorkerHeartbeat(side.worker1, None))
    system_dispatch(side, "schedule_ready_tasks")
    assigned = recovery_claim(side)
    assert assigned.get("assignment_id"), assigned
    with side.uow(readonly=True) as uow:
        grants = uow.repo(AccessGrantRepository)
        actor = side.worker1_client._actor
        args = {"reason": GrantReason.ASSIGNMENT, "ref": assigned["assignment_id"]}
        assert grants.active_for(actor.principal_id, version.id, side.clock.now(), **args) is not None
        assert grants.active_for(actor.principal_id, newer_id, side.clock.now(), **args) is None
