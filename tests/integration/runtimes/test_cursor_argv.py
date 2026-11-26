"""Offline unit, detection, routing exclusion, and refusal tests for Cursor adapter.

Verifies that Cursor v1 implements detect + honest unknown capability matrix only, refuses
routing for active roles, and fails closed on ``CursorRuntime.start()`` before spawning.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from uuid import UUID, uuid4

import pytest

from skm.adapters.runtimes._cli_session.probe import (
    CommandOutput,
)
from skm.adapters.runtimes.cursor.detect import (
    DEFAULT_CURSOR_BINARY,
    CursorDetector,
    compute_launch_config_digest,
)
from skm.adapters.runtimes.cursor.runtime import CursorRuntime
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
    RuntimeCatalogEntry,
)
from skm.modules.runtimes.domain.classes import Effort, ModelClass, RoleId
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.error_rules import parse_error_rules
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
)
from skm.modules.runtimes.domain.routing import RouteConfig, RouteRequest, route
from skm.modules.runtimes.ports import SessionHandle
from skm.platform.config.sources.document import decode_document
from skm.platform.schema.registry import SchemaRegistry
from skm.plugin_api.manifest import ComponentKind

ROOT = Path(__file__).resolve().parents[3]
ADAPTER_DIR = ROOT / "src/skm/adapters/runtimes/cursor"
FIXTURES_DIR = ROOT / "tests/fixtures/runtimes/cursor"
HOST_1 = HostId(UUID("0193a6f0-0100-7a00-8000-9a8b7c6d5e4f"))
TODAY = date(2026, 11, 10)
NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)
DIGEST = "sha256:" + "c" * 64
HONEST_LIMITATION = "not verified; headless contract unknown"


def _write_executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    os.chmod(path, 0o700)
    return path


def _make_cursor_request(tmp_path: Path) -> AgentRequest:
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    step_id = uuid4()
    run_id = uuid4()
    prompt = "Verify cursor refusal."
    owner = ProcessOwner(
        host_id=run_id,
        worker_id=run_id,
        attempt_id=run_id,
        stage_record_id=run_id,
        unit_kind="step",
        unit_id=step_id,
        owner_nonce="synthetic-cursor-nonce-0001",
        identity_dir=str(state_dir / "identities"),
    )
    return AgentRequest(
        request_id=str(step_id),
        runtime_id="cursor",
        model="cursor-default",
        effort=Effort.MEDIUM,
        role=RoleId.EXECUTOR,
        rendered_prompt=prompt,
        prompt_digest=f"sha256:{sha256(prompt.encode('utf-8')).hexdigest()}",
        result_format=ResultFormat.TEXT,
        result_schema_urn=None,
        workdir=str(workdir),
        permissions=PermissionGrant(
            fs_read=PathRules((PathRule(str(workdir), "**"),), ()),
            fs_write=PathRules((PathRule(str(workdir), "**"),), ()),
            commands=CommandRules("any", (), (), ()),
            network=NetworkRules("any", ()),
            tools=frozenset(),
            external_effects=frozenset(),
        ),
        isolation_profile=IsolationProfile.LANDLOCK,
        process_owner=owner,
        config_mode="inherit",
        client_home=None,
        resume_session_ref=None,
        session_policy="ephemeral",
        env_allowlist=(),
        extra_env={},
        secret_env={},
        mcp_servers=(),
        limits=RuntimeLimits(
            timeout_seconds=30,
            idle_timeout_seconds=10,
            max_turns=5,
            max_output_tokens=None,
            max_output_bytes=1024 * 1024,
        ),
        labels={},
    )


def test_cursor_honest_capability_matrix_and_bootstrap_aliases(tmp_path: Path) -> None:
    schemas = SchemaRegistry.load_default()
    caps_doc = decode_document((ADAPTER_DIR / "capabilities.toml").read_text(encoding="utf-8"), "toml")
    rules_doc = decode_document((ADAPTER_DIR / "error_rules.toml").read_text(encoding="utf-8"), "toml")

    assert schemas.validate("urn:skm:runtimes:capabilities:v1", caps_doc) == ()
    assert schemas.validate("urn:skm:runtimes:error-rules:v1", rules_doc) == ()

    caps = parse_capabilities(caps_doc)
    rules = parse_error_rules(rules_doc)
    catalog = StaticCapabilityCatalog(declarations={"cursor": caps}, rules={"cursor": rules})
    assert catalog.registered() == frozenset({"cursor"})
    assert set(caps.records) == set(Capability)
    assert caps.status(Capability.HEADLESS_EXECUTION) is CapabilityStatus.UNKNOWN
    assert caps.status(Capability.CONFIG_ISOLATION) is CapabilityStatus.UNKNOWN
    assert caps.status(Capability.STRUCTURED_RESULT) is CapabilityStatus.UNKNOWN
    assert caps.status(Capability.STREAM_EVENTS) is CapabilityStatus.UNKNOWN
    assert caps.status(Capability.RELIABLE_CANCELLATION) is CapabilityStatus.UNKNOWN
    assert caps.status(Capability.WORKSPACE_BINDING) is CapabilityStatus.NATIVE

    for cap, record in caps.records.items():
        if cap is not Capability.WORKSPACE_BINDING:
            assert record.status is CapabilityStatus.UNKNOWN
        assert HONEST_LIMITATION in record.limitations

    eff = effective_capabilities(caps, (), host_version="0.45.0", now=TODAY)
    assert eff.status(Capability.HEADLESS_EXECUTION) is CapabilityStatus.UNKNOWN
    assert eff.status(Capability.CONFIG_ISOLATION) is CapabilityStatus.UNKNOWN

    custom_bin = _write_executable(tmp_path / "bin" / "my-cursor-agent", "#!/bin/sh\nexit 0\n")
    ctx = SimpleNamespace(config={"runtimes.binaries": {"cursor": str(custom_bin)}})
    for key in ("cursor", "cursor-agent"):
        built = RUNTIME_FACTORIES[key](ctx, environ={})
        assert isinstance(built, CursorRuntime)
        assert built.runtime_id == "cursor"

    cursor_specs = [s for s in BUILTIN_COMPONENTS if s.kind is ComponentKind.RUNTIME and s.key == "cursor"]
    assert len(cursor_specs) == 1
    assert component_problem(cursor_specs[0], RUNTIME_FACTORIES["cursor"](environ={})) is None


def test_cursor_detection_probe_6tuple_cache_and_synthetic_fixture(tmp_path: Path) -> None:
    fixture_lines = [
        json.loads(line)
        for line in (FIXTURES_DIR / "synthetic_protocol_probe.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert all(item["provenance"] == "synthetic" for item in fixture_lines)
    assert fixture_lines[0]["verified"] is False
    probe_stdout = str(fixture_lines[1]["stdout"])

    binary = _write_executable(tmp_path / "bin" / DEFAULT_CURSOR_BINARY, "#!/bin/sh\nexit 0\n")
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...], *, env: object, timeout_seconds: float) -> CommandOutput:
        del env, timeout_seconds
        calls.append(argv)
        return CommandOutput(0, probe_stdout, "")

    kernel_val = "Linux:6.8.0"
    detector = CursorDetector(run_cmd=runner, os_kernel_fn=lambda: kernel_val)
    digest = compute_launch_config_digest(adapter_version="0.1.0")

    p1 = detector.probe(
        binary=DEFAULT_CURSOR_BINARY,
        environ={"PATH": str(binary.parent)},
        env_allowlist=(),
        adapter_version="0.1.0",
        launch_config_digest=digest,
    )
    p2 = detector.probe(
        binary=DEFAULT_CURSOR_BINARY,
        environ={"PATH": str(binary.parent)},
        env_allowlist=(),
        adapter_version="0.1.0",
        launch_config_digest=digest,
    )
    assert p1 is p2
    assert p1.version == "0.45.0"
    assert len(calls) == 1

    runtime = CursorRuntime(
        environ={"PATH": str(binary.parent)},
        probe_runner=runner,
        os_kernel_fn=lambda: kernel_val,
    )
    inst = runtime.detect(DetectProbe(host_id=HOST_1, binary=None, env_allowlist=(), timeout_seconds=10))
    assert inst.runtime_id == "cursor"
    assert inst.version == "0.45.0"
    assert inst.auth_state is AuthState.UNKNOWN
    assert inst.details["headless_contract"] == "unknown"

    missing_rt = CursorRuntime(binary="/nonexistent/cursor-agent", environ={})
    with pytest.raises(FileNotFoundError):
        missing_rt.detect(DetectProbe(host_id=HOST_1, binary=None, env_allowlist=(), timeout_seconds=10))


def test_cursor_excluded_by_routing_and_start_fails_closed(tmp_path: Path) -> None:
    runtime = CursorRuntime(environ={})
    req = _make_cursor_request(tmp_path)

    sources = runtime.self_loaded_context(req)
    assert {s.kind for s in sources} == {
        SelfLoadKind.PROJECT_SETTINGS,
        SelfLoadKind.PROJECT_INSTRUCTIONS,
        SelfLoadKind.USER_CONFIG,
    }

    with pytest.raises(CapabilityUnavailable) as start_err:
        runtime.start(req)
    assert start_err.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert start_err.value.details == {"capability": "headless_execution", "runtime_id": "cursor"}

    fake_handle = SessionHandle(
        runtime_id="cursor",
        request_id=req.request_id,
        pid=None,
        process_start_ticks=None,
        started_at=NOW,
        ownership=ProcessOwnership(req.process_owner, "pgroup_best_effort", "cursor/none"),
    )
    with pytest.raises(ValueError, match="CursorRuntime"):
        list(runtime.events(fake_handle))
    with pytest.raises(ValueError, match="CursorRuntime"):
        runtime.cancel(fake_handle, grace_seconds=1.0)
    with pytest.raises(ValueError, match="CursorRuntime"):
        runtime.result(fake_handle)

    eff_caps = effective_capabilities(runtime.capabilities(), (), host_version="0.45.0", now=TODAY)
    cursor_entry = RuntimeCatalogEntry(
        runtime_id="cursor",
        class_selectors=MappingProxyType({ModelClass.IMPLEMENTATION: ("cursor-default",)}),
        effort_selectors=MappingProxyType({Effort.MEDIUM: "medium", Effort.HIGH: "high"}),
        models=(
            ModelEntry(
                runtime_id="cursor",
                id="cursor-default",
                display_name="Cursor Default",
                classes=frozenset({ModelClass.IMPLEMENTATION}),
                suited_roles=frozenset({RoleId.EXECUTOR, RoleId.REVIEWER, RoleId.RESEARCHER}),
                context_window_tokens=128_000,
                max_output_tokens=16_000,
                patterns=(),
                pricing=None,
                status=ModelStatus.CONFIRMED,
                verified_at=TODAY,
                source="test",
                notes="",
            ),
        ),
    )
    catalog = ModelCatalog(
        catalog_version="1.0.0",
        resource_version_ids=(),
        digest=DIGEST,
        runtimes={"cursor": cursor_entry},
    )
    installs = {
        "cursor": RuntimeInstallation(
            host_id=HOST_1,
            runtime_id="cursor",
            version="0.45.0",
            binary_locator="/usr/bin/cursor-agent",
            auth_state=AuthState.OK,
            detected_at=NOW,
            details={},
        )
    }
    admission = admit(
        AdmissionFacts(
            operation=Operation.NEW_IMPLEMENTATION,
            role=RoleId.EXECUTOR,
            task_min_class=None,
            task_min_effort=None,
            started_by=None,
            previous=None,
            contract_digest=DIGEST,
            previous_contract_digest=None,
            fix_brief=None,
            previous_output_id=None,
        ),
        ADMISSION_DEFAULTS,
    )
    cfg = RouteConfig(
        allowed=frozenset({"cursor"}),
        preference=("cursor",),
        role_routing={},
        degraded_allow=frozenset(),
        config_isolation_required=False,
    )
    route_req = RouteRequest(
        role=RoleId.EXECUTOR,
        required_capabilities=frozenset({Capability.HEADLESS_EXECUTION}),
        optional_capabilities=frozenset(),
        model_class=ModelClass.IMPLEMENTATION,
        effort=Effort.MEDIUM,
        explicit_runtime="cursor",
        explicit_model=None,
        host_id=HOST_1,
        admission=admission,
        config_mode="inherit",
        excluded_routes=frozenset(),
        network_read_only=False,
        policy_profile="trusted-full-access",
    )
    with pytest.raises(CapabilityUnavailable) as route_err:
        route(route_req, cfg, catalog, {"cursor": eff_caps}, installs, frozenset({"cursor"}))
    assert route_err.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
