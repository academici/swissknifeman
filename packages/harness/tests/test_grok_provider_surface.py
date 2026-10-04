"""Grok project surfaces follow Grok's own hook and config contract."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import EffectiveProvider, ProviderId
from harness.grok_render import render_grok_config_toml
from harness.hooks import (LifecycleRequest, plan_codex_lifecycle_artifacts, plan_lifecycle,
                           render_codex_hook_handler, render_codex_hooks)
from harness.profiles import load_catalog, resolve_profile
from harness.provider_render import render_profile


PACKAGE = Path(__file__).resolve().parents[1]
CATALOG = PACKAGE / "configs/common/profile-catalog.json"
PROFILE_BINDINGS = PACKAGE / "configs/grok/config/profile-bindings.json"
HOOK_BINDINGS = PACKAGE / "configs/grok/hooks/lifecycle-context-bindings.json"


def effective(provider_id):
    return EffectiveProvider(provider_id, True)


class GrokProviderSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(CATALOG)

    def _resolve(self, profile_id, **extra):
        return resolve_profile(
            self.catalog, provider_id=ProviderId.GROK, profile_id=profile_id,
            target_scope="project", trusted=True, origin="operation",
            effective_provider=effective(ProviderId.GROK), **extra)

    def test_project_config_is_deny_floor_without_ui_mode(self):
        resolution = self._resolve("workspace-contained")
        self.assertTrue(resolution.green)
        rendered = render_profile(resolution, codex_bindings_path=PROFILE_BINDINGS).decode()
        self.assertEqual(rendered, render_grok_config_toml(resolution, PROFILE_BINDINGS).decode())
        self.assertNotIn("[ui]", rendered)
        self.assertNotIn("permission_mode", rendered)
        self.assertIn("[permission]", rendered)
        self.assertIn('"Read(.env*)"', rendered)

    def test_trusted_profile_refuses_a_non_self_host_target(self):
        foreign = self._resolve(
            "trusted-full-access", operation_id="self-host-apply", target_identity="repo:other")
        self.assertTrue(foreign.green)
        with self.assertRaisesRegex(ValueError, "HARNESS_GROK_TRUSTED_NON_SELF_HOST_REFUSED"):
            render_profile(foreign, codex_bindings_path=PROFILE_BINDINGS)
        hosted = self._resolve(
            "trusted-full-access", operation_id="self-host-apply", target_identity="repo:swissknifeman")
        hosted_text = render_profile(hosted, codex_bindings_path=PROFILE_BINDINGS).decode()
        self.assertNotIn("[ui]", hosted_text)
        self.assertIn("[permission]", hosted_text)

    def test_hooks_land_in_the_directory_grok_loads(self):
        plan = plan_lifecycle(
            self.catalog, provider_id=ProviderId.GROK, trusted=True,
            requests=(LifecycleRequest("context.observer"),
                      LifecycleRequest("security.safe-dirs"),
                      LifecycleRequest("lifecycle.command-log")),
            codex_bindings_path=HOOK_BINDINGS)
        self.assertTrue(plan.green)
        document, handler = plan_codex_lifecycle_artifacts(plan, bindings_path=HOOK_BINDINGS)
        self.assertEqual(document.target.path, ".grok/hooks/swissknifeman.json")
        self.assertEqual(handler.target.path, ".grok/hooks/lifecycle.py")
        rendered = json.loads(render_codex_hooks(plan))
        self.assertIn("SessionStart", rendered["hooks"])
        self.assertIn("PreToolUse", rendered["hooks"])
        commands = json.dumps(rendered["hooks"])
        self.assertIn(".grok/hooks/lifecycle.py", commands)
        self.assertNotIn("afterShellExecution", commands)
        self.assertNotIn("beforeShellExecution", commands)
        safe = next(binding for binding in plan.bindings if binding.surface_id == "security.safe-dirs")
        self.assertEqual(safe.event, "PreToolUse")
        self.assertEqual(safe.matcher, "^Bash$")

    def test_shared_handler_stamps_grok_not_codex(self):
        source = render_codex_hook_handler(state_dir=".grok").decode()
        self.assertIn("_STATE_DIR = '.grok'", source)
        self.assertIn("_PROVIDER_ID = 'grok'", source)
        self.assertIn('record["provider_id"] = _PROVIDER_ID', source)
        self.assertIn('"--provider", _PROVIDER_ID', source)
        self.assertNotIn('record["provider_id"] = "codex"', source)
        self.assertNotIn('"--provider", "codex"', source)

    def test_grok_pretooluse_normalizes_payload_and_keeps_maind_repair_reachable(self):
        """A Grok envelope must not turn an observer into a silent exit-2 brick."""
        source = render_codex_hook_handler(state_dir=".grok")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handler = root / "lifecycle.py"
            handler.write_bytes(source)
            bindir = root / "bin"
            bindir.mkdir()
            maind = bindir / "maind"

            def invoke(payload, *, status="connected"):
                maind.write_text("#!/bin/sh\nprintf '%s\\n' '" + json.dumps({"status": status})
                                 + "'\n", encoding="utf-8")
                maind.chmod(0o755)
                return subprocess.run(
                    [sys.executable, str(handler), "--surface", "lifecycle.tool-telemetry"],
                    input=json.dumps(payload).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env={**os.environ, "PATH": f"{bindir}:{os.environ.get('PATH', '')}"},
                    timeout=20)

            def payload(tool_name, tool_input):
                return {"hookEventName": "pre_tool_use", "toolName": tool_name,
                        "toolInput": tool_input, "cwd": str(root),
                        "workspaceRoot": str(root), "sessionId": "grok-session",
                        "permissionMode": "acceptEdits"}

            for command in ("maind health --cwd", "maind health --cwd --fix",
                            "maind health --cwd; echo EXIT:$?",
                            "maind health --cwd --fix; echo EXIT:$?"):
                self.assertEqual(invoke(payload("run_terminal_command", {"command": command}),
                                        status="partial").returncode, 0)
            self.assertEqual(invoke(payload("read_file", {
                "path": ".grok/hooks/swissknifeman.json"}), status="partial").returncode, 0)
            denied = invoke(payload("run_terminal_command", {"command": "true"}), status="partial")
            self.assertEqual(denied.returncode, 2)
            decision = json.loads(denied.stdout)
            self.assertEqual(decision["decision"], "deny")
            self.assertEqual(decision["reason"], decision["hookSpecificOutput"]["permissionDecisionReason"])
            self.assertIn("maind health --cwd --fix", decision["reason"])
            self.assertIn(decision["reason"].encode(), denied.stderr)
            # A bounded reviewer must be able to read under both compatibility
            # plan mode and the explicit dontAsk allowlist used by Task transport.
            for mode in ("plan", "dontAsk"):
                for tool_name, tool_input in (("read_file", {"path": "src/Tree.php"}),
                                             ("grep", {"pattern": "lockForUpdate", "path": "src"}),
                                             ("list_dir", {"path": "src"})):
                    envelope = payload(tool_name, tool_input)
                    envelope["permissionMode"] = mode
                    self.assertEqual(invoke(envelope).returncode, 0, (mode, tool_name))
            for tool_name, tool_input in (
                    ("run_terminal_command", {"command": "true"}),
                    ("read_file", {"path": "README.md"}), ("grep", {"pattern": "needle"}),
                    ("search_replace", {"path": "/tmp/grok-hook-probe.txt"}),
                    ("web_search", {"query": "x"}), ("web_fetch", {"url": "https://example.test"}),
                    ("search_tool", {})):
                self.assertEqual(invoke(payload(tool_name, tool_input)).returncode, 0, tool_name)
            malformed = subprocess.run(
                [sys.executable, str(handler), "--surface", "lifecycle.tool-telemetry"],
                input=b'{', stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            self.assertEqual(malformed.returncode, 0)
            self.assertIn(b"payload was not parseable", malformed.stderr)
            unknown = invoke(payload("future_grok_tool", {}), status="partial")
            self.assertEqual(unknown.returncode, 0)
            self.assertIn(b"unrecognized Grok tool name", unknown.stderr)


if __name__ == "__main__":
    unittest.main()
