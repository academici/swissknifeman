"""The stdio launcher keeps wire bytes intact and archives only request identity."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from core.provider.request_lifecycle import status


class CodexRequestObserverLauncherTests(unittest.TestCase):
    def test_stdio_launcher_preserves_wire_bytes_and_archives_identity(self):
        launcher = Path(__file__).resolve().parents[1] / "scripts" / "codex-request-observer.py"
        messages = [
            {"id": 7, "result": {"turn": {"id": "turn"}}},
            {"method": "turn/started", "params": {"threadId": "thread", "turn": {"id": "turn"}}},
            {"method": "item/agentMessage/delta", "params": {
                "threadId": "thread", "turnId": "turn", "delta": "private answer"}},
            {"method": "turn/completed", "params": {
                "threadId": "thread", "turn": {"id": "turn", "status": "completed"}}},
        ]
        response = "".join(json.dumps(row) + "\n" for row in messages)
        request = json.dumps({"id": 7, "method": "turn/start", "params": {
            "threadId": "thread", "input": [{"text": "private prompt"}]}}) + "\n"
        server = "import sys; assert sys.stdin.readline() == " + repr(request) + "; sys.stdout.write(" + repr(response) + "); sys.stdout.flush()"
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run([sys.executable, str(launcher), "--output-dir", temporary,
                "--", sys.executable, "-u", "-c", server], input=request, text=True,
                capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, response)
            self.assertEqual(status(temporary)[0]["current_state"], "completed")
            archive = (Path(temporary) / "events.jsonl").read_text()
            self.assertNotIn("private prompt", archive)
            self.assertNotIn("private answer", archive)


if __name__ == "__main__":
    unittest.main()
