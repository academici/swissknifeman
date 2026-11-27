"""Integration tests for Claude Code permissions, MCP SecretRef, hooks, capabilities, and layers (P10.02)."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import pytest

from skm.adapters.checkout_fs.local import LocalCheckoutFs
from skm.adapters.integrations.claude_code.doctor_layers import read_claude_layers
from skm.adapters.integrations.claude_code.hooks import (
    MAX_PROMPT_BYTES,
    normalize_hook_payload,
    render_hook_decision,
)
from skm.adapters.integrations.claude_code.mcp import render_mcp
from skm.adapters.integrations.claude_code.settings import (
    CLAUDE_DENY_FLOOR,
    default_mode_for_profile,
    render_claude_rules,
    render_local_settings,
)
from skm.adapters.integrations.claude_code.target import ClaudeCodeTarget, load_capabilities
from skm.adapters.integrations.registry import StaticIntegrationTargetRegistry, default_target_registry
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import ProjectId
from skm.kernel.json_types import JsonValue
from skm.modules.integrations.domain.desired import ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookEventKind, HookSurfaceId, NormalizedHookEvent
from skm.modules.integrations.domain.hook_rules import HookDecision, HookVerdict
from skm.modules.integrations.domain.profiles import PermissionProfile, resolve_profile
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetId
from skm.modules.policy.application.composition import builtin_profiles
from skm.modules.policy.public import (
    Allow,
    CommandMode,
    CommandRule,
    EnforcementMode,
    FileEdit,
    FileRead,
    FileWrite,
    NetworkMode,
    PathOrigin,
    PathPolicy,
    PathRule,
    PathScope,
    PermissionLayer,
    PermissionSet,
    RunCommand,
    ScopeRoots,
    StaticPathFacts,
    TaskAuthority,
    WebAccess,
    check_tool_call,
    is_subset,
    narrow,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
HOOK_EXAMPLES_DIR = REPO_ROOT / "tests/fixtures/corpus/examples" / "integrations" / "hook-payloads"
PROJ_ID = ProjectId(UUID("01928f6e-7a3b-7c41-9d2e-5b8a1f3c4d60"))


def _minimal_inputs(
    *,
    profile: PermissionProfile = PermissionProfile.WORKSPACE_CONTAINED,
    mcp_servers: dict[str, dict[str, Any]] | None = None,
) -> ProjectionInputs:
    return ProjectionInputs(
        project_id=PROJ_ID,
        target=TargetId.CLAUDE_CODE,
        instructions_core={"enabled": False},
        instructions_project={"enabled": False},
        skills=(),
        permissions={},
        profile=profile,
        hook_modes={},
        host_subscription_events=(),
        mcp_servers=mcp_servers or {},
        agents=(),
        inputs_digest="sha256:" + "0" * 64,
        config_generation=1,
        diagnostics=(),
    )


def _assert_rendered_rules_subset_of_permission_set(perms: PermissionSet) -> None:
    """Verify every allow rule emitted by ``render_claude_rules`` is permitted by ``perms``."""
    rules = render_claude_rules(perms)
    # 1. Deny floor is always present in full at the head of deny
    assert rules.deny[: len(CLAUDE_DENY_FLOOR)] == CLAUDE_DENY_FLOOR

    roots = ScopeRoots(
        worktrees={"main": "/wt"},
        materials="/materials",
        tmp="/scratch",
        home="/home/dev",
        safe_dirs=("/safe",),
        protected=("/wt/.skm", "/state"),
        remote_hosts=frozenset(),
    )
    facts = StaticPathFacts(
        origins_by_path={"/wt/src/app.py": frozenset({PathOrigin.TRACKED})},
        home="/home/dev",
    )
    authority = TaskAuthority(
        write_scope=None,
        delete_scope=(),
        operations=frozenset(),
        capabilities=frozenset(),
    )

    read_patterns: list[dict[str, str]] = []
    write_patterns: list[dict[str, str]] = []
    hosts: list[str] = []

    for rule in rules.allow:
        if m := re.fullmatch(r"Read\((.+)\)", rule):
            pat = m.group(1)
            assert not pat.startswith("~")
            assert not pat.startswith("/")
            read_patterns.append({"scope": "worktree", "pattern": pat})
            sample = "/wt/src/app.py" if pat == "**" else f"/wt/{pat.removesuffix('/**').lstrip('/')}/f.py"
            decision = check_tool_call(
                perms,
                FileRead(sample),
                roots=roots,
                facts=facts,
                authority=authority,
                mode=EnforcementMode.INTERACTIVE,
            )
            assert isinstance(decision, Allow), f"{rule} widened FileRead({sample}): {decision}"
        elif m := re.fullmatch(r"(Edit|Write)\((.+)\)", rule):
            kind, pat = m.group(1), m.group(2)
            assert not pat.startswith("~")
            assert not pat.startswith("/")
            write_patterns.append({"scope": "worktree", "pattern": pat})
            sample = "/wt/src/app.py" if pat == "**" else f"/wt/{pat.removesuffix('/**').lstrip('/')}/f.py"
            call = FileEdit(sample) if kind == "Edit" else FileWrite(sample)
            decision = check_tool_call(
                perms,
                call,
                roots=roots,
                facts=facts,
                authority=authority,
                mode=EnforcementMode.INTERACTIVE,
            )
            assert isinstance(decision, Allow), f"{rule} widened {call}: {decision}"
        elif m := re.fullmatch(r"Bash\((.+) \*\)", rule):
            prefix = m.group(1)
            for sample_cmd in (f"{prefix} --help", f"{prefix} status"):
                decision = check_tool_call(
                    perms,
                    RunCommand(sample_cmd, "/wt"),
                    roots=roots,
                    facts=facts,
                    authority=authority,
                    mode=EnforcementMode.INTERACTIVE,
                )
                assert isinstance(decision, Allow), f"{rule} widened RunCommand({sample_cmd!r}): {decision}"
        elif m := re.fullmatch(r"WebFetch\(domain:(.+)\)", rule):
            domain = m.group(1)
            hosts.append(domain)
            decision = check_tool_call(
                perms,
                WebAccess("web.fetch", f"https://{domain}/index.html", None),
                roots=roots,
                facts=facts,
                authority=authority,
                mode=EnforcementMode.INTERACTIVE,
            )
            assert isinstance(decision, Allow), f"{rule} widened WebAccess({domain}): {decision}"

    read_deny = [
        {"scope": "home", "pattern": m.group(1)[2:]}
        if m.group(1).startswith("~/")
        else {"scope": "worktree", "pattern": m.group(1)}
        for d in rules.deny
        if (m := re.fullmatch(r"Read\((.+)\)", d))
    ]
    write_deny_raw = [
        {"scope": "home", "pattern": m.group(2)[2:]}
        if m.group(2).startswith("~/")
        else {"scope": "worktree", "pattern": m.group(2)}
        for d in rules.deny
        if (m := re.fullmatch(r"(Edit|Write)\((.+)\)", d))
    ]
    write_deny = list({f"{p['scope']}:{p['pattern']}": p for p in write_deny_raw}.values())

    req_doc: dict[str, JsonValue] = {}
    fs_doc: dict[str, JsonValue] = {}
    if read_patterns:
        fs_doc["read"] = {"allow": read_patterns, "deny": read_deny}  # type: ignore[assignment]
    if write_patterns:
        dedup_w = list({p["pattern"]: p for p in write_patterns}.values())
        fs_doc["write"] = {"allow": dedup_w, "deny": write_deny}  # type: ignore[assignment]
    if fs_doc:
        req_doc["fs"] = fs_doc
    if hosts:
        req_doc["network"] = {"mode": "allowlist", "hosts": hosts}  # type: ignore[assignment]
    if req_doc:
        assert is_subset(req_doc, perms) == ()


def test_deny_floor_and_subset_invariant_across_builtin_and_narrowed_profiles() -> None:
    """``render_claude_rules(perms)`` always includes ``CLAUDE_DENY_FLOOR`` and never widens ``perms``."""
    profiles = builtin_profiles()
    for name in ("read-only", "workspace-contained", "trusted-full-access"):
        perms = profiles[name].permissions
        rules = render_claude_rules(perms)
        for floor_item in CLAUDE_DENY_FLOOR:
            assert floor_item in rules.deny
            assert floor_item not in rules.allow
        _assert_rendered_rules_subset_of_permission_set(perms)

    # Read-only profile emits zero Edit/Write/WebFetch allow rules and skips risky/networked commands
    ro_rules = render_claude_rules(profiles["read-only"].permissions)
    assert not any(r.startswith(("Edit(", "Write(", "WebFetch(")) for r in ro_rules.allow)
    assert "Bash(git status *)" in ro_rules.allow
    assert "Bash(git branch *)" not in ro_rules.allow
    assert "Bash(git reflog *)" not in ro_rules.allow
    assert "Bash(git ls-remote *)" not in ro_rules.allow
    assert "Bash(gh api *)" not in ro_rules.allow
    assert "Bash(gh search *)" not in ro_rules.allow
    assert "Bash(gh *:view *)" not in ro_rules.allow
    assert "Bash(hostname *)" not in ro_rules.allow
    assert "Bash(find *)" not in ro_rules.allow
    assert "Bash(env *)" not in ro_rules.allow

    # Narrowed workspace-contained with untrusted python + explicit allowlist + explicit fs deny
    from skm.modules.policy.domain.commands import CommandsLayer
    from skm.modules.policy.domain.network import NetworkLayer

    narrowed = narrow(
        profiles["workspace-contained"].permissions,
        PermissionLayer(
            source="test:narrow",
            fs_write=PathPolicy(
                allow=(PathRule(PathScope.WORKTREE, "src/**"),),
                deny=(PathRule(PathScope.WORKTREE, "src/secrets/**"),),
            ),
            commands=CommandsLayer(
                mode=CommandMode.ALLOWLIST,
                allow=(
                    CommandRule("python3", None),
                    CommandRule("sudo", None),
                    CommandRule("pytest", None),
                ),
            ),
            network=NetworkLayer(
                mode=NetworkMode.ALLOWLIST,
                hosts=frozenset({"pypi.org", "evil.example.org"}),
            ),
            tools=frozenset({"fs.read", "fs.edit", "shell.run", "web.fetch", "TodoWrite"}),
        ),
    )
    n_rules = render_claude_rules(narrowed)
    assert "Bash(pytest *)" in n_rules.allow
    assert "Bash(python3 *)" not in n_rules.allow  # inline interpreter untrusted
    assert "Bash(sudo *)" not in n_rules.allow  # blocked by deny_patterns & deny floor
    assert "Edit(src/**)" in n_rules.allow
    assert "Write(src/**)" not in n_rules.allow  # fs.write omitted from tools
    assert "Edit(src/secrets/**)" in n_rules.deny
    assert "Write(src/secrets/**)" in n_rules.deny
    assert "WebFetch(domain:pypi.org)" in n_rules.allow
    assert "WebFetch(domain:evil.example.org)" not in n_rules.allow  # not in base host allowlist
    _assert_rendered_rules_subset_of_permission_set(narrowed)


def test_profile_modes_and_trusted_full_access_host_gate() -> None:
    """``permissions.defaultMode`` maps profiles accurately and refuses unapproved ``trusted_full_access``."""
    assert default_mode_for_profile(PermissionProfile.OBSERVE) == "default"
    assert default_mode_for_profile(PermissionProfile.WORKSPACE_CONTAINED) == "acceptEdits"
    assert default_mode_for_profile(PermissionProfile.TRUSTED_FULL_ACCESS) == "bypassPermissions"

    refused = resolve_profile(PermissionProfile.TRUSTED_FULL_ACCESS, host_allows_trusted=False)
    assert refused.profile is PermissionProfile.WORKSPACE_CONTAINED
    assert len(refused.diagnostics) == 1
    assert refused.diagnostics[0].code is ErrorCode.INTEGRATION_TRUSTED_REFUSED
    df_refused = render_local_settings(_minimal_inputs(profile=refused.profile))
    assert json.loads(df_refused.managed_bytes) == {"permissions": {"defaultMode": "acceptEdits"}}

    allowed = resolve_profile(PermissionProfile.TRUSTED_FULL_ACCESS, host_allows_trusted=True)
    assert allowed.profile is PermissionProfile.TRUSTED_FULL_ACCESS
    df_allowed = render_local_settings(_minimal_inputs(profile=allowed.profile))
    assert json.loads(df_allowed.managed_bytes) == {"permissions": {"defaultMode": "bypassPermissions"}}


def test_mcp_secret_ref_preserved_and_plaintext_rejected() -> None:
    """``.mcp.json`` keeps ``secret://...`` strings verbatim and rejects literal secret values."""
    df = render_mcp(
        _minimal_inputs(
            mcp_servers={
                "skm": {"enabled": True, "command": "skm", "args": ["mcp", "serve"]},
                "github": {
                    "enabled": True,
                    "command": "gh-mcp",
                    "env_refs": {"GITHUB_TOKEN": "secret://env/GITHUB_TOKEN"},
                },
                "disabled-srv": {"enabled": False, "command": "noop"},
            }
        )
    )
    assert df is not None
    doc = json.loads(df.managed_bytes)
    assert set(doc["mcpServers"]) == {"github", "skm"}
    assert doc["mcpServers"]["github"]["env"] == {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}

    with pytest.raises(ValidationFailed) as exc_info:
        render_mcp(
            _minimal_inputs(
                mcp_servers={
                    "bad": {
                        "enabled": True,
                        "command": "gh-mcp",
                        "env_refs": {"GITHUB_TOKEN": "ghp_plaintext_token"},
                    }
                }
            )
        )
    assert exc_info.value.code is ErrorCode.CONFIG_INVALID


def test_hook_payload_normalization_and_decision_rendering_against_spec_examples() -> None:
    """All 7 Claude Code hook event shapes + spec example payloads normalize and render cleanly."""
    target = ClaudeCodeTarget()

    # 1. Spec example: claude-pre-tool-use.json -> claude-pre-tool-use.normalized.json
    raw_pre = json.loads((HOOK_EXAMPLES_DIR / "claude-pre-tool-use.json").read_text("utf-8"))
    expected_norm = json.loads((HOOK_EXAMPLES_DIR / "claude-pre-tool-use.normalized.json").read_text("utf-8"))
    norm = target.normalize_hook_payload("PreToolUse", raw_pre)
    assert norm == NormalizedHookEvent(
        target=TargetId(expected_norm["target"]),
        kind=HookEventKind(expected_norm["kind"]),
        session_id=expected_norm["session_id"],
        cwd=expected_norm["cwd"],
        tool_name=expected_norm["tool_name"],
        command=expected_norm["command"],
        paths=tuple(expected_norm["paths"]),
        prompt=expected_norm["prompt"],
        stop_status=expected_norm["stop_status"],
        raw_event_name=expected_norm["raw_event_name"],
    )

    # Spec example decision: claude-pre-tool-use.decision.json
    expected_dec = json.loads((HOOK_EXAMPLES_DIR / "claude-pre-tool-use.decision.json").read_text("utf-8"))
    out = target.render_hook_decision(
        norm,
        HookDecision(
            verdict=HookVerdict.DENY,
            surface=HookSurfaceId.GIT_GUARDRAILS,
            reason_code=expected_dec["reason_code"],
            user_message=expected_dec["user_message"],
            agent_message=expected_dec["agent_message"],
            additional_context=None,
        ),
    )
    assert out == expected_dec["client_output"]

    # 2. Spec invalid-payload.json -> HOOK_PAYLOAD_INVALID
    bad_payload = json.loads((HOOK_EXAMPLES_DIR / "invalid-payload.json").read_text("utf-8"))
    with pytest.raises(ValidationFailed) as bad_exc:
        target.normalize_hook_payload("PreToolUse", bad_payload)
    assert bad_exc.value.code is ErrorCode.HOOK_PAYLOAD_INVALID

    # 3. Remaining Claude Code events from spec §4.7 table
    ev_start = normalize_hook_payload(
        "SessionStart",
        {"session_id": "s1", "cwd": "/repo", "hook_event_name": "SessionStart", "source": "startup"},
    )
    assert ev_start.kind is HookEventKind.SESSION_START

    long_prompt = "я" * 3000  # 6000 UTF-8 bytes -> truncated to <= 4096 UTF-8 bytes
    ev_prompt = normalize_hook_payload(
        "UserPromptSubmit",
        {"session_id": "s1", "cwd": "/repo", "prompt": long_prompt},
    )
    assert ev_prompt.kind is HookEventKind.USER_PROMPT
    assert ev_prompt.prompt is not None
    assert len(ev_prompt.prompt.encode("utf-8")) <= MAX_PROMPT_BYTES

    ev_edit = normalize_hook_payload(
        "PreToolUse",
        {
            "session_id": "s1",
            "cwd": "/repo",
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": "/repo/src/a.py",
                "edits": [{"file_path": "/repo/src/b.py"}, {"file_path": "/outside/c.py"}],
            },
        },
    )
    assert ev_edit.kind is HookEventKind.PRE_TOOL
    assert ev_edit.tool_name == "edit"
    assert ev_edit.paths == ("src/a.py", "src/b.py", "/outside/c.py")

    ev_write = normalize_hook_payload(
        "PostToolUse",
        {
            "session_id": "s1",
            "cwd": "/repo",
            "tool_name": "Write",
            "tool_input": {"file_path": "/repo/README.md"},
            "tool_response": {"ok": True},
        },
    )
    assert ev_write.kind is HookEventKind.POST_TOOL
    assert ev_write.tool_name == "write"
    assert ev_write.paths == ("README.md",)

    ev_mcp = normalize_hook_payload(
        "PreToolUse",
        {"session_id": "s1", "cwd": "/repo", "tool_name": "mcp__skm__memory_search", "tool_input": {}},
    )
    assert ev_mcp.tool_name == "mcp:skm:memory_search"

    ev_sub = normalize_hook_payload("SubagentStop", {"session_id": "s1", "stop_hook_active": False})
    assert ev_sub.kind is HookEventKind.SUBAGENT_STOP

    ev_end = normalize_hook_payload("SessionEnd", {"session_id": "s1", "reason": "completed"})
    assert ev_end.kind is HookEventKind.SESSION_END
    assert ev_end.stop_status == "completed"

    # 4. Verdicts: ASK, CONTEXT, ALLOW, NONE
    ask_out = render_hook_decision(
        norm,
        HookDecision(HookVerdict.ASK, HookSurfaceId.SUBSCRIPTIONS, "UNTRUSTED", "Confirm?", "Confirm?", None),
    )
    assert ask_out["stdout"] == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "Confirm?",
        },
        "systemMessage": "Confirm?",
    }

    ctx_out = render_hook_decision(
        ev_start,
        HookDecision(
            HookVerdict.CONTEXT,
            HookSurfaceId.SESSION_CONTEXT,
            None,
            None,
            None,
            "Active leaf: P10.02",
        ),
    )
    assert ctx_out == {
        "exit_code": 0,
        "stdout": {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "Active leaf: P10.02",
            }
        },
        "stderr": "",
    }

    for silent_verdict in (HookVerdict.ALLOW, HookVerdict.NONE):
        silent_out = render_hook_decision(
            norm, HookDecision(silent_verdict, HookSurfaceId.COMMAND_LOG, None, None, None, None)
        )
        assert silent_out == {"exit_code": 0, "stdout": "", "stderr": ""}


class _StubHomeReader:
    def __init__(self, payloads: dict[str, bytes | None]) -> None:
        self._payloads = payloads

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
        return self._payloads.get(logical)


def test_capabilities_registry_and_doctor_layers(tmp_path: Path) -> None:
    """Capabilities manifest, target registry, and read-only layer reader satisfy port contracts."""
    caps = load_capabilities()
    assert caps.target is TargetId.CLAUDE_CODE
    assert caps.tested_client_version == "2.1.220"
    assert caps.verified_at == date(2026, 8, 2)
    assert dict(caps.surfaces) == dict.fromkeys(Surface, SurfaceSupport.NATIVE)
    assert len(caps.hook_surfaces) == 9

    reg = default_target_registry()
    assert isinstance(reg, StaticIntegrationTargetRegistry)
    target = reg.get(TargetId.CLAUDE_CODE)
    assert target.instruction_paths() == ("CLAUDE.md",)

    checkout = tmp_path / "repo"
    (checkout / ".git").mkdir(parents=True)
    (checkout / ".gitignore").write_text(".claude/settings.local.json\n", encoding="utf-8")
    (checkout / ".claude").mkdir(parents=True)
    (checkout / ".claude" / "settings.json").write_text('{"permissions": {"allow": []}}\n', "utf-8")
    (checkout / ".claude" / "settings.local.json").write_text("{bad json\n", "utf-8")

    fs = LocalCheckoutFs(checkout, state_dir=tmp_path / "state")
    assert target.summarize_session({}, fs) is None

    home = _StubHomeReader(
        {
            "claude.user_settings": b'{"permissions": {"defaultMode": "default"}}\n',
            "claude.managed_settings": None,
            "vscode.user_settings": b'{"claudeCode.initialPermissionMode": "default"}\n',
        }
    )
    layers = read_claude_layers(fs, home)
    by_id = {str(layer["layer"]): layer for layer in layers}
    assert set(by_id) == {"user", "project", "local", "managed", "vscode"}
    assert by_id["user"]["exists"] is True
    assert by_id["user"]["valid"] is True
    assert by_id["project"]["exists"] is True
    assert by_id["project"]["valid"] is True
    assert by_id["local"]["exists"] is True
    assert by_id["local"]["valid"] is False
    assert by_id["local"]["error"] == "invalid_json"
    assert by_id["managed"]["exists"] is False
    assert by_id["managed"]["valid"] is True
    assert by_id["vscode"]["exists"] is True
    assert by_id["vscode"]["valid"] is True

    assert reg.get(TargetId.GROK).target_id is TargetId.GROK
    with pytest.raises(NotFound):
        StaticIntegrationTargetRegistry({}).get(TargetId.GROK)
