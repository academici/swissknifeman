"""Internal documentation."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

FAKE_CLAUDE = Path(__file__).resolve().parent / "fixtures_data" / "run" / "fake-claude"

from aicore.provider.models import ModelCatalogError, load_model_catalog, select_effort, select_model
from harness.run import worker


class BuildArgvTest(unittest.TestCase):
    def test_literal_argv_for_implementation_medium(self):
        argv = worker.build_argv(
            "2026.07.31-DEMO-PLAN", "P4.3",
            model_class="implementation", effort="medium",
            claude_bin="/usr/bin/fake-claude")
        self.assertEqual(argv, [
            "/usr/bin/fake-claude", "-p", "/planner:plan-run 2026.07.31-DEMO-PLAN P4.3",
            "--output-format", "json", "--model", "sonnet", "--effort", "medium",
        ])

    def test_unknown_model_class_is_worker_unavailable(self):
        with self.assertRaises(worker.WorkerUnavailable):
            worker.build_argv(
                "2026.07.31-DEMO-PLAN", "P4.3",
                model_class="not-a-class", effort="medium",
                claude_bin="/usr/bin/fake-claude")

    def test_selectors_come_from_the_aicore_model_catalog(self):
        catalog = load_model_catalog()
        argv = worker.build_argv("P", "P1.1", model_class="frontier", effort="xhigh",
                                 claude_bin="/usr/bin/fake-claude")
        self.assertEqual(argv[argv.index("--model") + 1], select_model(catalog, "claude-code", "frontier"))
        self.assertEqual(argv[argv.index("--effort") + 1], select_effort(catalog, "claude-code", "xhigh"))

    def test_unknown_class_names_the_model_catalog(self):
        with self.assertRaisesRegex(worker.WorkerUnavailable, "model catalog: no class selector 'nope'"):
            worker.build_argv("P", "P1.1", model_class="nope", effort="medium",
                              claude_bin="/usr/bin/fake-claude")

    def test_unreadable_model_catalog_is_worker_unavailable(self):
        with mock.patch.object(worker, "load_model_catalog",
                               side_effect=ModelCatalogError("", "unreadable", "gone")):
            with self.assertRaisesRegex(worker.WorkerUnavailable, "model catalog not available"):
                worker.build_argv("P", "P1.1", model_class="implementation", effort="medium",
                                  claude_bin="/usr/bin/fake-claude")


class RunOutcomeTest(unittest.TestCase):
    def _run(self, fixture_name, *, timeout=worker.DEFAULT_TIMEOUT):
        return worker.run(
            "2026.07.31-DEMO-PLAN", "P4.3",
            model_class="implementation", effort="medium",
            claude_bin=str(FAKE_CLAUDE / fixture_name),
            timeout=timeout)

    def test_success_envelope_is_ok(self):
        outcome = self._run("success")
        self.assertEqual(outcome["outcome"], worker.OUTCOME_OK)
        self.assertEqual(outcome["session_id"], "fake-session-success")
        self.assertEqual(outcome["total_cost_usd"], 0.08049650)
        self.assertEqual(outcome["num_turns"], 1)
        self.assertEqual(outcome["client_version"], "2.1.220 (Claude Code)")
        self.assertEqual(outcome["exit_code"], 0)

    def test_broken_json_is_transport(self):
        outcome = self._run("transport-broken-json")
        self.assertEqual(outcome["outcome"], worker.OUTCOME_TRANSPORT)
        self.assertIsNotNone(outcome["reason"])
        self.assertIn("{not-json-at-all", outcome["raw_stdout"])

    def test_empty_stdout_is_transport(self):
        outcome = self._run("transport-empty")
        self.assertEqual(outcome["outcome"], worker.OUTCOME_TRANSPORT)
        self.assertIsNotNone(outcome["reason"])

    def test_hung_process_is_timeout(self):
        outcome = self._run("timeout", timeout=0.5)
        self.assertEqual(outcome["outcome"], worker.OUTCOME_TIMEOUT)
        self.assertIsNotNone(outcome["reason"])

    def test_quota_marker_in_error_result_is_quota(self):
        outcome = self._run("quota")
        self.assertEqual(outcome["outcome"], worker.OUTCOME_QUOTA)
        self.assertEqual(outcome["exit_code"], 1)

    def test_permission_denials_stays_ok_but_propagates(self):
        outcome = self._run("permission-denials")
        self.assertEqual(outcome["outcome"], worker.OUTCOME_OK)
        self.assertTrue(outcome["permission_denials"])

    def test_missing_binary_is_worker_unavailable_not_silent_ok(self):
        env_backup = os.environ.get(worker.CLAUDE_BIN_ENV)
        os.environ[worker.CLAUDE_BIN_ENV] = "/definitely/not/a/real/claude-binary"
        try:
            with self.assertRaises(worker.WorkerUnavailable):
                worker.run("2026.07.31-DEMO-PLAN", "P4.3",
                          model_class="implementation", effort="medium",
                          claude_bin=None)
        finally:
            if env_backup is None:
                os.environ.pop(worker.CLAUDE_BIN_ENV, None)
            else:
                os.environ[worker.CLAUDE_BIN_ENV] = env_backup


class QuotaTextMarkerTest(unittest.TestCase):
    def test_both_donor_markers_recognized(self):
        self.assertTrue(worker._is_quota_text("Claude AI usage limit reached: session limit"))
        self.assertTrue(worker._is_quota_text("hit your weekly limit"))
        self.assertFalse(worker._is_quota_text("some other error entirely"))


if __name__ == "__main__":
    sys.exit(unittest.main())
