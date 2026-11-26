"""Tests onboard — chain register → integrate → deploy → seed (standalone-safe)."""
import os
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import maind.provision.onboard as onb
from maind.config import load_config
from maind.projects import get
from tests.fixtures import make_repo
from tests.harness_partner import RealHarnessCase


_XDG = {}


def setUpModule():
    # `onboard` starts the real skiller; without a throwaway machine state it would register the temporary
    # projects of these tests in the developer's own skiller/projects.json.
    _XDG["dir"] = tempfile.TemporaryDirectory()
    _XDG["patch"] = mock.patch.dict(os.environ, {"SKM_HOME": os.path.join(_XDG["dir"].name, "home")})
    _XDG["patch"].start()


def tearDownModule():
    _XDG["patch"].stop()
    _XDG["dir"].cleanup()


def _seed_config(root, projects=None):
    (root / "config.json").write_text(
        json.dumps({"_version": "1", "projects": projects or []}), encoding="utf-8")


class TestOnboard(unittest.TestCase):
    def test_new_path_full_chain(self):
        calls = []
        orig = onb.run_capability
        onb.run_capability = lambda e, c, pid, cap, extra=None, dry=False: \
            (calls.append(cap), 0)[1]
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)
            proj_dir = Path(tmp) / "newproj"
            proj_dir.mkdir()
            try:
                config, _ = load_config(env)
                report = onb.onboard(env, config, str(proj_dir),
                                     {"bundle": "recommended", "yes": True, "dry": False})
                self.assertEqual(report["project"], "newproj")
                self.assertTrue(report["created"])
                self.assertIn("skm:integrate", calls)                 # skills step
                self.assertTrue((proj_dir / ".mcp.json").exists())    # deploy wrote MCP
                cfg2, _ = load_config(env)
                self.assertTrue(get(cfg2, "newproj"))                 # registered
                names = {s["name"]: s["status"] for s in report["steps"]}
                self.assertEqual(names["register"], "ok")
                self.assertEqual(names["deploy"], "ok")
                self.assertEqual(names["graph"], "ok")
                # Instruction carriers are intentionally inapplicable outside the
                # umbrella monorepo; that conditional skip must not make onboarding fail.
                self.assertEqual(names["instructions"], "ok")
            finally:
                onb.run_capability = orig

    def test_onboard_reuses_one_provider_context_for_deploy_and_instructions(self):
        import maind.provision.deploy as deploy
        original, calls = deploy.provider_projection_context, []
        def counted(*args):
            calls.append(args[2]["id"])
            return original(*args)
        deploy.provider_projection_context = counted
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root, env = make_repo(tmp)
                _seed_config(root)
                project = Path(tmp) / "context-project"
                project.mkdir()
                config, _ = load_config(env)
                onb.onboard(env, config, str(project), {
                    "skip_skills": True, "yes": True, "dry": True,
                    "memory": "off", "repair": False,
                })
        finally:
            deploy.provider_projection_context = original
        self.assertEqual(calls, ["context-project"])

    def test_repeat_onboard_by_path_does_not_duplicate_entry(self):
        # Bug (incident loqum x3): _ensure_project matched an existing project ONLY by
        # id — repeated `maind onboard <same absolute path>` (not by id) couldn't find it
        # already registered entry and stamped a duplicate with the same id every time it is called.
        calls = []
        orig = onb.run_capability
        onb.run_capability = lambda e, c, pid, cap, extra=None, dry=False: \
            (calls.append(cap), 0)[1]
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)
            proj_dir = Path(tmp) / "loqum"
            proj_dir.mkdir()
            try:
                config, _ = load_config(env)
                r1 = onb.onboard(env, config, str(proj_dir),
                                 {"bundle": "recommended", "yes": True, "dry": False})
                self.assertTrue(r1["created"])
                config2, _ = load_config(env)
                r2 = onb.onboard(env, config2, str(proj_dir),
                                 {"bundle": "recommended", "yes": True, "dry": False})
                self.assertFalse(r2["created"])
                cfg3, _ = load_config(env)
                matches = [p for p in cfg3["projects"] if p.get("id") == "loqum"]
                self.assertEqual(len(matches), 1)
            finally:
                onb.run_capability = orig

    def test_repeat_onboard_via_symlink_does_not_duplicate_entry(self):
        # N4 (P1-review): residual edge same incident loqum — norm_path before
        # did only expanduser+normpath, without resolving symlinks, so onboarding
        # THE SAME directory through a symlink did not match with the already registered one
        # local_path and stamped a double entry.
        calls = []
        orig = onb.run_capability
        onb.run_capability = lambda e, c, pid, cap, extra=None, dry=False: \
            (calls.append(cap), 0)[1]
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)
            proj_dir = Path(tmp) / "loqum"
            proj_dir.mkdir()
            proj_link = Path(tmp) / "loqum-link"
            proj_link.symlink_to(proj_dir)
            try:
                config, _ = load_config(env)
                r1 = onb.onboard(env, config, str(proj_dir),
                                 {"bundle": "recommended", "yes": True, "dry": False})
                self.assertTrue(r1["created"])
                config2, _ = load_config(env)
                r2 = onb.onboard(env, config2, str(proj_link),
                                 {"bundle": "recommended", "yes": True, "dry": False})
                self.assertFalse(r2["created"])
                cfg3, _ = load_config(env)
                matches = [p for p in cfg3["projects"] if p.get("id") == "loqum"]
                self.assertEqual(len(matches), 1)
            finally:
                onb.run_capability = orig

    def test_skm_missing_skipped_but_deploys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)  # no project swissknifeman → integrate will fall → skip
            proj_dir = Path(tmp) / "p"
            proj_dir.mkdir()
            config, _ = load_config(env)
            with mock.patch.dict(os.environ, {"PATH": str(Path(tmp) / "none")}):
                for var in ("SKM_SKILLER_BIN", "SKM_SKILLER_ROOT", "MAIND_SKM_BIN"):
                    os.environ.pop(var, None)
                report = onb.onboard(env, config, str(proj_dir), {"yes": True, "dry": False})
            names = {s["name"]: s["status"] for s in report["steps"]}
            self.assertEqual(names["skills"], "skipped")
            self.assertEqual(names["deploy"], "ok")
            self.assertTrue((proj_dir / ".mcp.json").exists())

    def test_cmd_onboard_escalates_on_unavailable_dep(self):
        # S9: skiller not available → step skills skipped(not available) → rc≠0 (not «green»)
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)
            proj_dir = Path(tmp) / "p2"
            proj_dir.mkdir()
            with mock.patch.dict(os.environ, {"PATH": str(Path(tmp) / "none")}):
                for var in ("SKM_SKILLER_BIN", "SKM_SKILLER_ROOT", "MAIND_SKM_BIN"):
                    os.environ.pop(var, None)
                with self.assertRaises(SystemExit) as cm:
                    onb.cmd_onboard(env, [str(proj_dir), "--yes"])
            self.assertNotEqual(cm.exception.code, 0)

    def test_cmd_onboard_allow_partial_no_escalation(self):
        # --allow-partial: conscious partial onboarding does not escalate
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)
            proj_dir = Path(tmp) / "p3"
            proj_dir.mkdir()
            onb.cmd_onboard(env, [str(proj_dir), "--yes", "--allow-partial"])
            self.assertTrue(get(load_config(env)[0], "p3"))  # arrived without SystemExit

    def test_onboard_registers_namespaces(self):
        # registry config["namespaces"] (dict) is filling ns'ami of the project during onboarding.
        orig = onb.run_capability
        onb.run_capability = lambda *a, **k: 0
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)
            proj_dir = Path(tmp) / "nsproj"
            proj_dir.mkdir()
            try:
                config, _ = load_config(env)
                onb.onboard(env, config, str(proj_dir),
                           {"namespaces": ["axioma", "nsproj"], "yes": True, "dry": False})
                cfg2, _ = load_config(env)
                registry = cfg2.get("namespaces")
                self.assertIsInstance(registry, dict)
                self.assertIn("axioma", registry)
                self.assertIn("nsproj", registry)
                self.assertEqual(registry["nsproj"], {"name": "nsproj"})
            finally:
                onb.run_capability = orig

    def test_onboard_namespace_registration_idempotent(self):
        # re-onboarding should not overwrite already defined metadata namespace'a —
        # setdefault, not an assignment.
        orig = onb.run_capability
        onb.run_capability = lambda *a, **k: 0
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)
            proj_dir = Path(tmp) / "idemproj"
            proj_dir.mkdir()
            try:
                config, _ = load_config(env)
                config["namespaces"] = {"axioma": {"name": "axioma", "note": "curator set manually"}}
                onb.onboard(env, config, str(proj_dir),
                           {"namespaces": ["axioma", "idemproj"], "yes": True, "dry": False})
                cfg2, _ = load_config(env)
                self.assertEqual(cfg2["namespaces"]["axioma"],
                                 {"name": "axioma", "note": "curator set manually"})
                self.assertIn("idemproj", cfg2["namespaces"])
                # rerun with the same set - the registry does not change
                onb.onboard(env, cfg2, str(proj_dir),
                           {"namespaces": ["axioma", "idemproj"], "yes": True, "dry": False})
                cfg3, _ = load_config(env)
                self.assertEqual(cfg3["namespaces"]["axioma"],
                                 {"name": "axioma", "note": "curator set manually"})
            finally:
                onb.run_capability = orig

    def test_dry_run_writes_nothing(self):
        orig = onb.run_capability
        onb.run_capability = lambda *a, **k: 0
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)
            proj_dir = Path(tmp) / "d"
            proj_dir.mkdir()
            try:
                config, _ = load_config(env)
                onb.onboard(env, config, str(proj_dir), {"yes": True, "dry": True})
                self.assertFalse((proj_dir / ".mcp.json").exists())  # nothing recorded
                cfg2, _ = load_config(env)
                self.assertIsNone(get(cfg2, "d"))                    # not registered
            finally:
                onb.run_capability = orig


class TestOnboardInstructions(RealHarnessCase):
    """Instruction operations are harness's: this test needs the real partner (integration runner)."""

    def test_onboard_runs_instruction_provisioner_and_accepts_explicit_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)
            project = Path(tmp) / "instruction-project"
            for pkg in ("skiller", "maind", "harness"):
                (project / "packages" / pkg).mkdir(parents=True)
            config, _ = load_config(env)
            onb.onboard(env, config, str(project), {
                "skip_skills": True, "yes": True, "dry": False,
                "memory": "off", "repair": False,
            })
            (project / "CLAUDE.md").write_text(
                (project / "CLAUDE.md").read_text(encoding="utf-8").replace("#", "# drifted", 1),
                encoding="utf-8")
            config, _ = load_config(env)
            report = onb.onboard(env, config, str(project), {
                "skip_skills": True, "yes": True, "dry": False,
                "memory": "off", "repair": True,
            })
            step = next(item for item in report["steps"] if item["name"] == "instructions")
            self.assertEqual(step["status"], "ok")
            self.assertTrue((project / "CLAUDE.md").is_file())


if __name__ == "__main__":
    unittest.main()
