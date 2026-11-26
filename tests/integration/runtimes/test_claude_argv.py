"""Offline unit, integration, and contract replay tests for Claude Code runtime adapter.

Never invokes a real ``claude`` CLI binary. All binary probes and subprocess executions use
hermetic synthetic scripts or in-memory process doubles inside ``tmp_path``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from dataclasses import replace
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from uuid import UUID, uuid4

import pytest

from fakes.clock import FakeMonotonic, FrozenClock
from skm.adapters.runtimes._cli_session.probe import (
    CommandOutput,
    ProbeCacheKey,
)
from skm.adapters.runtimes.claude_code.detect import (
    OPTIONAL_FLAGS,
    REQUIRED_FLAGS,
    ClaudeDetector,
    parse_version_output,
)
from skm.adapters.runtimes.claude_code.launch import (
    CREDENTIAL_FILENAME,
    WRITABLE_CLIENT_HOME_DIRS,
    build_launch_plan,
    compute_launch_config_digest,
)
from skm.adapters.runtimes.claude_code.permissions import denial_hint
from skm.adapters.runtimes.claude_code.runtime import ClaudeCodeRuntime
from skm.adapters.runtimes.claude_code.stream_parser import ClaudeStreamParser
from skm.adapters.runtimes.claude_code.usage import UsageAccumulator, normalize_usage_counts
from skm.bootstrap.builtins import BUILTIN_COMPONENTS, component_problem
from skm.bootstrap.runtimes import RUNTIME_FACTORIES
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.ids import HostId
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.capability import (
    ENFORCING_CAPABILITIES,
    Capability,
    CapabilityStatus,
    SelfLoadKind,
    StaticCapabilityCatalog,
    effective_capabilities,
    explain_self_loads,
    parse_capabilities,
)
from skm.modules.runtimes.domain.catalog import Pricing
from skm.modules.runtimes.domain.classes import Effort, RoleId
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.error_rules import (
    ErrorClass,
    RuntimeSignals,
    classify,
    parse_error_rules,
)
from skm.modules.runtimes.domain.installation import AuthState
from skm.modules.runtimes.domain.request import (
    AgentRequest,
    CommandRules,
    McpServerSpec,
    NetworkRules,
    PathRule,
    PathRules,
    PermissionGrant,
    ProcessOwner,
    ProcessOwnership,
    ResultFormat,
    RuntimeLimits,
    SecretStr,
)
from skm.modules.runtimes.domain.result import result_to_json, validate_result_observation
from skm.modules.runtimes.domain.session_events import (
    CancelIgnored,
    SessionCompleted,
    SessionFailed,
    SessionStarted,
    TextDelta,
    ToolCallStatus,
    ToolCompleted,
    ToolRequested,
    UsageReported,
    session_event_to_json,
    validate_event_stream,
)
from skm.modules.runtimes.domain.usage import SubagentUsage, UsageStatus, cost
from skm.platform.config.sources.document import decode_document
from skm.platform.logging.redaction import MASK, Redactor
from skm.platform.schema.registry import SchemaRegistry
from skm.plugin_api.manifest import ComponentKind

ROOT = Path(__file__).resolve().parents[3]
ADAPTER_DIR = ROOT / "src/skm/adapters/runtimes/claude_code"
FIXTURES_DIR = ROOT / "tests/fixtures/runtimes/claude_code"

ALL_SUPPORTED_HELP_TEXT = "Usage: claude [options]\n" + "\n".join(
    f"  {flag}  supported option" for flag in (*REQUIRED_FLAGS, *OPTIONAL_FLAGS)
)


def _write_executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    os.chmod(path, 0o700)
    return path


def _make_stub_binary(tmp_path: Path, name: str = "claude") -> Path:
    return _write_executable(tmp_path / "bin" / name, "#!/bin/sh\nexit 0\n")


def _make_user_home(tmp_path: Path, *, with_credentials: bool = True) -> Path:
    home = tmp_path / "host-user-home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    if with_credentials:
        cred = claude_dir / CREDENTIAL_FILENAME
        cred.write_text('{"claudeAiOauth":{"accessToken":"synthetic-oauth-token"}}\n', encoding="utf-8")
        os.chmod(cred, 0o600)
    return home


def _make_request(
    tmp_path: Path,
    *,
    role: RoleId = RoleId.EXECUTOR,
    writable: bool = True,
    command_mode: Literal["none", "allowlist", "denylist", "any"] = "any",
    programs: tuple[str, ...] = (),
    deny_patterns: tuple[str, ...] = (),
    ask_patterns: tuple[str, ...] = (),
    network_mode: Literal["none", "allowlist", "any"] = "any",
    network_hosts: tuple[str, ...] = (),
    tools: frozenset[str] = frozenset(),
    isolation_profile: IsolationProfile = IsolationProfile.WORKTREE,
    config_mode: Literal["isolated", "inherit"] = "isolated",
    session_policy: Literal["ephemeral", "persistent"] = "ephemeral",
    resume_session_ref: str | None = None,
    effort: Effort | None = Effort.HIGH,
    model: str = "sonnet",
    prompt: str = "Implement module X according to contract.",
    extra_read_roots: tuple[str, ...] = (),
    extra_env: dict[str, str] | None = None,
    env_allowlist: tuple[str, ...] = (),
    secret_token: str | None = "skm-assign-secret-token-xyz987",
    mcp_servers: tuple[McpServerSpec, ...] = (),
    labels: dict[str, str] | None = None,
    timeout_seconds: int = 60,
    client_home: Path | None = None,
) -> AgentRequest:
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    step_id = uuid4()
    run_id = uuid4()
    read_rules = PathRules(
        tuple(PathRule(root, "**") for root in (str(workdir), *extra_read_roots)),
        (),
    )
    write_rules = PathRules((PathRule(str(workdir), "**"),), ()) if writable else PathRules((), ())
    owner = ProcessOwner(
        host_id=run_id,
        worker_id=run_id,
        attempt_id=run_id,
        stage_record_id=run_id,
        unit_kind="step",
        unit_id=step_id,
        owner_nonce="synthetic-step-nonce-0001",
        identity_dir=str(state_dir / "identities"),
    )
    resolved_home = (
        None
        if config_mode == "inherit"
        else str(client_home or (state_dir / "client-homes" / str(run_id) / "claude_code"))
    )
    secrets = {"SKM_TOKEN": SecretStr(secret_token)} if secret_token is not None else {}
    merged_labels = {"run_id": str(run_id), "step_id": str(step_id), **(labels or {})}
    return AgentRequest(
        request_id=str(step_id),
        runtime_id="claude_code",
        model=model,
        effort=effort,
        role=role,
        rendered_prompt=prompt,
        prompt_digest=f"sha256:{sha256(prompt.encode('utf-8')).hexdigest()}",
        result_format=ResultFormat.TEXT,
        result_schema_urn=None,
        workdir=str(workdir),
        permissions=PermissionGrant(
            fs_read=read_rules,
            fs_write=write_rules,
            commands=CommandRules(command_mode, programs, deny_patterns, ask_patterns),
            network=NetworkRules(network_mode, network_hosts),
            tools=tools,
            external_effects=frozenset(),
        ),
        isolation_profile=isolation_profile,
        process_owner=owner,
        config_mode=config_mode,
        client_home=resolved_home,
        resume_session_ref=resume_session_ref,
        session_policy=session_policy,
        env_allowlist=env_allowlist,
        extra_env=extra_env or {},
        secret_env=secrets,
        mcp_servers=mcp_servers,
        limits=RuntimeLimits(
            timeout_seconds=timeout_seconds,
            idle_timeout_seconds=15,
            max_turns=10,
            max_output_tokens=None,
            max_output_bytes=4 * 1024 * 1024,
        ),
        labels=merged_labels,
    )


# ---------------------------------------------------------------------------
# 1. Static Declarations, Capabilities, Self-Loads & Bootstrap Registration
# ---------------------------------------------------------------------------


def test_claude_code_static_toml_declarations_validate_against_product_schemas() -> None:
    schemas = SchemaRegistry.load_default()
    caps_doc = decode_document((ADAPTER_DIR / "capabilities.toml").read_text(encoding="utf-8"), "toml")
    rules_doc = decode_document((ADAPTER_DIR / "error_rules.toml").read_text(encoding="utf-8"), "toml")

    assert schemas.validate("urn:skm:runtimes:capabilities:v1", caps_doc) == ()
    assert schemas.validate("urn:skm:runtimes:error-rules:v1", rules_doc) == ()

    caps = parse_capabilities(caps_doc)
    rules = parse_error_rules(rules_doc)
    catalog = StaticCapabilityCatalog(declarations={"claude_code": caps}, rules={"claude_code": rules})
    assert catalog.registered() == frozenset({"claude_code"})
    assert set(caps.records) == set(Capability)
    assert caps.read_only_network is True
    assert caps.config_isolation is not None
    assert "CLAUDE_CONFIG_DIR" in caps.config_isolation.env
    assert "CLAUDE_CODE_DISABLE_CLAUDE_MDS" in caps.config_isolation.env
    assert "CLAUDE_CODE_DISABLE_AUTO_MEMORY" in caps.config_isolation.env

    by_kind = {item.kind: item for item in caps.self_loads}
    assert by_kind[SelfLoadKind.PROJECT_SETTINGS].suppressed_by == "config_isolation"

    # Without host verification context, enforcing capabilities degrade to unknown; functional stay active.
    eff = effective_capabilities(caps, (), host_version="2.1.266", now=date(2026, 10, 30))
    for cap in ENFORCING_CAPABILITIES:
        assert eff.status(cap) is CapabilityStatus.UNKNOWN
    assert eff.supports(Capability.HEADLESS_EXECUTION)
    assert eff.supports(Capability.SESSION_RESUME)

    # When config_isolation is verified, explain_self_loads marks project_settings suppressed in BOTH modes.
    iso_views = {v.kind: v for v in explain_self_loads(caps, "isolated")}
    inh_views = {v.kind: v for v in explain_self_loads(caps, "inherit")}
    assert iso_views[SelfLoadKind.PROJECT_SETTINGS].active is False
    assert inh_views[SelfLoadKind.PROJECT_SETTINGS].active is False
    assert iso_views[SelfLoadKind.USER_CONFIG].active is False
    assert inh_views[SelfLoadKind.USER_CONFIG].active is True


def test_claude_code_bootstrap_factories_satisfy_builtin_owner_protocol(tmp_path: Path) -> None:
    assert set(RUNTIME_FACTORIES) == {
        "antigravity",
        "claude_code",
        "claude-code",
        "codex",
        "codex-cli",
        "grok",
        "cursor",
        "cursor-agent",
        "gemini_cli",
    }
    spec = next(
        item
        for item in BUILTIN_COMPONENTS
        if item.kind is ComponentKind.RUNTIME and item.key == "claude_code"
    )
    for key in ("claude_code", "claude-code"):
        built = RUNTIME_FACTORIES[key]()
        assert isinstance(built, ClaudeCodeRuntime)
        assert built.runtime_id == "claude_code"
        assert component_problem(spec, built) is None

    fake_bin = _make_stub_binary(tmp_path)
    ctx = SimpleNamespace(
        config={
            "runtimes.binaries": {"claude_code": str(fake_bin)},
            "runtimes.credentials.copy": {"claude_code": False},
            "runtimes.claude_code": {"allow_skip_permissions": True},
        }
    )
    configured = RUNTIME_FACTORIES["claude_code"](ctx, environ={"PATH": str(fake_bin.parent)})
    assert isinstance(configured, ClaudeCodeRuntime)
    assert configured._binary == str(fake_bin)
    assert configured._copy_credentials is False
    assert configured._allow_skip_permissions is True


# ---------------------------------------------------------------------------
# 2. Probing, Timeout Retry, 6-Tuple Cache Key & Missing-Flag Degradation
# ---------------------------------------------------------------------------


def test_claude_code_detect_caches_by_six_tuple_and_invalidates_on_change(tmp_path: Path) -> None:
    binary = _make_stub_binary(tmp_path)
    calls: list[tuple[str, ...]] = []

    def fake_run(argv: tuple[str, ...], *, env: object, timeout_seconds: float) -> CommandOutput:
        del env
        calls.append(argv)
        if argv[-1] == "--version":
            assert timeout_seconds == 10.0
            return CommandOutput(0, "2.1.266 (Claude Code)\n", "")
        assert argv[-1] == "--help"
        assert timeout_seconds == 20.0
        return CommandOutput(0, ALL_SUPPORTED_HELP_TEXT, "")

    kernel_state = ["Linux:6.8.0"]
    detector = ClaudeDetector(run_cmd=fake_run, os_kernel_fn=lambda: kernel_state[0])
    digest_a = "sha256:" + "a" * 64
    digest_b = "sha256:" + "b" * 64
    env = {"PATH": str(binary.parent)}

    probed_1 = detector.probe(
        binary="claude",
        environ=env,
        env_allowlist=(),
        adapter_version="0.1.0",
        launch_config_digest=digest_a,
    )
    assert probed_1.version == "2.1.266"
    assert probed_1.missing_required_flags == ()
    assert probed_1.safe_mode_supported is True
    assert isinstance(probed_1.cache_key, ProbeCacheKey)
    assert len(calls) == 2

    # Identical 6-tuple hits cache with zero subprocess invocations.
    probed_2 = detector.probe(
        binary="claude",
        environ=env,
        env_allowlist=(),
        adapter_version="0.1.0",
        launch_config_digest=digest_a,
    )
    assert probed_2 is probed_1
    assert len(calls) == 2

    # Changing launch_config_digest invalidates cache.
    detector.probe(
        binary="claude",
        environ=env,
        env_allowlist=(),
        adapter_version="0.1.0",
        launch_config_digest=digest_b,
    )
    assert len(calls) == 4

    # Changing adapter_version invalidates cache.
    detector.probe(
        binary="claude",
        environ=env,
        env_allowlist=(),
        adapter_version="0.2.0",
        launch_config_digest=digest_b,
    )
    assert len(calls) == 6

    # Changing os_kernel invalidates cache.
    kernel_state[0] = "Linux:6.11.0"
    detector.probe(
        binary="claude",
        environ=env,
        env_allowlist=(),
        adapter_version="0.2.0",
        launch_config_digest=digest_b,
    )
    assert len(calls) == 8

    # Mutating binary contents changes binary_sha256 and invalidates cache.
    _write_executable(binary, "#!/bin/sh\n# updated binary bytes\nexit 0\n")
    probed_mutated = detector.probe(
        binary="claude",
        environ=env,
        env_allowlist=(),
        adapter_version="0.2.0",
        launch_config_digest=digest_b,
    )
    assert probed_mutated.binary_sha256 != probed_1.binary_sha256
    assert len(calls) == 10


def test_claude_code_detect_retries_help_on_timeout_and_degrades_missing_flags(tmp_path: Path) -> None:
    binary = _make_stub_binary(tmp_path)
    help_attempts = 0
    reduced_help = "\n".join(
        f"  {flag}" for flag in REQUIRED_FLAGS if flag not in ("--setting-sources", "--mcp-config")
    )

    def flaky_runner(argv: tuple[str, ...], *, env: object, timeout_seconds: float) -> CommandOutput:
        nonlocal help_attempts
        del env
        if argv[-1] == "--version":
            return CommandOutput(0, "claude-code version 2.0.14\n", "")
        help_attempts += 1
        if help_attempts == 1:
            raise subprocess.TimeoutExpired(argv, timeout_seconds)
        return CommandOutput(0, reduced_help, "")

    runtime = ClaudeCodeRuntime(
        state_dir=tmp_path / "state",
        binary=str(binary),
        environ={},
        probe_runner=flaky_runner,
    )
    inst = runtime.detect(
        DetectProbe(host_id=HostId(uuid4()), binary=None, env_allowlist=(), timeout_seconds=10)
    )
    assert help_attempts == 2
    assert inst.version == "2.0.14"
    assert inst.auth_state is AuthState.UNKNOWN
    assert "missing_flags" in inst.details

    caps = runtime.capabilities()
    assert caps.status(Capability.HEADLESS_EXECUTION) is CapabilityStatus.UNSUPPORTED
    assert "--setting-sources" in caps.records[Capability.HEADLESS_EXECUTION].limitations
    assert "--mcp-config" in caps.records[Capability.HEADLESS_EXECUTION].limitations

    req = _make_request(tmp_path)
    with pytest.raises(CapabilityUnavailable) as exc_info:
        runtime.start(req)
    assert exc_info.value.code is ErrorCode.CAPABILITY_UNAVAILABLE

    assert parse_version_output("Claude CLI build 2.1.266-rc1") == "2.1.266"
    assert parse_version_output("no semantic version here") is None


def test_claude_code_detect_missing_binary_raises_file_not_found(tmp_path: Path) -> None:
    runtime = ClaudeCodeRuntime(
        state_dir=tmp_path / "state", binary="nonexistent-claude-bin", environ={"PATH": ""}
    )
    with pytest.raises(FileNotFoundError):
        runtime.detect(DetectProbe(host_id=HostId(uuid4()), binary=None, env_allowlist=(), timeout_seconds=5))

    req = _make_request(tmp_path)
    with pytest.raises(CapabilityUnavailable) as exc_info:
        runtime.start(req)
    assert exc_info.value.code is ErrorCode.RUNTIME_NOT_INSTALLED


# ---------------------------------------------------------------------------
# 3. Argv Rendering, Permission Flags, K16 Config Isolation & Landlock
# ---------------------------------------------------------------------------


def test_claude_code_launch_plan_readonly_scout_and_writable_executor(tmp_path: Path) -> None:
    binary = _make_stub_binary(tmp_path)
    user_home = _make_user_home(tmp_path, with_credentials=True)
    host_env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(user_home),
        "XDG_CONFIG_HOME": str(tmp_path / "host-xdg"),
    }

    # 1. Read-only reviewer with shell: Bash,Read,Grep,Glob + --disallowedTools Edit,Write,NotebookEdit
    ro_req = _make_request(tmp_path / "ro", role=RoleId.REVIEWER, writable=False, command_mode="any")
    ro_step = tmp_path / "ro/state/steps" / ro_req.request_id
    ro_own = ProcessOwnership(ro_req.process_owner, "pgroup_best_effort", "claude_code/ro")
    ro_plan = build_launch_plan(
        ro_req,
        binary_path=str(binary),
        step_dir=ro_step,
        ownership=ro_own,
        host_environ=host_env,
    )
    argv = ro_plan.claude_argv
    assert argv[:7] == (
        str(binary),
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        "sonnet",
    )
    assert argv[7:9] == ("--effort", "high")
    assert argv[9:11] == ("--permission-prompts", "none")
    assert "--safe-mode" in argv
    assert "--no-session-persistence" in argv
    assert argv[argv.index("--setting-sources") + 1] == "user"
    assert argv[argv.index("--tools") + 1] == "Bash,Read,Grep,Glob"
    assert argv[argv.index("--disallowedTools") + 1] == "Edit,Write,NotebookEdit"
    assert argv[argv.index("--allowedTools") + 1] == "Bash"
    assert "--permission-mode" not in argv
    assert "--bare" not in argv
    assert "--dangerously-skip-permissions" not in argv
    assert ro_req.rendered_prompt not in argv
    assert ro_plan.stdin == ro_req.rendered_prompt.encode("utf-8")

    # 2. Scout role: Bash omitted even if command_mode="any".
    scout_req = _make_request(tmp_path / "scout", role=RoleId.SCOUT, writable=False, command_mode="any")
    scout_step = tmp_path / "scout/state/steps" / scout_req.request_id
    scout_own = ProcessOwnership(scout_req.process_owner, "pgroup_best_effort", "claude_code/scout")
    scout_plan = build_launch_plan(
        scout_req,
        binary_path=str(binary),
        step_dir=scout_step,
        ownership=scout_own,
        host_environ=host_env,
    )
    s_argv = scout_plan.claude_argv
    assert s_argv[s_argv.index("--tools") + 1] == "Read,Grep,Glob"
    assert s_argv[s_argv.index("--disallowedTools") + 1] == "Edit,Write,NotebookEdit"
    assert "--allowedTools" not in s_argv

    # 3. Writable executor with command allowlist prefixes and extra directory under workdir.
    sub_dir = tmp_path / "exec/workdir/subpkg"
    sub_dir.mkdir(parents=True)
    exec_req = _make_request(
        tmp_path / "exec",
        role=RoleId.EXECUTOR,
        writable=True,
        command_mode="allowlist",
        programs=("git", "pytest"),
        extra_read_roots=(str(sub_dir),),
        session_policy="persistent",
        resume_session_ref="sess_prev_42",
    )
    exec_step = tmp_path / "exec/state/steps" / exec_req.request_id
    exec_own = ProcessOwnership(exec_req.process_owner, "pgroup_best_effort", "claude_code/exec")
    exec_plan = build_launch_plan(
        exec_req,
        binary_path=str(binary),
        step_dir=exec_step,
        ownership=exec_own,
        host_environ=host_env,
    )
    e_argv = exec_plan.claude_argv
    assert e_argv[e_argv.index("--tools") + 1] == "Bash,Read,Edit,Write,Grep,Glob"
    assert e_argv[e_argv.index("--permission-mode") + 1] == "acceptEdits"
    assert "--disallowedTools" not in e_argv
    assert e_argv[e_argv.index("--allowedTools") + 1] == "Bash(git *),Bash(pytest *)"
    assert "--no-session-persistence" not in e_argv
    assert e_argv[e_argv.index("--resume") + 1] == "sess_prev_42"
    assert e_argv[e_argv.index("--add-dir") + 1] == str(sub_dir)


def test_claude_code_k16_config_isolation_credentials_and_mcp_secrets(tmp_path: Path) -> None:
    binary = _make_stub_binary(tmp_path)
    user_home = _make_user_home(tmp_path, with_credentials=True)
    secret_value = "skm-super-secret-assignment-token-777"
    mcp = McpServerSpec(
        name="skm_bus",
        command=("/usr/bin/python3", "-m", "skm.mcp_bridge"),
        env={"SKM_BUS_MODE": "stdio"},
        secret_env_names=("SKM_TOKEN",),
    )
    req = _make_request(
        tmp_path / "iso",
        mcp_servers=(mcp,),
        secret_token=secret_value,
        extra_env={
            "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "0",  # attempt to weaken must be overridden back to "1"
            "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "0",
            "HOME": str(tmp_path / "evil-override"),
        },
        network_mode="allowlist",
        network_hosts=("api.anthropic.com",),
    )
    step_dir = tmp_path / "iso/state/steps" / req.request_id
    ownership = ProcessOwnership(req.process_owner, "pgroup_best_effort", "claude_code/iso")
    plan = build_launch_plan(
        req,
        binary_path=str(binary),
        step_dir=step_dir,
        ownership=ownership,
        host_environ={
            "PATH": "/usr/bin:/bin",
            "HOME": str(user_home),
            "XDG_CONFIG_HOME": str(tmp_path / "leak"),
        },
    )

    assert plan.client_home is not None
    assert plan.client_home.stat().st_mode & 0o777 == 0o700
    for subdir in WRITABLE_CLIENT_HOME_DIRS:
        assert (plan.client_home / subdir).is_dir()
        assert (plan.client_home / subdir).stat().st_mode & 0o777 == 0o700

    copied_cred = plan.client_home / CREDENTIAL_FILENAME
    assert copied_cred.is_file()
    assert copied_cred.stat().st_mode & 0o777 == 0o600

    # Child env enforces isolated client_home and mandatory disable flags; XDG_CONFIG_HOME stripped.
    env = plan.command.env
    assert env["HOME"] == str(plan.client_home)
    assert env["CLAUDE_CONFIG_DIR"] == str(plan.client_home)
    assert env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1"
    assert env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert "XDG_CONFIG_HOME" not in env
    assert env["SKM_TOKEN"] == secret_value

    # Step settings.json is 0600 outside workdir, enables sandbox, disables hooks, omits project MCPs.
    settings_path = plan.permissions.settings_path
    assert settings_path == step_dir / "settings.json"
    assert settings_path.stat().st_mode & 0o777 == 0o600
    settings_json = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings_json["sandbox"]["enabled"] is True
    assert settings_json["sandbox"]["network"]["allowedDomains"] == ["api.anthropic.com"]
    assert settings_json["disableAllHooks"] is True
    assert settings_json["enableAllProjectMcpServers"] is False

    # Step mcp.json is 0600, bound with --strict-mcp-config, and contains NO plaintext secret!
    assert plan.permissions.mcp_path is not None
    assert plan.permissions.mcp_path.stat().st_mode & 0o777 == 0o600
    mcp_raw = plan.permissions.mcp_path.read_text(encoding="utf-8")
    assert secret_value not in mcp_raw
    mcp_json = json.loads(mcp_raw)
    assert mcp_json["mcpServers"]["skm_bus"]["env"]["SKM_TOKEN"] == "${SKM_TOKEN}"
    assert "--mcp-config" in plan.claude_argv
    assert "--strict-mcp-config" in plan.claude_argv
    assert not any(secret_value in arg for arg in plan.command.argv)

    # Missing credentials when copy_credentials=False must fail closed with RUNTIME_AUTH_EXPIRED.
    nocred_req = _make_request(tmp_path / "nocred")
    nocred_step = tmp_path / "nocred/state/steps" / nocred_req.request_id
    nocred_own = ProcessOwnership(nocred_req.process_owner, "pgroup_best_effort", "claude_code/nocred")
    with pytest.raises(CapabilityUnavailable) as exc_info:
        build_launch_plan(
            nocred_req,
            binary_path=str(binary),
            step_dir=nocred_step,
            ownership=nocred_own,
            host_environ={"PATH": "/usr/bin:/bin", "HOME": str(user_home)},
            copy_credentials=False,
        )
    assert exc_info.value.code is ErrorCode.RUNTIME_AUTH_EXPIRED


def test_claude_code_isolated_home_accepts_api_key_secret_without_credentials_file(tmp_path: Path) -> None:
    binary = _make_stub_binary(tmp_path)
    user_home = _make_user_home(tmp_path, with_credentials=False)
    req = replace(
        _make_request(tmp_path / "secret-auth"), secret_env={"ANTHROPIC_API_KEY": SecretStr("sk-ant-x")}
    )
    plan = build_launch_plan(
        req,
        binary_path=str(binary),
        step_dir=tmp_path / "secret-auth/state/steps" / req.request_id,
        ownership=ProcessOwnership(req.process_owner, "pgroup_best_effort", "claude_code/secret-auth"),
        host_environ={"PATH": "/usr/bin:/bin", "HOME": str(user_home)},
        copy_credentials=False,
    )
    assert plan.client_home is not None
    assert not (plan.client_home / ".credentials.json").exists()
    assert plan.command.env["ANTHROPIC_API_KEY"] == "sk-ant-x"


def test_claude_code_trusted_full_access_landlock_and_self_loaded_context(tmp_path: Path) -> None:
    binary = _make_stub_binary(tmp_path)
    user_home = _make_user_home(tmp_path, with_credentials=True)
    host_env = {"PATH": "/usr/bin:/bin", "HOME": str(user_home)}

    # trusted-full-access WITHOUT host opt-in: allows user,project but NOT --dangerously-skip-permissions.
    tfa_req = _make_request(
        tmp_path / "tfa1",
        labels={"policy_profile": "trusted-full-access"},
        isolation_profile=IsolationProfile.WORKTREE,
    )
    tfa_plan_no_opt = build_launch_plan(
        tfa_req,
        binary_path=str(binary),
        step_dir=tmp_path / "tfa1/state/steps" / tfa_req.request_id,
        ownership=ProcessOwnership(tfa_req.process_owner, "pgroup_best_effort", "claude_code/tfa1"),
        host_environ=host_env,
        allow_skip_permissions=False,
    )
    assert tfa_plan_no_opt.setting_sources == "user,project"
    assert "--dangerously-skip-permissions" not in tfa_plan_no_opt.claude_argv

    # trusted-full-access WITH host opt-in AND non-none isolation: emits --dangerously-skip-permissions.
    tfa_req2 = _make_request(
        tmp_path / "tfa2",
        labels={"policy_profile": "trusted-full-access"},
        isolation_profile=IsolationProfile.WORKTREE,
    )
    tfa_plan_opt = build_launch_plan(
        tfa_req2,
        binary_path=str(binary),
        step_dir=tmp_path / "tfa2/state/steps" / tfa_req2.request_id,
        ownership=ProcessOwnership(tfa_req2.process_owner, "pgroup_best_effort", "claude_code/tfa2"),
        host_environ=host_env,
        allow_skip_permissions=True,
    )
    assert "--dangerously-skip-permissions" in tfa_plan_opt.claude_argv

    # Host opt-in WITHOUT trusted-full-access: NEVER emits --dangerously-skip-permissions, keeps "user".
    std_req = _make_request(tmp_path / "std", isolation_profile=IsolationProfile.WORKTREE)
    std_plan = build_launch_plan(
        std_req,
        binary_path=str(binary),
        step_dir=tmp_path / "std/state/steps" / std_req.request_id,
        ownership=ProcessOwnership(std_req.process_owner, "pgroup_best_effort", "claude_code/std"),
        host_environ=host_env,
        allow_skip_permissions=True,
    )
    assert std_plan.setting_sources == "user"
    assert "--dangerously-skip-permissions" not in std_plan.claude_argv

    # Landlock profile prefixes python -P -m skm.adapters.sandbox.landlock_exec --no-default-rw --min-abi 3.
    ll_rw_req = _make_request(tmp_path / "ll_rw", writable=True, isolation_profile=IsolationProfile.LANDLOCK)
    ll_rw_plan = build_launch_plan(
        ll_rw_req,
        binary_path=str(binary),
        step_dir=tmp_path / "ll_rw/state/steps" / ll_rw_req.request_id,
        ownership=ProcessOwnership(ll_rw_req.process_owner, "pgroup_best_effort", "claude_code/ll_rw"),
        host_environ=host_env,
    )
    ll_argv = ll_rw_plan.command.argv
    assert ll_argv[:7] == (
        sys.executable,
        "-P",
        "-m",
        "skm.adapters.sandbox.landlock_exec",
        "--no-default-rw",
        "--min-abi",
        "3",
    )
    sep = ll_argv.index("--")
    rw_grants = [ll_argv[i + 1] for i in range(sep) if ll_argv[i] == "--rw"]
    assert str(Path(ll_rw_req.workdir).resolve()) in rw_grants
    assert ll_argv[sep + 1 :] == ll_rw_plan.claude_argv

    # Read-only Landlock step does NOT grant --rw on workdir.
    ll_ro_req = _make_request(tmp_path / "ll_ro", writable=False, isolation_profile=IsolationProfile.LANDLOCK)
    ll_ro_plan = build_launch_plan(
        ll_ro_req,
        binary_path=str(binary),
        step_dir=tmp_path / "ll_ro/state/steps" / ll_ro_req.request_id,
        ownership=ProcessOwnership(ll_ro_req.process_owner, "pgroup_best_effort", "claude_code/ll_ro"),
        host_environ=host_env,
    )
    ro_sep = ll_ro_plan.command.argv.index("--")
    ro_grants = [
        ll_ro_plan.command.argv[i + 1] for i in range(ro_sep) if ll_ro_plan.command.argv[i] == "--rw"
    ]
    assert str(Path(ll_ro_req.workdir).resolve()) not in ro_grants

    # self_loaded_context: before probe -> skills reported; after --safe-mode probe -> empty tuple.
    runtime = ClaudeCodeRuntime(
        state_dir=tmp_path / "rt_state",
        binary=str(binary),
        environ=host_env,
        probe_runner=lambda argv, **_: CommandOutput(
            0, "2.1.266\n" if argv[-1] == "--version" else ALL_SUPPORTED_HELP_TEXT, ""
        ),
    )
    unprobed_loads = runtime.self_loaded_context(std_req)
    assert len(unprobed_loads) == 1
    assert unprobed_loads[0].files == (".claude/skills/**", ".claude/agents/**")
    runtime.detect(DetectProbe(host_id=HostId(uuid4()), binary=None, env_allowlist=(), timeout_seconds=5))
    assert runtime.self_loaded_context(std_req) == ()
    assert len(runtime.self_loaded_context(tfa_req)) == 1

    # Canonical launch_config_digest is stable and changes when static launch options change.
    d1 = compute_launch_config_digest(
        adapter_version="0.1.0", allow_skip_permissions=False, copy_credentials=True
    )
    d2 = compute_launch_config_digest(
        adapter_version="0.1.0", allow_skip_permissions=True, copy_credentials=True
    )
    assert d1.startswith("sha256:")
    assert d1 != d2


# ---------------------------------------------------------------------------
# 4. Stream-JSON Parsing, Token Usage, Subagents & Error Classification
# ---------------------------------------------------------------------------


def test_claude_code_stream_parser_and_usage_normalization_invariants() -> None:
    # Invalid cache counters remain unavailable.
    counts = normalize_usage_counts(
        {
            "input_tokens": -5,
            "output_tokens": True,
            "cache_read_input_tokens": 3.14,
            "cache_creation_input_tokens": "99",
        }
    )
    assert (
        counts.input_tokens,
        counts.output_tokens,
        counts.cache_read_tokens,
        counts.cache_write_tokens,
    ) == (
        0,
        0,
        None,
        None,
    )

    # Standalone parser redacts secrets in args_preview, drops malformed lines, suppresses thinking.
    secret = "skm-secret-in-tool-args-12345"
    redactor = Redactor()
    redactor.register_secret(secret)
    parser = ClaudeStreamParser(runtime_version="2.1.266", redact=redactor.text)

    assert tuple(parser.feed(b"not-valid-json\n")) == ()
    assert tuple(parser.feed(b"[1, 2, 3]\n")) == ()
    assert parser.is_terminal(b"not-json") is False

    basic_lines = (FIXTURES_DIR / "stream_basic.jsonl").read_bytes().splitlines()
    emitted = [ev for line in basic_lines for ev in parser.feed(line)]
    assert any(isinstance(ev, SessionStarted) for ev in emitted)
    deltas = [ev for ev in emitted if isinstance(ev, TextDelta)]
    assert [d.text for d in deltas] == ["Implemented requested module."]
    assert parser.is_terminal(basic_lines[-1]) is True
    assert parser.saw_terminal() is True
    outcome = parser.finish(0)
    assert outcome.final_text == "Implemented requested module."
    assert outcome.usage.status is UsageStatus.REPORTED
    assert outcome.usage.input_tokens == 320
    assert outcome.usage.output_tokens == 45
    assert outcome.usage.cache_read_tokens == 1200
    assert outcome.usage.cache_write_tokens == 150
    assert outcome.usage.cost_usd_micros is None
    assert outcome.usage.subagents == SubagentUsage(used=False, disclosed=False)

    # Catalog pricing computes cost_usd_micros with ROUND_CEILING.
    pricing = Pricing(
        input_per_mtok_usd=Decimal("3.00"),
        output_per_mtok_usd=Decimal("15.00"),
        cache_read_per_mtok_usd=Decimal("0.30"),
        cache_write_per_mtok_usd=Decimal("3.75"),
        currency="USD",
        verified_at=date(2026, 10, 26),
        source="https://docs.anthropic.com/pricing",
    )
    assert cost(outcome.usage, pricing) == 2558

    # Tool arguments preview is canonical JSON, redacted, <= 500 chars; denial_hint never leaks raw input.
    tool_line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "id": "m1",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "Bash",
                        "input": {"z": "pad" * 250, "a": f"Authorization: {secret}"},
                    }
                ],
            },
        }
    ).encode("utf-8")
    tool_events = list(parser.feed(tool_line))
    assert len(tool_events) == 1
    req_ev = tool_events[0]
    assert isinstance(req_ev, ToolRequested)
    assert len(req_ev.args_preview) <= 500
    assert secret not in req_ev.args_preview
    assert MASK in req_ev.args_preview
    assert req_ev.args_preview.startswith('{"a":')  # sort_keys=True

    hint = denial_hint("Bash", {"command": f"curl -H 'Bearer {secret}' https://example.invalid"})
    assert secret not in hint
    assert "curl" in hint


def test_claude_code_stream_fixtures_tools_denials_multi_result_subagent_and_crash() -> None:
    # 1. Tools ok + error
    p_tools = ClaudeStreamParser()
    t_events = [
        ev
        for line in (FIXTURES_DIR / "stream_tools.jsonl").read_bytes().splitlines()
        for ev in p_tools.feed(line)
    ]
    completed = [ev for ev in t_events if isinstance(ev, ToolCompleted)]
    assert [(c.call_id, c.status, c.duration_ms) for c in completed] == [
        ("toolu_01read", ToolCallStatus.OK, 12),
        ("toolu_02bash", ToolCallStatus.ERROR, 145),
    ]
    assert p_tools.finish(0).tools.observed_calls == 2

    # 2. Permission denied -> ToolCompleted(denied) + secret-free ToolDenial
    p_den = ClaudeStreamParser()
    d_events = [
        ev
        for line in (FIXTURES_DIR / "stream_permission_denied.jsonl").read_bytes().splitlines()
        for ev in p_den.feed(line)
    ]
    d_comp = [ev for ev in d_events if isinstance(ev, ToolCompleted)]
    assert [(c.call_id, c.status) for c in d_comp] == [("toolu_01write", ToolCallStatus.DENIED)]
    d_out = p_den.finish(0)
    assert len(d_out.denials) == 1
    assert d_out.denials[0].tool == "Write"
    assert "raw-argument-payload-not-for-hints" not in d_out.denials[0].hint

    # 3. Multiple result records concatenate with \n\n and accumulate usage.
    p_multi = ClaudeStreamParser()
    for line in (FIXTURES_DIR / "stream_multi_result.jsonl").read_bytes().splitlines():
        list(p_multi.feed(line))
    m_out = p_multi.finish(0)
    assert m_out.final_text == "First segment.\n\nSecond segment."
    assert (
        m_out.usage.input_tokens,
        m_out.usage.output_tokens,
        m_out.usage.cache_read_tokens,
        m_out.usage.cache_write_tokens,
    ) == (250, 50, 130, 15)

    # 4. Native subagent Task invocation sets SubagentUsage(used=True, disclosed=False).
    p_sub = ClaudeStreamParser()
    for line in (FIXTURES_DIR / "stream_subagent_task.jsonl").read_bytes().splitlines():
        list(p_sub.feed(line))
    s_out = p_sub.finish(0)
    assert s_out.usage.subagents == SubagentUsage(used=True, disclosed=False)

    # 5. Partial crash sums unique message.id usages (componentwise max within msg_turn_1 + msg_turn_2).
    p_crash = ClaudeStreamParser()
    for line in (FIXTURES_DIR / "stream_partial_crash.jsonl").read_bytes().splitlines():
        list(p_crash.feed(line))
    assert p_crash.saw_terminal() is False
    c_out = p_crash.finish(1)
    assert c_out.usage.status is UsageStatus.ESTIMATED
    assert c_out.usage.source == "stream:delta"
    assert c_out.usage.input_tokens == 310  # 110 + 200
    assert c_out.usage.output_tokens == 65  # max(15, 40) + 25
    assert c_out.usage.cache_read_tokens == 120  # 20 + 100
    assert c_out.usage.cache_write_tokens == 5  # 5 + 0

    # Empty accumulator yields unknown_usage().
    assert UsageAccumulator().final_usage().status is UsageStatus.UNKNOWN


def test_claude_code_error_rules_classify_401_403_429_529_and_network_timeouts() -> None:
    runtime = ClaudeCodeRuntime()
    rules = runtime._error_rules
    now_unix = 1_790_000_000

    # 429 fixture with api_retry + rate_limit_event resetsAt -> RATE_LIMITED + retry_after_seconds.
    p_429 = ClaudeStreamParser()
    for line in (FIXTURES_DIR / "stream_api_retry_429.jsonl").read_bytes().splitlines():
        list(p_429.feed(line))
    out_429 = p_429.finish(1)
    assert out_429.signals.api_retries == 2
    f_429 = classify("claude_code", out_429.signals, rules, now_unix=now_unix)
    assert f_429.code is ErrorCode.RATE_LIMITED
    assert f_429.error_class is ErrorClass.RATE_LIMIT
    assert f_429.retryable is True
    assert f_429.retry_after_seconds == 7200

    # 401 fixture -> RUNTIME_AUTH_EXPIRED (retryable=False), and an earlier allowed rate_limit_event
    # never attaches retry_after_seconds to non-rate-limit errors!
    p_401 = ClaudeStreamParser()
    list(
        p_401.feed(
            b'{"type":"rate_limit_event","rate_limit_info":{"status":"allowed","resetsAt":1790009999}}\n'
        )
    )
    for line in (FIXTURES_DIR / "stream_auth_401.jsonl").read_bytes().splitlines():
        list(p_401.feed(line))
    f_401 = classify("claude_code", p_401.finish(1).signals, rules, now_unix=now_unix)
    assert f_401.code is ErrorCode.RUNTIME_AUTH_EXPIRED
    assert f_401.retryable is False
    assert f_401.retry_after_seconds is None

    # 403 -> RUNTIME_FORBIDDEN
    f_403 = classify("claude_code", RuntimeSignals(http_status=403, exit_code=1), rules, now_unix=now_unix)
    assert f_403.code is ErrorCode.RUNTIME_FORBIDDEN
    assert f_403.retryable is False

    # 529 fixture -> RUNTIME_OVERLOADED (retryable=True)
    p_529 = ClaudeStreamParser()
    for line in (FIXTURES_DIR / "stream_overload_529.jsonl").read_bytes().splitlines():
        list(p_529.feed(line))
    f_529 = classify("claude_code", p_529.finish(1).signals, rules, now_unix=now_unix)
    assert f_529.code is ErrorCode.RUNTIME_OVERLOADED
    assert f_529.retryable is True

    # Connect error -> RUNTIME_TIMEOUT
    f_conn = classify(
        "claude_code",
        RuntimeSignals(stderr_tail="TypeError: fetch failed: ECONNREFUSED", exit_code=1),
        rules,
        now_unix=now_unix,
    )
    assert f_conn.code is ErrorCode.RUNTIME_TIMEOUT
    assert f_conn.retryable is True


# ---------------------------------------------------------------------------
# 5. End-to-End Subprocess Execution via Synthetic Mock CLI Script
# ---------------------------------------------------------------------------


def _build_mock_claude_script(tmp_path: Path) -> Path:
    script = tmp_path / "bin" / "mock-claude"
    code = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import json, os, signal, sys, time
        from pathlib import Path

        argv = sys.argv[1:]
        if "--version" in argv:
            sys.stdout.write("2.1.266 (Claude Code)\\n")
            sys.exit(0)
        if "--help" in argv:
            sys.stdout.write({ALL_SUPPORTED_HELP_TEXT!r} + "\\n")
            sys.exit(0)

        mode = os.environ.get("MOCK_CLAUDE_MODE", "basic")
        prompt = sys.stdin.read()

        # Verify K16: if --setting-sources contains project/local, touch canary to catch regressions!
        idx = argv.index("--setting-sources")
        sources = argv[idx + 1].split(",")
        if "project" in sources or "local" in sources:
            canary = Path.cwd() / ".claude" / "canary_triggered"
            canary.parent.mkdir(parents=True, exist_ok=True)
            canary.write_text("leaked", encoding="utf-8")

        if mode == "hang_ignore_int":
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            init_rec = {{
                "type": "system",
                "subtype": "init",
                "session_id": "s_hang",
                "model": "claude-sonnet-4-5",
            }}
            sys.stdout.write(json.dumps(init_rec) + "\\n")
            sys.stdout.flush()
            time.sleep(30.0)
            sys.exit(0)

        if mode == "fixture":
            fixture_path = Path(os.environ["MOCK_FIXTURE_PATH"])
            sys.stdout.buffer.write(fixture_path.read_bytes())
            sys.stdout.buffer.flush()
            sys.exit(int(os.environ.get("MOCK_EXIT_CODE", "0")))

        # Default "basic": echo inspected isolation facts + leaked secret test into stream-json.
        tok = os.environ.get("SKM_TOKEN", "")
        sys.stderr.write(f"debug stderr token={{tok}}\\n")
        sys.stderr.flush()
        payload_summary = json.dumps({{
            "prompt": prompt,
            "home": os.environ.get("HOME"),
            "config_dir": os.environ.get("CLAUDE_CONFIG_DIR"),
            "disable_mds": os.environ.get("CLAUDE_CODE_DISABLE_CLAUDE_MDS"),
            "disable_mem": os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY"),
            "resumed": argv[argv.index("--resume") + 1] if "--resume" in argv else None,
        }}, sort_keys=True)
        usage_obj = {{
            "input_tokens": 55,
            "output_tokens": 21,
            "cache_read_input_tokens": 10,
            "cache_creation_input_tokens": 4,
        }}
        records = [
            {{
                "type": "system",
                "subtype": "init",
                "session_id": "sess_e2e_1",
                "model": "claude-sonnet-4-5-20250929",
                "claude_code_version": "2.1.266",
            }},
            {{
                "type": "assistant",
                "message": {{
                    "id": "m_e2e_1",
                    "model": "claude-sonnet-4-5-20250929",
                    "content": [{{"type": "text", "text": payload_summary}}],
                    "usage": usage_obj,
                }},
            }},
            {{
                "type": "result",
                "subtype": "success",
                "session_id": "sess_e2e_1",
                "is_error": False,
                "stop_reason": "end_turn",
                "result": payload_summary,
                "usage": usage_obj,
            }},
        ]
        for rec in records:
            sys.stdout.write(json.dumps(rec) + "\\n")
        sys.stdout.flush()
        """
    )
    return _write_executable(script, code)


@pytest.mark.parametrize(
    ("fixture_name", "exit_code", "expected_outcome", "expected_code"),
    [
        ("stream_basic.jsonl", 0, "completed", None),
        ("stream_tools.jsonl", 0, "completed", None),
        ("stream_permission_denied.jsonl", 0, "completed", None),
        ("stream_multi_result.jsonl", 0, "completed", None),
        ("stream_subagent_task.jsonl", 0, "completed", None),
        ("stream_resume.jsonl", 0, "completed", None),
        ("stream_exit0_no_result.jsonl", 0, "failed", ErrorCode.RUNTIME_STREAM_INCOMPLETE),
        ("stream_partial_crash.jsonl", 1, "failed", ErrorCode.RUNTIME_CRASHED),
        ("stream_api_retry_429.jsonl", 1, "failed", ErrorCode.RATE_LIMITED),
        ("stream_auth_401.jsonl", 1, "failed", ErrorCode.RUNTIME_AUTH_EXPIRED),
        ("stream_overload_529.jsonl", 1, "failed", ErrorCode.RUNTIME_OVERLOADED),
    ],
)
def test_claude_code_contract_replay_all_fixtures_end_to_end(
    tmp_path: Path,
    fixture_name: str,
    exit_code: int,
    expected_outcome: str,
    expected_code: ErrorCode | None,
) -> None:
    """Replay all 11 fixtures through ClaudeCodeRuntime + CliSession + SchemaRegistry."""
    mock_bin = _build_mock_claude_script(tmp_path)
    user_home = _make_user_home(tmp_path, with_credentials=True)
    schemas = SchemaRegistry.load_default()

    runtime = ClaudeCodeRuntime(
        state_dir=tmp_path / "state",
        binary=str(mock_bin),
        environ={"PATH": "/usr/bin:/bin", "HOME": str(user_home)},
        poll_interval_seconds=0.02,
    )
    req = _make_request(
        tmp_path / "case",
        extra_env={
            "MOCK_CLAUDE_MODE": "fixture",
            "MOCK_FIXTURE_PATH": str(FIXTURES_DIR / fixture_name),
            "MOCK_EXIT_CODE": str(exit_code),
        },
    )
    handle = runtime.start(req)
    events = list(runtime.events(handle))
    result = runtime.result(handle)
    assert runtime.result(handle) is result

    assert validate_event_stream(events) == ()
    for ev in events:
        assert schemas.validate("urn:skm:runtimes:session-event:v1", session_event_to_json(ev)) == ()
    assert schemas.validate("urn:skm:runtimes:runtime-result:v1", result_to_json(result)) == ()
    assert validate_result_observation(result, request_id=UUID(req.request_id)) == ()

    # K4 guarantee: UsageReported(cumulative=True) always immediately precedes terminal event.
    assert isinstance(events[-2], UsageReported)
    assert events[-2].cumulative is True
    assert isinstance(events[-1], SessionCompleted if expected_outcome == "completed" else SessionFailed)

    assert result.outcome == expected_outcome
    assert (None if result.failure is None else result.failure.code) == expected_code

    if fixture_name == "stream_basic.jsonl":
        assert runtime.auth_state is AuthState.OK
        assert result.transcript_path is not None
        assert "Internal chain of thought" in Path(result.transcript_path).read_text(encoding="utf-8")
    elif fixture_name == "stream_auth_401.jsonl":
        assert runtime.auth_state is AuthState.EXPIRED
    elif fixture_name == "stream_partial_crash.jsonl":
        assert result.usage.status is UsageStatus.ESTIMATED
        assert result.usage.input_tokens == 310


def test_claude_code_e2e_stdin_secret_redaction_resume_and_cancellation(tmp_path: Path) -> None:
    mock_bin = _build_mock_claude_script(tmp_path)
    user_home = _make_user_home(tmp_path, with_credentials=True)
    secret_tok = "skm-e2e-confidential-token-5555"

    runtime = ClaudeCodeRuntime(
        state_dir=tmp_path / "state",
        binary=str(mock_bin),
        environ={"PATH": "/usr/bin:/bin", "HOME": str(user_home)},
        poll_interval_seconds=0.02,
    )
    assert runtime.auth_state is AuthState.UNKNOWN

    req = _make_request(
        tmp_path / "e2e",
        prompt="Verify isolated launch over stdin.",
        session_policy="persistent",
        resume_session_ref="sess_prior_99",
        secret_token=secret_tok,
    )
    # Plant worktree .claude/settings.json canary; K16 must prevent --setting-sources project/local.
    wt_claude = Path(req.workdir) / ".claude"
    wt_claude.mkdir(parents=True, exist_ok=True)
    (wt_claude / "settings.json").write_text('{"hooks":{}}', encoding="utf-8")

    handle = runtime.start(req)
    assert handle.pid is not None
    assert handle.pid > 0
    events = list(runtime.events(handle))
    res = runtime.result(handle)

    assert validate_event_stream(events) == ()
    assert res.outcome == "completed"
    assert runtime.auth_state is AuthState.OK
    assert not (wt_claude / "canary_triggered").exists()

    summary = json.loads(res.final_text)
    assert summary["prompt"] == "Verify isolated launch over stdin."
    assert summary["home"] == req.client_home
    assert summary["config_dir"] == req.client_home
    assert summary["disable_mds"] == "1"
    assert summary["disable_mem"] == "1"
    assert summary["resumed"] == "sess_prior_99"

    # Secret written to stderr by child must be masked in stream.stderr!
    assert res.stderr_path is not None
    stderr_disk = Path(res.stderr_path).read_text(encoding="utf-8")
    assert secret_tok not in stderr_disk
    assert MASK in stderr_disk

    # Cancellation: hanging child that ignores SIGINT escalates cleanly and removes identity marker.
    fast_clock = FakeMonotonic()

    class FastSleeper:
        def sleep(self, seconds: float) -> None:
            fast_clock.advance(seconds)
            time_sleep = min(seconds, 0.01)
            if time_sleep > 0:
                import time as _t

                _t.sleep(time_sleep)

    cancel_rt = ClaudeCodeRuntime(
        state_dir=tmp_path / "cancel_state",
        binary=str(mock_bin),
        environ={"PATH": "/usr/bin:/bin", "HOME": str(user_home)},
        clock=FrozenClock(),
        monotonic=fast_clock,
        sleeper=FastSleeper(),
        poll_interval_seconds=0.02,
    )
    hang_req = _make_request(
        tmp_path / "hang",
        extra_env={"MOCK_CLAUDE_MODE": "hang_ignore_int"},
    )
    hang_req = replace(
        hang_req,
        process_owner=replace(hang_req.process_owner, identity_dir=str(tmp_path / "cancel_state/identities")),
    )
    hang_handle = cancel_rt.start(hang_req)
    event_iter = cancel_rt.events(hang_handle)
    first_event = next(event_iter)
    assert isinstance(first_event, SessionStarted)
    cancel_res = cancel_rt.cancel(hang_handle, grace_seconds=0.1)
    hang_events = [first_event, *event_iter]
    hang_final = cancel_rt.result(hang_handle)

    assert cancel_res.stopped is True
    assert cancel_res.signal_used in ("SIGTERM", "SIGKILL")
    assert any(isinstance(ev, CancelIgnored) for ev in hang_events)
    assert validate_event_stream(hang_events) == ()
    assert hang_final.outcome == "cancelled"
    assert not list((tmp_path / "cancel_state/identities").glob("*.json"))


def test_claude_code_rejects_missing_workdir_and_symlink_client_home(tmp_path: Path) -> None:
    mock_bin = _build_mock_claude_script(tmp_path)
    user_home = _make_user_home(tmp_path, with_credentials=True)
    runtime = ClaudeCodeRuntime(
        state_dir=tmp_path / "state",
        binary=str(mock_bin),
        environ={"PATH": "/usr/bin:/bin", "HOME": str(user_home)},
    )

    missing_req = _make_request(tmp_path / "missing")
    os.rmdir(missing_req.workdir)
    with pytest.raises(ValidationFailed) as exc_info:
        runtime.start(missing_req)
    assert exc_info.value.code is ErrorCode.RUNTIME_INVALID_REQUEST

    real_target = tmp_path / "real-target"
    real_target.mkdir()
    sym_home = tmp_path / "sym-home"
    sym_home.symlink_to(real_target)
    sym_req = _make_request(tmp_path / "sym", client_home=sym_home)
    with pytest.raises(ValidationFailed) as sym_err:
        runtime.start(sym_req)
    assert sym_err.value.code is ErrorCode.RUNTIME_INVALID_REQUEST
