"""Role processes of the conductor: a role that keeps writing is never stopped for its length; a silent one is."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from orch.conductor import process  # noqa: E402

BUSY = ("import sys,time\\nsys.stdin.read()\\nfor n in range(6):\\n print('{\"type\":\"x\"}', flush=True)\\n time.sleep(0.5)\\n"
        "print('{\"type\":\"result\",\"result\":\"done\",\"usage\":{}}', flush=True)")
LINGER = ("import sys,time\\nsys.stdin.read()\\nprint('{\"type\":\"result\",\"result\":\"done\",\"usage\":{}}', flush=True)\\n"
          "time.sleep(60)")  # the final result is out, but a background task of the provider keeps the process alive
SILENT = "import sys,time\nsys.stdin.read()\ntime.sleep(30)"


class RoleProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old = process.POLL_S
        process.POLL_S = 0.2
        self.addCleanup(setattr, process, "POLL_S", self.old)

    def run_role(self, code, **limits):
        return process.run_role([sys.executable, "-c", code.replace("\\n", "\n")], "prompt", transport="stream-json",
                                cwd=Path(self.tmp.name), raw_path=Path(self.tmp.name) / "out.jsonl", **limits)

    def test_a_role_that_keeps_writing_outlives_the_idle_limit(self):
        run = self.run_role(BUSY, timeout_s=0, idle_timeout_s=2)  # runs about 3 s, silent for 0.5 s at most
        self.assertIsNone(run.error, run.detail)
        self.assertEqual(run.text, "done")

    def test_a_role_that_has_given_its_result_but_does_not_exit_is_reaped_after_the_grace(self):
        started = time.monotonic()
        run = self.run_role(LINGER, timeout_s=0, idle_timeout_s=0, result_grace_s=1)
        self.assertLess(time.monotonic() - started, 20)
        self.assertIsNone(run.error, run.detail)
        self.assertEqual((run.text, run.exit, run.lingered), ("done", 0, True))

    def test_a_role_that_exits_by_itself_is_not_marked_lingering(self):
        run = self.run_role(BUSY, timeout_s=0, idle_timeout_s=0, result_grace_s=1)
        self.assertFalse(run.lingered)

    def test_a_silent_role_is_stopped_by_the_idle_limit(self):
        run = self.run_role(SILENT, timeout_s=0, idle_timeout_s=1)
        self.assertEqual((run.error, run.detail), ("TIMEOUT", "no output for 1 s"))

    def test_the_wall_clock_ceiling_still_stops_a_long_role_when_asked_for(self):
        run = self.run_role(BUSY, timeout_s=1, idle_timeout_s=0)
        self.assertEqual((run.error, run.detail), ("TIMEOUT", "no result within 1 s"))


if __name__ == "__main__":
    unittest.main()


class ActivityAndUsageTests(unittest.TestCase):
    def test_activity_names_the_child_processes_of_a_role(self):
        import subprocess
        child = subprocess.Popen(["sh", "-c", "sleep 30 & wait"], start_new_session=True)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        import time
        time.sleep(0.3)
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "s.jsonl"
            raw.write_text('{"type":"assistant","message":{"id":"m1","content":[{"type":"tool_use","name":"Bash",'
                           '"input":{"command":"bash scripts/test.sh"}}],"usage":{"input_tokens":5,'
                           '"cache_read_input_tokens":7,"output_tokens":2}}}\n', encoding="utf-8")
            text = process.activity(child.pid, raw)
            self.assertIn("last command: Bash: bash scripts/test.sh", text)
            self.assertIn("sleep 30", text)
            self.assertEqual(process.partial_usage(raw.read_text()), {"input": 5, "cached": 7, "output": 2})
        import os
        import signal
        os.killpg(child.pid, signal.SIGKILL)

    def test_activity_follows_the_process_tree_into_other_sessions(self):
        # the shell of a model's Bash tool may sit in a session of its own
        import subprocess
        import time
        code = ("import subprocess, time\\nsubprocess.Popen(['sleep', '31'], start_new_session=True)\\ntime.sleep(31)")
        child = subprocess.Popen([sys.executable, "-c", code.replace("\\n", "\n")], start_new_session=True)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        time.sleep(0.5)
        with tempfile.TemporaryDirectory() as tmp:
            text = process.activity(child.pid, Path(tmp) / "none")
        subprocess.run(["pkill", "-fx", "sleep 31"], check=False)
        self.assertIn("sleep 31", text)

    def test_a_role_without_children_is_said_to_wait_on_its_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("no child process", process.activity(999999, Path(tmp) / "none"))
