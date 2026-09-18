"""Tests for codegraph_usage fleet scanner."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from maind.codegraph_usage import fleet_summary, scan_project, usage_note


class TestCodegraphUsage(unittest.TestCase):
    def test_scan_project_counts_codegraph_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / ".claude" / "runs"
            runs.mkdir(parents=True)
            (runs / "a.json").write_text(json.dumps({
                "tools": {"by_name": {"Read": 5, "mcp__codegraph__find_symbol": 2}},
                "codegraph": {"find_symbol": {"calls": 2}},
            }), encoding="utf-8")
            (runs / "b.json").write_text(json.dumps({
                "tools": {"by_name": {"Grep": 10}},
            }), encoding="utf-8")
            snap = scan_project(tmp, limit=10)
            self.assertEqual(snap["sessions"], 2)
            self.assertEqual(snap["code_sessions"], 1)
            self.assertEqual(snap["calls"], 2)

    def test_fleet_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / ".cursor" / "runs"
            runs.mkdir(parents=True)
            (runs / "c.json").write_text(json.dumps({
                "provider_id": "cursor",
                "codegraph": {"find_symbol": {"calls": 1}},
            }), encoding="utf-8")
            projects = [{"id": "demo", "enabled": True, "local_path": tmp, "code": True}]
            fleet = fleet_summary(projects)
            self.assertEqual(fleet["totals"]["calls"], 1)
            self.assertIn("1/1", usage_note(fleet))


if __name__ == "__main__":
    unittest.main()
