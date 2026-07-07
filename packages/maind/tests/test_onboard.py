"""Тесты onboard — цепочка register → integrate → deploy → seed (standalone-safe)."""
import json
import tempfile
import unittest
from pathlib import Path

import maind.provision.onboard as onb
from maind.config import load_config
from maind.projects import get
from tests.fixtures import make_repo


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
            finally:
                onb.run_capability = orig

    def test_repeat_onboard_by_path_does_not_duplicate_entry(self):
        # Баг (инцидент loqum x3): _ensure_project матчил существующий проект ТОЛЬКО по
        # id — повторный `maind onboard <тот же абсолютный путь>` (не по id) не находил
        # уже зарегистрированную запись и штамповал дубль с тем же id при каждом вызове.
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
        # N4 (P1-review): остаточный edge того же инцидента loqum — norm_path раньше
        # делал только expanduser+normpath, без резолва симлинков, поэтому онбординг
        # ТОГО ЖЕ каталога через симлинк на него не матчился с уже зарегистрированным
        # local_path и штамповал дубль-запись.
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
            _seed_config(root)  # нет проекта swissknifeman → integrate упадёт → skip
            proj_dir = Path(tmp) / "p"
            proj_dir.mkdir()
            config, _ = load_config(env)
            report = onb.onboard(env, config, str(proj_dir), {"yes": True, "dry": False})
            names = {s["name"]: s["status"] for s in report["steps"]}
            self.assertEqual(names["skills"], "skipped")
            self.assertEqual(names["deploy"], "ok")
            self.assertTrue((proj_dir / ".mcp.json").exists())

    def test_cmd_onboard_escalates_on_unavailable_dep(self):
        # S9: skiller недоступен → шаг skills skipped(недоступен) → rc≠0 (не «зелёный»)
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)
            proj_dir = Path(tmp) / "p2"
            proj_dir.mkdir()
            with self.assertRaises(SystemExit) as cm:
                onb.cmd_onboard(env, [str(proj_dir), "--yes"])
            self.assertNotEqual(cm.exception.code, 0)

    def test_cmd_onboard_allow_partial_no_escalation(self):
        # --allow-partial: осознанный частичный онбординг не эскалирует
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)
            proj_dir = Path(tmp) / "p3"
            proj_dir.mkdir()
            onb.cmd_onboard(env, [str(proj_dir), "--yes", "--allow-partial"])
            self.assertTrue(get(load_config(env)[0], "p3"))  # дошли без SystemExit

    def test_onboard_registers_namespaces(self):
        # реестр config["namespaces"] (dict) наполняется ns'ами проекта при онбординге.
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
        # повторный онбординг не должен перетирать уже заданные метаданные namespace'а —
        # setdefault, не присвоение.
        orig = onb.run_capability
        onb.run_capability = lambda *a, **k: 0
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _seed_config(root)
            proj_dir = Path(tmp) / "idemproj"
            proj_dir.mkdir()
            try:
                config, _ = load_config(env)
                config["namespaces"] = {"axioma": {"name": "axioma", "note": "куратор задал вручную"}}
                onb.onboard(env, config, str(proj_dir),
                           {"namespaces": ["axioma", "idemproj"], "yes": True, "dry": False})
                cfg2, _ = load_config(env)
                self.assertEqual(cfg2["namespaces"]["axioma"],
                                 {"name": "axioma", "note": "куратор задал вручную"})
                self.assertIn("idemproj", cfg2["namespaces"])
                # повторный прогон тем же набором — реестр не меняется
                onb.onboard(env, cfg2, str(proj_dir),
                           {"namespaces": ["axioma", "idemproj"], "yes": True, "dry": False})
                cfg3, _ = load_config(env)
                self.assertEqual(cfg3["namespaces"]["axioma"],
                                 {"name": "axioma", "note": "куратор задал вручную"})
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
                self.assertFalse((proj_dir / ".mcp.json").exists())  # ничего не записано
                cfg2, _ = load_config(env)
                self.assertIsNone(get(cfg2, "d"))                    # не зарегистрирован
            finally:
                onb.run_capability = orig


if __name__ == "__main__":
    unittest.main()
