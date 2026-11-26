"""Test fleet-audit (audit.py): per-project read-only optimization checks."""
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
    """Stub script harness (see test_orchestrate._fake_bin): prints body in stdout."""
    p = Path(tmp) / "fake-harness"
    p.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    p.chmod(0o755)
    return p


class SettingsDimCase(unittest.TestCase):
    """Measurement settings in audit_project/run_audit — fail-soft subprocess to harness (D10)."""

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
        # no harness launcher anywhere → PARTNER_UNAVAILABLE → SystemExit → unavailable
        with mock.patch.dict(os.environ, {"PATH": str(self.tmp)}):
            os.environ.pop("SKM_HARNESS_BIN", None)
            os.environ.pop("SKM_HARNESS_ROOT", None)
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
    if plugins:  # connect-channel: enabledPlugins buckets in settings.local.json
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
        # hub-servers are not candidates for revision, third party - yes
        self.assertIn("laravel-boost", row["mcp"]["review"])
        self.assertNotIn("agentmemory", row["mcp"]["review"])
        self.assertNotIn("maind", row["mcp"]["review"])
        self.assertGreater(row["claude_md_lines"], audit.CLAUDE_MD_WARN)
        self.assertTrue(row["deny"])
        # 2 CORE present → others in missing
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

    def test_audit_project_reports_mcp_parity(self):
        p = _make_project(self.tmp, mcp=["maind", "figma"])
        (p / ".cursor").mkdir(parents=True, exist_ok=True)
        (p / ".cursor" / "mcp.json").write_text(json.dumps({
            "mcpServers": {"maind": {}, "figma": {}}}), encoding="utf-8")
        (p / ".codex").mkdir(exist_ok=True)
        (p / ".codex" / "config.toml").write_text(
            "[mcp_servers.maind]\ncommand = \"maind\"\n", encoding="utf-8")
        (p / ".claude" / "settings.json").write_text(json.dumps({
            "mcpServers": {"figma": {"url": "https://example.test"}}}), encoding="utf-8")
        row = audit.audit_project(self.env, {"id": "proj", "local_path": str(p)},
                                  ("mcp",), self.code_st, config={})
        parity = row["mcp"]["parity"]
        self.assertEqual(parity["settings_dup"], ["figma"])
        self.assertTrue(any(d["only_left"] == ["figma"] for d in parity["drifts"]))

    def _carriers(self, p, claude, cursor, codex):
        (p / ".mcp.json").write_text(json.dumps({"mcpServers": {n: {} for n in claude}}), encoding="utf-8")
        (p / ".cursor").mkdir(parents=True, exist_ok=True)
        (p / ".cursor" / "mcp.json").write_text(json.dumps({"mcpServers": {n: {} for n in cursor}}), encoding="utf-8")
        (p / ".codex").mkdir(exist_ok=True)
        (p / ".codex" / "config.toml").write_text(
            "".join(f"[mcp_servers.{n}]\ncommand = \"x\"\n" for n in codex), encoding="utf-8")

    def test_code_providers_exclude_code_graph_only_from_disallowed_surfaces(self):
        p = _make_project(self.tmp)
        self._carriers(p, ["maind", "codegraph"], ["maind", "codegraph"], ["maind"])
        project = {"id": "proj", "local_path": str(p), "code_providers": ["claude-code", "cursor"]}
        row = audit.audit_project(self.env, project, ("mcp",), self.code_st, config={})
        self.assertEqual(row["mcp"]["parity"]["drifts"], [])

    def test_code_providers_keep_drift_between_allowed_surfaces(self):
        p = _make_project(self.tmp)
        self._carriers(p, ["maind", "codegraph"], ["maind"], ["maind"])
        project = {"id": "proj", "local_path": str(p), "code_providers": ["claude-code", "cursor"]}
        row = audit.audit_project(self.env, project, ("mcp",), self.code_st, config={})
        pairs = {(d["left"], d["right"]) for d in row["mcp"]["parity"]["drifts"]}
        self.assertEqual(pairs, {("claude", "cursor")})

    def test_core_present_via_connect_buckets(self):
        # connect-channel: CORE comes with bucket plugins general+oss-dev (without physical. files)
        p = _make_project(self.tmp, plugins=["general", "oss-dev"])
        row = audit.audit_project(self.env, {"id": "c", "local_path": str(p)},
                                  audit.DIMS, self.code_st)
        self.assertEqual(row["core"]["missing"], [])

    def test_core_present_via_connect_core_plugin(self):
        # connect-channel (current default): supervised core@ instead general+oss-dev
        p = _make_project(self.tmp, plugins=["core"])
        row = audit.audit_project(self.env, {"id": "c", "local_path": str(p)},
                                  audit.DIMS, self.code_st)
        self.assertEqual(row["core"]["missing"], [])

    def test_core_partial_via_connect_buckets(self):
        # enabled only general → gh-review (oss-dev) remains missing
        p = _make_project(self.tmp, plugins=["general"])
        row = audit.audit_project(self.env, {"id": "c", "local_path": str(p)},
                                  audit.DIMS, self.code_st)
        self.assertEqual(row["core"]["missing"], ["gh-review"])

    def test_present_skills_list_lock_format(self):
        """Brain-valt and others: skills-lock.json::skills like list, not dict."""
        p = _make_project(self.tmp)
        (p / "skills-lock.json").write_text(json.dumps({
            "skills": [{"name": "context-economy", "source": "swissknifeman"}],
        }), encoding="utf-8")
        row = audit.audit_project(self.env, {"id": "brain", "local_path": str(p)},
                                  audit.DIMS, self.code_st)
        self.assertNotIn("context-economy", row["core"]["missing"])

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
