"""Тест fleet-аудита (audit.py): per-project read-only проверки оптимизаций."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from maind.analysis import audit  # noqa: E402
from maind import codegraph  # noqa: E402
from maind import pao  # noqa: E402
import tests.fixtures as fx  # noqa: E402


def _fake_harness_bin(tmp, body):
    """Скрипт-заглушка harness (см. test_orchestrate._fake_bin): печатает body в stdout."""
    p = Path(tmp) / "fake-harness"
    p.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    p.chmod(0o755)
    return p


class SettingsDimCase(unittest.TestCase):
    """Измерение settings в audit_project/run_audit — fail-soft subprocess к harness (D10)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_repo(self.tmp)
        self.code_st = codegraph.settings({})
        self._old_env = os.environ.get("MAIND_HARNESS_BIN")

    def tearDown(self):
        self._tmp.cleanup()
        if self._old_env is None:
            os.environ.pop("MAIND_HARNESS_BIN", None)
        else:
            os.environ["MAIND_HARNESS_BIN"] = self._old_env

    def test_settings_status_reports_counts_from_fake_harness(self):
        payload = json.dumps({"counts": {"error": 1, "warn": 2, "info": 0}})
        os.environ["MAIND_HARNESS_BIN"] = str(
            _fake_harness_bin(self.tmp, f"echo '{payload}'"))
        p = _make_project(self.tmp)
        row = audit.audit_project(self.env, {"id": "proj", "local_path": str(p)},
                                  ("settings",), self.code_st, config={})
        self.assertEqual(row["settings"], {"error": 1, "warn": 2, "info": 0})

    def test_settings_status_unavailable_when_harness_missing(self):
        os.environ.pop("MAIND_HARNESS_BIN", None)
        p = _make_project(self.tmp)
        # config без записи проекта swissknifeman → _sibling_bin die() → SystemExit → unavailable
        row = audit.audit_project(self.env, {"id": "proj", "local_path": str(p)},
                                  ("settings",), self.code_st, config={})
        self.assertEqual(row["settings"], "unavailable")

    def test_settings_status_broken_stdout_is_unavailable_no_traceback(self):
        os.environ["MAIND_HARNESS_BIN"] = str(
            _fake_harness_bin(self.tmp, "echo 'not json at all {'"))
        p = _make_project(self.tmp)
        row = audit.audit_project(self.env, {"id": "proj", "local_path": str(p)},
                                  ("settings",), self.code_st, config={})
        self.assertEqual(row["settings"], "unavailable")

    def test_run_audit_settings_dim_prints_ok_and_does_not_crash(self):
        payload = json.dumps({"counts": {"error": 0, "warn": 0, "info": 3}})
        os.environ["MAIND_HARNESS_BIN"] = str(
            _fake_harness_bin(self.tmp, f"echo '{payload}'"))
        p = _make_project(self.tmp, claude_lines=1)
        fx.write_maind_config(self.root, projects=[
            {"id": "proj", "name": "Proj", "type": "node-package",
             "status": "active", "dependencies": [], "local_path": str(p)}])
        from maind.config import load_config
        config, _ = load_config(self.env)
        _, out = fx.capture(audit.run_audit, self.env, config, "settings")
        self.assertIn("settings✓", out)


def _make_project(tmp, *, claude_lines=0, deny=False, mcp=None, skills=None,
                  plugins=None):
    p = Path(tmp) / "proj"
    p.mkdir(parents=True, exist_ok=True)
    if claude_lines:
        (p / "CLAUDE.md").write_text("x\n" * claude_lines, encoding="utf-8")
    (p / ".claude").mkdir(exist_ok=True)
    if deny:
        (p / ".claude" / "settings.json").write_text(json.dumps(
            {"permissions": {"deny": ["Read(_ide_helper*.php)"]}}), encoding="utf-8")
    if plugins:  # connect-канал: enabledPlugins бакеты в settings.local.json
        (p / ".claude" / "settings.local.json").write_text(json.dumps(
            {"enabledPlugins": {f"{b}@swissknifeman": True for b in plugins}}),
            encoding="utf-8")
    if mcp:
        (p / ".mcp.json").write_text(json.dumps(
            {"mcpServers": {n: {} for n in mcp}}), encoding="utf-8")
    for s in (skills or []):
        (p / ".claude" / "skills" / s).mkdir(parents=True, exist_ok=True)
    return p


class AuditCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_repo(self.tmp)
        self.code_st = codegraph.settings({})

    def tearDown(self):
        self._tmp.cleanup()

    def test_audit_project_full(self):
        p = _make_project(self.tmp, claude_lines=250, deny=True,
                          mcp=["agentmemory", "maind", "laravel-boost"],
                          skills=["context-economy", "anti-drift"])
        row = audit.audit_project(self.env, {"id": "proj", "local_path": str(p)},
                                  audit.DIMS, self.code_st)
        self.assertEqual(row["status"], "ok")
        # hub-серверы не кандидаты на ревизию, сторонний — да
        self.assertIn("laravel-boost", row["mcp"]["review"])
        self.assertNotIn("agentmemory", row["mcp"]["review"])
        self.assertNotIn("maind", row["mcp"]["review"])
        self.assertGreater(row["claude_md_lines"], audit.CLAUDE_MD_WARN)
        self.assertTrue(row["deny"])
        # 2 CORE присутствуют → остальные в missing
        self.assertEqual(set(row["core"]["missing"]),
                         {"compact-responses", "session-handoff", "gh-review"})

    def test_audit_project_bare(self):
        p = _make_project(self.tmp)
        row = audit.audit_project(self.env, {"id": "bare", "local_path": str(p)},
                                  audit.DIMS, self.code_st)
        self.assertIsNone(row["claude_md_lines"])
        self.assertFalse(row["deny"])
        self.assertEqual(set(row["core"]["missing"]), set(audit.CORE_SKILLS))
        self.assertEqual(row["mcp"]["servers"], [])

    def test_core_present_via_connect_buckets(self):
        # connect-канал: CORE доезжает бакет-плагинами general+oss-dev (без физ. файлов)
        p = _make_project(self.tmp, plugins=["general", "oss-dev"])
        row = audit.audit_project(self.env, {"id": "c", "local_path": str(p)},
                                  audit.DIMS, self.code_st)
        self.assertEqual(row["core"]["missing"], [])

    def test_core_partial_via_connect_buckets(self):
        # включён только general → gh-review (oss-dev) остаётся missing
        p = _make_project(self.tmp, plugins=["general"])
        row = audit.audit_project(self.env, {"id": "c", "local_path": str(p)},
                                  audit.DIMS, self.code_st)
        self.assertEqual(row["core"]["missing"], ["gh-review"])

    def test_missing_path(self):
        row = audit.audit_project(self.env,
                                  {"id": "gone", "local_path": str(self.tmp / "nope")},
                                  audit.DIMS, self.code_st)
        self.assertEqual(row["status"], "missing-path")

    def test_run_audit_smoke(self):
        p = _make_project(self.tmp, claude_lines=10, mcp=["maind"])
        fx.write_maind_config(self.root, projects=[
            {"id": "proj", "name": "Proj", "type": "node-package",
             "status": "active", "dependencies": [], "local_path": str(p)}])
        from maind.config import load_config
        config, _ = load_config(self.env)
        _, out = fx.capture(audit.run_audit, self.env, config, "all")
        self.assertIn("proj", out)
        self.assertIn("maind audit", out)

    def test_invalid_dim_dies(self):
        with self.assertRaises(SystemExit):
            audit.run_audit(self.env, {}, "bogus")

    @mock.patch.object(pao, "_php_version", return_value=(8, 4))
    def test_audit_pao_missing(self, _m):
        p = _make_project(self.tmp)
        proj = {"id": "proj", "type": "laravel-project", "local_path": str(p)}
        row = audit.audit_project(self.env, proj, ("pao",), self.code_st)
        self.assertEqual(row["pao"], "missing")

    @mock.patch.object(pao, "_php_version", return_value=(8, 4))
    def test_audit_pao_installed(self, _m):
        p = _make_project(self.tmp)
        (p / "vendor" / "laravel" / "pao").mkdir(parents=True)
        proj = {"id": "proj", "type": "laravel-project", "local_path": str(p)}
        row = audit.audit_project(self.env, proj, ("pao",), self.code_st)
        self.assertEqual(row["pao"], "installed")

    def test_audit_pao_not_applicable_for_non_php(self):
        p = _make_project(self.tmp)
        proj = {"id": "proj", "type": "node-package", "local_path": str(p)}
        row = audit.audit_project(self.env, proj, ("pao",), self.code_st)
        self.assertEqual(row["pao"], "n-a")

    @mock.patch.object(pao, "_php_version", return_value=(8, 1))
    def test_audit_pao_php_too_old_is_clean(self, _m):
        p = _make_project(self.tmp)
        proj = {"id": "proj", "type": "php-package", "local_path": str(p)}
        row = audit.audit_project(self.env, proj, ("pao",), self.code_st)
        self.assertEqual(row["pao"], "php-too-old")

    def test_audit_pao_optout_is_clean(self):
        p = _make_project(self.tmp)
        proj = {"id": "proj", "type": "laravel-project",
               "pao_opt_out": True, "local_path": str(p)}
        row = audit.audit_project(self.env, proj, ("pao",), self.code_st)
        self.assertEqual(row["pao"], "opt-out")

    @mock.patch.object(pao, "_php_version", return_value=(8, 4))
    def test_run_audit_pao_warns_in_text_output(self, _m):
        p = _make_project(self.tmp)
        fx.write_maind_config(self.root, projects=[
            {"id": "phpproj", "name": "PhpProj", "type": "laravel-project",
             "status": "active", "dependencies": [], "local_path": str(p)}])
        from maind.config import load_config
        config, _ = load_config(self.env)
        _, out = fx.capture(audit.run_audit, self.env, config, "pao")
        self.assertIn("pao⚠(missing: composer require laravel/pao --dev)", out)


if __name__ == "__main__":
    unittest.main()
