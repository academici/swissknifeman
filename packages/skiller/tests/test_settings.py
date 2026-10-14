"""Tests skiller settings: [skiller] / [skiller.sync] in .swissknifeman/config.toml and the legacy files.

Cover: legacy-only projects read as before, the TOML section, the "whole section" rule, error paths,
the machine layer refusal, vendor settings, writers (materialize, adopt) and backups through aicore.state.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore.config import ConfigError
from aicore.state import machine_config_file

from skiller import settings
from skiller.config import find_project_root, load_config
from skiller.connect import do_connect
from skiller.skillset import (
    cmd_init, load_skillset_config, materialize_skillset_config, skillset_config_path)
from skiller.update import adopt_codex_provider_config

import tests.fixtures as fx


def _json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _toml(project, text):
    path = project / ".swissknifeman" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class SettingsCase(unittest.TestCase):
    def setUp(self):
        settings._EMITTED.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.project = fx.make_laravel_project(self.tmp)
        # The machine file follows SKM_HOME or XDG_CONFIG_HOME when they are set; keep the tests off any shared one.
        patch = mock.patch.dict(os.environ, {"SKM_HOME": str(self.tmp / "skm-home")})
        patch.start()
        self.addCleanup(patch.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def quiet(self, fn, *args, **kwargs):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            result = fn(*args, **kwargs)
        return result, err.getvalue()

    # --- selection keys -----------------------------------------------------------------
    def test_legacy_only_reads_as_before_with_one_warning(self):
        _json(self.project / ".swissknife.json",
              {"project_type": "laravel-project", "buckets": ["quality"], "providers": {"x": 1}})
        cfg, err = self.quiet(load_config, self.env, self.project)
        self.assertEqual(cfg.project_type, "laravel-project")
        self.assertEqual(cfg.buckets, ["quality"])
        self.assertEqual(cfg.plugins, [])
        self.assertEqual(cfg.get("providers"), {"x": 1})
        self.assertNotIn("plugins", cfg.raw)
        self.assertEqual(dict(cfg.raw), {"project_type": "laravel-project", "buckets": ["quality"],
                                         "providers": {"x": 1}})
        self.assertEqual(err.count("SKILLER_LEGACY_CONFIG"), 1)
        _, again = self.quiet(load_config, self.env, self.project)
        self.assertEqual(again, "", "the warning is printed once per process and file")

    def test_no_files_is_an_empty_config(self):
        cfg, err = self.quiet(load_config, self.env, self.project)
        self.assertEqual(dict(cfg), {})
        self.assertEqual(cfg.buckets, [])
        self.assertEqual(err, "")

    def test_toml_only_has_no_warnings_and_marks_the_project_root(self):
        project = self.tmp / "toml-only"
        project.mkdir()
        _toml(project, 'schema_version = 1\n[skiller]\nproject_type = "laravel-project"\n')
        cfg, err = self.quiet(load_config, self.env, project)
        self.assertEqual(cfg.project_type, "laravel-project")
        self.assertEqual(dict(cfg.raw), {"project_type": "laravel-project"})
        self.assertEqual(cfg.source, "config")
        self.assertEqual(err, "")
        self.assertEqual(find_project_root(self.env, project), (project.resolve(), ".swissknifeman/config.toml"))

    def test_the_project_root_search_is_the_shared_one(self):
        """aicore.state.resolve_project with skiller's markers: own order, the home directory ends the walk,
        SKM_PROJECT_ROOT names the project outright."""
        home = self.env.home.resolve()
        work = home / "scratch" / "deep"
        work.mkdir(parents=True)
        self.assertEqual(find_project_root(self.env, work), (None, None))
        (home / ".claude").mkdir(exist_ok=True)
        self.assertEqual(find_project_root(self.env, work), (home, ".claude/"))
        (home / "scratch" / ".git").mkdir()
        self.assertEqual(find_project_root(self.env, work), (home / "scratch", ".git"))
        # a marker of the wrong kind does not stop the walk (a file named .claude, a directory named config.toml)
        proj = home / "proj"
        (proj / ".git").mkdir(parents=True)
        mid = proj / "mid"
        mid.mkdir()
        (mid / ".claude").write_text("x")
        self.assertEqual(find_project_root(self.env, mid), (proj, ".git"))
        (mid / ".claude").unlink()
        (mid / ".claude").mkdir()
        self.assertEqual(find_project_root(self.env, mid), (mid, ".claude/"))
        (mid / ".claude").rmdir()
        (mid / ".swissknifeman" / "config.toml").mkdir(parents=True)
        self.assertEqual(find_project_root(self.env, mid), (proj, ".git"))
        named = self.tmp / "named"
        named.mkdir()
        with mock.patch.dict(os.environ, {"SKM_PROJECT_ROOT": str(named)}):
            self.assertEqual(find_project_root(self.env, work), (named, "SKM_PROJECT_ROOT"))

    def test_section_as_a_whole_toml_wins_over_the_legacy_file(self):
        _toml(self.project, 'schema_version = 1\n[skiller]\nbuckets = ["quality"]\n')
        _json(self.project / ".swissknife.json",
              {"buckets": ["devops"], "presets": ["x"], "memory_brain": "core"})
        cfg, err = self.quiet(load_config, self.env, self.project)
        self.assertEqual(cfg.buckets, ["quality"])
        self.assertEqual(cfg.presets, [], "legacy keys are not merged key by key")
        self.assertEqual(cfg.get("memory_brain"), "core")
        self.assertNotIn("presets", cfg.raw)
        self.assertEqual(err.count("SKILLER_LEGACY_IGNORED"), 1)
        self.assertIn("buckets, presets", err)
        self.assertNotIn("SKILLER_LEGACY_CONFIG", err)

    def test_unknown_keys_fail(self):
        _json(self.project / ".swissknife.json", {"bukkets": ["php"]})
        with self.assertRaises(SystemExit):
            self.quiet(load_config, self.env, self.project)
        (self.project / ".swissknife.json").unlink()
        path = _toml(self.project, 'schema_version = 1\n[skiller]\nbukkets = ["php"]\n')
        with self.assertRaises(ConfigError) as caught:
            self.quiet(load_config, self.env, self.project)
        self.assertEqual(caught.exception.code, "CONFIG_UNKNOWN_KEY")
        self.assertEqual(caught.exception.file, str(path))
        self.assertEqual(caught.exception.line, 3)

    def test_unknown_profile_in_toml_fails(self):
        _toml(self.project, 'schema_version = 1\n[skiller]\nproject_type = "no-such"\n')
        with self.assertRaises(SystemExit):
            self.quiet(load_config, self.env, self.project)

    def test_selection_is_refused_in_the_machine_layer(self):
        machine = machine_config_file(env=os.environ, home=self.env.home)
        machine.parent.mkdir(parents=True, exist_ok=True)
        machine.write_text('schema_version = 1\n[skiller]\nbuckets = ["quality"]\n', encoding="utf-8")
        with self.assertRaises(ConfigError) as caught:
            self.quiet(load_config, self.env, self.project)
        self.assertEqual(caught.exception.code, "CONFIG_LAYER_FORBIDDEN")

    def test_selection_label_names_the_source(self):
        from skiller.config import resolve_selection
        _toml(self.project, 'schema_version = 1\n[skiller]\nplugins = ["quality"]\n')
        cfg, _ = self.quiet(load_config, self.env, self.project)
        items, _p, _s, label, _m = resolve_selection(self.env, self.project, cfg, "", [])
        self.assertEqual((items, label), (["quality"], "[skiller] plugins"))

    # --- vendor settings ----------------------------------------------------------------
    def test_vendor_legacy_file_is_returned_as_it_was(self):
        legacy = {"version": 1, "mode": "vendor", "include": ["code-style"], "_comment": "kept"}
        _json(self.project / ".swissknifeman" / "config.json", legacy)
        cfg, err = self.quiet(load_skillset_config, self.project, self.env)
        self.assertEqual(cfg, legacy)
        self.assertEqual(err.count("SKILLER_LEGACY_CONFIG"), 1)
        self.assertEqual(skillset_config_path(self.project, self.env),
                         self.project / ".swissknifeman" / "config.json")

    def test_vendor_toml_gets_version_and_mode(self):
        _toml(self.project, 'schema_version = 1\n[skiller.sync]\ninclude = ["code-style"]\n')
        cfg, err = self.quiet(load_skillset_config, self.project, self.env)
        self.assertEqual(cfg, {"version": 1, "mode": "vendor", "include": ["code-style"]})
        self.assertEqual(err, "")
        self.assertEqual(skillset_config_path(self.project, self.env),
                         self.project / ".swissknifeman" / "config.toml")

    def test_vendor_neither_is_none(self):
        cfg, err = self.quiet(load_skillset_config, self.project, self.env)
        self.assertIsNone(cfg)
        self.assertEqual(err, "")

    def test_vendor_section_as_a_whole(self):
        _toml(self.project, 'schema_version = 1\n[skiller.sync]\nbuckets = ["php"]\n')
        _json(self.project / ".swissknifeman" / "config.json", {"mode": "vendor", "include": ["code-style"]})
        cfg, err = self.quiet(load_skillset_config, self.project, self.env)
        self.assertEqual(cfg, {"version": 1, "mode": "vendor", "buckets": ["php"]})
        self.assertEqual(err.count("SKILLER_LEGACY_IGNORED"), 1)

    def test_vendor_legacy_validation_keeps_its_messages(self):
        _json(self.project / ".swissknifeman" / "config.json", {"mode": "connect"})
        with self.assertRaises(SystemExit):
            self.quiet(load_skillset_config, self.project, self.env)

    def test_materialize_writes_toml_for_a_new_project(self):
        (cfg, profile, created), _ = self.quiet(materialize_skillset_config, self.env, self.project, {})
        self.assertTrue(created)
        self.assertEqual(profile, "laravel-project")
        text = (self.project / ".swissknifeman" / "config.toml").read_text()
        self.assertTrue(text.startswith("schema_version = 1"))
        self.assertIn("[skiller.sync]", text)
        self.assertFalse((self.project / ".swissknifeman" / "config.json").exists())
        again, _ = self.quiet(load_skillset_config, self.project, self.env)
        self.assertEqual(again["buckets"], cfg["buckets"])
        self.assertEqual(again["mode"], "vendor")

    def test_materialize_leaves_the_toml_alone_while_a_legacy_file_exists(self):
        _json(self.project / ".swissknifeman" / "config.json", {"mode": "vendor", "include": ["code-style"]})
        (cfg, _profile, created), _ = self.quiet(materialize_skillset_config, self.env, self.project, {})
        self.assertFalse(created)
        self.assertEqual(cfg["include"], ["code-style"])
        self.assertFalse((self.project / ".swissknifeman" / "config.toml").exists())
        (_cfg, _p, created), _ = self.quiet(
            materialize_skillset_config, self.env, self.project, {}, force=True)
        self.assertTrue(created)
        self.assertFalse((self.project / ".swissknifeman" / "config.toml").exists())
        self.assertEqual(json.loads((self.project / ".swissknifeman" / "config.json").read_text())["mode"], "vendor")

    def test_init_force_rewrites_the_keys_in_the_toml_and_keeps_the_rest(self):
        path = _toml(self.project, 'schema_version = 1\n# mine\n[skiller.sync]\ngitignore_managed = true\n'
                                   'include = ["code-style"]\n')
        out, _ = self.quiet(cmd_init, self.env, ["--target", str(self.project)])
        self.assertIsNone(out)
        self.assertIn("include", path.read_text())
        self.quiet(cmd_init, self.env, ["--target", str(self.project), "--force"])
        text = path.read_text()
        self.assertIn("# mine", text)
        self.assertIn("gitignore_managed = true", text)
        cfg, _ = self.quiet(load_skillset_config, self.project, self.env)
        self.assertEqual(cfg["include"], [])
        self.assertEqual(cfg["agent"], "claude")
        backups = list((self.project / ".swissknifeman" / "backups").glob("*/.swissknifeman/config.toml"))
        self.assertTrue(backups, "the TOML is backed up through aicore.state before an edit")

    # --- writers ------------------------------------------------------------------------
    def test_adopt_writes_plugins_to_toml_and_providers_to_json(self):
        _toml(self.project, 'schema_version = 1\n[skiller]\nagent = "claude"\n')
        _json(self.project / ".swissknife.json", {"memory_brain": "core"})
        changed, _ = self.quiet(adopt_codex_provider_config, self.project, plugins=["quality"], env=self.env)
        self.assertTrue(changed)
        legacy = json.loads((self.project / ".swissknife.json").read_text())
        self.assertIn("providers", legacy)
        self.assertNotIn("plugins", legacy)
        self.assertEqual(legacy["memory_brain"], "core")
        cfg, _ = self.quiet(load_config, self.env, self.project)
        self.assertEqual(cfg.plugins, ["quality"])
        backups = self.project / ".swissknifeman" / "backups"
        self.assertTrue(list(backups.glob("*/.swissknife.json")))
        self.assertEqual(list(self.project.glob("*.bak")), [])
        self.assertEqual(list(self.project.glob(".swissknife.json.bak")), [])

    def test_adopt_keeps_plugins_in_the_legacy_file_without_a_toml_section(self):
        _json(self.project / ".swissknife.json", {"agent": "claude"})
        self.quiet(adopt_codex_provider_config, self.project, plugins=["quality"], env=self.env)
        legacy = json.loads((self.project / ".swissknife.json").read_text())
        self.assertEqual(legacy["plugins"], ["quality"])
        self.assertFalse((self.project / ".swissknifeman" / "config.toml").exists())

    def test_connect_backs_the_settings_up_in_state_backups(self):
        claude = self.project / ".claude"
        _json(claude / "settings.local.json", {"model": "keep"})
        self.quiet(do_connect, self.env, self.project, {"plugins": "quality"})
        copies = list((self.project / ".swissknifeman" / "backups").glob("*/.claude/settings.local.json"))
        self.assertEqual(len(copies), 1)
        self.assertEqual(json.loads(copies[0].read_text()), {"model": "keep"})
        self.assertFalse((claude / "settings.local.json.bak").exists())

    # --- readers that only look for a path ----------------------------------------------
    def test_skills_paths_come_from_both_sections_and_never_fail(self):
        _toml(self.project, 'schema_version = 1\n[skiller]\nskills_path = ".ai/skills"\n'
                            '[skiller.sync]\nskills_path = ".agents/skills"\n')
        self.assertEqual(settings.configured_skills_paths(self.project, env=self.env),
                         [".agents/skills", ".ai/skills"])
        _toml(self.project, "not toml at all [")
        self.assertEqual(settings.configured_skills_paths(self.project, env=self.env), [])


if __name__ == "__main__":
    unittest.main()
