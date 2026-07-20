"""P3.4 provider distribution: preflight, provider-owned targets and native boundary."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skiller.connect import do_connect
from skiller.publication import run_codex_native_install
from skiller.registry import build_registry
from skiller.skillset import do_sync
import tests.fixtures as fx


def materialize_registry(env):
    registry, *_ = build_registry(env)
    (env.root / "skills.json").write_text(json.dumps(registry), encoding="utf-8")


def providers(*, claude=True, codex=True):
    return {"contract_version": "1.0.0", "selection": {
        "claude-code": {"enabled": claude}, "codex": {"enabled": codex}}}


class ProviderDistributionCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        materialize_registry(self.env)
        self.project = fx.make_laravel_project(self.tmp)
        (self.project / ".swissknifeman").mkdir()
        (self.project / ".swissknifeman" / "config.json").write_text(
            json.dumps({"mode": "vendor", "include": ["code-style"]}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def write_provider_config(self, value):
        (self.project / ".swissknife.json").write_text(
            json.dumps({"providers": value}), encoding="utf-8")

    def test_legacy_default_keeps_claude_only_vendor_bytes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            do_sync(self.env, self.project, {})
        self.assertTrue((self.project / ".claude/skills/code-style/SKILL.md").is_file())
        self.assertFalse((self.project / ".agents/skills/code-style").exists())
        lock = json.loads((self.project / "skills-lock.json").read_text())
        self.assertIn("code-style", lock["skills"])
        self.assertNotIn("providers", lock)

    def test_dual_vendor_preflights_then_keeps_provider_qualified_locks(self):
        self.write_provider_config(providers())
        with contextlib.redirect_stdout(io.StringIO()):
            do_sync(self.env, self.project, {})
        self.assertTrue((self.project / ".claude/skills/code-style/SKILL.md").is_file())
        self.assertTrue((self.project / ".agents/skills/code-style/SKILL.md").is_file())
        lock = json.loads((self.project / "skills-lock.json").read_text())
        self.assertIn("code-style", lock["skills"])
        self.assertIn("code-style", lock["providers"]["codex"])

    def test_explicit_disable_does_not_mean_legacy_missing(self):
        self.write_provider_config(providers(claude=False, codex=True))
        with contextlib.redirect_stdout(io.StringIO()):
            do_sync(self.env, self.project, {})
        self.assertFalse((self.project / ".claude/skills/code-style").exists())
        self.assertTrue((self.project / ".agents/skills/code-style/SKILL.md").is_file())

    def test_shared_vendor_root_fails_before_any_provider_write(self):
        self.write_provider_config(providers())
        cfg = self.project / ".swissknifeman" / "config.json"
        cfg.write_text(json.dumps({"mode": "vendor", "skills_path": ".agents/skills",
                                   "include": ["code-style"]}), encoding="utf-8")
        with self.assertRaises(SystemExit):
            do_sync(self.env, self.project, {})
        self.assertFalse((self.project / ".agents/skills").exists())

    def test_dual_vendor_unmanaged_codex_conflict_fails_before_any_write(self):
        self.write_provider_config(providers())
        unmanaged = self.project / ".agents/skills/code-style"
        unmanaged.mkdir(parents=True)
        (unmanaged / "SKILL.md").write_text("user-owned\n", encoding="utf-8")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            do_sync(self.env, self.project, {})

        self.assertIn("SPUB_OWNERSHIP_CONFLICT", stderr.getvalue())
        self.assertIn("provider codex", stderr.getvalue())
        self.assertFalse((self.project / ".claude/skills").exists())
        self.assertFalse((self.project / "skills-lock.json").exists())
        self.assertFalse(self.env.db_file.exists())
        self.assertEqual((unmanaged / "SKILL.md").read_text(encoding="utf-8"),
                         "user-owned\n")

    def test_dual_connect_external_target_fails_before_claude_settings_write(self):
        self.write_provider_config(providers())
        with self.assertRaises(SystemExit):
            do_connect(self.env, self.project, {"profile": "laravel-project"})
        self.assertFalse((self.project / ".claude/settings.local.json").exists())

    def test_native_install_is_explicit_and_dry_run_never_calls_runner(self):
        calls = []
        ok, message = run_codex_native_install(
            repo_root=self.root, plugin="core", dry_run=True,
            runner=lambda *args, **kwargs: calls.append((args, kwargs)))
        self.assertTrue(ok)
        self.assertIn("SPUB_INSTALL_EXPLICIT_REQUIRED", message)
        self.assertEqual(calls, [])

    def test_native_install_reports_missing_codex_without_runner(self):
        calls = []
        with mock.patch("skiller.publication.shutil.which", return_value=None):
            ok, message = run_codex_native_install(
                repo_root=self.root, plugin="core", dry_run=False,
                runner=lambda *args, **kwargs: calls.append((args, kwargs)))
        self.assertFalse(ok)
        self.assertIn("SPUB_INSTALL_UNAVAILABLE", message)
        self.assertEqual(calls, [])

    def test_native_install_uses_injected_runner_with_no_shell(self):
        commands = []

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def runner(command, **kwargs):
            commands.append((command, kwargs))
            return Result()

        with mock.patch("skiller.publication.shutil.which", return_value="/bin/codex"):
            ok, _ = run_codex_native_install(repo_root=self.root, plugin="core",
                                              dry_run=False, runner=runner)
        self.assertTrue(ok)
        self.assertEqual(commands[0][0][:4], ["codex", "plugin", "marketplace", "add"])
        self.assertEqual(commands[1][0], ["codex", "plugin", "add", "core@swissknifeman"])
        self.assertTrue(all(item[1].get("shell") is None for item in commands))

    def test_provider_b_failure_is_honest_and_repairable(self):
        self.write_provider_config(providers())
        from skiller import skillset
        original_copy = skillset.safe_copy_skill
        calls = []

        def first_then_fail(*args, **kwargs):
            calls.append(1)
            return original_copy(*args, **kwargs) if len(calls) == 1 else False

        with mock.patch("skiller.skillset.safe_copy_skill", side_effect=first_then_fail):
            with self.assertRaises(SystemExit):
                do_sync(self.env, self.project, {"no_core": True})
        self.assertTrue((self.project / ".claude/skills/code-style/SKILL.md").is_file())
        self.assertFalse((self.project / ".agents/skills/code-style").exists())
        with contextlib.redirect_stdout(io.StringIO()):
            do_sync(self.env, self.project, {"no_core": True})
        self.assertTrue((self.project / ".agents/skills/code-style/SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
