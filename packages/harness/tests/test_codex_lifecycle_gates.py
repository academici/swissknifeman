"""P2.3 — class B Codex lifecycle gates: refusal on PreToolUse and SubagentStop."""
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
from harness.hooks import LifecycleRequest, plan_lifecycle, render_codex_hook_handler, render_codex_hooks
from harness.profiles import load_catalog

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]
CATALOG = PACKAGE / "configs/common/profile-catalog.json"
BINDINGS = PACKAGE / "configs/codex/hooks/lifecycle-context-bindings.json"
MANIFEST = ROOT / "configs/provider-capabilities.json"

CLASS_B_SURFACES = ("lifecycle.pack-guard", "lifecycle.changelog-gate", "lifecycle.review-gate",
                   "security.safe-dirs", "lifecycle.daemon-safety", "lifecycle.git-guardrails")
_MODAL_SURFACES = ("lifecycle.pack-guard", "lifecycle.changelog-gate", "lifecycle.review-gate",
                  "lifecycle.git-guardrails")

_COMMON_FIELDS = {"session_id": "s1", "cwd": "/tmp/project", "model": "gpt-5.6-terra"}


def _run_handler(handler_path, surface, payload, *, env=None, cwd=None):
    return subprocess.run([sys.executable, str(handler_path), "--surface", surface],
                         input=json.dumps(payload).encode(), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=env, cwd=cwd, timeout=20)


class CodexLifecycleGateTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(CATALOG)
        self.handler_bytes = render_codex_hook_handler()

    def _write_handler(self, directory):
        path = Path(directory) / "lifecycle.py"
        path.write_bytes(self.handler_bytes)
        return path

    def _project_env(self, home):
        return {**os.environ, "HOME": home}

    def _core_env(self):
        return {**os.environ, "PATH": f"{ROOT / 'bin'}:{os.environ.get('PATH', '')}"}

    def test_manifest_levels_raised_with_adapter_id_and_evidence(self):
        manifest = load_provider_manifest(MANIFEST)
        for surface_id in CLASS_B_SURFACES:
            support = support_for(manifest, surface_id, ProviderId.CODEX)
            self.assertEqual(support.level.value, "adapted")
            self.assertEqual(support.adapter_id, f"harness.codex.{surface_id}")
            self.assertTrue(support.limitations)
            self.assertTrue(support.evidence)
            for evidence in support.evidence:
                self.assertEqual(evidence.source,
                                 "plans/archive/2026.07.29-HARNESS-AGNOSTIC/root/contracts/"
                                 "codex-parity-verdicts-v1.md")

    def test_bindings_are_hook_native_with_manifest_synchronized(self):
        requests = tuple(LifecycleRequest(surface_id) for surface_id in CLASS_B_SURFACES)
        plan = plan_lifecycle(self.catalog, provider_id=ProviderId.CODEX, trusted=True,
                              requests=requests, codex_bindings_path=BINDINGS)
        self.assertTrue(plan.green)
        levels = {binding.surface_id: binding.support_level for binding in plan.bindings}
        self.assertEqual(levels, {surface_id: "hook-native" for surface_id in CLASS_B_SURFACES})
        events = {binding.surface_id: binding.event for binding in plan.bindings}
        self.assertEqual(events, {
            "lifecycle.pack-guard": "PreToolUse", "lifecycle.changelog-gate": "PreToolUse",
            "lifecycle.review-gate": "SubagentStop", "security.safe-dirs": "PreToolUse",
            "lifecycle.daemon-safety": "PreToolUse", "lifecycle.git-guardrails": "PreToolUse"})
        rendered = json.loads(render_codex_hooks(plan))
        commands = json.dumps(rendered["hooks"])
        for surface_id in CLASS_B_SURFACES:
            self.assertIn(surface_id, commands)

    def test_dispatcher_still_rejects_unknown_surface_and_malformed_subagentstop_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            handler = self._write_handler(directory)
            missing_field = _run_handler(handler, "lifecycle.review-gate",
                                        {**_COMMON_FIELDS, "hook_event_name": "SubagentStop"})
            self.assertEqual(missing_field.returncode, 2)

    # -- lifecycle.pack-guard ------------------------------------------------

    def test_pack_guard_refuses_managed_asset_and_passes_unmanaged_in_strict_mode(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            claude_dir = Path(project) / ".claude"
            claude_dir.mkdir()
            codex_dir = Path(project) / ".codex"
            codex_dir.mkdir()
            (codex_dir / "pack-guard.env.ini").write_text("MODE=strict\n", encoding="utf-8")
            (claude_dir / "agent-pack.lock.json").write_text(json.dumps({"packs": {"demo": {
                "files": [{"target": ".claude/agents/foo.md", "user_owned": False},
                          {"target": ".claude/notes.md", "user_owned": True}]}}}), encoding="utf-8")
            managed = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "PreToolUse",
                      "tool_name": "apply_patch",
                      "tool_input": {"input": "*** Update File: .claude/agents/foo.md\n"}}
            refused = _run_handler(handler, "lifecycle.pack-guard", managed, env=self._core_env())
            self.assertEqual(refused.returncode, 2)
            self.assertIn(b"demo", refused.stderr)
            unmanaged = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "PreToolUse",
                        "tool_name": "apply_patch",
                        "tool_input": {"input": "*** Update File: .claude/notes.md\n"}}
            passed = _run_handler(handler, "lifecycle.pack-guard", unmanaged, env=self._core_env())
            self.assertEqual(passed.returncode, 0)
            self.assertEqual(passed.stdout, b"")

    def test_pack_guard_inactive_by_default_without_mode_file(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            claude_dir = Path(project) / ".claude"
            claude_dir.mkdir()
            (claude_dir / "agent-pack.lock.json").write_text(json.dumps({"packs": {"demo": {
                "files": [{"target": ".claude/agents/foo.md", "user_owned": False}]}}}), encoding="utf-8")
            payload = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "PreToolUse",
                      "tool_name": "apply_patch",
                      "tool_input": {"input": "*** Update File: .claude/agents/foo.md\n"}}
            result = _run_handler(handler, "lifecycle.pack-guard", payload, env=self._core_env())
            self.assertEqual(result.returncode, 0)

    # -- lifecycle.changelog-gate --------------------------------------------

    def _git(self, cwd, *args):
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _changelog_project(self, project):
        self._git(project, "init", "-q")
        self._git(project, "config", "user.email", "t@example.com")
        self._git(project, "config", "user.name", "t")
        (Path(project) / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
        self._git(project, "add", "CHANGELOG.md")
        self._git(project, "commit", "-qm", "init")

    def test_changelog_gate_warns_on_content_commit_without_changelog_and_passes_docs(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            self._changelog_project(project)
            (Path(project) / ".codex").mkdir()
            (Path(project) / ".codex" / "changelog-gate.env.ini").write_text(
                "MODE=warn\n", encoding="utf-8")
            feat = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "PreToolUse",
                   "tool_name": "Bash", "tool_input": {"command": 'git commit -m "feat: add x"'}}
            warned = _run_handler(handler, "lifecycle.changelog-gate", feat, env=self._core_env())
            self.assertEqual(warned.returncode, 0)
            hint = json.loads(warned.stdout)["systemMessage"]
            self.assertIn("changelog-gate", hint)
            docs = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "PreToolUse",
                   "tool_name": "Bash", "tool_input": {"command": 'git commit -m "docs: x"'}}
            passed = _run_handler(handler, "lifecycle.changelog-gate", docs, env=self._core_env())
            self.assertEqual(passed.returncode, 0)
            self.assertEqual(passed.stdout, b"")

    def test_changelog_gate_strict_blocks_and_skip_marker_is_honored(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            self._changelog_project(project)
            (Path(project) / ".codex").mkdir()
            (Path(project) / ".codex" / "changelog-gate.env.ini").write_text(
                "MODE=strict\n", encoding="utf-8")
            feat = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "PreToolUse",
                   "tool_name": "Bash", "tool_input": {"command": 'git commit -m "fix: y"'}}
            blocked = _run_handler(handler, "lifecycle.changelog-gate", feat, env=self._core_env())
            self.assertEqual(blocked.returncode, 2)
            skipped = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "PreToolUse",
                      "tool_name": "Bash",
                      "tool_input": {"command": 'git commit -m "fix: y [changelog-skip]"'}}
            passed = _run_handler(handler, "lifecycle.changelog-gate", skipped, env=self._core_env())
            self.assertEqual(passed.returncode, 0)

    # -- lifecycle.review-gate ------------------------------------------------

    def _review_gate_home(self, home, check_command):
        cfg = Path(home) / ".claude" / "hooks" / "review-gate"
        cfg.mkdir(parents=True)
        (cfg / "config.json").write_text(json.dumps({"check_command": check_command}),
                                         encoding="utf-8")

    def test_review_gate_strict_forces_continuation_then_gives_up_after_the_attempt_cap(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch, \
                tempfile.TemporaryDirectory() as home:
            handler = self._write_handler(scratch)
            self._review_gate_home(home, "exit 1")
            (Path(project) / ".codex").mkdir()
            (Path(project) / ".codex" / "review-gate.env.ini").write_text(
                "MODE=strict\n", encoding="utf-8")
            payload = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "SubagentStop",
                      "agent_type": "reviewer", "agent_id": "a1"}
            env = self._project_env(home)
            codes = [_run_handler(handler, "lifecycle.review-gate", payload, env=env).returncode
                    for _ in range(4)]
            self.assertEqual(codes, [2, 2, 2, 0])

    def test_review_gate_passes_when_check_succeeds_and_is_inactive_without_config(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch, \
                tempfile.TemporaryDirectory() as home:
            handler = self._write_handler(scratch)
            self._review_gate_home(home, "exit 0")
            (Path(project) / ".codex").mkdir()
            (Path(project) / ".codex" / "review-gate.env.ini").write_text(
                "MODE=strict\n", encoding="utf-8")
            payload = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "SubagentStop",
                      "agent_type": "reviewer", "agent_id": "a1"}
            ok = _run_handler(handler, "lifecycle.review-gate", payload,
                             env=self._project_env(home))
            self.assertEqual(ok.returncode, 0)
            self.assertEqual(ok.stdout, b"")
            # no MODE file at all -> inactive regardless of machine config
            with tempfile.TemporaryDirectory() as other_project:
                payload2 = {**payload, "cwd": other_project}
                inactive = _run_handler(handler, "lifecycle.review-gate", payload2,
                                        env=self._project_env(home))
                self.assertEqual(inactive.returncode, 0)
                self.assertEqual(inactive.stdout, b"")

    # -- security.safe-dirs ----------------------------------------------------

    def _safe_dirs_env(self, config_path):
        env = {**os.environ, "PATH": f"{ROOT / 'bin'}:{os.environ.get('PATH', '')}",
               "SKM_SAFE_DIRS_CONFIG": str(config_path)}
        return env

    def test_safe_dirs_refuses_rm_outside_the_allowlist_and_allows_it_inside(self):
        with tempfile.TemporaryDirectory() as scratch, tempfile.TemporaryDirectory() as allowed:
            handler = self._write_handler(scratch)
            config = Path(scratch) / "safe-dirs.json"
            config.write_text(json.dumps({"version": 1, "dirs": [allowed],
                                          "include_registered_projects": False}), encoding="utf-8")
            env = self._safe_dirs_env(config)
            target = Path(allowed) / "junk.txt"
            target.write_text("x", encoding="utf-8")
            payload = {**_COMMON_FIELDS, "cwd": allowed, "hook_event_name": "PreToolUse",
                      "tool_name": "Bash", "tool_input": {"command": f"rm {target}"}}
            allowed_result = _run_handler(handler, "security.safe-dirs", payload, env=env)
            self.assertEqual(allowed_result.returncode, 0)
            outside = {**_COMMON_FIELDS, "cwd": scratch, "hook_event_name": "PreToolUse",
                      "tool_name": "Bash", "tool_input": {"command": f"rm -rf {scratch}"}}
            refused = _run_handler(handler, "security.safe-dirs", outside, env=env)
            self.assertEqual(refused.returncode, 2)
            self.assertIn(b"not covered by the safe-dirs allowlist", refused.stderr)

    def test_safe_dirs_ignores_non_rm_commands_and_refuses_when_checkout_unreachable(self):
        with tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            env = self._safe_dirs_env(Path(scratch) / "safe-dirs.json")
            benign = {**_COMMON_FIELDS, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                     "tool_input": {"command": "ls -la"}}
            passed = _run_handler(handler, "security.safe-dirs", benign, env=env)
            self.assertEqual(passed.returncode, 0)
            unreachable_env = {**env, "PATH": "/nonexistent-only"}
            rm_cmd = {**_COMMON_FIELDS, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                     "tool_input": {"command": "rm somefile"}}
            refused = _run_handler(handler, "security.safe-dirs", rm_cmd, env=unreachable_env)
            self.assertEqual(refused.returncode, 2)
            self.assertIn(b"checkout unreachable", refused.stderr)

    # -- lifecycle.daemon-safety -------------------------------------------

    def test_daemon_safety_always_blocks_destructive_pattern_and_honors_env_kill_switch(self):
        with tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            danger = "pk" + "ill -f perplexity"
            payload = {**_COMMON_FIELDS, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_input": {"command": danger}}
            blocked = _run_handler(handler, "lifecycle.daemon-safety", payload, env=self._core_env())
            self.assertEqual(blocked.returncode, 2)
            self.assertIn(b"daemon-safety", blocked.stderr)
            bypassed_env = {**self._core_env(), "PERPLEXITY_DAEMON_GUARD": "off"}
            bypassed = _run_handler(handler, "lifecycle.daemon-safety", payload, env=bypassed_env)
            self.assertEqual(bypassed.returncode, 0)

    def test_daemon_safety_passes_benign_bash_commands(self):
        with tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            payload = {**_COMMON_FIELDS, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_input": {"command": "ls -la"}}
            result = _run_handler(handler, "lifecycle.daemon-safety", payload, env=self._core_env())
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")

    # -- lifecycle.git-guardrails -------------------------------------------

    def test_git_guardrails_strict_blocks_dangerous_command_and_warn_only_hints(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            (Path(project) / ".codex").mkdir()
            (Path(project) / ".codex" / "git-guardrails.env.ini").write_text(
                "MODE=strict\n", encoding="utf-8")
            payload = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "PreToolUse",
                      "tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}}
            blocked = _run_handler(handler, "lifecycle.git-guardrails", payload, env=self._core_env())
            self.assertEqual(blocked.returncode, 2)
            (Path(project) / ".codex" / "git-guardrails.env.ini").write_text(
                "MODE=warn\n", encoding="utf-8")
            warned = _run_handler(handler, "lifecycle.git-guardrails", payload, env=self._core_env())
            self.assertEqual(warned.returncode, 0)
            self.assertIn(b"git-guardrails", warned.stdout)

    def test_git_guardrails_passes_benign_git_commands_and_is_inactive_by_default(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as scratch:
            handler = self._write_handler(scratch)
            (Path(project) / ".codex").mkdir()
            (Path(project) / ".codex" / "git-guardrails.env.ini").write_text(
                "MODE=strict\n", encoding="utf-8")
            benign = {**_COMMON_FIELDS, "cwd": project, "hook_event_name": "PreToolUse",
                     "tool_name": "Bash", "tool_input": {"command": "git status"}}
            passed = _run_handler(handler, "lifecycle.git-guardrails", benign, env=self._core_env())
            self.assertEqual(passed.returncode, 0)
            no_mode_project = tempfile.mkdtemp()
            dangerous_but_off = {**benign, "cwd": no_mode_project,
                                "tool_input": {"command": "git push --force"}}
            inactive = _run_handler(handler, "lifecycle.git-guardrails", dangerous_but_off,
                                    env=self._core_env())
            self.assertEqual(inactive.returncode, 0)


if __name__ == "__main__":
    unittest.main()
