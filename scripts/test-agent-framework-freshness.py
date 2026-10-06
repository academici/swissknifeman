#!/usr/bin/env python3
"""Tests scripts/agent-framework-freshness.py — synthetic canon table and pack.json files."""
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "agent_framework_freshness",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent-framework-freshness.py"),
)
freshness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(freshness)

TABLE = "# Overview\n\n| Pack | Version |\n| --- | --- |\n{rows}\n\nAfter.\n"


class TestAgentFrameworkFreshness(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.overview = self.root / "framework-overview.md"
        self.packs = self.root / "agent-packs"
        self.packs.mkdir()

    def canon(self, rows):
        self.overview.write_text(TABLE.format(rows="\n".join(rows)), encoding="utf-8")

    def pack(self, name, value):
        path = self.packs / name / "pack.json"
        path.parent.mkdir()
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")

    def test_matching_table_is_green(self):
        self.canon(["| base | 1.2.0 |", "| php | 0.3.1 |"])
        self.pack("base", {"version": "1.2.0"})
        self.pack("php", {"version": "0.3.1"})
        errors, note = freshness.check(self.overview, self.packs)
        self.assertEqual(errors, [])
        self.assertEqual(note, "framework canon: table «pack → version» matches pack.json (2 packs)")

    def test_stale_missing_and_superfluous_rows_fail(self):
        self.canon(["| base | 1.1.0 |", "| gone | 0.1.0 |"])
        self.pack("base", {"version": "1.2.0"})
        self.pack("new", {"version": "0.1.0"})
        errors, _ = freshness.check(self.overview, self.packs)
        self.assertEqual(errors, [
            "pack `base`: canon announces `1.1.0`, pack.json carries `1.2.0` — update the table "
            "in `framework-overview.md`: `base` `1.2.0`",
            "pack `new` is not declared in canon - update the table in `framework-overview.md`: "
            "`new` `0.1.0`",
            "string `gone` is superfluous in canon (pack is not in "
            "packages/harness/configs/claude-code/agent-packs) — remove line from tables in "
            "`framework-overview.md`",
        ])

    def test_malformed_row_names_its_line(self):
        self.canon(["| base | v1 |"])
        self.pack("base", {"version": "1.2.0"})
        errors, _ = freshness.check(self.overview, self.packs)
        self.assertTrue(errors[0].startswith("docs/agent-framework/framework-overview.md:5: table row"))

    def test_missing_table_and_bad_pack_json_fail(self):
        self.overview.write_text("# no table\n", encoding="utf-8")
        self.pack("broken", "{")
        self.pack("unversioned", {"name": "x"})
        errors, _ = freshness.check(self.overview, self.packs)
        self.assertIn("no table «pack → version»", errors[0])
        self.assertTrue(any(e.startswith("agent-packs/broken/pack.json: invalid JSON") for e in errors))
        self.assertIn("agent-packs/unversioned/pack.json: no string field version", errors)

    def test_missing_inputs_skip_explicitly(self):
        errors, note = freshness.check(self.overview, self.root / "absent")
        self.assertEqual(errors, [])
        self.assertIn("standalone-layout", note)
        errors, note = freshness.check(self.root / "absent.md", self.packs)
        self.assertEqual(errors, [])
        self.assertIn("freshness gate missed", note)

    def test_main_exit_codes(self):
        self.canon(["| base | 1.0.0 |"])
        self.pack("base", {"version": "2.0.0"})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = freshness.main(["--overview", str(self.overview), "--packs", str(self.packs)])
        self.assertEqual(rc, 1)
        self.assertIn("ERROR: frame canon has fallen behind the tree (1)", err.getvalue())
        (self.packs / "base" / "pack.json").write_text(json.dumps({"version": "1.0.0"}),
                                                       encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = freshness.main(["--overview", str(self.overview), "--packs", str(self.packs)])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
