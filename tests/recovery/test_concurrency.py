"""All twelve testing §11.1 PostgreSQL interleavings and checkpoint admission races.

Every contender dispatches on its own committed UoW. Barriers release the contenders
simultaneously; assertions accept only the explicitly legal serializations.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from typing import cast

import psycopg
import pytest

from contracts.execution._worker_protocol_support import begin, make_case, worker_claim
from fixtures.execution.harness import (
    clean_test_database,
    pg_session,
    recovery,
    recovery_claim,
    test_database,
)
from fixtures.execution.planning import draft, ready_revision
from fixtures.execution.protocol import dispatch_result
from integration.artifacts.test_upload_flow import add_file_dto
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.generated import commands as art
from skm.modules.execution import public as execution
from skm.modules.execution.generated.commands import (
    PauseRun,
    ReconfigureRun,
    ResumeRun,
    StartRun,
    ValidateForExecution,
)
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)
from skm.modules.planning.generated.commands import SaveDraft
from support.fault_injection import FaultPlan, FaultPoint, FaultyClient, InjectedFault

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = pytest.mark.pg


def race(*operations):
    gate = Barrier(len(operations))

    def run(operation):
        gate.wait(timeout=10)
        try:
            return operation()
        except SkmError as error:
            return error.code.value

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        pending = [pool.submit(run, op) for op in operations]
        return [future.result(timeout=30) for future in pending]


def send(side, command):
    return side.client.dispatch(command, idempotency_key=f"race:{side.new_id()}")


def test_01_concurrent_draft_edits_compare_edit_version(recovery):
    side = recovery
    opened, saved, _ = draft(side)
    results = race(
        *(
            lambda text=text: send(
                side, SaveDraft(side.plan1, opened.draft_id, saved.edit_version, merge_patch={"goal": text})
            )
            for text in ("one", "two")
        )
    )
    assert results.count("VERSION_CONFLICT") == 1
    assert sum(not isinstance(result, str) for result in results) == 1


def test_02_concurrent_publications_compare_base_revision(recovery):
    side = recovery
    commands = [draft(side, {"goal": goal})[2] for goal in ("one", "two")]
    results = race(*(lambda command=command: send(side, command) for command in commands))
    assert results.count("BASE_REVISION_CHANGED") == 1
    assert sum(not isinstance(result, str) for result in results) == 1


def test_03_claim_contention_creates_exactly_one_lease(recovery):
    side = recovery
    _, _, attempt, assignment = make_case(side)
    results = race(lambda: recovery_claim(side), lambda: recovery_claim(side))
    assignments = []
    for result in results:
        assert isinstance(result, dict), result
        assignments.append(result.get("assignment_id"))
    assert assignments.count(str(assignment.id)) == 1
    with side.uow(readonly=True) as uow:
        assert (
            len(
                [
                    a
                    for a in uow.repo(AssignmentRepository).for_attempt(attempt.id)
                    if a.state.value == "leased"
                ]
            )
            == 1
        )
        assert uow.repo(AssignmentRepository).lease(assignment.id) is not None


def test_04_reissued_lease_refuses_old_result(recovery):
    from fixtures.execution.harness import expire

    side = recovery
    make_case(side)
    old = recovery_claim(side)
    ready = begin(side, old)
    expire(side)
    results = race(lambda: recovery_claim(side), lambda: dispatch_result(side, old, ready))
    assert results[1] == "LEASE_LOST"
    new = results[0]
    assert isinstance(new, dict), new
    assert new["assignment_id"] != old["assignment_id"]


def add_file(side, data=b"racing bytes\n"):
    staged = side.client.upload_blob(side.ws, (data,), size=len(data))
    return send(side, add_file_dto(side.ws, side.proj, staged))


def test_05_trash_racing_revision_binding_has_consistent_material_state(recovery):
    side = recovery
    created = add_file(side)
    from skm.modules.planning import public as planning
    from skm.modules.planning.domain.specification import to_document

    with side.uow(readonly=True) as uow:
        document = to_document(planning.get_revision_specification(uow, side.rev2))
        materials = cast("list[JsonObject]", document["materials"])
    materials[0]["file_version_id"] = str(created.file_version_id)
    publication = draft(side, {"materials": materials})[2]
    results = race(
        lambda: send(side, publication),
        lambda: send(side, artifacts.TrashFile(created.file_id, 2, "racing binding")),
    )
    assert not isinstance(results[1], str), results
    assert not isinstance(results[0], str) or results[0] in {
        "FILE_TRASHED",
        "FILE_VERSION_NOT_READY",
        "MATERIAL_UNAVAILABLE",
        "PLAN_NOT_READY",
    }, results
    with side.uow(readonly=True) as uow:
        # A successful publication must retain the exact pinned version, never substitute latest.
        if not isinstance(results[0], str):
            spec = planning.get_revision_specification(uow, results[0].revision_id)
            assert str(spec.materials[0].file_version_id) == str(created.file_version_id)


def test_06_identical_uploads_deduplicate_bytes_but_keep_two_file_versions(recovery):
    side = recovery
    data = b"identical concurrent payload\n"
    first, second = race(lambda: add_file(side, data), lambda: add_file(side, data))
    assert isinstance(first, artifacts.AddFileResult)
    assert isinstance(second, artifacts.AddFileResult)
    assert first.file_id != second.file_id
    assert first.file_version_id != second.file_version_id
    with psycopg.connect(side.dsn) as conn:
        rows = conn.execute(
            "SELECT blob_id FROM skm_artifacts.file_versions WHERE id=ANY(%s)",
            ([first.file_version_id, second.file_version_id],),
        ).fetchall()
    assert len(rows) == 2
    assert rows[0] == rows[1]


def test_05_physical_cleanup_preserves_revision_bound_bytes(recovery):
    from fixtures.execution.checkpoints import physical_cleanup_vs_binding

    physical_cleanup_vs_binding(recovery, race, send, add_file, draft)


def test_expiry_between_stages_preserves_committed_cursor(recovery):
    from fixtures.execution.checkpoints import expire_between_stages

    expire_between_stages(recovery)


def test_07_new_version_and_trash_compare_one_file_row(recovery):
    side = recovery
    created = add_file(side)
    staged = side.client.upload_blob(side.ws, (b"new bytes",), size=9)
    version = art.AddFileVersion.from_json(
        {
            "file_id": str(created.file_id),
            "expected_row_version": 2,
            "blob": staged.to_json(),
            "original_filename": "audit.txt",
            "declared_media_type": None,
            "source": {"kind": "upload"},
        }
    )
    results = race(
        lambda: send(side, version), lambda: send(side, artifacts.TrashFile(created.file_id, 2, "race"))
    )
    assert sum(not isinstance(r, str) for r in results) == 1, results
    assert any(r in {"VERSION_CONFLICT", "FILE_TRASHED"} for r in results if isinstance(r, str)), results


def start_command(side, revision):
    selection = {"task_keys": ["P1.1/U1"], "phases": []}
    report = side.client.dispatch(
        ValidateForExecution.from_json(
            {"plan_id": str(side.plan1), "revision_id": str(revision), "selection": selection}
        )
    )
    from skm.modules.execution.generated.queries import GetReadinessReport

    view = side.client.ask(GetReadinessReport(report.report_id)).to_json()
    assert report.status in {"ready", "ready_with_advisories"}, view
    return StartRun.from_json(
        {
            "plan_id": str(side.plan1),
            "revision_id": str(revision),
            "readiness_report_id": str(report.report_id),
            "overrides": {},
            "reason": "pinned revision race",
            "selection": selection,
        }
    )


@pytest.mark.parametrize(
    "publications", [1, 2], ids=["08-start-vs-publication", "12-start-vs-two-publications"]
)
def test_08_12_start_run_remains_pinned_to_invocation_revision(recovery, publications):
    side = recovery
    revision = ready_revision(side)
    command = start_command(side, revision)
    publishes = [draft(side, {"goal": f"replacement-{i}"})[2] for i in range(publications)]
    results = race(lambda: send(side, command), *(lambda cmd=cmd: send(side, cmd) for cmd in publishes))
    assert not isinstance(results[0], str), results
    with side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).get(results[0].run_id).revision_id == revision
    assert sum(not isinstance(r, str) for r in results[1:]) == 1
    if publications == 2:
        assert results[1:].count("BASE_REVISION_CHANGED") == 1


def test_09_lost_command_reply_replays_single_committed_result(recovery):
    side = recovery
    _, _, attempt, _ = make_case(side)
    claimed = recovery_claim(side)
    client = FaultyClient(side.worker1_client, FaultPlan({FaultPoint.CLIENT_AFTER_SERVER_COMMIT: 1}))
    command = execution.BeginStage(
        claim=worker_claim(side, claimed),
        stage_id="prepare",
        round_no=1,
        input_digest=claimed["instruction"]["input_digest"],
    )
    key = f"timeout:{side.new_id()}"
    with pytest.raises(InjectedFault):
        client.dispatch(command, idempotency_key=key)
    results = race(
        lambda: client.dispatch(command, idempotency_key=key),
        lambda: side.worker1_client.dispatch(command, idempotency_key=key),
    )
    assert results[0] == results[1]
    with side.uow(readonly=True) as uow:
        assert len(uow.repo(StageRepository).history(attempt.id).entries) == 1


def test_10_idempotency_key_reused_with_changed_body_is_refused(recovery):
    side = recovery
    from skm.modules.planning.generated.commands import OpenDraft

    key = f"same-key:{side.new_id()}"
    command = OpenDraft(side.plan1, "current")
    first = side.client.dispatch(command, idempotency_key=key)
    results = race(
        lambda: side.client.dispatch(command, idempotency_key=key),
        lambda: side.client.dispatch(OpenDraft(side.plan1, "empty"), idempotency_key=key),
    )
    assert results == [first, "IDEMPOTENCY_KEY_REUSED"]


def test_11_staging_gc_and_binding_serialize_consumption(recovery):
    side = recovery
    staged = side.client.upload_blob(side.ws, (b"gc payload",), size=10)
    # Expiry is a fixture input; the production GC and add_file compete for the same row/digest guard.
    # Both read the application clock, which is frozen at created_at, so expire relative to it and
    # move the clock past it. The database wall clock may still be within a second of created_at.
    with psycopg.connect(side.dsn) as conn:
        conn.execute(
            "UPDATE skm_artifacts.staged_blobs "
            "SET expires_at=created_at+interval '1 millisecond' WHERE id=%s",
            (staged.staged_blob_id,),
        )
    side.clock.advance(timedelta(seconds=1))
    results = race(
        lambda: send(side, add_file_dto(side.ws, side.proj, staged)),
        lambda: side.system.dispatch(art.ExpireStagedBlobs()),
    )
    # The blob is expired for both: add_file refuses it whether it locks first (expired) or after
    # the GC removed it (not found), and the GC expires it exactly once without an error.
    assert results[0] in {"STAGED_BLOB_EXPIRED", "NOT_FOUND"}, results
    assert not isinstance(results[1], str), results
    assert results[1].expired == 1, results


@pytest.mark.parametrize("started", [False, True])
def test_checkpoint_race_refuses_begin_and_reconfigure_until_release(recovery, started):
    side = recovery
    run, _, attempt, _ = make_case(side)
    claimed = recovery_claim(side)
    if started:
        begin(side, claimed)
    side.client.dispatch(PauseRun(run.id, "pause before next Begin"))
    with side.uow(readonly=True) as uow:
        version = uow.repo(RunRepository).get(run.id).row_version
        before = uow.repo(AttemptRepository).get(attempt.id)
    command = ReconfigureRun(run.id, version, {"execution.parallel.max_units": 1}, "parallel 2 to 1")
    results = race(lambda: begin(side, claimed), lambda: side.client.dispatch(command))
    refused = results[0]
    assert isinstance(refused, dict)
    assert refused["outcome"] == "refused"
    assert results[1] == "INVALID_TRANSITION"
    if started:
        return
    side.client.dispatch(ResumeRun(run.id))
    side.worker1_client.dispatch(
        execution.ReleaseAssignment(
            claim=worker_claim(side, claimed), reason="paused", retain_environment=True
        ),
        idempotency_key=f"release:{side.new_id()}",
    )
    with side.uow(readonly=True) as uow:
        after = uow.repo(AttemptRepository).get(attempt.id)
        assert after.continuation == before.continuation
        assert after.started_at == before.started_at
    fresh = recovery_claim(side)
    assert fresh["attempt_id"] == str(attempt.id)


def test_drained_checkpoint_applies_parallel_two_to_one_without_resetting_attempt(recovery):
    from skm.modules.execution.ports import BundleRepository
    from unit.execution.application._support import set_setting

    side = recovery
    set_setting(side, "execution.parallel.max_units", 2)
    run, task, attempt, _ = make_case(side)
    claimed = recovery_claim(side)
    side.client.dispatch(PauseRun(run.id, "drain for 2 to 1"))
    side.worker1_client.dispatch(
        execution.ReleaseAssignment(
            claim=worker_claim(side, claimed), reason="paused", retain_environment=True
        ),
        idempotency_key=f"release:{side.new_id()}",
    )
    with side.uow(readonly=True) as uow:
        version = uow.repo(RunRepository).get(run.id).row_version
        before = uow.repo(AttemptRepository).get(attempt.id)
    # The current ceiling may narrow after this checkpoint, but counters and origin stay immutable.
    from decimal import Decimal

    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
    from skm.modules.execution.ports import BudgetRepository

    with side.uow() as uow:
        uow.repo(BudgetRepository).add_accounts(
            (
                BudgetAccount(
                    side.new_id(),
                    run.id,
                    "task",
                    task.id,
                    BudgetDimension.ATTEMPTS,
                    Decimal(3),
                    Decimal(1),
                    Decimal(0),
                    1,
                ),
            )
        )
        uow.commit()
    side.client.dispatch(
        ReconfigureRun(
            run.id,
            version,
            {"execution.parallel.max_units": 1, "budgets.task.max_attempts": 1},
            "lower future attempt allowance",
        )
    )
    side.client.dispatch(ResumeRun(run.id))
    fresh = recovery_claim(side)
    assert fresh["attempt_id"] == str(attempt.id)
    assert fresh["instruction"]["input_digest"] != claimed["instruction"]["input_digest"]
    with side.uow(readonly=True) as uow:
        saved = uow.repo(AttemptRepository).get(attempt.id)
        assert saved.started_at == before.started_at
        assert saved.continuation.cause == before.continuation.cause
        assert len(uow.repo(BundleRepository).reconfigurations(run.id)) == 1
        assert uow.repo(TaskRepository).get(task.id).attempt_count == 1
    from fixtures.execution.checkpoints import future_attempt_is_blocked

    future_attempt_is_blocked(side, run, task, attempt, fresh)
