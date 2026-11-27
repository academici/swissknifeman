"""Unit and integration tests for Cursor permissions, camelCase hooks, capabilities, and layers (P10.04.a)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest

from skm.adapters.checkout_fs.local import LocalCheckoutFs
from skm.adapters.integrations.cursor.hooks import (
    CURSOR_HOOK_EVENTS,
    normalize_hook_payload,
    render_hook_decision,
    render_hook_entries,
)
from skm.adapters.integrations.cursor.instructions import CURSOR_INSTRUCTIONS_PATH
from skm.adapters.integrations.cursor.mcp import render_mcp
from skm.adapters.integrations.cursor.permissions import (
    CURSOR_DENY_FLOOR,
    render_cli_permissions,
    render_cursor_rules,
    render_ide_permissions,
    validate_no_cli_mode_keys,
)
from skm.adapters.integrations.cursor.target import CursorTarget
from skm.adapters.integrations.registry import StaticIntegrationTargetRegistry, default_target_registry
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import ProjectId
from skm.kernel.json_types import JsonObject
from skm.modules.integrations.domain.desired import HostSubscriptionEvent, ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookClass, HookEventKind, HookSurfaceId
from skm.modules.integrations.domain.hook_rules import HookDecision, HookMode, HookVerdict
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetId

REPO_ROOT = Path(__file__).resolve().parents[4]
HOOK_EXAMPLES = REPO_ROOT / "tests/fixtures/corpus/examples" / "integrations" / "hook-payloads"
PROJ_ID = ProjectId(UUID("01928f6e-7a3b-7c41-9d2e-5b8a1f3c4d60"))


class _StubHomeReader:
    def __init__(self, files: dict[str, bytes | None]) -> None:
        self._files = files

    def read(
        self,
        logical: Literal[
            "claude.user_settings",
            "claude.managed_settings",
            "codex.user_config",
            "gemini.user_settings",
            "vscode.user_settings",
        ],
    ) -> bytes | None:
        return self._files.get(logical)


def _minimal_inputs(**overrides: object) -> ProjectionInputs:
    defaults: dict[str, object] = {
        "project_id": PROJ_ID,
        "target": TargetId.CURSOR,
        "instructions_core": {},
        "instructions_project": {},
        "skills": (),
        "permissions": {},
        "profile": PermissionProfile.WORKSPACE_CONTAINED,
        "hook_modes": {},
        "host_subscription_events": (),
        "mcp_servers": {},
        "agents": (),
        "inputs_digest": "sha256:" + "0" * 64,
        "config_generation": 1,
        "diagnostics": (),
    }
    defaults.update(overrides)
    return ProjectionInputs(**defaults)  # type: ignore[arg-type]


def test_normative_cursor_before_shell_fixture_roundtrip() -> None:
    """``cursor-before-shell.json`` normalizes and renders decision byte-for-byte with spec examples."""
    raw_payload = json.loads((HOOK_EXAMPLES / "cursor-before-shell.json").read_text("utf-8"))
    expected_norm = json.loads((HOOK_EXAMPLES / "cursor-before-shell.normalized.json").read_text("utf-8"))
    expected_dec = json.loads((HOOK_EXAMPLES / "cursor-before-shell.decision.json").read_text("utf-8"))

    event = normalize_hook_payload("beforeShellExecution", raw_payload)
    wire_event: JsonObject = {
        "schema": "urn:skm:integrations:defs:v1#/$defs/hook_event",
        "target": event.target.value,
        "kind": event.kind.value,
        "session_id": event.session_id,
        "cwd": event.cwd,
        "tool_name": event.tool_name,
        "command": event.command,
        "paths": list(event.paths),
        "prompt": event.prompt,
        "stop_status": event.stop_status,
        "raw_event_name": event.raw_event_name,
    }
    assert wire_event == expected_norm

    decision = HookDecision(
        verdict=HookVerdict(expected_dec["verdict"]),
        surface=HookSurfaceId(expected_dec["surface"]),
        reason_code=expected_dec["reason_code"],
        user_message=expected_dec["user_message"],
        agent_message=expected_dec["agent_message"],
        additional_context=expected_dec.get("additional_context"),
    )
    rendered = render_hook_decision(event, decision)
    assert rendered == expected_dec["client_output"]


def test_normalize_all_seven_cursor_camelcase_events() -> None:
    """All 7 Cursor camelCase hook events normalize to canonical ``NormalizedHookEvent``."""
    assert len(CURSOR_HOOK_EVENTS) == 7

    ev_start = normalize_hook_payload(
        "sessionStart",
        {
            "hook_event_name": "sessionStart",
            "conversation_id": "c-1",
            "session_id": "s-1",
            "workspace_roots": ["/repo"],
        },
    )
    assert ev_start.kind is HookEventKind.SESSION_START
    assert ev_start.session_id == "s-1"
    assert ev_start.cwd == "/repo"

    ev_after_shell = normalize_hook_payload(
        "afterShellExecution",
        {
            "hook_event_name": "afterShellExecution",
            "conversation_id": "c-1",
            "command": "pytest -q",
            "duration": 1.25,
            "sandbox": True,
            "workspace_roots": ["/repo"],
        },
    )
    assert ev_after_shell.kind is HookEventKind.POST_SHELL
    assert ev_after_shell.tool_name == "shell"
    assert ev_after_shell.command == "pytest -q"
    assert ev_after_shell.cwd == "/repo"

    ev_write = normalize_hook_payload(
        "preToolUse",
        {
            "hook_event_name": "preToolUse",
            "conversation_id": "c-1",
            "cwd": "/repo",
            "tool_name": "Write",
            "tool_input": {"path": "/repo/src/app.py"},
        },
    )
    assert ev_write.kind is HookEventKind.PRE_TOOL
    assert ev_write.tool_name == "write"
    assert ev_write.paths == ("src/app.py",)

    ev_delete = normalize_hook_payload(
        "preToolUse",
        {
            "hook_event_name": "preToolUse",
            "conversation_id": "c-1",
            "cwd": "/repo",
            "tool_name": "Delete",
            "tool_input": {"file_path": "old.txt"},
        },
    )
    assert ev_delete.tool_name == "delete"
    assert ev_delete.paths == ("old.txt",)

    ev_task = normalize_hook_payload(
        "preToolUse",
        {
            "hook_event_name": "preToolUse",
            "conversation_id": "c-1",
            "cwd": "/repo",
            "tool_name": "Task",
            "tool_input": {"prompt": "inspect"},
        },
    )
    assert ev_task.tool_name == "task"
    assert ev_task.paths == ()

    ev_mcp = normalize_hook_payload(
        "preToolUse",
        {
            "hook_event_name": "preToolUse",
            "conversation_id": "c-1",
            "cwd": "/repo",
            "tool_name": "MCP:skm:memory_search",
            "tool_input": {"query": "hooks"},
        },
    )
    assert ev_mcp.tool_name == "mcp:skm:memory_search"

    ev_sub_stop = normalize_hook_payload(
        "subagentStop",
        {
            "hook_event_name": "subagentStop",
            "conversation_id": "c-1",
            "status": "completed",
            "loop_count": 1,
        },
    )
    assert ev_sub_stop.kind is HookEventKind.SUBAGENT_STOP
    assert ev_sub_stop.stop_status == "completed"

    ev_stop = normalize_hook_payload(
        "stop",
        {
            "hook_event_name": "stop",
            "conversation_id": "c-1",
            "status": "completed",
            "loop_count": 0,
        },
    )
    assert ev_stop.kind is HookEventKind.STOP
    assert ev_stop.stop_status == "completed"

    ev_end = normalize_hook_payload(
        "sessionEnd",
        {
            "hook_event_name": "sessionEnd",
            "conversation_id": "c-1",
            "reason": "completed",
        },
    )
    assert ev_end.kind is HookEventKind.SESSION_END
    assert ev_end.stop_status == "completed"


@pytest.mark.parametrize(
    ("event_name", "payload"),
    [
        ("unknownEvent", {"hook_event_name": "unknownEvent", "conversation_id": "c-1"}),
        ("sessionStart", {"hook_event_name": "sessionEnd", "conversation_id": "c-1", "session_id": "s-1"}),
        ("sessionStart", {"hook_event_name": "sessionStart", "conversation_id": "c-1"}),
        (
            "beforeShellExecution",
            {"hook_event_name": "beforeShellExecution", "conversation_id": "c-1", "command": "ls"},
        ),
        (
            "afterShellExecution",
            {
                "hook_event_name": "afterShellExecution",
                "conversation_id": "c-1",
                "cwd": "/repo",
                "command": "ls",
                "duration": True,
                "sandbox": False,
            },
        ),
        (
            "preToolUse",
            {
                "hook_event_name": "preToolUse",
                "conversation_id": "c-1",
                "cwd": "/repo",
                "tool_name": "Write",
                "tool_input": {},
            },
        ),
        (
            "preToolUse",
            {
                "hook_event_name": "preToolUse",
                "conversation_id": "c-1",
                "cwd": "/repo",
                "tool_name": "MCP:broken",
                "tool_input": {},
            },
        ),
        (
            "stop",
            {"hook_event_name": "stop", "conversation_id": "c-1", "status": "completed", "loop_count": True},
        ),
        ("sessionEnd", {"hook_event_name": "sessionEnd", "conversation_id": "c-1"}),
    ],
)
def test_invalid_hook_payloads_fail_closed(event_name: str, payload: dict[str, object]) -> None:
    """Missing or mistyped Cursor hook payload fields fail closed with ``HOOK_PAYLOAD_INVALID``."""
    with pytest.raises(ValidationFailed) as exc_info:
        normalize_hook_payload(event_name, payload)  # type: ignore[arg-type]
    assert exc_info.value.code is ErrorCode.HOOK_PAYLOAD_INVALID


def test_hook_decisions_and_loop_limits() -> None:
    """Cursor hook decisions emit exit 0 + JSON permission; subagentStop/stop set loop_limit=3."""
    pre_shell = normalize_hook_payload(
        "beforeShellExecution",
        {
            "hook_event_name": "beforeShellExecution",
            "conversation_id": "c-1",
            "command": "git push --force",
            "cwd": "/repo",
        },
    )
    post_shell = normalize_hook_payload(
        "afterShellExecution",
        {
            "hook_event_name": "afterShellExecution",
            "conversation_id": "c-1",
            "command": "git status",
            "cwd": "/repo",
            "duration": 0.2,
            "sandbox": True,
        },
    )

    ask_out = render_hook_decision(
        pre_shell,
        HookDecision(
            verdict=HookVerdict.ASK,
            surface=HookSurfaceId.GIT_GUARDRAILS,
            reason_code="git.force_push",
            user_message="Confirm push",
            agent_message="Confirm push",
            additional_context=None,
        ),
    )
    assert ask_out == {
        "exit_code": 0,
        "stdout": {"permission": "ask", "user_message": "Confirm push", "agent_message": "Confirm push"},
        "stderr": "",
    }

    ctx_out = render_hook_decision(
        pre_shell,
        HookDecision(
            verdict=HookVerdict.CONTEXT,
            surface=HookSurfaceId.SESSION_CONTEXT,
            reason_code=None,
            user_message=None,
            agent_message=None,
            additional_context="Active leaf: P10.04.a",
        ),
    )
    assert ctx_out == {
        "exit_code": 0,
        "stdout": {"permission": "allow", "agent_message": "Active leaf: P10.04.a"},
        "stderr": "",
    }

    none_pre = render_hook_decision(
        pre_shell,
        HookDecision(
            verdict=HookVerdict.NONE,
            surface=HookSurfaceId.SAFE_DIRS,
            reason_code=None,
            user_message=None,
            agent_message=None,
            additional_context=None,
        ),
    )
    assert none_pre == {"exit_code": 0, "stdout": {"permission": "allow"}, "stderr": ""}

    none_obs = render_hook_decision(
        post_shell,
        HookDecision(
            verdict=HookVerdict.NONE,
            surface=HookSurfaceId.COMMAND_LOG,
            reason_code=None,
            user_message=None,
            agent_message=None,
            additional_context=None,
        ),
    )
    assert none_obs == {"exit_code": 0, "stdout": "", "stderr": ""}

    entries = render_hook_entries(
        _minimal_inputs(
            hook_modes={HookSurfaceId.REVIEW_GATE: HookMode.STRICT},
            host_subscription_events=(HostSubscriptionEvent(HookEventKind.STOP, (HookClass.WORKFLOW,)),),
        )
    )
    assert entries["subagentStop"][0]["loop_limit"] == 3
    assert entries["stop"][0]["loop_limit"] == 3


@pytest.mark.parametrize(
    "forbidden_doc",
    [
        {"approvalMode": "yolo"},
        {"sandbox": "disabled"},
        {"approval_mode": "auto"},
        {"sandbox_mode": "workspace-write"},
        {"permissions": {"approvalMode": "allowlist"}},
        {"permissions": {"sandbox": True}},
    ],
)
def test_cli_mode_keys_refused_in_project_projection(forbidden_doc: dict[str, object]) -> None:
    """Project ``.cursor/cli.json`` refuses ``approvalMode`` and ``sandbox`` keys."""
    with pytest.raises(ValidationFailed) as exc_direct:
        validate_no_cli_mode_keys(forbidden_doc)
    assert exc_direct.value.code is ErrorCode.INTEGRATION_BOUNDARY_INVALID

    with pytest.raises(ValidationFailed) as exc_render:
        render_cli_permissions(_minimal_inputs(permissions=forbidden_doc))
    assert exc_render.value.code is ErrorCode.INTEGRATION_BOUNDARY_INVALID


def test_permission_narrowing_profiles_and_mcp_secret_guard() -> None:
    """``render_cursor_rules`` enforces ``CURSOR_DENY_FLOOR``, profile bounds, and MCP SecretRef rules."""
    obs_rules = render_cursor_rules(
        {
            "fs_read": [{"allow": [{"scope": "worktree", "pattern": "**"}], "deny": []}],
            "fs_write": [{"allow": [{"scope": "worktree", "pattern": "src/**"}], "deny": []}],
            "commands": {"mode": "allowlist", "allow": ["git status", "rm -rf /"]},
            "tools": [["fs.read", "fs.write", "shell.run", "mcp:skm/*"]],
        },
        profile=PermissionProfile.OBSERVE,
    )
    assert all(not r.startswith("Write(") for r in obs_rules.allow)
    assert "Shell(git status)" in obs_rules.allow
    assert all("rm" not in r for r in obs_rules.allow)
    assert "Mcp(skm:*_recall)" in obs_rules.allow
    for floor_rule in CURSOR_DENY_FLOOR:
        assert floor_rule in obs_rules.deny

    ide_trusted = render_ide_permissions(_minimal_inputs(profile=PermissionProfile.TRUSTED_FULL_ACCESS))
    ide_doc = json.loads(ide_trusted.managed_bytes.decode("utf-8"))
    assert "autoRun" not in ide_doc
    assert ide_doc["mcpAllowlist"] == ["*:*"]
    assert ide_doc["terminalAllowlist"] == ["*"]

    with pytest.raises(ValidationFailed) as exc_mcp:
        render_mcp(
            _minimal_inputs(
                mcp_servers={
                    "bad": {
                        "enabled": True,
                        "command": "npx",
                        "env": {"API_KEY": "plaintext-secret"},
                    }
                }
            )
        )
    assert exc_mcp.value.code is ErrorCode.CONFIG_INVALID


def test_capabilities_registry_and_doctor_layers(tmp_path: Path) -> None:
    """``CursorTarget`` capabilities, registry lookup, and read-only ``client_layers`` match §4.8."""
    reg = default_target_registry()
    target = reg.get(TargetId.CURSOR)
    assert isinstance(target, CursorTarget)
    assert target.instruction_paths() == (CURSOR_INSTRUCTIONS_PATH,)

    caps = target.capabilities()
    assert caps.target is TargetId.CURSOR
    assert caps.tested_client_version == "2026.09.15-d2fe57e"
    assert caps.verified_at == date(2026, 10, 26)
    for surface in Surface:
        assert caps.surfaces[surface] is SurfaceSupport.NATIVE

    checkout = tmp_path / "checkout"
    (checkout / ".cursor").mkdir(parents=True)
    (checkout / ".claude").mkdir(parents=True)
    (checkout / ".cursor/cli.json").write_text('{"permissions": {"allow": [], "deny": []}}\n', "utf-8")
    (checkout / ".cursor/hooks.json").write_text("{ broken json\n", "utf-8")
    (checkout / ".claude/settings.json").write_text('{"hooks": {}}\n', "utf-8")

    fs = LocalCheckoutFs(checkout, state_dir=tmp_path / "state")
    home = _StubHomeReader(
        {
            "claude.user_settings": b'{"permissions": {"allow": ["Bash(ls *)"]}}\n',
            "vscode.user_settings": None,
        }
    )
    layers = {layer["layer"]: layer for layer in target.client_layers(fs, home)}
    assert layers["cli"]["exists"] is True
    assert layers["cli"]["valid"] is True
    assert layers["hooks"]["exists"] is True
    assert layers["hooks"]["valid"] is False
    assert layers["hooks"]["error"] == "invalid_json"
    assert layers["claude_user"]["exists"] is True
    assert layers["claude_project"]["exists"] is True
    assert layers["vscode"]["exists"] is False

    assert reg.get(TargetId.GROK).target_id is TargetId.GROK
    with pytest.raises(NotFound):
        StaticIntegrationTargetRegistry({}).get(TargetId.GROK)
