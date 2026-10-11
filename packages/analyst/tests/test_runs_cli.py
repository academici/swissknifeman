"""analyst runs show|codegraph: output validates against run-lookup/v1 and run-codegraph/v1."""
import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

import aicore
from aicore.util.schema import load_contract, validate
from analyst.cli import main

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
FOUNDATION = Path(aicore.__file__).resolve().parents[2] / "schemas"


def _registry(name):
    registry, kind = load_contract(SCHEMAS / name / "v1", urn_prefix="urn:swissknifeman:analyst:", foundation=FOUNDATION)
    return registry, kind


def _event(session="s1", event_id="e1"):
    return {
        "contract_version": "1.0.0", "provider_id": "claude-code", "session_id": session,
        "project_id": "proj", "event_id": event_id, "occurred_at": "2026-01-01T00:00:00Z",
        "event_kind": "run_summary", "outcome": "ok", "metrics": {"tools": 3},
        "provenance": {"raw_ref": "local:abc", "sha256": hashlib.sha256(b"x").hexdigest(),
                       "reader_id": "r", "reader_version": "1"},
    }


class TestRunsCli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.proj = Path(self._tmp.name).resolve()

    def run_cli(self, *args, expect=0):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                main(["/unused", "runs", *args])
            except SystemExit as exc:
                code = exc.code
        self.assertEqual(code or 0, expect, err.getvalue())
        return out.getvalue(), err.getvalue()

    def show(self, *extra):
        out, _ = self.run_cli("show", "--project", str(self.proj), *extra, "--json")
        doc = json.loads(out)
        registry, kind = _registry("run-lookup")
        self.assertEqual([issue for issue in validate(doc, kind, registry)], [])
        return doc

    def write_report(self, session, report, folder=".claude/runs", mtime=None):
        path = self.proj / folder / f"{session}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report), encoding="utf-8")
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def test_missing_report_exits_zero(self):
        doc = self.show()
        self.assertEqual(doc["lookup"], {"status": "missing", "path": None, "reason": None})
        self.assertEqual((doc["report"], doc["codegraph"], doc["events"]), (None, None, []))
        self.assertEqual(doc["project"], str(self.proj))

    def test_found_report_with_codegraph_and_events(self):
        path = self.write_report("s1", {"session_id": "s1", "tools": {"by_name": {"mcp__serena__find_symbol": 2}}})
        events = self.proj / ".swissknife" / "analytics" / "events.ndjson"
        events.parent.mkdir(parents=True)
        events.write_text(json.dumps(_event("s1")) + "\n" + json.dumps(_event("s2", "e2")) + "\n", encoding="utf-8")
        doc = self.show("--session", "s1")
        self.assertEqual(doc["lookup"], {"status": "found", "path": str(path), "reason": None})
        self.assertEqual(doc["report"]["session_id"], "s1")
        self.assertEqual(doc["codegraph"]["by_op"], {"find_symbol": 2})
        self.assertEqual([event["event_id"] for event in doc["events"]], ["e1"])
        self.assertEqual(len(self.show()["events"]), 2)

    def test_rejected_report_carries_the_reason(self):
        self.write_report("s1", {"session_id": "s1", "cwd": "/somewhere/else"})
        doc = self.show("--session", "s1")
        self.assertEqual(doc["lookup"]["status"], "rejected")
        self.assertEqual(doc["lookup"]["reason"], "RUN_REPORT_PROJECT_MISMATCH")
        self.assertIsNone(doc["report"])

    def test_text_output(self):
        out, _ = self.run_cli("show", "--project", str(self.proj))
        self.assertTrue(out.startswith("run report: missing"))

    def test_codegraph_lists_reports_newest_first_and_limits(self):
        self.write_report("old", {"tools": {"by_name": {"mcp__serena__find_symbol": 1}}}, mtime=1000)
        self.write_report("new", {"tools": {"by_name": {"mcp__serena__find_symbol": 4}}}, folder=".cursor/runs", mtime=2000)
        (self.proj / ".codex" / "runs").mkdir(parents=True)
        (self.proj / ".codex" / "runs" / "bad.json").write_text("{", encoding="utf-8")
        out, _ = self.run_cli("codegraph", "--project", str(self.proj), "--json")
        doc = json.loads(out)
        registry, kind = _registry("run-codegraph")
        self.assertEqual(validate(doc, kind, registry), [])
        self.assertEqual([(row["provider"], row["summary"]["calls"]) for row in doc["reports"]],
                         [("cursor", 4), ("claude-code", 1)])
        limited = json.loads(self.run_cli("codegraph", "--project", str(self.proj), "--limit", "1", "--json")[0])
        self.assertEqual(len(limited["reports"]), 1)

    def test_argument_errors_exit_two(self):
        self.run_cli("show", expect=2)
        self.run_cli("nope", expect=2)
        self.run_cli("show", "--project", str(self.proj), "--bogus", expect=2)
        self.run_cli("codegraph", "--project", str(self.proj), "--limit", "x", expect=2)


if __name__ == "__main__":
    unittest.main()
