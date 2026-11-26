"""Real bus boundary: raw output identity, scope, prepare evidence and host binding."""

import base64
from copy import deepcopy
from dataclasses import replace
from typing import Any, cast
from uuid import UUID

import pytest

from contracts.execution._worker_protocol_support import begin, claim, make_case, worker_claim
from contracts.execution.harness import exec_side as exec_side
from skm.kernel.errors import SkmError
from skm.kernel.ids import EntityId
from skm.modules.artifacts import public as artifacts
from skm.modules.execution import public as execution
from skm.modules.execution.domain.output import (
    ChangedPath,
    DiffStats,
    OutputManifest,
    OutputMount,
    display_path,
    manifest_to_json,
    output_tree_digest,
)
from skm.modules.execution.domain.task import PathPattern
from skm.modules.execution.ports import (
    EnvironmentRepository,
    EvidenceBindingRepository,
    OutputRepository,
    TaskRepository,
)
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database


def changed(raw, *, old=None):
    return ChangedPath(
        "repo",
        display_path(raw),
        base64.urlsafe_b64encode(raw).decode().rstrip("="),
        "modified" if old is None else "renamed",
        None if old is None else display_path(old),
        None if old is None else base64.urlsafe_b64encode(old).decode().rstrip("="),
        "100644 " + "4" * 40,
    )


def manifest(side, paths):
    mounts = (OutputMount("repo", side.repo_id, "sha1", "1" * 40, "2" * 40, "3" * 40),)
    return cast(
        "dict[str, Any]",
        manifest_to_json(
            OutputManifest(
                "skm-output-v2",
                mounts,
                tuple(paths),
                output_tree_digest(mounts, paths),
                (),
                (),
                None,
                DiffStats(len(paths), 0, 0),
                not paths,
            )
        ),
    )


def active_executor(side):
    from contracts.execution.test_step_notes import owned_agent

    _, task, attempt, claimed, stage, step, _, _, _ = owned_agent(side)
    with side.uow() as uow:
        repo = uow.repo(TaskRepository)
        repo.save(
            replace(task, declared_write_scope=(PathPattern("repo", "src/*.py"),)),
            expected_version=task.row_version,
        )
        uow.commit()
    return attempt, claimed, {"stage_record_id": str(stage.id), "step_id": str(step.id)}


def seal(side, claimed, ready, raw):
    return side.worker1_client.dispatch(
        execution.SealOutput(
            claim=worker_claim(side, claimed),
            stage_record_id=ready["stage_record_id"],
            source="executor",
            step_id=ready["step_id"],
            manifest=raw,
        ),
        idempotency_key=f"seal:{side.new_id()}",
    )


def test_server_rehashes_before_writes_and_recomputes_scope(exec_side):
    side = exec_side
    attempt, claimed, ready = active_executor(side)
    paths = [
        changed(b"src/top.py"),
        changed(b"src/deep/nested.py"),
        changed(b"outside/new.py", old=b"src/old.py"),
        changed(b"src/\xff.py"),
    ]
    raw = manifest(side, paths)
    malformed = []
    bad = deepcopy(raw)
    bad["tree_digest"] = "sha256:" + "0" * 64
    malformed.append(bad)
    bad = deepcopy(raw)
    bad["mounts"][0]["head_commit"] = "9" * 40
    malformed.append(bad)
    bad = deepcopy(raw)
    bad["changed_paths"][2]["old_path"] = "src/forged.py"
    malformed.append(bad)
    bad = deepcopy(raw)
    bad["changed_paths"][0]["fingerprint"] = "160000 " + "4" * 40
    malformed.append(bad)
    malformed.append(manifest(side, [changed(b".skm/runtime.log")]))
    malformed.append(manifest(side, [changed(b".skm/\xff")]))
    for bad in malformed:
        with pytest.raises(SkmError):
            seal(side, claimed, ready, bad)
        with side.uow(readonly=True) as uow:
            assert uow.repo(OutputRepository).latest(attempt.id) is None
    # Client-provided outside/excluded lists never authorize scope or exclusion decisions.
    raw["outside_write_scope"] = [deepcopy(raw["changed_paths"][0])]
    raw["excluded_paths"] = manifest(side, [changed(b".skm/runtime.log"), changed(b"user.txt")])[
        "changed_paths"
    ]
    result = seal(side, claimed, ready, raw)
    with side.uow(readonly=True) as uow:
        output = uow.repo(OutputRepository).get(UUID(result["output_id"]))
        assert output.manifest.tree_digest == raw["tree_digest"]
        assert output.manifest.outside_write_scope == tuple(paths[1:])
        assert [p.path for p in output.manifest.excluded_paths] == [".skm/runtime.log"]


def patch(side, attempt, filename, content):
    from datetime import timedelta

    # PostgreSQL fences use database time; the shared harness intentionally starts in the past.
    upload_time = side.clock.now()
    with side.uow() as uow:
        if getattr(uow, "connection", None) is not None:
            now = uow.connection.execute("SELECT clock_timestamp()").fetchone()[0]
            side.clock.set(now + timedelta(seconds=10))
    staged = side.client.upload_blob(side.ws, (content,), size=len(content), media_type="text/x-patch")
    side.clock.set(upload_time)
    return {
        "owner": "attempt",
        "owner_id": str(attempt.id),
        "role": "patch",
        "filename": filename,
        "media_type": "text/x-patch",
        "staged_blob": staged.to_json(),
    }


def preparation(side, attempt):
    locator = f"/owned/environments/{attempt.id}"
    return {
        "environment_id": str(side.new_id()),
        "kind": "existing_checkout",
        "branch": f"skm/attempt/{attempt.id}",
        "mounts": [
            {
                "mount": name,
                "local_locator": f"/user/{name}",
                "environment_locator": locator,
                "dirty_patch_filename": f"{name}.dirty.patch",
            }
            for name in ("repo", "other")
        ],
        "baseline": [
            {
                "mount": name,
                "repository_id": str(side.repo_id),
                "commit_sha": oid * 40,
                "source_head_sha": "1" * 40,
                "dirty_patch_file_version_id": None,
            }
            for name, oid in (("repo", "2"), ("other", "3"))
        ],
    }


def record(side, claimed, ready, outcome, evidence):
    return side.worker1_client.dispatch(
        execution.RecordStageResult(
            claim=worker_claim(side, claimed),
            stage_record_id=ready["stage_record_id"],
            outcome_kind="success",
            outcome=outcome,
            evidence=evidence,
        ),
        idempotency_key=f"record:{side.new_id()}",
    )


def test_prepare_binds_each_fresh_patch_and_owned_locator(exec_side):
    side = exec_side
    _, _, attempt, _ = make_case(side)
    claimed = claim(side)
    ready = begin(side, claimed)
    outcome = preparation(side, attempt)
    evidence = [
        patch(side, attempt, f"{name}.dirty.patch", f"{name} patch bytes".encode())
        for name in ("repo", "other")
    ]
    for field in ("forged_id", "foreign_locator", "missing_patch", "ambiguous_patch"):
        bad = deepcopy(outcome)
        files = evidence
        if field == "forged_id":
            bad["baseline"][0]["dirty_patch_file_version_id"] = str(side.fv1)
        elif field == "foreign_locator":
            bad["mounts"][0]["environment_locator"] = f"/owned/{side.new_id()}"
        elif field == "missing_patch":
            files = evidence[:1]
        else:
            bad["mounts"][1]["dirty_patch_filename"] = "repo.dirty.patch"
        with pytest.raises(SkmError):
            record(side, claimed, ready, bad, files)
        with side.uow(readonly=True) as uow:
            assert uow.repo(EnvironmentRepository).for_attempt(attempt.id) is None
            assert not uow.repo(EvidenceBindingRepository).for_owner("attempt", attempt.id)
    record(side, claimed, ready, outcome, evidence)
    with side.uow(readonly=True) as uow:
        env = uow.repo(EnvironmentRepository).for_attempt(attempt.id)
        assert env.local_locator == f"/owned/environments/{attempt.id}"
        versions = uow.repo(artifacts.FileVersionRepository)
        assert [versions.get(b.dirty_patch_file_version_id).original_filename for b in env.baseline] == [
            "repo.dirty.patch",
            "other.dirty.patch",
        ]
        assert len({b.dirty_patch_file_version_id for b in env.baseline}) == 2
        assert [b.commit_sha for b in env.baseline] == ["2" * 40, "3" * 40]
        assert {b.source_head_sha for b in env.baseline} == {"1" * 40}


@pytest.mark.parametrize("expected_exit", [0, 7])
def test_check_results_keep_precise_errors_and_tree_invalidation(exec_side, monkeypatch, expected_exit):
    from types import SimpleNamespace

    from contracts.context.harness import CHK_ID
    from contracts.execution.seed_helpers import seed_output
    from skm.modules.execution.application._worker_host_stages import record_checks
    from skm.modules.execution.domain.check_execution import CheckExecution, CheckKind, CheckState
    from skm.modules.execution.domain.stage_record import (
        StageOutcomeKind,
        begin_stage_record,
        complete_stage,
    )
    from skm.modules.execution.domain.workflow.stage_inputs import StageMode
    from skm.modules.execution.ports import CheckRepository, StageRepository

    if expected_exit:
        monkeypatch.setattr(
            "skm.modules.execution.application._worker_host_stages.check_definitions",
            lambda *_: (
                SimpleNamespace(
                    id=EntityId(UUID(CHK_ID)), definition=SimpleNamespace(expected_exit=expected_exit)
                ),
            ),
        )
    side = exec_side
    run, task, attempt, _ = make_case(side, env=True)
    with side.uow() as uow:
        output = seed_output(side, uow, attempt)
        records, results, stages = [], [], []
        cases = [
            ("command", "error", None, "CHECK_COMMAND_NOT_FOUND"),
            ("command", "error", None, "CHECK_TIMEOUT"),
            ("command", "failed", -9, "CHECK_KILLED"),
            ("command", "error", None, "CHECK_MISCONFIGURED"),
            ("command", "passed", expected_exit, None),
            ("command", "failed", 0 if expected_exit else 1, None),
            ("command", "unknown", None, None),
            ("manual", "manual_pending", None, "MANUAL_PENDING"),
        ]
        for round_no, (kind, state, exit_code, code) in enumerate(cases, 1):
            stage_repo = uow.repo(StageRepository)
            stage = begin_stage_record(
                [entry.record for entry in stage_repo.history(attempt.id).entries],
                record_id=side.new_id(),
                attempt_id=attempt.id,
                run_id=run.id,
                task_id=task.id,
                stage_id=f"checks_{round_no}",
                stage_type="run_checks",
                round_no=1,
                mode=StageMode.NORMAL,
                input_digest="sha256:" + "a" * 64,
                fencing_token=1,
                now=side.clock.now(),
            )
            stage = complete_stage(
                stage, outcome_kind=StageOutcomeKind.SUCCESS, outcome={}, now=side.clock.now()
            )
            stage_repo.add(stage)
            stages.append(stage)
            check = CheckExecution(
                side.new_id(),
                side.ws,
                run.id,
                task.id,
                attempt.id,
                output.id,
                EntityId(UUID(CHK_ID)),
                "check:key",
                CheckKind(kind),
                True,
                CheckState.PENDING,
                None,
                "",
                None,
                None,
                "sha256:" + "a" * 64,
                None,
                None,
                round_no,
            )
            records.append(check)
            results.append(
                {
                    "check_execution_id": str(check.id),
                    "check_spec_id": str(check.check_spec_id),
                    "state": state,
                    "exit_code": exit_code,
                    "summary": (f"{code}: " if code else "") + "first\n" + "long log\n" * 500,
                }
            )
        repo = uow.repo(CheckRepository)
        repo.add_many(records)
        fenced = SimpleNamespace(attempt=attempt, now=side.clock.now())
        for stage, result in zip(stages, results, strict=True):
            if result["state"] == "error":
                with pytest.raises(SkmError, match="contradicts"):
                    record_checks(uow, fenced, stage, {"results": [{**result, "state": "passed"}]})
            record_checks(uow, fenced, stage, {"results": [result]})
        saved = [repo.get(c.id) for c in records]
        assert [c.error_code for c in saved] == [case[3] for case in cases]
        assert [c.state.value for c in saved] == [
            "error",
            "error",
            "error",
            "error",
            "passed",
            "failed",
            "unknown",
            "manual_pending",
        ]
        assert all(len(c.summary) <= 4000 and len(c.summary.splitlines()) <= 41 for c in saved)
        for stage, result in zip(stages, results, strict=True):
            record_checks(uow, fenced, stage, {"results": [result], "tree_changed": True})
        assert {repo.get(c.id).state for c in records} == {CheckState.UNKNOWN}
        assert {repo.get(c.id).error_code for c in records} == {"CHECK_TREE_CHANGED"}
        uow.commit()
