"""Grok argv/config capture: grok and Grok ``agent``; never Cursor ``agent --workspace``."""
import os
import tempfile
import unittest
from pathlib import Path

try:
    import fixtures  # noqa: F401 — puts lib/ and the monorepo root on sys.path
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fixtures  # noqa: F401,E402

from task.route_evidence import MODEL_CLASS_ORDER, RouteEvidenceError
from task.route_evidence_grok import capture_current
from task.task_contract import MODEL_CLASS_ORDER as CONTRACT_ORDER


ROUTING = Path(__file__).resolve().parents[1] / "configs" / "command-routing.json"


class GrokConfigRouteTests(unittest.TestCase):
    def test_config_default_model_needs_no_manual_class(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.toml"
            config.write_text(
                '[models]\ndefault = "grok-4.6"\ndefault_reasoning_effort = "high"\n',
                encoding="utf-8")
            evidence = capture_current(
                expected_invocation="/task:plan-run 2026.08.06-DEMO-PLAN P14.4",
                expected_cwd=os.getcwd(),
                routing_path=ROUTING,
                config_path=config,
                process_table={},
            )
        self.assertEqual(evidence["model"], "grok-4.6")
        self.assertEqual(evidence["effort"], "high")
        self.assertEqual(evidence["model_class"], "implementation")
        self.assertEqual(evidence["source"], "provider-config")
        self.assertIn(evidence["model_class"], MODEL_CLASS_ORDER)
        self.assertGreaterEqual(
            CONTRACT_ORDER.index(evidence["model_class"]),
            CONTRACT_ORDER.index("implementation"))


class GrokArgvRouteTests(unittest.TestCase):
    def _table(self, *argv):
        return {10: (1, argv)}

    def test_grok_binary_slash_prompt_admits_session_suffix(self):
        prompt = "/task:plan-run LOQUM-DEV P1.8 — session E10. rest"
        evidence = capture_current(
            expected_invocation="/task:plan-run LOQUM-DEV P1.8",
            expected_cwd=os.getcwd(),
            routing_path=ROUTING,
            process_table=self._table(
                "grok", "--cwd", os.getcwd(), "--model", "grok-4.7",
                "--always-approve", prompt),
            start_pid=10,
        )
        self.assertEqual(evidence["model"], "grok-4.7")
        self.assertEqual(evidence["model_class"], "frontier")
        self.assertEqual(evidence["effort"], "medium")
        self.assertEqual(evidence["source"], "cli-flag")
        self.assertEqual(evidence["source_version"], "grok-ancestor-argv-v1")
        self.assertEqual(evidence["invocation"], prompt)

    def test_agent_alias_with_cwd_is_grok(self):
        prompt = "/task:fix"
        evidence = capture_current(
            expected_invocation="/task:fix",
            expected_cwd=os.getcwd(),
            routing_path=ROUTING,
            process_table=self._table(
                "/home/user/.grok/bin/agent", "--cwd", os.getcwd(),
                "-m", "grok-4.6", prompt),
            start_pid=10,
        )
        self.assertEqual(evidence["model"], "grok-4.6")
        self.assertEqual(evidence["model_class"], "implementation")

    def test_cursor_agent_workspace_is_not_grok(self):
        prompt = "task:plan-run LOQUM-DEV P1.8"
        with self.assertRaises(RouteEvidenceError) as caught:
            capture_current(
                expected_invocation="/task:plan-run LOQUM-DEV P1.8",
                expected_cwd=os.getcwd(),
                routing_path=ROUTING,
                config_path=Path("/nonexistent/config.toml"),
                process_table=self._table(
                    "agent", "--workspace", os.getcwd(), "--model", "grok-4.7",
                    "--force", prompt),
                start_pid=10,
            )
        self.assertEqual(caught.exception.code, "ROUTE_LAUNCH_UNAVAILABLE")
