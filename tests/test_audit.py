"""Тест fleet-аудита (audit.py): per-project read-only проверки оптимизаций."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from maind import audit, codegraph  # noqa: E402
import tests.fixtures as fx  # noqa: E402


def _make_project(tmp, *, claude_lines=0, deny=False, mcp=None, skills=None):
    p = Path(tmp) / "proj"
    p.mkdir(parents=True, exist_ok=True)
    if claude_lines:
        (p / "CLAUDE.md").write_text("x\n" * claude_lines, encoding="utf-8")
    (p / ".claude").mkdir(exist_ok=True)
    if deny:
        (p / ".claude" / "settings.json").write_text(json.dumps(
            {"permissions": {"deny": ["Read(_ide_helper*.php)"]}}), encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
