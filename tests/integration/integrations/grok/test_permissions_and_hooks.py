"""Integration tests for Grok permissions deny floor, mode non-leakage, hooks, MCP, and layers (P10.04.b)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from skm.adapters.checkout_fs.local import LocalCheckoutFs
from skm.adapters.integrations.grok.config_toml import GROK_CONFIG_PATH, render_config_toml
from skm.adapters.integrations.grok.hooks import (
    GROK_HOOK_EVENTS,
    GROK_HOOKS_PATH,
    MAX_PROMPT_BYTES,
    normalize_hook_payload,
    render_hook_decision,
    render_hook_entries,
    render_hooks,
)
from skm.adapters.integrations.grok.instructions import GROK_INSTRUCTIONS_PATH
from skm.adapters.integrations.grok.permissions import (
    GROK_DENY_FLOOR,
    GROK_FORBIDDEN_PROJECT_MODE_KEYS,
    launch_flags_for_profile,
    launch_mode_for_profile,
    render_grok_deny,
    validate_no_project_mode_keys,
)
from skm.adapters.integrations.grok.target import GrokTarget, load_capabilities, read_grok_layers
from skm.adapters.integrations.registry import StaticIntegrationTargetRegistry, default_target_registry
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import ProjectId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.integrations.domain.decisions import FileDecisionKind, decide_file
from skm.modules.integrations.domain.desired import HostSubscriptionEvent, ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookClass, HookEventKind, HookSurfaceId
from skm.modules.integrations.domain.hook_rules import HookDecision, HookMode, HookVerdict
from skm.modules.integrations.domain.merged_toml import merge_owned_toml, parse_toml
from skm.modules.integrations.domain.observed import observe_bytes
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetId
from skm.platform.config.sources.document import decode_document

REPO_ROOT = Path(__file__).resolve().parents[4]
HOOK_EXAMPLES = REPO_ROOT / "tests/fixtures/corpus/examples" / "integrations" / "hook-payloads"
PROJ_ID = ProjectId(UUID("01928f6e-7a3b-7c41-9d2e-5b8a1f3c4d60"))


class _StubHomeReader:
    def __init__(self, files: dict[str, bytes | None]) -> None:
        self._files = files

    def read(self, logical: str) -> bytes | None:
        return self._files.get(logical)


def _minimal_inputs(**overrides: Any) -> ProjectionInputs:
    base = ProjectionInputs(
        project_id=PROJ_ID,
        target=TargetId.GROK,
        instructions_core={"enabled": False},
        instructions_project={"enabled": False},
        skills=(),
        permissions={"digest": "sha256:" + "a" * 64},
        profile=PermissionProfile.WORKSPACE_CONTAINED,
        hook_modes={},
        host_subscription_events=(),
        mcp_servers={},
        agents=(),
        inputs_digest="sha256:" + "b" * 64,
        config_generation=1,
        diagnostics=(),
    )
    return replace(base, **overrides)


def test_normative_grok_pre_tool_use_example_roundtrip() -> None:
    """Normative ``grok-pre-tool-use`` example normalizes and renders decision byte-for-byte."""
    target = GrokTarget()
    raw_payload: JsonObject = json.loads((HOOK_EXAMPLES / "grok-pre-tool-use.json").read_text("utf-8"))
    expected_norm = json.loads((HOOK_EXAMPLES / "grok-pre-tool-use.normalized.json").read_text("utf-8"))
    expected_dec = json.loads((HOOK_EXAMPLES / "grok-pre-tool-use.decision.json").read_text("utf-8"))

    ev = target.normalize_hook_payload("PreToolUse", raw_payload)
    assert {
        "schema": "urn:skm:integrations:defs:v1#/$defs/hook_event",
        "target": ev.target.value,
        "kind": ev.kind.value,
        "session_id": ev.session_id,
        "cwd": ev.cwd,
        "tool_name": ev.tool_name,
        "command": ev.command,
        "paths": list(ev.paths),
        "prompt": ev.prompt,
        "stop_status": ev.stop_status,
        "raw_event_name": ev.raw_event_name,
    } == expected_norm

    out = target.render_hook_decision(
        ev,
        HookDecision(
            verdict=HookVerdict(expected_dec["verdict"]),
            surface=HookSurfaceId(expected_dec["surface"]),
            reason_code=expected_dec["reason_code"],
            user_message=expected_dec["user_message"],
            agent_message=expected_dec["agent_message"],
            additional_context=expected_dec["additional_context"],
        ),
    )
    assert out == expected_dec["client_output"]


def test_all_grok_camelcase_hook_events_and_rejections() -> None:
    """All 6 Grok camelCase events normalize cleanly; snake_case or malformed payloads fail."""
    ev_start = normalize_hook_payload(
        "SessionStart",
        {"hookEventName": "SessionStart", "sessionId": "grk-1", "cwd": "/repo"},
    )
    assert ev_start.kind is HookEventKind.SESSION_START
    assert ev_start.session_id == "grk-1"
    assert ev_start.cwd == "/repo"

    long_prompt = "я" * 3000  # 6000 UTF-8 bytes -> truncated cleanly at codepoint boundary
    ev_prompt = normalize_hook_payload(
        "UserPromptSubmit",
        {"hookEventName": "UserPromptSubmit", "sessionId": "grk-1", "cwd": "/repo", "prompt": long_prompt},
    )
    assert ev_prompt.kind is HookEventKind.USER_PROMPT
    assert ev_prompt.prompt is not None
    assert len(ev_prompt.prompt.encode("utf-8")) <= MAX_PROMPT_BYTES

    patch_body = "*** Begin Patch\n*** Update File: /repo/src/app.py\n*** Add File: tests/test_app.py\n"
    ev_patch = normalize_hook_payload(
        "PreToolUse",
        {
            "hookEventName": "PreToolUse",
            "sessionId": "grk-1",
            "cwd": "/repo",
            "toolName": "apply_patch",
            "toolInput": {"input": patch_body},
        },
    )
    assert ev_patch.kind is HookEventKind.PRE_TOOL
    assert ev_patch.tool_name == "apply_patch"
    assert ev_patch.paths == ("src/app.py", "tests/test_app.py")

    ev_mcp = normalize_hook_payload(
        "PreToolUse",
        {
            "hookEventName": "PreToolUse",
            "toolName": "mcp__skm__memory_search",
            "toolInput": {},
        },
    )
    assert ev_mcp.kind is HookEventKind.PRE_TOOL
    assert ev_mcp.tool_name == "mcp:skm:memory_search"
    assert ev_mcp.session_id is None

    ev_task = normalize_hook_payload(
        "PreToolUse",
        {"hookEventName": "PreToolUse", "toolName": "Task", "toolInput": {}},
    )
    assert ev_task.tool_name == "task"

    ev_post = normalize_hook_payload(
        "PostToolUse",
        {
            "hookEventName": "PostToolUse",
            "sessionId": "grk-1",
            "cwd": "/repo",
            "toolName": "Write",
            "toolInput": {"filePath": "/repo/docs/guide.md"},
            "toolResponse": {"ok": True},
        },
    )
    assert ev_post.kind is HookEventKind.POST_TOOL
    assert ev_post.tool_name == "write"
    assert ev_post.paths == ("docs/guide.md",)

    ev_sub = normalize_hook_payload(
        "SubagentStop",
        {"hookEventName": "SubagentStop", "sessionId": "grk-1", "stopHookActive": True},
    )
    assert ev_sub.kind is HookEventKind.SUBAGENT_STOP
    assert ev_sub.stop_status == "active"

    ev_end = normalize_hook_payload(
        "SessionEnd",
        {"hookEventName": "SessionEnd", "sessionId": "grk-1", "reason": "completed"},
    )
    assert ev_end.kind is HookEventKind.SESSION_END
    assert ev_end.stop_status == "completed"

    # Codex/Claude snake_case payload MUST fail on Grok camelCase normalizer
    bad_examples: tuple[tuple[str, dict[str, JsonValue]], ...] = (
        (
            "PreToolUse",
            {
                "hook_event_name": "PreToolUse",
                "session_id": "s1",
                "cwd": "/repo",
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
            },
        ),
        ("PreToolUse", json.loads((HOOK_EXAMPLES / "invalid-payload.json").read_text("utf-8"))),
        ("PreToolUse", {"hookEventName": "PostToolUse", "toolName": "Bash", "toolInput": {"command": "ls"}}),
        ("PreToolUse", {"hookEventName": "PreToolUse", "toolName": "Bash", "toolInput": {}}),
        (
            "PreToolUse",
            {"hookEventName": "PreToolUse", "toolName": "apply_patch", "toolInput": {"input": "nope"}},
        ),
        ("PreToolUse", {"hookEventName": "PreToolUse", "toolName": "mcp__broken", "toolInput": {}}),
        ("Stop", {"hookEventName": "Stop", "sessionId": "grk-1"}),
    )
    for ev_name, bad_payload in bad_examples:
        with pytest.raises(ValidationFailed) as exc_info:
            normalize_hook_payload(ev_name, bad_payload)
        assert exc_info.value.code is ErrorCode.HOOK_PAYLOAD_INVALID


def test_hook_decision_rendering_and_managed_hook_file() -> None:
    """Grok decision rendering emits exit 2 + stderr on deny/ask and Claude-shaped context JSON."""
    ev = normalize_hook_payload(
        "SessionStart",
        {"hookEventName": "SessionStart", "sessionId": "grk-9", "cwd": "/repo"},
    )
    assert render_hook_decision(
        ev,
        HookDecision(HookVerdict.DENY, HookSurfaceId.GIT_GUARDRAILS, "BLOCKED", "No force push", None, None),
    ) == {"exit_code": 2, "stdout": "", "stderr": "No force push"}

    assert render_hook_decision(
        ev,
        HookDecision(HookVerdict.ASK, HookSurfaceId.GIT_GUARDRAILS, "ASK_USER", "Confirm push", None, None),
    ) == {"exit_code": 2, "stdout": "", "stderr": "Confirm push (confirmation required)"}

    assert render_hook_decision(
        ev,
        HookDecision(
            HookVerdict.CONTEXT, HookSurfaceId.SESSION_CONTEXT, None, None, None, "Active leaf P10.04.b"
        ),
    ) == {
        "exit_code": 0,
        "stdout": {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "Active leaf P10.04.b",
            }
        },
        "stderr": "",
    }

    for silent in (HookVerdict.ALLOW, HookVerdict.NONE):
        assert render_hook_decision(
            ev, HookDecision(silent, HookSurfaceId.COMMAND_LOG, None, None, None, None)
        ) == {"exit_code": 0, "stdout": "", "stderr": ""}

    # When all hook surfaces and subscriptions are off, no skm.json is emitted.
    assert render_hooks(_minimal_inputs()) is None

    # Active surfaces + subscription emit MANAGED_FILE .grok/hooks/skm.json.
    hooks_df = render_hooks(
        _minimal_inputs(
            hook_modes={HookSurfaceId.REVIEW_GATE: HookMode.STRICT},
            host_subscription_events=(
                HostSubscriptionEvent(HookEventKind.USER_PROMPT, (HookClass.OBSERVATION,)),
            ),
        )
    )
    assert hooks_df is not None
    assert hooks_df.relative_path == GROK_HOOKS_PATH
    entries = render_hook_entries(
        _minimal_inputs(
            hook_modes={
                sid: HookMode.STRICT for sid in HookSurfaceId if sid is not HookSurfaceId.SUBSCRIPTIONS
            }
        )
    )
    assert set(entries).issubset(set(GROK_HOOK_EVENTS))


@pytest.mark.parametrize(
    ("profile", "expected_mode", "expected_flags"),
    [
        (PermissionProfile.OBSERVE, "ask", ("--permission-mode", "ask")),
        (PermissionProfile.WORKSPACE_CONTAINED, "acceptEdits", ("--permission-mode", "acceptEdits")),
        (PermissionProfile.TRUSTED_FULL_ACCESS, "always-approve", ("--always-approve",)),
    ],
)
def test_permission_deny_floor_and_mode_non_leakage_across_all_profiles(
    profile: PermissionProfile,
    expected_mode: str,
    expected_flags: tuple[str, ...],
) -> None:
    """Across all 3 profiles, ``.grok/config.toml`` keeps ``GROK_DENY_FLOOR`` and zero mode keys."""
    assert launch_mode_for_profile(profile) == expected_mode
    assert launch_flags_for_profile(profile) == expected_flags

    cfg_df = render_config_toml(
        _minimal_inputs(
            profile=profile,
            permissions={
                "digest": "sha256:" + "d" * 64,
                "fs_read": [{"allow": [], "deny": [{"scope": "home", "pattern": ".aws/**"}]}],
                "fs_write": [{"allow": [], "deny": [{"scope": "worktree", "pattern": "secrets/**"}]}],
            },
        )
    )
    assert cfg_df.relative_path == GROK_CONFIG_PATH
    text = cfg_df.managed_bytes.decode("utf-8")
    parsed = decode_document(text, "toml")

    for forbidden in (*GROK_FORBIDDEN_PROJECT_MODE_KEYS, "ui"):
        assert forbidden not in parsed
    perm_tbl = parsed["permission"]
    assert isinstance(perm_tbl, dict)
    assert set(perm_tbl) == {"deny"}
    deny_list = perm_tbl["deny"]
    assert isinstance(deny_list, list)
    for floor_rule in GROK_DENY_FLOOR:
        assert floor_rule in deny_list
    assert "Read(~/.aws/**)" in deny_list
    assert "Write(secrets/**)" in deny_list


@pytest.mark.parametrize(
    "forbidden_doc",
    [
        {"permission_mode": "always-approve"},
        {"mode": "acceptEdits"},
        {"always-approve": True},
        {"approval_policy": "never"},
        {"sandbox_mode": "danger-full-access"},
        {"ui": {"permission_mode": "ask"}},
        {"permission": {"mode": "always-approve"}},
        {"permission": {"acceptEdits": True}},
    ],
)
def test_forbidden_project_mode_keys_raise_boundary_invalid(forbidden_doc: dict[str, object]) -> None:
    """Attempting to inject launch/permission mode keys into project permissions is rejected."""
    with pytest.raises(ValidationFailed) as exc_direct:
        validate_no_project_mode_keys(forbidden_doc)
    assert exc_direct.value.code is ErrorCode.INTEGRATION_BOUNDARY_INVALID

    with pytest.raises(ValidationFailed) as exc_deny:
        render_grok_deny(forbidden_doc)
    assert exc_deny.value.code is ErrorCode.INTEGRATION_BOUNDARY_INVALID

    with pytest.raises(ValidationFailed) as exc_cfg:
        render_config_toml(_minimal_inputs(permissions=forbidden_doc))
    assert exc_cfg.value.code is ErrorCode.INTEGRATION_BOUNDARY_INVALID


def test_mcp_secret_refs_and_toml_scalar_table_collision() -> None:
    """MCP ``secret://`` refs stay literal, plaintext env fails, and TOML scalar/table collision fails."""
    cfg_df = render_config_toml(
        _minimal_inputs(
            mcp_servers={
                "skm": {
                    "enabled": True,
                    "type": "stdio",
                    "command": "skm",
                    "args": ["mcp"],
                    "env": {"SKM_API_TOKEN": "secret://env/SKM_API_TOKEN"},
                }
            }
        )
    )
    parsed = decode_document(cfg_df.managed_bytes.decode("utf-8"), "toml")
    mcp_tbl = cast("dict[str, Any]", parsed["mcp_servers"])
    assert mcp_tbl["skm"]["env"] == {"SKM_API_TOKEN": "secret://env/SKM_API_TOKEN"}

    with pytest.raises(ValidationFailed) as exc_secret:
        render_config_toml(
            _minimal_inputs(
                mcp_servers={
                    "bad": {
                        "enabled": True,
                        "command": "npx",
                        "env": {"API_KEY": "plaintext-token"},
                    }
                }
            )
        )
    assert exc_secret.value.code is ErrorCode.CONFIG_INVALID

    # Scalar vs table collision in pre-existing .grok/config.toml fails cleanly with BOUNDARY_INVALID.
    with pytest.raises(ValueError, match="INTEGRATION_BOUNDARY_INVALID"):
        merge_owned_toml(
            'mcp_servers = "scalar-not-a-table"\n',
            parse_toml(cfg_df.managed_bytes.decode("utf-8")),
            cfg_df.boundary.owned_keys,
        )

    obs_collided = observe_bytes(
        GROK_CONFIG_PATH,
        b'mcp_servers = "scalar-not-a-table"\n',
        cfg_df.boundary,
        is_symlink=False,
        has_conflict_file=False,
    )
    dec_collided = decide_file(cfg_df, None, obs_collided, safe=True)
    assert dec_collided.kind is FileDecisionKind.BOUNDARY_INVALID
    assert dec_collided.diagnostic == ErrorCode.INTEGRATION_BOUNDARY_INVALID.value


def test_capabilities_registry_and_doctor_layers(tmp_path: Path) -> None:
    """``GrokTarget`` capabilities report ``agents = unsupported`` honestly and read layers cleanly."""
    caps = load_capabilities()
    assert caps.target is TargetId.GROK
    assert caps.tested_client_version == "0.1.0"
    assert caps.verified_at == date(2026, 10, 26)
    assert caps.surfaces[Surface.AGENTS] is SurfaceSupport.UNSUPPORTED
    for supported in (
        Surface.INSTRUCTIONS,
        Surface.SKILLS,
        Surface.PERMISSIONS,
        Surface.HOOKS,
        Surface.MCP,
    ):
        assert caps.surfaces[supported] is SurfaceSupport.NATIVE
    assert len(caps.hook_surfaces) == 9

    reg = default_target_registry()
    assert isinstance(reg, StaticIntegrationTargetRegistry)
    target = reg.get(TargetId.GROK)
    assert isinstance(target, GrokTarget)
    assert target.instruction_paths() == (GROK_INSTRUCTIONS_PATH,)

    checkout = tmp_path / "repo"
    (checkout / ".git").mkdir(parents=True)
    (checkout / ".grok" / "hooks").mkdir(parents=True)
    (checkout / ".grok" / "config.toml").write_text('[permission]\ndeny = ["Read(.env*)"]\n', "utf-8")
    (checkout / ".grok" / "hooks" / "skm.json").write_text("{broken json\n", "utf-8")

    fs = LocalCheckoutFs(checkout, state_dir=tmp_path / "state")
    assert target.summarize_session({}, fs) is None

    home = _StubHomeReader({"grok.user_config": b'[ui]\npermission_mode = "ask"\n'})
    layers = {str(layer["layer"]): layer for layer in read_grok_layers(fs, home)}
    assert set(layers) == {"user", "project", "hooks"}
    assert layers["user"]["exists"] is True
    assert layers["user"]["valid"] is True
    assert layers["project"]["exists"] is True
    assert layers["project"]["valid"] is True
    assert layers["hooks"]["exists"] is True
    assert layers["hooks"]["valid"] is False
    assert layers["hooks"]["error"] == "invalid_json"

    bad_home = _StubHomeReader({"grok.user_config": b"permission = [unterminated\n"})
    bad_layers = read_grok_layers(fs, bad_home)
    assert bad_layers[0]["valid"] is False
    assert bad_layers[0]["error"] == "invalid_toml"

    with pytest.raises(NotFound):
        StaticIntegrationTargetRegistry({}).get(TargetId.GROK)
