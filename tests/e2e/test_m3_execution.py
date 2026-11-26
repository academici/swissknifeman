"""M3: PostgreSQL DAG, OS workers, failed check/review correction, pinned material, typed replay."""

import json

import psycopg
import pytest

from fixtures.execution.harness import clean_test_database, pg_session, recovery, test_database
from fixtures.execution.m3 import (
    KEYS,
    assert_rework_trace,
    assert_shared_budget,
    dag,
    rebuild,
    scripts,
    start,
)
from fixtures.execution.m3_recovery import interrupt_first_executor
from fixtures.execution.processes import worker
from integration.git.conftest import make_repo
from skm.modules.artifacts.domain.blob import LocationState
from skm.modules.artifacts.ports import BlobRepository, FileVersionRepository
from skm.modules.context import public as context
from skm.modules.execution.generated.queries import GetRunHistory
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AssignmentRepository,
    AttemptRepository,
    OutputRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)
from support.service_runner import Instance, ServiceRunner

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = [pytest.mark.pg, pytest.mark.e2e]


def test_material_lost_after_start_blocks_ready_task_without_an_attempt(recovery):
    from fixtures.execution.harness import system_dispatch
    from fixtures.execution.planning import ready_revision
    from recovery.test_concurrency import start_command
    from skm.modules.execution.domain.budget import BudgetDimension
    from skm.modules.execution.ports import BudgetRepository

    side = recovery
    started = side.client.dispatch(start_command(side, ready_revision(side)))
    with side.uow() as uow:
        tasks = uow.repo(TaskRepository).list_for_run(started.run_id)
        assert any(t.status.value == "ready" for t in tasks)
        version = uow.repo(FileVersionRepository).get(side.fv1)
        for location in uow.repo(BlobRepository).locations(version.blob_id):
            uow.repo(BlobRepository).mark_location(
                version.blob_id, location.backend_id, LocationState.MISSING, side.clock.now()
            )
        uow.commit()
    for _ in range(2):
        system_dispatch(side, "schedule_ready_tasks")
        with side.uow(readonly=True) as uow:
            tasks = uow.repo(TaskRepository).list_for_run(started.run_id)
            assert all(t.current_attempt_id is None and t.attempt_count == 0 for t in tasks)
            assert any(
                t.status.value == "blocked" and t.blocking_reason.code.value == "BLOCKED_BY_MATERIAL"
                for t in tasks
            )
            accounts = [
                account
                for task in tasks
                for account in uow.repo(BudgetRepository).accounts_for(
                    started.run_id, task.id, BudgetDimension.ATTEMPTS
                )
            ]
            assert accounts
            assert all(a.spent == 0 and a.reserved == 0 for a in accounts)


def test_three_task_dag_reworks_reviews_integrates_and_rebuilds_history(recovery):  # noqa: PLR0915 - one end-to-end acceptance trace
    side = recovery
    repository = side.root / "m3-repository"
    git, _ = make_repo(repository)
    (repository / "src").mkdir()
    (repository / "src/target.py").write_text("answer = 0\n")
    from fixtures.execution.protocol import AUTHOR

    git.run(repository, ["add", "."])
    git.run_bytes(repository, ["commit", "-m", "M3 baseline"], env=AUTHOR)
    revision = dag(side)
    started = start(side, revision)
    run_id = started.run_id
    git.run(repository, ["branch", f"skm/integration/{run_id}", "main"])
    script_path = scripts(side, interrupted=True)
    with ServiceRunner(side) as services:
        Instance.wait_until(services.healthy, description="M3 services")
        interrupt_first_executor(side, run_id, repository, script_path)
        # Every worker is a fresh external process; its one assignment includes the complete workflow.
        for _ in KEYS:

            def available():
                with side.uow(readonly=True) as uow:
                    return any(
                        a.state.value == "available"
                        for task in uow.repo(TaskRepository).list_for_run(run_id)
                        if task.current_attempt_id
                        for a in uow.repo(AssignmentRepository).for_attempt(task.current_attempt_id)
                    )

            Instance.wait_until(available, timeout=30, description="next DAG assignment")
            with worker(side, repository, script_path) as process:
                process.wait(timeout=300)
                stdout = (side.root / "worker.stdout").read_text()
                stderr = (side.root / "worker.stderr").read_text()
                assert process.returncode == 0, stdout + stderr
                slots = json.loads(stdout)["slots"]
                assert len(slots) == 1, stdout + stderr
                assert slots[0].get("reason") is None, stdout + stderr
                assert slots[0]["assignments"] == 1, stdout + stderr

        def succeeded():
            assert services.healthy()
            with side.uow(readonly=True) as uow:
                return uow.repo(RunRepository).get(run_id).status.value == "succeeded"

        Instance.wait_until(succeeded, description="all checked integrations accepted")
    with side.uow(readonly=True) as uow:
        tasks = {t.display_key: t for t in uow.repo(TaskRepository).list_for_run(run_id)}
        assert set(tasks) == set(KEYS)
        assert all(task.status.value == "accepted" for task in tasks.values())
        first = tasks[KEYS[0]]
        assert first.check_fix_rounds == 1
        assert first.review_rounds == 2
        for task in tasks.values():
            decisions = uow.repo(AcceptanceRepository).decisions_for_task(task.id)
            assert len(decisions) == 1
            assert task.attempt_count == 1
        attempt = uow.repo(AttemptRepository).get(first.current_attempt_id)
        history = uow.repo(StageRepository).history(attempt.id).entries
        assert_rework_trace(history)
        executor_steps = [s for entry in history for s in entry.steps if s.role.value == "executor"]
        assert len(executor_steps) == 4
        assert sum(s.state.value == "succeeded" for s in executor_steps) == 3
        assert (
            uow.connection.execute(
                "SELECT count(*) FROM skm_execution.attempt_outputs WHERE attempt_id=%s", (attempt.id,)
            ).fetchone()[0]
            == 3
        )
        summaries = uow.connection.execute(
            "SELECT summary FROM skm_execution.check_executions WHERE attempt_id=%s", (attempt.id,)
        ).fetchall()
        assert any("M3 exact feedback: expected 42" in row[0] for row in summaries)
        assert [s.model for s in executor_steps] == ["fake-a", "fake-a", "fake-b", "fake-b"]
        # Every reroute/rework owns its own context; an earlier prompt cannot authorize a later step.
        assert len({s.context_manifest_id for s in executor_steps}) == len(executor_steps)
        for entry in history:
            for step in entry.steps:
                manifest = context.require_final(uow, step.context_manifest_id)
                assert manifest.owner_ref == f"step:{step.id}"
                assert manifest.model == step.model
                assert manifest.prompt_digest
                assert manifest.prompt_file_version_id
                assert manifest.estimator_id == side.estimator.estimator_id
        assert all(s.admission["operation"] == "bounded_fix" for s in executor_steps[2:])
        assert not uow.repo(OutputRepository).latest(attempt.id).manifest.empty
        assert all(s.finished_at is not None for entry in history for s in entry.steps)
    assert_shared_budget(side, run_id, tasks.values())
    cutoff, baseline = rebuild(side, run_id)
    text = json.dumps(baseline)
    assert "acceptance" in text
    assert "integration" in text
    assert "secret://" not in text
    # K3 is checked from committed event order, including the post-integration recheck.
    positions = {}
    for entry in baseline:
        for node in entry.get("nodes", []):
            if node.get("ref", {}).get("kind") == "task":
                positions.setdefault(node["ref"]["id"], []).append((entry["seq"], node.get("state")))
    parent_accepted = min(seq for seq, state in positions[str(tasks[KEYS[0]].id)] if state == "accepted")
    dependent_assigned = min(seq for seq, state in positions[str(tasks[KEYS[2]].id)] if state == "assigned")
    assert parent_accepted < dependent_assigned
    side.app.config.clear_cache()
    with psycopg.connect(side.dsn) as conn:
        # Only operational result text is changed; fixed-cutoff immutable events remain authoritative.
        conn.execute(
            "UPDATE skm_execution.attempt_steps SET result = result || %s::jsonb WHERE attempt_id=%s",
            (json.dumps({"summary": "HISTORY-METADATA-CANARY"}), attempt.id),
        )
    _, replay = rebuild(side, run_id, through=cutoff)
    assert replay == baseline
    assert "HISTORY-METADATA-CANARY" not in json.dumps(replay)
    page = side.client.ask(GetRunHistory(run_id, through_seq=cutoff, limit=200)).to_json()
    assert page["through_seq"] == cutoff


def test_missing_pinned_material_blocks_scheduling_without_substituting_new_version(recovery):
    from fixtures.execution.harness import system_dispatch
    from fixtures.execution.planning import ready_revision
    from recovery.test_concurrency import start_command
    from skm.modules.artifacts.generated import commands as art

    side = recovery
    revision = ready_revision(side)
    from unit.execution.application._support import set_setting

    set_setting(side, "execution.readiness.required", False)
    command = start_command(side, revision)
    with side.uow() as uow:
        version = uow.repo(FileVersionRepository).get(side.fv1)
        blob = uow.repo(BlobRepository)
        locations = blob.locations(version.blob_id)
        for location in locations:
            blob.mark_location(version.blob_id, location.backend_id, LocationState.MISSING, side.clock.now())
        uow.commit()
    newer = side.client.upload_blob(side.ws, (b"guide v2",), size=8)
    added = side.client.dispatch(
        art.AddFileVersion.from_json(
            {
                "file_id": str(version.file_id),
                "expected_row_version": 2,
                "blob": newer.to_json(),
                "original_filename": "guide.txt",
                "declared_media_type": None,
                "source": {"kind": "upload"},
            }
        ),
        idempotency_key=f"material-v2:{side.new_id()}",
    )
    started = side.client.dispatch(command)
    system_dispatch(side, "schedule_ready_tasks")
    with side.uow(readonly=True) as uow:
        tasks = uow.repo(TaskRepository).list_for_run(started.run_id)
        assert tasks
        assert all(task.blocking_reason.code.value == "BLOCKED_BY_MATERIAL" for task in tasks)
        assert all(task.current_attempt_id is None for task in tasks)
    # The revision still references v1 although a distinct v2 is now the file's latest version.
    from skm.modules.planning import public as planning

    with side.uow(readonly=True) as uow:
        spec = planning.get_revision_specification(uow, revision)
        assert str(spec.materials[0].file_version_id) == str(side.fv1)
    from fixtures.execution.materials import restore_and_assert_pinned_grant

    restore_and_assert_pinned_grant(side, started.run_id, version, locations, added.file_version_id)
