"""Tests for codegraph_usage fleet scanner: it reads the report summaries through analyst."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from aicore.util.partners import partner_command
from maind.codegraph_usage import fleet_summary, format_project_line, scan_project, usage_note
from tests.fixtures import make_fake_analyst
from tests.test_analyze import partner_env


def _report(provider, calls, by_op=None):
    return {"provider": provider, "path": f"/p/{provider}.json", "mtime": 1.0,
            "summary": {"calls": calls, "ops": len(by_op or {}), "by_op": by_op or {}}}


def _payload(project, reports):
    return {"$schema": "urn:swissknifeman:analyst:run-codegraph:v1", "project": str(project), "reports": reports}


class TestCodegraphUsage(unittest.TestCase):
    def test_scan_project_counts_codegraph_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake, calls = make_fake_analyst(Path(tmp) / "bin", codegraph=_payload(tmp, [
                _report("claude-code", 2, {"find_symbol": 2}), _report("claude-code", 0)]))
            with partner_env(fake):
                snap = scan_project(tmp, limit=10)
            self.assertEqual((snap["status"], snap["sessions"], snap["code_sessions"], snap["calls"]),
                             ("ok", 2, 1, 2))
            self.assertEqual(snap["by_op"], {"find_symbol": 2})
            self.assertEqual(snap["by_provider"]["claude-code"], {"sessions": 2, "code_sessions": 1, "calls": 2})
            self.assertEqual(calls(), [["runs", "codegraph", "--project", tmp, "--limit", "10", "--json"]])

    def test_fleet_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake, _ = make_fake_analyst(Path(tmp) / "bin", codegraph=_payload(tmp, [
                _report("cursor", 1, {"find_symbol": 1})]))
            projects = [{"id": "demo", "enabled": True, "local_path": tmp, "code": True}]
            with partner_env(fake):
                fleet = fleet_summary(projects)
            self.assertEqual(fleet["totals"]["calls"], 1)
            self.assertIn("1/1", usage_note(fleet))

    def test_project_without_reports_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake, _ = make_fake_analyst(Path(tmp) / "bin", codegraph=_payload(tmp, []))
            with partner_env(fake):
                fleet = fleet_summary([{"id": "demo", "enabled": True, "local_path": tmp}])
            self.assertEqual(fleet["projects"], [])

    def test_without_analyst_the_project_row_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp, partner_env():
            snap = scan_project(tmp)
            fleet = fleet_summary([{"id": "demo", "enabled": True, "local_path": tmp}])
        self.assertEqual((snap["status"], snap["reason"]), ("unavailable", "PARTNER_UNAVAILABLE"))
        self.assertEqual(fleet["projects"][0]["status"], "unavailable")
        self.assertEqual(usage_note(fleet), "analyst unavailable (PARTNER_UNAVAILABLE)")
        self.assertEqual(format_project_line(fleet["projects"][0], True), "demo[code:on] unavailable (PARTNER_UNAVAILABLE)")

    def test_failing_analyst_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake, _ = make_fake_analyst(Path(tmp) / "bin", exit_code=1)
            with partner_env(fake):
                self.assertEqual(scan_project(tmp)["reason"], "PARTNER_FAILED")


class TestWithRealAnalyst(unittest.TestCase):
    def setUp(self):
        if not (os.environ.get("SKM_ANALYST_ROOT") or os.environ.get("SKM_ANALYST_BIN")) \
                or partner_command("analyst") is None:
            self.skipTest("analyst not found (set SKM_ANALYST_ROOT)")

    def test_scan_project_counts_codegraph_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / ".claude" / "runs"
            runs.mkdir(parents=True)
            (runs / "a.json").write_text(json.dumps({
                "tools": {"by_name": {"Read": 5, "mcp__codegraph__find_symbol": 2}},
                "codegraph": {"find_symbol": {"calls": 2}},
            }), encoding="utf-8")
            (runs / "b.json").write_text(json.dumps({"tools": {"by_name": {"Grep": 10}}}), encoding="utf-8")
            snap = scan_project(tmp, limit=10)
            self.assertEqual((snap["sessions"], snap["code_sessions"], snap["calls"]), (2, 1, 2))


if __name__ == "__main__":
    unittest.main()
