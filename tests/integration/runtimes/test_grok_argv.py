"""Offline unit, integration, and contract replay tests for Grok runtime adapter.

Never invokes a real ``grok`` CLI binary. All binary probes and subprocess executions use
hermetic synthetic scripts or in-memory probe doubles inside ``tmp_path``.
"""

from __future__ import annotations

import os
import sys
import textwrap
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Literal
from uuid import UUID, uuid4

import pytest

from skm.adapters.runtimes._cli_session.probe import (
    CommandOutput,
)
from skm.adapters.runtimes.grok.detect import (
    OPTIONAL_FLAGS,
    REQUIRED_FLAGS,
    GrokDetector,
)
from skm.adapters.runtimes.grok.launch import (
    build_launch_plan,
    compute_launch_config_digest,
)
from skm.adapters.runtimes.grok.permissions import READ_ONLY_DISALLOWED_TOOLS, denial_hint
from skm.adapters.runtimes.grok.runtime import GrokRuntime
from skm.adapters.runtimes.grok.stream_parser import GrokStreamParser
from skm.adapters.runtimes.grok.usage import UsageAccumulator, normalize_usage_counts
from skm.bootstrap.builtins import BUILTIN_COMPONENTS, component_problem
from skm.bootstrap.runtimes import RUNTIME_FACTORIES
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.ids import HostId
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.admission import (
    ADMISSION_DEFAULTS,
    AdmissionFacts,
    Operation,
    admit,
)
from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityStatus,
    SelfLoadKind,
    StaticCapabilityCatalog,
    effective_capabilities,
    parse_capabilities,
)
from skm.modules.runtimes.domain.catalog import (
    ModelCatalog,
    ModelEntry,
    ModelStatus,
    Pricing,
    RuntimeCatalogEntry,
)
from skm.modules.runtimes.domain.classes import Effort, ModelClass, RoleId
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.error_rules import (
    ErrorClass,
    RuntimeSignals,
    classify,
    parse_error_rules,
)
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.domain.request import (
    AgentRequest,
    CommandRules,
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
from skm.modules.runtimes.domain.routing import RouteConfig, RouteRequest, route
from skm.modules.runtimes.domain.session_events import (
    SessionCompleted,
    SessionFailed,
    validate_event_stream,
)
from skm.modules.runtimes.domain.usage import UsageStatus, cost
from skm.platform.config.sources.document import decode_document
from skm.platform.schema.registry import SchemaRegistry
from skm.plugin_api.manifest import ComponentKind

ROOT = Path(__file__).resolve().parents[3]
ADAPTER_DIR = ROOT / "src/skm/adapters/runtimes/grok"
FIXTURES_DIR = ROOT / "tests/fixtures/runtimes/grok"
HOST_1 = HostId(UUID("0193a6f0-0100-7a00-8000-9a8b7c6d5e4f"))
TODAY = date(2026, 11, 10)
NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)
DIGEST = "sha256:" + "b" * 64

ALL_SUPPORTED_HELP_TEXT = "Usage: grok [options]\n" + "\n".join(
    f"  {flag}  supported option" for flag in (*REQUIRED_FLAGS, *OPTIONAL_FLAGS)
)


def _write_executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    os.chmod(path, 0o700)
    return path


def _make_stub_binary(tmp_path: Path, name: str = "grok") -> Path:
    return _write_executable(tmp_path / "bin" / name, "#!/bin/sh\nexit 0\n")


def _make_request(
    tmp_path: Path,
    *,
    role: RoleId = RoleId.EXECUTOR,
    writable: bool = True,
    network_mode: Literal["none", "allowlist", "any"] = "any",
    isolation_profile: IsolationProfile = IsolationProfile.LANDLOCK,
    config_mode: Literal["isolated", "inherit"] = "inherit",
    resume_session_ref: str | None = None,
    effort: Effort | None = Effort.HIGH,
    model: str = "grok-4.7",
    prompt: str = "Inspect repository and verify contract.",
    secret_token: str | None = "skm-grok-secret-token-998877",
) -> AgentRequest:
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    step_id = uuid4()
    run_id = uuid4()
    read_rules = PathRules((PathRule(str(workdir), "**"),), ())
    write_rules = PathRules((PathRule(str(workdir), "**"),), ()) if writable else PathRules((), ())
    owner = ProcessOwner(
        run_id, run_id, run_id, run_id, "step", step_id, "synthetic-grok-nonce-0001", str(state_dir / "id")
    )
    resolved_home = (
        None if config_mode == "inherit" else str(state_dir / "client-homes" / str(run_id) / "grok")
    )
    secrets = {"SKM_TOKEN": SecretStr(secret_token)} if secret_token is not None else {}
    return AgentRequest(
        request_id=str(step_id),
        runtime_id="grok",
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
            commands=CommandRules("none" if role is RoleId.SCOUT else "any", (), (), ()),
            network=NetworkRules(network_mode, ()),
            tools=frozenset(),
            external_effects=frozenset(),
        ),
        isolation_profile=isolation_profile,
        process_owner=owner,
        config_mode=config_mode,
        client_home=resolved_home,
        resume_session_ref=resume_session_ref,
        session_policy="ephemeral",
        env_allowlist=(),
        extra_env={},
        secret_env=secrets,
        mcp_servers=(),
        limits=RuntimeLimits(30, 10, 10, None, 4 * 1024 * 1024),
        labels={"run_id": str(run_id), "step_id": str(step_id)},
    )


def test_grok_static_toml_declarations_and_bootstrap_registration(tmp_path: Path) -> None:
    schemas = SchemaRegistry.load_default()
    caps_doc = decode_document((ADAPTER_DIR / "capabilities.toml").read_text(encoding="utf-8"), "toml")
    rules_doc = decode_document((ADAPTER_DIR / "error_rules.toml").read_text(encoding="utf-8"), "toml")

    assert schemas.validate("urn:skm:runtimes:capabilities:v1", caps_doc) == ()
    assert schemas.validate("urn:skm:runtimes:error-rules:v1", rules_doc) == ()

    caps = parse_capabilities(caps_doc)
    rules = parse_error_rules(rules_doc)
    catalog = StaticCapabilityCatalog(declarations={"grok": caps}, rules={"grok": rules})
    assert catalog.registered() == frozenset({"grok"})
    assert set(caps.records) == set(Capability)
    assert caps.status(Capability.HEADLESS_EXECUTION) is CapabilityStatus.ADAPTED
    assert caps.status(Capability.CONFIG_ISOLATION) is CapabilityStatus.UNSUPPORTED
    assert caps.status(Capability.SANDBOX_NATIVE) is CapabilityStatus.UNSUPPORTED
    assert caps.status(Capability.TOOL_INTERCEPTION) is CapabilityStatus.UNSUPPORTED

    proj_settings = [s for s in caps.self_loads if s.kind is SelfLoadKind.PROJECT_SETTINGS]
    assert len(proj_settings) == 1
    assert proj_settings[0].suppressed_by == "never"

    custom_bin = _make_stub_binary(tmp_path, "custom-grok")
    ctx = SimpleNamespace(config={"runtimes.binaries": {"grok": str(custom_bin)}})
    built = RUNTIME_FACTORIES["grok"](ctx, environ={})
    assert isinstance(built, GrokRuntime)
    assert built.runtime_id == "grok"

    grok_specs = [s for s in BUILTIN_COMPONENTS if s.kind is ComponentKind.RUNTIME and s.key == "grok"]
    assert len(grok_specs) == 1
    assert component_problem(grok_specs[0], built) is None


def test_grok_detector_6tuple_cache_and_invalidation(tmp_path: Path) -> None:
    binary = _make_stub_binary(tmp_path, "grok")
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...], *, env: object, timeout_seconds: float) -> CommandOutput:
        del env, timeout_seconds
        calls.append(argv)
        if argv[-1] == "--version":
            return CommandOutput(0, "grok-cli 0.1.0\n", "")
        return CommandOutput(0, ALL_SUPPORTED_HELP_TEXT, "")

    kernel_val = "Linux:6.8.0"
    detector = GrokDetector(run_cmd=runner, os_kernel_fn=lambda: kernel_val)
    digest = compute_launch_config_digest(adapter_version="0.1.0")
    env = {"PATH": str(binary.parent)}

    p1 = detector.probe(
        binary="grok", environ=env, env_allowlist=(), adapter_version="0.1.0", launch_config_digest=digest
    )
    p2 = detector.probe(
        binary="grok", environ=env, env_allowlist=(), adapter_version="0.1.0", launch_config_digest=digest
    )
    assert p1 is p2
    assert len(calls) == 2

    # Mutate binary contents -> new binary_sha256 -> re-probes version + help.
    _write_executable(binary, "#!/bin/sh\n# updated\nexit 0\n")
    p3 = detector.probe(
        binary="grok", environ=env, env_allowlist=(), adapter_version="0.1.0", launch_config_digest=digest
    )
    assert p3.binary_sha256 != p1.binary_sha256
    assert len(calls) == 4

    # Missing binary raises FileNotFoundError on detect and RUNTIME_NOT_INSTALLED on start.
    rt_missing = GrokRuntime(state_dir=tmp_path / "st", binary="/nonexistent/grok", environ={})
    with pytest.raises(FileNotFoundError):
        rt_missing.detect(DetectProbe(host_id=HOST_1, binary=None, env_allowlist=(), timeout_seconds=10))
    with pytest.raises(CapabilityUnavailable) as exc_info:
        rt_missing.start(_make_request(tmp_path, isolation_profile=IsolationProfile.LANDLOCK))
    assert exc_info.value.code is ErrorCode.RUNTIME_NOT_INSTALLED


def test_grok_argv_rendering_landlock_grants_and_stdin_prompt(tmp_path: Path) -> None:
    binary = _make_stub_binary(tmp_path, "grok")
    user_home = tmp_path / "user-home"
    (user_home / ".grok").mkdir(parents=True)

    # 1. Read-only scout without network: --disallowed-tools, --disable-web-search, --protect <workdir>.
    scout_req = _make_request(
        tmp_path / "scout",
        role=RoleId.SCOUT,
        writable=False,
        network_mode="none",
        isolation_profile=IsolationProfile.LANDLOCK,
        prompt="Find secret_needle without editing files.",
    )
    scout_plan = build_launch_plan(
        scout_req,
        binary_path=str(binary),
        step_dir=tmp_path / "scout-step",
        ownership=ProcessOwnership(scout_req.process_owner, "pgroup_best_effort", "grok/scout"),
        host_environ={"HOME": str(user_home)},
        user_home=user_home,
    )
    assert scout_plan.grok_argv == (
        str(binary),
        "--cwd",
        str(Path(scout_req.workdir).resolve()),
        "--prompt-file",
        "/dev/stdin",
        "--model",
        "grok-4.7",
        "--effort",
        "high",
        "--permission-mode",
        "bypassPermissions",
        "--output-format",
        "streaming-messages-json",
        "--disallowed-tools",
        ",".join(READ_ONLY_DISALLOWED_TOOLS),
        "--disable-web-search",
    )
    assert scout_plan.stdin == b"Find secret_needle without editing files."
    assert all("secret_needle" not in arg for arg in scout_plan.command.argv)
    assert all("skm-grok-secret-token-998877" not in arg for arg in scout_plan.command.argv)
    assert scout_plan.command.env["SKM_TOKEN"] == "skm-grok-secret-token-998877"
    assert scout_plan.command.env["HOME"] == str(user_home)
    assert scout_plan.scope_roots.tmp == scout_plan.command.env["TMPDIR"] == str(scout_plan.step_tmp)

    ll_argv = scout_plan.command.argv
    assert "--no-default-rw" in ll_argv
    assert "--protect" in ll_argv
    assert str(Path(scout_req.workdir).resolve()) == ll_argv[ll_argv.index("--protect") + 1]
    assert str(user_home) not in ll_argv
    assert str(user_home / ".grok") not in ll_argv

    # 2. Reviewer with existing vendor dir gets --protect <workdir> and --rw <workdir>/vendor.
    rev_req = _make_request(
        tmp_path / "rev",
        role=RoleId.REVIEWER,
        writable=False,
        network_mode="any",
        isolation_profile=IsolationProfile.LANDLOCK,
    )
    vendor_dir = Path(rev_req.workdir) / "vendor"
    vendor_dir.mkdir()
    rev_plan = build_launch_plan(
        rev_req,
        binary_path=str(binary),
        step_dir=tmp_path / "rev-step",
        ownership=ProcessOwnership(rev_req.process_owner, "pgroup_best_effort", "grok/rev"),
        host_environ={},
    )
    assert "--disable-web-search" not in rev_plan.grok_argv
    assert str(vendor_dir.resolve()) in rev_plan.command.argv

    # 3. Writable executor with session resume gets --rw <workdir> and --resume.
    exec_req = _make_request(
        tmp_path / "exec",
        role=RoleId.EXECUTOR,
        writable=True,
        isolation_profile=IsolationProfile.LANDLOCK,
        resume_session_ref="00000000-0000-0000-0000-000000000099",
    )
    exec_plan = build_launch_plan(
        exec_req,
        binary_path=str(binary),
        step_dir=tmp_path / "exec-step",
        ownership=ProcessOwnership(exec_req.process_owner, "pgroup_best_effort", "grok/exec"),
        host_environ={},
    )
    assert "--disallowed-tools" not in exec_plan.grok_argv
    assert "--resume" in exec_plan.grok_argv
    assert exec_plan.grok_argv[exec_plan.grok_argv.index("--resume") + 1] == (
        "00000000-0000-0000-0000-000000000099"
    )
    assert "--protect" not in exec_plan.command.argv
    assert str(Path(exec_req.workdir).resolve()) in exec_plan.command.argv


@pytest.mark.parametrize("bad_profile", [IsolationProfile.NONE, IsolationProfile.WORKTREE])
def test_grok_refuses_uncontained_isolation_and_registrar_role(
    tmp_path: Path,
    bad_profile: IsolationProfile,
) -> None:
    runtime = GrokRuntime(state_dir=tmp_path / "state", environ={})

    with pytest.raises(CapabilityUnavailable) as iso_err:
        runtime.start(_make_request(tmp_path / "uncontained", isolation_profile=bad_profile))
    assert iso_err.value.code is ErrorCode.SANDBOX_UNAVAILABLE
    assert iso_err.value.details.get("runtime_id") == "grok"

    with pytest.raises(CapabilityUnavailable) as reg_err:
        runtime.start(
            _make_request(
                tmp_path / "registrar",
                role=RoleId.REGISTRAR,
                isolation_profile=IsolationProfile.LANDLOCK,
            )
        )
    assert reg_err.value.code is ErrorCode.SANDBOX_UNAVAILABLE
    assert reg_err.value.details.get("reason") == "role_forbidden"


def test_grok_usage_error_rules_and_subprocess_stream_replays(tmp_path: Path) -> None:
    # Error rules & denial hints unit checks.
    rules_doc = decode_document((ADAPTER_DIR / "error_rules.toml").read_text(encoding="utf-8"), "toml")
    rules = parse_error_rules(rules_doc)
    rate_hit = classify(
        "grok",
        RuntimeSignals(exit_code=1, http_status=429, limit_resets_at=1_800_000_000),
        rules,
        now_unix=1_799_999_900,
    )
    assert rate_hit.error_class is ErrorClass.RATE_LIMIT
    assert rate_hit.code is ErrorCode.RATE_LIMITED
    assert rate_hit.retry_after_seconds == 100
    assert "git" in denial_hint("run_terminal_command", {"command": "git push origin main"})

    counts = normalize_usage_counts(
        {"input_tokens": 100, "output_tokens": 15, "cache_read_input_tokens": 20, "total_cost_usd": 9.99}
    )
    acc = UsageAccumulator()
    acc.mark_tool("spawn_subagent")
    rep = acc.record_result_usage(
        {"input_tokens": counts.input_tokens, "output_tokens": counts.output_tokens}
    )
    assert rep is not None
    assert rep.cost_usd_micros is None
    assert rep.source == "grok.stream"
    assert rep.subagents.used is True
    assert rep.subagents.disclosed is False

    # Subprocess CLI replay across fixtures (success, error result, exit 0 without result, malformed).
    script = _write_executable(
        tmp_path / "bin" / "mock-grok",
        f"#!{sys.executable}\n"
        + textwrap.dedent(
            """\
            import os, pathlib, sys
            if "--version" in sys.argv:
                print("grok 0.1.0")
                raise SystemExit(0)
            if "--help" in sys.argv:
                print(
                    "--cwd --prompt-file --model --effort --permission-mode "
                    "--output-format --resume --disallowed-tools --disable-web-search"
                )
                raise SystemExit(0)
            prompt = sys.stdin.read()
            pathlib.Path(os.environ["MOCK_PROMPT_OUT"]).write_text(prompt, encoding="utf-8")
            mode = os.environ["MOCK_GROK_MODE"]
            fdir = pathlib.Path(os.environ["MOCK_FIXTURES_DIR"])
            if mode == "ok":
                sys.stdout.write((fdir / "streaming-messages-json.jsonl").read_text(encoding="utf-8"))
                raise SystemExit(0)
            if mode == "err":
                sys.stdout.write((fdir / "streaming-messages-json-error.jsonl").read_text(encoding="utf-8"))
                raise SystemExit(1)
            if mode == "exit0_no_result":
                sys.stdout.write((fdir / "stream_exit0_no_result.jsonl").read_text(encoding="utf-8"))
                raise SystemExit(0)
            sys.stdout.write("not-json-at-all\\n")
            raise SystemExit(0)
            """
        ),
    )

    def run_mode(mode: str, sub: str):
        prompt_out = tmp_path / f"prompt-{sub}.txt"
        rt_inst = GrokRuntime(
            state_dir=tmp_path / f"state-{sub}",
            binary=str(script),
            environ={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "MOCK_GROK_MODE": mode,
                "MOCK_FIXTURES_DIR": str(FIXTURES_DIR),
                "MOCK_PROMPT_OUT": str(prompt_out),
            },
            wrap_landlock=False,
            result_grace_seconds=0.2,
        )
        req = _make_request(
            tmp_path / f"case-{sub}",
            isolation_profile=IsolationProfile.CONTAINER,
            prompt=f"prompt-for-{sub}",
        )
        req = replace(
            req,
            env_allowlist=("PATH", "MOCK_GROK_MODE", "MOCK_FIXTURES_DIR", "MOCK_PROMPT_OUT"),
        )
        handle = rt_inst.start(req)
        events = list(rt_inst.events(handle))
        res = rt_inst.result(handle)
        return events, res, prompt_out.read_text(encoding="utf-8")

    ok_events, ok_res, ok_prompt = run_mode("ok", "ok")
    assert ok_prompt == "prompt-for-ok"
    assert validate_event_stream(ok_events) == ()
    assert isinstance(ok_events[-1], SessionCompleted)
    assert ok_res.outcome == "completed"
    assert ok_res.final_text == "checked"
    assert ok_res.usage.status is UsageStatus.REPORTED
    assert ok_res.usage.source == "grok.stream"
    assert ok_res.usage.input_tokens == 100
    assert ok_res.usage.output_tokens == 15
    assert ok_res.usage.cache_read_tokens == 20
    assert ok_res.usage.cost_usd_micros is None
    pricing = Pricing(Decimal("3.0"), Decimal("15.0"), Decimal("0.3"), Decimal("3.75"), "USD", TODAY, "test")
    assert cost(ok_res.usage, pricing) == 531

    err_events, err_res, _ = run_mode("err", "err")
    assert validate_event_stream(err_events) == ()
    assert isinstance(err_events[-1], SessionFailed)
    assert err_res.outcome == "failed"
    assert err_res.usage.input_tokens == 100
    assert err_res.usage.cost_usd_micros is None

    inc_events, inc_res, _ = run_mode("exit0_no_result", "inc")
    assert validate_event_stream(inc_events) == ()
    assert inc_res.failure is not None
    assert inc_res.failure.code is ErrorCode.RUNTIME_STREAM_INCOMPLETE
    assert inc_res.usage.status is UsageStatus.ESTIMATED
    assert inc_res.usage.input_tokens == 64

    mal_events, mal_res, _ = run_mode("malformed", "mal")
    assert validate_event_stream(mal_events) == ()
    assert mal_res.failure is not None
    assert mal_res.failure.code is ErrorCode.RUNTIME_STREAM_INCOMPLETE

    parser = GrokStreamParser(runtime_version="0.1.0")
    for raw_line in (FIXTURES_DIR / "streaming-messages-json.jsonl").read_bytes().splitlines():
        list(parser.feed(raw_line))
    assert parser.saw_terminal() is True


def test_grok_self_loaded_context_and_routing_isolation_gate(tmp_path: Path) -> None:
    runtime = GrokRuntime(state_dir=tmp_path / "state", environ={})
    sources = runtime.self_loaded_context(_make_request(tmp_path))
    assert {src.kind for src in sources} == {
        SelfLoadKind.PROJECT_SETTINGS,
        SelfLoadKind.PROJECT_INSTRUCTIONS,
        SelfLoadKind.SKILLS,
        SelfLoadKind.PLUGINS,
        SelfLoadKind.USER_CONFIG,
    }
    assert all(src.trust == "untrusted" for src in sources)

    eff_caps = effective_capabilities(runtime.capabilities(), (), host_version="0.1.0", now=TODAY)
    grok_entry = RuntimeCatalogEntry(
        runtime_id="grok",
        class_selectors=MappingProxyType({ModelClass.IMPLEMENTATION: ("grok-4.7",)}),
        effort_selectors=MappingProxyType({Effort.MEDIUM: "medium", Effort.HIGH: "high"}),
        models=(
            ModelEntry(
                "grok-4.7",
                "grok",
                "Grok 4.7",
                frozenset({ModelClass.IMPLEMENTATION}),
                frozenset({RoleId.EXECUTOR, RoleId.REVIEWER}),
                128_000,
                16_000,
                None,
                (),
                ModelStatus.CONFIRMED,
                TODAY,
                "test",
                "",
            ),
        ),
    )
    catalog = ModelCatalog("1.0.0", (), DIGEST, {"grok": grok_entry})
    installs = {
        "grok": RuntimeInstallation(HOST_1, "grok", "0.1.0", "/usr/bin/grok", AuthState.OK, NOW, {}),
    }
    admission = admit(
        AdmissionFacts(
            Operation.NEW_IMPLEMENTATION, RoleId.EXECUTOR, None, None, None, None, DIGEST, None, None, None
        ),
        ADMISSION_DEFAULTS,
    )

    # 1. Unattended strict (isolated) -> rejected because config_isolation is unsupported.
    strict_cfg = RouteConfig(frozenset({"grok"}), ("grok",), {}, frozenset(), config_isolation_required=True)
    strict_req = RouteRequest(
        RoleId.EXECUTOR,
        frozenset({Capability.HEADLESS_EXECUTION}),
        frozenset(),
        ModelClass.IMPLEMENTATION,
        Effort.HIGH,
        "grok",
        None,
        HOST_1,
        admission,
        "isolated",
        frozenset(),
        False,
        "unattended-strict",
    )
    with pytest.raises(CapabilityUnavailable):
        route(strict_req, strict_cfg, catalog, {"grok": eff_caps}, installs, frozenset({"grok"}))

    # 2. Even with config_isolation_required=False & inherit, non-trusted profile is refused on ./.grok/**.
    relaxed_cfg = replace(strict_cfg, config_isolation_required=False)
    inherit_unattended = replace(strict_req, config_mode="inherit", policy_profile="unattended-relaxed")
    with pytest.raises(CapabilityUnavailable):
        route(inherit_unattended, relaxed_cfg, catalog, {"grok": eff_caps}, installs, frozenset({"grok"}))

    # 3. Explicit trusted-full-access allows routing to Grok.
    trusted_req = replace(strict_req, config_mode="inherit", policy_profile="trusted-full-access")
    decision = route(trusted_req, relaxed_cfg, catalog, {"grok": eff_caps}, installs, frozenset({"grok"}))
    assert decision.runtime_id == "grok"
    assert decision.model == "grok-4.7"
