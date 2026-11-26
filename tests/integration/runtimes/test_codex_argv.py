"""Offline unit, integration, and mock-CLI replay tests for Codex runtime adapter."""

from __future__ import annotations

import json
import os
import sys
import textwrap
from dataclasses import replace
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import pytest

from fakes.clock import FakeMonotonic, FrozenClock
from skm.adapters.runtimes._cli_session.binding import launch_verification_digest
from skm.adapters.runtimes._cli_session.probe import (
    CommandOutput,
)
from skm.adapters.runtimes.codex.detect import (
    REQUIRED_FLAGS,
    CodexDetector,
    parse_login_status_output,
    parse_version_output,
)
from skm.adapters.runtimes.codex.launch import (
    CREDENTIAL_FILENAME,
    WRITABLE_CLIENT_HOME_DIRS,
    build_launch_plan,
    compute_launch_config_digest,
)
from skm.adapters.runtimes.codex.permissions import (
    can_bypass_approvals_and_sandbox,
    denial_hint,
    resolve_sandbox_mode,
)
from skm.adapters.runtimes.codex.runtime import CodexRuntime
from skm.adapters.runtimes.codex.stream_parser import CodexStreamParser
from skm.adapters.runtimes.codex.usage import UsageAccumulator, normalize_usage_counts
from skm.bootstrap.builtins import BUILTIN_COMPONENTS, component_problem
from skm.bootstrap.runtimes import RUNTIME_FACTORIES
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.ids import HostId
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    SelfLoadKind,
    StaticCapabilityCatalog,
    VerificationContext,
    effective_capabilities,
    explain_self_loads,
    parse_capabilities,
    self_loaded_instruction_files,
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
from skm.platform.logging.redaction import MASK
from skm.platform.schema.registry import SchemaRegistry
from skm.plugin_api.manifest import ComponentKind

ROOT = Path(__file__).resolve().parents[3]
ADAPTER_DIR = ROOT / "src/skm/adapters/runtimes/codex"
FIXTURES_DIR = ROOT / "tests/fixtures/runtimes/codex"
EXAMPLES_DIR = ROOT / "tests/fixtures/corpus/examples/adapters/runtimes/codex"

ALL_SUPPORTED_ROOT_HELP = """
Usage: codex [OPTIONS] [COMMAND]

Commands:
  exec    Run Codex non-interactively
  resume  Resume a previous session
  login   Manage authentication

Options:
  -a, --ask-for-approval <APPROVAL_POLICY>
  -c, --config <key=value>
  -C, --cd <DIR>
  -m, --model <MODEL>
  -s, --sandbox <SANDBOX_MODE>
"""

ALL_SUPPORTED_EXEC_HELP = """
Usage: codex exec [OPTIONS] [PROMPT] [COMMAND]

Commands:
  resume  Resume a previous session by id

Options:
  --json
  -s, --sandbox <SANDBOX_MODE>
  -m, --model <MODEL>
  -c, --config <key=value>
  --ephemeral
  --dangerously-bypass-approvals-and-sandbox
"""


def _write_executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    os.chmod(path, 0o700)
    return path


def _make_stub_binary(tmp_path: Path, name: str = "codex", marker: str = "v1") -> Path:
    return _write_executable(
        tmp_path / "bin" / name,
        f"#!/bin/sh\n# stub binary {marker}\necho 'codex-cli 0.165.0'\n",
    )


def _make_user_home(tmp_path: Path, *, with_credentials: bool = True) -> Path:
    user_home = tmp_path / "user_home"
    codex_dir = user_home / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    if with_credentials:
        cred = codex_dir / CREDENTIAL_FILENAME
        cred.write_text(
            '{"OPENAI_API_KEY":"sk-live-oauth-token","tokens":{"access_token":"tok"}}\n',
            encoding="utf-8",
        )
        os.chmod(cred, 0o600)
    return user_home


def _make_request(
    tmp_path: Path,
    *,
    role: RoleId = RoleId.EXECUTOR,
    model: str = "gpt-5.3-codex",
    effort: Effort | None = Effort.HIGH,
    writable: bool = True,
    wildcard_write: bool = False,
    command_mode: Literal["none", "allowlist", "denylist", "any"] = "any",
    programs: tuple[str, ...] = (),
    network_mode: Literal["none", "allowlist", "any"] = "none",
    network_hosts: tuple[str, ...] = (),
    tools: frozenset[str] = frozenset({"Read", "Edit", "Write", "Bash"}),
    session_policy: Literal["ephemeral", "persistent"] = "persistent",
    resume_session_ref: str | None = None,
    config_mode: Literal["isolated", "inherit"] = "isolated",
    client_home: Path | None = None,
    isolation_profile: IsolationProfile = IsolationProfile.WORKTREE,
    mcp_servers: tuple[McpServerSpec, ...] = (),
    secret_token: str | None = None,
    extra_env: dict[str, str] | None = None,
    labels: dict[str, str] | None = None,
    prompt: str = "Fix failing unit test in service.py",
    timeout_seconds: int = 60,
) -> AgentRequest:
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    step_id = uuid4()
    run_id = uuid4()
    read_rules = PathRules((PathRule(str(workdir), "**"),), ())
    if wildcard_write:
        write_rules = PathRules((PathRule("*", "**"),), ())
    elif writable:
        write_rules = PathRules((PathRule(str(workdir), "**"),), ())
    else:
        write_rules = PathRules((), ())

    owner = ProcessOwner(
        host_id=run_id,
        worker_id=run_id,
        attempt_id=run_id,
        stage_record_id=run_id,
        unit_kind="step",
        unit_id=step_id,
        owner_nonce="synthetic-codex-nonce-0001",
        identity_dir=str(state_dir / "identities"),
    )
    resolved_home = (
        None
        if config_mode == "inherit"
        else str(client_home or (state_dir / "client-homes" / str(run_id) / "codex"))
    )
    secrets = {"SKM_TOKEN": SecretStr(secret_token)} if secret_token is not None else {}
    merged_labels = {"run_id": str(run_id), "step_id": str(step_id), **(labels or {})}

    return AgentRequest(
        request_id=str(step_id),
        runtime_id="codex",
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
            commands=CommandRules(command_mode, programs, (), ()),
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
        env_allowlist=("PATH", "HOME", "LANG", "TERM"),
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
# 1. Static TOML Schema Validation & Built-in Catalog Registration
# ---------------------------------------------------------------------------


def test_codex_static_capabilities_and_error_rules_validate_against_schemas() -> None:
    schemas = SchemaRegistry.load_default()
    caps_raw = decode_document((ADAPTER_DIR / "capabilities.toml").read_text(encoding="utf-8"), "toml")
    rules_raw = decode_document((ADAPTER_DIR / "error_rules.toml").read_text(encoding="utf-8"), "toml")

    assert schemas.validate("urn:skm:runtimes:capabilities:v1", caps_raw) == ()
    assert schemas.validate("urn:skm:runtimes:error-rules:v1", rules_raw) == ()

    caps = parse_capabilities(caps_raw)
    assert caps.runtime_id == "codex"
    assert caps.adapter_version == "0.1.0"
    assert caps.read_only_network is False
    assert set(caps.records) == set(Capability)
    assert caps.status(Capability.TOOL_INTERCEPTION) is CapabilityStatus.UNSUPPORTED
    assert caps.status(Capability.NATIVE_SUBAGENTS) is CapabilityStatus.UNKNOWN
    assert caps.config_isolation is not None
    assert caps.config_isolation.writable_home_dirs == ("sessions", "cache", "tmp")
    assert caps.config_isolation.env["CODEX_HOME"] == "{client_home}"
    assert caps.config_isolation.env["HOME"] == "{client_home}"
    assert len(caps.config_isolation.credential_mounts) == 1
    assert caps.config_isolation.credential_mounts[0].source == "~/.codex/auth.json"
    assert caps.config_isolation.credential_mounts[0].target == "auth.json"

    rules = parse_error_rules(rules_raw)
    assert len(rules) >= 9
    assert all(r.runtime_id == "codex" for r in rules)

    catalog = StaticCapabilityCatalog(
        declarations={"codex": caps},
        rules={"codex": rules},
    )
    assert "codex" in catalog.registered()
    assert catalog.static("codex").runtime_id == "codex"
    assert len(catalog.error_rules("codex")) == len(rules)


def test_codex_self_loads_and_self_loaded_context(tmp_path: Path) -> None:
    runtime = CodexRuntime()
    static_caps = runtime.capabilities()

    v_ctx = VerificationContext(
        host_id=HostId(uuid4()),
        binary_sha256="sha256:" + "a" * 64,
        os="Linux",
        kernel="6.8.0",
        adapter_version=static_caps.adapter_version,
        isolation_profile=IsolationProfile.WORKTREE,
        launch_config_digest=runtime.launch_config_digest,
    )
    verified = (
        CapabilityRecord(
            capability=Capability.CONFIG_ISOLATION,
            status=CapabilityStatus.ADAPTED,
            evidence="test:codex_isolation",
            tested_runtime_version="0.165.0",
            limitations="",
            last_verified_at=date(2026, 10, 26),
            verification_context=v_ctx,
        ),
    )
    eff_caps = effective_capabilities(
        static_caps,
        verified,
        host_version="0.165.0",
        verification_context=v_ctx,
        now=date(2026, 10, 27),
    )
    views = explain_self_loads(eff_caps, "isolated")
    by_kind = {v.kind: v for v in views}
    assert by_kind[SelfLoadKind.USER_CONFIG].active is False
    assert by_kind[SelfLoadKind.PLUGINS].active is False
    assert by_kind[SelfLoadKind.SKILLS].active is False
    assert by_kind[SelfLoadKind.PROJECT_SETTINGS].active is False
    assert by_kind[SelfLoadKind.PROJECT_SETTINGS].reason == "untrusted_suppressed"
    # AGENTS.md has suppressed_by = "never" and remains active even in isolated mode!
    assert by_kind[SelfLoadKind.PROJECT_INSTRUCTIONS].active is True
    assert by_kind[SelfLoadKind.PROJECT_INSTRUCTIONS].reason == "cannot_suppress"
    assert self_loaded_instruction_files(views, eff_caps) == ("AGENTS.md",)

    req = _make_request(tmp_path)
    self_loaded = runtime.self_loaded_context(req)
    assert len(self_loaded) == 1
    assert self_loaded[0].kind is SelfLoadKind.PROJECT_INSTRUCTIONS
    assert self_loaded[0].files == ("AGENTS.md",)
    assert self_loaded[0].when == "start"
    assert self_loaded[0].trust == "untrusted"


# ---------------------------------------------------------------------------
# 2. Bootstrap Factory Protocol
# ---------------------------------------------------------------------------


def test_verified_template_normalizes_only_the_worker_bound_stage_socket(tmp_path: Path) -> None:
    binary = _write_executable(tmp_path / "codex", f"#!{sys.executable}\n")
    user_home = _make_user_home(tmp_path)
    request = _make_request(tmp_path)
    command = (sys.executable, "-m", "skm.entrypoints.cli.main", "mcp")

    def digest(
        socket_path: str,
        *,
        bound: bool,
        server_command: tuple[str, ...] = command,
        server_socket: str | None = None,
    ) -> str:
        env = {"SKM_STAGE_SOCKET": socket_path}
        launch_request = replace(
            request,
            stage_tool_socket=socket_path if bound else None,
            extra_env=env,
            mcp_servers=(
                McpServerSpec("skm", server_command, {"SKM_STAGE_SOCKET": server_socket or socket_path}, ()),
            ),
        )
        plan = build_launch_plan(
            launch_request,
            binary_path=str(binary),
            step_dir=tmp_path / "step",
            ownership=ProcessOwnership(request.process_owner, "pgroup_best_effort", "codex"),
            host_environ={},
            user_home=user_home,
        )
        config = plan.permissions.config_path.read_text()
        assert socket_path in config
        assert plan.command.env["SKM_STAGE_SOCKET"] == socket_path
        return launch_verification_digest(plan.command.as_wrapped(), str(binary))

    first, second = str(tmp_path / "stage-one.sock"), str(tmp_path / "stage-two.sock")
    fingerprint = digest(first, bound=True)
    assert fingerprint == digest(second, bound=True)
    assert digest(first, bound=False) != digest(second, bound=False)
    assert fingerprint != digest("{stage_tool_socket}", bound=False)
    assert fingerprint != digest(first, bound=True, server_command=(*command, "--json"))
    with pytest.raises(ValueError, match="MCP server differs"):
        digest(first, bound=True, server_socket="{stage_tool_socket}")


def test_codex_bootstrap_factories_produce_configured_runtime(tmp_path: Path) -> None:
    assert "codex" in RUNTIME_FACTORIES
    assert "codex-cli" in RUNTIME_FACTORIES

    spec = next(
        item for item in BUILTIN_COMPONENTS if item.kind is ComponentKind.RUNTIME and item.key == "codex"
    )
    for key in ("codex", "codex-cli"):
        built = RUNTIME_FACTORIES[key](environ={"PATH": "/usr/bin"})
        assert isinstance(built, CodexRuntime)
        assert built.runtime_id == "codex"
        assert component_problem(spec, built) is None

    dummy_ctx = SimpleNamespace(
        config={
            "runtimes.binaries": {"codex": "/custom/bin/codex"},
            "runtimes.credentials.copy": {"codex": False},
            "runtimes.codex": {"allow_full_access": True},
        }
    )

    rt_instance = RUNTIME_FACTORIES["codex"](
        dummy_ctx,
        state_dir=tmp_path / "state",
        environ={"PATH": "/usr/bin"},
    )
    assert isinstance(rt_instance, CodexRuntime)
    assert rt_instance.runtime_id == "codex"
    assert rt_instance._binary == "/custom/bin/codex"
    assert rt_instance._copy_credentials is False
    assert rt_instance._allow_full_access is True

    alias_instance = RUNTIME_FACTORIES["codex-cli"](environ={"PATH": "/usr/bin"})
    assert isinstance(alias_instance, CodexRuntime)


# ---------------------------------------------------------------------------
# 3. Detection, Login Probing & 6-Tuple Caching
# ---------------------------------------------------------------------------


def test_codex_detector_version_flags_login_status_and_6tuple_cache(tmp_path: Path) -> None:
    assert parse_version_output("codex-cli 0.165.0\n") == "0.165.0"
    assert parse_version_output("no version") is None

    assert parse_login_status_output(CommandOutput(0, "Logged in using ChatGPT\n", "")) is AuthState.OK
    assert parse_login_status_output(CommandOutput(1, "Not logged in\n", "")) is AuthState.MISSING
    assert (
        parse_login_status_output(CommandOutput(2, "", "error: unrecognized subcommand 'login'"))
        is AuthState.UNKNOWN
    )

    binary = _make_stub_binary(tmp_path, marker="v1")
    calls: list[tuple[str, ...]] = []

    def fake_runner(
        argv: tuple[str, ...],
        *,
        env: Any,
        timeout_seconds: float,
    ) -> CommandOutput:
        del env, timeout_seconds
        calls.append(argv)
        if "--version" in argv:
            return CommandOutput(0, "codex-cli 0.165.0\n", "")
        if argv[-2:] == ("exec", "--help"):
            return CommandOutput(0, ALL_SUPPORTED_EXEC_HELP, "")
        if "--help" in argv:
            return CommandOutput(0, ALL_SUPPORTED_ROOT_HELP, "")
        if argv[-2:] == ("login", "status"):
            return CommandOutput(0, "Logged in using ChatGPT Plus\n", "")
        return CommandOutput(1, "", "")

    detector = CodexDetector(run_cmd=fake_runner, os_kernel_fn=lambda: "Linux:6.8.0")
    digest_1 = compute_launch_config_digest(
        adapter_version="0.1.0",
        allow_full_access=False,
        copy_credentials=True,
    )
    env_map = {"PATH": str(binary.parent)}

    probed_1 = detector.probe(
        binary="codex",
        environ=env_map,
        env_allowlist=("PATH",),
        adapter_version="0.1.0",
        launch_config_digest=digest_1,
    )
    assert probed_1.version == "0.165.0"
    assert probed_1.missing_required_flags == ()
    assert probed_1.auth_state is AuthState.OK
    assert probed_1.bypass_supported is True
    for req_flag in REQUIRED_FLAGS:
        assert req_flag in probed_1.supported_flags
    assert len(calls) == 4  # --version, --help, exec --help, login status

    # Cached binary facts still require a new native login status observation.
    probed_cached = detector.probe(
        binary="codex",
        environ=env_map,
        env_allowlist=("PATH",),
        adapter_version="0.1.0",
        launch_config_digest=digest_1,
    )
    assert probed_cached == probed_1
    assert calls[4:] == [(str(binary.resolve()), "login", "status")]

    # Changing launch_config_digest invalidates the 6-tuple cache.
    digest_2 = compute_launch_config_digest(
        adapter_version="0.1.0",
        allow_full_access=True,
        copy_credentials=True,
    )
    probed_2 = detector.probe(
        binary="codex",
        environ=env_map,
        env_allowlist=("PATH",),
        adapter_version="0.1.0",
        launch_config_digest=digest_2,
    )
    assert probed_2.cache_key.launch_config_digest == digest_2
    assert len(calls) == 9

    # Mutating binary bytes changes binary_sha256 and invalidates cache.
    _make_stub_binary(tmp_path, marker="v2-mutated")
    probed_3 = detector.probe(
        binary="codex",
        environ=env_map,
        env_allowlist=("PATH",),
        adapter_version="0.1.0",
        launch_config_digest=digest_2,
    )
    assert probed_3.binary_sha256 != probed_2.binary_sha256
    assert len(calls) == 13


def test_codex_missing_required_flags_degrades_headless_execution(tmp_path: Path) -> None:
    binary = _make_stub_binary(tmp_path)

    def incomplete_runner(
        argv: tuple[str, ...],
        *,
        env: Any,
        timeout_seconds: float,
    ) -> CommandOutput:
        del env, timeout_seconds
        if "--version" in argv:
            return CommandOutput(0, "codex-cli 0.1.0\n", "")
        return CommandOutput(0, "Usage: codex --model <MODEL>\n", "")

    runtime = CodexRuntime(
        state_dir=tmp_path / "state",
        binary=str(binary),
        environ={"PATH": str(binary.parent)},
        probe_runner=incomplete_runner,
    )
    inst = runtime.detect(
        DetectProbe(
            host_id=HostId(uuid4()),
            binary=str(binary),
            env_allowlist=("PATH",),
            timeout_seconds=10,
        )
    )
    assert "missing_flags" in inst.details
    assert runtime.capabilities().status(Capability.HEADLESS_EXECUTION) is CapabilityStatus.UNSUPPORTED

    req = _make_request(tmp_path)
    with pytest.raises(CapabilityUnavailable) as exc_info:
        runtime.start(req)
    assert exc_info.value.code is ErrorCode.CAPABILITY_UNAVAILABLE


# ---------------------------------------------------------------------------
# 4. Launch Plan Rendering & Argv Invariants
# ---------------------------------------------------------------------------


def test_codex_argv_matches_normative_examples_json(tmp_path: Path) -> None:
    examples_doc = json.loads((EXAMPLES_DIR / "argv-examples.json").read_text(encoding="utf-8"))
    cases = {c["name"]: c for c in examples_doc["cases"]}
    user_home = _make_user_home(tmp_path, with_credentials=True)
    host_env = {"PATH": "/usr/bin:/bin", "HOME": str(user_home)}

    # 1. executor-workspace-write
    exec_req = _make_request(
        tmp_path / "exec",
        role=RoleId.EXECUTOR,
        model="gpt-5.5-codex",
        effort=Effort.HIGH,
        writable=True,
        session_policy="persistent",
    )
    exec_plan = build_launch_plan(
        exec_req,
        binary_path="codex",
        step_dir=tmp_path / "exec/state/steps" / exec_req.request_id,
        ownership=ProcessOwnership(exec_req.process_owner, "pgroup_best_effort", "codex/exec"),
        host_environ=host_env,
        wrap_landlock=False,
    )
    assert list(exec_plan.codex_argv) == cases["executor-workspace-write"]["argv"]

    # 2. executor-resume
    resume_req = _make_request(
        tmp_path / "resume",
        role=RoleId.EXECUTOR,
        model="gpt-5.5-codex",
        effort=Effort.HIGH,
        writable=True,
        session_policy="persistent",
        resume_session_ref="0199aa00-thread-7",
    )
    resume_plan = build_launch_plan(
        resume_req,
        binary_path="codex",
        step_dir=tmp_path / "resume/state/steps" / resume_req.request_id,
        ownership=ProcessOwnership(resume_req.process_owner, "pgroup_best_effort", "codex/resume"),
        host_environ=host_env,
        wrap_landlock=False,
    )
    assert list(resume_plan.codex_argv) == cases["executor-resume"]["argv"]

    # 3. reviewer-read-only
    rev_req = _make_request(
        tmp_path / "reviewer",
        role=RoleId.REVIEWER,
        model="gpt-5.5",
        effort=Effort.HIGH,
        writable=False,
        command_mode="none",
        tools=frozenset({"Read", "Grep", "Glob"}),
        session_policy="ephemeral",
    )
    rev_plan = build_launch_plan(
        rev_req,
        binary_path="codex",
        step_dir=tmp_path / "reviewer/state/steps" / rev_req.request_id,
        ownership=ProcessOwnership(rev_req.process_owner, "pgroup_best_effort", "codex/reviewer"),
        host_environ=host_env,
        wrap_landlock=False,
    )
    assert list(rev_plan.codex_argv) == cases["reviewer-read-only"]["argv"]

    # 4. trusted-full-access
    full_req = _make_request(
        tmp_path / "trusted",
        role=RoleId.EXECUTOR,
        model="gpt-5.5-codex",
        effort=Effort.MEDIUM,
        writable=True,
        wildcard_write=True,
        session_policy="persistent",
        isolation_profile=IsolationProfile.NONE,
    )
    full_plan = build_launch_plan(
        full_req,
        binary_path="codex",
        step_dir=tmp_path / "trusted/state/steps" / full_req.request_id,
        ownership=ProcessOwnership(full_req.process_owner, "pgroup_best_effort", "codex/trusted"),
        host_environ=host_env,
        allow_full_access=True,
        wrap_landlock=False,
    )
    assert list(full_plan.codex_argv) == cases["trusted-full-access"]["argv"]


def test_codex_sandbox_modes_read_only_network_refusal_and_bypass_guard(tmp_path: Path) -> None:
    user_home = _make_user_home(tmp_path, with_credentials=True)
    host_env = {"PATH": "/usr/bin:/bin", "HOME": str(user_home)}

    # Trusted full access with host opt-in -> danger-full-access
    full_req = _make_request(
        tmp_path / "full",
        writable=True,
        wildcard_write=True,
        isolation_profile=IsolationProfile.LANDLOCK,
        labels={"policy_profile": "trusted-full-access"},
    )
    assert resolve_sandbox_mode(full_req, allow_full_access=True) == "danger-full-access"
    assert resolve_sandbox_mode(full_req, allow_full_access=False) == "workspace-write"

    # Bypass flag only permitted when external containment + trusted-full-access + opt-in
    assert (
        can_bypass_approvals_and_sandbox(
            full_req,
            policy_profile="trusted-full-access",
            allow_full_access=True,
            request_bypass=True,
        )
        is True
    )
    no_iso_req = replace(full_req, isolation_profile=IsolationProfile.NONE)
    assert (
        can_bypass_approvals_and_sandbox(
            no_iso_req,
            policy_profile="trusted-full-access",
            allow_full_access=True,
            request_bypass=True,
        )
        is False
    )
    worktree_req = replace(full_req, isolation_profile=IsolationProfile.WORKTREE)
    assert (
        can_bypass_approvals_and_sandbox(
            worktree_req,
            policy_profile="trusted-full-access",
            allow_full_access=True,
            request_bypass=True,
        )
        is False
    )
    with pytest.raises(CapabilityUnavailable) as wt_bypass_err:
        build_launch_plan(
            worktree_req,
            binary_path="/usr/bin/codex",
            step_dir=tmp_path / "wt_bypass/state/steps" / worktree_req.request_id,
            ownership=ProcessOwnership(worktree_req.process_owner, "pgroup_best_effort", "codex/wt_bypass"),
            host_environ=host_env,
            allow_full_access=True,
            request_bypass=True,
        )
    assert wt_bypass_err.value.code is ErrorCode.CAPABILITY_UNAVAILABLE

    # Landlock with wrap_landlock=False -> rejected fail-closed with CAPABILITY_UNAVAILABLE
    with pytest.raises(CapabilityUnavailable) as ll_unwrap_err:
        build_launch_plan(
            full_req,
            binary_path="/usr/bin/codex",
            step_dir=tmp_path / "ll_unwrap/state/steps" / full_req.request_id,
            ownership=ProcessOwnership(full_req.process_owner, "pgroup_best_effort", "codex/ll_unwrap"),
            host_environ=host_env,
            allow_full_access=True,
            request_bypass=True,
            wrap_landlock=False,
        )
    assert ll_unwrap_err.value.code is ErrorCode.CAPABILITY_UNAVAILABLE

    # Container isolation profile -> permitted
    container_req = _make_request(
        tmp_path / "container_full",
        writable=True,
        wildcard_write=True,
        isolation_profile=IsolationProfile.CONTAINER,
        labels={"policy_profile": "trusted-full-access"},
    )
    assert (
        can_bypass_approvals_and_sandbox(
            container_req,
            policy_profile="trusted-full-access",
            allow_full_access=True,
            request_bypass=True,
        )
        is True
    )
    plan_container_bypass = build_launch_plan(
        container_req,
        binary_path="/usr/bin/codex",
        step_dir=tmp_path / "container_full/state/steps" / container_req.request_id,
        ownership=ProcessOwnership(
            container_req.process_owner,
            "container",
            "codex/container_full",
            daemon_identity="podman-daemon-1",
        ),
        host_environ=host_env,
        allow_full_access=True,
        request_bypass=True,
        wrap_landlock=False,
    )
    assert "--dangerously-bypass-approvals-and-sandbox" in plan_container_bypass.codex_argv

    assert (
        CodexRuntime(request_bypass=False).launch_config_digest
        != CodexRuntime(request_bypass=True).launch_config_digest
    )

    plan_bypass = build_launch_plan(
        full_req,
        binary_path="/usr/bin/codex",
        step_dir=tmp_path / "full/state/steps" / full_req.request_id,
        ownership=ProcessOwnership(full_req.process_owner, "pgroup_best_effort", "codex/full"),
        host_environ=host_env,
        allow_full_access=True,
        request_bypass=True,
        wrap_landlock=True,
    )
    assert "--dangerously-bypass-approvals-and-sandbox" in plan_bypass.codex_argv
    assert "skm.adapters.sandbox.landlock_exec" in plan_bypass.command.argv

    # Network in read-only sandbox -> refused fail-closed with CAPABILITY_UNAVAILABLE
    researcher_ro = _make_request(
        tmp_path / "researcher",
        role=RoleId.RESEARCHER,
        writable=False,
        network_mode="any",
        tools=frozenset({"Read", "WebSearch"}),
    )
    with pytest.raises(CapabilityUnavailable) as net_err:
        resolve_sandbox_mode(researcher_ro)
    assert net_err.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert net_err.value.details.get("reason") == "read_only_network_unsupported"

    # Secret plaintext in argv is rejected
    secret_val = "sk-secret-must-not-leak-999"
    leaking_req = _make_request(
        tmp_path / "leak",
        model=secret_val,
        secret_token=secret_val,
    )
    with pytest.raises(ValueError, match="secret values must never appear in Codex argv"):
        build_launch_plan(
            leaking_req,
            binary_path="/usr/bin/codex",
            step_dir=tmp_path / "leak/state/steps" / leaking_req.request_id,
            ownership=ProcessOwnership(leaking_req.process_owner, "pgroup_best_effort", "codex/leak"),
            host_environ=host_env,
        )


# ---------------------------------------------------------------------------
# 5. Config Isolation, Credentials Mount & Canary Suppression
# ---------------------------------------------------------------------------


def test_codex_isolated_client_home_credentials_mcp_toml_and_symlinks(tmp_path: Path) -> None:
    user_home = _make_user_home(tmp_path, with_credentials=True)
    secret_value = "skm-codex-secret-token-888"
    mcp = McpServerSpec(
        name="skm",
        command=("skm", "mcp", "serve", "--stdio", "--step-token-env", "SKM_TOKEN"),
        env={"DEL_CHAR": "a\x7fb", "SKM_RUNTIME": "codex"},
        secret_env_names=("SKM_TOKEN",),
    )
    req = _make_request(
        tmp_path / "iso",
        mcp_servers=(mcp,),
        secret_token=secret_value,
        extra_env={"HOME": str(tmp_path / "ignored-override")},
    )
    step_dir = tmp_path / "iso/state/steps" / req.request_id
    plan = build_launch_plan(
        req,
        binary_path="/usr/bin/codex",
        step_dir=step_dir,
        ownership=ProcessOwnership(req.process_owner, "pgroup_best_effort", "codex/iso"),
        host_environ={
            "PATH": "/usr/bin:/bin",
            "HOME": str(user_home),
            "CODEX_HOME": str(tmp_path / "host-codex-home"),
            "XDG_CONFIG_HOME": str(tmp_path / "host-xdg"),
        },
    )

    assert plan.client_home is not None
    assert plan.client_home.stat().st_mode & 0o777 == 0o700
    for subdir in WRITABLE_CLIENT_HOME_DIRS:
        sub_path = plan.client_home / subdir
        assert sub_path.is_dir()
        assert sub_path.stat().st_mode & 0o777 == 0o700

    copied_auth = plan.client_home / CREDENTIAL_FILENAME
    assert copied_auth.is_file()
    assert copied_auth.stat().st_mode & 0o777 == 0o600

    # Child env enforces isolated CODEX_HOME and HOME; strips XDG_CONFIG_HOME.
    env = plan.command.env
    assert env["CODEX_HOME"] == str(plan.client_home)
    assert env["HOME"] == str(plan.client_home)
    assert env["TMPDIR"] == str(plan.client_home / "tmp")
    assert "XDG_CONFIG_HOME" not in env
    assert env["SKM_TOKEN"] == secret_value

    # Generated <client_home>/config.toml has 0600 permissions, valid TOML, and no secret plaintext.
    config_path = plan.permissions.config_path
    assert config_path == plan.client_home / "config.toml"
    assert config_path.stat().st_mode & 0o777 == 0o600
    raw_toml = config_path.read_text(encoding="utf-8")
    assert secret_value not in raw_toml
    assert "\x7f" not in raw_toml
    assert "\\u007f" in raw_toml
    parsed_toml = decode_document(raw_toml, "toml")
    mcp_servers = cast("dict[str, Any]", parsed_toml["mcp_servers"])
    skm_mcp = cast("dict[str, Any]", mcp_servers["skm"])
    assert skm_mcp["command"] == "skm"
    assert skm_mcp["env_vars"] == ["SKM_TOKEN"]
    assert skm_mcp["env"] == {"DEL_CHAR": "a\x7fb", "SKM_RUNTIME": "codex"}

    # Missing credentials without OPENAI_API_KEY / CODEX_API_KEY raises RUNTIME_AUTH_EXPIRED.
    empty_home = _make_user_home(tmp_path / "empty_user", with_credentials=False)
    no_auth_req = _make_request(tmp_path / "no_auth")
    with pytest.raises(CapabilityUnavailable) as auth_err:
        build_launch_plan(
            no_auth_req,
            binary_path="/usr/bin/codex",
            step_dir=tmp_path / "no_auth/state/steps" / no_auth_req.request_id,
            ownership=ProcessOwnership(no_auth_req.process_owner, "pgroup_best_effort", "codex/no_auth"),
            host_environ={"PATH": "/usr/bin:/bin", "HOME": str(empty_home)},
        )
    assert auth_err.value.code is ErrorCode.RUNTIME_AUTH_EXPIRED


# ---------------------------------------------------------------------------
# 6. Stream Parser, Usage Normalization & Error Rules
# ---------------------------------------------------------------------------


def test_codex_stream_parser_basic_and_usage_normalization() -> None:
    secret = "sk-secret-value-12345"

    def redact(text: str) -> str:
        return text.replace(secret, MASK)

    p_basic = CodexStreamParser(default_model="gpt-5.3-codex", runtime_version="0.165.0", redact=redact)
    basic_lines = (FIXTURES_DIR / "stream_basic.jsonl").read_bytes().splitlines()
    emitted = [ev for line in basic_lines for ev in p_basic.feed(line)]

    assert isinstance(emitted[0], SessionStarted)
    assert emitted[0].session_ref == "0199aa00-thread-7"
    assert emitted[0].model == "gpt-5.3-codex"
    assert emitted[0].runtime_version == "0.165.0"

    # Reasoning text must not appear in public TextDelta events.
    deltas = [ev for ev in emitted if isinstance(ev, TextDelta)]
    assert len(deltas) == 1
    assert "Plan: read the file" not in deltas[0].text
    assert deltas[0].text == '{"status": "done", "summary": "Renamed x to y", "questions": []}'

    tool_reqs = [ev for ev in emitted if isinstance(ev, ToolRequested)]
    tool_comps = [ev for ev in emitted if isinstance(ev, ToolCompleted)]
    assert [t.tool for t in tool_reqs] == ["command_execution", "file_change"]
    assert [(t.call_id, t.status) for t in tool_comps] == [
        ("item_1", ToolCallStatus.OK),
        ("item_2", ToolCallStatus.OK),
    ]

    assert p_basic.is_terminal(basic_lines[-1]) is True
    assert p_basic.saw_terminal() is True
    outcome = p_basic.finish(0)
    assert outcome.final_text == '{"status": "done", "summary": "Renamed x to y", "questions": []}'
    assert outcome.usage.status is UsageStatus.REPORTED
    assert outcome.usage.source == "stream:result"
    assert outcome.usage.input_tokens == 1000
    assert outcome.usage.cache_read_tokens == 9000
    assert outcome.usage.cache_write_tokens is None
    assert outcome.usage.output_tokens == 100
    assert outcome.usage.cost_usd_micros is None
    assert outcome.usage.subagents == SubagentUsage(used=None, disclosed=False)

    pricing = Pricing(
        input_per_mtok_usd=Decimal("2.00"),
        output_per_mtok_usd=Decimal("8.00"),
        cache_read_per_mtok_usd=Decimal("0.50"),
        cache_write_per_mtok_usd=None,
        currency="USD",
        verified_at=date(2026, 10, 26),
        source="https://openai.com/api/pricing",
    )
    assert cost(outcome.usage, pricing) == 7300


def test_codex_stream_parser_termination_turn_scoping_denials_and_partial_crash() -> None:
    secret = "sk-secret-value-12345"

    # 1. Replay stream_no_terminal.jsonl: exit 0 without turn.completed -> saw_terminal() is False!
    p_no_term = CodexStreamParser(default_model="gpt-5.3-codex")
    for line in (FIXTURES_DIR / "stream_no_terminal.jsonl").read_bytes().splitlines():
        list(p_no_term.feed(line))
    assert p_no_term.saw_terminal() is False
    out_no_term = p_no_term.finish(0)
    assert out_no_term.final_text == ""
    assert out_no_term.signals.terminal is False

    # 2. Replay stream_notification_error.jsonl: non-fatal error notification does not fail turn.
    p_notif = CodexStreamParser(default_model="gpt-5.3-codex")
    for line in (FIXTURES_DIR / "stream_notification_error.jsonl").read_bytes().splitlines():
        list(p_notif.feed(line))
    assert p_notif.saw_terminal() is True
    out_notif = p_notif.finish(0)
    assert out_notif.is_error is False
    assert out_notif.signals.api_retries == 1
    assert out_notif.final_text == '{"status": "done", "summary": "Renamed x to y", "questions": []}'

    # 3. Turn scoping of final_text: failed turn's message is discarded; subsequent successful turn wins.
    p_turns = CodexStreamParser(default_model="gpt-5.3-codex")
    turn_lines = [
        b'{"type":"thread.started","thread_id":"t_scoped"}',
        b'{"type":"turn.started"}',
        b'{"type":"item.completed","item":{"id":"m1","type":"agent_message","text":"Discarded turn 1"}}',
        b'{"type":"turn.failed","error":{"message":"transient error"}}',
        b'{"type":"turn.started"}',
        b'{"type":"item.completed","item":{"id":"m2","type":"agent_message","text":"Accepted turn 2"}}',
        b'{"type":"turn.completed","usage":{"input_tokens":500,"cached_input_tokens":200,"output_tokens":30}}',
    ]
    for line in turn_lines:
        list(p_turns.feed(line))
    assert p_turns.saw_terminal() is True
    out_turns = p_turns.finish(0)
    assert out_turns.is_error is False
    assert out_turns.final_text == "Accepted turn 2"

    # Subsequent completed turn with no message clears accepted_turn_texts (strict final-turn scoping).
    for line in [
        b'{"type":"turn.started"}',
        b'{"type":"turn.completed","usage":{"input_tokens":600,"cached_input_tokens":200,"output_tokens":35}}',
    ]:
        list(p_turns.feed(line))
    assert p_turns.finish(0).final_text == ""

    # Non-fatal 429 error notification does not misclassify later turn.failed without HTTP status.
    p_stale_status = CodexStreamParser(default_model="gpt-5.3-codex")
    for line in [
        b'{"type":"thread.started","thread_id":"t_status"}',
        b'{"type":"turn.started"}',
        b'{"type":"error","message":"429 Too Many Requests: Reconnecting... 1/5","http_status":429}',
        b'{"type":"turn.failed","error":{"message":"Selected model is at capacity"}}',
    ]:
        list(p_stale_status.feed(line))
    out_stale = p_stale_status.finish(1)
    assert out_stale.signals.fatal_text == "Selected model is at capacity"
    assert out_stale.signals.http_status is None
    assert (
        classify("codex", out_stale.signals, CodexRuntime()._error_rules, now_unix=1_790_000_000).code
        is ErrorCode.MODEL_UNAVAILABLE
    )

    # 4. Sandbox denial -> ToolCompleted(DENIED) + secret-free ToolDenial hint.
    p_denial = CodexStreamParser(default_model="gpt-5.3-codex")
    d_events = [
        ev
        for line in (FIXTURES_DIR / "stream_sandbox_denial.jsonl").read_bytes().splitlines()
        for ev in p_denial.feed(line)
    ]
    d_comp = [ev for ev in d_events if isinstance(ev, ToolCompleted)]
    assert [(c.call_id, c.status) for c in d_comp] == [("item_s1", ToolCallStatus.DENIED)]
    out_denial = p_denial.finish(0)
    assert len(out_denial.denials) == 1
    assert out_denial.denials[0].tool == "command_execution"
    assert "rm" in out_denial.denials[0].hint

    hint = denial_hint("command_execution", {"command": f"curl -H 'Bearer {secret}' https://example.invalid"})
    assert secret not in hint
    assert "curl" in hint

    # 5. Partial crash preserves prior turn usage as ESTIMATED.
    p_crash = CodexStreamParser(default_model="gpt-5.3-codex")
    for line in (FIXTURES_DIR / "stream_partial_crash.jsonl").read_bytes().splitlines():
        list(p_crash.feed(line))
    assert p_crash.saw_terminal() is False
    out_crash = p_crash.finish(1)
    assert out_crash.usage.status is UsageStatus.ESTIMATED
    assert out_crash.usage.source == "stream:delta"
    assert out_crash.usage.input_tokens == 400
    assert out_crash.usage.cache_read_tokens == 2000
    assert out_crash.usage.output_tokens == 75

    assert UsageAccumulator().final_usage().status is UsageStatus.UNKNOWN
    assert normalize_usage_counts({"input_tokens": 100, "cached_input_tokens": 250}).input_tokens == 0


def test_codex_error_rules_evaluation_order() -> None:
    runtime = CodexRuntime()
    rules = runtime._error_rules
    now_unix = 1_790_000_000

    cases = [
        (
            RuntimeSignals(fatal_text="auth.json is missing or corrupted", exit_code=1),
            ErrorClass.AUTHENTICATION,
            ErrorCode.RUNTIME_AUTH_EXPIRED,
            False,
        ),
        (
            RuntimeSignals(fatal_text="To use Codex with your ChatGPT plan, upgrade access", exit_code=1),
            ErrorClass.AUTHORIZATION,
            ErrorCode.RUNTIME_FORBIDDEN,
            False,
        ),
        (
            RuntimeSignals(
                fatal_text="You\u2019ve hit your usage limit",
                limit_resets_at=1_790_003_600,
                exit_code=1,
            ),
            ErrorClass.QUOTA,
            ErrorCode.QUOTA_EXHAUSTED,
            False,
        ),
        (
            RuntimeSignals(fatal_text="rate limit exceeded, retry later", exit_code=1),
            ErrorClass.RATE_LIMIT,
            ErrorCode.RATE_LIMITED,
            True,
        ),
        (
            RuntimeSignals(fatal_text="ran out of room in the model's context window", exit_code=1),
            ErrorClass.CONTEXT_LIMIT,
            ErrorCode.CONTEXT_OVERFLOW,
            False,
        ),
        (
            RuntimeSignals(fatal_text="Selected model is at capacity", exit_code=1),
            ErrorClass.MODEL_UNAVAILABLE,
            ErrorCode.MODEL_UNAVAILABLE,
            False,
        ),
        (
            RuntimeSignals(fatal_text="experiencing high demand", exit_code=1),
            ErrorClass.PROVIDER_INTERNAL,
            ErrorCode.RUNTIME_OVERLOADED,
            True,
        ),
        (
            RuntimeSignals(fatal_text="blocked by reason: content_filter", exit_code=1),
            ErrorClass.CONTENT_POLICY,
            ErrorCode.CONTENT_REFUSED,
            False,
        ),
        (
            RuntimeSignals(fatal_text="stream disconnected before completion", exit_code=1),
            ErrorClass.TRANSPORT,
            ErrorCode.RUNTIME_TRANSPORT,
            True,
        ),
    ]
    for signals, expected_class, expected_code, expected_retryable in cases:
        failure = classify("codex", signals, rules, now_unix=now_unix)
        assert failure.error_class is expected_class
        assert failure.code is expected_code
        assert failure.retryable is expected_retryable


# ---------------------------------------------------------------------------
# 7. End-to-End Subprocess Execution via Synthetic Mock CLI Script
# ---------------------------------------------------------------------------


def _build_mock_codex_script(tmp_path: Path) -> Path:
    script = tmp_path / "bin" / "mock-codex"
    code = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import json, os, signal, sys, time
        from pathlib import Path

        argv = sys.argv[1:]
        if "--version" in argv:
            sys.stdout.write("codex-cli 0.165.0\\n")
            sys.exit(0)
        if argv[-2:] == ["exec", "--help"]:
            sys.stdout.write({ALL_SUPPORTED_EXEC_HELP!r} + "\\n")
            sys.exit(0)
        if "--help" in argv:
            sys.stdout.write({ALL_SUPPORTED_ROOT_HELP!r} + "\\n")
            sys.exit(0)
        if argv[-2:] == ["login", "status"]:
            sys.stdout.write("Logged in using ChatGPT\\n")
            sys.exit(0)

        mode = os.environ.get("MOCK_CODEX_MODE", "basic")
        prompt = sys.stdin.read()

        # Canary check: if CODEX_HOME is not isolated or points inside worktree, trigger canary!
        codex_home = os.environ.get("CODEX_HOME", "")
        wt_codex = Path.cwd() / ".codex"
        if not codex_home or Path(codex_home).resolve() == wt_codex.resolve():
            canary = wt_codex / "canary_triggered"
            canary.parent.mkdir(parents=True, exist_ok=True)
            canary.write_text("leaked", encoding="utf-8")

        if mode == "hang_ignore_int":
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            sys.stdout.write(json.dumps({{"type": "thread.started", "thread_id": "t_hang"}}) + "\\n")
            sys.stdout.flush()
            time.sleep(30.0)
            sys.exit(0)

        if mode == "fixture":
            fixture_path = Path(os.environ["MOCK_FIXTURE_PATH"])
            sys.stdout.buffer.write(fixture_path.read_bytes())
            sys.stdout.buffer.flush()
            sys.exit(int(os.environ.get("MOCK_EXIT_CODE", "0")))

        tok = os.environ.get("SKM_TOKEN", "")
        sys.stderr.write(f"debug stderr token={{tok}}\\n")
        sys.stderr.flush()

        resumed = None
        if "resume" in argv:
            r_idx = argv.index("resume")
            if r_idx + 1 < len(argv):
                resumed = argv[r_idx + 1]

        payload_summary = json.dumps({{
            "prompt": prompt,
            "home": os.environ.get("HOME"),
            "codex_home": codex_home,
            "resumed": resumed,
            "stdin_dash": argv[-1] == "-",
            "approval_never": argv[:2] == ["-a", "never"],
        }}, sort_keys=True)
        records = [
            {{"type": "thread.started", "thread_id": "019a4f10-7c00-7000-8000-000000000001"}},
            {{"type": "turn.started"}},
            {{
                "type": "item.completed",
                "item": {{"id": "item_1", "type": "agent_message", "text": payload_summary}},
            }},
            {{
                "type": "turn.completed",
                "usage": {{"input_tokens": 1200, "cached_input_tokens": 900, "output_tokens": 45}},
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
        ("stream_notification_error.jsonl", 0, "completed", None),
        ("stream_resume.jsonl", 0, "completed", None),
        ("stream_sandbox_denial.jsonl", 0, "completed", None),
        ("stream_no_terminal.jsonl", 0, "failed", ErrorCode.RUNTIME_STREAM_INCOMPLETE),
        ("stream_turn_failed.jsonl", 1, "failed", ErrorCode.MODEL_UNAVAILABLE),
        ("stream_partial_crash.jsonl", 1, "failed", ErrorCode.RUNTIME_CRASHED),
        ("stream_quota.jsonl", 1, "failed", ErrorCode.QUOTA_EXHAUSTED),
        ("stream_auth_401.jsonl", 1, "failed", ErrorCode.RUNTIME_AUTH_EXPIRED),
    ],
)
def test_codex_contract_replay_all_fixtures_end_to_end(
    tmp_path: Path,
    fixture_name: str,
    exit_code: int,
    expected_outcome: str,
    expected_code: ErrorCode | None,
) -> None:
    """Replay all 9 fixtures through CodexRuntime + CliSession + SchemaRegistry."""
    mock_bin = _build_mock_codex_script(tmp_path)
    user_home = _make_user_home(tmp_path, with_credentials=True)
    schemas = SchemaRegistry.load_default()

    runtime = CodexRuntime(
        state_dir=tmp_path / "state",
        binary=str(mock_bin),
        environ={"PATH": "/usr/bin:/bin", "HOME": str(user_home)},
        poll_interval_seconds=0.02,
    )
    req = _make_request(
        tmp_path / "case",
        extra_env={
            "MOCK_CODEX_MODE": "fixture",
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

    assert isinstance(events[-2], UsageReported)
    assert events[-2].cumulative is True
    assert isinstance(events[-1], SessionCompleted if expected_outcome == "completed" else SessionFailed)

    assert result.outcome == expected_outcome
    assert (None if result.failure is None else result.failure.code) == expected_code

    if fixture_name == "stream_basic.jsonl":
        assert runtime.auth_state is AuthState.OK
        assert result.transcript_path is not None
        assert "Plan: read the file" in Path(result.transcript_path).read_text(encoding="utf-8")
    elif fixture_name == "stream_auth_401.jsonl":
        assert runtime.auth_state is AuthState.EXPIRED
    elif fixture_name == "stream_partial_crash.jsonl":
        assert result.usage.status is UsageStatus.ESTIMATED
        assert result.usage.input_tokens == 400


def test_codex_e2e_canary_suppression_stdin_secret_redaction_resume_and_cancellation(
    tmp_path: Path,
) -> None:
    mock_bin = _build_mock_codex_script(tmp_path)
    user_home = _make_user_home(tmp_path, with_credentials=True)
    secret_tok = "skm-codex-e2e-secret-9999"

    runtime = CodexRuntime(
        state_dir=tmp_path / "state",
        binary=str(mock_bin),
        environ={"PATH": "/usr/bin:/bin", "HOME": str(user_home)},
        poll_interval_seconds=0.02,
    )
    req = _make_request(
        tmp_path / "e2e",
        prompt="Verify isolated CODEX_HOME over stdin.",
        session_policy="persistent",
        resume_session_ref="019a4f10-7c00-7000-8000-000000000001",
        secret_token=secret_tok,
    )
    # Plant untrusted <worktree>/.codex/config.toml canary; isolated CODEX_HOME must ignore it.
    wt_codex = Path(req.workdir) / ".codex"
    wt_codex.mkdir(parents=True, exist_ok=True)
    (wt_codex / "config.toml").write_text('[mcp_servers.evil]\ncommand = "evil"\n', encoding="utf-8")

    handle = runtime.start(req)
    events = list(runtime.events(handle))
    res = runtime.result(handle)

    assert validate_event_stream(events) == ()
    assert res.outcome == "completed"
    assert runtime.auth_state is AuthState.OK
    assert not (wt_codex / "canary_triggered").exists()

    summary = json.loads(res.final_text)
    assert summary["prompt"] == "Verify isolated CODEX_HOME over stdin."
    assert summary["home"] == req.client_home
    assert summary["codex_home"] == req.client_home
    assert summary["resumed"] == "019a4f10-7c00-7000-8000-000000000001"
    assert summary["stdin_dash"] is True
    assert summary["approval_never"] is True

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

    cancel_rt = CodexRuntime(
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
        extra_env={"MOCK_CODEX_MODE": "hang_ignore_int"},
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


def test_codex_rejects_missing_workdir_and_symlink_client_home(tmp_path: Path) -> None:
    mock_bin = _build_mock_codex_script(tmp_path)
    user_home = _make_user_home(tmp_path, with_credentials=True)
    runtime = CodexRuntime(
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
