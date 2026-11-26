"""TR fail-closed host path and real read-only/DEVNULL/timeout canaries; no simulated exits."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from integration.checks.test_check_stdin import check_harness
from integration.worker.test_worker_loop import documents
from skm.adapters.checks.command import ReproductionRunner
from skm.adapters.checks.registry import CheckRunnerRegistry
from skm.adapters.sandbox.landlock_exec import landlock_abi, probe_enforcement
from skm.modules.execution.domain.finding import Severity
from skm.modules.execution.domain.triage import reverify_decision
from skm.modules.execution.domain.work_policy import (
    HardCeilings,
    Intensity,
    WorkPolicyOverride,
    WorkPolicySettings,
    resolve_work_policy,
    soft_warnings,
)
from skm.modules.execution.host.checks import CheckDeps
from skm.modules.execution.host.reproduce import run_reproduction
from skm.modules.execution.host.worker_loop import run
from skm.modules.execution.ports import CheckRunner
from skm.modules.execution.ports import CheckRunnerRegistry as CheckRunnerPort
from unit.execution.domain.test_finding_key import make
from unit.execution.host.stages.test_roles import exercise


def reproduction(argv: list[str], exit_code: int = 0) -> dict[str, Any]:
    return {"argv": argv, "exit": exit_code, "observed": "independent command evidence"}


@pytest.mark.parametrize("profile", ["none", "worktree", "landlock", "missing"])
def test_real_gateway_refuses_unproved_read_only_reproduction(
    tmp_path: Any, monkeypatch: Any, profile: str
) -> None:
    finding = make(1, Severity.BLOCKER, "high")
    target = tmp_path / "must-not-exist"
    repro = reproduction([sys.executable, "-c", f"open({str(target)!r}, 'w').write('bad')"])
    doc = {
        **documents()["triager"],
        "confirmed": [],
        "rejected": [{"finding_id": "F1", "reason": "claimed absent", "reproduction": repro}],
    }
    fixture = exercise(tmp_path, monkeypatch, "triager", doc, triage_findings=lambda _: (finding,))
    (tmp_path / "check").mkdir()
    runner, _, _, _, _ = check_harness(tmp_path / "check", profile=profile, runner_class=ReproductionRunner)
    fixture.entries[CheckRunnerPort] = CheckRunnerRegistry({"command": cast("CheckRunner", runner)})
    run(fixture.ctx, fixture.request)
    outcome = fixture.outcomes[0]
    receipt = json.loads(outcome.payload["detail"])["triage"]["reverify"][0]
    assert receipt["decision"] == "confirmed"
    assert receipt["code"] == "TRIAGE_REPRO_UNVERIFIED"
    assert receipt["finding_key"] == finding.finding_key
    assert receipt["verification"]["spawn_error"] == "SANDBOX_UNAVAILABLE"
    assert not target.exists()
    assert outcome.payload["role_result"]["rejected"] == []
    assert json.loads(outcome.files[0].path.read_text()) == doc
    assert len(outcome.files) == 3
    assert all(file.path.exists() for file in outcome.files)


@pytest.mark.parametrize(
    "argv",
    [["true"], [":"], ["exit", "0"], ["echo", "not evidence"], ["printf", "ok"], ["bash", "-lc", "true"]],
)
def test_trivial_rejection_through_actual_triager_stage(
    tmp_path: Any, monkeypatch: Any, argv: list[str]
) -> None:
    finding = make(1, Severity.MAJOR, "high")
    doc = {
        **documents()["triager"],
        "confirmed": [],
        "rejected": [{"finding_id": "F1", "reason": "claim", "reproduction": reproduction(argv)}],
    }
    fixture = exercise(tmp_path, monkeypatch, "triager", doc, triage_findings=lambda _: (finding,))
    run(fixture.ctx, fixture.request)
    outcome = fixture.outcomes[0]
    assert outcome.payload["role_result"]["rejected"] == []
    assert json.loads(outcome.payload["detail"])["triage"]["reverify"][0]["code"] == "TRIAGE_REPRO_TRIVIAL"
    assert len(outcome.files) == 1


@pytest.mark.parametrize(("tier", "warning"), [("light", 30), ("medium", 60), ("heavy", 90)])
def test_soft_reproduction_warning_does_not_replace_emergency_timeout(
    tmp_path: Any, monkeypatch: Any, tier: str, warning: int
) -> None:
    policy = resolve_work_policy(
        WorkPolicySettings.defaults(),
        unit=WorkPolicyOverride.from_json({"role_intensity": {"triager": tier}}),
        ceilings=HardCeilings(role_wall_seconds={"reviewer": 1800}),
    )
    assert policy.triage_repro_warn_seconds == warning
    assert soft_warnings(policy, "triager", elapsed_seconds=100, repro_seconds=100)
    fixture = exercise(tmp_path, monkeypatch, "triager", documents()["triager"])
    run(fixture.ctx, fixture.request)
    request, deps = fixture.requests[0]
    (tmp_path / "check").mkdir()
    runner, _, _, _, _ = check_harness(tmp_path / "check", runner_class=ReproductionRunner)
    deps = replace(deps, check_runners=CheckRunnerRegistry({"command": cast("CheckRunner", runner)}))
    deps.config.values["execution.work_policy.repro_warn_seconds"] = {tier: warning}
    # The real runner validates the requested timeout before refusing missing read-only isolation.
    observed = []
    original = runner.run

    def record(check: Any, check_deps: Any) -> Any:
        observed.append(check)
        return original(check, check_deps)

    runner.run = record  # type: ignore[method-assign]
    facts, _ = run_reproduction(
        request,
        CheckDeps(deps.environment, deps.uploader, deps.clock, deps.monotonic, deps.log, deps.cancel),
        reproduction([sys.executable, "-c", "pass"]),
        run_check=lambda check, check_deps: deps.check_runners.get("command").run(check, check_deps),
        timeout_seconds=deps.config.get("execution.triage.repro_timeout_seconds"),
        finding_id="F2",
        remaining_seconds=240,
    )
    assert observed[0].timeout_seconds == 240
    assert observed[0].idle_timeout_seconds == 0
    assert observed[0].isolation.read_only_root
    assert observed[0].isolation.writable == ()
    assert facts["verified"] is False
    assert policy.emergency_role_seconds["reviewer"] == 1800
    assert Intensity(tier).value == tier


def test_exhausted_emergency_wall_never_starts_a_reproduction(tmp_path: Any, monkeypatch: Any) -> None:
    fixture = exercise(tmp_path, monkeypatch, "triager", documents()["triager"])
    run(fixture.ctx, fixture.request)
    request, deps = fixture.requests[0]
    target = tmp_path / "never"
    facts, files = run_reproduction(
        request,
        CheckDeps(deps.environment, deps.uploader, deps.clock, deps.monotonic, deps.log, deps.cancel),
        reproduction([sys.executable, "-c", f"open({str(target)!r}, 'w')"]),
        run_check=lambda check, check_deps: deps.check_runners.get("command").run(check, check_deps),
        finding_id="F2",
        remaining_seconds=0,
    )
    assert facts == {"verified": False, "timed_out": True}
    assert files == ()
    assert not target.exists()


def readonly_command(script: str) -> list[str]:
    if landlock_abi() < 3 or probe_enforcement() is not None:
        pytest.skip("real Landlock enforcement unavailable; no positive read-only evidence")
    return [
        sys.executable,
        "-P",
        "-m",
        "skm.adapters.sandbox.landlock_exec",
        "--no-default-rw",
        "--",
        sys.executable,
        "-c",
        script,
    ]


def execute_readonly(script: str, *, timeout: float = 5) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        readonly_command(script),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={"PATH": os.defpath, "PYTHONPATH": str(Path(__file__).resolve().parents[5] / "src")},
    )


def test_real_readonly_process_reads_devnull_without_waiting() -> None:
    result = execute_readonly(
        "import os,sys; print(os.readlink('/proc/self/fd/0')); print(repr(sys.stdin.buffer.read()))"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "/dev/null\nb''\n"


def test_real_readonly_process_cannot_modify_current_output(tmp_path: Path) -> None:
    target = tmp_path / "candidate"
    target.write_text("original")
    result = execute_readonly(f"open({str(target)!r}, 'w').write('changed')")
    assert result.returncode != 0
    assert "PermissionError" in result.stderr
    assert target.read_text() == "original"


@pytest.mark.parametrize(("reported", "decision"), [(3, "rejected"), (0, "confirmed")])
def test_real_readonly_exit_drives_match_and_mismatch(reported: int, decision: str) -> None:
    result = execute_readonly("raise SystemExit(3)")
    assert result.returncode == 3, result.stderr
    receipt = reverify_decision(
        make(1, Severity.MAJOR, "high"),
        {
            "decision": "rejected",
            "reproduction": reproduction([sys.executable, "-c", "raise SystemExit(3)"], reported),
            "verification": {"verified": True, "exit_code": result.returncode},
        },
    )
    assert receipt["decision"] == decision


def test_real_readonly_timeout_preserves_confirmation() -> None:
    with pytest.raises(subprocess.TimeoutExpired):
        execute_readonly("while True: pass", timeout=0.25)
    receipt = reverify_decision(
        make(1, Severity.BLOCKER, "high"),
        {
            "decision": "rejected",
            "reproduction": reproduction([sys.executable, "-c", "while True: pass"]),
            "verification": {"verified": False, "timed_out": True},
        },
    )
    assert receipt["decision"] == "confirmed"
    assert receipt["code"] == "TRIAGE_REPRO_UNVERIFIED"
