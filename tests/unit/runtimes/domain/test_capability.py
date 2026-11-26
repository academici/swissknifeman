"""Unit tests for effective capabilities, enforcing proof, self-loads and config_mode (runtimes §4.3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.ids import HostId
from skm.kernel.isolation import IsolationProfile, parse_isolation_profile
from skm.kernel.outcomes import Severity
from skm.modules.runtimes.domain.capability import (
    ENFORCING_CAPABILITIES,
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    ConfigIsolationSpec,
    RuntimeCapabilities,
    SelfLoad,
    SelfLoadKind,
    VerificationContext,
    config_mode_for,
    effective_capabilities,
    explain_self_loads,
    self_loaded_instruction_files,
    verification_context_key,
)

HOST_1 = HostId(UUID("0193a6f0-0100-7a00-8000-9a8b7c6d5e4f"))
HOST_2 = HostId(UUID("0193a6f0-0200-7a00-8000-9a8b7c6d5e4f"))
TODAY = date(2026, 11, 10)
BIN_SHA = "sha256:" + "1" * 64
ALT_BIN_SHA = "sha256:" + "2" * 64
CFG_SHA = "sha256:" + "3" * 64
ALT_CFG_SHA = "sha256:" + "4" * 64


def make_ctx(**overrides: Any) -> VerificationContext:
    base = VerificationContext(
        host_id=HOST_1,
        binary_sha256=BIN_SHA,
        os="linux",
        kernel="6.8.0-generic",
        adapter_version="2.0.0",
        isolation_profile=IsolationProfile.LANDLOCK,
        launch_config_digest=CFG_SHA,
    )
    return replace(base, **overrides)


def make_record(
    capability: Capability,
    status: CapabilityStatus = CapabilityStatus.NATIVE,
    *,
    version: str | None = "2.1.266",
    verified_at: date | None = TODAY - timedelta(days=5),
    ctx: VerificationContext | None = None,
    evidence: str = "fixture:stream.jsonl",
    limitations: str = "",
) -> CapabilityRecord:
    return CapabilityRecord(
        capability=capability,
        status=status,
        evidence=evidence,
        tested_runtime_version=version,
        limitations=limitations,
        last_verified_at=verified_at,
        verification_context=ctx,
    )


def make_static(
    records: dict[Capability, CapabilityRecord],
    *,
    adapter_version: str = "2.0.0",
    self_loads: tuple[SelfLoad, ...] = (),
) -> RuntimeCapabilities:
    return RuntimeCapabilities(
        runtime_id="claude_code",
        adapter_version=adapter_version,
        records=records,
        self_loads=self_loads,
        read_only_network=True,
        config_isolation=ConfigIsolationSpec(
            env={"CLAUDE_CONFIG_DIR": "{client_home}"},
            args=(),
            credential_mounts=(),
            writable_home_dirs=(),
        ),
    )


def test_verification_context_validation_and_canonical_key() -> None:
    ctx_a = make_ctx()
    ctx_b = make_ctx(isolation_profile=parse_isolation_profile("landlock"))
    assert verification_context_key(ctx_a) == verification_context_key(ctx_b)
    assert verification_context_key(ctx_a).startswith("sha256:")
    assert verification_context_key(ctx_a) != verification_context_key(make_ctx(binary_sha256=ALT_BIN_SHA))

    plugin_ctx = make_ctx(isolation_profile=parse_isolation_profile("acme:firejail"))
    assert verification_context_key(plugin_ctx) != verification_context_key(ctx_a)

    with pytest.raises(ValueError, match="binary_sha256"):
        make_ctx(binary_sha256="md5:deadbeef")
    with pytest.raises(ValueError, match="launch_config_digest"):
        make_ctx(launch_config_digest="not-a-digest")
    with pytest.raises(ValueError, match="os"):
        make_ctx(os="")
    with pytest.raises(ValueError, match="isolation profile"):
        make_ctx(isolation_profile="bogus-profile")


@pytest.mark.parametrize("enforcing_cap", sorted(ENFORCING_CAPABILITIES, key=str))
def test_enforcing_capabilities_fail_closed_without_exact_fresh_verification(
    enforcing_cap: Capability,
) -> None:
    ctx = make_ctx()
    static = make_static({enforcing_cap: make_record(enforcing_cap, CapabilityStatus.NATIVE, ctx=None)})

    # 1. Static claim without verification -> unknown (unverified_enforcing)
    eff_unverified = effective_capabilities(
        static, (), host_version="2.1.266", verification_context=ctx, now=TODAY
    )
    assert eff_unverified.status(enforcing_cap) is CapabilityStatus.UNKNOWN
    assert "unverified_enforcing" in eff_unverified.records[enforcing_cap].limitations

    # 2. Static unsupported stays unsupported
    static_unsup = make_static(
        {enforcing_cap: make_record(enforcing_cap, CapabilityStatus.UNSUPPORTED, ctx=None)}
    )
    eff_unsup = effective_capabilities(
        static_unsup, (), host_version="2.1.266", verification_context=ctx, now=TODAY
    )
    assert eff_unsup.status(enforcing_cap) is CapabilityStatus.UNSUPPORTED

    # 3. Exact fresh verification -> accepted!
    good_ver = make_record(enforcing_cap, CapabilityStatus.NATIVE, version="2.1.266", ctx=ctx)
    eff_ok = effective_capabilities(
        static, (good_ver,), host_version="2.1.266", verification_context=ctx, now=TODAY
    )
    assert eff_ok.status(enforcing_cap) is CapabilityStatus.NATIVE
    assert eff_ok.supports(enforcing_cap) is True

    # 4. Any mismatch in VerificationContext or host_version -> unknown!
    mismatches = [
        ("missing_ctx", None, "2.1.266"),
        ("missing_host_version", ctx, None),
        ("version_mismatch", ctx, "2.1.265"),
        ("version_upgrade", ctx, "2.1.267"),
        ("different_host", make_ctx(host_id=HOST_2), "2.1.266"),
        ("rebuilt_binary_same_version", make_ctx(binary_sha256=ALT_BIN_SHA), "2.1.266"),
        ("different_os", make_ctx(os="darwin"), "2.1.266"),
        ("different_kernel", make_ctx(kernel="6.9.1-generic"), "2.1.266"),
        ("different_adapter_version", make_ctx(adapter_version="2.0.1"), "2.1.266"),
        (
            "different_isolation_profile",
            make_ctx(isolation_profile=IsolationProfile.CONTAINER),
            "2.1.266",
        ),
        ("different_launch_config", make_ctx(launch_config_digest=ALT_CFG_SHA), "2.1.266"),
    ]
    for label, probe_ctx, probe_ver in mismatches:
        eff_bad = effective_capabilities(
            static, (good_ver,), host_version=probe_ver, verification_context=probe_ctx, now=TODAY
        )
        assert eff_bad.status(enforcing_cap) is CapabilityStatus.UNKNOWN, label

    # 5. Stale enforcing verification drops to unknown EVEN when stale_policy="warn"
    stale_ver = make_record(
        enforcing_cap,
        CapabilityStatus.NATIVE,
        version="2.1.266",
        verified_at=TODAY - timedelta(days=31),
        ctx=ctx,
    )
    eff_stale = effective_capabilities(
        static,
        (stale_ver,),
        host_version="2.1.266",
        verification_context=ctx,
        now=TODAY,
        stale_after_days=30,
        stale_policy="warn",
    )
    assert eff_stale.status(enforcing_cap) is CapabilityStatus.UNKNOWN
    assert "stale=age" in eff_stale.records[enforcing_cap].limitations


def test_functional_capabilities_merge_recency_version_and_staleness() -> None:
    cap = Capability.SESSION_RESUME
    static = make_static(
        {cap: make_record(cap, CapabilityStatus.NATIVE, version="2.1.260", verified_at=TODAY - timedelta(10))}
    )

    # Older verification does NOT override newer static claim
    older_ver = make_record(
        cap, CapabilityStatus.UNSUPPORTED, version="2.1.250", verified_at=TODAY - timedelta(20)
    )
    eff_older = effective_capabilities(static, (older_ver,), host_version="2.1.260", now=TODAY)
    assert eff_older.status(cap) is CapabilityStatus.NATIVE

    # Newer verification overrides static claim
    newer_ver = make_record(
        cap, CapabilityStatus.ADAPTED, version="2.1.266", verified_at=TODAY - timedelta(2)
    )
    eff_newer = effective_capabilities(static, (newer_ver,), host_version="2.1.266", now=TODAY)
    assert eff_newer.status(cap) is CapabilityStatus.ADAPTED

    # Host version <= tested stays valid; host_version > tested drops to unknown (stale=version)
    eff_older_host = effective_capabilities(static, (newer_ver,), host_version="2.1.265", now=TODAY)
    assert eff_older_host.status(cap) is CapabilityStatus.ADAPTED

    eff_newer_host = effective_capabilities(static, (newer_ver,), host_version="2.2.0", now=TODAY)
    assert eff_newer_host.status(cap) is CapabilityStatus.UNKNOWN
    assert "stale=version" in eff_newer_host.records[cap].limitations

    # Unparseable version -> unknown (invalid_version)
    eff_bad_ver = effective_capabilities(static, (newer_ver,), host_version="nightly-unknown", now=TODAY)
    assert eff_bad_ver.status(cap) is CapabilityStatus.UNKNOWN
    assert "invalid_version" in eff_bad_ver.records[cap].limitations

    # Age staleness: warn keeps status + marks limitation; refuse drops to unknown
    static_very_old = make_static(
        {cap: make_record(cap, CapabilityStatus.NATIVE, version="2.1.260", verified_at=TODAY - timedelta(90))}
    )
    aged = make_record(cap, CapabilityStatus.NATIVE, version="2.1.266", verified_at=TODAY - timedelta(45))
    eff_warn = effective_capabilities(
        static_very_old, (aged,), host_version="2.1.266", now=TODAY, stale_after_days=30, stale_policy="warn"
    )
    assert eff_warn.status(cap) is CapabilityStatus.NATIVE
    assert "stale=age" in eff_warn.records[cap].limitations

    eff_refuse = effective_capabilities(
        static_very_old,
        (aged,),
        host_version="2.1.266",
        now=TODAY,
        stale_after_days=30,
        stale_policy="refuse",
    )
    assert eff_refuse.status(cap) is CapabilityStatus.UNKNOWN
    assert "stale=age" in eff_refuse.records[cap].limitations


def test_self_loaded_instruction_files_and_config_mode_narrowing() -> None:
    ctx = make_ctx()
    loads = (
        SelfLoad(
            kind=SelfLoadKind.PROJECT_INSTRUCTIONS,
            locator="<workdir>/CLAUDE.md",
            files=("CLAUDE.md", ".claude/CLAUDE.md"),
            when="start",
            suppressed_by="config_isolation",
            note="",
        ),
        SelfLoad(
            kind=SelfLoadKind.PROJECT_INSTRUCTIONS,
            locator="<workdir>/AGENTS.md",
            files=("AGENTS.md", "CLAUDE.md"),
            when="start",
            suppressed_by="never",
            note="",
        ),
        SelfLoad(
            kind=SelfLoadKind.PROJECT_INSTRUCTIONS,
            locator="subdir/AGENTS.md",
            files=("LATE.md",),
            when="on_access",
            suppressed_by="never",
            note="",
        ),
    )
    static = make_static(
        {Capability.CONFIG_ISOLATION: make_record(Capability.CONFIG_ISOLATION, CapabilityStatus.NATIVE)},
        self_loads=loads,
    )
    # Without verified config_isolation, both start project_instructions are active
    unverified_eff = effective_capabilities(static, (), host_version="2.1.266", now=TODAY)
    views_unverified = explain_self_loads(unverified_eff, "isolated")
    assert self_loaded_instruction_files(views_unverified, unverified_eff) == (
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        "AGENTS.md",
    )

    # With verified config_isolation, suppressible CLAUDE.md is inactive; unsuppressible AGENTS.md remains
    ver = make_record(Capability.CONFIG_ISOLATION, CapabilityStatus.NATIVE, version="2.1.266", ctx=ctx)
    verified_eff = effective_capabilities(
        static, (ver,), host_version="2.1.266", verification_context=ctx, now=TODAY
    )
    views_verified = explain_self_loads(verified_eff, "isolated")
    assert self_loaded_instruction_files(views_verified, verified_eff) == ("AGENTS.md", "CLAUDE.md")

    # config_mode_for rule 1 (§4.3.1)
    assert config_mode_for(False, scope_inherit=False) == ("isolated", ())
    assert config_mode_for(False, scope_inherit=True) == ("isolated", ())
    assert config_mode_for(True, scope_inherit=True) == ("inherit", ())
    mode, diags = config_mode_for(True, scope_inherit=False)
    assert mode == "isolated"
    assert len(diags) == 1
    assert diags[0].code == "INHERIT_USER_GLOBAL_NARROWED"
    assert diags[0].severity is Severity.WARNING
