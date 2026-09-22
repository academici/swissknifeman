"""P3.4 provider distribution: preflight, provider-owned targets and native boundary."""
import contextlib
import hashlib
import io
import json
import os
try:
    import tomllib
except ImportError:
    tomllib = None
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skiller.connect import do_connect
from skiller.publication import run_codex_native_install
from skiller.registry import build_registry
from skiller.skillset import do_sync, plan_sync
from skiller.update import update_one
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

    @unittest.skipUnless(tomllib, "native activation requires stdlib tomllib (Python 3.11+)")
    def test_native_selection_is_opt_in_dry_run_and_explicit_project_only(self):
        self.write_provider_config(providers())
        materialize_codex_marketplace(self.root)
        config = self.project / ".codex/config.toml"
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(self.tmp / "codex-home")}), \
                mock.patch("skiller.publication.run_codex_native_install", side_effect=AssertionError("native install")), \
                contextlib.redirect_stdout(io.StringIO()):
            do_connect(self.env, self.project, {"plugins": "php", "no_core": True, "dry_run": True,
                                               "native_codex": True}, register=False)
            self.assertFalse(config.exists())
            do_connect(self.env, self.project, {"plugins": "php", "no_core": True}, register=False)
            self.assertFalse(config.exists())
            with mock.patch("skiller.connect.apply_permissions", side_effect=AssertionError("permissions write")):
                do_connect(self.env, self.project, {"plugins": "php", "no_core": True,
                                                   "native_codex": True}, register=False)
        plugins = tomllib.loads(config.read_text())["plugins"]
        self.assertTrue(plugins["php@swissknifeman"]["enabled"])
        self.assertFalse(plugins["quality@swissknifeman"]["enabled"])

    def test_native_selection_parse_failure_precedes_connect_mutations(self):
        self.write_provider_config(providers())
        materialize_codex_marketplace(self.root)
        config = self.project / ".codex/config.toml"
        config.parent.mkdir()
        config.write_text("[broken")
        before = {p.relative_to(self.project): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit):
            do_connect(self.env, self.project, {"plugins": "php", "no_core": True,
                                               "native_codex": True}, register=False)
        self.assertEqual(before, {p.relative_to(self.project): p.read_bytes()
                                  for p in self.project.rglob("*") if p.is_file()})

    @unittest.skipUnless(tomllib, "native activation requires stdlib tomllib (Python 3.11+)")
    def test_native_hub_runs_once_after_project_selection_and_includes_agents(self):
        self.write_provider_config(providers())
        materialize_codex_marketplace(self.root)
        opts = {"plugins": "php", "no_core": True, "native_codex": True, "hub": True}

        def hub_after_selection(env, target, *, root_files):
            self.assertEqual(root_files, ("AGENTS.md",))
            plugins = tomllib.loads((target / ".codex/config.toml").read_text())["plugins"]
            self.assertTrue(plugins["php@swissknifeman"]["enabled"])
            self.assertFalse(plugins["quality@swissknifeman"]["enabled"])
            self.assertTrue((target / ".agents/plugins/marketplace.json").is_file())

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(self.tmp / "codex-home")}), \
                mock.patch("skiller.connect.generate_hub", side_effect=hub_after_selection) as generate, \
                contextlib.redirect_stdout(io.StringIO()):
            do_connect(self.env, self.project, {**opts, "dry_run": True}, register=False)
            generate.assert_not_called()
            do_connect(self.env, self.project, opts, register=False)
            generate.assert_called_once_with(self.env, self.project, root_files=("AGENTS.md",))

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

    def test_marketplace_update_keeps_codex_out_of_vendor_channel(self):
        self.write_provider_config(providers())
        materialize_codex_marketplace(self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            do_connect(self.env, self.project, {
                "profile": "laravel-project",
                "no_permissions": True,
            })
            update_one(self.env, self.project)

        self.assertTrue((self.project / ".claude/skills/code-style/SKILL.md").is_file())
        self.assertFalse((self.project / ".agents/skills").exists())
        lock_path = self.project / "skills-lock.json"
        lock = json.loads(lock_path.read_text())
        self.assertNotIn("providers", lock)
        first_lock = lock_path.read_bytes()

        with contextlib.redirect_stdout(io.StringIO()):
            update_one(self.env, self.project)
        self.assertEqual(lock_path.read_bytes(), first_lock)
        self.assertFalse((self.project / ".agents/skills").exists())

    def test_dual_connect_bundle_keeps_runtime_files_and_consumer_exclusions(self):
        self.write_provider_config(providers())
        skill = self.root / "skills/quality/test-writer"
        included = {
            "snippets/tests.md": "tests\n",
            "references/guide.md": "guide\n",
            "scripts/check.py": "print('ok')\n",
            "assets/icon.txt": "icon\n",
        }
        excluded = {
            "upstream.json": "{}\n",
            ".claude-plugin/plugin.json": "{}\n",
            "SKILL.ru.md": "private source\n",
            "SKILL.notes.md": "private notes\n",
            "evals/case.md": "eval\n",
            "__pycache__/check.pyc": "bytecode\n",
            "scripts/cached.pyc": "bytecode\n",
        }
        for relative, content in {**included, **excluded}.items():
            path = skill / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        materialize_codex_marketplace(self.root)

        with contextlib.redirect_stdout(io.StringIO()):
            do_connect(self.env, self.project, {
                "profile": "laravel-project",
                "no_permissions": True,
            })

        bundle_skill = (
            self.project / ".agents/plugins/bundles/quality/test-writer"
        )
        for relative, content in included.items():
            delivered = bundle_skill / relative
            self.assertTrue(delivered.is_file(), relative)
            self.assertEqual(delivered.read_text(encoding="utf-8"), content)
        for relative in excluded:
            self.assertFalse((bundle_skill / relative).exists(), relative)

    def test_dual_connect_preflights_escaping_runtime_symlink_before_claude_write(self):
        self.write_provider_config(providers())
        outside = self.tmp / "outside.md"
        outside.write_text("outside\n", encoding="utf-8")
        reference = self.root / "skills/quality/test-writer/references/escape.md"
        reference.parent.mkdir(parents=True)
        reference.symlink_to(outside)
        materialize_codex_marketplace(self.root)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            do_connect(self.env, self.project, {
                "profile": "laravel-project",
                "no_permissions": True,
            })

        self.assertIn("SPUB_PATH_UNCONTAINED", stderr.getvalue())
        self.assertFalse((self.project / ".claude/settings.local.json").exists())
        self.assertFalse((self.project / ".agents/plugins/marketplace.json").exists())

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

    def test_connect_replacement_dry_run_matches_apply_without_consumer_writes(self):
        self.write_provider_config(providers())
        materialize_codex_marketplace(self.root)
        opts = {"plugins": "php,quality", "no_core": True, "no_permissions": True}
        with contextlib.redirect_stdout(io.StringIO()):
            do_connect(self.env, self.project, opts)
        before = {path.relative_to(self.project).as_posix(): path.read_bytes()
                  for path in self.project.rglob("*") if path.is_file()}
        replacement = dict(opts, plugins="php")
        with contextlib.redirect_stdout(io.StringIO()):
            do_connect(self.env, self.project, dict(replacement, dry_run=True))
        after = {path.relative_to(self.project).as_posix(): path.read_bytes()
                 for path in self.project.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        with contextlib.redirect_stdout(io.StringIO()):
            do_connect(self.env, self.project, replacement)
        marketplace = json.loads((self.project / ".agents/plugins/marketplace.json").read_text())
        self.assertEqual([entry["name"] for entry in marketplace["plugins"]], ["php"])
        self.assertFalse((self.project / ".agents/plugins/bundles/quality").exists())

    def test_connect_replacement_refuses_modified_preimage_without_writes(self):
        self.write_provider_config(providers())
        materialize_codex_marketplace(self.root)
        opts = {"plugins": "php,quality", "no_core": True, "no_permissions": True}
        with contextlib.redirect_stdout(io.StringIO()):
            do_connect(self.env, self.project, opts)
        path = self.project / ".agents/plugins/bundles/php/.codex-plugin/plugin.json"
        path.write_text('{"name":"modified"}\n', encoding="utf-8")
        before = {p.relative_to(self.project).as_posix(): p.read_bytes()
                  for p in self.project.rglob("*") if p.is_file()}
        for dry_run in (True, False):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit):
                do_connect(self.env, self.project, dict(opts, plugins="php", dry_run=dry_run))
            self.assertEqual(before, {p.relative_to(self.project).as_posix(): p.read_bytes()
                                     for p in self.project.rglob("*") if p.is_file()})

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

    def test_native_install_upgrades_matching_git_source_without_replacement(self):
        commands = []

        def runner(command, **kwargs):
            commands.append(command)
            if command[2:4] == ["marketplace", "add"]:
                return subprocess.CompletedProcess(command, 1, "", "already added from a different source")
            if command[-2:] == ["list", "--json"]:
                return subprocess.CompletedProcess(command, 0, json.dumps({"marketplaces": [{"name": "swissknifeman", "marketplaceSource": {"sourceType": "git", "source": "https://example.test/repo.git"}}]}), "")
            if command[0] == "git":
                return subprocess.CompletedProcess(command, 0, "https://example.test/repo.git\n", "")
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch("skiller.publication.shutil.which", return_value="/bin/codex"):
            ok, _ = run_codex_native_install(repo_root=self.root, plugin="core", dry_run=False, runner=runner)
        self.assertTrue(ok)
        self.assertIn(["codex", "plugin", "marketplace", "upgrade", "swissknifeman"], commands)
        self.assertFalse(any("remove" in command for command in commands))

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

    def test_repair_restores_managed_skill_deleted_from_project(self):
        """Удалённый managed-скилл — тоже managed-drift, но пре-образа у него нет.

        Регрессия: `--repair` требовал SKILL.md для бэкапа и умирал
        SPUB_OWNERSHIP_CONFLICT «no recoverable pre-image», из-за чего ЕДИНСТВЕННЫЙ
        путь восстановления удалённого скилла был недостижим (наблюдено на живом
        проекте: `plan-protocol` пропал из `.claude/skills`, sync не чинился).
        """
        self.write_provider_config(providers())
        with contextlib.redirect_stdout(io.StringIO()):
            do_sync(self.env, self.project, {"no_core": True})
        codex_skill_dir = self.project / ".agents/skills/code-style"
        shutil.rmtree(codex_skill_dir)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = do_sync(self.env, self.project, {"no_core": True, "repair": True})
        source = (self.root / "skills/php/code-style/SKILL.md").read_bytes()
        self.assertEqual((codex_skill_dir / "SKILL.md").read_bytes(), source)
        # бэкапа нет и быть не может — локальных байт не существовало
        self.assertFalse((codex_skill_dir / "SKILL.md.provider-artifact.bak").exists())
        evidence = next(record for record in result["providers"]
                        if record["provider"] == "codex")["repair"][0]
        self.assertEqual(evidence["observed"], "sha256:<missing>")
        cfg = json.loads((self.project / ".swissknifeman/config.json").read_text())
        codex_plan = plan_sync(self.env, self.project,
                               {**cfg, "skills_path": ".agents/skills", "agent": "codex"},
                               provider="codex")
        self.assertEqual(codex_plan["managed_drift"], [])
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


class RepositoryBootstrapConsumerRejectionCase(unittest.TestCase):
    """P1.2 (D31): consumer vendor selection rejects a private/source-only bucket's records
    outright — never copying them into a project, whether requested by bucket or by name."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        fx.write_skill(self.root / "skills" / "repository-bootstrap" / "private-example",
                       "private-example", description="Private example")
        bj = json.loads((self.root / "buckets.json").read_text())
        bj["repository-bootstrap"] = {"description": "Private", "category": "meta",
                                      "tags": [], "private_source_only": True}
        (self.root / "buckets.json").write_text(json.dumps(bj), encoding="utf-8")
        materialize_registry(self.env)
        self.project = fx.make_laravel_project(self.tmp)
        (self.project / ".swissknifeman").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_vendor_bucket_request_dies_before_any_write(self):
        (self.project / ".swissknifeman" / "config.json").write_text(
            json.dumps({"mode": "vendor", "buckets": ["repository-bootstrap"]}),
            encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            do_sync(self.env, self.project, {})
        self.assertIn("repository-bootstrap", stderr.getvalue())
        self.assertIn("приватный source-only", stderr.getvalue())
        self.assertFalse((self.project / ".claude" / "skills").exists())

    def test_vendor_include_by_name_is_never_resolved(self):
        from skiller.skillset import load_skillset_config
        (self.project / ".swissknifeman" / "config.json").write_text(
            json.dumps({"mode": "vendor", "include": ["private-example"]}),
            encoding="utf-8")
        cfg = load_skillset_config(self.project)
        plan = plan_sync(self.env, self.project, cfg)
        self.assertEqual(plan["add"], [])
        self.assertIn("private-example", plan["skipped"])


class CoreDonorMutualExclusionCase(unittest.TestCase):
    """P1.5 (D42): `skiller doctor --provider-distribution` names every identity the curated
    `core` unit shares with a donor bucket (`general`/`research`/`oss-dev`) — read-only,
    never a repair, never a live-profile read."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[3]
        self.package_root = self.repo_root / "packages" / "skiller"
        from skiller.common import Env
        self.env = Env(self.package_root)

    def _catalog(self):
        from skiller.registry import build_catalog, build_registry
        registry, metadata, buckets = build_registry(self.env)
        return build_catalog(self.env, metadata, buckets, registry)

    def test_worst_case_declared_set_names_exactly_the_four_core_pairs(self):
        from skiller.doctor import detect_core_donor_collisions
        catalog = self._catalog()
        enabled = {unit.plugin_id: True for unit in catalog.units}
        findings = detect_core_donor_collisions(catalog, enabled=enabled)
        pairs = {(item["identity"], tuple(item["carriers"])) for item in findings}
        general_identities = {"anti-drift", "context-economy",
                              "session-handoff", "verify-claims"}
        for identity in general_identities:
            self.assertIn((identity, ("unit:core", "unit:general")), pairs)
        self.assertEqual(len(findings), 4)  # the curated CORE, not the whole general bucket
        for item in findings:
            self.assertEqual(item["owner"], "P1.5")
            self.assertTrue(item["safe_owner_action"])

    def test_core_disabled_yields_no_findings(self):
        from skiller.doctor import detect_core_donor_collisions
        catalog = self._catalog()
        enabled = {unit.plugin_id: True for unit in catalog.units}
        enabled["core"] = False
        self.assertEqual(detect_core_donor_collisions(catalog, enabled=enabled), ())

    def test_single_donor_enabled_narrows_to_its_own_identities(self):
        from skiller.doctor import detect_core_donor_collisions
        catalog = self._catalog()
        findings = detect_core_donor_collisions(
            catalog, enabled={"core": True, "research": True})
        self.assertEqual(findings, ())

    def test_doctor_provider_distribution_prints_d42_diagnostics(self):
        import contextlib
        import io
        from skiller.doctor import cmd_doctor
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with contextlib.suppress(SystemExit):
                cmd_doctor(self.env, ["--provider-distribution", "--target",
                                      str(self.package_root)])
        out = buf.getvalue()
        self.assertIn("D42 core↔donor mutual exclusion", out)
        self.assertIn("verify-claims", out)


class ProviderDistributionDoctorSelectionCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        materialize_registry(self.env)
        materialize_codex_marketplace(self.root)
        self.project = fx.make_laravel_project(self.tmp)
        (self.project / ".swissknife.json").write_text(json.dumps({
            "plugins": ["php"],
            "providers": providers(claude=False, codex=True),
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_doctor_passes_resolved_plugin_selection_to_codex_plan(self):
        from skiller.doctor import cmd_doctor
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            cmd_doctor(self.env, ["--provider-distribution", "--target",
                                  str(self.project)])

        self.assertIn("[ok ] marketplace plan: codex", output.getvalue())
        self.assertNotIn("SPUB_BUNDLE_INCOMPLETE", output.getvalue())


class EffectiveRuntimeGateCase(unittest.TestCase):
    """P1.4 (D51/D62/D63): cold per-provider install/discover of the declared fixture
    (repo marketplace minus the three donor buckets) proves catalog-wide identity
    uniqueness — never a named-ID list — plus the negative fixture (D42 curated CORE pairs +
    class-B `workflow-craft` precondition) and the D62 reconciliation against a frozen
    collision snapshot. Runs against the REAL repo catalog (like
    CoreDonorMutualExclusionCase above) — a synthetic fixture has neither the
    root-bootstrap config nor the `task` sibling this gate must cover."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[3]
        self.package_root = self.repo_root / "packages" / "skiller"
        from skiller.common import Env
        self.env = Env(self.package_root)

    def _catalog(self):
        from skiller.registry import build_catalog, build_registry
        registry, metadata, buckets = build_registry(self.env)
        return build_catalog(self.env, metadata, buckets, registry)

    def test_declared_fixture_unit_set_excludes_exactly_the_three_donors(self):
        from skiller.doctor import declared_fixture_unit_set
        catalog = self._catalog()
        doc = declared_fixture_unit_set(catalog, repo_root=self.repo_root)
        self.assertEqual(doc["schema_version"], "p1.4-fixture-unit-set/v1")
        for provider in ("codex", "claude-code"):
            record = doc["providers"][provider]
            self.assertEqual(record["excluded"], ["general", "oss-dev", "research"])
            self.assertEqual(record["excluded_reason"], "d42-donor-bucket")
            self.assertNotIn("general", record["units"])
            self.assertNotIn("research", record["units"])
            self.assertNotIn("oss-dev", record["units"])
            self.assertIn("core", record["units"])
            self.assertIn("architect", record["units"])
            self.assertIn("task", record["units"])

    def test_positive_fixture_has_zero_catalog_wide_collisions_and_zero_undeclared_roots(self):
        from skiller.doctor import run_effective_runtime_gate
        result = run_effective_runtime_gate(self.env)
        for provider in ("codex", "claude-code"):
            self.assertEqual(result["collisions_by_provider"][provider], {},
                             f"{provider}: catalog-wide collision under the declared fixture")
            self.assertEqual(result["undeclared_by_provider"][provider], [],
                             f"{provider}: undeclared root directory under the declared fixture")
        # sanity floor: the fixture is the whole non-donor catalog, not a narrow slice
        self.assertGreater(len(result["positive_maps"]["codex"]), 150)
        self.assertGreater(len(result["positive_maps"]["claude-code"]), 150)
        # the 16 previously-colliding identities resolve exactly once, from the
        # installed bundle only — the deleted root carrier never reappears
        for identity, expected_unit in (
                ("anti-drift", "unit:core"), ("context-economy", "unit:core"),
                ("session-handoff", "unit:core"), ("verify-claims", "unit:core"),
                ("architecture", "unit:architect"), ("codebase-design", "unit:architect"),
                ("domain-modeling", "unit:architect"),
                ("package-contribution-protocol", "unit:architect"),
                ("task-design", "unit:task"), ("task-plan-audit", "unit:task"),
                ("task-plan-close", "unit:task"), ("task-plan-design", "unit:task"),
                ("task-plan-exec", "unit:task"), ("task-plan-run", "unit:task")):
            self.assertEqual(result["positive_maps"]["codex"].get(identity), [expected_unit],
                             f"{identity}: expected exactly-once {expected_unit}, no root carrier")
        # class-A resolves via root only (private bucket, never a unit member) on both
        # providers; class-B `workflow-craft` is Codex-only by declared asymmetry (D43)
        self.assertEqual(result["positive_maps"]["codex"].get("cross-project-optimizer"),
                         ["root:codex"])
        self.assertEqual(result["positive_maps"]["claude-code"].get("cross-project-optimizer"),
                         ["root:claude-code"])
        self.assertEqual(result["positive_maps"]["codex"].get("workflow-craft"), ["root:codex"])
        self.assertNotIn("workflow-craft", result["positive_maps"]["claude-code"])

    def test_negative_fixture_proves_the_four_pairs_and_class_b_precondition(self):
        from skiller.doctor import run_effective_runtime_gate
        result = run_effective_runtime_gate(self.env)
        self.assertEqual(len(result["negative_pairs"]), 4)
        self.assertIn("verify-claims", {item["identity"] for item in result["negative_pairs"]})
        self.assertIsNotNone(result["workflow_craft_precondition_error"])
        self.assertIn("precondition violated", result["workflow_craft_precondition_error"])

    def test_cli_effective_runtime_reports_ok_and_writes_artifacts(self):
        import contextlib
        import io
        from skiller.doctor import cmd_doctor
        with tempfile.TemporaryDirectory() as tmp:
            fixture_out = Path(tmp) / "fixture-unit-set.json"
            carrier_out = Path(tmp) / "effective-carrier-set.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cmd_doctor(self.env, ["--effective-runtime",
                                      "--fixture-out", str(fixture_out),
                                      "--carrier-out", str(carrier_out)])
            out = buf.getvalue()
            self.assertIn("OK — 0 catalog-wide collisions, 0 undeclared root directories", out)
            fixture_doc = json.loads(fixture_out.read_text(encoding="utf-8"))
            self.assertEqual(fixture_doc["schema_version"], "p1.4-fixture-unit-set/v1")
            carrier_doc = json.loads(carrier_out.read_text(encoding="utf-8"))
            self.assertEqual(carrier_doc["schema_version"], "p1.4-effective-carrier-set/v1")
            self.assertTrue(carrier_doc["measured_at_commit"])


class ReconcileRemediationCollisionsCase(unittest.TestCase):
    """D62: every FROZEN collision record classifies to exactly one of `still-measured` /
    `resolved` / `unowned-or-unexplained`, computed fresh — never the frozen snapshot's own
    point-in-time counters. Synthetic input (no dependency on any plan's on-disk artifact,
    which may be archived/removed once its plan closes)."""

    def _record(self, identity, provider, carriers, classes, owners):
        return {"identity": identity, "provider": provider, "carriers": carriers,
               "classes": classes,
               "owners": [{"owner_item": o} for o in owners]}

    def test_root_vs_unit_with_terminal_owner_and_gone_from_positive_map_resolves(self):
        from skiller.doctor import reconcile_remediation_collisions
        record = self._record("anti-drift", "codex", ["root:anti-drift", "unit:core"],
                              ["root-vs-unit"], ["P1.2"])
        results = reconcile_remediation_collisions(
            [record], positive_maps={"codex": {"anti-drift": ["unit:core"]}},
            negative_pairs=(), terminal_owner_items={"P1.2"})
        self.assertEqual(results, [{"identity": "anti-drift", "provider": "codex",
                                   "outcome": "resolved"}])

    def test_unit_vs_unit_still_measured_iff_pair_present_in_negative_fixture(self):
        from skiller.doctor import reconcile_remediation_collisions
        record = self._record("query-craft", "codex", ["unit:core", "unit:research"],
                              ["unit-vs-unit"], ["P1.5"])
        negative_pairs = ({"identity": "query-craft",
                          "carriers": ["unit:core", "unit:research"]},)
        results = reconcile_remediation_collisions(
            [record], positive_maps={"codex": {}}, negative_pairs=negative_pairs,
            terminal_owner_items={"P1.5"})
        self.assertEqual(results[0]["outcome"], "still-measured")

    def test_combined_classes_stay_still_measured_even_after_root_deletion(self):
        from skiller.doctor import reconcile_remediation_collisions
        record = self._record("anti-drift", "codex",
                              ["root:anti-drift", "unit:core", "unit:general"],
                              ["root-vs-unit", "unit-vs-unit"], ["P1.2", "P1.5"])
        negative_pairs = ({"identity": "anti-drift",
                          "carriers": ["unit:core", "unit:general"]},)
        results = reconcile_remediation_collisions(
            [record], positive_maps={"codex": {"anti-drift": ["unit:core"]}},
            negative_pairs=negative_pairs, terminal_owner_items={"P1.2", "P1.5"})
        self.assertEqual(results[0]["outcome"], "still-measured")

    def test_non_terminal_owner_or_still_live_collision_is_unowned_or_unexplained(self):
        from skiller.doctor import reconcile_remediation_collisions
        # owner not terminal, and identity no longer collides — neither "still-measured"
        # (single carrier) nor "resolved" (owner not terminal) — a real defect.
        record = self._record("architecture", "codex",
                              ["root:architecture", "unit:architect"],
                              ["root-vs-unit"], ["P9.9"])
        results = reconcile_remediation_collisions(
            [record], positive_maps={"codex": {"architecture": ["unit:architect"]}},
            negative_pairs=(), terminal_owner_items={"P1.2", "P1.3", "P1.5"})
        self.assertEqual(results[0]["outcome"], "unowned-or-unexplained")
        # still ≥2 carriers under the positive fixture — a brand-new, unowned collision
        record2 = self._record("architecture", "codex",
                               ["root:architecture", "unit:architect"],
                               ["root-vs-unit"], ["P1.5"])
        results2 = reconcile_remediation_collisions(
            [record2],
            positive_maps={"codex": {"architecture": ["root:architecture", "unit:architect"]}},
            negative_pairs=(), terminal_owner_items={"P1.5"})
        self.assertEqual(results2[0]["outcome"], "still-measured")


if __name__ == "__main__":
    unittest.main()
