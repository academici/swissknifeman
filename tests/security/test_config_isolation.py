"""Security & cross-adapter config isolation verification suite.

Verifies invariants K16, K17, RT-11, S-20, S-21, and S-55 across ``claude_code``, ``codex``, ``grok``,
and ``cursor``, ``executor-transparent`` narrowing, policy ceiling immutability, ``VerificationContext``
invalidation, Landlock read-only host auth confinement, and opt-in ``SKM_EVALS=1`` live CLI probes.
"""

from __future__ import annotations

import json
import os
import pwd
import shutil
import subprocess
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

import pytest

from contracts.runtimes.test_client_home import FIXTURES, ROOT, _make_request, _poisoned_user_home
from fakes.clock import FrozenClock
from security.test_permissions_widening import WT, compose, decide, wide
from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.runtimes import REPOSITORIES as MEMORY_RUNTIMES
from skm.adapters.postgres.access.repositories import PostgresPrincipalRepository
from skm.adapters.postgres.runtimes import REPOSITORIES as POSTGRES_RUNTIMES
from skm.adapters.runtimes._cli_session.probe import resolve_binary_path
from skm.adapters.runtimes._cli_session.transcript import TranscriptWriter
from skm.adapters.runtimes.claude_code import launch as claude_launch
from skm.adapters.runtimes.claude_code.runtime import ClaudeCodeRuntime
from skm.adapters.runtimes.codex import launch as codex_launch
from skm.adapters.runtimes.codex.runtime import CodexRuntime
from skm.adapters.runtimes.cursor.runtime import CursorRuntime
from skm.adapters.runtimes.grok import launch as grok_launch
from skm.adapters.runtimes.grok.runtime import GrokRuntime
from skm.adapters.sandbox.landlock_exec import landlock_abi
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.ids import HostId, PrincipalId, ResourceVersionId
from skm.kernel.isolation import IsolationProfile
from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import Severity
from skm.modules.access.domain.principal import new_principal
from skm.modules.extensions.public import parse_agent_profile
from skm.modules.policy.domain.calls import FileWrite, RunCommand, WebAccess
from skm.modules.policy.domain.profiles import parse_layer
from skm.modules.policy.domain.tool_call import Deny
from skm.modules.runtimes.domain import capability as cap_dom
from skm.modules.runtimes.domain import request as req_dom
from skm.modules.runtimes.domain.admission import Admission, Operation, ResumePolicy
from skm.modules.runtimes.domain.catalog import ModelCatalog, load_catalog
from skm.modules.runtimes.domain.classes import Effort, ModelClass, RoleId
from skm.modules.runtimes.domain.detection import DetectProbe, VerificationRecord
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.domain.routing import RouteConfig, RouteRequest, route
from skm.modules.runtimes.ports import CapabilityVerificationRepository
from skm.platform.config.sources.document import decode_document
from skm.platform.fs.storage_budget import StorageBudget, StorageOwnerIdentity
from skm.platform.schema.registry import SchemaRegistry
from support.backend import PostgresTestBackend
from support.pg import TestDatabase, clean_test_database, pg_session, test_database  # noqa: F401

PROFILES_DIR = ROOT / "resources/packs/core/agent-profiles"
MODELS_TOML = ROOT / "resources/packs/core/runtimes/models.toml"
ADAPTERS_DIR = ROOT / "src/skm/adapters/runtimes"


@dataclass(frozen=True, slots=True)
class _CatRes:
    key: str
    resource_version_id: ResourceVersionId
    manifest: Mapping[str, JsonValue]


def _load_all_static_caps() -> dict[str, cap_dom.RuntimeCapabilities]:
    schemas = SchemaRegistry.load_default()
    out: dict[str, cap_dom.RuntimeCapabilities] = {}
    for rid in ("claude_code", "codex", "grok", "cursor"):
        doc = decode_document((ADAPTERS_DIR / rid / "capabilities.toml").read_text("utf-8"), "toml")
        assert schemas.validate("urn:skm:runtimes:capabilities:v1", doc) == ()
        out[rid] = cap_dom.parse_capabilities(doc)
    return out


def _catalog() -> ModelCatalog:
    raw = decode_document(MODELS_TOML.read_text(encoding="utf-8"), "toml")
    return load_catalog([_CatRes("core/default", ResourceVersionId(uuid4()), raw)])


def _poisoned_env_and_homes(tmp_path: Path) -> tuple[Path, Path]:
    workdir = tmp_path / "workdir"
    shutil.copytree(FIXTURES / "worktree", workdir)
    return workdir, _poisoned_user_home(tmp_path)


def _req(
    runtime_id: str,
    workdir: Path,
    state_dir: Path,
    *,
    config_mode: Literal["isolated", "inherit"] = "isolated",
    isolation_profile: IsolationProfile = IsolationProfile.WORKTREE,
    extra_env: dict[str, str] | None = None,
    mcp_servers: tuple[req_dom.McpServerSpec, ...] = (),
    secret_token: str = "skm-sec-assign-token-ultra-secret-42",
) -> tuple[req_dom.AgentRequest, req_dom.ProcessOwnership]:
    return _make_request(
        runtime_id=runtime_id,
        workdir=workdir,
        state_dir=state_dir,
        config_mode=config_mode,
        isolation_profile=isolation_profile,
        env_allowlist=("PATH",),
        extra_env=extra_env,
        mcp_servers=mcp_servers,
        secret_token=secret_token,
    )


def _verified_caps(
    static: cap_dom.RuntimeCapabilities, host_id: HostId, today: date
) -> cap_dom.RuntimeCapabilities:
    vctx = cap_dom.VerificationContext(
        host_id,
        "sha256:" + "a" * 64,
        "linux",
        "7.0.0",
        static.adapter_version,
        IsolationProfile.WORKTREE,
        "sha256:" + "b" * 64,
    )
    ver = static.records[cap_dom.Capability.HEADLESS_EXECUTION].tested_runtime_version or "1.0.0"
    recs = [
        cap_dom.CapabilityRecord(cap, cap_dom.CapabilityStatus.ADAPTED, "live-eval", ver, "", today, vctx)
        for cap in cap_dom.ENFORCING_CAPABILITIES
    ]
    return cap_dom.effective_capabilities(
        static, recs, host_version=ver, verification_context=vctx, now=today
    )


def _plan(
    runtime_id: str,
    req: req_dom.AgentRequest,
    own: req_dom.ProcessOwnership,
    state_dir: Path,
    user_home: Path,
    *,
    binary: str | None = None,
    env: Mapping[str, str] | None = None,
    profile: str | None = None,
    suffix: str = "",
) -> Any:
    fn: Any = {
        "claude_code": claude_launch.build_launch_plan,
        "codex": codex_launch.build_launch_plan,
        "grok": grok_launch.build_launch_plan,
    }[runtime_id]
    kw: dict[str, Any] = {
        "binary_path": binary or f"/usr/bin/{runtime_id}",
        "step_dir": state_dir / "steps" / f"{req.request_id}{suffix}",
        "ownership": own,
        "host_environ": env or {},
        "user_home": user_home,
    }
    if profile is not None:
        kw["policy_profile"] = profile
    return fn(req, **kw)


def test_user_home_canaries_and_xdg_env_stripped_with_unoverridable_flags(tmp_path: Path) -> None:
    workdir, user_home = _poisoned_env_and_homes(tmp_path)
    state_dir = tmp_path / "state"
    ambient_env = {
        "HOME": str(user_home),
        "PATH": "/usr/bin:/bin",
        "CLAUDE_CONFIG_DIR": str(user_home / ".claude"),
        "CODEX_HOME": str(user_home / ".codex"),
        "CODEX_HOME_USER": str(user_home / ".codex"),
        "XDG_CONFIG_HOME": str(user_home / ".config"),
        "XDG_CACHE_HOME": str(user_home / ".cache"),
        "XDG_DATA_HOME": str(user_home / ".local/share"),
        "XDG_STATE_HOME": str(user_home / ".local/state"),
    }

    c_req, c_own = _req(
        "claude_code",
        workdir,
        state_dir,
        extra_env={"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "0", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "0"},
    )
    c_plan = _plan("claude_code", c_req, c_own, state_dir, user_home, env=ambient_env)
    assert c_plan.client_home is not None
    c_env = c_plan.command.env
    assert c_env["HOME"] == str(c_plan.client_home) == c_env["CLAUDE_CONFIG_DIR"]
    assert c_env["TMPDIR"] == str(c_plan.client_home / "tmp")
    for k in (
        "CLAUDE_CODE_DISABLE_CLAUDE_MDS",
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
        "DISABLE_AUTOUPDATER",
    ):
        assert c_env[k] == "1"
    for xdg in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        assert xdg not in c_env
    assert (c_plan.setting_sources, "--safe-mode" in c_plan.claude_argv) == ("user", True)

    c_trusted = _plan(
        "claude_code", c_req, c_own, state_dir, user_home, profile="trusted-full-access", suffix="-t"
    )
    assert c_trusted.setting_sources == "user,project"

    x_req, x_own = _req("codex", workdir, state_dir)
    x_plan = _plan("codex", x_req, x_own, state_dir, user_home, env=ambient_env)
    assert x_plan.client_home is not None
    x_env = x_plan.command.env
    assert x_env["HOME"] == str(x_plan.client_home) == x_env["CODEX_HOME"]
    assert ("CODEX_HOME_USER" in x_env, "XDG_CONFIG_HOME" in x_env) == (False, False)
    cfg_toml = (x_plan.client_home / "config.toml").read_text(encoding="utf-8")
    for marker in ("CANARY_USER_CODEX", "evil_user_codex_mcp", "evil_worktree_codex_mcp"):
        assert marker not in cfg_toml


def test_four_adapter_routing_gate_and_self_load_accounting_matrix(tmp_path: Path) -> None:
    static_all = _load_all_static_caps()
    schemas = SchemaRegistry.load_default()
    today, host_id, now_dt = date(2026, 11, 14), HostId(uuid4()), datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
    cap_iso = cap_dom.Capability.CONFIG_ISOLATION

    assert {k: v.status(cap_iso) for k, v in static_all.items()} == {
        "claude_code": cap_dom.CapabilityStatus.ADAPTED,
        "codex": cap_dom.CapabilityStatus.ADAPTED,
        "grok": cap_dom.CapabilityStatus.UNSUPPORTED,
        "cursor": cap_dom.CapabilityStatus.UNKNOWN,
    }

    claude_eff = _verified_caps(static_all["claude_code"], host_id, today)
    codex_eff = _verified_caps(static_all["codex"], host_id, today)
    for mode in ("isolated", "inherit"):
        for eff in (claude_eff, codex_eff):
            ps = {v.kind: v for v in cap_dom.explain_self_loads(eff, mode)}[
                cap_dom.SelfLoadKind.PROJECT_SETTINGS
            ]
            assert (ps.active, ps.reason) == (False, "untrusted_suppressed")

    assert (
        cap_dom.self_loaded_instruction_files(cap_dom.explain_self_loads(claude_eff, "isolated"), claude_eff)
        == ()
    )
    assert cap_dom.self_loaded_instruction_files(
        cap_dom.explain_self_loads(codex_eff, "isolated"), codex_eff
    ) == ("AGENTS.md",)

    workdir, state_dir = tmp_path / "workdir", tmp_path / "state"
    observed = CodexRuntime(state_dir=state_dir).self_loaded_context(_req("codex", workdir, state_dir)[0])
    assert (len(observed), observed[0].files, observed[0].trust) == (1, ("AGENTS.md",), "untrusted")
    uid, dig = str(uuid4()), "sha256:" + "c" * 64
    block = {
        "request_id": "b1",
        "status": "self_loaded",
        "resolved_path": "AGENTS.md",
        "text_digest": None,
        "size_bytes": None,
        "tokens_estimate": None,
    }
    sel = {
        "included": [],
        "excluded": [["b1", "self_loaded", "AGENTS.md"]],
        "class_usage": {},
        "total_tokens": 0,
        "task_digest": dig,
        "mode": "full",
    }
    rsl = [
        {"kind": s.kind.value, "locator": s.locator, "files": list(s.files), "when": s.when} for s in observed
    ]
    finalize_cmd = {
        "claim": {"assignment_id": uid, "attempt_id": uid, "worker_id": uid, "fencing_token": 1},
        "manifest_id": uid,
        "draft_digest": dig,
        "host_blocks": [block],
        "host_facts": {"deps": [], "work_paths_count": 0, "work_paths_truncated": False, "work_paths": []},
        "selection": sel,
        "rendered_prompt_digest": dig,
        "prompt_file_version_id": uid,
        "estimator_id": "char4",
        "runtime_self_loaded": rsl,
    }
    assert schemas.validate("urn:skm:context:command:finalize-manifest:v1", finalize_cmd) == ()

    g_req, _ = _req("grok", workdir, state_dir, isolation_profile=IsolationProfile.LANDLOCK)
    grok_sources = GrokRuntime(state_dir=state_dir).self_loaded_context(g_req)
    assert {s.kind for s in grok_sources} >= {
        cap_dom.SelfLoadKind.PROJECT_SETTINGS,
        cap_dom.SelfLoadKind.USER_CONFIG,
    }
    assert all(s.trust == "untrusted" for s in grok_sources)

    op = Operation.NEW_IMPLEMENTATION
    adm = Admission(
        op, op, ModelClass.IMPLEMENTATION, Effort.HIGH, ("role",), frozenset(), ResumePolicy.NEVER, None, ()
    )
    catalog = _catalog()
    installs = {
        rid: RuntimeInstallation(host_id, rid, "1.0.0", f"/usr/bin/{rid}", AuthState.OK, now_dt, {})
        for rid in ("claude_code", "codex", "grok", "cursor")
    }
    grok_eff = cap_dom.effective_capabilities(static_all["grok"], (), host_version="0.1.0", now=today)
    cursor_eff = cap_dom.effective_capabilities(static_all["cursor"], (), host_version="0.1.0", now=today)
    permissive_cfg = RouteConfig(frozenset({"grok"}), ("grok",), {}, frozenset(cap_dom.Capability), False)
    req_caps = frozenset({cap_dom.Capability.HEADLESS_EXECUTION})
    route_req = RouteRequest(
        RoleId.EXECUTOR,
        req_caps,
        frozenset(),
        ModelClass.IMPLEMENTATION,
        Effort.HIGH,
        "grok",
        None,
        host_id,
        adm,
        "inherit",
        frozenset(),
        False,
        "workspace-contained",
    )
    with pytest.raises(CapabilityUnavailable) as exc_grok:
        route(route_req, permissive_cfg, catalog, {"grok": grok_eff}, installs, frozenset({"grok"}))
    rejected = cast("list[dict[str, Any]]", exc_grok.value.details["rejected"])
    assert (rejected[0]["reason"], rejected[0]["detail"]) == (
        "capability_missing:config_isolation",
        "project_settings_not_suppressible",
    )
    trusted_req = replace(route_req, policy_profile="trusted-full-access")
    assert (
        route(
            trusted_req, permissive_cfg, catalog, {"grok": grok_eff}, installs, frozenset({"grok"})
        ).runtime_id
        == "grok"
    )
    strict_cfg = RouteConfig(frozenset({"cursor"}), ("cursor",), {}, frozenset(), True)
    cursor_req = replace(route_req, explicit_runtime="cursor", config_mode="isolated")
    with pytest.raises(CapabilityUnavailable):
        route(cursor_req, strict_cfg, catalog, {"cursor": cursor_eff}, installs, frozenset({"cursor"}))
    with pytest.raises(CapabilityUnavailable) as exc_cur:
        CursorRuntime().start(_req("cursor", workdir, state_dir)[0])
    assert exc_cur.value.code is ErrorCode.CAPABILITY_UNAVAILABLE


def test_executor_transparent_narrowing_and_policy_ceiling_non_widening() -> None:
    schemas = SchemaRegistry.load_default()
    exec_doc = decode_document((PROFILES_DIR / "executor.toml").read_text("utf-8"), "toml")
    trans_doc = decode_document((PROFILES_DIR / "executor-transparent.toml").read_text("utf-8"), "toml")
    assert schemas.validate("urn:skm:extensions:agent-profile:v1", exec_doc) == ()
    assert schemas.validate("urn:skm:extensions:agent-profile:v1", trans_doc) == ()

    exec_prof, trans_prof = parse_agent_profile(exec_doc), parse_agent_profile(trans_doc)
    assert (exec_prof.context["inherit_user_global"], trans_prof.context["inherit_user_global"]) == (
        False,
        True,
    )
    assert cap_dom.config_mode_for(False, scope_inherit=False) == ("isolated", ())
    assert cap_dom.config_mode_for(False, scope_inherit=True) == ("isolated", ())
    mode_narrowed, diags = cap_dom.config_mode_for(True, scope_inherit=False)
    assert (mode_narrowed, len(diags), diags[0].code, diags[0].severity) == (
        "isolated",
        1,
        "INHERIT_USER_GLOBAL_NARROWED",
        Severity.WARNING,
    )
    assert cap_dom.config_mode_for(True, scope_inherit=True) == ("inherit", ())

    claude_eff = _verified_caps(_load_all_static_caps()["claude_code"], HostId(uuid4()), date(2026, 11, 14))
    inherit_views = {v.kind: v for v in cap_dom.explain_self_loads(claude_eff, "inherit")}
    uc = inherit_views[cap_dom.SelfLoadKind.USER_CONFIG]
    assert (uc.active, uc.reason, inherit_views[cap_dom.SelfLoadKind.PROJECT_SETTINGS].active) == (
        True,
        "inherited",
        False,
    )

    raw_role = trans_prof.permissions.layer
    role_layer = parse_layer(raw_role, source="role:executor-transparent") if raw_role is not None else None
    eff_perms = compose(
        profile_id=trans_prof.permissions.policy_profile, role=role_layer, task=wide("task:poisoned")
    )
    for call in (
        FileWrite("/etc/hosts"),
        FileWrite("/home/agent/.claude/settings.json"),
        FileWrite(f"{WT}/.git/hooks/pre-commit"),
        RunCommand("git push origin main", WT),
        WebAccess("web.fetch", "https://evil.example.com/", None),
    ):
        assert isinstance(decide(eff_perms, call), Deny), call


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def verification_repo(
    request: pytest.FixtureRequest,
) -> Iterator[tuple[CapabilityVerificationRepository, PrincipalId, HostId]]:
    now = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    actor_id, host_a = PrincipalId(uuid4()), HostId(uuid4())
    if request.param == "memory":
        repo = cast("Any", MEMORY_RUNTIMES[CapabilityVerificationRepository])(
            MemoryBackendState(), clock=clock
        )
        yield repo, actor_id, host_a
        return
    db: TestDatabase = request.getfixturevalue("clean_test_database")
    pg = PostgresTestBackend(db, pool_max_size=2)
    try:
        with pg.pool.connection() as conn:
            principal = new_principal(
                principal_id=actor_id, kind=PrincipalKind.HUMAN, display_name="op", created_by=None, now=now
            )
            PostgresPrincipalRepository(conn, clock=clock).add(principal)
            pg_repo = cast("Any", POSTGRES_RUNTIMES[CapabilityVerificationRepository])(conn, clock=clock)
            yield pg_repo, actor_id, host_a
            conn.rollback()
    finally:
        pg.close()


def test_verification_context_replay_never_proves_host_and_mutation_invalidates(
    verification_repo: tuple[CapabilityVerificationRepository, PrincipalId, HostId],
) -> None:
    repo, actor_id, host_a = verification_repo
    static_all = _load_all_static_caps()
    static_claude, static_codex = static_all["claude_code"], static_all["codex"]
    today, host_b = date(2026, 11, 14), HostId(uuid4())
    cap_iso = cap_dom.Capability.CONFIG_ISOLATION

    unverified = cap_dom.effective_capabilities(static_claude, (), host_version="2.1.266", now=today)
    assert unverified.status(cap_iso) is cap_dom.CapabilityStatus.UNKNOWN
    assert "unverified_enforcing" in unverified.records[cap_iso].limitations

    d_true = claude_launch.compute_launch_config_digest(
        adapter_version=static_claude.adapter_version, allow_skip_permissions=False, copy_credentials=True
    )
    d_false = claude_launch.compute_launch_config_digest(
        adapter_version=static_claude.adapter_version, allow_skip_permissions=False, copy_credentials=False
    )
    assert d_true != d_false
    assert codex_launch.compute_launch_config_digest(
        adapter_version=static_codex.adapter_version, allow_full_access=False, copy_credentials=True
    ) != codex_launch.compute_launch_config_digest(
        adapter_version=static_codex.adapter_version, allow_full_access=False, copy_credentials=False
    )

    sha_one, ver = "sha256:" + "1" * 64, static_claude.adapter_version
    vctx = cap_dom.VerificationContext(
        host_a, sha_one, "linux", "7.0.0-31-generic", ver, IsolationProfile.WORKTREE, d_true
    )
    vkey = cap_dom.verification_context_key(vctx)
    rec = cap_dom.CapabilityRecord(
        cap_iso, cap_dom.CapabilityStatus.ADAPTED, "live-eval", "2.1.266", "", today, vctx
    )
    repo.add(VerificationRecord("claude_code", "2.1.266", vctx, vkey, rec, actor_id))
    stored = repo.latest("claude_code", "2.1.266", vkey)

    def _eff_status(ctx: cap_dom.VerificationContext) -> cap_dom.CapabilityStatus:
        eff = cap_dom.effective_capabilities(
            static_claude, stored, host_version="2.1.266", verification_context=ctx, now=today
        )
        return eff.status(cap_iso)

    assert _eff_status(vctx) is cap_dom.CapabilityStatus.ADAPTED
    for mutated_ctx in (
        replace(vctx, binary_sha256="sha256:" + "2" * 64),
        replace(vctx, launch_config_digest=d_false),
        replace(vctx, isolation_profile=IsolationProfile.LANDLOCK),
        replace(vctx, kernel="6.12.0-generic"),
        replace(vctx, host_id=host_b),
    ):
        assert _eff_status(mutated_ctx) is cap_dom.CapabilityStatus.UNKNOWN


def test_skm_token_never_persisted_in_client_home_or_transcripts(tmp_path: Path) -> None:
    workdir, user_home = _poisoned_env_and_homes(tmp_path)
    state_dir = tmp_path / "state"
    secret_val = "skm-assign-token-never-on-disk-998877"
    mcp = (req_dom.McpServerSpec("skm_coord", ("/usr/bin/skm-mcp",), {}, ("SKM_TOKEN",)),)

    c_req, c_own = _req("claude_code", workdir, state_dir, mcp_servers=mcp, secret_token=secret_val)
    c_plan = _plan("claude_code", c_req, c_own, state_dir, user_home)
    x_req, x_own = _req("codex", workdir, state_dir, mcp_servers=mcp, secret_token=secret_val)
    x_plan = _plan("codex", x_req, x_own, state_dir, user_home)

    serialized = json.dumps(req_dom.request_to_json(c_req))
    assert (secret_val in repr(c_req), secret_val in serialized, req_dom.REDACTED in serialized) == (
        False,
        False,
        True,
    )
    assert all(secret_val not in arg for arg in (*c_plan.command.argv, *x_plan.command.argv))
    for file_path in state_dir.rglob("*"):
        if file_path.is_file():
            assert secret_val not in file_path.read_text(encoding="utf-8"), file_path

    mcp_json = json.loads((state_dir / "steps" / c_req.request_id / "mcp.json").read_text(encoding="utf-8"))
    assert mcp_json["mcpServers"]["skm_coord"]["env"]["SKM_TOKEN"] == "${SKM_TOKEN}"
    assert x_plan.client_home is not None
    assert 'env_vars = ["SKM_TOKEN"]' in (x_plan.client_home / "config.toml").read_text(encoding="utf-8")

    budget = StorageBudget(
        state_dir / "locks",
        free_bytes=lambda _: 10**9,
        identity=lambda: StorageOwnerIdentity("boot", 1, "1"),
        owner_alive=lambda _: True,
    )
    res = budget.reserve(state_dir, owner_id="t1", max_bytes=1024 * 1024, min_free_bytes=0, max_files=3)
    t_step = state_dir / "steps/transcript-check"
    writer = TranscriptWriter(t_step, res, max_stream_bytes=1024 * 1024, workdir=workdir)
    writer.register_secret(secret_val)
    writer.write("stdout", f'{{"leaked":"{secret_val}"}}\n'.encode())
    writer.write("stderr", f"err: {secret_val}\n".encode())
    writer.close()
    assert secret_val not in (t_step / "stream.jsonl").read_text(encoding="utf-8")
    assert secret_val not in (t_step / "stream.stderr").read_text(encoding="utf-8")


@pytest.mark.skipif(landlock_abi() < 3, reason="Linux Landlock ABI >= 3 required for real confinement proof")
@pytest.mark.parametrize("runtime_id", ["claude_code", "codex", "grok"])
def test_landlock_keeps_host_user_home_auth_material_strictly_read_only(
    tmp_path: Path, runtime_id: Literal["claude_code", "codex", "grok"]
) -> None:
    workdir, user_home = _poisoned_env_and_homes(tmp_path)
    state_dir = tmp_path / "state"
    req, own = _req(
        runtime_id,
        workdir,
        state_dir,
        config_mode="inherit" if runtime_id == "grok" else "isolated",
        isolation_profile=IsolationProfile.LANDLOCK,
    )
    host_auth_file = {
        "claude_code": user_home / ".claude" / claude_launch.CREDENTIAL_FILENAME,
        "codex": user_home / ".codex" / codex_launch.CREDENTIAL_FILENAME,
        "grok": user_home / ".grok" / "config.toml",
    }[runtime_id]
    original_bytes = host_auth_file.read_bytes()

    probe_script = tmp_path / f"probe_{runtime_id}.py"
    probe_script.write_text(
        f"#!{sys.executable}\nimport pathlib\n"
        f"auth = pathlib.Path({str(host_auth_file)!r})\nassert auth.read_bytes()\n"
        f"(pathlib.Path({str(workdir)!r}) / 'allowed.txt').write_text('ok', encoding='utf-8')\n"
        "try:\n    auth.write_text('tampered', encoding='utf-8')\n"
        "except PermissionError:\n    raise SystemExit(0)\nraise SystemExit(99)\n",
        encoding="utf-8",
    )
    os.chmod(probe_script, 0o700)

    argv = _plan(
        runtime_id, req, own, state_dir, user_home, binary=str(probe_script), env={"HOME": str(user_home)}
    ).command.argv
    sep = argv.index("--")
    completed = subprocess.run(
        (*argv[: sep + 1], str(probe_script)), cwd=workdir, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    assert host_auth_file.read_bytes() == original_bytes


@pytest.mark.evals
@pytest.mark.parametrize("runtime_id", ["claude_code", "codex"])
def test_live_evals_detect_and_verification_context_probe(
    tmp_path: Path, runtime_id: Literal["claude_code", "codex"]
) -> None:
    binary_name = "claude" if runtime_id == "claude_code" else "codex"
    located = shutil.which(binary_name)
    if located is None:
        pytest.skip(f"live {binary_name!r} binary absent; replay does not substitute for live proof")
    real_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    env = {**os.environ, "HOME": str(real_home)}
    rt_obj: ClaudeCodeRuntime | CodexRuntime = (
        ClaudeCodeRuntime(state_dir=tmp_path / "state", binary=located, user_home=real_home, environ=env)
        if runtime_id == "claude_code"
        else CodexRuntime(state_dir=tmp_path / "state", binary=located, user_home=real_home, environ=env)
    )
    inst = rt_obj.detect(
        DetectProbe(host_id=HostId(uuid4()), binary=located, env_allowlist=(), timeout_seconds=20)
    )
    assert inst.version is not None
    assert inst.details["binary_sha256"].startswith("sha256:")
    assert inst.details["launch_config_digest"] == rt_obj.launch_config_digest


@pytest.mark.parametrize("path_var", [":/nonexistent", "/nonexistent:", ".", "bin"])
def test_relative_or_empty_path_entries_never_find_a_binary_in_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path_var: str
) -> None:
    # An empty or relative PATH entry means the cwd, which may be a checkout the agent controls.
    for folder in (tmp_path, tmp_path / "bin"):
        folder.mkdir(exist_ok=True)
        planted = folder / "fake-agent"
        planted.write_text("#!/bin/sh\n")
        planted.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        resolve_binary_path("fake-agent", environ={"PATH": path_var}, display_name="Fake")
    found = resolve_binary_path("fake-agent", environ={"PATH": f"{path_var}:{tmp_path}"}, display_name="Fake")
    assert found == (tmp_path / "fake-agent").resolve()
