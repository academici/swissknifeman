"""Mandatory offline diagnostics: no provider fixtures and no evals marker."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import ModuleType
from typing import cast, override

import pytest

from skm.adapters.runtimes.claude_code.runtime import ClaudeCodeRuntime
from skm.kernel.json_types import JsonValue
from skm.modules.runtimes.domain.detection import CancellationResult
from skm.modules.runtimes.domain.request import AgentRequest
from skm.modules.runtimes.domain.result import ExitInfo, RuntimeResult
from skm.modules.runtimes.domain.session_events import (
    SessionCompleted,
    SessionEvent,
    SessionStarted,
    StopReason,
    UsageReported,
)
from skm.modules.runtimes.domain.usage import SubagentUsage, UsageReport, UsageStatus, unknown_usage
from skm.modules.runtimes.ports import SessionHandle

from .conftest import (
    CHECK,
    LIMITS,
    EvalBudget,
    credential_redactor,
    disposable_task,
    locate_cli,
    make_request,
    parse_ceiling,
    require_credentials,
    require_opt_in,
    run_small_task,
)

SECRET = 'fake-credential-quoted-"-12345678'
FIXED = 'def greet(name):\n    return "Hello, " + name + "!"\n'


def usage(micros: int | None) -> UsageReport:
    return UsageReport(
        10, 20, 0, 0, 0, micros, UsageStatus.REPORTED, "offline:fake", SubagentUsage(False, True)
    )


class FakeRuntime(ClaudeCodeRuntime):
    """Local synchronous fake child; never registers live capability evidence."""

    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode
        self.request: AgentRequest | None = None
        self.cancelled = False

    @override
    def start(self, request: AgentRequest) -> SessionHandle:
        self.request = request
        assert request.client_home is not None
        home = Path(request.client_home)
        home.mkdir(parents=True)
        (home / ".credentials.json").write_text(json.dumps({"token": SECRET}), encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                "from pathlib import Path; import os,sys; "
                "Path('greeting.py').write_text(sys.argv[1]); "
                "print(os.environ['HOME']); print(os.environ['EVAL_TOKEN'])",
                FIXED if self.mode != "broken" else "def greet(name): return 'wrong'\n",
            ],
            cwd=request.workdir,
            env={"HOME": request.client_home, "EVAL_TOKEN": SECRET},
            capture_output=True,
            text=True,
            check=True,
            timeout=request.limits.timeout_seconds,
        )
        assert len(completed.stdout.encode()) < request.limits.max_output_bytes
        assert completed.stdout.splitlines()[0] == request.client_home
        step = Path(request.workdir).parent / "state" / "steps" / request.request_id
        step.mkdir(parents=True)
        (step / "stream.jsonl").write_text(json.dumps({"text": SECRET}) + "\n", encoding="utf-8")
        (step / "stream.stderr").write_text(completed.stdout, encoding="utf-8")
        return SessionHandle(
            self.runtime_id, request.request_id, None, None, datetime(2026, 11, 17, tzinfo=UTC), None
        )

    @override
    def events(self, handle: SessionHandle) -> Iterator[SessionEvent]:
        if self.mode == "interrupt":
            raise RuntimeError("fake stream interrupted")
        now = datetime(2026, 11, 17, tzinfo=UTC)
        yield SessionStarted(1, now, None, "sonnet", "offline-fake")
        yield UsageReported(2, now, usage(200_000), True)
        yield SessionCompleted(3, now, StopReason.END_TURN, "sha256:" + sha256(b"done").hexdigest())

    @override
    def result(self, handle: SessionHandle) -> RuntimeResult:
        return RuntimeResult(
            outcome="completed",
            final_text="done",
            structured=None,
            session_ref=None,
            model="sonnet",
            usage=usage(200_000),
            failure=None,
            exit=ExitInfo(0, None, False, 1),
            lingered=False,
            denials=(),
            api_retries=0,
            transcript_path=None,
            stderr_path=None,
        )

    @override
    def cancel(self, handle: SessionHandle, *, grace_seconds: float) -> CancellationResult:
        self.cancelled = True
        return CancellationResult(True, None, False)


def test_offline_policy_and_gate(request: pytest.FixtureRequest) -> None:
    assert request.node.get_closest_marker("evals") is None
    sock = socket.socket.__new__(socket.socket)
    with pytest.raises(RuntimeError, match="loopback"):
        sock.connect(("192.0.2.1", -1))
    # Root controls survived env scrubbing; the default runner has no live opt-in.
    # This test remains valid when the outer runner explicitly enables live evals.
    assert not any(name.startswith("SKM_") for name in os.environ)


@pytest.mark.parametrize("gate", [None, "0", "1"])
def test_collection_and_opt_in_survive_environment_scrubbing(
    runner: Callable[..., pytest.RunResult],
    pytester: pytest.Pytester,
    gate: str | None,
) -> None:
    suite = pytester.path / "evals"
    suite.mkdir()
    (suite / "conftest.py").write_text(Path(__file__).with_name("conftest.py").read_text(), encoding="utf-8")
    (suite / "test_harness.py").write_text(
        "import socket, pytest\n"
        "def test_offline(request):\n"
        "    assert request.node.get_closest_marker('evals') is None\n"
        "    assert request.node.get_closest_marker('skip') is None\n"
        "    sock = socket.socket.__new__(socket.socket)\n"
        "    with pytest.raises(RuntimeError, match='loopback'):\n"
        "        sock.connect(('192.0.2.1', -1))\n",
        encoding="utf-8",
    )
    live_source = (
        "import os\n"
        "def test_live(request):\n"
        "    assert request.node.get_closest_marker('evals') is not None\n"
        "    assert 'SKM_EVALS' not in os.environ\n"
        "    plugin = request.config.pluginmanager.getplugin(str(request.path.parent / 'conftest.py'))\n"
        "    plugin.require_opt_in(request.config)\n"
        "    assert plugin.parse_ceiling(request.config.getoption('evals_max_usd')) == 123456\n"
    )
    for name in ("test_claude_code_small_task.py", "test_codex_small_task.py"):
        (suite / name).write_text(live_source, encoding="utf-8")
    # Assert actual collection, before setup can apply any skip policy.
    with (suite / "conftest.py").open("a", encoding="utf-8") as stream:
        stream.write(
            "\n@pytest.hookimpl(trylast=True)\n"
            "def pytest_collection_finish(session):\n"
            "    assert len(session.items) == 3\n"
            "    for item in session.items:\n"
            "        live = item.path.name in LIVE_FILES\n"
            "        assert bool(item.get_closest_marker('evals')) == live\n"
            "        assert item.get_closest_marker('skip') is None\n"
            "        assert item.get_closest_marker('skipif') is None\n"
        )
    controls = {"SKM_EVALS_MAX_USD": "0.123456"}
    if gate is not None:
        controls["SKM_EVALS"] = gate
    result = runner(
        "", controls=controls, args=("evals", "-rs", "--import-mode=importlib", "-p", "xdist.plugin")
    )
    if gate == "1":
        result.assert_outcomes(passed=3)
    else:
        result.assert_outcomes(passed=1, skipped=2)
        result.stdout.fnmatch_lines(["*SKM_EVALS=1*"])


def test_fixture_gate_refuses_before_live_access(request: pytest.FixtureRequest) -> None:
    root = cast(
        "ModuleType", request.config.pluginmanager.getplugin(str(Path(__file__).parents[1] / "conftest.py"))
    )
    controls = request.config.stash[root.CONTROLS]
    request.config.stash[root.CONTROLS] = replace(controls, evals=False)
    try:
        with pytest.raises(pytest.skip.Exception, match="SKM_EVALS=1"):
            require_opt_in(request.config)
    finally:
        request.config.stash[root.CONTROLS] = controls


@pytest.mark.parametrize("invalid", ["0", "-1", "NaN", "Infinity", "bad", "0.0000001"])
def test_invalid_budget_is_rejected(invalid: str) -> None:
    with pytest.raises(pytest.UsageError, match="finite and positive"):
        parse_ceiling(invalid)


def test_budget_accumulates_and_stops_without_treating_unknown_as_zero() -> None:
    budget = EvalBudget(parse_ceiling("0.50"))
    budget.record(usage(200_000))
    budget.require_available()
    budget.record(usage(300_001))
    assert budget.spent == 500_001
    with pytest.raises(pytest.exit.Exception, match="500001 >= 500000"):
        budget.require_available()
    for missing in (unknown_usage(), usage(None)):
        budget = EvalBudget(500_000)
        budget.record(usage(10))
        budget.record(missing)
        assert budget.spent == 10
        with pytest.raises(pytest.exit.Exception, match="unknown usage or unpriced cost"):
            budget.require_available()


@pytest.mark.parametrize("runtime_id", ["claude_code", "codex"])
def test_missing_credentials_skip_with_reason(tmp_path: Path, runtime_id: str) -> None:
    with pytest.raises(pytest.skip.Exception, match="user credentials absent"):
        require_credentials(runtime_id, {}, tmp_path)


@pytest.mark.parametrize("runtime_id", ["claude_code", "codex"])
def test_missing_cli_skips_before_probing(monkeypatch: pytest.MonkeyPatch, runtime_id: str) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(pytest.skip.Exception, match="is not installed on PATH"):
        locate_cli(runtime_id)


def test_codex_home_user_selects_credentials_and_redacts_their_secret(tmp_path: Path) -> None:
    home = tmp_path / "home"
    default_credentials = home / ".codex" / "auth.json"
    default_credentials.parent.mkdir(parents=True)
    default_secret = "default-home-token-12345678"
    default_credentials.write_text(json.dumps({"token": default_secret}), encoding="utf-8")
    codex_home = tmp_path / "custom-codex-home"
    codex_home.mkdir()
    custom_credentials = codex_home / "auth.json"
    custom_credentials.write_text(json.dumps({"token": SECRET}), encoding="utf-8")
    env = {"CODEX_HOME_USER": str(codex_home)}

    credentials = require_credentials("codex", env, home)
    assert credentials == custom_credentials
    redactor = credential_redactor(env, credentials)
    assert SECRET not in redactor.text(SECRET)
    assert json.dumps(SECRET)[1:-1] not in redactor.text(json.dumps({"text": SECRET}))
    assert redactor.text(default_secret) == default_secret

    # A configured but missing source must not fall back to the default HOME credentials.
    custom_credentials.unlink()
    with pytest.raises(pytest.skip.Exception, match="user credentials absent"):
        require_credentials("codex", env, home)


@pytest.mark.parametrize("mode", ["success", "broken", "interrupt"])
def test_fake_child_caps_checks_sanitized_evidence_and_cleanup(tmp_path: Path, mode: str) -> None:
    before = dict(os.environ)
    credentials = tmp_path / "auth.json"
    credentials.write_text(json.dumps({"token": SECRET}), encoding="utf-8")
    redactor = credential_redactor({"EVAL_TOKEN": SECRET}, credentials)
    budget = EvalBudget(500_000)
    destination = tmp_path / "evidence"
    metadata: dict[str, JsonValue] = {"check": "not_run", "capabilities": "offline fake only"}
    runtime = FakeRuntime(mode)
    with disposable_task() as root:
        request = make_request("claude_code", root)
        assert request.limits == LIMITS
        assert 0 < LIMITS.timeout_seconds <= 120
        assert LIMITS.max_output_tokens is not None
        assert 0 < LIMITS.max_output_tokens <= 1024
        assert LIMITS.max_turns is not None
        assert 0 < LIMITS.max_turns <= 4
        assert 0 < LIMITS.max_output_bytes <= 256 * 1024
        assert request.client_home is not None
        assert not Path(request.client_home).is_relative_to(root / "repo")
        assert (root / "repo" / "check.py").read_text() == CHECK
        if mode == "success":
            run_small_task(runtime, root, budget, destination, metadata, redactor)
        else:
            error = subprocess.CalledProcessError if mode == "broken" else RuntimeError
            with pytest.raises(error):
                run_small_task(runtime, root, budget, destination, metadata, redactor)
    assert not root.exists(), "repository, isolated HOME, credentials and raw captures must be removed"
    assert dict(os.environ) == before
    assert budget.spent == (0 if mode == "interrupt" else 200_000)
    assert runtime.cancelled == (mode == "interrupt")
    summary = json.loads((destination / "summary.json").read_text())
    assert summary["check"] == {"success": "passed", "broken": "failed", "interrupt": "not_run"}[mode]
    assert summary["outcome"] == ("passed" if mode == "success" else "failed")
    if mode == "interrupt":
        assert summary["usage"]["status"] == "unknown"
        assert summary["usage"]["cost_usd_micros"] is None
    for artifact in destination.iterdir():
        text = artifact.read_text()
        assert SECRET not in text
        assert json.dumps(SECRET)[1:-1] not in text
        assert artifact.stat().st_mode & 0o077 == 0
    assert not list(destination.rglob("*credentials*"))
