"""Тесты onboard — цепочка register → integrate → deploy → seed (standalone-safe)."""
import json
import tempfile
import unittest
from pathlib import Path

import maind.onboard as onb
from maind.config import load_config
from maind.projects import get
from tests.fixtures import make_repo


def _seed_config(root, projects=None):
    (root / ".maind.json").write_text(
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
            finally:
                onb.run_capability = orig

    def test_skm_missing_skipped_but_deploys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)  # нет проекта swissknifeman → integrate упадёт → skip
            proj_dir = Path(tmp) / "p"
            proj_dir.mkdir()
            config, _ = load_config(env)
            report = onb.onboard(env, config, str(proj_dir), {"yes": True, "dry": False})
            names = {s["name"]: s["status"] for s in report["steps"]}
            self.assertEqual(names["skills"], "skipped")
            self.assertEqual(names["deploy"], "ok")
            self.assertTrue((proj_dir / ".mcp.json").exists())

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
                self.assertFalse((proj_dir / ".mcp.json").exists())  # ничего не записано
                cfg2, _ = load_config(env)
                self.assertIsNone(get(cfg2, "d"))                    # не зарегистрирован
            finally:
                onb.run_capability = orig


if __name__ == "__main__":
    unittest.main()
