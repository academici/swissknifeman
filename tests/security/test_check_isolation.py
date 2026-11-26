"""Checks cannot bypass wrap, disk admission or uncertain process cleanup."""

import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from integration.checks.test_check_stdin import check_harness
from skm.adapters.checks.command import CheckExecutor, ReproductionRunner
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonValue
from skm.modules.execution.domain.assignment import StageInstruction
from skm.modules.execution.domain.check_execution import CheckKind, CheckState, classify_check_result
from skm.modules.execution.host.isolation import WrappedCommand
from skm.modules.execution.ports import StageDeps
from skm.modules.runtimes.public import ProcessOwnership
from skm.platform.fs.storage_budget import BudgetedFile
from skm.platform.process.identity import identity_of


class NoSpawn:
    def __init__(self):
        self.calls = []

    def validate(self, command):
        self.calls.append(command)
        raise AssertionError("validation must not be reached")

    def spawn(self, *args, **kwargs):
        raise AssertionError("spawn must not be reached")


@pytest.mark.parametrize("profile", ["worktree", "landlock", "missing"])
def test_unproved_required_properties_reject_malicious_check_before_spawn(tmp_path, profile):
    process = NoSpawn()
    runner, request, deps, _, _ = check_harness(tmp_path, profile=profile, process=process)
    secret = tmp_path / "host-secret"
    secret.write_text("host canary")
    script = (
        f"import pathlib,socket; pathlib.Path({str(secret)!r}).read_text(); "
        f"pathlib.Path({str(tmp_path / 'outside')!r}).write_text('bad'); "
        "socket.socket().connect(('127.0.0.1',9))"
    )
    request = replace(
        request,
        definition={"argv": [sys.executable, "-c", script]},
        isolation=replace(request.isolation, network="none"),
    )
    result = runner.run(request, deps)
    assert result.spawn_error == "SANDBOX_UNAVAILABLE"
    assert result.exit_code is None
    assert not process.calls
    assert not (tmp_path / "outside").exists()
    assert secret.read_text() == "host canary"


def test_wrap_is_required_and_only_wrapped_argv_is_spawned(tmp_path):
    runner, request, deps, _, _ = check_harness(tmp_path)
    events = []

    class Backend:
        def available(self, host):
            events.append("available")
            return {"available": True}

        def wrap(self, argv, spec):
            events.append("wrap")
            intent = Path(spec.owner.identity_dir) / (str(spec.owner.unit_id) + ".intent.json")
            import json

            assert json.loads(intent.read_text())["owner_nonce"] == spec.owner.owner_nonce
            ownership = ProcessOwnership(spec.owner, "pgroup_best_effort", "group:" + str(spec.owner.unit_id))
            return WrappedCommand(
                (sys.executable, "-c", "print('wrapped-only')"), spec.env, spec.workdir, ownership
            )

    runner.registry = SimpleNamespace(get=lambda _: Backend())
    result = runner.run(replace(request, definition={"argv": ["/this-raw-command-must-not-run"]}), deps)
    assert events == ["available", "wrap"]
    assert result.exit_code == 0
    assert result.stdout_path.read_text() == "wrapped-only\n"


@pytest.mark.parametrize("runner_class", [CheckExecutor, ReproductionRunner])
def test_disk_floor_rejects_check_and_reproduction_before_wrap_or_spawn(tmp_path, runner_class):
    process = NoSpawn()
    runner, request, deps, _, _ = check_harness(
        tmp_path, free=8192, process=process, runner_class=runner_class
    )
    with pytest.raises(SkmError):
        runner.run(request, deps)
    assert not process.calls
    assert not (Path(request.isolation.owner.identity_dir)).exists()


@pytest.mark.parametrize("reason", ["permission", "unknown_reap", "close_failure"])
def test_permission_or_unknown_reap_never_becomes_passed(tmp_path, reason):
    class Process:
        pid = os.getpid()
        identity = identity_of(os.getpid())

        def confirmed(self, ownership):
            return True

        def empty(self):
            return True if reason == "close_failure" else None

        def signal(self, sig):
            raise PermissionError("cannot signal")

        def pump(self):
            pass

        def poll(self):
            if reason == "unknown_reap":
                raise ChildProcessError("status unknown")
            return 0

        def close(self):
            raise PermissionError("cannot prove reap")

    class Launcher:
        def validate(self, command):
            pass

        def spawn(self, command, **kwargs):
            return Process()

    runner, request, deps, _, _ = check_harness(tmp_path, process=Launcher())
    result = runner.run(request, deps)
    state, _ = classify_check_result(
        CheckKind.COMMAND, result.exit_code, result.timed_out, result.spawn_error, result.interrupted
    )
    assert state is not CheckState.PASSED
    assert runner._pending
    assert list(Path(request.isolation.owner.identity_dir).glob("*.json"))


def test_fsync_failure_retains_capture_reservation_until_reconcile(tmp_path, monkeypatch):
    runner, request, deps, storage, _ = check_harness(tmp_path)
    close = BudgetedFile.close

    def fail(writer):
        raise OSError("capture fsync unconfirmed")

    monkeypatch.setattr(BudgetedFile, "close", fail)
    with pytest.raises(OSError, match="fsync"):
        runner.run(request, deps)
    assert storage.snapshot(tmp_path, min_free_bytes=0).reserved_bytes > 0
    monkeypatch.setattr(BudgetedFile, "close", close)
    assert storage.reconcile(tmp_path).reserved_bytes > 0  # still-live/unknown owner is never reclaimed


def test_crash_keeps_full_shared_capture_reservation(tmp_path):
    runner, request, deps, storage, _ = check_harness(tmp_path)

    class CrashBackend:
        def available(self, host):
            return {"available": True}

        def wrap(self, argv, spec):
            os._exit(0)

    runner.registry = SimpleNamespace(get=lambda _: CrashBackend())
    child = os.fork()
    if child == 0:
        try:
            runner.run(request, deps)
        finally:
            os._exit(2)
    _, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    maximum = request.output_limits["capture_max_bytes"]
    assert isinstance(maximum, int)
    assert storage.snapshot(tmp_path, min_free_bytes=0).reserved_bytes >= maximum


@pytest.mark.parametrize("restriction", ["readonly", "network"])
def test_explicit_unconfined_consent_does_not_weaken_required_properties(tmp_path, restriction):
    runner, request, deps, _, _ = check_harness(tmp_path)
    spec = (
        replace(request.isolation, read_only_root=True)
        if restriction == "readonly"
        else replace(request.isolation, network="none")
    )
    result = runner.run(replace(request, isolation=spec), deps)
    assert result.spawn_error == "SANDBOX_UNAVAILABLE"
    assert result.exit_code is None


def test_pidfd_failure_prevents_command_execution(tmp_path, monkeypatch):
    from threading import Event

    runner, request, deps, _, _ = check_harness(tmp_path)
    canary = tmp_path / "command-executed"
    real_open, calls = os.pidfd_open, []

    def denied(pid, flags=0):
        calls.append(pid)
        if len(calls) >= 3:
            raise PermissionError("pidfd refused after launcher admission")
        return real_open(pid, flags)

    monkeypatch.setattr(os, "pidfd_open", denied)
    result = runner.run(
        replace(
            request,
            definition={
                "argv": [
                    sys.executable,
                    "-c",
                    f"from pathlib import Path; Path({str(canary)!r}).write_text('executed')",
                ]
            },
        ),
        deps,
    )
    assert len(calls) == 3
    assert result.spawn_error
    assert result.exit_code is None
    Event().wait(0.2)  # the old post-Popen pidfd failure let the command write this canary
    assert not canary.exists()


@pytest.mark.parametrize("cleanup_denied", [False, True])
def test_partial_check_initialization_retains_owned_child_until_reaped(tmp_path, monkeypatch, cleanup_denied):
    import skm.adapters.checks.lifecycle as lifecycle
    from skm.platform.process.ownership import discard

    runner, request, deps, _, options = check_harness(tmp_path)
    canary = tmp_path / "command-executed"
    handles, launch = [], lifecycle.launch

    def denied(*args):
        raise PermissionError("initialization refused")

    def capture(*args, **kwargs):
        pipes, owned = launch(*args, **kwargs)
        handles.append((pipes, owned))
        if cleanup_denied:
            monkeypatch.setattr(owned, "signal_group", denied)
        return pipes, owned

    monkeypatch.setattr(lifecycle, "launch", capture)
    monkeypatch.setattr(lifecycle.selectors, "DefaultSelector", denied)
    try:
        result = runner.run(
            replace(
                request,
                definition={
                    "argv": [
                        sys.executable,
                        "-c",
                        f"from pathlib import Path; Path({str(canary)!r}).write_text('executed')",
                    ]
                },
            ),
            deps,
        )
        assert result.exit_code is None
        assert result.spawn_error == "PermissionError"
        assert not canary.exists()  # the actual command is still behind the release gate
        assert len(handles) == 1
        pipes, owned = handles[0]
        if cleanup_denied:
            assert runner._pending
            assert owned._pidfd is not None
            with pytest.raises(SkmError, match="reap/reconcile"):
                CheckExecutor(**options).run(request, deps)
        else:
            assert not runner._pending
            assert owned._pidfd is None
            assert all(stream.closed for stream in (pipes.stdin, pipes.stdout, pipes.stderr))
            assert not list((options["state_dir"] / "check-environments").glob("*.json"))
    finally:
        monkeypatch.undo()
        for pipes, owned in handles:
            if owned._pidfd is not None:
                discard(pipes, owned, RuntimeError("test cleanup"))


def test_stage_stops_after_uncertain_reap_and_environment_blocks_fresh_runners(tmp_path):
    from uuid import UUID, uuid4

    from skm.adapters.checks.shell import shell_check_runner
    from skm.modules.execution.domain.stage_record import StageOutcomeKind
    from skm.modules.execution.host.stages.base import StageRequest
    from skm.modules.execution.host.stages.run_checks import RunChecksStage
    from skm.platform.schema.registry import SchemaRegistry

    calls, proof = [], {"empty": False}

    class Process:
        pid = os.getpid()
        identity = identity_of(os.getpid())

        def confirmed(self, ownership):
            return True

        def empty(self):
            return True if proof["empty"] else None  # an exited leader does not prove an empty group

        def signal(self, sig):
            raise PermissionError("no proven reap")

        def poll(self):
            return 0

        def pump(self):
            pass

        def close(self):
            assert proof["empty"], "must not close an uncertain containment"

    class Launcher:
        def validate(self, command):
            pass

        def spawn(self, command, **kwargs):
            calls.append(command)
            return Process()

    runner, check, deps, _, options = check_harness(tmp_path, process=Launcher())
    checks: list[JsonValue] = [
        {
            "check_execution_id": str(check_id),
            "check_spec_id": str(uuid4()),
            "kind": "command",
            "definition": {"argv": [sys.executable, "-c", "pass"]},
        }
        for check_id in (check.check_execution_id, uuid4())
    ]
    stage = RunChecksStage(
        isolation=lambda raw, *a: replace(
            check.isolation,
            owner=replace(check.isolation.owner, unit_id=UUID(str(raw["check_execution_id"]))),
        ),
        read_capture=lambda path: path.read_bytes(),
        verify_environment=lambda _: None,
        candidate_marks=lambda *a: {},
    )
    stage_deps = SimpleNamespace(
        environment=deps.environment,
        check_runners=SimpleNamespace(get=lambda _: runner),
        vcs=SimpleNamespace(),
        uploader=deps.uploader,
        clock=deps.clock,
        monotonic=deps.monotonic,
        log=deps.log,
        cancel=deps.cancel,
        config=SimpleNamespace(get=lambda _: 4096),
    )
    outcome = stage.run(
        StageRequest(StageInstruction(kind="run_stage", params={}), {"checks": checks}, None, {}),
        cast("StageDeps", stage_deps),
    )
    assert len(calls) == 1
    assert runner._pending
    assert outcome.kind is StageOutcomeKind.CHECKS_UNKNOWN
    results = outcome.payload["results"]
    assert isinstance(results, list)
    states = []
    for raw in results:
        assert isinstance(raw, dict)
        states.append(raw["state"])
    assert states == ["unknown", "unknown"]
    assert len(outcome.files) == 2
    SchemaRegistry.load_default().require_valid(
        "urn:skm:execution:stage-outcome-run-checks:v1", dict(outcome.payload)
    )
    second = replace(check, check_execution_id=uuid4())
    second = replace(
        second,
        isolation=replace(
            second.isolation, owner=replace(second.isolation.owner, unit_id=second.check_execution_id)
        ),
    )
    # Both the in-memory runner and fresh command/shell/reproduction instances share this barrier.
    runners = [
        runner,
        CheckExecutor(**options),
        shell_check_runner(shell_allowed=True, **options),
        ReproductionRunner(**options),
    ]
    for blocked in runners:
        with pytest.raises(SkmError, match="reap/reconcile"):
            blocked.run(second, deps)
    assert len(calls) == 1
    assert list((options["state_dir"] / "check-environments").glob("*.json"))

    assert not runner.reconcile(deps)
    assert runner._pending
    proof["empty"] = True
    assert runner.reconcile(deps)
    assert not runner._pending
    assert not list((options["state_dir"] / "check-environments").glob("*.json"))
    result = runner.run(second, deps)
    assert result.exit_code == 0
    assert len(calls) == 2
