"""AgentRequest invariants, host-only process ownership and redaction (runtimes §4.5, §6)."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, SkmError, ValidationFailed
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    RuntimeCapabilities,
    SelfLoadKind,
    StaticCapabilityCatalog,
    parse_capabilities,
)
from skm.modules.runtimes.domain.classes import Effort, RoleId
from skm.modules.runtimes.domain.error_rules import ErrorClass, ErrorRule, ErrorScope
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
    request_to_json,
    validate_request,
)
from skm.modules.runtimes.ports import SessionHandle
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
URN = "urn:skm:runtimes:agent-request:v1"
STEP = "0193a7c2-5b10-7c11-8a00-3f1e2d4c5b6a"
WORKDIR = "/srv/skm/worktrees/attempt-1/main"
CLIENT_HOME = "/srv/skm/client-homes/attempt-1/claude_code"
TOKEN = "skm_at_" + "z" * 40
NONCE = "nonce-0123456789abcdef"
IDENTITY_DIR = "/srv/skm/owners/0193a7c2"


@cache
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def owner(unit_kind: Any = "step", unit_id: str = STEP) -> ProcessOwner:
    return ProcessOwner(
        host_id=UUID("0193a7c2-0000-7000-8000-000000000001"),
        worker_id=UUID("0193a7c2-0000-7000-8000-000000000002"),
        attempt_id=UUID("0193a7c2-0000-7000-8000-000000000003"),
        stage_record_id=UUID("0193a7c2-0000-7000-8000-000000000004"),
        unit_kind=unit_kind,
        unit_id=UUID(unit_id),
        owner_nonce=NONCE,
        identity_dir=IDENTITY_DIR,
    )


def grant(*roots: str) -> PermissionGrant:
    rules = PathRules(allow=tuple(PathRule(root, "**") for root in roots or (WORKDIR,)), deny=())
    return PermissionGrant(
        fs_read=rules,
        fs_write=PathRules(allow=(PathRule(WORKDIR, "src/**"),), deny=(PathRule(WORKDIR, ".git/**"),)),
        commands=CommandRules("denylist", (), ("sudo",), ()),
        network=NetworkRules("none", ()),
        tools=frozenset({"fs.read", "fs.write"}),
        external_effects=frozenset(),
    )


def request(**changes: Any) -> AgentRequest:
    base = AgentRequest(
        request_id=STEP,
        runtime_id="claude_code",
        model="sonnet",
        effort=Effort.HIGH,
        role=RoleId.EXECUTOR,
        rendered_prompt="## Task\nDo the work.",
        prompt_digest="sha256:" + "5" * 64,
        result_format=ResultFormat.JSON,
        result_schema_urn="urn:skm:execution:role-result:executor:v1",
        workdir=WORKDIR,
        permissions=grant(),
        isolation_profile=IsolationProfile.WORKTREE,
        process_owner=owner(),
        config_mode="isolated",
        client_home=CLIENT_HOME,
        resume_session_ref=None,
        session_policy="persistent",
        env_allowlist=("PATH", "LANG"),
        extra_env={"SKM_STEP_ID": STEP},
        secret_env={"SKM_TOKEN": SecretStr(TOKEN)},
        mcp_servers=(McpServerSpec("skm", ("skm", "mcp"), {}, ("SKM_TOKEN",)),),
        limits=RuntimeLimits(1800, 900, None, None, 64 * 1024 * 1024),
        labels={"step_id": STEP, "attempt_id": "0193a7c2-0000-7000-8000-000000000003"},
    )
    return dataclasses.replace(base, **changes)


def caps(resume: CapabilityStatus = CapabilityStatus.NATIVE) -> RuntimeCapabilities:
    record = CapabilityRecord(Capability.SESSION_RESUME, resume, "fixture:test", None, "", None)
    return RuntimeCapabilities("claude_code", "0.1.0", {Capability.SESSION_RESUME: record}, (), True, None)


def refusal(req: AgentRequest, capabilities: RuntimeCapabilities | None = None) -> SkmError:
    with pytest.raises(SkmError) as info:
        validate_request(req, capabilities or caps())
    return info.value


def test_valid_request_passes_and_serializes_to_the_schema_with_redacted_secret() -> None:
    req = request()
    validate_request(req, caps())
    encoded = request_to_json(req)
    assert registry().validate(URN, encoded) == ()
    assert encoded["secret_env"] == {"SKM_TOKEN": "***"}
    assert TOKEN not in json.dumps(encoded)


def test_example_request_matches_the_schema() -> None:
    sample = json.loads((ROOT / "tests/fixtures/corpus/examples/runtimes/agent-request.json").read_text())
    assert registry().validate(URN, sample) == ()


def test_repr_never_contains_secret_or_owner_nonce() -> None:
    text = repr(request())
    assert TOKEN not in text
    assert NONCE not in text
    assert TOKEN not in repr(SecretStr(TOKEN))
    assert str(SecretStr(TOKEN)) == "***"
    assert NONCE not in repr(owner())


def test_secret_env_accepts_only_skm_token() -> None:
    error = refusal(request(secret_env={"SKM_TOKEN": SecretStr(TOKEN), "GITHUB_TOKEN": SecretStr("x")}))
    assert error.code is ErrorCode.RUNTIME_INVALID_REQUEST
    assert error.details["reason"] == "secret_env_not_allowed"


@pytest.mark.parametrize(
    "changes",
    [{"extra_env": {"SKM_TOKEN": "literal"}}, {"env_allowlist": ("PATH", "SKM_TOKEN")}],
    ids=["extra_env", "env_allowlist"],
)
def test_secret_names_do_not_overlap_plain_env(changes: dict[str, Any]) -> None:
    error = refusal(request(**changes))
    assert error.code is ErrorCode.RUNTIME_INVALID_REQUEST
    assert error.details["reason"] == "secret_env_conflict"


def test_mcp_secret_names_must_be_provided() -> None:
    error = refusal(request(secret_env={}))
    assert error.code is ErrorCode.RUNTIME_INVALID_REQUEST
    assert error.details["reason"] == "mcp_secret_missing"


@pytest.mark.parametrize(
    "changes",
    [
        {"rendered_prompt": f"token {TOKEN}"},
        {"labels": {"step_id": TOKEN}},
        {"extra_env": {"SKM_RUN": TOKEN}},
    ],
    ids=["prompt", "labels", "extra_env"],
)
def test_secret_value_never_appears_in_visible_fields(changes: dict[str, Any]) -> None:
    error = refusal(request(**changes))
    assert error.details["reason"] == "secret_exposed"
    assert TOKEN not in str(error)


def mcp(**changes: Any) -> tuple[McpServerSpec, ...]:
    base = McpServerSpec("skm", ("skm", "mcp"), {}, ("SKM_TOKEN",))
    return (dataclasses.replace(base, **changes),)


DUPLICATED_SECRET = [
    {"mcp_servers": mcp(command=("skm", "mcp", TOKEN))},
    {"mcp_servers": mcp(command=("skm", "mcp", f"--token={TOKEN}"))},
    {"mcp_servers": mcp(name=f"skm-{TOKEN}")},
    {"mcp_servers": mcp(env={"SKM_AUTH": TOKEN})},
    {"mcp_servers": mcp(env={f"X_{TOKEN}": "secret://env/X"})},
    {"labels": {f"k{TOKEN}": "v"}},
    {"model": f"sonnet-{TOKEN}"},
    {"permissions": dataclasses.replace(grant(), network=NetworkRules("allowlist", (f"{TOKEN}.example",)))},
]
DUPLICATED_IDS = [
    "mcp-argv-arg",
    "mcp-argv-inside-arg",
    "mcp-name",
    "mcp-env-value",
    "mcp-env-key",
    "label-key",
    "model",
    "permission-host",
]


@pytest.mark.parametrize("changes", DUPLICATED_SECRET, ids=DUPLICATED_IDS)
def test_secret_duplicated_into_any_open_field_is_refused(changes: dict[str, Any]) -> None:
    error = refusal(request(**changes))
    assert error.code is ErrorCode.RUNTIME_INVALID_REQUEST
    assert error.details["reason"] == "secret_exposed"
    assert TOKEN not in str(error)
    assert TOKEN not in json.dumps(dict(error.details))


@pytest.mark.parametrize("changes", DUPLICATED_SECRET, ids=DUPLICATED_IDS)
def test_repr_and_json_mask_a_duplicated_secret_before_validation(changes: dict[str, Any]) -> None:
    req = request(**changes)
    assert TOKEN not in repr(req)
    assert TOKEN not in json.dumps(request_to_json(req))


def test_masking_survives_repr_escaping_and_keeps_safe_fields() -> None:
    token = "tok'en\"\n" + "q" * 20
    req = request(
        secret_env={"SKM_TOKEN": SecretStr(token)},
        mcp_servers=mcp(command=("skm", f"a'{token}")),
    )
    text = repr(req)
    assert token not in text
    assert repr(token)[1:-1] not in text
    assert "'skm'" in text
    encoded = request_to_json(req)
    assert encoded["mcp_servers"] == [
        {"name": "skm", "command": ["skm", "a'***"], "env": {}, "secret_env_names": ["SKM_TOKEN"]}
    ]


def test_skm_token_passes_by_name_to_mcp_servers() -> None:
    servers = mcp(command=("skm", "mcp", "--stdio"), env={"SKM_URL": "secret://env/SKM_URL"})
    req = request(mcp_servers=servers)
    validate_request(req, caps())
    encoded = request_to_json(req)
    assert registry().validate(URN, encoded) == ()
    assert encoded["mcp_servers"] == [
        {
            "name": "skm",
            "command": ["skm", "mcp", "--stdio"],
            "env": {"SKM_URL": "secret://env/SKM_URL"},
            "secret_env_names": ["SKM_TOKEN"],
        }
    ]
    assert req.secret_env["SKM_TOKEN"].reveal() == TOKEN


@pytest.mark.parametrize(
    "changes",
    [{"rendered_prompt": f"see {IDENTITY_DIR}"}, {"labels": {"nonce": NONCE}}],
    ids=["identity_dir-in-prompt", "nonce-in-labels"],
)
def test_process_owner_metadata_stays_out_of_model_context_and_labels(changes: dict[str, Any]) -> None:
    assert refusal(request(**changes)).details["reason"] == "owner_exposed"


def test_resume_needs_persistent_session_and_the_capability() -> None:
    ephemeral = refusal(request(resume_session_ref="ref-1", session_policy="ephemeral"))
    assert ephemeral.code is ErrorCode.SCHEMA_INVALID
    assert ephemeral.details["reason"] == "resume_requires_persistent"
    unsupported = refusal(request(resume_session_ref="ref-1"), caps(CapabilityStatus.UNSUPPORTED))
    assert isinstance(unsupported, CapabilityUnavailable)
    assert unsupported.details["capability"] == "session_resume"
    missing = RuntimeCapabilities("claude_code", "0.1.0", {}, (), True, None)
    assert isinstance(refusal(request(resume_session_ref="ref-1"), missing), CapabilityUnavailable)
    validate_request(request(resume_session_ref="ref-1"), caps(CapabilityStatus.ADAPTED))


@pytest.mark.parametrize(
    "root",
    [
        "/srv/skm/worktrees/attempt-1",
        "/srv/skm/worktrees/attempt-1/main-other",
        f"{WORKDIR}/../escape",
        "/home/dev/.claude",
    ],
)
def test_file_grants_stay_inside_the_worktree(root: str) -> None:
    error = refusal(request(permissions=grant(WORKDIR, root)))
    assert error.code is ErrorCode.RUNTIME_INVALID_REQUEST
    assert error.details["reason"] == "grant_outside_worktree"


def test_nested_grants_inside_the_worktree_are_allowed() -> None:
    validate_request(request(permissions=grant(f"{WORKDIR}/src", WORKDIR)), caps())


def test_client_home_iff_isolated_and_outside_the_worktree() -> None:
    assert refusal(request(client_home=None)).details["reason"] == "client_home_mismatch"
    assert refusal(request(config_mode="inherit")).details["reason"] == "client_home_mismatch"
    validate_request(request(config_mode="inherit", client_home=None), caps())
    inside = refusal(request(client_home=f"{WORKDIR}/.home"))
    assert inside.details["reason"] == "client_home_inside_worktree"


def test_json_result_needs_its_schema_and_workdir_is_absolute() -> None:
    assert refusal(request(result_schema_urn=None)).details["reason"] == "result_schema_missing"
    validate_request(request(result_format=ResultFormat.TEXT, result_schema_urn=None), caps())
    assert refusal(request(workdir="worktrees/main")).details["reason"] == "workdir_not_absolute"


def test_request_id_is_the_step_and_owns_the_process() -> None:
    assert refusal(request(request_id="step-1")).details["reason"] == "request_id_not_uuid"
    other = "0193a7c2-5b10-7c11-8a00-ffffffffffff"
    assert refusal(request(process_owner=owner(unit_id=other))).details["reason"] == "process_owner_mismatch"
    check_owner = owner("check", other)
    assert refusal(request(process_owner=check_owner)).details["reason"] == "process_owner_mismatch"


def test_runtime_id_is_open_but_patterned_and_capabilities_must_match() -> None:
    plugin_caps = RuntimeCapabilities("acme_agent", "1.0", {}, (), False, None)
    validate_request(request(runtime_id="acme_agent"), plugin_caps)
    assert refusal(request(runtime_id="Acme-Agent"), plugin_caps).details["reason"] == "capabilities_mismatch"
    with pytest.raises(ValueError, match="runtime id"):
        RuntimeCapabilities("Acme-Agent", "1.0", {}, (), False, None)


@pytest.mark.parametrize("profile", ["none", "worktree", "landlock", "container", "acme.sandbox:strict"])
def test_isolation_is_four_builtins_plus_plugin_keys(profile: str) -> None:
    req = request(isolation_profile=profile)
    validate_request(req, caps())
    assert registry().validate(URN, request_to_json(req)) == ()


@pytest.mark.parametrize("profile", ["trusted", "read_only", "Acme:x", "acme:"])
def test_unknown_isolation_profiles_are_refused(profile: str) -> None:
    with pytest.raises(ValueError, match="isolation profile"):
        request(isolation_profile=profile)


def test_roles_are_exactly_seven() -> None:
    assert [role.value for role in RoleId] == [
        "scout",
        "executor",
        "reviewer",
        "triager",
        "advisor",
        "researcher",
        "registrar",
    ]
    with pytest.raises(ValueError, match="report_fixer"):
        request(role="report_fixer")


def test_process_owner_kinds_for_steps_checks_and_git_effects() -> None:
    effect = "0193a7c2-9999-7000-8000-000000000009"
    for kind in ("step", "check", "git_effect"):
        assert owner(kind, effect).unit_kind == kind
    with pytest.raises(ValueError, match="unit_kind"):
        owner("review")
    with pytest.raises(ValueError, match="owner_nonce"):
        dataclasses.replace(owner(), owner_nonce="short")
    with pytest.raises(TypeError, match="UUID"):
        dataclasses.replace(owner(), unit_id=STEP)


def test_ownership_carries_a_durable_backend_ref() -> None:
    ownership = ProcessOwnership(owner(), "cgroup", "/sys/fs/cgroup/skm/step-1")
    assert ownership.daemon_identity is None
    with pytest.raises(ValueError, match="daemon identity"):
        ProcessOwnership(owner(), "container", "c0ffee")
    ProcessOwnership(owner(), "container", "c0ffee", daemon_identity="docker:sha256:abc")
    with pytest.raises(ValueError, match="ref"):
        ProcessOwnership(owner(), "pgroup_best_effort", "")


def test_session_handle_returns_the_actual_ownership_of_its_step() -> None:
    ownership = ProcessOwnership(owner(), "cgroup", "/sys/fs/cgroup/skm/step-1")
    started = datetime(2026, 10, 25, 14, 0, tzinfo=UTC)
    handle = SessionHandle("claude_code", STEP, 4242, 991, started, ownership)
    assert handle.ownership is ownership
    SessionHandle("fake", STEP, None, None, started, None)  # in-process runtime: no child
    check = ProcessOwnership(owner("check"), "cgroup", "/sys/fs/cgroup/skm/check-1")
    with pytest.raises(ValueError, match="owned by its step"):
        SessionHandle("claude_code", STEP, 4242, 991, started, check)
    with pytest.raises(ValueError, match="UTC"):
        SessionHandle("claude_code", STEP, 4242, 991, datetime(2026, 1, 1), ownership)  # noqa: DTZ001


def test_validation_failures_are_typed_errors() -> None:
    error = refusal(request(result_schema_urn=None))
    assert isinstance(error, ValidationFailed)


# Static capabilities registry: data only, no adapter implementation imported.

CAPABILITIES_DOC: dict[str, Any] = {
    "runtime_id": "acme_agent",
    "adapter_version": "1.0.0",
    "records": [
        {
            "capability": "session_resume",
            "status": "native",
            "evidence": "fixture:acme/resume.jsonl",
            "tested_runtime_version": "2.0.0",
            "limitations": "",
            "last_verified_at": "2026-10-01",
        },
        {
            "capability": "config_isolation",
            "status": "unsupported",
            "evidence": "docs:acme",
            "tested_runtime_version": None,
            "limitations": "project settings are always read",
            "last_verified_at": None,
            "verification_context": None,
        },
    ],
    "self_loads": [
        {
            "kind": "project_settings",
            "locator": "<workdir>/.acme/",
            "files": [],
            "when": "start",
            "suppressed_by": "never",
            "note": "",
        }
    ],
    "read_only_network": False,
    "config_isolation": {
        "env": {"ACME_HOME": "{client_home}"},
        "args": [],
        "credential_mounts": [{"source": "~/.acme/auth.json", "target": "auth.json", "required": True}],
        "writable_home_dirs": [],
    },
}


def test_capabilities_document_parses_into_runtime_capabilities() -> None:
    assert registry().validate("urn:skm:runtimes:capabilities:v1", CAPABILITIES_DOC) == ()
    parsed = parse_capabilities(CAPABILITIES_DOC)
    assert parsed.status(Capability.SESSION_RESUME) is CapabilityStatus.NATIVE
    assert parsed.supports(Capability.SESSION_RESUME)
    assert not parsed.supports(Capability.CONFIG_ISOLATION)
    assert (
        parsed.status(Capability.MCP_SUPPORT) is CapabilityStatus.UNKNOWN
    )  # missing is unknown, not success
    assert not parsed.supports(Capability.MCP_SUPPORT)
    assert parsed.self_loads[0].kind is SelfLoadKind.PROJECT_SETTINGS
    assert parsed.config_isolation is not None
    assert parsed.config_isolation.credential_mounts[0].required is True
    twice = CAPABILITIES_DOC | {"records": CAPABILITIES_DOC["records"][:1] * 2}
    with pytest.raises(ValidationFailed, match="declared twice"):
        parse_capabilities(twice)


def test_static_catalog_serves_registered_runtimes_only() -> None:
    caps_ = parse_capabilities(CAPABILITIES_DOC)
    rule = ErrorRule(
        "acme_agent",
        ErrorClass.QUOTA,
        ErrorCode.QUOTA_EXHAUSTED,
        ErrorScope.ACCOUNT,
        {},
        {},
        ("quota",),
        None,
        None,
        None,
    )
    catalog = StaticCapabilityCatalog({"acme_agent": caps_}, {"acme_agent": (rule,)})
    assert catalog.registered() == frozenset({"acme_agent"})
    assert catalog.static("acme_agent") is caps_
    assert catalog.error_rules("acme_agent") == (rule,)
    assert StaticCapabilityCatalog({"acme_agent": caps_}, {}).error_rules("acme_agent") == ()
    with pytest.raises(SkmError) as info:
        catalog.static("claude_code")
    assert info.value.code is ErrorCode.NOT_FOUND
    assert info.value.details["kind"] == "runtime"
    with pytest.raises(ValueError, match="filed under"):
        StaticCapabilityCatalog({"other_agent": caps_}, {})
    with pytest.raises(ValueError, match="unregistered"):
        StaticCapabilityCatalog({"acme_agent": caps_}, {"codex": ()})


def test_capability_records_are_filed_under_their_capability() -> None:
    record = CapabilityRecord(Capability.MCP_SUPPORT, CapabilityStatus.NATIVE, "x", None, "", None)
    with pytest.raises(ValueError, match="filed under"):
        RuntimeCapabilities("acme_agent", "1", {Capability.SESSION_RESUME: record}, (), False, None)
