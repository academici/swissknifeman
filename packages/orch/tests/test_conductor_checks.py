"""Acceptance checks of the conductor: ``parallel`` runs command checks together and keeps the order of the rows."""
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from orch.conductor import checks  # noqa: E402


def doc(*commands):
    return {"input_id": "T.W1@abc", "acceptance": {"checks": [
        {"id": f"V{index}", "cmd": cmd, "expect": "exit 0", "kind": "acceptance"}
        for index, cmd in enumerate(commands, 1)]}}


class ParallelChecksTests(unittest.TestCase):
    def setUp(self):  # the checks share the jobs budget: a worker of a test runner (budget 1) would run them one by one
        patcher = mock.patch.dict("os.environ", {"SKM_TEST_JOBS": "8"})
        patcher.start()
        self.addCleanup(patcher.stop)

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
        rows, took = self.run_checks(3, slow, "exit 3", slow)  # fail_fast: the red one cannot stop checks already running
        self.assertEqual([(row["id"], row["exit"]) for row in rows], [("V1", 0), ("V2", 3), ("V3", 0)])
        self.assertLess(took, 3.0)

    def test_sequential_checks_run_one_after_another(self):
        rows, took = self.run_checks(1, "sleep 1", "sleep 1")
        self.assertEqual([row["green"] for row in rows], [True, True])
        self.assertGreaterEqual(took, 2.0)


class KindsTests(unittest.TestCase):
    def test_a_quick_pass_runs_acceptance_checks_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"]):
                subprocess.run(["git", *args], cwd=tmp, check=True, capture_output=True)
            marker = root / "ran-impact"
            document = doc("true", f"touch {marker}")
            document["acceptance"]["checks"][1]["kind"] = "impact"
            quick = checks.run_checks(document, project=root, evidence_dir=root / "ev", log_dir=root / "log", timeout_s=30,
                                      evidence_prefix="r:W1:checks.1", kinds=("acceptance",))
            self.assertEqual([row["id"] for row in quick], ["V1"])
            self.assertFalse(marker.exists())
            full = checks.run_checks(document, project=root, evidence_dir=root / "ev", log_dir=root / "log", timeout_s=30,
                                     evidence_prefix="r:W1:checks.2")
            self.assertEqual([row["id"] for row in full], ["V1", "V2"])
            self.assertTrue(marker.exists())


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
            self.assertEqual(rows[1]["skip_reason"], "fail_fast")
            self.assertFalse(marker.exists())  # the other check did not run
            ok = checks.run_checks(doc("true", f"touch {marker}"), project=root, evidence_dir=root / "ev",
                                   log_dir=root / "log", timeout_s=30, evidence_prefix="r:W1:checks.3", first=["V1"])
            self.assertEqual([row["green"] for row in ok], [True, True])  # V1 green, so the rest ran
            self.assertTrue(marker.exists())


class RedFirstProcedureTests(unittest.TestCase):
    def test_a_procedure_check_without_a_verdict_does_not_hold_the_command_checks_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"]):
                subprocess.run(["git", *args], cwd=tmp, check=True, capture_output=True)
            marker = root / "ran-v3"
            document = doc("true", "true", f"touch {marker}")
            document["acceptance"]["checks"][0] = {"id": "V1", "kind": "acceptance", "procedure": "observe the fix"}
            rows = checks.run_checks(document, project=root, evidence_dir=root / "ev", log_dir=root / "log", timeout_s=30,
                                     evidence_prefix="r:W1:checks.3", first=["V1"])
            self.assertEqual([(row["id"], row["green"], bool(row.get("skipped"))) for row in rows],
                             [("V1", False, False), ("V2", True, False), ("V3", True, False)])
            self.assertTrue(marker.exists())  # V1 stays red (no verdict), yet the command checks ran


def _repo(tmp: str) -> Path:
    for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", *args], cwd=tmp, check=True, capture_output=True)
    return Path(tmp)


class HangAndTreeTests(unittest.TestCase):
    def test_a_silent_check_is_stopped_by_the_silence_ceiling_and_a_talking_one_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _repo(tmp)
            silent_then_talking = "for i in 1 2 3 4 5 6 7; do echo tick; sleep 1; done"
            with mock.patch.object(checks, "POLL_S", 0.2):
                rows = checks.run_checks(doc("sleep 30", silent_then_talking), project=root, evidence_dir=root / "ev",
                                         log_dir=root / "log", timeout_s=0, idle_s=2, evidence_prefix="r:W1:checks.1",
                                         fail_fast=False)
            self.assertEqual([(row["id"], row["exit"]) for row in rows], [("V1", 124), ("V2", 0)])
            self.assertIn("no output for 2 s", (root / "log" / "V1.log").read_text(encoding="utf-8"))
            self.assertLess(rows[0]["seconds"], 10)

    def test_files_a_check_changes_are_reported_and_its_own_evidence_is_not(self):
        """``on_changed`` is what the checks stage turns into the CHECK_CHANGED_TREE beacon."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _repo(tmp)
            seen = []
            checks.run_checks(doc("echo generated > gen.txt", "true"), project=root, evidence_dir=root / "ev",
                              log_dir=root / "log", timeout_s=30, evidence_prefix="r:W1:checks.1",
                              on_changed=seen.append)
            self.assertEqual(seen, [["gen.txt"]])
            quiet = []
            checks.run_checks(doc("true", "true"), project=root, evidence_dir=root / "ev", log_dir=root / "log",
                              timeout_s=30, evidence_prefix="r:W1:checks.2", on_changed=quiet.append)
            self.assertEqual(quiet, [])

    def test_a_check_whose_cwd_leads_outside_the_project_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _repo(tmp)
            document = doc("touch escaped")
            document["acceptance"]["checks"][0]["cwd"] = ".."
            with self.assertRaises(ValueError) as caught:
                checks.run_checks(document, project=root, evidence_dir=root / "ev", log_dir=root / "log", timeout_s=30,
                                  evidence_prefix="r:W1:checks.1")
            self.assertIn("outside the project", str(caught.exception))
            self.assertFalse((root.parent / "escaped").exists())

    def test_python_output_of_a_check_is_unbuffered(self):
        self.assertEqual(checks.check_env(Path("."), environ={})["PYTHONUNBUFFERED"], "1")


if __name__ == "__main__":
    unittest.main()
