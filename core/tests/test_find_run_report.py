"""Tests core.runs.find_run_report* (the run-report finder stays in core until the analyst move)."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import find_run_report


class TestFindRunReport(unittest.TestCase):
    def _make(self, root, sid, payload):
        runs = Path(root) / ".claude" / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        (runs / f"{sid}.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_by_session(self):
        with tempfile.TemporaryDirectory() as d:
            self._make(d, "s1", {"session_id": "s1"})
            self.assertEqual(find_run_report(d, "s1")["session_id"], "s1")

    def test_latest(self):
        with tempfile.TemporaryDirectory() as d:
            self._make(d, "s1", {"session_id": "s1"})
            self.assertIsNotNone(find_run_report(d))

    def test_no_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(find_run_report(d))

    def test_foreign_absolute_changed_file_rejects_report_even_when_cwd_claims_project(self):
        from core.runs import find_run_report_result
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / ".claude" / "runs"
            runs.mkdir(parents=True)
            (runs / "s1.json").write_text(json.dumps({
                "session_id": "s1", "cwd": str(root),
                "files_changed": ["/tmp/another-project/app.py"],
            }), encoding="utf-8")
            result = find_run_report_result(root, "s1")
            self.assertIsNone(result.report)
            self.assertEqual(result.diagnostic["code"], "RUN_REPORT_PROJECT_MISMATCH")

    def test_session_provider_and_project_identity_are_checked_when_present(self):
        from core.runs import find_run_report_result
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make(root, "s1", {
                "session_id": "other", "provider_id": "codex",
                "project_id": "other-project", "cwd": str(root),
            })
            result = find_run_report_result(root, "s1", project_id="expected-project")
            self.assertIsNone(result.report)
            self.assertEqual(
                {row["field"] for row in result.diagnostic["conflicts"]},
                {"provider", "session_id", "project_id"},
            )

    def test_expanduser(self):
        # ~-path should expand (discrepancy that fixes the offset in core)
        with tempfile.TemporaryDirectory() as home:
            with mock.patch.dict(os.environ, {"HOME": home}):
                self._make(home, "s1", {"session_id": "s1"})
                self.assertIsNotNone(find_run_report("~", "s1"))


if __name__ == "__main__":
    unittest.main()
