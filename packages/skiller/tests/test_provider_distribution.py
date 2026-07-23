"""P3.4 provider distribution: preflight, provider-owned targets and native boundary."""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skiller.connect import do_connect
from skiller.publication import run_codex_native_install
from skiller.registry import build_registry
from skiller.skillset import do_sync, plan_sync
try:
    import tests.fixtures as fx
except ModuleNotFoundError:
    from packages.skiller.tests import fixtures as fx


def materialize_registry(env):
    registry, *_ = build_registry(env)
    (env.root / "skills.json").write_text(json.dumps(registry), encoding="utf-8")


def materialize_codex_marketplace(root):
    plugins = []
    for name in ("php", "quality"):
        source = root / "skills" / name
        manifest = source / ".codex-plugin" / "plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({
            "name": name,
            "version": "0.1.0",
            "description": name,
            "skills": ["./"],
        }) + "\n", encoding="utf-8")
        plugins.append({
            "name": name,
            "source": f"./skills/{name}",
            "description": name,
            "category": "engineering",
        })
    marketplace = root / ".agents" / "plugins" / "marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text(json.dumps({
        "name": "swissknifeman",
        "plugins": plugins,
    }) + "\n", encoding="utf-8")


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

    def test_dual_connect_external_target_gets_contained_bundle_with_claude_parity(self):
        self.write_provider_config(providers())
        materialize_codex_marketplace(self.root)
        with mock.patch("skiller.publication.subprocess.run",
                        side_effect=AssertionError("implicit native install")), \
                contextlib.redirect_stdout(io.StringIO()):
            do_connect(self.env, self.project, {
                    "profile": "laravel-project",
                    "no_permissions": True,
                })

        settings = json.loads(
            (self.project / ".claude/settings.local.json").read_text(encoding="utf-8"))
        claude_plugins = {
            key.split("@", 1)[0] for key, enabled in settings["enabledPlugins"].items()
            if enabled
        }
        marketplace_path = self.project / ".agents/plugins/marketplace.json"
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        codex_plugins = {entry["name"] for entry in marketplace["plugins"]}
        self.assertEqual(codex_plugins, claude_plugins)
        for entry in marketplace["plugins"]:
            source = entry["source"]["path"]
            self.assertTrue(source.startswith("./.agents/plugins/bundles/"))
            bundle = self.project / source.removeprefix("./")
            self.assertTrue((bundle / ".codex-plugin/plugin.json").is_file())
            self.assertTrue(any(bundle.rglob("SKILL.md")))
        lock = json.loads(
            (self.project / ".swissknifeman/provider-artifacts.lock.json")
            .read_text(encoding="utf-8"))
        codex_targets = {
            record["target_path"] for record in lock["records"]
            if record["provider_id"] == "codex"
        }
        self.assertIn(".agents/plugins/marketplace.json", codex_targets)
        self.assertTrue(all(
            path == ".agents/plugins/marketplace.json"
            or path.startswith(".agents/plugins/bundles/")
            for path in codex_targets
        ))

    def test_dual_connect_preflights_incomplete_codex_before_claude_write(self):
        self.write_provider_config(providers())
        materialize_codex_marketplace(self.root)
        (self.root / "skills/quality/.codex-plugin/plugin.json").write_text(
            json.dumps({
                "name": "quality",
                "version": "0.1.0",
                "description": "quality",
                "skills": ["./missing"],
            }) + "\n",
            encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            do_connect(self.env, self.project, {
                "profile": "laravel-project",
                "no_permissions": True,
            })
        self.assertIn("SPUB_BUNDLE_INCOMPLETE", stderr.getvalue())
        self.assertFalse((self.project / ".claude/settings.local.json").exists())
        self.assertFalse((self.project / ".agents/plugins/marketplace.json").exists())

    def test_dual_connect_preflights_uncontained_codex_source_before_claude_write(self):
        self.write_provider_config(providers())
        materialize_codex_marketplace(self.root)
        marketplace_path = self.root / ".agents/plugins/marketplace.json"
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        marketplace["plugins"][0]["source"] = "./../outside"
        marketplace_path.write_text(json.dumps(marketplace) + "\n", encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            do_connect(self.env, self.project, {
                "profile": "laravel-project",
                "no_permissions": True,
            })
        self.assertIn("SPUB_PATH_UNCONTAINED", stderr.getvalue())
        self.assertFalse((self.project / ".claude/settings.local.json").exists())
        self.assertFalse((self.project / ".agents/plugins/marketplace.json").exists())

    def test_dual_connect_refuses_unowned_codex_target_before_claude_write(self):
        self.write_provider_config(providers())
        materialize_codex_marketplace(self.root)
        target = self.project / ".agents/plugins/marketplace.json"
        target.parent.mkdir(parents=True)
        target.write_text('{"name":"user-owned"}\n', encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            do_connect(self.env, self.project, {
                "profile": "laravel-project",
                "no_permissions": True,
            })
        self.assertIn("SPUB_OWNERSHIP_CONFLICT", stderr.getvalue())
        self.assertFalse((self.project / ".claude/settings.local.json").exists())
        self.assertEqual(target.read_text(encoding="utf-8"),
                         '{"name":"user-owned"}\n')

    def test_dual_connect_bundle_is_deterministic_and_self_host_stays_thin(self):
        self.write_provider_config(providers())
        materialize_codex_marketplace(self.root)
        opts = {"profile": "laravel-project", "no_permissions": True}
        with contextlib.redirect_stdout(io.StringIO()):
            do_connect(self.env, self.project, opts)
        first = {
            path.relative_to(self.project).as_posix(): path.read_bytes()
            for path in (self.project / ".agents/plugins").rglob("*")
            if path.is_file()
        }
        with contextlib.redirect_stdout(io.StringIO()):
            do_connect(self.env, self.project, opts)
        second = {
            path.relative_to(self.project).as_posix(): path.read_bytes()
            for path in (self.project / ".agents/plugins").rglob("*")
            if path.is_file()
        }
        self.assertEqual(second, first)

        (self.root / ".swissknife.json").write_text(
            json.dumps({"providers": providers()}), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            do_connect(self.env, self.root, opts, register=False)
        self.assertFalse((self.root / ".agents/plugins/bundles").exists())

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

    def test_managed_drift_refuses_all_provider_writes_by_default(self):
        self.write_provider_config(providers())
        with contextlib.redirect_stdout(io.StringIO()):
            do_sync(self.env, self.project, {"no_core": True})
        edited = b"local Codex edit\n"
        codex_skill = self.project / ".agents/skills/code-style/SKILL.md"
        codex_skill.write_bytes(edited)
        before = {
            "config": (self.project / ".swissknifeman/config.json").read_bytes(),
            "lock": (self.project / "skills-lock.json").read_bytes(),
            "claude": (self.project / ".claude/skills/code-style/SKILL.md").read_bytes(),
            "codex": codex_skill.read_bytes(),
            "state": self.env.db_file.read_bytes(),
        }
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            do_sync(self.env, self.project, {"no_core": True})
        self.assertIn("SPUB_OWNERSHIP_CONFLICT", stderr.getvalue())
        self.assertIn("provider codex", stderr.getvalue())
        self.assertIn("managed-drift", stderr.getvalue())
        self.assertEqual((self.project / ".swissknifeman/config.json").read_bytes(), before["config"])
        self.assertEqual((self.project / "skills-lock.json").read_bytes(), before["lock"])
        self.assertEqual((self.project / ".claude/skills/code-style/SKILL.md").read_bytes(), before["claude"])
        self.assertEqual(codex_skill.read_bytes(), before["codex"])
        self.assertEqual(self.env.db_file.read_bytes(), before["state"])

    def test_repair_saves_preimage_reports_hashes_and_replans_clean(self):
        self.write_provider_config(providers())
        with contextlib.redirect_stdout(io.StringIO()):
            do_sync(self.env, self.project, {"no_core": True})
        codex_skill = self.project / ".agents/skills/code-style/SKILL.md"
        observed = b"local Codex edit\n"
        codex_skill.write_bytes(observed)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = do_sync(self.env, self.project, {"no_core": True, "repair": True})
        backup = codex_skill.with_name("SKILL.md.provider-artifact.bak")
        self.assertEqual(backup.read_bytes(), observed)
        source = (self.root / "skills/php/code-style/SKILL.md").read_bytes()
        self.assertEqual(codex_skill.read_bytes(), source)
        codex_record = next(record for record in result["providers"]
                            if record["provider"] == "codex")
        evidence = codex_record["repair"][0]
        self.assertEqual(evidence["observed"], "sha256:" + hashlib.sha256(observed).hexdigest())
        self.assertEqual(evidence["expected"], "sha256:" + hashlib.sha256(source).hexdigest())
        self.assertEqual(evidence["source"], "sha256:" + hashlib.sha256(source).hexdigest())
        self.assertIn("observed=", output.getvalue())
        self.assertIn("expected=", output.getvalue())
        self.assertIn("source=", output.getvalue())
        cfg = json.loads((self.project / ".swissknifeman/config.json").read_text())
        codex_plan = plan_sync(self.env, self.project,
                               {**cfg, "skills_path": ".agents/skills", "agent": "codex"},
                               provider="codex")
        self.assertEqual(codex_plan["managed_drift"], [])
        self.assertEqual(codex_plan["update"], [])
        self.assertIn("code-style", codex_plan["keep"])

    def test_source_staleness_updates_without_repair_backup(self):
        self.write_provider_config(providers())
        with contextlib.redirect_stdout(io.StringIO()):
            do_sync(self.env, self.project, {"no_core": True})
        fx.write_skill(self.root / "skills/php/code-style", "code-style",
                       description="Changed canonical source", body="Changed.\n")
        materialize_registry(self.env)
        cfg = json.loads((self.project / ".swissknifeman/config.json").read_text())
        codex_plan = plan_sync(self.env, self.project,
                               {**cfg, "skills_path": ".agents/skills", "agent": "codex"},
                               provider="codex")
        self.assertEqual(codex_plan["managed_drift"], [])
        self.assertIn("code-style", codex_plan["update"])
        with contextlib.redirect_stdout(io.StringIO()):
            do_sync(self.env, self.project, {"no_core": True})
        self.assertIn("Changed.", (self.project / ".agents/skills/code-style/SKILL.md")
                       .read_text(encoding="utf-8"))
        self.assertFalse((self.project / ".agents/skills/code-style"
                          / "SKILL.md.provider-artifact.bak").exists())

    def test_invalid_lock_refuses_before_config_or_provider_write(self):
        self.write_provider_config(providers())
        config = self.project / ".swissknifeman/config.json"
        config.unlink()
        lock = self.project / "skills-lock.json"
        lock.write_text('{"version": 2, "skills": {}}', encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            do_sync(self.env, self.project, {"no_core": True})
        self.assertIn("SPUB_OWNERSHIP_CONFLICT", stderr.getvalue())
        self.assertIn("provider claude-code, codex", stderr.getvalue())
        self.assertIn("unsupported-version", stderr.getvalue())
        self.assertFalse(config.exists())
        self.assertFalse((self.project / ".claude/skills").exists())
        self.assertFalse((self.project / ".agents/skills").exists())
        self.assertEqual(lock.read_text(encoding="utf-8"), '{"version": 2, "skills": {}}')
        self.assertFalse(self.env.db_file.exists())


if __name__ == "__main__":
    unittest.main()
