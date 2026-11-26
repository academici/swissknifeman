"""Opt-in small-task evals; importing this module never contacts a provider."""

from __future__ import annotations

import json
import os
import pwd
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from typing import cast
from uuid import uuid4

import pytest

from skm.adapters.runtimes.claude_code.runtime import ClaudeCodeRuntime
from skm.adapters.runtimes.codex.runtime import CodexRuntime
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.ids import HostId
from skm.kernel.isolation import IsolationProfile
from skm.kernel.json_types import JsonValue
from skm.modules.runtimes.domain.classes import Effort, RoleId
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.installation import AuthState
from skm.modules.runtimes.domain.request import (
    AgentRequest,
    CommandRules,
    NetworkRules,
    PathRule,
    PathRules,
    PermissionGrant,
    ProcessOwner,
    ResultFormat,
    RuntimeLimits,
    validate_request,
)
from skm.modules.runtimes.domain.result import RuntimeResult, validate_result_observation
from skm.modules.runtimes.domain.session_events import validate_event_stream
from skm.modules.runtimes.domain.usage import UsageReport, UsageStatus, unknown_usage, usage_to_json
from skm.modules.runtimes.ports import AgentRuntime
from skm.platform.logging.redaction import Redactor
from skm.platform.system_clock import SystemClock
from support.git_repo import init_git_repo

LIVE_FILES = frozenset({"test_claude_code_small_task.py", "test_codex_small_task.py"})
AUTH_NAMES = {
    "claude_code": ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"),
    "codex": ("OPENAI_API_KEY", "CODEX_API_KEY"),
}
LIMITS = RuntimeLimits(
    timeout_seconds=90,
    idle_timeout_seconds=30,
    max_turns=4,
    max_output_tokens=1024,
    max_output_bytes=256 * 1024,
)
INITIAL = 'def greet(name):\n    return "Hello!"\n'
PROMPT = (
    "Change only greeting.py so greet(name) returns 'Hello, ' + name + '!'. "
    "Keep the function name and signature. Do not commit. Do not change check.py. "
    "The deterministic check is python check.py."
)
CHECK = (
    "from greeting import greet\nassert greet('Ada') == 'Hello, Ada!'\nassert greet('Lin') == 'Hello, Lin!'\n"
)
type LiveRuntime = Callable[[str], RuntimeResult]


def pytest_addoption(parser: pytest.Parser) -> None:
    # Initial eval paths load this hook before the root config scrubs SKM_*.
    # The Makefile passes the option explicitly as well, including for late loading.
    parser.addoption("--evals-max-usd", default=os.environ.get("SKM_EVALS_MAX_USD", "0.50"))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.parent == Path(__file__).parent and item.path.name in LIVE_FILES:
            item.add_marker(pytest.mark.evals)


def require_opt_in(config: pytest.Config) -> None:
    # Read the actual root plugin's StashKey, also when copied into a pytester suite.
    root = cast("ModuleType", config.pluginmanager.getplugin(str(Path(__file__).parents[1] / "conftest.py")))
    if not config.stash[root.CONTROLS].evals:
        pytest.skip("live eval requires explicit SKM_EVALS=1")


def parse_ceiling(value: str) -> int:
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount <= 0:
            raise ValueError
        micros = int((amount * 1_000_000).to_integral_value(rounding=ROUND_FLOOR))
        if micros <= 0:
            raise ValueError
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise pytest.UsageError("SKM_EVALS_MAX_USD/--evals-max-usd must be finite and positive") from exc
    else:
        return micros


@dataclass
class EvalBudget:
    ceiling: int
    spent: int = 0
    stop_reason: str | None = None

    def require_available(self) -> None:
        if self.stop_reason is not None:
            pytest.exit(self.stop_reason, returncode=1)

    def record(self, usage: UsageReport) -> None:
        if usage.status is UsageStatus.UNKNOWN or usage.cost_usd_micros is None:
            self.stop_reason = "live eval budget stopped: unknown usage or unpriced cost (never zero)"
            return
        self.spent += usage.cost_usd_micros
        if self.spent >= self.ceiling:
            self.stop_reason = f"live eval budget stopped: {self.spent} >= {self.ceiling} USD micros"


@pytest.fixture(scope="session")
def eval_budget(pytestconfig: pytest.Config) -> EvalBudget:
    return EvalBudget(parse_ceiling(str(pytestconfig.getoption("evals_max_usd"))))


@contextmanager
def disposable_task() -> Iterator[Path]:
    with TemporaryDirectory(prefix="skm-live-eval-") as temporary:
        root = Path(temporary)
        repo = init_git_repo(root / "repo")
        repo.commit_file("greeting.py", INITIAL)
        repo.commit_file("check.py", CHECK)
        yield root


def make_request(runtime_id: str, root: Path) -> AgentRequest:
    step_id, attempt_id = uuid4(), uuid4()
    paths = PathRules((PathRule(str(root / "repo"), "**"),), ())
    return AgentRequest(
        request_id=str(step_id),
        runtime_id=runtime_id,
        model="sonnet" if runtime_id == "claude_code" else "gpt-6-sol",
        effort=Effort.LOW,
        role=RoleId.EXECUTOR,
        rendered_prompt=PROMPT,
        prompt_digest="sha256:" + sha256(PROMPT.encode()).hexdigest(),
        result_format=ResultFormat.TEXT,
        result_schema_urn=None,
        workdir=str(root / "repo"),
        permissions=PermissionGrant(
            paths,
            paths,
            CommandRules("none", (), (), ()),
            NetworkRules("any", ()),
            frozenset({"Read", "Edit", "Write"}),
            frozenset(),
        ),
        isolation_profile=IsolationProfile.WORKTREE,
        process_owner=ProcessOwner(
            host_id=uuid4(),
            worker_id=uuid4(),
            attempt_id=attempt_id,
            stage_record_id=uuid4(),
            unit_kind="step",
            unit_id=step_id,
            owner_nonce=uuid4().hex,
            identity_dir=str(root / "identities"),
        ),
        config_mode="isolated",
        client_home=str(root / "client-homes" / str(attempt_id) / runtime_id),
        resume_session_ref=None,
        session_policy="ephemeral",
        env_allowlist=AUTH_NAMES[runtime_id],
        extra_env={},
        secret_env={},
        mcp_servers=(),
        limits=LIMITS,
        labels={"step_id": str(step_id)},
    )


def require_credentials(runtime_id: str, env: Mapping[str, str], home: Path) -> Path:
    codex_home = Path(env["CODEX_HOME_USER"]) if env.get("CODEX_HOME_USER") else home / ".codex"
    credentials = (
        home / ".claude" / ".credentials.json" if runtime_id == "claude_code" else codex_home / "auth.json"
    )
    if not credentials.is_file() and not any(env.get(name) for name in AUTH_NAMES[runtime_id]):
        pytest.skip(f"{runtime_id}: user credentials absent (real HOME or provider auth environment)")
    return credentials


def locate_cli(runtime_id: str) -> str:
    binary_name = {"claude_code": "claude", "codex": "codex"}[runtime_id]
    binary = shutil.which(binary_name)
    if binary is None:
        pytest.skip(f"{runtime_id}: CLI {binary_name!r} is not installed on PATH")
    return binary


def credential_redactor(env: Mapping[str, str], credentials: Path) -> Redactor:
    redactor = Redactor()

    def register(value: JsonValue) -> None:
        if isinstance(value, str):
            redactor.register_secret(value)
            redactor.register_secret(json.dumps(value)[1:-1])
        elif isinstance(value, dict):
            for child in value.values():
                register(child)
        elif isinstance(value, list):
            for child in value:
                register(child)

    for name, value in env.items():
        if any(word in name.upper() for word in ("TOKEN", "KEY", "SECRET", "PASSWORD")):
            register(value)
    if credentials.is_file():
        # Fail closed on malformed credentials; never export a transcript without their masking registry.
        register(json.loads(credentials.read_text(encoding="utf-8")))
    return redactor


def preserve_evidence(
    destination: Path,
    root: Path,
    result: RuntimeResult | None,
    metadata: dict[str, JsonValue],
    redactor: Redactor,
) -> None:
    destination.mkdir(mode=0o700, parents=True)
    # Only known stream files, never the credential-containing client homes or result envelopes.
    for path in sorted((root / "state" / "steps").glob("*/stream.*")):
        if path.is_file() and not path.is_symlink():
            safe = redactor.text(path.read_text(encoding="utf-8", errors="replace"))
            target = destination / f"{path.parent.name}-{path.name}"
            target.write_text(safe, encoding="utf-8")
            target.chmod(0o600)
    metadata["usage"] = usage_to_json(result.usage if result else unknown_usage())
    metadata["runtime_outcome"] = result.outcome if result else "unknown"
    metadata.setdefault("outcome", "passed" if metadata.get("check") == "passed" else "failed")
    target = destination / "summary.json"
    target.write_text(json.dumps(redactor.document(metadata), indent=2) + "\n", encoding="utf-8")
    target.chmod(0o600)


def run_small_task(
    runtime: AgentRuntime,
    root: Path,
    budget: EvalBudget,
    destination: Path,
    metadata: dict[str, JsonValue],
    redactor: Redactor,
) -> RuntimeResult:
    budget.require_available()
    request = make_request(runtime.runtime_id, root)
    validate_request(request, runtime.capabilities())
    handle = runtime.start(request)
    result = None
    try:
        events = list(runtime.events(handle))
        result = runtime.result(handle)
        assert validate_event_stream(events) == ()
        assert validate_result_observation(result, request_id=request.process_owner.unit_id) == ()
        if result.failure is not None and result.failure.code is ErrorCode.RUNTIME_AUTH_EXPIRED:
            metadata["outcome"] = "skipped"
            pytest.skip(f"{runtime.runtime_id}: runtime rejected expired/missing credentials")
        assert result.outcome == "completed", "runtime did not complete; inspect sanitized evidence"
        assert not result.exit.output_truncated
        metadata["check"] = "failed"
        assert (root / "repo" / "greeting.py").read_text(encoding="utf-8") != INITIAL
        assert (root / "repo" / "check.py").read_text(encoding="utf-8") == CHECK
        git = shutil.which("git")
        assert git is not None
        changed = subprocess.run(
            [git, "diff", "--name-only", "HEAD"],
            cwd=root / "repo",
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        assert changed.stdout.splitlines() == ["greeting.py"]
        status = subprocess.run(
            [git, "status", "--porcelain", "--untracked-files=all"],
            cwd=root / "repo",
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        assert status.stdout.splitlines() == [" M greeting.py"]
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                "import runpy,sys;sys.path.insert(0,'.');runpy.run_path('check.py')",
            ],
            cwd=root / "repo",
            capture_output=True,
            check=True,
            timeout=10,
        )
        metadata["check"] = "passed"
        return result
    finally:
        try:
            if result is None:
                runtime.cancel(handle, grace_seconds=3)
        finally:
            budget.record(result.usage if result else unknown_usage())
            metadata["budget_spent_usd_micros"] = budget.spent
            metadata["budget_stop_reason"] = budget.stop_reason
            preserve_evidence(destination, root, result, metadata, redactor)


@pytest.fixture
def live_runtime(request: pytest.FixtureRequest, eval_budget: EvalBudget) -> Iterator[LiveRuntime]:
    require_opt_in(request.config)
    if request.node.get_closest_marker("evals") is None:
        pytest.fail("live_runtime requires an evals-marked live test")
    if request.config.getoption("numprocesses", default=0):
        pytest.fail("live evals require serial execution (-n 0) for a shared run budget")
    eval_budget.require_available()

    def run(runtime_id: str) -> RuntimeResult:
        eval_budget.require_available()
        binary = locate_cli(runtime_id)
        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        env = {**os.environ, "HOME": str(home)}
        credentials = require_credentials(runtime_id, env, home)
        redactor = credential_redactor(env, credentials)
        with disposable_task() as root:
            runtime: AgentRuntime = (
                ClaudeCodeRuntime(state_dir=root / "state", binary=binary, environ=env, user_home=home)
                if runtime_id == "claude_code"
                else CodexRuntime(state_dir=root / "state", binary=binary, environ=env, user_home=home)
            )
            installation = runtime.detect(
                DetectProbe(HostId(uuid4()), binary, AUTH_NAMES[runtime_id], timeout_seconds=10)
            )
            if installation.auth_state in (AuthState.MISSING, AuthState.EXPIRED):
                pytest.skip(f"{runtime_id}: runtime detect reports {installation.auth_state.value} auth")
            assert installation.version is not None, "runtime detect did not identify CLI version"
            assert not installation.details.get("missing_flags"), "CLI is missing required flags"
            cache = request.config.cache
            assert cache is not None
            artifacts = cache.mkdir("live-evals")
            artifacts.chmod(0o700)
            destination = artifacts / f"{runtime_id}-{uuid4().hex}"
            metadata: dict[str, JsonValue] = {
                "date": SystemClock().now().isoformat(),
                "runtime": runtime_id,
                "version": installation.version,
                "admission": "bounded executor; isolated config; worktree; validated request",
                "capabilities": {
                    r.capability.value: r.status.value for r in runtime.capabilities().records.values()
                },
                "check": "not_run",
                "budget_ceiling_usd_micros": eval_budget.ceiling,
            }
            try:
                return run_small_task(runtime, root, eval_budget, destination, metadata, redactor)
            except CapabilityUnavailable as exc:
                if exc.code is ErrorCode.RUNTIME_AUTH_EXPIRED:
                    pytest.skip(f"{runtime_id}: runtime rejected expired/missing credentials")
                raise

    yield run
    # Stop only after the temporary repository and isolated credentials have been removed.
    eval_budget.require_available()
