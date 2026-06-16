"""Тесты codegraph.py — провиженер дефолтного .serena/project.yml (код-граф Serena)."""
import tempfile
import unittest
from pathlib import Path

from maind import codegraph
from maind.config import load_config
from tests.fixtures import make_repo, write_maind_config

_CFG = Path(".serena") / "project.yml"


def _setup(tmp, **proj):
    root, env = make_repo(tmp)
    pdir = Path(tmp) / "flexcrm"
    pdir.mkdir(parents=True, exist_ok=True)
    p = {"id": "flexcrm", "name": "FlexCRM", "type": "php-package",
         "enabled": True, "local_path": str(pdir)}
    p.update(proj)
    write_maind_config(root, projects=[p])
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
            self.assertIn("- php", txt)                 # язык по типу php-package
            self.assertIn('- "vendor"', txt)
            self.assertIn('- "packages"', txt)          # симлинки first-party не индексируем
            self.assertIn("initial_prompt:", txt)       # директива нацеливания на symbol-tools
            self.assertIn("Serena", txt)

    def test_disabled_when_graphify_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)   # без graphify
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
            (pdir / _CFG).write_text("project_name: mine\n# мой конфиг\n", encoding="utf-8")
            r = codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            self.assertEqual(r["state"], "present")
            self.assertFalse(r["changed"])
            self.assertIn("мой конфиг", (pdir / _CFG).read_text())  # не перезаписан

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
            self.assertIn('- "**/vendor"', txt)              # рекурсию/дубли режем
            self.assertNotIn('- "packages"', txt)            # пакеты НЕ игнорим (единый граф)
            self.assertIn("ignore_all_files_in_gitignore: false", txt)
            self.assertIn("workspace", txt)                  # промпт про единый граф/правки

    def test_workspace_auto_detected_by_packages_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, graphify=True)   # без явного флага
            (pdir / "packages").mkdir()                            # → авто-workspace
            codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            txt = (pdir / _CFG).read_text(encoding="utf-8")
            self.assertNotIn('- "packages"', txt)
            self.assertIn('- "**/vendor"', txt)

    def test_explicit_false_overrides_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, graphify=True, graphify_workspace=False)
            (pdir / "packages").mkdir()                            # есть, но флаг=false
            codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            self.assertIn('- "packages"', (pdir / _CFG).read_text())  # дефолтный игнор

    def test_node_package_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp, graphify=True, type="node-package")
            codegraph.apply_serena_config(env, config, proj, "auto", dry=False)
            self.assertIn("- typescript", (pdir / _CFG).read_text())


if __name__ == "__main__":
    unittest.main()
