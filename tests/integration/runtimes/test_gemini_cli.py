"""Gemini CLI runtime coverage using an offline executable and real session supervision."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from skm.adapters.runtimes._cli_session.probe import CommandOutput
from skm.adapters.runtimes.gemini_cli.runtime import GeminiCliRuntime
from skm.bootstrap.builtins import builtin_runtime_data
from skm.bootstrap.runtimes import RUNTIME_FACTORIES
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.capability import Capability, CapabilityStatus
from skm.modules.runtimes.domain.classes import Effort, RoleId
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership, SecretStr
from skm.modules.runtimes.domain.session_events import (
    SessionStarted,
    ToolCompleted,
    ToolRequested,
    validate_event_stream,
)
from skm.platform.config.sources.document import decode_document
from skm.platform.process.ownership import OwnershipUnavailable
from skm.platform.process.runner import run
from skm.platform.schema.registry import SchemaRegistry

from .test_grok_argv import HOST_1, _make_request

_MODEL = "gemini-3.8-flash"
_KEY = "synthetic-gemini-credential"


def _probe_cli(argv: tuple[str, ...], *, env: Mapping[str, str], timeout_seconds: float) -> CommandOutput:
    process = subprocess.run(
        argv, env=env, timeout=timeout_seconds, capture_output=True, text=True, check=False
    )
    return CommandOutput(process.returncode, process.stdout, process.stderr)


@pytest.fixture
def native_process_ownership(tmp_path: Path) -> None:
    try:
        run((sys.executable, "-c", "pass"), cwd=tmp_path, env={}, timeout_seconds=5)
    except OwnershipUnavailable as exc:
        pytest.skip(f"Native process ownership unavailable: {exc}")


def _request(tmp_path: Path, prompt: str = "success") -> AgentRequest:
    request = _make_request(
        tmp_path,
        role=RoleId.REVIEWER,
        writable=False,
        config_mode="isolated",
        effort=Effort.HIGH,
        model=_MODEL,
        prompt=prompt,
    )
    return replace(request, runtime_id="gemini_cli")


@pytest.fixture
def fake_gemini(tmp_path: Path) -> Path:
    executable = tmp_path / "gemini"
    executable.write_text(
        f"""#!{sys.executable}
import json
import os
import sys

if sys.argv[1:] == ["--version"]:
    print("0.68.0")
    sys.exit(0)
if sys.argv[1:] == ["--help"]:
    print("--model --output-format (text, json, stream-json) --approval-mode --prompt")
    sys.exit(0)
assert sys.argv[1:] == [
    "--output-format", "stream-json", "--approval-mode", "plan", "--prompt", "", "--model", "{_MODEL}",
]
assert os.environ["GEMINI_API_KEY"] == "{_KEY}"
assert "SKM_TOKEN" not in os.environ and "NODE_OPTIONS" not in os.environ
assert os.environ["GEMINI_CLI_HOME"] == os.environ["HOME"]
assert all(os.path.isabs(entry) for entry in os.environ["PATH"].split(os.pathsep))
with open(os.environ["GEMINI_CLI_SYSTEM_SETTINGS_PATH"], encoding="utf-8") as file:
    settings = json.load(file)
assert settings["advanced"]["ignoreLocalEnv"] is True
assert settings["hooksConfig"] == {{"enabled": False}}
assert "run_shell_command" not in settings["tools"]["core"]
try:
    open("forbidden", "w", encoding="utf-8").close()
except PermissionError:
    pass
else:
    raise AssertionError("checkout write escaped Landlock")

def emit(kind, **fields):
    print(json.dumps({{"type": kind, **fields}}), flush=True)

mode = sys.stdin.read()
if mode == "auth":
    emit("result", status="error", error={{"message": "401 API key invalid: {_KEY}"}})
    sys.exit(1)
emit("init", session_id="gemini-session", model="{_MODEL}")
emit("message", role="user", content=mode)
emit("message", role="assistant", content="Reading the files.", delta=True)
emit("tool_use", tool_name="read_file", tool_id="call-1", parameters={{"file_path": "README.md"}})
emit("tool_result", tool_id="call-1", status="success", output="file content")
emit("message", role="assistant", content="Final ", delta=True)
emit("message", role="assistant", content="answer", delta=True)
if mode != "partial":
    emit("result", status="success", stats={{"input_tokens": 45, "cached": 11, "output_tokens": 12}})
""",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    return executable


@pytest.mark.parametrize(
    ("prompt", "failure"),
    [
        ("success", None),
        ("partial", ErrorCode.RUNTIME_STREAM_INCOMPLETE),
        ("auth", ErrorCode.RUNTIME_AUTH_EXPIRED),
    ],
)
@pytest.mark.usefixtures("native_process_ownership")
def test_gemini_cli_supervised_session(
    tmp_path: Path, fake_gemini: Path, prompt: str, failure: ErrorCode | None
) -> None:
    request = _request(tmp_path, prompt)
    (Path(request.workdir) / ".git").touch()
    runtime = RUNTIME_FACTORIES["gemini_cli"](
        SimpleNamespace(config={"runtimes.binaries": {"gemini_cli": str(fake_gemini)}}),
        state_dir=tmp_path / "state",
        environ={"PATH": os.defpath, "GEMINI_API_KEY": _KEY, "NODE_OPTIONS": "--invalid"},
    )
    installation = runtime.detect(DetectProbe(HOST_1, None, (), 5))
    assert installation.runtime_id == "gemini_cli"
    assert installation.version == "0.68.0"
    handle = runtime.start(request)
    events = tuple(runtime.events(handle))
    result = runtime.result(handle)
    assert validate_event_stream(events) == ()
    assert not (Path(request.workdir) / "forbidden").exists()
    step = tmp_path / "state" / "steps" / request.request_id
    assert not (step / "gemini-home").exists()
    assert _KEY not in (step / "stream.jsonl").read_text(encoding="utf-8")

    if failure is None:
        assert result.failure is None
        assert result.final_text == "Final answer"
        assert result.model == _MODEL
        assert isinstance(events[0], SessionStarted)
        assert events[0].session_ref == result.session_ref == "gemini-session"
        assert sum(isinstance(event, ToolRequested) for event in events) == 1
        assert sum(isinstance(event, ToolCompleted) for event in events) == 1
        assert result.usage.input_tokens == 34
        assert result.usage.output_tokens == 12
        assert result.usage.cache_read_tokens == 11
    else:
        assert result.failure is not None
        assert result.failure.code is failure
        assert result.final_text == ""


def test_gemini_cli_launch_command_runs_under_landlock(tmp_path: Path, fake_gemini: Path) -> None:
    repo = tmp_path / "repository"
    request = _request(repo)
    (repo / ".git").touch()
    (tmp_path / ".env").touch()
    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".gemini" / "settings.json").write_text("{}", encoding="utf-8")
    request = replace(
        request,
        secret_env={**request.secret_env, "GEMINI_API_KEY": SecretStr(_KEY)},
    )
    runtime = GeminiCliRuntime(
        binary=str(fake_gemini),
        environ={"PATH": f".:{os.defpath}:", "GEMINI_API_KEY": "overridden-key", "NODE_OPTIONS": "--invalid"},
        probe_runner=_probe_cli,
    )
    installation = runtime.detect(DetectProbe(HOST_1, None, (), 5))
    assert installation.version == "0.68.0"
    assert runtime.capabilities().supports(Capability.HEADLESS_EXECUTION)
    probed = runtime._last_probed()
    assert probed is not None
    step_dir = tmp_path / "step"
    step_dir.mkdir()
    command, stdin = runtime._build_launch(
        request,
        probed,
        step_dir=step_dir,
        ownership=ProcessOwnership(request.process_owner, "pgroup_best_effort", "test"),
    )
    result = subprocess.run(
        command.argv,
        cwd=command.cwd,
        env=command.env,
        input=stdin,
        capture_output=True,
        timeout=5,
        check=True,
    )
    parser = runtime._make_parser(request, probed, str)
    events = [event for line in result.stdout.splitlines() for event in parser.feed(line)]
    assert isinstance(events[0], SessionStarted)
    assert isinstance(events[2], ToolRequested)
    assert isinstance(events[3], ToolCompleted)
    assert parser.saw_terminal()
    outcome = parser.finish(result.returncode)
    assert outcome.final_text == "Final answer"
    assert outcome.usage.input_tokens == 34
    assert outcome.usage.cache_read_tokens == 11


def test_gemini_cli_manifest_and_probe_gate(tmp_path: Path, fake_gemini: Path) -> None:
    entry = next(item for item in builtin_runtime_data() if item.runtime_id == "gemini_cli")
    assert set(entry.capabilities.records) == set(Capability)
    assert entry.capabilities.status(Capability.HEADLESS_EXECUTION) is CapabilityStatus.ADAPTED
    assert entry.capabilities.status(Capability.EFFORT_CONTROL) is CapabilityStatus.UNSUPPORTED
    assert entry.capabilities.status(Capability.SESSION_RESUME) is CapabilityStatus.UNSUPPORTED

    schemas = SchemaRegistry.load_default()
    source = Path(__file__).resolve().parents[3] / "src/skm/adapters/runtimes/gemini_cli"
    for name, urn in [("capabilities", "capabilities"), ("error_rules", "error-rules")]:
        document = decode_document((source / f"{name}.toml").read_text(encoding="utf-8"), "toml")
        assert schemas.validate(f"urn:skm:runtimes:{urn}:v1", document) == ()

    def old_cli(argv: tuple[str, ...], *, env: object, timeout_seconds: float) -> CommandOutput:
        del env, timeout_seconds
        text = "0.68.0" if argv[-1] == "--version" else "--output-format --prompt --model"
        return CommandOutput(0, text, "")

    runtime = GeminiCliRuntime(binary=str(fake_gemini), probe_runner=old_cli)
    runtime.detect(DetectProbe(HOST_1, None, (), 5))
    assert runtime.capabilities().status(Capability.HEADLESS_EXECUTION) is CapabilityStatus.UNSUPPORTED
    with pytest.raises(CapabilityUnavailable) as exc_info:
        runtime.start(_request(tmp_path))
    assert exc_info.value.code is ErrorCode.CAPABILITY_UNAVAILABLE


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("write", ErrorCode.SANDBOX_UNAVAILABLE),
        ("worktree", ErrorCode.SANDBOX_UNAVAILABLE),
        ("workspace_dotenv", ErrorCode.SANDBOX_UNAVAILABLE),
        ("model", ErrorCode.MODEL_UNAVAILABLE),
        ("missing_key", ErrorCode.RUNTIME_AUTH_EXPIRED),
    ],
)
def test_gemini_cli_rejects_unsafe_or_unsupported_launch(
    tmp_path: Path, fake_gemini: Path, case: str, code: ErrorCode
) -> None:
    repo = tmp_path / "repository"
    request = _request(repo)
    (repo / ".git").touch()
    if case == "write":
        grant = _make_request(repo).permissions.fs_write
        request = replace(request, permissions=replace(request.permissions, fs_write=grant))
    elif case == "worktree":
        request = replace(request, isolation_profile=IsolationProfile.WORKTREE)
    elif case == "workspace_dotenv":
        (repo / ".env").touch()
    elif case == "model":
        request = replace(request, model="--unsafe-flag")
    runtime = GeminiCliRuntime(
        binary=str(fake_gemini),
        state_dir=tmp_path / "state",
        environ={"PATH": os.defpath},
        probe_runner=_probe_cli,
    )
    with pytest.raises(CapabilityUnavailable) as exc_info:
        runtime.start(request)
    assert exc_info.value.code is code
