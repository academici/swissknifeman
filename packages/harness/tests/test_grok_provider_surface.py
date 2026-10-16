"""Grok project surfaces follow Grok's own hook and config contract."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from aicore.provider.values import EffectiveProvider, ProviderId
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
        self.assertNotIn('record["provider_id"] = "codex"', source)
        self.assertNotIn('"--provider", "codex"', source)

    def test_grok_envelope_is_normalized_and_malformed_input_fails_open(self):
        """A Grok envelope must not turn an observer into a silent exit-2 brick."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handlers = {}
            for state_dir in (".grok", ".codex"):
                handler = root / (state_dir.strip(".") + "-lifecycle.py")
                handler.write_bytes(render_codex_hook_handler(state_dir=state_dir))
                handlers[state_dir] = handler

            def invoke(state_dir, payload):
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                return subprocess.run(
                    [sys.executable, str(handlers[state_dir]), "--surface", "lifecycle.tool-telemetry"],
                    input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=root, env={**os.environ}, timeout=20)

            native = {"hookEventName": "pre_tool_use", "toolName": "run_terminal_command",
                      "toolInput": {"command": "true"}, "cwd": str(root),
                      "sessionId": "grok-session", "permissionMode": "acceptEdits"}
            self.assertEqual(invoke(".grok", native).returncode, 0)
            malformed = invoke(".grok", b"{")
            self.assertEqual(malformed.returncode, 0)
            self.assertIn(b"payload was not parseable", malformed.stderr)
            mismatch = invoke(".grok", {**native, "hookEventName": "session_start"})
            self.assertEqual(mismatch.returncode, 0)
            self.assertIn(b"did not match the lifecycle event", mismatch.stderr)
            # Codex keeps the fail-closed contract for the same malformed input.
            self.assertEqual(invoke(".codex", b"{").returncode, 2)


if __name__ == "__main__":
    unittest.main()
