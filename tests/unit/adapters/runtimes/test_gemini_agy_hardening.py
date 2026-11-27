from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from integration.runtimes.test_codex_argv import _make_request
from skm.adapters.runtimes._cli_session import probe as cli_probe
from skm.adapters.runtimes._cli_session.launch import LaunchCommand
from skm.adapters.runtimes._cli_session.probe import CommandOutput, ProbeCacheKey
from skm.adapters.runtimes._cli_session.runtime import load_static_declarations
from skm.adapters.runtimes.antigravity.detect import REQUIRED_FLAGS
from skm.adapters.runtimes.gemini_cli import runtime as gemini
from skm.adapters.runtimes.gemini_cli.detect import ProbedBinary
from skm.bootstrap.host_services import build_host_storage
from skm.bootstrap.runtimes import RUNTIME_FACTORIES, WorkerRuntimeSettings
from skm.bootstrap.worker_runtimes import HostPlugins, WorkerRuntimes
from skm.kernel.error_codes import ErrorCode
from skm.kernel.ids import HostId
from skm.kernel.isolation import IsolationProfile
from skm.kernel.json_types import JsonObject
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.error_rules import RuntimeSignals, classify
from skm.modules.runtimes.domain.request import ProcessOwnership
from skm.modules.settings.public import GetHostConfigResultPlugins

_DIGEST = "sha256:" + "0" * 64


def test_gemini_forces_telemetry_off_and_preserves_api_key(tmp_path: Path) -> None:
    request = replace(
        _make_request(tmp_path, writable=False, isolation_profile=IsolationProfile.LANDLOCK),
        runtime_id="gemini_cli",
        model="gemini-3.8-flash",
        extra_env={"GEMINI_TELEMETRY_ENABLED": "true", "HTTPS_PROXY": "credential-bearing-input"},
    )
    runner = gemini.GeminiCliRuntime(environ={"GEMINI_API_KEY": "synthetic-api-key"})
    step = tmp_path / "step"
    step.mkdir()
    probed = ProbedBinary(
        ProbeCacheKey("/bin/true", _DIGEST, "1.0.0", "test", "1", _DIGEST), "/bin/true", "1.0.0", ()
    )
    command, _ = runner._build_launch(
        request,
        probed,
        step_dir=step,
        ownership=ProcessOwnership(request.process_owner, "pgroup_best_effort", "test"),
    )
    assert command.env["GEMINI_TELEMETRY_ENABLED"] == "false"
    assert command.env["GEMINI_API_KEY"] == "synthetic-api-key"
    assert "HTTPS_PROXY" not in command.env
    assert cast("LaunchCommand", command).verification_template == runner.launch_config_digest


@pytest.mark.parametrize(
    ("status", "text", "code"),
    [
        (None, "", ErrorCode.RUNTIME_TIMEOUT),
        (401, "", ErrorCode.RUNTIME_AUTH_EXPIRED),
        (403, "", ErrorCode.RUNTIME_FORBIDDEN),
        (429, "", ErrorCode.RATE_LIMITED),
        (429, "daily quota exhausted", ErrorCode.QUOTA_EXHAUSTED),
    ],
)
def test_gemini_exit_53_preserves_provider_precedence(status: int | None, text: str, code: ErrorCode) -> None:
    _, rules = load_static_declarations(Path(gemini.__file__).parent)
    signals = RuntimeSignals(exit_code=53, http_status=status, fatal_text=text)
    failure = classify("gemini_cli", signals, rules, now_unix=0)
    assert failure.code is code
    if status is None:
        assert failure.scope == "session"
        assert not failure.retryable
        assert failure.safe_message == "Gemini CLI turn limit exceeded"
    assert (
        classify("gemini_cli", RuntimeSignals(exit_code=42), rules, now_unix=0).code
        is ErrorCode.RUNTIME_INVALID_REQUEST
    )


@pytest.mark.parametrize(
    ("explicit", "configured", "ambient", "winner"),
    [
        ("explicit", "configured", "ambient", "explicit"),
        (None, "configured", "ambient", "configured"),
        (None, None, "ambient", "ambient"),
        (None, None, None, "agy"),
    ],
)
def test_antigravity_binary_priority_through_runtime_factory(
    tmp_path: Path,
    explicit: str | None,
    configured: str | None,
    ambient: str | None,
    winner: str,
) -> None:
    for name in ("explicit", "configured", "ambient", "agy"):
        path = tmp_path / name
        path.write_bytes(b"synthetic binary")
        path.chmod(0o700)
    environ = {"PATH": str(tmp_path)}
    if ambient is not None:
        environ["AGY_BIN"] = ambient
    ctx = SimpleNamespace(config={"runtimes.binaries": {"antigravity": configured}})
    seen: list[str] = []

    def probe(argv: tuple[str, ...], *, env: Mapping[str, str], timeout_seconds: float) -> CommandOutput:
        seen.append(argv[0])
        return CommandOutput(0, "agy 1.2.3" if argv[1] == "--version" else " ".join(REQUIRED_FLAGS), "")

    runtime = RUNTIME_FACTORIES["antigravity"](ctx, binary=explicit, environ=environ, probe_runner=probe)
    installation = runtime.detect(DetectProbe(HostId(uuid4()), None, (), 5))
    assert installation.binary_locator == str(tmp_path / winner)
    assert seen == [str(tmp_path / winner)] * 2


@pytest.mark.parametrize("configured", [False, True])
def test_worker_admits_the_detected_antigravity_binary(
    tmp_path: Path, configured: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = replace(_make_request(tmp_path), runtime_id="antigravity", expected_runtime_version="1.2.3")
    binary = tmp_path / ("configured-agy" if configured else "env-agy")
    binary.write_bytes(b"synthetic binary")
    binary.chmod(0o700)

    def run_probe(argv: tuple[str, ...], **_: object) -> SimpleNamespace:
        assert argv[0] == str(binary)
        output = "agy 1.2.3" if argv[1] == "--version" else " ".join(REQUIRED_FLAGS)
        return SimpleNamespace(exit_code=0, stdout=output.encode(), stderr=b"", timed_out=False)

    monkeypatch.setattr(cli_probe, "require_support", lambda: None)
    monkeypatch.setattr(cli_probe, "run", run_probe)
    binaries: JsonObject = {"antigravity": binary.name} if configured else {}
    settings = WorkerRuntimeSettings(
        allowed=frozenset({request.runtime_id}),
        options={"runtimes.binaries": binaries},
        models={request.runtime_id: {request.model: frozenset({request.effort or "default"})}},
    )
    state = tmp_path / "state"
    worker = WorkerRuntimes(
        HostPlugins(lambda: settings, lambda: GetHostConfigResultPlugins((), ())),
        lambda: settings,
        lambda: None,
        state,
        build_host_storage(state),
        {"PATH": str(tmp_path), "AGY_BIN": "env-agy"},
        lambda _: {},
        account=lambda *_: True,
    )

    runtime = worker.get(request.runtime_id)
    installation = runtime.detect(DetectProbe(HostId(request.process_owner.host_id), None, (), 5))
    assert installation.binary_locator == str(binary)
    worker.observe_installation(runtime, installation)
    worker.verify_runtime(request, installation.details["binary_sha256"], registry=None)
