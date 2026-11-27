"""Native Claude and Gemini hook contracts for P04."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from skm.adapters.checkout_fs.local import LocalCheckoutFs
from skm.adapters.checkout_fs.user_home import LocalUserHomeReader
from skm.adapters.integrations.claude_code import hooks as claude
from skm.adapters.integrations.gemini_cli.target import GeminiCliTarget
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.contracts import UserHomeSelector
from skm.modules.integrations.domain.desired import HostSubscriptionEvent
from skm.modules.integrations.domain.hook_events import HookClass, HookEventKind, HookSurfaceId
from skm.modules.integrations.domain.hook_rules import HookDecision, HookMode, HookVerdict
from skm.modules.integrations.domain.ownership import Ownership
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.ports import UserHomeReader
from unit.adapters.integrations.test_skill_invocation_rendering import _inputs

_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures/integrations/gemini-cli/0.71.1/hooks.json"
_DENY = HookDecision(HookVerdict.DENY, HookSurfaceId.SAFE_DIRS, None, None, "guard refused", None)


def test_gemini_versioned_tool_hooks(tmp_path: Path) -> None:
    fixture = json.loads(_FIXTURE.read_text())
    target = GeminiCliTarget()
    assert target.capabilities().tested_client_version == fixture["client_version"]
    assert target.instruction_paths() == ("AGENTS.md", "GEMINI.md")
    inputs = replace(
        _inputs(TargetId.GEMINI_CLI),
        instructions_project={"enabled": True, "zero_shadowing": False, "content": "Project guidance"},
    )
    files = target.render(inputs)
    assert ".gemini/settings.json" in {file.relative_path for file in files}
    assert all(file.relative_path != "GEMINI.md" for file in files)
    instructions = next(file for file in files if file.relative_path == "AGENTS.md")
    assert instructions.boundary.ownership is Ownership.MANAGED_BLOCK
    assert b"Project guidance" in instructions.managed_bytes
    settings = next(file for file in files if file.surface is Surface.PERMISSIONS)
    assert settings.boundary.ownership is Ownership.MERGED_JSON
    actual = json.loads(settings.managed_bytes)
    assert actual["context"] == fixture["settings"]["context"]
    assert actual["advanced"] == fixture["settings"]["advanced"]
    for name, timeout in fixture["settings"]["timeouts_ms"].items():
        assert actual["hooks"][name][0]["hooks"][0]["timeout"] == timeout
    before_write, before_shell, after = fixture["payloads"]
    write = target.normalize_hook_payload("BeforeTool", before_write)
    assert (write.kind, write.paths) == (HookEventKind.PRE_TOOL, ("/checkout/.env",))
    assert target.render_hook_decision(write, _DENY) == {
        "exit_code": 2,
        "stdout": "",
        "stderr": "guard refused",
    }
    shell = target.normalize_hook_payload("BeforeTool", before_shell)
    assert (shell.kind, shell.command) == (HookEventKind.PRE_SHELL, "git status")
    edit = target.normalize_hook_payload("AfterTool", after)
    assert (edit.kind, edit.paths) == (HookEventKind.POST_TOOL, ("/checkout/lib/main.dart",))
    context = replace(_DENY, verdict=HookVerdict.CONTEXT, additional_context="Dart analysis failed")
    assert target.render_hook_decision(edit, context)["stdout"] == {
        "hookSpecificOutput": {"additionalContext": "Dart analysis failed"}
    }
    with pytest.raises(ValidationFailed):
        target.normalize_hook_payload("AfterTool", {**after, "tool_response": None})

    project, home = tmp_path / "project", tmp_path / "home"
    for root in (project, home):
        (root / ".gemini").mkdir(parents=True)
    (project / ".gemini/settings.json").write_bytes(settings.managed_bytes)
    user_file = home / ".gemini/settings.json"
    user_file.write_text('{"context":{"fileName":"LOCAL.md"}}')
    local_reader = LocalUserHomeReader(home)
    user_layer, project_layer = target.client_layers(LocalCheckoutFs(project), local_reader)
    assert user_layer["data"] == {"context": {"fileName": "LOCAL.md"}}
    assert project_layer["data"] == actual

    class ReadOnlyHome:
        def read(self, logical: UserHomeSelector) -> bytes | None:
            assert logical == "gemini.user_settings"
            return local_reader.read(logical)

    reader: UserHomeReader = ReadOnlyHome()
    assert target.client_layers(LocalCheckoutFs(project), reader)[0] == user_layer
    user_file.unlink()
    user_file.symlink_to(project / ".gemini/settings.json")
    assert target.client_layers(LocalCheckoutFs(project), LocalUserHomeReader(home))[0]["valid"] is False


def test_claude_stop_and_pre_tool_bindings() -> None:
    inputs = replace(
        _inputs(TargetId.CLAUDE_CODE),
        hook_modes={HookSurfaceId.SAFE_DIRS: HookMode.STRICT},
        host_subscription_events=(
            HostSubscriptionEvent(HookEventKind.POST_TOOL, (HookClass.WORKFLOW,)),
            HostSubscriptionEvent(HookEventKind.STOP, (HookClass.ENFORCEMENT,)),
        ),
    )
    bound = cast("dict[str, list[dict[str, Any]]]", claude.render_hook_entries(inputs))
    pre = bound["PreToolUse"][0]
    assert pre["matcher"] == "Edit|Write|MultiEdit|Bash"
    assert pre["hooks"][0]["onFailure"] == "block"
    assert "--class workflow" in bound["PostToolUse"][0]["hooks"][0]["command"]
    stop = bound["Stop"][0]["hooks"][0]
    assert "--class enforcement" in stop["command"]
    assert "onFailure" not in stop
    event = claude.normalize_hook_payload(
        "Stop", {"session_id": "s", "stop_hook_active": False, "cwd": "/checkout"}
    )
    assert (event.kind, event.stop_status) == (HookEventKind.STOP, "idle")
    assert claude.render_hook_decision(event, _DENY)["stdout"] == {
        "decision": "block",
        "reason": "guard refused",
    }
