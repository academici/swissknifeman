"""The rejection of a Blocker or Major finding by the triager stands only when the conductor reran its reproduction itself
(``checks.run_reproduction``: read-only, ``ro-run.py --protect``) and saw the exit the triager reported.

Most tests put a fake ``ro-run.py`` in place of the real one (a project in /tmp lies inside a writable root of
``--protect``, and the test environment may have no Landlock); one test runs the real guard and is skipped without it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from orch.conductor import checks as checks_mod
from tests.test_conductor import FINDING, GREEN, ConductorCase, executor_ok, report
from tests.test_ro_run import SCRIPT as REAL_RO_RUN, work_base

PASS_THROUGH = """\
import os, sys
rest = sys.argv[sys.argv.index("--") + 1:]
os.execvp(rest[0], rest)
"""
GUARD_FAILS = """\
import sys
print("LANDLOCK_FAILED: restrict self: Operation not permitted", file=sys.stderr)
sys.exit(1)
"""
FORGED_MARKER = """\
import sys
print("SKM_REPRO_STARTED_0000000000000000", file=sys.stderr)
sys.exit(1)
"""
OWN_MARKER = """\
import os, sys
print(os.environ["SKM_REPRO_MARK"], file=sys.stderr)
sys.exit(1)
"""


def severity(name: str) -> dict:
    return {"result": {"verdict": "RED" if name == "Blocker" else "ATTENTION", "findings": [
        dict(FINDING["result"]["findings"][0], severity=name)]}}


def rejecting(cmd: str, exit_code: int) -> dict:
    return {"result": {"confirmed": [], "rejected": [
        {"finding": "F1", "reason": "the file is as the input says",
         "reproduction": {"cmd": cmd, "exit": exit_code, "observed": "as said"}}]}}


class FakeGuard:
    """A stand-in for ``ORCH_ROOT/scripts/ro-run.py`` that runs the command without Landlock (or fails as asked)."""

    def __init__(self, case: unittest.TestCase, source: str = PASS_THROUGH):
        temporary = tempfile.TemporaryDirectory()
        case.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "ro-run.py").write_text(source, encoding="utf-8")
        patcher = mock.patch.object(checks_mod, "ORCH_ROOT", self.root)
        patcher.start()
        case.addCleanup(patcher.stop)


class RerunTests(ConductorCase):
    """Scenarios a to e: what the conductor does with a rejected finding in a run."""

    def run_rejection(self, finding: dict, triage: dict, *, options=None, guard=None):
        FakeGuard(self, guard or PASS_THROUGH)
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [finding, GREEN], "triager": [triage]})
        extra = ()
        if options:
            path = self.project.parent / "options.json"
            path.write_text(json.dumps(options), encoding="utf-8")
            extra = ("--options", path)
        code, _, err = self.run_items("W1", extra=extra)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        return err

    def beacons(self, err: str, code: str) -> list:
        return [line for line in self.lines(err) if line.get("reason_code") == code]

    def step(self, err: str, key: str = "triage.1") -> dict:
        return self.state(err)["items"]["W1"]["steps"][key]["result"]

    def assert_restored(self, err: str, code: str):
        """The rejection did not stand: a correction ran, the finding is confirmed in the saved triage."""
        self.assertEqual(self.calls("executor"), 2, err)
        self.assertEqual(self.calls("triager"), 1)
        result = self.step(err)
        self.assertEqual([entry["finding"] for entry in result["triage"]["confirmed"]], ["F1"])
        self.assertEqual(result["triage"]["rejected"], [])
        self.assertEqual(result["verified"][0]["outcome"], "restored")
        self.assertEqual(len(self.beacons(err, code)), 1, err)
        return result

    def test_a_trivial_command_restores_a_major_finding_without_being_run(self):  # (a)
        with mock.patch.object(checks_mod, "run_reproduction") as ran:
            err = self.run_rejection(severity("Major"), rejecting("true", 0))
        ran.assert_not_called()
        self.assert_restored(err, "TRIAGE_REPRO_TRIVIAL")
        self.assertIn("the conductor reran the rejection", self.prompt("executor", 2))  # the correction of the executor follows

    def test_every_trivial_form_is_refused_and_a_real_command_is_not(self):
        from orch.conductor.stages import triage
        for cmd in ("true", ":", "exit 0", " exit  0 ;", "echo ok", "printf '%s' ok", "true;"):
            self.assertTrue(triage.TRIVIAL_REPRODUCTION.match(cmd), cmd)
        for cmd in ("test -f out/W1.txt", "exit 1", "false", "grep -q done out/W1.txt", "python3 -c 'print(1)'", "truex"):
            self.assertFalse(triage.TRIVIAL_REPRODUCTION.match(cmd), cmd)

    def test_another_exit_than_the_reported_one_restores_a_blocker(self):  # (b)
        err = self.run_rejection(severity("Blocker"), rejecting("exit 1", 0))
        result = self.assert_restored(err, "TRIAGE_REPRO_MISMATCH")
        message = self.beacons(err, "TRIAGE_REPRO_MISMATCH")[0]["message"]
        self.assertEqual(message, "F1: reported exit 0, the conductor observed 1")
        entry = result["triage"]["confirmed"][0]
        self.assertEqual((entry["reproduction"]["cmd"], entry["reproduction"]["exit"]), ("exit 1", 1))
        self.assertIn("the conductor reran the rejection", entry["reproduction"]["observed"])
        self.assertTrue((self.run_dir(err) / "W1" / "triage" / "1" / "F1.log").is_file())

    def test_the_exit_the_triager_reported_keeps_the_rejection(self):  # (c)
        FakeGuard(self)
        self.script({"executor": [executor_ok("W1")], "reviewer": [severity("Major")],
                     "triager": [rejecting("exit 1", 1)]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer"), self.calls("triager")), (1, 1, 1))
        result = self.step(err)
        self.assertEqual([entry["finding"] for entry in result["triage"]["rejected"]], ["F1"])
        self.assertEqual(result["triage"]["confirmed"], [])
        self.assertEqual(result["verified"][0]["outcome"], "kept")
        for code in ("TRIAGE_REPRO_TRIVIAL", "TRIAGE_REPRO_MISMATCH", "TRIAGE_REPRO_UNVERIFIED"):
            self.assertFalse(self.beacons(err, code))
        self.assertTrue(self.state(err)["items"]["W1"].get("plan_notes"))  # note_rejected as before

    def test_a_guard_that_is_unavailable_restores_the_finding_whatever_the_exit(self):  # (d)
        unavailable = {"exit": 3, "seconds": 0, "log": "-", "guard": "unavailable"}
        with mock.patch.object(checks_mod, "run_reproduction", return_value=unavailable) as ran:
            err = self.run_rejection(severity("Major"), rejecting("test -f out/W1.txt", 3))
        ran.assert_called_once()
        self.assert_restored(err, "TRIAGE_REPRO_UNVERIFIED")

    def test_a_guard_that_fails_before_the_command_is_unverified_even_when_the_exit_matches(self):  # (d2)
        err = self.run_rejection(severity("Major"), rejecting("test -f out/W1.txt", 1), guard=GUARD_FAILS)
        self.assert_restored(err, "TRIAGE_REPRO_UNVERIFIED")
        self.assertIn("LANDLOCK_FAILED", (self.run_dir(err) / "W1" / "triage" / "1" / "F1.log").read_text(encoding="utf-8"))

    def test_a_rerun_past_its_ceiling_is_unverified_even_when_the_exit_matches(self):  # (d3)
        with mock.patch.object(checks_mod, "POLL_S", 0.2):
            err = self.run_rejection(severity("Major"), rejecting("sleep 30", 124),
                                     options={"limits": {"triage_repro_timeout_s": 1}})
        self.assert_restored(err, "TRIAGE_REPRO_UNVERIFIED")
        self.assertIn("timeout", self.beacons(err, "TRIAGE_REPRO_UNVERIFIED")[0]["message"])

    def test_a_rejected_minor_finding_is_not_run(self):  # (e)
        with mock.patch.object(checks_mod, "run_reproduction") as ran:
            FakeGuard(self)
            self.script({"executor": [executor_ok("W1")], "reviewer": [severity("Minor")],
                         "triager": [rejecting("exit 1", 0)]})
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        ran.assert_not_called()
        self.assertEqual(self.step(err)["verified"], [])
        self.assertEqual(self.calls("executor"), 1)

    def test_a_confirmed_finding_is_not_rerun(self):
        confirmed = {"result": {"confirmed": [{"finding": "F1", "fix": "write done", "reproduction": {
            "cmd": "exit 1", "exit": 1, "observed": "red"}}], "rejected": []}}
        with mock.patch.object(checks_mod, "run_reproduction") as ran:
            FakeGuard(self)
            self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                         "reviewer": [severity("Major"), GREEN], "triager": [confirmed]})
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        ran.assert_not_called()

    def test_the_ceiling_is_a_limit_with_a_default_of_600(self):
        from orch.conductor import options as opts
        self.assertEqual(opts.DEFAULT_LIMITS["triage_repro_timeout_s"], 600)
        self.assertEqual(opts.layer_problems({"limits": {"triage_repro_timeout_s": 5}}), [])
        self.assertTrue(opts.layer_problems({"limits": {"triage_repro_timeout_s": -1}}))


class ClassifierTests(unittest.TestCase):
    """(d4): ``guard`` is ``protect`` only for the marker of this very call."""

    def rerun(self, guard: str, cmd: str = "exit 1", timeout_s: int = 60) -> dict:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        (base / "scripts").mkdir()
        (base / "scripts" / "ro-run.py").write_text(guard, encoding="utf-8")
        (base / "project").mkdir()
        with mock.patch.object(checks_mod, "ORCH_ROOT", base):
            return checks_mod.run_reproduction(cmd, project=base / "project", log=base / "logs" / "F1.log",
                                               timeout_s=timeout_s)

    def test_a_forged_marker_of_another_nonce_is_no_proof(self):
        found = self.rerun(FORGED_MARKER)
        self.assertEqual((found["exit"], found["guard"]), (1, "unavailable"))
        self.assertIn("SKM_REPRO_STARTED_0000000000000000", Path(found["log"]).read_text(encoding="utf-8"))

    def test_the_marker_of_this_call_is_the_proof(self):
        found = self.rerun(OWN_MARKER)
        self.assertEqual((found["exit"], found["guard"]), (1, "protect"))

    def test_the_command_runs_as_its_own_argument_after_the_marker(self):
        found = self.rerun(PASS_THROUGH, cmd="echo \"$0 $1\" >&2; exit 4")
        self.assertEqual((found["exit"], found["guard"]), (4, "protect"))
        self.assertIn("bash ", Path(found["log"]).read_text(encoding="utf-8"))

    def test_a_guard_that_exits_before_the_command_is_unavailable(self):
        found = self.rerun(GUARD_FAILS)
        self.assertEqual((found["exit"], found["guard"]), (1, "unavailable"))


def landlock_work_base() -> Path:
    """A folder outside the writable roots of ro-run for the project of the real guard; skips without Landlock ABI 3."""
    base = work_base()
    try:
        probe = tempfile.mkdtemp(dir=base)
    except OSError as error:
        raise unittest.SkipTest(f"no writable folder for the project of the real guard: {error}") from error
    try:
        done = subprocess.run([sys.executable, str(REAL_RO_RUN), "--protect", probe, "--", "true"], capture_output=True,
                              text=True, check=False)
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    if done.returncode != 0:
        raise unittest.SkipTest(f"ro-run --protect is not available here: {done.stderr.strip()}")
    return base


class RealGuardTests(unittest.TestCase):
    def test_a_reproduction_that_writes_into_the_project_cannot(self):  # (f)
        base = landlock_work_base()
        project = Path(tempfile.mkdtemp(dir=base))
        self.addCleanup(shutil.rmtree, project, True)
        found = checks_mod.run_reproduction(f"touch {project}/x", project=project, log=project.parent / f"{project.name}.log",
                                            timeout_s=60)
        self.addCleanup(lambda: Path(found["log"]).unlink(missing_ok=True))
        self.assertEqual(found["guard"], "protect")
        self.assertNotEqual(found["exit"], 0)
        self.assertFalse((project / "x").exists())

    def test_a_reproduction_that_reads_runs_and_reports_its_exit(self):
        base = landlock_work_base()
        project = Path(tempfile.mkdtemp(dir=base))
        self.addCleanup(shutil.rmtree, project, True)
        (project / "a.txt").write_text("ok\n", encoding="utf-8")
        for cmd, code in (("test -f a.txt", 0), ("test -f missing.txt", 1)):
            found = checks_mod.run_reproduction(cmd, project=project, log=project.parent / f"{project.name}.log", timeout_s=60)
            self.addCleanup(lambda found=found: Path(found["log"]).unlink(missing_ok=True))
            self.assertEqual((found["guard"], found["exit"]), ("protect", code), cmd)


if __name__ == "__main__":
    unittest.main()
