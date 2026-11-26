"""PostgreSQL checkpoint boundaries exercised through registered worker/service commands."""

from dataclasses import asdict
from datetime import timedelta
from typing import cast

import psycopg

from contracts.execution._worker_protocol_support import begin, make_case, worker_claim
from fixtures.execution.harness import expire, recovery_claim, system_dispatch
from fixtures.execution.protocol import real_environment
from skm.kernel.json_types import JsonObject
from skm.modules.access.public import generate_secret
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.ports import BlobRepository, BlobStore, FileVersionRepository
from skm.modules.execution import public as execution
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    BudgetRepository,
    StageRepository,
    TaskRepository,
)


def expire_between_stages(side):
    _, task, attempt, _ = make_case(side)
    prepared, _, _ = real_environment(side, attempt)
    old = recovery_claim(side)
    ready = begin(side, old)
    side.worker1_client.dispatch(
        execution.RecordStageResult(
            claim=worker_claim(side, old),
            stage_record_id=ready["stage_record_id"],
            outcome_kind="success",
            outcome={
                "environment_id": str(prepared.environment_id),
                "kind": "git_worktree",
                "branch": prepared.branch,
                "baseline": [{**asdict(b), "repository_id": str(b.repository_id)} for b in prepared.baseline],
                "mounts": [
                    {"mount": m, "local_locator": str(p), "environment_locator": prepared.locator}
                    for m, p in prepared.mounts.items()
                ],
            },
        ),
        idempotency_key=f"prepare:{side.new_id()}",
    )
    with side.uow(readonly=True) as uow:
        before = uow.repo(AttemptRepository).get(attempt.id)
        assert uow.repo(StageRepository).get(ready["stage_record_id"]).finished_at is not None
        assert before.continuation is not None
    assert expire(side)["expired"] == 1
    fresh = recovery_claim(side)
    assert fresh["attempt_id"] == str(attempt.id)
    assert fresh["assignment_id"] != old["assignment_id"]
    with side.uow(readonly=True) as uow:
        after = uow.repo(AttemptRepository).get(attempt.id)
        assert after.continuation == before.continuation
        assert after.started_at == before.started_at
        assert uow.repo(TaskRepository).get(task.id).attempt_count == 1
    secret = str(generate_secret(lambda n: b"Q" * n))
    assert begin(side, fresh, secret=secret)["stage_record_id"] != ready["stage_record_id"]


def future_attempt_is_blocked(side, run, task, attempt, fresh):
    ready = begin(side, fresh)
    side.worker1_client.dispatch(
        execution.ReportAttemptFailure(
            claim=worker_claim(side, fresh),
            stage_record_id=ready["stage_record_id"],
            error_class="environment_lost",
            detail="future attempt after count lowering",
            worktree_dirty=False,
        ),
        idempotency_key=f"new-attempt:{side.new_id()}",
    )
    system_dispatch(side, "schedule_ready_tasks")
    with side.uow(readonly=True) as uow:
        saved = uow.repo(TaskRepository).get(task.id)
        assert saved.attempt_count == 1
        assert saved.current_attempt_id is None
        assert saved.status.value == "awaiting_decision"
        assert saved.blocking_reason is not None
        assert not any(
            a.state.value == "available" for a in uow.repo(AssignmentRepository).for_attempt(attempt.id)
        )
        from skm.modules.execution.domain.budget import BudgetDimension

        accounts = uow.repo(BudgetRepository).accounts_for(run.id, task.id, BudgetDimension.ATTEMPTS)
        assert accounts
        assert all(a.spent == 1 and a.reserved == 0 for a in accounts)


def physical_cleanup_vs_binding(side, race, send, add_file, draft):
    from skm.modules.artifacts.generated.commands import ExpireStagedBlobs
    from skm.modules.planning import public as planning
    from skm.modules.planning.domain.specification import to_document

    data = b"physical contention bytes\n"
    created = add_file(side, data)
    duplicate = side.client.upload_blob(side.ws, (data,), size=len(data))
    orphan = side.client.upload_blob(side.ws, (b"orphan bytes",), size=12)
    with psycopg.connect(side.dsn) as conn:
        conn.execute(
            "UPDATE skm_artifacts.staged_blobs SET created_at=%s, expires_at=%s WHERE id=ANY(%s)",
            (
                side.clock.now() - timedelta(seconds=2),
                side.clock.now() - timedelta(seconds=1),
                [duplicate.staged_blob_id, orphan.staged_blob_id],
            ),
        )
    with side.uow(readonly=True) as uow:
        document = to_document(planning.get_revision_specification(uow, side.rev2))
        materials = cast("list[JsonObject]", document["materials"])
        version = uow.repo(FileVersionRepository).get(created.file_version_id)
        locations = uow.repo(BlobRepository).locations(version.blob_id)
    materials[0]["file_version_id"] = str(created.file_version_id)
    publication = draft(side, {"materials": materials})[2]
    published, cleaned = race(
        lambda: send(side, publication), lambda: side.system.dispatch(ExpireStagedBlobs())
    )
    assert not isinstance(published, str), published
    assert cleaned.expired == 2
    assert cleaned.objects_deleted == 1
    with side.uow(readonly=True) as uow:
        artifacts.require_ready_versions(uow, side.ws, (created.file_version_id,))
        spec = planning.get_revision_specification(uow, published.revision_id)
        assert str(spec.materials[0].file_version_id) == str(created.file_version_id)
    store = side.app.gateways.get(BlobStore)
    assert all(
        store.exists(
            {
                "backend_id": loc.backend_id,
                "storage_key": loc.storage_key,
                "storage_version": loc.storage_version,
            }
        )
        for loc in locations
    )
