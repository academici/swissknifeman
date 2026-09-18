"""Cursor P4 gates: daemon-safety activation and shared-core enforcement."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import ProviderId, load_provider_manifest, support_for
from harness.hooks import LifecycleRequest, plan_lifecycle, render_cursor_hook_handler, render_cursor_hooks
from harness.profiles import load_catalog

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]
CATALOG = PACKAGE / "configs/common/profile-catalog.json"
CURSOR_BINDINGS = PACKAGE / "configs/cursor/hooks/lifecycle-context-bindings.json"
MANIFEST = ROOT / "configs/provider-capabilities.json"


def _run_handler(handler_path, surface, payload, *, env=None):
    return subprocess.run(
        [sys.executable, str(handler_path), "--surface", surface],
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=20,
    )


class CursorLifecycleGateTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(CATALOG)

    def _cursor_plan(self, *surfaces):
        requests = tuple(LifecycleRequest(surface, True) for surface in surfaces)
        return plan_lifecycle(
            self.catalog,
            provider_id=ProviderId.CURSOR,
            trusted=True,
            requests=requests,
            cursor_bindings_path=CURSOR_BINDINGS,
        )

    def _git(self, cwd, *args):
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _seed_changelog_repo(self, project):
        self._git(project, "init", "-q")
        self._git(project, "config", "user.email", "t@example.com")
        self._git(project, "config", "user.name", "t")
        (Path(project) / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
        self._git(project, "add", "CHANGELOG.md")
        self._git(project, "commit", "-qm", "init")

    def test_manifest_daemon_safety_row_is_adapted_with_named_adapter(self):
        manifest = load_provider_manifest(MANIFEST)
        support = support_for(manifest, "lifecycle.daemon-safety", ProviderId.CURSOR)
        self.assertEqual(support.level.value, "adapted")
        self.assertEqual(support.adapter_id, "harness.cursor.lifecycle.daemon-safety")
        self.assertTrue(support.evidence)
        self.assertTrue(support.limitations)

    def test_binding_and_render_register_daemon_safety_on_before_shell(self):
        plan = self._cursor_plan("lifecycle.daemon-safety")
        self.assertTrue(plan.green)
        self.assertEqual(plan.bindings[0].support_level, "hook-native")
        self.assertEqual(plan.bindings[0].event, "beforeShellExecution")
        rendered = json.loads(render_cursor_hooks(plan))
        entry = rendered["hooks"]["beforeShellExecution"][0]
        self.assertIn("--surface lifecycle.daemon-safety", entry["command"])
        self.assertEqual(entry.get("failClosed"), True)

    def test_daemon_safety_blocks_destructive_command_and_honors_kill_switch(self):
        with tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            payload = {
                "hook_event_name": "beforeShellExecution",
                "conversation_id": "conv-daemon",
                "command": "pkill -f perplexity",
                "workspace_roots": [str(ROOT)],
            }
            blocked = _run_handler(handler, "lifecycle.daemon-safety", payload)
            self.assertEqual(blocked.returncode, 2)
            self.assertIn(b"daemon-safety", blocked.stderr)
            bypassed = _run_handler(
                handler,
                "lifecycle.daemon-safety",
                payload,
                env={**os.environ, "PERPLEXITY_DAEMON_GUARD": "off"},
            )
            self.assertEqual(bypassed.returncode, 0)

    def test_daemon_safety_false_positive_case_is_pinned(self):
        with tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            payload = {
                "hook_event_name": "beforeShellExecution",
                "conversation_id": "conv-fp",
                "command": 'echo "rm /tmp/Singleton"',
                "workspace_roots": [str(ROOT)],
            }
            result = _run_handler(handler, "lifecycle.daemon-safety", payload)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"matched rule", result.stderr)

    def test_git_guardrails_binding_and_render_use_before_shell(self):
        plan = self._cursor_plan("lifecycle.git-guardrails")
        self.assertTrue(plan.green)
        self.assertEqual(plan.bindings[0].support_level, "hook-native")
        self.assertEqual(plan.bindings[0].event, "beforeShellExecution")
        rendered = json.loads(render_cursor_hooks(plan))
        entry = rendered["hooks"]["beforeShellExecution"][0]
        self.assertIn("--surface lifecycle.git-guardrails", entry["command"])
        self.assertEqual(entry.get("matcher"), "\\bgit\\b")
        self.assertEqual(entry.get("failClosed"), True)

    def test_git_guardrails_strict_warn_and_off_modes(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            cursor_dir = Path(project) / ".cursor"
            cursor_dir.mkdir()
            payload = {
                "hook_event_name": "beforeShellExecution",
                "conversation_id": "conv-git",
                "cwd": project,
                "workspace_roots": [str(ROOT)],
                "command": "git reset --hard HEAD~1",
            }
            (cursor_dir / "git-guardrails.env.ini").write_text("MODE=strict\n", encoding="utf-8")
            blocked = _run_handler(handler, "lifecycle.git-guardrails", payload)
            self.assertEqual(blocked.returncode, 2)
            (cursor_dir / "git-guardrails.env.ini").write_text("MODE=warn\n", encoding="utf-8")
            warned = _run_handler(handler, "lifecycle.git-guardrails", payload)
            self.assertEqual(warned.returncode, 0)
            warning = json.loads(warned.stdout.decode("utf-8"))
            self.assertEqual(warning["permission"], "allow")
            self.assertIn("git-guardrails", warning["agent_message"])
            (cursor_dir / "git-guardrails.env.ini").write_text("MODE=off\n", encoding="utf-8")
            inactive = _run_handler(handler, "lifecycle.git-guardrails", payload)
            self.assertEqual(inactive.returncode, 0)
            self.assertEqual(inactive.stdout, b"")

    def test_git_guardrails_false_positive_case_is_pinned(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            cursor_dir = Path(project) / ".cursor"
            cursor_dir.mkdir()
            (cursor_dir / "git-guardrails.env.ini").write_text("MODE=strict\n", encoding="utf-8")
            payload = {
                "hook_event_name": "beforeShellExecution",
                "conversation_id": "conv-git-fp",
                "cwd": project,
                "workspace_roots": [str(ROOT)],
                "command": 'echo "git reset --hard"',
            }
            result = _run_handler(handler, "lifecycle.git-guardrails", payload)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"matched rule", result.stderr)

    def test_changelog_gate_binding_and_render_use_before_shell(self):
        plan = self._cursor_plan("lifecycle.changelog-gate")
        self.assertTrue(plan.green)
        self.assertEqual(plan.bindings[0].support_level, "hook-native")
        self.assertEqual(plan.bindings[0].event, "beforeShellExecution")
        rendered = json.loads(render_cursor_hooks(plan))
        entry = rendered["hooks"]["beforeShellExecution"][0]
        self.assertIn("--surface lifecycle.changelog-gate", entry["command"])
        self.assertEqual(entry.get("matcher"), "git.*commit")
        self.assertEqual(entry.get("failClosed"), True)

    def test_changelog_gate_strict_warn_off_and_skip_marker(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            self._seed_changelog_repo(project)
            cursor_dir = Path(project) / ".cursor"
            cursor_dir.mkdir()
            payload = {
                "hook_event_name": "beforeShellExecution",
                "conversation_id": "conv-changelog",
                "cwd": project,
                "workspace_roots": [str(ROOT)],
                "command": 'git commit -m "feat: add x"',
            }
            (cursor_dir / "changelog-gate.env.ini").write_text("MODE=strict\n", encoding="utf-8")
            blocked = _run_handler(handler, "lifecycle.changelog-gate", payload)
            self.assertEqual(blocked.returncode, 2)
            (cursor_dir / "changelog-gate.env.ini").write_text("MODE=warn\n", encoding="utf-8")
            warned = _run_handler(handler, "lifecycle.changelog-gate", payload)
            self.assertEqual(warned.returncode, 0)
            warning = json.loads(warned.stdout.decode("utf-8"))
            self.assertEqual(warning["permission"], "allow")
            self.assertIn("changelog-gate", warning["agent_message"])
            skipped = {**payload, "command": 'git commit -m "fix: y [changelog-skip]"'}
            allowed = _run_handler(handler, "lifecycle.changelog-gate", skipped)
            self.assertEqual(allowed.returncode, 0)
            self.assertEqual(allowed.stdout, b"")
            (cursor_dir / "changelog-gate.env.ini").write_text("MODE=off\n", encoding="utf-8")
            inactive = _run_handler(handler, "lifecycle.changelog-gate", payload)
            self.assertEqual(inactive.returncode, 0)
            self.assertEqual(inactive.stdout, b"")

    def test_changelog_gate_false_positive_case_is_pinned(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            self._seed_changelog_repo(project)
            cursor_dir = Path(project) / ".cursor"
            cursor_dir.mkdir()
            (cursor_dir / "changelog-gate.env.ini").write_text("MODE=strict\n", encoding="utf-8")
            payload = {
                "hook_event_name": "beforeShellExecution",
                "conversation_id": "conv-changelog-fp",
                "cwd": project,
                "workspace_roots": [str(ROOT)],
                "command": 'echo git commit -m "feat: add x"',
            }
            result = _run_handler(handler, "lifecycle.changelog-gate", payload)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"matched rule", result.stderr)

    def test_pack_guard_binding_and_render_use_pretooluse(self):
        plan = self._cursor_plan("lifecycle.pack-guard")
        self.assertTrue(plan.green)
        self.assertEqual(plan.bindings[0].support_level, "hook-native")
        self.assertEqual(plan.bindings[0].event, "preToolUse")
        rendered = json.loads(render_cursor_hooks(plan))
        entry = rendered["hooks"]["preToolUse"][0]
        self.assertIn("--surface lifecycle.pack-guard", entry["command"])
        self.assertEqual(entry.get("matcher"), "^(Write|Delete|Task|MCP:.*)$")
        self.assertEqual(entry.get("failClosed"), True)

    def test_pack_guard_strict_warn_and_off_modes(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            (Path(project) / ".claude").mkdir()
            (Path(project) / ".cursor").mkdir()
            (Path(project) / ".claude" / "agent-pack.lock.json").write_text(
                json.dumps({
                    "packs": {
                        "demo": {
                            "files": [
                                {"target": ".claude/agents/foo.md", "user_owned": False},
                                {"target": ".claude/notes.md", "user_owned": True},
                            ]
                        }
                    }
                }),
                encoding="utf-8",
            )
            payload = {
                "hook_event_name": "preToolUse",
                "conversation_id": "conv-pack",
                "cwd": project,
                "workspace_roots": [str(ROOT)],
                "tool_name": "Write",
                "tool_input": {"file_path": ".claude/agents/foo.md"},
            }
            (Path(project) / ".cursor" / "pack-guard.env.ini").write_text(
                "MODE=strict\n", encoding="utf-8")
            blocked = _run_handler(handler, "lifecycle.pack-guard", payload)
            self.assertEqual(blocked.returncode, 2)
            self.assertIn(b"demo", blocked.stderr)
            (Path(project) / ".cursor" / "pack-guard.env.ini").write_text(
                "MODE=warn\n", encoding="utf-8")
            warned = _run_handler(handler, "lifecycle.pack-guard", payload)
            self.assertEqual(warned.returncode, 0)
            warning = json.loads(warned.stdout.decode("utf-8"))
            self.assertEqual(warning["permission"], "allow")
            self.assertIn("pack-guard", warning["agent_message"])
            (Path(project) / ".cursor" / "pack-guard.env.ini").write_text(
                "MODE=off\n", encoding="utf-8")
            inactive = _run_handler(handler, "lifecycle.pack-guard", payload)
            self.assertEqual(inactive.returncode, 0)
            self.assertEqual(inactive.stdout, b"")

    def test_pack_guard_false_positive_case_is_pinned(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            (Path(project) / ".claude").mkdir()
            (Path(project) / ".cursor").mkdir()
            (Path(project) / ".claude" / "agent-pack.lock.json").write_text(
                json.dumps({
                    "packs": {
                        "demo": {
                            "files": [{"target": ".claude/agents/foo.md", "user_owned": False}]
                        }
                    }
                }),
                encoding="utf-8",
            )
            (Path(project) / ".cursor" / "pack-guard.env.ini").write_text(
                "MODE=strict\n", encoding="utf-8")
            payload = {
                "hook_event_name": "preToolUse",
                "conversation_id": "conv-pack-fp",
                "cwd": project,
                "workspace_roots": [str(ROOT)],
                "tool_name": "Task",
                "tool_input": {
                    "description": "explain why .claude/agents/foo.md is managed by a pack"
                },
            }
            result = _run_handler(handler, "lifecycle.pack-guard", payload)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"matched managed target", result.stderr)


if __name__ == "__main__":
    unittest.main()
