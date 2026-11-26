"""Real checks use DEVNULL, bounded shared capture, sanitized environment and the host budget."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from integration.git.conftest import make_repo
from skm.adapters.checks.command import CheckExecutor
from skm.adapters.checks.external import external_check_runner
from skm.adapters.checks.manual import manual_check_runner
from skm.adapters.checks.shell import shell_check_runner
from skm.adapters.sandbox.registry import build_isolation_registry
from skm.application_bus.host import HostContext
from skm.kernel.cancel import CancelSource
from skm.kernel.ids import RepositoryId
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.assignment import StageInstruction
from skm.modules.execution.domain.ids import CheckExecutionId, EnvironmentId
from skm.modules.execution.generated.commands import RecordStageResult
from skm.modules.execution.host.checks import CheckDeps, CheckRequest
from skm.modules.execution.host.environment import PreparedEnvironment
from skm.modules.execution.host.isolation import IsolationSpec
from skm.modules.execution.ports import StageDeps
from skm.modules.runtimes.public import ProcessOwner
from skm.platform.fs.storage_budget import StorageBudget, StorageOwnerIdentity
from skm.platform.logging.logger import get_logger
from skm.platform.system_clock import SystemClock, SystemMonotonic


class UnusedUploader:
    def upload_blob(self, content: bytes) -> JsonObject:
        raise AssertionError("check execution must defer evidence uploads to stage recording")


def check_harness(tmp_path, *, free=10**12, profile="none", process=None, runner_class=CheckExecutor):
    root = tmp_path / "repo"
    if not root.exists():
        make_repo(root)
    state = tmp_path / "state"
    storage = StorageBudget(
        tmp_path / "ledger",
        free_bytes=lambda _: free,
        identity=lambda: StorageOwnerIdentity("test-boot", os.getpid(), "test-start"),
        owner_alive=lambda _: True,
    )
    registry = build_isolation_registry(allow_unconfined=True)
    kwargs = {
        "storage": storage,
        "capture_floor_bytes": 8192,
        "state_dir": state,
        "isolation_registry": registry,
        "profile": profile,
        "host": object(),
        "sanitized_env": {"PATH": os.defpath},
        "process": process,
        "allow_pgroup_best_effort": True,
    }
    runner = runner_class(**kwargs)
    check_id, attempt_id = CheckExecutionId(uuid4()), uuid4()
    owner = ProcessOwner(
        uuid4(),
        uuid4(),
        attempt_id,
        uuid4(),
        "check",
        check_id,
        "nonce-" + uuid4().hex,
        str(state / "identity"),
    )
    isolation = IsolationSpec(
        root, (root,), (root,), (root / ".git",), False, "full", (), {}, None, (), owner
    )
    request = CheckRequest(
        check_id,
        {"argv": [sys.executable, "-c", "pass"]},
        root,
        {},
        5,
        1,
        isolation,
        {"capture_max_bytes": 4096},
    )
    environment = PreparedEnvironment(
        EnvironmentId(uuid4()), str(root), {"main": root}, (), "skm/attempt/test"
    )
    deps = CheckDeps(
        environment,
        UnusedUploader(),
        SystemClock(),
        SystemMonotonic(),
        get_logger("execution.checks"),
        CancelSource().token,
    )
    return runner, request, deps, storage, kwargs


def test_stdin_is_devnull_and_reader_never_waits(tmp_path):
    runner, request, deps, _, _ = check_harness(tmp_path)
    script = "import os,sys; print(os.readlink('/proc/self/fd/0')); print(repr(sys.stdin.buffer.read()))"
    result = runner.run(replace(request, definition={"argv": [sys.executable, "-c", script]}), deps)
    assert result.exit_code == 0
    assert not result.timed_out
    assert result.stdout_path.read_bytes() == b"/dev/null\nb''\n"
    assert not list(Path(request.isolation.owner.identity_dir).glob("*.json"))


def test_host_credentials_never_reach_check_even_when_requested(tmp_path, monkeypatch):
    secrets = {
        "DATABASE_URL": "postgresql://secret",
        "SKM_TOKEN": "worker-secret",
        "OPENAI_API_KEY": "provider-secret",
        "SSH_AUTH_SOCK": "/secret-agent",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    _, request, deps, _, options = check_harness(tmp_path)
    runner = CheckExecutor(**{**options, "sanitized_env": {"PATH": os.defpath, **secrets}})
    request = replace(
        request,
        env_allow=secrets,
        definition={
            "argv": [sys.executable, "-c", "import os,json; print(json.dumps(dict(os.environ)))"],
            "env_allow": list(secrets),
        },
    )
    result = runner.run(request, deps)
    env = json.loads(result.stdout_path.read_bytes())
    assert result.exit_code == 0
    assert set(secrets).isdisjoint(env)
    assert env["HOME"] != os.environ.get("HOME")
    assert env["CI"] == "1"
    assert "check-home" in env["HOME"]


def test_concurrent_streams_share_one_capture_ceiling_and_keep_draining(tmp_path):
    runner, request, deps, storage, _ = check_harness(tmp_path)
    script = "import os; [(os.write(1,b'o'*200+b'\\n'),os.write(2,b'e'*200+b'\\n')) for _ in range(2000)]"
    request = replace(
        request, definition={"argv": [sys.executable, "-c", script]}, output_limits={"capture_max_bytes": 512}
    )
    result = runner.run(request, deps)
    assert result.exit_code == 0
    out, err = result.stdout_path.read_bytes(), result.stderr_path.read_bytes()
    assert len(out) + len(err) <= 512
    assert b"[truncated]" in out + err
    assert storage.snapshot(tmp_path, min_free_bytes=0).reserved_bytes == 0


@pytest.mark.parametrize(("script", "expected"), [("raise SystemExit(7)", 7), ("pass", 0)])
def test_exit_code_is_a_fact(tmp_path, script, expected):
    runner, request, deps, _, _ = check_harness(tmp_path)
    result = runner.run(replace(request, definition={"argv": [sys.executable, "-c", script]}), deps)
    assert result.exit_code == expected
    assert not result.interrupted


def test_timeout_and_missing_command_are_errors(tmp_path):
    runner, request, deps, _, _ = check_harness(tmp_path)
    result = runner.run(
        replace(
            request,
            timeout_seconds=1,
            definition={"argv": [sys.executable, "-c", "import time; time.sleep(30)"]},
        ),
        deps,
    )
    assert result.timed_out
    second = replace(
        request,
        check_execution_id=uuid4(),
        isolation=replace(request.isolation, owner=replace(request.isolation.owner, unit_id=uuid4())),
    )
    second = replace(
        second,
        check_execution_id=second.isolation.owner.unit_id,
        definition={"argv": ["/nonexistent-check-binary"]},
    )
    result = runner.run(second, deps)
    assert result.spawn_error == "CHECK_COMMAND_NOT_FOUND"
    assert result.exit_code is None


def test_shell_requires_both_host_setting_and_risk_ack(tmp_path):
    _, request, deps, _, kwargs = check_harness(tmp_path)
    request = replace(request, definition={"script": "printf shell-ok", "risk_ack": True})
    runner = shell_check_runner(shell_allowed=True, **kwargs)
    result = runner.run(request, deps)
    assert result.exit_code == 0
    assert result.stdout_path.read_text() == "shell-ok"
    denied_dir = tmp_path / "denied"
    denied_dir.mkdir()
    _, denied, denied_deps, _, options = check_harness(denied_dir)
    runner = shell_check_runner(shell_allowed=False, **options)
    result = runner.run(
        replace(denied, definition={"script": "touch forbidden", "risk_ack": True}), denied_deps
    )
    assert result.spawn_error == "ValueError"
    assert not (denied.cwd / "forbidden").exists()


def test_manual_and_external_do_not_spawn_or_require_sandbox(tmp_path):
    _, request, deps, _, _ = check_harness(tmp_path)
    manual = manual_check_runner().run(
        replace(request, definition={"instructions_md": "Look at the screen"}), deps
    )
    assert manual.exit_code is None
    assert manual.spawn_error is None
    assert not manual.timed_out
    external = external_check_runner().run(request, deps)
    assert external.spawn_error == "CAPABILITY_UNAVAILABLE"


def test_summary_capture_redacts_secrets_split_across_writes(tmp_path):
    runner, request, deps, _, _ = check_harness(tmp_path)
    script = "import os; os.write(1,b'Authorization: Bearer '); os.write(1,b'secret-value-here\\n')"
    result = runner.run(replace(request, definition={"argv": [sys.executable, "-c", script]}), deps)
    assert result.exit_code == 0
    assert b"secret-value-here" not in result.stdout_path.read_bytes()


def test_escaped_report_path_is_rejected(tmp_path):
    runner, request, deps, _, _ = check_harness(tmp_path)
    result = runner.run(
        replace(request, definition={"argv": [sys.executable, "-c", "pass"], "report_files": ["../secret"]}),
        deps,
    )
    assert result.spawn_error
    assert not result.report_files


def test_stage_invalidates_check_tree_mutation(tmp_path):
    from skm.adapters.git.commit import git_vcs
    from skm.adapters.git.runner import GitRunner
    from skm.modules.execution.domain.environment import BaselineEntry
    from skm.modules.execution.domain.stage_record import StageOutcomeKind
    from skm.modules.execution.host.stages.base import StageRequest
    from skm.modules.execution.host.stages.run_checks import RunChecksStage

    runner, check, deps, _, _ = check_harness(tmp_path)
    vcs = git_vcs(GitRunner(), state_dir=tmp_path / "snapshots")
    base = vcs.head(check.cwd)
    environment = replace(
        deps.environment, baseline=(BaselineEntry("main", RepositoryId(uuid4()), base, base, None),)
    )
    stage_deps = SimpleNamespace(
        environment=environment,
        vcs=vcs,
        check_runners=SimpleNamespace(get=lambda _: runner),
        uploader=deps.uploader,
        clock=deps.clock,
        monotonic=deps.monotonic,
        log=deps.log,
        cancel=deps.cancel,
        config=SimpleNamespace(get=lambda _: 4096),
    )
    script = "from pathlib import Path; Path('file.txt').write_text('check mutation')"
    payload = {
        "check_execution_id": str(check.check_execution_id),
        "check_spec_id": str(uuid4()),
        "kind": "command",
        "definition": {"argv": [sys.executable, "-c", script]},
    }
    request = StageRequest(StageInstruction(kind="run_stage", params={}), {"checks": [payload]}, None, {})
    stage = RunChecksStage(
        isolation=lambda *a: check.isolation,
        read_capture=lambda p: p.read_bytes(),
        verify_environment=lambda _: None,
        candidate_marks=lambda *a: {"main": {}},
    )
    result = stage.run(request, cast("StageDeps", stage_deps))
    from skm.platform.schema.registry import SchemaRegistry

    SchemaRegistry.load_default().require_valid(
        "urn:skm:execution:stage-outcome-run-checks:v1", dict(result.payload)
    )
    assert result.kind is StageOutcomeKind.TREE_CHANGED
    assert result.payload["tree_changed"] is True
    assert len(result.files) == 2
    results = result.payload["results"]
    assert isinstance(results, list)
    assert isinstance(results[0], dict)
    assert results[0]["state"] == "unknown"
    assert (check.cwd / "file.txt").read_text() == "check mutation"


def test_candidate_drift_before_check_rejects_without_spawn(tmp_path):
    from skm.adapters.git.commit import git_vcs
    from skm.adapters.git.runner import GitRunner
    from skm.modules.execution.domain.environment import BaselineEntry
    from skm.modules.execution.domain.stage_record import StageOutcomeKind
    from skm.modules.execution.host.stages.base import StageRequest
    from skm.modules.execution.host.stages.run_checks import RunChecksStage

    _, check, deps, _, _ = check_harness(tmp_path)
    vcs = git_vcs(GitRunner(), state_dir=tmp_path / "snapshots")
    base = vcs.head(check.cwd)
    environment = replace(
        deps.environment, baseline=(BaselineEntry("main", RepositoryId(uuid4()), base, base, None),)
    )
    (check.cwd / "file.txt").write_text("edited after seal")
    stage = RunChecksStage(
        isolation=lambda *a: pytest.fail("must not build launch"),
        read_capture=lambda _: b"",
        verify_environment=lambda _: None,
        candidate_marks=lambda *a: {"main": {}},
    )
    result = stage.run(
        StageRequest(StageInstruction(kind="run_stage", params={}), {"checks": []}, None, {}),
        cast("StageDeps", SimpleNamespace(environment=environment, vcs=vcs)),
    )
    from skm.platform.schema.registry import SchemaRegistry

    SchemaRegistry.load_default().require_valid(
        "urn:skm:execution:stage-outcome-run-checks:v1", dict(result.payload)
    )
    assert result.kind is StageOutcomeKind.TREE_CHANGED


def test_full_evidence_uploads_precede_result_and_failure_prevents_dispatch(tmp_path):
    from skm.modules.execution.host.evidence import EvidenceFile, record_with_evidence

    _, check, _, _, _ = check_harness(tmp_path)
    files = []
    for name in ("stdout", "stderr"):
        path = tmp_path / name
        path.write_bytes((name.encode() + b"\n") * 1000)
        files.append(
            EvidenceFile(
                path, "check_execution:" + str(check.check_execution_id), "evidence", name, "text/plain"
            )
        )
    calls = []

    class Uploader:
        def upload_blob(self, content):
            calls.append(("upload", len(content)))
            return {
                "staged_blob_id": str(uuid4()),
                "workspace_id": str(uuid4()),
                "digest": "sha256:" + "1" * 64,
                "size": len(content),
                "media_type": "text/plain",
            }

    class Client:
        def dispatch(self, command, **kwargs):
            calls.append(("dispatch", command))
            return {"recorded": True}

    raw: RecordStageResult = {
        "claim": {
            "assignment_id": str(uuid4()),
            "attempt_id": str(check.isolation.owner.attempt_id),
            "worker_id": str(check.isolation.owner.worker_id),
            "fencing_token": 1,
        },
        "stage_record_id": str(uuid4()),
        "outcome_kind": "success",
        "outcome": {"results": []},
    }
    ctx = cast("HostContext", SimpleNamespace(client=Client()))
    result = record_with_evidence(
        ctx,
        raw,
        files=files,
        uploader=Uploader(),
        read=lambda p: p.read_bytes(),
        idempotency_key="result-key",
        command_factory=lambda command: command,
    )
    assert result == {"recorded": True}
    assert [name for name, _ in calls] == ["upload", "upload", "dispatch"]
    assert calls[0][1] == files[0].path.stat().st_size
    assert len(calls[-1][1]["evidence"]) == 2
    calls.clear()

    def unavailable(path):
        raise OSError("evidence unavailable")

    with pytest.raises(OSError, match="unavailable"):
        record_with_evidence(
            ctx,
            raw,
            files=files,
            uploader=Uploader(),
            read=unavailable,
            idempotency_key="result-key",
            command_factory=lambda command: command,
        )
    assert not calls
