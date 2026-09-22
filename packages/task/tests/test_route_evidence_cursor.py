"""Cursor cli-config capture resolves grok-4.7 without a manual model_class."""
import json
import os
import tempfile
import unittest
from pathlib import Path

import fixtures  # noqa: F401 — puts lib/ and the monorepo root on sys.path

from task.route_evidence import MODEL_CLASS_ORDER
from task.route_evidence_cursor import capture_current
from task.task_contract import MODEL_CLASS_ORDER as CONTRACT_ORDER


ROUTING = Path(__file__).resolve().parents[1] / "configs" / "command-routing.json"


class CursorCliConfigRouteTests(unittest.TestCase):
    def test_selected_model_and_reasoning_effort_need_no_manual_class(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "cli-config.json"
            config.write_text(json.dumps({
                "selectedModel": {
                    "modelId": "grok-4.7",
                    "parameters": [
                        {"id": "context", "value": "500k"},
                        {"id": "reasoning_effort", "value": "high"},
                    ],
                },
            }), encoding="utf-8")
            evidence = capture_current(
                expected_invocation="task:plan-run 2026.08.06-EDUFY-BUILD P14.4",
                expected_cwd=os.getcwd(),
                routing_path=ROUTING,
                cli_config_path=config,
                process_table={},
            )
            self.assertNotIn(
                "model_class",
                json.loads(config.read_text(encoding="utf-8"))["selectedModel"],
            )

        self.assertEqual(evidence["model"], "grok-4.7")
        self.assertEqual(evidence["effort"], "high")
        self.assertGreaterEqual(
            CONTRACT_ORDER.index(evidence["model_class"]),
            CONTRACT_ORDER.index("implementation"),
        )
        self.assertEqual(evidence["source"], "provider-config")
        self.assertIn(evidence["model_class"], MODEL_CLASS_ORDER)


if __name__ == "__main__":
    unittest.main()
