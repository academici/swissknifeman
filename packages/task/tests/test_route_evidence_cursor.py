"""Cursor cli-config capture resolves grok-4.7 without a manual model_class."""
import json
import os
import sqlite3
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import fixtures  # noqa: F401 — puts lib/ and the monorepo root on sys.path

from task.route_evidence import MODEL_CLASS_ORDER, RouteEvidenceError
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

    def test_grok_46_effort_alias_maps_to_frontier_high(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "cli-config.json"
            config.write_text(json.dumps({
                "selectedModel": {
                    "modelId": "grok-4.6",
                    "parameters": [
                        {"id": "effort", "value": "high"},
                        {"id": "fast", "value": "false"},
                    ],
                },
            }), encoding="utf-8")
            evidence = capture_current(
                expected_invocation="task:plan-run 2026.09.22-№1-CHATOM-PRODUCT-FOUNDATION P00.4 P00.5",
                expected_cwd=os.getcwd(),
                routing_path=ROUTING,
                cli_config_path=config,
                process_table={},
            )

        self.assertEqual(evidence["model"], "grok-4.6")
        self.assertEqual(evidence["model_class"], "frontier")
        self.assertEqual(evidence["effort"], "high")
        self.assertEqual(evidence["source"], "provider-config")


class CursorArgvRouteTests(unittest.TestCase):
    def _table(self, model: str, prompt: str) -> dict:
        return {
            10: (1, (
                "agent",
                "--workspace", os.getcwd(),
                "--model", model,
                "--force",
                prompt,
            )),
        }

    def test_grok_47_high_slug_admits_session_suffix(self):
        prompt = "task:plan-exec LOQUM-DEV P1.8 — session E10. rest"
        evidence = capture_current(
            expected_invocation="task:plan-exec LOQUM-DEV P1.8",
            expected_cwd=os.getcwd(),
            routing_path=ROUTING,
            process_table=self._table("grok-4.7-high", prompt),
            start_pid=10,
        )
        self.assertEqual(evidence["model"], "grok-4.7-high")
        self.assertEqual(evidence["model_class"], "frontier")
        self.assertEqual(evidence["effort"], "high")
        self.assertEqual(evidence["source"], "cli-flag")
        self.assertEqual(evidence["source_version"], "cursor-ancestor-argv-v1")
        self.assertEqual(evidence["invocation"], prompt)

    def test_argv_thread_uses_cursor_conversation_id(self):
        prompt = "task:plan-exec LOQUM-DEV P1.9 — session E11. rest"
        with unittest.mock.patch.dict(
            os.environ,
            {"CURSOR_CONVERSATION_ID": "conv-e11"},
            clear=False,
        ):
            evidence = capture_current(
                expected_invocation="task:plan-exec LOQUM-DEV P1.9",
                expected_cwd=os.getcwd(),
                routing_path=ROUTING,
                process_table=self._table("grok-4.7-high", prompt),
                start_pid=10,
            )
        self.assertEqual(evidence["thread_id"], "conv-e11")
        self.assertEqual(evidence["source"], "cli-flag")

    def test_catalog_model_without_effort_suffix_stays_medium(self):
        evidence = capture_current(
            expected_invocation="task:plan-exec LOQUM-DEV P1.8",
            expected_cwd=os.getcwd(),
            routing_path=ROUTING,
            process_table=self._table("grok-4.7", "task:plan-exec LOQUM-DEV P1.8"),
            start_pid=10,
        )
        self.assertEqual(evidence["model"], "grok-4.7")
        self.assertEqual(evidence["effort"], "medium")
        self.assertEqual(evidence["model_class"], "frontier")

    def test_thinking_high_catalog_id_is_not_split(self):
        evidence = capture_current(
            expected_invocation="task:plan-exec LOQUM-DEV P1.8",
            expected_cwd=os.getcwd(),
            routing_path=ROUTING,
            process_table=self._table(
                "claude-opus-5-thinking-high",
                "task:plan-exec LOQUM-DEV P1.8",
            ),
            start_pid=10,
        )
        self.assertEqual(evidence["model"], "claude-opus-5-thinking-high")
        self.assertEqual(evidence["model_class"], "frontier")
        self.assertEqual(evidence["effort"], "medium")

    def test_item_prefix_does_not_match_longer_id(self):
        with self.assertRaises(RouteEvidenceError) as raised:
            capture_current(
                expected_invocation="task:plan-exec LOQUM-DEV P1.8",
                expected_cwd=os.getcwd(),
                routing_path=ROUTING,
                process_table=self._table(
                    "grok-4.7-high",
                    "task:plan-exec LOQUM-DEV P1.80",
                ),
                start_pid=10,
            )
        self.assertEqual(raised.exception.code, "ROUTE_LAUNCH_MISMATCH")


class CursorResumeRouteTests(unittest.TestCase):
    def test_resume_reads_last_used_model_and_latest_prompt(self):
        prompt = "task:plan-exec LOQUM-DEV P1.8 — session E10. rest"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            chat = root / "bucket" / "chat-1"
            chat.mkdir(parents=True)
            (chat / "meta.json").write_text(json.dumps({"cwd": os.getcwd()}), encoding="utf-8")
            (chat / "prompt_history.json").write_text(json.dumps([prompt, "older"]), encoding="utf-8")
            connection = sqlite3.connect(chat / "store.db")
            connection.execute("CREATE TABLE meta (key TEXT, value TEXT)")
            payload = json.dumps({
                "agentId": "chat-1",
                "lastUsedModel": "grok-4.7-high",
                "blobEncryptionKey": "secret-must-not-matter",
            }).encode("utf-8")
            connection.execute("INSERT INTO meta VALUES (?, ?)", ("0", payload.hex()))
            connection.commit()
            connection.close()
            evidence = capture_current(
                expected_invocation="task:plan-exec LOQUM-DEV P1.8",
                expected_cwd=os.getcwd(),
                routing_path=ROUTING,
                process_table={10: (1, ("cursor-agent", "resume", "--force", "--sandbox", "disabled"))},
                start_pid=10,
                chats_root=root,
                conversation_id="chat-1",
                cli_config_path=root / "missing-cli-config.json",
            )
        self.assertEqual(evidence["model"], "grok-4.7-high")
        self.assertEqual(evidence["model_class"], "frontier")
        self.assertEqual(evidence["effort"], "high")
        self.assertEqual(evidence["source"], "provider-thread-state")
        self.assertEqual(evidence["source_version"], "cursor-chat-store-v1")
        self.assertEqual(evidence["thread_id"], "chat-1")
        self.assertEqual(evidence["invocation"], prompt)
        self.assertNotIn("secret-must-not-matter", json.dumps(evidence))


if __name__ == "__main__":
    unittest.main()
