"""plan-guard (generated plan files) and plan-regen (check + render after a JSON edit)."""
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

from harness.hooks import (LifecycleRequest, plan_lifecycle, render_codex_hook_handler,
                           render_cursor_hook_handler)
from harness.lifecycle_plan_guard_core import MESSAGE, generated_plan_file, plan_guard_hit
from harness.profiles import load_catalog
from core import ProviderId

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]
GUARD = PACKAGE / "configs/claude-code/hooks/plan-guard/plan-guard.py"
REGEN = PACKAGE / "configs/claude-code/hooks/plan-regen/plan-regen.py"
PLAN_CLI = ROOT / "packages/planner/scripts/plan.py"
CATALOG = PACKAGE / "configs/common/profile-catalog.json"
CODEX_BINDINGS = PACKAGE / "configs/codex/hooks/lifecycle-context-bindings.json"
CURSOR_BINDINGS = PACKAGE / "configs/cursor/hooks/lifecycle-context-bindings.json"


def _run(script, payload, *, args=(), env=None):
    return subprocess.run([sys.executable, str(script), *args], input=json.dumps(payload),
                          text=True, capture_output=True, env=env, timeout=60)


class PlanFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.plan = self.root / "plans" / "X"
        self.plan.mkdir(parents=True)
        (self.plan / "plan.json").write_text("{}", encoding="utf-8")
        self.legacy = self.root / "plans" / "Y"
        self.legacy.mkdir()


class PlanGuardCoreTests(PlanFixture):
    def test_generated_files_are_recognised_only_inside_a_plan_directory(self):
        cwd = str(self.root)
        for relative in ("views/index.md", "views/plan.md", "views/roadmap.md", "views/status.md", "views/handoff.md",
                         "views/open-questions.md", "views/AGENTS.md", "views/CLAUDE.md", "context/P1.1.json",
                         "phases/P1/P1.1/U1/brief.json"):
            with self.subTest(relative=relative):
                self.assertEqual(generated_plan_file(f"plans/X/{relative}", cwd), str(self.plan))
                self.assertIsNone(generated_plan_file(f"plans/Y/{relative}", cwd))
        for relative in ("plan.json", "log.jsonl", "artifacts/status.md", "phases/P1/P1.1/notes.md"):
            self.assertIsNone(generated_plan_file(f"plans/X/{relative}", cwd), relative)

    def test_patch_headers_and_plain_paths_are_candidates(self):
        patch = {"input": "*** Begin Patch\n*** Update File: plans/X/views/status.md\n@@\n"}
        self.assertEqual(plan_guard_hit(patch, str(self.root)), "plans/X/views/status.md")
        self.assertIsNone(plan_guard_hit({"input": "*** Update File: plans/Y/views/status.md\n"}, str(self.root)))


class ClaudePlanGuardTests(PlanFixture):
    def _payload(self, relative, tool="Edit", plan="X"):
        return {"cwd": str(self.root), "tool_name": tool,
                "tool_input": {"file_path": f"plans/{plan}/{relative}"}}

    def _mode(self, mode):
        (self.root / ".claude").mkdir(exist_ok=True)
        (self.root / ".claude/plan-guard.env.ini").write_text(f"MODE={mode}\n", encoding="utf-8")

    def test_write_to_a_generated_file_is_blocked_when_plan_json_exists(self):
        self._mode("strict")
        for tool in ("Edit", "Write", "MultiEdit"):
            result = _run(GUARD, self._payload("views/status.md", tool))
            self.assertEqual(result.returncode, 2, tool)
            self.assertIn(MESSAGE, result.stderr)
        for relative in ("context/P1.1.json", "phases/P1/P1.1/U1/brief.json", "views/AGENTS.md"):
            self.assertEqual(_run(GUARD, self._payload(relative)).returncode, 2, relative)

    def test_same_write_without_plan_json_is_allowed(self):
        self._mode("strict")
        result = _run(GUARD, self._payload("views/status.md", plan="Y"))
        self.assertEqual((result.returncode, result.stderr), (0, ""))

    def test_plan_json_itself_is_never_blocked(self):
        self._mode("strict")
        self.assertEqual(_run(GUARD, self._payload("plan.json")).returncode, 0)

    def test_warn_does_not_block_and_off_is_silent(self):
        self._mode("warn")
        warned = _run(GUARD, self._payload("views/status.md"))
        self.assertEqual(warned.returncode, 0)
        self.assertIn("[warn]", warned.stderr)
        self._mode("off")
        self.assertEqual(_run(GUARD, self._payload("views/status.md")).stderr, "")

    def test_inactive_without_a_mode_file(self):
        self.assertEqual(_run(GUARD, self._payload("views/status.md")).returncode, 0)

    def test_decision_matches_the_shared_core(self):
        self._mode("strict")
        for relative in ("views/status.md", "context/a.md", "plan.json", "phases/P1/P1.1/U1/brief.json",
                         "artifacts/index.md"):
            blocked = _run(GUARD, self._payload(relative)).returncode == 2
            self.assertEqual(blocked, generated_plan_file(f"plans/X/{relative}", str(self.root)) is not None,
                             relative)


class ProviderPlanGuardTests(PlanFixture):
    def _core_env(self):
        return {**os.environ, "PATH": f"{ROOT / 'bin'}:{os.environ.get('PATH', '')}"}

    def test_codex_dispatcher_blocks_apply_patch_over_a_generated_file(self):
        with tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_codex_hook_handler())
            (self.root / ".codex").mkdir()
            (self.root / ".codex/plan-guard.env.ini").write_text("MODE=strict\n", encoding="utf-8")
            base = {"session_id": "s1", "model": "gpt-5.6-terra", "cwd": str(self.root),
                    "hook_event_name": "PreToolUse", "tool_name": "apply_patch"}
            refused = None
            for plan, code in (("X", 2), ("Y", 0)):
                payload = {**base, "tool_input": {"input": f"*** Update File: plans/{plan}/views/status.md\n"}}
                result = subprocess.run(
                    [sys.executable, str(handler), "--surface", "lifecycle.plan-guard"],
                    input=json.dumps(payload).encode(), capture_output=True,
                    env=self._core_env(), timeout=20)
                self.assertEqual(result.returncode, code, (plan, result.stderr))
                refused = result if plan == "X" else refused
            self.assertIn(MESSAGE.encode(), refused.stderr)

    def test_cursor_dispatcher_denies_a_write_over_a_generated_file(self):
        with tempfile.TemporaryDirectory() as scratch:
            handler = Path(scratch) / "lifecycle.py"
            handler.write_bytes(render_cursor_hook_handler())
            (self.root / ".cursor").mkdir()
            (self.root / ".cursor/plan-guard.env.ini").write_text("MODE=strict\n", encoding="utf-8")
            base = {"hook_event_name": "preToolUse", "conversation_id": "c1", "cwd": str(self.root),
                    "workspace_roots": [str(ROOT)], "tool_name": "Write"}
            outcomes = {}
            for plan in ("X", "Y"):
                payload = {**base, "tool_input": {"file_path": f"plans/{plan}/views/status.md"}}
                result = subprocess.run(
                    [sys.executable, str(handler), "--surface", "lifecycle.plan-guard"],
                    input=json.dumps(payload).encode(), capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                outcomes[plan] = json.loads(result.stdout)
            self.assertEqual(outcomes["X"]["permission"], "deny")
            self.assertIn(MESSAGE, outcomes["X"]["user_message"])
            self.assertEqual(outcomes["Y"], {"permission": "allow"})

    def test_bindings_exist_for_guard_and_regen_is_unsupported_outside_claude(self):
        catalog = load_catalog(CATALOG)
        for provider, bindings, event in ((ProviderId.CODEX, CODEX_BINDINGS, "PreToolUse"),):
            plan = plan_lifecycle(catalog, provider_id=provider, trusted=True,
                                  requests=(LifecycleRequest("lifecycle.plan-guard"),
                                            LifecycleRequest("lifecycle.plan-regen")),
                                  codex_bindings_path=bindings)
            levels = {item.surface_id: (item.support_level, item.event) for item in plan.bindings}
            self.assertEqual(levels["lifecycle.plan-guard"], ("hook-native", event))
            self.assertEqual(levels["lifecycle.plan-regen"][0], "unsupported")
        claude = plan_lifecycle(catalog, provider_id=ProviderId.CLAUDE_CODE, trusted=True,
                                requests=(LifecycleRequest("lifecycle.plan-guard"),
                                          LifecycleRequest("lifecycle.plan-regen")))
        events = {item.surface_id: item.event for item in claude.bindings}
        self.assertEqual(events, {"lifecycle.plan-guard": "PreToolUse",
                                  "lifecycle.plan-regen": "PostToolUse"})


class PlanRegenTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "plans").mkdir()
        created = subprocess.run(
            [sys.executable, str(PLAN_CLI), "new", "--codename", "DEMO", "--title", "Demo",
             "--actor", "claude-code/x/high", "--message", "m"],
            cwd=self.root, text=True, capture_output=True)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.plan = next((self.root / "plans").iterdir())
        self.env = {**os.environ, "TASK_PLAN_CLI": str(PLAN_CLI)}
        (self.root / ".claude").mkdir()

    def _payload(self, path):
        return {"cwd": str(self.root), "tool_name": "Write", "tool_input": {"file_path": str(path)}}

    def _enable(self):
        (self.root / ".claude/plan-regen.env.ini").write_text("MODE=on\n", encoding="utf-8")

    def test_invalid_json_edit_returns_check_errors_and_does_not_render(self):
        self._enable()
        data = json.loads((self.plan / "plan.json").read_text(encoding="utf-8"))
        data["status"] = "not-a-status"
        (self.plan / "plan.json").write_text(json.dumps(data), encoding="utf-8")
        status = self.plan / "views/status.md"
        status.write_text("sentinel\n", encoding="utf-8")
        result = _run(REGEN, self._payload(self.plan / "plan.json"), env=self.env)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("plan.py check failed", result.stderr)
        self.assertEqual(status.read_text(encoding="utf-8"), "sentinel\n")

    def test_valid_json_edit_renders_the_generated_views(self):
        self._enable()
        status = self.plan / "views/status.md"
        status.write_text("stale\n", encoding="utf-8")
        result = _run(REGEN, self._payload(self.plan / "plan.json"), env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(status.read_text(encoding="utf-8"), "stale\n")

    def test_inactive_by_default_and_for_non_json_or_plain_directories(self):
        status = self.plan / "views/status.md"
        status.write_text("stale\n", encoding="utf-8")
        _run(REGEN, self._payload(self.plan / "plan.json"), env=self.env)
        self.assertEqual(status.read_text(encoding="utf-8"), "stale\n")
        self._enable()
        _run(REGEN, self._payload(self.plan / "notes.md"), env=self.env)
        self.assertEqual(status.read_text(encoding="utf-8"), "stale\n")
        other = self.root / "elsewhere"
        other.mkdir()
        (other / "data.json").write_text("{}", encoding="utf-8")
        self.assertEqual(_run(REGEN, self._payload(other / "data.json"), env=self.env).returncode, 0)


if __name__ == "__main__":
    unittest.main()
