"""Acceptance checks of the conductor: ``parallel`` runs command checks together and keeps the order of the rows."""
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from orch.conductor import checks  # noqa: E402


def doc(*commands):
    return {"input_id": "T.W1@abc", "acceptance": {"checks": [
        {"id": f"V{index}", "cmd": cmd, "expect": "exit 0", "kind": "acceptance"}
        for index, cmd in enumerate(commands, 1)]}}


class ParallelChecksTests(unittest.TestCase):
    def run_checks(self, parallel, *commands):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"]):
                subprocess.run(["git", *args], cwd=tmp, check=True, capture_output=True)
            started = time.monotonic()
            rows = checks.run_checks(doc(*commands), project=root, evidence_dir=root / "ev", log_dir=root / "log",
                                     timeout_s=30, evidence_prefix="r:W1:checks.1", parallel=parallel)
            return rows, time.monotonic() - started

    def test_parallel_checks_keep_the_order_and_save_time(self):
        slow = "sleep 1.5"
        rows, took = self.run_checks(3, slow, "exit 3", slow)
        self.assertEqual([(row["id"], row["exit"]) for row in rows], [("V1", 0), ("V2", 3), ("V3", 0)])
        self.assertLess(took, 3.0)

    def test_sequential_checks_run_one_after_another(self):
        rows, took = self.run_checks(1, "sleep 1", "sleep 1")
        self.assertEqual([row["green"] for row in rows], [True, True])
        self.assertGreaterEqual(took, 2.0)


class RedFirstTests(unittest.TestCase):
    def test_previously_red_checks_run_first_and_a_red_one_skips_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"]):
                subprocess.run(["git", *args], cwd=tmp, check=True, capture_output=True)
            marker = root / "ran-v2"
            rows = checks.run_checks(doc("exit 1", f"touch {marker}"), project=root, evidence_dir=root / "ev",
                                     log_dir=root / "log", timeout_s=30, evidence_prefix="r:W1:checks.2", first=["V1"])
            self.assertEqual([(row["id"], row["green"], bool(row.get("skipped"))) for row in rows],
                             [("V1", False, False), ("V2", False, True)])
            self.assertFalse(marker.exists())  # the other check did not run
            ok = checks.run_checks(doc("true", f"touch {marker}"), project=root, evidence_dir=root / "ev",
                                   log_dir=root / "log", timeout_s=30, evidence_prefix="r:W1:checks.3", first=["V1"])
            self.assertEqual([row["green"] for row in ok], [True, True])  # V1 green, so the rest ran
            self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
