"""Permissions, merged TOML safety, hook codecs, capabilities, and layer tests for Codex (P10.03)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest

from skm.adapters.checkout_fs.local import LocalCheckoutFs
from skm.adapters.integrations.codex.config_toml import render_config_toml
from skm.adapters.integrations.codex.doctor_layers import (
    effective_hooks_enabled,
    project_machine_local_keys,
    read_codex_layers,
)
from skm.adapters.integrations.codex.hooks import (
    MAX_PROMPT_BYTES,
    normalize_hook_payload,
    render_hook_decision,
)
from skm.adapters.integrations.codex.mcp import build_mcp_servers
from skm.adapters.integrations.codex.permissions import (
    CodexMode,
    render_codex_mode,
    validate_no_machine_local_keys,
)
from skm.adapters.integrations.codex.target import CodexTarget, load_capabilities
from skm.adapters.integrations.registry import StaticIntegrationTargetRegistry, default_target_registry
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, NotFound, ValidationFailed
from skm.kernel.ids import ProjectId
from skm.kernel.json_types import JsonValue
from skm.modules.integrations.domain.desired import ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookEventKind, HookSurfaceId
from skm.modules.integrations.domain.hook_rules import HookDecision, HookVerdict
from skm.modules.integrations.domain.merged_toml import merge_owned_toml, parse_toml
from skm.modules.integrations.domain.profiles import PermissionProfile, resolve_profile
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetId

REPO_ROOT = Path(__file__).resolve().parents[4]
PAYLOADS_DIR = REPO_ROOT / "tests/fixtures/corpus/examples" / "integrations" / "hook-payloads"
PROJECT_ID = ProjectId(UUID("01928f6e-7a3b-7c41-9d2e-5b8a1f3c4d60"))


class _StubHomeReader:
    def __init__(self, mapping: dict[str, bytes | None]) -> None:
        self._mapping = mapping

    def read(
        self,
        logical: Literal[
            "claude.user_settings", "claude.managed_settings", "codex.user_config", "vscode.user_settings"
        ],
    ) -> bytes | None:
        return self._mapping.get(logical)


def _minimal_inputs() -> ProjectionInputs:
    return ProjectionInputs(
        project_id=PROJECT_ID,
        target=TargetId.CODEX,
        instructions_core={},
        instructions_project={},
        skills=(),
        permissions={},
        profile=PermissionProfile.WORKSPACE_CONTAINED,
        hook_modes={},
        host_subscription_events=(),
        mcp_servers={},
        agents=(),
        inputs_digest="sha256:" + "0" * 64,
        config_generation=1,
        diagnostics=(),
    )


def _base_codex_payload(event_name: str) -> dict[str, JsonValue]:
    return {
        "session_id": "019a3b2c-4d5e-7f60-8a9b-0c1d2e3f4a5b",
        "cwd": "/home/dev/demo",
        "hook_event_name": event_name,
        "model": "gpt-5-codex",
        "source": "cli",
    }


def test_profile_mapping_and_trusted_host_gate() -> None:
    """Profile modes map to exact Codex keys and ``trusted_full_access`` narrows without host opt-in."""
    assert render_codex_mode(PermissionProfile.OBSERVE) == CodexMode("untrusted", "read-only")
    assert render_codex_mode(PermissionProfile.WORKSPACE_CONTAINED) == CodexMode("never", "workspace-write")
    assert render_codex_mode(PermissionProfile.TRUSTED_FULL_ACCESS) == CodexMode(
        "never", "danger-full-access"
    )

    refused = resolve_profile(PermissionProfile.TRUSTED_FULL_ACCESS, host_allows_trusted=False)
    assert refused.profile is PermissionProfile.WORKSPACE_CONTAINED
    assert refused.diagnostics[0].code == ErrorCode.INTEGRATION_TRUSTED_REFUSED.value
    assert render_codex_mode(refused.profile) == CodexMode("never", "workspace-write")

    allowed = resolve_profile(PermissionProfile.TRUSTED_FULL_ACCESS, host_allows_trusted=True)
    assert allowed.profile is PermissionProfile.TRUSTED_FULL_ACCESS
    assert render_codex_mode(allowed.profile) == CodexMode("never", "danger-full-access")


def test_unrepresentable_permissions_deny_floor_and_machine_keys_refused() -> None:
    """Unrepresentable fine-grained denies, deny-floor weakening, and machine-local keys are refused."""
    with pytest.raises(CapabilityUnavailable) as exc_floor:
        render_codex_mode(
            PermissionProfile.WORKSPACE_CONTAINED,
            {"fs_read": [{"allow": [{"scope": "worktree", "pattern": ".env"}], "deny": []}]},
        )
    assert exc_floor.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert exc_floor.value.details["reason"] == "deny_floor_weakened"

    with pytest.raises(CapabilityUnavailable) as exc_ssh:
        render_codex_mode(
            PermissionProfile.WORKSPACE_CONTAINED,
            {"fs_read": [{"allow": [{"scope": "home", "pattern": ".ssh/id_rsa"}], "deny": []}]},
        )
    assert exc_ssh.value.details["reason"] == "deny_floor_weakened"

    with pytest.raises(CapabilityUnavailable) as exc_read_deny:
        render_codex_mode(
            PermissionProfile.WORKSPACE_CONTAINED,
            {
                "fs_read": [
                    {
                        "allow": [{"scope": "worktree", "pattern": "**"}],
                        "deny": [{"scope": "worktree", "pattern": "private/**"}],
                    }
                ]
            },
        )
    assert exc_read_deny.value.details["reason"] == "unrepresentable_fs_read_deny"

    with pytest.raises(CapabilityUnavailable) as exc_write_deny:
        render_codex_mode(
            PermissionProfile.WORKSPACE_CONTAINED,
            {
                "fs_write": [
                    {
                        "allow": [{"scope": "worktree", "pattern": "**"}],
                        "deny": [{"scope": "worktree", "pattern": "infra/**"}],
                    }
                ]
            },
        )
    assert exc_write_deny.value.details["reason"] == "unrepresentable_fs_write_deny"

    with pytest.raises(CapabilityUnavailable) as exc_mod_denied:
        render_codex_mode(
            PermissionProfile.WORKSPACE_CONTAINED,
            {"operations": {"modify_write_set": {"deny": True}}},
        )
    assert exc_mod_denied.value.details["reason"] == "write_forbidden_by_permissions"

    with pytest.raises(CapabilityUnavailable) as exc_no_shell:
        render_codex_mode(
            PermissionProfile.WORKSPACE_CONTAINED,
            {"commands": {"mode": "none"}},
        )
    assert exc_no_shell.value.details["reason"] == "shell_forbidden_by_permissions"

    for bad_key in ("model_provider", "auth", "notify", "profile", "otel", "telemetry"):
        with pytest.raises(ValidationFailed) as exc_mk:
            validate_no_machine_local_keys({bad_key: "local-override"})
        assert exc_mk.value.code is ErrorCode.CONFIG_INVALID


def test_mcp_secret_refs_and_merged_toml_table_collision_safety() -> None:
    """Plaintext MCP env is rejected; merged TOML refuses scalar/table collisions and keeps foreign tables."""
    bad_inputs = replace(
        _minimal_inputs(),
        mcp_servers={
            "github": {
                "enabled": True,
                "command": "npx",
                "env_refs": {"GITHUB_TOKEN": "ghp_plaintext_secret_leak"},
            }
        },
    )
    with pytest.raises(ValidationFailed) as exc_secret:
        build_mcp_servers(bad_inputs)
    assert exc_secret.value.code is ErrorCode.CONFIG_INVALID

    unsafe_name_inputs = replace(
        _minimal_inputs(),
        mcp_servers={"../evil": {"enabled": True, "command": "npx"}},
    )
    with pytest.raises(ValidationFailed) as exc_name:
        build_mcp_servers(unsafe_name_inputs)
    assert exc_name.value.code is ErrorCode.INTEGRATION_UNSAFE_TARGET

    valid_inputs = replace(
        _minimal_inputs(),
        mcp_servers={
            "skm": {"enabled": True, "command": "skm", "args": ["mcp"]},
            "github": {
                "enabled": True,
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env_refs": {"GITHUB_TOKEN": "secret://env/GITHUB_TOKEN"},
            },
        },
    )
    cfg_df = render_config_toml(valid_inputs)
    managed_doc = parse_toml(cfg_df.managed_bytes.decode("utf-8"))

    # Scalar collision on owned table container fails safely with INTEGRATION_BOUNDARY_INVALID.
    with pytest.raises(ValueError, match="INTEGRATION_BOUNDARY_INVALID"):
        merge_owned_toml('mcp_servers = "not-a-table"\n', managed_doc, cfg_df.boundary.owned_keys)

    # Table collision on owned top-level scalar fails safely with INTEGRATION_BOUNDARY_INVALID.
    with pytest.raises(ValueError, match="INTEGRATION_BOUNDARY_INVALID"):
        merge_owned_toml('[approval_policy]\nmode = "never"\n', managed_doc, cfg_df.boundary.owned_keys)


def test_hook_payload_normalization_and_spec_examples() -> None:
    """All 8 Codex hook events normalize cleanly and match the normative example payloads."""
    target = CodexTarget()

    raw_example = json.loads((PAYLOADS_DIR / "codex-pre-tool-use.json").read_text("utf-8"))
    expected_norm = json.loads((PAYLOADS_DIR / "codex-pre-tool-use.normalized.json").read_text("utf-8"))
    expected_dec = json.loads((PAYLOADS_DIR / "codex-pre-tool-use.decision.json").read_text("utf-8"))

    norm = target.normalize_hook_payload("PreToolUse", raw_example)
    assert {
        "schema": "urn:skm:integrations:defs:v1#/$defs/hook_event",
        "target": norm.target.value,
        "kind": norm.kind.value,
        "session_id": norm.session_id,
        "cwd": norm.cwd,
        "tool_name": norm.tool_name,
        "command": norm.command,
        "paths": list(norm.paths),
        "prompt": norm.prompt,
        "stop_status": norm.stop_status,
        "raw_event_name": norm.raw_event_name,
    } == expected_norm

    deny_dec = HookDecision(
        verdict=HookVerdict.DENY,
        surface=HookSurfaceId.PACK_GUARD,
        reason_code="MANAGED_FILE_EDIT",
        user_message=expected_dec["user_message"],
        agent_message=expected_dec["agent_message"],
        additional_context=None,
    )
    assert target.render_hook_decision(norm, deny_dec) == expected_dec["client_output"]

    # Multi-file apply_patch (Update / Add / Delete / absolute path under cwd)
    multi_patch = {
        **_base_codex_payload("PreToolUse"),
        "tool_name": "apply_patch",
        "tool_input": {
            "input": (
                "*** Begin Patch\n"
                "*** Update File: /home/dev/demo/src/app.py\n"
                "*** Add File: tests/test_app.py\n"
                "*** Delete File: old.py\n"
                "*** End Patch\n"
            )
        },
    }
    norm_multi = normalize_hook_payload("PreToolUse", multi_patch)
    assert norm_multi.kind is HookEventKind.PRE_TOOL
    assert norm_multi.paths == ("src/app.py", "tests/test_app.py", "old.py")

    # Bash PreToolUse, PostToolUse, PermissionRequest
    bash_pre = normalize_hook_payload(
        "PreToolUse",
        {**_base_codex_payload("PreToolUse"), "tool_name": "Bash", "tool_input": {"command": "git status"}},
    )
    assert bash_pre.kind is HookEventKind.PRE_SHELL
    assert bash_pre.tool_name == "shell"
    assert bash_pre.command == "git status"

    bash_post = normalize_hook_payload(
        "PostToolUse",
        {**_base_codex_payload("PostToolUse"), "tool_name": "Bash", "tool_input": {"command": "pytest -q"}},
    )
    assert bash_post.kind is HookEventKind.POST_TOOL
    assert bash_post.tool_name == "shell"

    perm_req = normalize_hook_payload(
        "PermissionRequest",
        {
            **_base_codex_payload("PermissionRequest"),
            "tool_name": "Bash",
            "tool_input": {"command": "git push"},
        },
    )
    assert perm_req.kind is HookEventKind.PERMISSION_REQUEST
    assert perm_req.command == "git push"

    # SessionStart, UserPromptSubmit, SubagentStop, Stop, SessionEnd
    sess_start = normalize_hook_payload(
        "SessionStart",
        {**_base_codex_payload("SessionStart"), "permission_mode": "workspace-write"},
    )
    assert sess_start.kind is HookEventKind.SESSION_START

    huge_prompt = "x" * (MAX_PROMPT_BYTES + 200)
    usr_prompt = normalize_hook_payload(
        "UserPromptSubmit",
        {**_base_codex_payload("UserPromptSubmit"), "prompt": huge_prompt},
    )
    assert usr_prompt.kind is HookEventKind.USER_PROMPT
    assert usr_prompt.prompt is not None
    assert len(usr_prompt.prompt.encode("utf-8")) == MAX_PROMPT_BYTES

    sub_stop = normalize_hook_payload(
        "SubagentStop",
        {**_base_codex_payload("SubagentStop"), "agent_type": "reviewer"},
    )
    assert sub_stop.kind is HookEventKind.SUBAGENT_STOP

    stop_ev = normalize_hook_payload(
        "Stop",
        {**_base_codex_payload("Stop"), "stop_hook_active": True, "last_assistant_message": "Done."},
    )
    assert stop_ev.kind is HookEventKind.STOP
    assert stop_ev.stop_status == "active"

    sess_end = normalize_hook_payload(
        "SessionEnd",
        {**_base_codex_payload("SessionEnd"), "reason": "completed"},
    )
    assert sess_end.kind is HookEventKind.SESSION_END
    assert sess_end.stop_status == "completed"

    invalid_example = json.loads((PAYLOADS_DIR / "invalid-payload.json").read_text("utf-8"))
    with pytest.raises(ValidationFailed) as exc_inv:
        normalize_hook_payload("PreToolUse", invalid_example)
    assert exc_inv.value.code is ErrorCode.HOOK_PAYLOAD_INVALID


def test_hook_decision_rendering_variants() -> None:
    """Ask, context, allow, and none verdicts render exact Codex stdout/stderr/exit_code contracts."""
    ev = normalize_hook_payload(
        "SessionStart",
        {**_base_codex_payload("SessionStart"), "permission_mode": "workspace-write"},
    )
    ask_out = render_hook_decision(
        ev,
        HookDecision(HookVerdict.ASK, HookSurfaceId.GIT_GUARDRAILS, "ASK_USER", "Confirm push", None, None),
    )
    assert ask_out == {"exit_code": 2, "stdout": "", "stderr": "Confirm push (confirmation required)"}

    ctx_out = render_hook_decision(
        ev,
        HookDecision(
            HookVerdict.CONTEXT, HookSurfaceId.SESSION_CONTEXT, None, None, None, "Active leaf P10.03"
        ),
    )
    assert ctx_out == {
        "exit_code": 0,
        "stdout": {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "Active leaf P10.03",
            }
        },
        "stderr": "",
    }

    for silent_verdict in (HookVerdict.ALLOW, HookVerdict.NONE):
        out = render_hook_decision(
            ev, HookDecision(silent_verdict, HookSurfaceId.COMMAND_LOG, None, None, None, None)
        )
        assert out == {"exit_code": 0, "stdout": "", "stderr": ""}


def test_capabilities_registry_and_doctor_layers(tmp_path: Path) -> None:
    """Capabilities manifest, target registry, and read-only Codex layers satisfy doctor contracts."""
    caps = load_capabilities()
    assert caps.target is TargetId.CODEX
    assert caps.tested_client_version == "0.165.0"
    assert caps.verified_at == date(2026, 10, 26)
    assert dict(caps.surfaces) == dict.fromkeys(Surface, SurfaceSupport.NATIVE)
    assert len(caps.hook_surfaces) == 9

    reg = default_target_registry()
    assert isinstance(reg, StaticIntegrationTargetRegistry)
    target = reg.get(TargetId.CODEX)
    assert target.instruction_paths() == ("AGENTS.md",)

    checkout = tmp_path / "repo"
    (checkout / ".git").mkdir(parents=True)
    (checkout / ".codex").mkdir(parents=True)
    (checkout / ".codex" / "config.toml").write_text(
        'approval_policy = "never"\nnotify = ["notify-send"]\n\n[features]\nhooks = false\n',
        encoding="utf-8",
    )
    fs = LocalCheckoutFs(checkout, state_dir=tmp_path / "state")
    assert target.summarize_session({}, fs) is None

    home = _StubHomeReader({"codex.user_config": b"[features]\nhooks = true\n"})
    layers = read_codex_layers(fs, home)
    by_id = {str(layer["layer"]): layer for layer in layers}
    assert set(by_id) == {"user", "project"}
    assert by_id["user"]["exists"] is True
    assert by_id["user"]["valid"] is True
    assert by_id["project"]["exists"] is True
    assert by_id["project"]["valid"] is True
    assert effective_hooks_enabled(layers) is False
    assert project_machine_local_keys(layers) == ("notify",)

    # Corrupt user config yields valid=False, error='invalid_toml' without raising.
    bad_home = _StubHomeReader({"codex.user_config": b"approval_policy = [unterminated\n"})
    bad_layers = read_codex_layers(fs, bad_home)
    assert bad_layers[0]["valid"] is False
    assert bad_layers[0]["error"] == "invalid_toml"

    assert reg.get(TargetId.GROK).target_id is TargetId.GROK
    with pytest.raises(NotFound):
        StaticIntegrationTargetRegistry({}).get(TargetId.GROK)
