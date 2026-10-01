"""Tests codegraph.py — code-graph policy resolver + promoter .serena/project.yml."""
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from maind import codegraph
from maind.config import load_config
from tests.fixtures import make_repo, write_maind_config

_CFG = Path(".serena") / "project.yml"


def _setup(tmp, *, code_graph=None, **proj):
    root, env = make_repo(tmp)
    pdir = Path(tmp) / "flexcrm"
    pdir.mkdir(parents=True, exist_ok=True)
    p = {"id": "flexcrm", "name": "FlexCRM", "type": "php-package",
         "enabled": True, "local_path": str(pdir)}
    p.update(proj)
    extra = {"code_graph": code_graph} if code_graph is not None else {}
    write_maind_config(root, projects=[p], **extra)
    config, _ = load_config(env)
    return env, config, config["projects"][0], pdir


class TestSerenaConfig(unittest.TestCase):
    def test_writes_when_graphify_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, graphify=True)
            r = codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            self.assertEqual(r["state"], "absent")
            self.assertTrue(r["changed"])
            txt = (pdir / _CFG).read_text(encoding="utf-8")
            self.assertIn('project_name: "flexcrm"', txt)
            self.assertIn("- php", txt)                 # language by type php-package
            self.assertIn('- "vendor"', txt)
            self.assertIn('- "packages"', txt)          # symlinks first-party not indexable
            self.assertIn("initial_prompt:", txt)       # targeting directive symbol-tools
            self.assertIn("Serena", txt)

    def test_disabled_when_graphify_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)   # without graphify
            r = codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            self.assertEqual(r["state"], "disabled")
            self.assertFalse((pdir / _CFG).exists())

    def test_skip_custom_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, graphify=True,
                                             graphify_command="php",
                                             graphify_server_name="laravel-boost")
            r = codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            self.assertEqual(r["state"], "custom")
            self.assertFalse((pdir / _CFG).exists())

    def test_does_not_clobber_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, graphify=True)
            (pdir / ".serena").mkdir()
            (pdir / _CFG).write_text("project_name: mine\n# my config\n", encoding="utf-8")
            r = codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            self.assertEqual(r["state"], "present")
            self.assertFalse(r["changed"])
            self.assertIn("my config", (pdir / _CFG).read_text())  # not overwritten

    def test_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, graphify=True)
            r = codegraph.apply_serena_config(env, config, proj, "auto", dry=True)
            self.assertEqual(r["status"], "dry")
            self.assertFalse((pdir / _CFG).exists())

    def test_workspace_mode_includes_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, graphify=True, graphify_workspace=True)
            codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            txt = (pdir / _CFG).read_text(encoding="utf-8")
            self.assertIn('- "**/vendor"', txt)              # recursion/cutting duplicates
            self.assertNotIn('- "packages"', txt)            # packets are NOT ignored (single graph)
            self.assertIn("ignore_all_files_in_gitignore: false", txt)
            self.assertIn("workspace", txt)                  # prompt about a single graph/edits

    def test_workspace_auto_detected_by_packages_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, graphify=True)   # without explicit flag
            (pdir / "packages").mkdir()                            # → auto-workspace
            codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            txt = (pdir / _CFG).read_text(encoding="utf-8")
            self.assertNotIn('- "packages"', txt)
            self.assertIn('- "**/vendor"', txt)

    def test_explicit_false_overrides_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, graphify=True, graphify_workspace=False)
            (pdir / "packages").mkdir()                            # is there, but the flag=false
            codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            self.assertIn('- "packages"', (pdir / _CFG).read_text())  # default ignore

    def test_node_package_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, graphify=True, type="node-package")
            codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            self.assertIn("- typescript", (pdir / _CFG).read_text())

    def test_code_language_override_beats_type(self):
        # per-project code_language interrupts language_by_type (node-package→typescript):
        # mixed repo (python-code + TS-docks) graph as python, without touching the general constants.
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, code=True, type="node-package",
                                             code_language="python")
            codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            txt = (pdir / _CFG).read_text()
            self.assertIn("- python", txt)
            self.assertNotIn("- typescript", txt)

    def test_code_languages_list_renders_multi(self):
        # list of languages → several language servers (multi-language mixed repo graph)
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, code=True,
                                             code_languages=["python", "typescript"])
            codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            txt = (pdir / _CFG).read_text()
            self.assertIn("language_servers:", txt)
            self.assertNotIn("\nlanguages:", txt)
            self.assertIn("- python", txt)
            self.assertIn("- typescript", txt)

    def test_language_servers_key_always_present_when_undetected(self):
        # standalone-type + empty repo: language not detected → language_servers STILL
        # is written (empty list). Current Serena requires the key as required and crashes
        # KeyError in its absence - this test protects against regression (onboarding chatom).
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, code=True, type="standalone")
            codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            txt = (pdir / _CFG).read_text()
            self.assertIn("language_servers:", txt)
            self.assertIn("language_servers: []", txt)


class TestConfigDriven(unittest.TestCase):
    def test_code_alias_equals_graphify(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, code=True)   # new field name (alias graphify)
            r = codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            self.assertTrue(r["changed"])
            self.assertIn('project_name: "flexcrm"', (pdir / _CFG).read_text())

    def test_ignores_from_config_not_hardcode(self):
        # ignore policy is taken from the section code_graph, not from code
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(
                tmp, code=True,
                code_graph={"ignores": ["vendor", "custom-dir"]})
            codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            txt = (pdir / _CFG).read_text()
            self.assertIn('- "custom-dir"', txt)
            self.assertNotIn('- "packages"', txt)        # no default - took the config

    def test_pre_index_launched_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, code=True,
                                          code_graph={"pre_index": True})
            with mock.patch.object(codegraph.shutil, "which", return_value="/u/uvx"), \
                 mock.patch.object(codegraph.subprocess, "Popen") as popen:
                codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
                popen.assert_called_once()
                argv = popen.call_args.args[0]
                self.assertIn("index", argv)
                self.assertIn(str(pdir), argv)            # {root} substituted

    def test_pre_index_skipped_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, _ = _setup(tmp, code=True,
                                          code_graph={"pre_index": False})
            with mock.patch.object(codegraph.shutil, "which", return_value="/u/uvx"), \
                 mock.patch.object(codegraph.subprocess, "Popen") as popen:
                codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
                popen.assert_not_called()


class TestSchemaConnectivity(unittest.TestCase):
    """Gate connectivity diagram↔pin (D111, P5.4): check_schema_connectivity."""

    def test_consistent_state_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, code=True)
            self.assertEqual(codegraph.check_schema_connectivity(config), [])

    def test_schema_mismatch_detected(self):
        # pretends D109: pin awaits old key 'languages', renderer prints
        # 'language_servers' — the gate must fall precisely at this discrepancy.
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, code=True)
            with mock.patch.object(codegraph, "SERENA_SCHEMA_FIELDS",
                                    frozenset({"languages"})):
                issues = codegraph.check_schema_connectivity(config)
            self.assertTrue(any("scheme diverged" in i for i in issues), issues)
            self.assertTrue(any("languages" in i and "language_servers" in i
                                 for i in issues), issues)

    def test_unpinned_source_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, code=True)
            with mock.patch.object(codegraph, "SERENA_SRC",
                                    "git+https://github.com/oraios/serena"):
                issues = codegraph.check_schema_connectivity(config)
            self.assertTrue(any("pin missing" in i and "SERENA_SRC" in i
                                 for i in issues), issues)

    def test_missing_optional_key_not_flagged(self):
        # optional key (defaulted Serena) missing from renderer output - gate
        # should NOT consider this a discrepancy (F2, D117: set narrowed to FIELDS_WITHOUT_DEFAULTS).
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, code=True)
            original = codegraph.render_project_yaml

            def _without_encoding(*a, **kw):
                return "\n".join(line for line in original(*a, **kw).splitlines()
                                  if not line.startswith("encoding:"))

            with mock.patch.object(codegraph, "render_project_yaml", _without_encoding):
                issues = codegraph.check_schema_connectivity(config)
            self.assertEqual(issues, [])

    def test_missing_required_key_flagged(self):
        # required key (language_servers) is missing in the renderer output - the gate must
        # catch this (F2, D117: narrowing should not weaken the real divergence).
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, code=True)
            original = codegraph.render_project_yaml

            def _without_language_servers(*a, **kw):
                return "\n".join(line for line in original(*a, **kw).splitlines()
                                  if not line.startswith("language_servers"))

            with mock.patch.object(codegraph, "render_project_yaml", _without_language_servers):
                issues = codegraph.check_schema_connectivity(config)
            self.assertTrue(any("scheme diverged" in i and "language_servers" in i
                                 for i in issues), issues)

    def test_pins_diverge_between_src_and_config_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(
                tmp, code=True,
                code_graph={"args": [
                    "--from", "git+https://github.com/oraios/serena@v1.5.3",
                    "serena", "start-mcp-server",
                ]})
            issues = codegraph.check_schema_connectivity(config)
            self.assertTrue(any("pins dispersed" in i for i in issues), issues)


if __name__ == "__main__":
    unittest.main()
