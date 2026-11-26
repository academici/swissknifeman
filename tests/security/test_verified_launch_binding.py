"""Verified CLI launch evidence is checked before any child process starts."""

import json
import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from shutil import copyfile
from stat import S_IMODE
from textwrap import dedent
from typing import Literal
from uuid import uuid4

import pytest

from integration.runtimes.test_codex_argv import (
    ALL_SUPPORTED_EXEC_HELP,
    ALL_SUPPORTED_ROOT_HELP,
    _make_request,
    _make_user_home,
    _write_executable,
)
from skm.adapters.runtimes._cli_session import binding as cli_binding
from skm.adapters.runtimes._cli_session import session as cli_session
from skm.adapters.runtimes._cli_session.binding import launch_verification_digest
from skm.adapters.runtimes.codex.launch import build_launch_plan
from skm.adapters.runtimes.codex.runtime import CodexRuntime
from skm.adapters.sandbox import landlock_exec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.ids import HostId
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.capability import VerificationContext, verification_context_key
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.request import AgentRequest, McpServerSpec, ProcessOwnership, request_to_json
from skm.platform.process.ownership import ChildPipes, OwnedProcess

type VerifiedCodex = tuple[CodexRuntime, AgentRequest, Path, Path, Path]


@pytest.fixture
def verified_codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> VerifiedCodex:
    return _verified_codex(tmp_path, monkeypatch, IsolationProfile.WORKTREE)


def _verified_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: IsolationProfile
) -> VerifiedCodex:
    request = _make_request(tmp_path, isolation_profile=profile, secret_token="assignment-token-canary")
    request = replace(request, mcp_servers=(McpServerSpec("approved", ("/bin/true",), {}, ()),))
    assert request.client_home is not None
    home = Path(request.client_home)
    canary = home / "ran"
    probe_canary = tmp_path / "probed"
    wrapper = tmp_path / "landlock_exec.py"
    copyfile(landlock_exec.__file__, wrapper)
    monkeypatch.setattr(cli_binding, "_LANDLOCK_WRAPPER", wrapper)
    interpreter = tmp_path / "python"
    interpreter.symlink_to(Path(sys.executable).resolve())
    binary = _write_executable(
        tmp_path / "bin" / "codex",
        dedent(
            f"""\
            #!{interpreter}
            import json
            import os
            import sys
            from pathlib import Path

            messages = {{
                ("--version",): "codex-cli 0.165.0",
                ("--help",): {ALL_SUPPORTED_ROOT_HELP!r},
                ("exec", "--help"): {ALL_SUPPORTED_EXEC_HELP!r},
                ("login", "status"): "Logged in using ChatGPT",
            }}
            reply = messages.get(tuple(sys.argv[1:]))
            if reply is not None:
                Path({str(probe_canary)!r}).write_text(__file__)
                if tuple(sys.argv[1:]) == ("login", "status"):
                    wallet = Path(os.environ["CODEX_HOME"]) / "auth.json"
                    if wallet.exists():
                        Path({str(home / "login-account")!r}).write_text(wallet.read_text())
                print(reply)
            else:
                wallet = Path(os.environ["CODEX_HOME"]) / "auth.json"
                if wallet.exists():
                    Path({str(home / "launch-account")!r}).write_text(wallet.read_text())
                config = Path(os.environ["CODEX_HOME"]) / "config.toml"
                observed = [__file__, sys.executable, str(config), config.read_text()]
                Path({str(canary)!r}).write_text(json.dumps(observed))
                sys.stdin.read()
                print('{{"type":"thread.started","thread_id":"session-1"}}')
                print('{{"type":"item.completed","item":{{"id":"item_1","type":"agent_message","text":"ok"}}}}')
                print('{{"type":"turn.completed","usage":{{"input_tokens":1,"output_tokens":1}}}}')
            """
        ),
    )
    environ = {"PATH": "/usr/bin:/bin"}
    user_home = _make_user_home(tmp_path)
    (user_home / ".codex").chmod(0o700)
    runtime = CodexRuntime(
        binary=str(binary),
        state_dir=tmp_path / "state",
        user_home=user_home,
        environ=environ,
        require_exec_binding=True,
        os_kernel_fn=lambda: "Linux/test-kernel",
    )
    host_id = HostId(request.process_owner.host_id)
    installation = runtime.detect(DetectProbe(host_id, None, (), 10))
    probe_canary.unlink()
    plan = build_launch_plan(
        request,
        binary_path=str(binary),
        step_dir=tmp_path / "canary-step",
        ownership=ProcessOwnership(request.process_owner, "pgroup_best_effort", "canary"),
        host_environ=environ,
        user_home=user_home,
    )
    context = VerificationContext(
        host_id=host_id,
        binary_sha256=installation.details["binary_sha256"],
        os="Linux",
        kernel="test-kernel",
        adapter_version=installation.details["adapter_version"],
        isolation_profile=request.isolation_profile,
        launch_config_digest=launch_verification_digest(plan.command.as_wrapped(), str(binary)),
    )
    verified = replace(
        request,
        verification_context=context,
        verification_key=verification_context_key(context),
        expected_runtime_version=installation.version,
    )
    assert installation.version == "0.165.0"
    assert request_to_json(verified) == request_to_json(request)
    return runtime, verified, binary, canary, probe_canary


@pytest.mark.parametrize("profile", [IsolationProfile.WORKTREE, IsolationProfile.LANDLOCK])
def test_verified_launch_executes_the_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: IsolationProfile
) -> None:
    if profile is IsolationProfile.LANDLOCK and landlock_exec.landlock_abi() < 3:
        pytest.skip("Landlock ABI 3 unavailable")
    runtime, request, binary, canary, probe_canary = _verified_codex(tmp_path, monkeypatch, profile)
    result = runtime.result(runtime.start(request))
    assert result.outcome == "completed", result.failure
    assert result.observation is not None
    assert request.verification_context is not None
    assert result.observation.binding.executable_sha256 == request.verification_context.binary_sha256
    assert result.observation.binding.verification_key == request.verification_key
    assert result.observation.binding.runtime_version == request.expected_runtime_version
    script_path, interpreter_path, _, _ = json.loads(canary.read_text())
    pinned = Path(script_path)
    assert pinned == binary.parents[1] / "state" / "steps" / request.request_id / ".pinned-bin" / binary.name
    assert S_IMODE(pinned.parent.stat().st_mode) == 0o700
    assert S_IMODE(pinned.stat().st_mode) == 0o500
    assert pinned.read_bytes() == binary.read_bytes()
    assert Path(probe_canary.read_text()) == pinned
    interpreter = pinned.parent / "shebang-interpreter/executable"
    assert Path(interpreter_path) == interpreter
    assert S_IMODE(interpreter.stat().st_mode) == 0o500
    if profile is IsolationProfile.LANDLOCK:
        assert S_IMODE((pinned.parent / "landlock-interpreter/executable").stat().st_mode) == 0o500
        assert S_IMODE((pinned.parent / "landlock_exec.py").stat().st_mode) == 0o500


def test_verified_steps_use_same_selected_wallet_for_login_and_launch(
    tmp_path: Path, verified_codex: VerifiedCodex
) -> None:
    runtime, request, _, _, _ = verified_codex
    assert request.client_home is not None
    selected = tmp_path / "user_home" / ".codex" / "auth.json"
    cached = Path(request.client_home) / "auth.json"
    initial = selected.read_text()
    assert cached.read_text() == initial

    assert runtime.result(runtime.start(request)).final_text == "ok"
    assert (cached.parent / "login-account").read_text() == initial
    assert (cached.parent / "launch-account").read_text() == initial

    replacement = '{"synthetic_account":"B"}'
    selected.write_text(replacement)
    step_id = uuid4()
    next_step = replace(
        request,
        request_id=str(step_id),
        process_owner=replace(request.process_owner, unit_id=step_id),
    )
    assert runtime.result(runtime.start(next_step)).final_text == "ok"
    assert (cached.parent / "login-account").read_text() == replacement
    assert (cached.parent / "launch-account").read_text() == replacement
    assert cached.read_text() == initial


def test_shared_config_replacement_before_exec_cannot_change_verified_config(
    verified_codex: VerifiedCodex, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, request, _, canary, _ = verified_codex
    assert request.client_home is not None
    shared_home = Path(request.client_home)
    shared_config = shared_home / "config.toml"
    approved_config = shared_config.read_text()
    assert "[mcp_servers.approved]" in approved_config
    replacement_config = '[mcp_servers.unapproved]\ncommand = "/bin/false"\n'
    launch = cli_session.launch

    def launch_after_replacement(
        argv: tuple[str, ...], *, cwd: Path, env: Mapping[str, str]
    ) -> tuple[ChildPipes, OwnedProcess]:
        replacement = shared_config.with_suffix(".new")
        replacement.write_text(replacement_config)
        replacement.replace(shared_config)
        return launch(argv, cwd=cwd, env=env)

    monkeypatch.setattr(cli_session, "launch", launch_after_replacement)
    result = runtime.result(runtime.start(request))
    assert result.outcome == "completed", result.failure
    assert shared_config.read_text() == replacement_config
    _, _, path, observed_config = json.loads(canary.read_text())
    assert observed_config == approved_config
    snapshot = Path(path)
    assert snapshot.parent != shared_home
    assert S_IMODE(snapshot.stat().st_mode) == 0o400
    assert (snapshot.parent / "sessions").resolve() == shared_home / "sessions"


@pytest.mark.parametrize("field", ["binary", "isolation_profile", "runtime_version"])
def test_verified_launch_refuses_drift_before_starting_a_child(
    verified_codex: VerifiedCodex,
    field: Literal["binary", "isolation_profile", "runtime_version"],
) -> None:
    runtime, request, binary, canary, probe_canary = verified_codex
    if field == "binary":
        binary.write_bytes(binary.read_bytes() + b"\n# updater changed the binary\n")
    elif field == "isolation_profile":
        request = replace(request, isolation_profile=IsolationProfile.LANDLOCK)
    else:
        request = replace(request, expected_runtime_version="0.164.0")

    with pytest.raises(CapabilityUnavailable) as failure:
        runtime.start(request)
    assert failure.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert not canary.exists()
    assert not probe_canary.exists()
    assert not list((binary.parents[1] / "state").rglob(".pinned-bin"))


@pytest.mark.parametrize("change", ["sandbox", "mcp", "session_policy", "resume"])
def test_effective_launch_drift_refuses_before_spawn(verified_codex: VerifiedCodex, change: str) -> None:
    runtime, request, binary, canary, probe_canary = verified_codex
    if change == "sandbox":
        grant = replace(request.permissions, fs_write=replace(request.permissions.fs_write, allow=()))
        request = replace(request, permissions=grant)
    elif change == "mcp":
        request = replace(request, mcp_servers=(McpServerSpec("probe", ("/bin/true",), {}, ()),))
    elif change == "session_policy":
        request = replace(request, session_policy="ephemeral")
    else:
        request = replace(request, resume_session_ref="previous-session")
    _assert_launch_config_refusal(runtime, request, binary, canary, probe_canary)


@pytest.mark.parametrize("dependency", ["interpreter", "wrapper"])
def test_executable_dependency_drift_refuses_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dependency: str
) -> None:
    runtime, request, binary, canary, probe_canary = _verified_codex(
        tmp_path, monkeypatch, IsolationProfile.LANDLOCK
    )
    if dependency == "interpreter":
        interpreter = tmp_path / "python"
        old = interpreter.resolve()
        interpreter.unlink()
        copyfile(old, interpreter)
        with interpreter.open("ab") as file:
            file.write(b"\nchanged interpreter")
        interpreter.chmod(0o700)
    else:
        with (tmp_path / "landlock_exec.py").open("ab") as file:
            file.write(b"\n# changed wrapper\n")
    _assert_launch_config_refusal(runtime, request, binary, canary, probe_canary)


def _assert_launch_config_refusal(
    runtime: CodexRuntime, request: AgentRequest, binary: Path, canary: Path, probe_canary: Path
) -> None:
    with pytest.raises(CapabilityUnavailable) as failure:
        runtime.start(request)
    assert failure.value.details.get("reason") == "verified_launch_config_changed"
    assert not canary.exists()
    assert not probe_canary.exists()
    assert not list((binary.parents[1] / "state").rglob(".pinned-bin"))
