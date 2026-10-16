"""Native request identity survives delivery gaps without inventing inference state."""
from pathlib import Path
import tempfile
import unittest

from aicore.provider.request_lifecycle import Observer, status


class RequestLifecycleTests(unittest.TestCase):
    def test_delivery_gap_then_tool_and_terminal(self):
        with tempfile.TemporaryDirectory() as temporary:
            now = [10]
            observer = Observer(temporary, clock=lambda: now[0])
            observer.observe("client", {"id": 7, "method": "turn/start", "params": {
                "threadId": "thread", "input": [{"text": "private prompt"}]}})
            view = status(temporary, now=100)[0]
            self.assertEqual(view["request_id"], 7)
            self.assertEqual(view["phase"], "submitted")
            self.assertEqual(view["current_state"], "unknown")
            observer.observe("server", {"id": 7, "result": {"turn": {"id": "turn"}}})
            observer.observe("server", {"method": "turn/started", "params": {
                "threadId": "thread", "turn": {"id": "turn"}}})
            observer.observe("server", {"method": "item/started", "params": {
                "threadId": "thread", "turnId": "turn", "item": {"id": "tool", "type": "commandExecution"}}})
            self.assertEqual(status(temporary, now=10)[0]["phase"], "waiting-tool")
            observer.observe("server", {"method": "item/agentMessage/delta", "params": {
                "threadId": "thread", "turnId": "turn", "delta": "private answer"}})
            self.assertEqual(status(temporary, now=10)[0]["phase"], "waiting-tool")
            observer.observe("server", {"method": "item/completed", "params": {
                "threadId": "thread", "turnId": "turn", "item": {"id": "tool"}}})
            observer.observe("server", {"method": "turn/completed", "params": {
                "threadId": "thread", "turn": {"id": "turn", "status": "interrupted"}}})
            observer.disconnect(exit_code=0)
            self.assertEqual(status(temporary, now=1000)[0]["current_state"], "interrupted")
            evidence = (Path(temporary) / "events.jsonl").read_text()
            self.assertNotIn("private prompt", evidence)
            self.assertNotIn("private answer", evidence)

    def test_ack_after_started_and_failed_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            observer = Observer(temporary)
            observer.observe("client", {"id": "a", "method": "turn/start", "params": {"threadId": "t"}})
            observer.observe("server", {"method": "turn/started", "params": {"threadId": "t", "turn": {"id": "v"}}})
            observer.observe("server", {"id": "a", "result": {"turn": {"id": "v"}}})
            self.assertEqual(status(temporary)[0]["turn_id"], "v")
            observer.observe("client", {"id": "b", "method": "turn/start", "params": {"threadId": "u"}})
            observer.observe("server", {"id": "b", "error": {"code": -1, "message": "private error"}})
            observer.disconnect(exit_code=1)
            rows = {row["request_id"]: row for row in status(temporary)}
            self.assertEqual(rows["a"]["phase"], "unknown")
            self.assertEqual(rows["b"]["phase"], "failed")
