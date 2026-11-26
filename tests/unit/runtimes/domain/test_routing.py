"""Unit & property tests for deterministic routing and candidate filtering (runtimes §4.10, §4.11)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, PreconditionFailed
from skm.kernel.ids import HostId
from skm.modules.runtimes.domain.admission import (
    ADMISSION_DEFAULTS,
    Admission,
    AdmissionFacts,
    Operation,
    PreviousRoute,
    ResumePolicy,
    admit,
)
from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    RuntimeCapabilities,
    SelfLoad,
    SelfLoadKind,
)
from skm.modules.runtimes.domain.catalog import (
    ModelCatalog,
    ModelEntry,
    ModelStatus,
    RuntimeCatalogEntry,
)
from skm.modules.runtimes.domain.classes import Effort, ModelClass, RoleId
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.domain.routing import (
    RouteConfig,
    RouteRequest,
    route,
)

HOST_1 = HostId(UUID("0193a6f0-0100-7a00-8000-9a8b7c6d5e4f"))
TODAY = date(2026, 11, 10)
NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


def make_model(
    runtime_id: str,
    model_id: str,
    classes: tuple[ModelClass, ...],
    *,
    status: ModelStatus = ModelStatus.CONFIRMED,
    window: int = 200_000,
) -> ModelEntry:
    return ModelEntry(
        runtime_id=runtime_id,
        id=model_id,
        display_name=model_id,
        classes=frozenset(classes),
        suited_roles=frozenset({RoleId.EXECUTOR, RoleId.RESEARCHER, RoleId.REVIEWER}),
        context_window_tokens=window,
        max_output_tokens=16_000,
        patterns=(),
        pricing=None,
        status=status,
        verified_at=TODAY,
        source="test",
        notes="",
    )


def make_catalog() -> ModelCatalog:
    claude = RuntimeCatalogEntry(
        runtime_id="claude_code",
        class_selectors=MappingProxyType(
            {
                ModelClass.ECONOMY: ("haiku",),
                ModelClass.IMPLEMENTATION: ("sonnet",),
                ModelClass.FRONTIER: ("opus",),
            }
        ),
        effort_selectors=MappingProxyType(
            {Effort.LOW: "low", Effort.MEDIUM: "medium", Effort.HIGH: "high", Effort.XHIGH: "xhigh"}
        ),
        models=(
            make_model("claude_code", "haiku", (ModelClass.ECONOMY,), window=200_000),
            make_model("claude_code", "sonnet", (ModelClass.IMPLEMENTATION,), window=200_000),
            make_model(
                "claude_code", "opus", (ModelClass.IMPLEMENTATION, ModelClass.FRONTIER), window=200_000
            ),
            make_model(
                "claude_code", "old-sonnet", (ModelClass.IMPLEMENTATION,), status=ModelStatus.DEPRECATED
            ),
        ),
    )
    codex = RuntimeCatalogEntry(
        runtime_id="codex",
        class_selectors=MappingProxyType(
            {
                ModelClass.ECONOMY: ("gpt-6-luna",),
                ModelClass.IMPLEMENTATION: ("gpt-6-sol",),
                ModelClass.FRONTIER: ("gpt-6-astra",),
            }
        ),
        effort_selectors=MappingProxyType(
            {Effort.LOW: "low", Effort.MEDIUM: "medium", Effort.HIGH: "high", Effort.XHIGH: "xhigh"}
        ),
        models=(
            make_model("codex", "gpt-6-luna", (ModelClass.ECONOMY,), window=128_000),
            make_model("codex", "gpt-6-sol", (ModelClass.IMPLEMENTATION,), window=128_000),
            make_model(
                "codex", "gpt-6-astra", (ModelClass.IMPLEMENTATION, ModelClass.FRONTIER), window=128_000
            ),
        ),
    )
    grok = RuntimeCatalogEntry(
        runtime_id="grok",
        class_selectors=MappingProxyType({ModelClass.ECONOMY: ("grok-4.5",)}),
        effort_selectors=MappingProxyType({Effort.MEDIUM: "medium", Effort.HIGH: "high"}),
        models=(make_model("grok", "grok-4.5", (ModelClass.ECONOMY,), window=128_000),),
    )
    return ModelCatalog(
        catalog_version="2.0.0",
        resource_version_ids=(),
        digest=DIGEST,
        runtimes={"claude_code": claude, "codex": codex, "grok": grok},
    )


def make_caps(
    runtime_id: str,
    *,
    supported: tuple[Capability, ...] = (
        Capability.CONFIG_ISOLATION,
        Capability.SESSION_RESUME,
        Capability.EFFORT_CONTROL,
    ),
    unknown: tuple[Capability, ...] = (),
    read_only_network: bool = True,
    self_loads: tuple[SelfLoad, ...] = (),
) -> RuntimeCapabilities:
    records: dict[Capability, CapabilityRecord] = {}
    for cap in supported:
        records[cap] = CapabilityRecord(
            capability=cap,
            status=CapabilityStatus.NATIVE,
            evidence="verified",
            tested_runtime_version="1.0.0",
            limitations="",
            last_verified_at=TODAY,
        )
    for cap in unknown:
        records[cap] = CapabilityRecord(
            capability=cap,
            status=CapabilityStatus.UNKNOWN,
            evidence="unverified",
            tested_runtime_version="1.0.0",
            limitations="unverified",
            last_verified_at=TODAY,
        )
    return RuntimeCapabilities(
        runtime_id=runtime_id,
        adapter_version="2.0.0",
        records=records,
        self_loads=self_loads,
        read_only_network=read_only_network,
        config_isolation=None,
    )


def make_install(runtime_id: str, auth: AuthState = AuthState.OK) -> RuntimeInstallation:
    return RuntimeInstallation(
        host_id=HOST_1,
        runtime_id=runtime_id,
        version="1.0.0",
        binary_locator=f"/usr/local/bin/{runtime_id}",
        auth_state=auth,
        detected_at=NOW,
        details={},
    )


def base_admission(
    op: Operation = Operation.NEW_IMPLEMENTATION,
    role: RoleId = RoleId.EXECUTOR,
    *,
    previous: PreviousRoute | None = None,
    task_min_effort: Effort | None = None,
) -> Admission:
    return admit(
        AdmissionFacts(
            operation=op,
            role=role,
            task_min_class=None,
            task_min_effort=task_min_effort,
            started_by=previous,
            previous=previous,
            contract_digest=DIGEST,
            previous_contract_digest=DIGEST if previous is not None else None,
            fix_brief=None,
            previous_output_id="out-1" if op in (Operation.REVIEW, Operation.FINAL_CLOSE) else None,
        ),
        ADMISSION_DEFAULTS,
    )


def make_req(**overrides: Any) -> RouteRequest:
    req = RouteRequest(
        role=RoleId.EXECUTOR,
        required_capabilities=frozenset(),
        optional_capabilities=frozenset(),
        model_class=ModelClass.IMPLEMENTATION,
        effort=Effort.MEDIUM,
        explicit_runtime=None,
        explicit_model=None,
        host_id=HOST_1,
        admission=base_admission(),
        config_mode="isolated",
        excluded_routes=frozenset(),
        network_read_only=False,
    )
    return replace(req, **overrides)


def make_cfg(**overrides: Any) -> RouteConfig:
    cfg = RouteConfig(
        allowed=frozenset({"claude_code", "codex", "grok"}),
        preference=("claude_code", "codex", "grok"),
        role_routing={},
        degraded_allow=frozenset(),
        config_isolation_required=True,
        unknown_model="warn",
    )
    return replace(cfg, **overrides)


def test_candidate_precedence_previous_over_plan_over_role_over_fallback_over_preference() -> None:
    cat = make_catalog()
    caps = {r: make_caps(r) for r in ("claude_code", "codex", "grok")}
    installs = {r: make_install(r) for r in ("claude_code", "codex", "grok")}
    reg = frozenset({"claude_code", "codex", "grok"})

    prev = PreviousRoute("codex", "gpt-6-sol", ModelClass.IMPLEMENTATION, Effort.HIGH, "sess-1", "step-1")
    adm_cont = base_admission(Operation.CONTINUATION, previous=prev)
    cfg = make_cfg(
        preference=("claude_code", "codex"),
        role_routing={
            RoleId.EXECUTOR: {
                "runtime": "grok",
                "fallback": [{"runtime": "claude_code"}],
            }
        },
    )

    # 1. previous_route wins first
    d_prev = route(make_req(admission=adm_cont), cfg, cat, caps, installs, reg)
    assert (d_prev.source, d_prev.runtime_id, d_prev.model) == ("previous_route", "codex", "gpt-6-sol")

    # 2. If previous_route is excluded_by_retry, explicit plan_route wins when set
    d_plan = route(
        make_req(
            admission=adm_cont,
            excluded_routes=frozenset({("codex", "gpt-6-sol")}),
            explicit_runtime="claude_code",
            explicit_model="opus",
            effort=Effort.HIGH,
        ),
        cfg,
        cat,
        caps,
        installs,
        reg,
    )
    assert (d_plan.source, d_plan.runtime_id, d_plan.model) == ("plan_route", "claude_code", "opus")
    assert d_plan.rejected[0].reason == "excluded_by_retry"

    # 3. Without explicit plan_route: role_routing tries grok (no_model_for_class), then role_fallback!
    d_fb = route(
        make_req(admission=adm_cont, excluded_routes=frozenset({("codex", "gpt-6-sol")})),
        cfg,
        cat,
        caps,
        installs,
        reg,
    )
    assert (d_fb.source, d_fb.runtime_id, d_fb.model) == ("role_fallback", "claude_code", "sonnet")
    assert [r.reason for r in d_fb.rejected] == ["excluded_by_retry", "no_model_for_class"]

    # 4. Without role_routing: preference order selects first allowed runtime
    d_pref = route(make_req(), make_cfg(preference=("codex", "claude_code")), cat, caps, installs, reg)
    assert (d_pref.source, d_pref.runtime_id, d_pref.model) == ("preference", "codex", "gpt-6-sol")


def test_every_rejection_reason_and_project_settings_fail_closed() -> None:
    cat = make_catalog()
    unsupp_proj_settings = SelfLoad(
        kind=SelfLoadKind.PROJECT_SETTINGS,
        locator="<workdir>/.cursor/mcp.json",
        files=(".cursor/mcp.json",),
        when="start",
        suppressed_by="never",
        note="",
    )
    caps = {
        "claude_code": make_caps("claude_code", read_only_network=False),
        "codex": make_caps(
            "codex",
            supported=(Capability.CONFIG_ISOLATION, Capability.EFFORT_CONTROL),
            unknown=(Capability.MCP_SUPPORT,),
        ),
        "grok": make_caps("grok", self_loads=(unsupp_proj_settings,)),
    }
    installs = {
        "claude_code": make_install("claude_code", AuthState.OK),
        "codex": make_install("codex", AuthState.EXPIRED),
    }

    # Gate checks: not_allowed, not_registered, read_only_network_unsupported,
    # project_settings_not_suppressible, auth_expired, not_installed
    cfg = make_cfg(
        allowed=frozenset({"claude_code", "codex", "grok", "unregistered_rt"}),
        role_routing={
            RoleId.RESEARCHER: {
                "runtime": "disallowed_rt",
                "fallback": [
                    {"runtime": "unregistered_rt"},
                    {"runtime": "claude_code"},
                    {"runtime": "grok"},
                    {"runtime": "codex"},
                ],
            }
        },
        config_isolation_required=False,  # Even when false, unsuppressible project_settings MUST be rejected!
        degraded_allow=frozenset({Capability.CONFIG_ISOLATION}),
    )
    req = make_req(
        role=RoleId.RESEARCHER,
        admission=base_admission(Operation.RESEARCH, RoleId.RESEARCHER),
        model_class=ModelClass.ECONOMY,
        network_read_only=True,
    )
    with pytest.raises(CapabilityUnavailable) as exc_info:
        route(req, cfg, cat, caps, installs, frozenset({"claude_code", "codex", "grok"}))
    assert exc_info.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    reasons = [(item["runtime_id"], item["reason"]) for item in exc_info.value.details["rejected"]]  # type: ignore[index]
    assert reasons == [
        ("disallowed_rt", "not_allowed"),
        ("unregistered_rt", "not_registered"),
        ("claude_code", "read_only_network_unsupported"),
        ("grok", "capability_missing:config_isolation"),
        ("codex", "auth_expired"),
    ]

    # Exemption: policy_profile == "trusted-full-access" permits unsuppressible project_settings!
    installs_with_grok = {**installs, "grok": make_install("grok", AuthState.OK)}
    trusted_dec = route(
        replace(req, network_read_only=False, policy_profile="trusted-full-access"),
        make_cfg(preference=("grok",)),
        cat,
        caps,
        installs_with_grok,
        frozenset({"grok"}),
    )
    assert trusted_dec.runtime_id == "grok"


def test_degraded_allow_auth_states_unknown_and_deprecated_models_and_undershoot() -> None:
    cat = make_catalog()
    caps = {
        "codex": make_caps(
            "codex",
            supported=(Capability.CONFIG_ISOLATION, Capability.EFFORT_CONTROL),
            unknown=(Capability.MCP_SUPPORT,),
        ),
        "claude_code": make_caps("claude_code"),
    }

    # auth_missing is rejected; auth_unknown passes with degraded_details=("auth_unknown",)
    with pytest.raises(CapabilityUnavailable) as missing_exc:
        route(
            make_req(explicit_runtime="claude_code"),
            make_cfg(),
            cat,
            caps,
            {"claude_code": make_install("claude_code", AuthState.MISSING)},
            frozenset({"claude_code"}),
        )
    assert missing_exc.value.details["rejected"][0]["reason"] == "auth_missing"  # type: ignore[index]

    # Required unknown capability passes ONLY when in degraded_allow, recorded in decision.degraded
    dec_deg = route(
        make_req(
            explicit_runtime="codex",
            required_capabilities=frozenset({Capability.MCP_SUPPORT}),
        ),
        make_cfg(degraded_allow=frozenset({Capability.MCP_SUPPORT})),
        cat,
        caps,
        {"codex": make_install("codex", AuthState.UNKNOWN)},
        frozenset({"codex"}),
    )
    assert dec_deg.degraded == frozenset({Capability.MCP_SUPPORT})
    assert dec_deg.degraded_details == ("auth_unknown",)

    # Deprecated model -> model_deprecated
    with pytest.raises(CapabilityUnavailable) as dep_exc:
        route(
            make_req(explicit_runtime="claude_code", explicit_model="old-sonnet"),
            make_cfg(),
            cat,
            caps,
            {"claude_code": make_install("claude_code")},
            frozenset({"claude_code"}),
        )
    assert dep_exc.value.details["rejected"][0]["reason"] == "model_deprecated"  # type: ignore[index]

    # Unknown model: accepted at economy under unknown_model="warn"; refused under "refuse"
    eco_req = make_req(
        role=RoleId.RESEARCHER,
        admission=base_admission(Operation.RESEARCH, RoleId.RESEARCHER),
        model_class=ModelClass.ECONOMY,
        explicit_runtime="codex",
        explicit_model="custom-preview-1",
    )
    dec_unk = route(
        eco_req,
        make_cfg(unknown_model="warn"),
        cat,
        caps,
        {"codex": make_install("codex")},
        frozenset({"codex"}),
    )
    assert dec_unk.context_window_tokens == 128_000
    assert "model_unknown" in dec_unk.degraded_details

    with pytest.raises(CapabilityUnavailable) as unk_exc:
        route(
            eco_req,
            make_cfg(unknown_model="refuse"),
            cat,
            caps,
            {"codex": make_install("codex")},
            frozenset({"codex"}),
        )
    assert unk_exc.value.details["rejected"][0]["reason"] == "model_unknown"  # type: ignore[index]

    # Explicit economy model for implementation operation -> class_too_low -> ROUTE_UNDERSHOOT
    with pytest.raises(CapabilityUnavailable) as under_exc:
        route(
            make_req(explicit_runtime="claude_code", explicit_model="haiku"),
            make_cfg(),
            cat,
            caps,
            {"claude_code": make_install("claude_code")},
            frozenset({"claude_code"}),
        )
    assert under_exc.value.code is ErrorCode.ROUTE_UNDERSHOOT

    # Explicit low effort when task requires high effort -> effort_too_low -> ROUTE_UNDERSHOOT
    with pytest.raises(CapabilityUnavailable) as eff_exc:
        route(
            make_req(
                admission=base_admission(Operation.NEW_IMPLEMENTATION, task_min_effort=Effort.HIGH),
                explicit_runtime="claude_code",
                explicit_model="sonnet",
                effort=Effort.LOW,
            ),
            make_cfg(),
            cat,
            caps,
            {"claude_code": make_install("claude_code")},
            frozenset({"claude_code"}),
        )
    assert eff_exc.value.code is ErrorCode.ROUTE_UNDERSHOOT
    assert eff_exc.value.details["rejected"][0]["reason"] == "effort_too_low"  # type: ignore[index]


def test_required_resume_unavailable_raises_admission_refused() -> None:
    cat = make_catalog()
    prev = PreviousRoute("codex", "gpt-6-sol", ModelClass.IMPLEMENTATION, Effort.MEDIUM, "sess-1", "step-1")
    policy_req = replace(
        ADMISSION_DEFAULTS,
        resume=MappingProxyType({**ADMISSION_DEFAULTS.resume, Operation.CONTINUATION: ResumePolicy.REQUIRED}),
    )
    adm = admit(
        AdmissionFacts(
            operation=Operation.CONTINUATION,
            role=RoleId.EXECUTOR,
            task_min_class=None,
            task_min_effort=None,
            started_by=prev,
            previous=prev,
            contract_digest=DIGEST,
            previous_contract_digest=DIGEST,
            fix_brief=None,
            previous_output_id=None,
        ),
        policy_req,
    )
    # codex lacks SESSION_RESUME -> resume_unavailable -> ADMISSION_REFUSED
    caps = {"codex": make_caps("codex", supported=(Capability.CONFIG_ISOLATION,))}
    with pytest.raises(PreconditionFailed) as exc_info:
        route(
            make_req(admission=adm),
            make_cfg(),
            cat,
            caps,
            {"codex": make_install("codex")},
            frozenset({"codex"}),
        )
    assert exc_info.value.code is ErrorCode.ADMISSION_REFUSED


@settings(max_examples=40, deadline=None)
@given(
    cap_perm=st.permutations(["claude_code", "codex", "grok"]),
    inst_perm=st.permutations(["claude_code", "codex", "grok"]),
    cat_perm=st.permutations(["claude_code", "codex", "grok"]),
    role_perm=st.permutations([RoleId.RESEARCHER, RoleId.EXECUTOR, RoleId.REVIEWER]),
)
def test_routing_is_invariant_under_dictionary_key_permutations(
    cap_perm: list[str],
    inst_perm: list[str],
    cat_perm: list[str],
    role_perm: list[RoleId],
) -> None:
    base_cat = make_catalog()
    perm_cat = ModelCatalog(
        catalog_version=base_cat.catalog_version,
        resource_version_ids=base_cat.resource_version_ids,
        digest=base_cat.digest,
        runtimes={k: base_cat.runtimes[k] for k in cat_perm},
    )
    all_caps = {
        "claude_code": make_caps("claude_code"),
        "codex": make_caps("codex"),
        "grok": make_caps("grok"),
    }
    perm_caps = {k: all_caps[k] for k in cap_perm}

    all_inst = {
        "claude_code": make_install("claude_code", AuthState.EXPIRED),
        "codex": make_install("codex", AuthState.OK),
        "grok": make_install("grok", AuthState.OK),
    }
    perm_inst = {k: all_inst[k] for k in inst_perm}

    routing_map = {
        RoleId.RESEARCHER: {"runtime": "grok"},
        RoleId.EXECUTOR: {"runtime": "claude_code", "fallback": [{"runtime": "grok"}, {"runtime": "codex"}]},
        RoleId.REVIEWER: {"runtime": "codex"},
    }
    perm_routing = {r: routing_map[r] for r in role_perm}

    req = make_req()
    baseline = route(
        req,
        make_cfg(role_routing=routing_map),
        base_cat,
        all_caps,
        all_inst,
        frozenset({"claude_code", "codex", "grok"}),
    )
    permuted = route(
        req,
        make_cfg(role_routing=perm_routing),
        perm_cat,
        perm_caps,
        perm_inst,
        frozenset(reversed(cap_perm)),
    )
    assert permuted == baseline
