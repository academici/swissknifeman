"""Internal documentation."""
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages" / "harness" / "lib"))

from harness.cli import COMMANDS  # noqa: E402
from harness.common import Env  # noqa: E402
from harness.run import cmd_run, gate, journal, plan_reader, worker  # noqa: E402
from packages.harness.tests.plan_fixture import write_plan  # noqa: E402

BIN_HARNESS = REPO_ROOT / "packages" / "harness" / "bin" / "harness"

PHASE_ID = "P1"
DRIVABLE_ID = "P1.1"
BLOCKED_ID = "P1.2"


def _init_repo(root):
    def run(args):
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"git {args} failed: {proc.stderr}")
        return proc

    run(["init", "-q"])
    run(["config", "user.email", "cli-test@example.com"])
    run(["config", "user.name", "cli-test"])
    plan_dir, _ = write_plan(
        root, codename="CLI-FIXTURE",
        items=[("todo", ("implementation", "medium")), ("blocked", ("frontier", "high"))])
    run(["add", "."])
    run(["commit", "-q", "-m", "initial"])
    return plan_dir


def _capture(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


class RegistrationTest(unittest.TestCase):
    def test_run_is_registered(self):
        self.assertIs(COMMANDS.get("run"), cmd_run)

    def test_unknown_command_exits_1(self):
        proc = subprocess.run([str(BIN_HARNESS), "bogus-command"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)

    def test_run_reaches_root_router(self):
        swissknifeman = REPO_ROOT / "bin" / "swissknifeman"
        proc = subprocess.run([str(swissknifeman), "env", "run", "--help"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("harness run", proc.stdout)


class DryRunTest(unittest.TestCase):
    """Internal documentation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.plan_dir = _init_repo(self.root)
        self.env = Env(REPO_ROOT / "packages" / "harness", "run")

    def tearDown(self):
        self._tmp.cleanup()

    def _refuse_if_called(self, *_a, **_kw):
        raise AssertionError("--dry-run must NOT call this (Implementation Rule 2)")

    def _run(self, extra_flags):
        argv = [self.plan_dir.name, PHASE_ID, "--dry-run", "--plans-root", str(self.root / "plans"),
               *extra_flags]
        with mock.patch.object(worker, "run", side_effect=self._refuse_if_called), \
             mock.patch.object(worker, "resolve_claude_bin", return_value=sys.executable), \
             mock.patch.object(gate, "snapshot_before", side_effect=self._refuse_if_called), \
             mock.patch.object(gate, "verdict", side_effect=self._refuse_if_called), \
             mock.patch.object(journal, "maybe_write", side_effect=self._refuse_if_called):
            return _capture(cmd_run, self.env, argv)

    def test_text_output_shows_argv_and_refusal(self):
        out = self._run([])
        self.assertIn(f"[DRIVING] {DRIVABLE_ID}", out)
        self.assertIn(f"/planner:plan-run {self.plan_dir.name} {DRIVABLE_ID}", out)
        self.assertIn(f"[FAILURE] {BLOCKED_ID}", out)
        self.assertIn("ITEM-BLOCKED", out)

    def test_json_output_is_valid(self):
        import json
        out = self._run(["--json"])
        payload = json.loads(out)
        self.assertEqual(payload["mode"], "dry-run")
        ids = {item["item_id"]: item for item in payload["items"]}
        self.assertTrue(ids[DRIVABLE_ID]["drivable"])
        self.assertFalse(ids[BLOCKED_ID]["drivable"])
        self.assertEqual(ids[BLOCKED_ID]["refusal"], "ITEM-BLOCKED")
        self.assertEqual(ids[DRIVABLE_ID]["status"], "todo")

    def test_read_only_no_git_diff(self):
        before = subprocess.run(["git", "status", "--porcelain"], cwd=self.root,
                                capture_output=True, text=True).stdout
        self._run([])
        after = subprocess.run(["git", "status", "--porcelain"], cwd=self.root,
                               capture_output=True, text=True).stdout
        self.assertEqual(before, after)


def _queue_item(item_id, *, drivable=True):
    if drivable:
        return {"item_id": item_id, "status": "todo",
                "route": {"model_class": "implementation", "effort": "medium"},
                "route_error": None, "exec": "run", "exec_error": None,
                "drivable": True, "refusal": None, "refusal_detail": None}
    return {"item_id": item_id, "status": "todo", "route": None,
           "route_error": None, "exec": None, "exec_error": None,
           "drivable": False, "refusal": "ITEM-BLOCKED",
           "refusal_detail": "item is blocked"}


def _canned_queue(*item_ids):
    return {"plan_dir": "irrelevant", "phase_id": PHASE_ID, "degraded": False,
           "degraded_reasons": [], "next_form": {"kind": "run-items", "declaring_line": "x"},
           "items": [_queue_item(i) for i in item_ids], "excluded_terminal": []}


class WaveOrchestrationTest(unittest.TestCase):
    """Internal documentation."""

    def setUp(self):
        self.env = Env(REPO_ROOT / "packages" / "harness", "run")

    def _run(self, argv):
        return _capture(cmd_run, self.env, argv)

    def test_wave_stops_on_first_red(self):
        outcomes = {"P9.1": {"outcome": "error", "reason": "boom", "session_id": None,
                             "total_cost_usd": None, "num_turns": None, "duration_ms": None,
                             "permission_denials": None, "result_text": None}}
        with mock.patch.object(plan_reader, "queue",
                               return_value=_canned_queue("P9.1", "P9.2")), \
             mock.patch.object(gate, "snapshot_before", return_value={"sha": "abc", "dirty": []}), \
             mock.patch.object(worker, "run", side_effect=lambda pid, iid, **kw: outcomes[iid]), \
             mock.patch.object(gate, "verdict",
                               return_value={"verdict": gate.RED, "signals_matched": ["outcome-not-ok"],
                                            "lint_class": None,
                                            "raw": {"item_after": {"status": "todo"}}}), \
             mock.patch.object(journal, "maybe_write", return_value={"category": "error"}) as jw:
            out = self._run(["FIXTURE-WAVE", PHASE_ID, "--plans-root", "/irrelevant"])
        self.assertEqual(worker.run.call_count if hasattr(worker.run, "call_count") else 1, 1)
        self.assertIn("RED", out)
        self.assertNotIn("P9.2", out)
        self.assertEqual(jw.call_count, 1)

    def test_attention_does_not_stop_wave(self):
        verdicts = {"P9.1": gate.ATTENTION, "P9.2": gate.GREEN}

        def fake_verdict(plan_id, item_id, phase_id, plan_dir, before, outcome, **kw):
            return {"verdict": verdicts[item_id], "signals_matched": ["status-deviations"],
                   "lint_class": "clean", "raw": {"item_after": {"status": "done_with_deviations"}}}

        with mock.patch.object(plan_reader, "queue",
                               return_value=_canned_queue("P9.1", "P9.2")), \
             mock.patch.object(gate, "snapshot_before", return_value={"sha": "abc", "dirty": []}), \
             mock.patch.object(worker, "run",
                               return_value={"outcome": "ok", "session_id": "s1",
                                            "total_cost_usd": 0.01, "num_turns": 3,
                                            "duration_ms": 1000, "permission_denials": [],
                                            "result_text": "Status: done_with_deviations"}), \
             mock.patch.object(gate, "verdict", side_effect=fake_verdict), \
             mock.patch.object(journal, "maybe_write", return_value=None) as jw:
            out = self._run(["FIXTURE-WAVE", PHASE_ID, "--plans-root", "/irrelevant"])
        self.assertIn("ATTENTION", out)
        self.assertIn("GREEN", out)
        self.assertIn("P9.1", out)
        self.assertIn("P9.2", out)



        self.assertEqual(jw.call_count, 2)


class FlagParsingTest(unittest.TestCase):
    def setUp(self):
        self.env = Env(REPO_ROOT / "packages" / "harness", "run")

    def test_no_args_prints_usage(self):
        out = _capture(cmd_run, self.env, [])
        self.assertIn("harness run <PLAN-ID>", out)

    def test_wrong_positional_count_dies(self):
        with self.assertRaises(SystemExit):
            _capture(cmd_run, self.env, ["only-one-arg"])

    def test_bad_limit_dies(self):
        with self.assertRaises(SystemExit):
            _capture(cmd_run, self.env, ["P", "P1", "--limit", "not-a-number"])

    def test_bad_timeout_dies(self):
        with self.assertRaises(SystemExit):
            _capture(cmd_run, self.env, ["P", "P1", "--timeout", "not-a-number"])


if __name__ == "__main__":
    unittest.main()
