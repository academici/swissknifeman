from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from artifex import cli


PLAN_SOURCE = Path(__file__).resolve().parents[3] / "artifacts/P1/supervisor-run-cases-v1.json"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"; self.repo.mkdir()
        self.plan = self.repo / "plan"; (self.plan / "artifacts/P1").mkdir(parents=True)
        (self.plan / "plan.md").write_text("# plan\n", encoding="utf-8")
        (self.plan / "artifacts/P1/supervisor-run-cases-v1.json").write_bytes(PLAN_SOURCE.read_bytes())
        self.runs = self.plan / "runs"; self.mandate = self.plan / "mandate.json"; self.mandate.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *tail):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = cli.main(["--repo-root", str(self.repo), "--plan-dir", "plan", "--runs-root", "plan/runs", *tail])
        return code, json.loads(stream.getvalue())

    def start(self, run_id="run-1"):
        manifest = {"content_hash": "a" * 64, "source_hashes": {"base_commit": "b" * 64, "plan": "c" * 64}, "plan_id": "plan", "scope": {"validation": ["check"]}}
        with mock.patch("artifex.cli.compiler.compile_slice", return_value=manifest):
            return self.call("start", "--run-id", run_id, "--phase", "P2", "--item", "P2.5", "--mandate", "plan/mandate.json")

    def test_start_status_report_and_idempotent_stop_are_bounded_json(self):
        code, result = self.start()
        self.assertEqual((0, "READY"), (code, result["state"]))
        code, result = self.call("status", "--run-id", "run-1")
        self.assertEqual((0, "READY"), (code, result["state"]))
        code, result = self.call("report", "--run-id", "run-1")
        self.assertEqual((0, True), (code, result["redacted"]))
        code, result = self.call("stop", "--run-id", "run-1")
        self.assertEqual((0, "ABORTED"), (code, result["state"]))
        code, result = self.call("stop", "--run-id", "run-1")
        self.assertEqual((0, True), (code, result["idempotent"]))

    def test_not_found_and_path_escape_refuse_without_writing(self):
        code, result = self.call("status", "--run-id", "missing")
        self.assertEqual((3, "RUN_NOT_FOUND"), (code, result["reason"]))
        code, result = self.call("start", "--run-id", "../escape", "--phase", "P2", "--item", "P2.5", "--mandate", "plan/mandate.json")
        self.assertEqual((2, "RUN_IDENTITY_MISMATCH"), (code, result["reason"]))
        self.assertFalse((self.repo.parent / "escape").exists())

    def test_reconcile_requires_a_durable_intent(self):
        self.start()
        code, result = self.call("reconcile", "--run-id", "run-1", "--observed", "third")
        self.assertEqual((2, "UNRESOLVED_INTENT_MISSING"), (code, result["reason"]))
