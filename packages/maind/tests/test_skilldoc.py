"""Tests skilldoc.py: managed skill provider ecosystem-mcp to projects."""
import shutil
import tempfile
import unittest
from pathlib import Path

from maind.provision import skilldoc
from maind.config import load_config
from tests.fixtures import make_repo, write_maind_config

_TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
_SKILL = Path(".claude") / "skills" / "ecosystem-mcp" / "SKILL.md"
_CODEX_SKILL = Path(".agents") / "skills" / "ecosystem-mcp" / "SKILL.md"


def _setup(tmp):
    root, env = make_repo(tmp)
    shutil.copytree(_TEMPLATES, root / "templates")  # templates available in env.root
    proj = Path(tmp) / "flexcrm"
    proj.mkdir(parents=True, exist_ok=True)
    projects = [{"id": "flexcrm", "name": "FlexCRM", "type": "php-package",
                 "status": "active", "enabled": True, "local_path": str(proj),
                 "memory_scope": "project:flexcrm", "namespaces": ["axioma"]}]
    write_maind_config(root, graph={"adapter": "federation"}, projects=projects)
    config, _ = load_config(env)
    return env, config, config["projects"][0], proj


class TestEcosystemSkill(unittest.TestCase):
    def test_skiller_root_bootstrap_projection_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            for name, apply in (("ecosystem-mcp", skilldoc.apply_ecosystem_skill),
                                ("ecosystem-setup", skilldoc.apply_setup_skill)):
                paths = (pdir / ".claude/skills" / name / "SKILL.md",
                         pdir / ".agents/skills" / name / "SKILL.md")
                text = ("---\nname: " + name + "\ncanonical: packages/skiller/skills/"
                        "repository-bootstrap/" + name + "/SKILL.md\n"
                        "generator: packages/skiller/lib/skiller/registry.py\n---\n"
                        "Thin projection.\n")
                for path in paths:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text, encoding="utf-8")
                self.assertEqual(apply(env, config, proj, "auto", True)["state"],
                                 "foreign-owner")
                result = apply(env, config, proj, "auto", False)
                self.assertEqual(result["status"], "skip")
                self.assertFalse(result["changed"])
                for path in paths:
                    self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_install_then_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            r1 = skilldoc.apply_ecosystem_skill(env, config, proj, "auto", dry=False)
            self.assertEqual(r1["state"], "absent")
            self.assertTrue(r1["changed"])
            text = (pdir / _SKILL).read_text(encoding="utf-8")
            self.assertIn("name: ecosystem-mcp", text)
            self.assertIn("flexcrm", text)            # {{PROJECT}}
            self.assertIn("project:flexcrm", text)    # {{SCOPE}}
            self.assertIn("axioma", text)             # {{NAMESPACES}}
            self.assertNotIn("{{", text)              # all placeholders are substituted
            self.assertEqual(text, (pdir / _CODEX_SKILL).read_text(encoding="utf-8"))
            r2 = skilldoc.apply_ecosystem_skill(env, config, proj, "auto", dry=False)
            self.assertEqual(r2["state"], "fresh")
            self.assertFalse(r2["changed"])

    def test_install_skips_stale_update_applies(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            skilldoc.apply_ecosystem_skill(env, config, proj, "auto", dry=False)
            target = pdir / _SKILL
            target.write_text(target.read_text() + "\ndrift\n", encoding="utf-8")
            r = skilldoc.apply_ecosystem_skill(env, config, proj, "install", dry=False)
            self.assertEqual(r["state"], "stale")
            self.assertFalse(r["changed"])            # install does not update outdated
            r2 = skilldoc.apply_ecosystem_skill(env, config, proj, "update", dry=False)
            self.assertTrue(r2["changed"])            # update — updates
            self.assertNotIn("drift", target.read_text())

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            r = skilldoc.apply_ecosystem_skill(env, config, proj, "auto", dry=True)
            self.assertEqual(r["status"], "dry")
            self.assertFalse((pdir / _SKILL).exists())
            self.assertFalse((pdir / _CODEX_SKILL).exists())

    def test_no_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, _ = _setup(tmp)
            proj = dict(proj)
            proj.pop("local_path")
            r = skilldoc.apply_ecosystem_skill(env, config, proj, "auto", dry=False)
            self.assertEqual(r["state"], "absent")
            self.assertFalse(r["changed"])


_SETUP_SKILL = Path(".claude") / "skills" / "ecosystem-setup" / "SKILL.md"
_CODEX_SETUP_SKILL = Path(".agents") / "skills" / "ecosystem-setup" / "SKILL.md"


class TestSetupSkill(unittest.TestCase):
    def test_install_substitutes_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            r1 = skilldoc.apply_setup_skill(env, config, proj, "auto", dry=False)
            self.assertEqual(r1["state"], "absent")
            self.assertTrue(r1["changed"])
            text = (pdir / _SETUP_SKILL).read_text(encoding="utf-8")
            self.assertIn("name: ecosystem-setup", text)
            self.assertIn("flexcrm", text)            # {{PROJECT}}
            self.assertIn("php-package", text)        # {{TYPE}}
            self.assertNotIn("{{", text)              # all placeholders are substituted
            self.assertEqual(text, (pdir / _CODEX_SETUP_SKILL).read_text(encoding="utf-8"))
            r2 = skilldoc.apply_setup_skill(env, config, proj, "auto", dry=False)
            self.assertEqual(r2["state"], "fresh")
            self.assertFalse(r2["changed"])

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            r = skilldoc.apply_setup_skill(env, config, proj, "auto", dry=True)
            self.assertEqual(r["status"], "dry")
            self.assertFalse((pdir / _SETUP_SKILL).exists())
            self.assertFalse((pdir / _CODEX_SETUP_SKILL).exists())


if __name__ == "__main__":
    unittest.main()
