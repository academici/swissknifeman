"""Role processes of the conductor: a role that keeps writing is never stopped for its length; a silent one is."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from orch.conductor import process  # noqa: E402

BUSY = ("import sys,time\\nsys.stdin.read()\\nfor n in range(6):\\n print('{\"type\":\"x\"}', flush=True)\\n time.sleep(0.5)\\n"
        "print('{\"type\":\"result\",\"result\":\"done\",\"usage\":{}}', flush=True)")
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

    def test_a_silent_role_is_stopped_by_the_idle_limit(self):
        run = self.run_role(SILENT, timeout_s=0, idle_timeout_s=1)
        self.assertEqual((run.error, run.detail), ("TIMEOUT", "no output for 1 s"))

    def test_the_wall_clock_ceiling_still_stops_a_long_role_when_asked_for(self):
        run = self.run_role(BUSY, timeout_s=1, idle_timeout_s=0)
        self.assertEqual((run.error, run.detail), ("TIMEOUT", "no result within 1 s"))


if __name__ == "__main__":
    unittest.main()
