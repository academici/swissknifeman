"""Internal documentation."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from aicore.util.partners import partner_command

PKG = Path(__file__).resolve().parents[1]
RG_SRC = PKG / "configs" / "claude-code" / "hooks" / "review-gate"


def _run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _init_repo(root):
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.email", "review-gate-test@example.invalid"], root)
    _run(["git", "config", "user.name", "review-gate-test"], root)
    (root / "README.md").write_text("base\n")
    _run(["git", "add", "."], root)
    _run(["git", "commit", "-q", "-m", "base"], root)


def _hookdir(tmp, state_dir, mode="strict"):
    """Internal documentation."""
    dst = tmp / "hookdir"
    shutil.copytree(RG_SRC, dst)
    (dst / "env.ini").write_text("MODE=strict\n")
    (dst / "config.json").write_text(json.dumps({
        "version": 2,
        "check_command": "$REVIEW_GATE_DIR/checks/run-checks.sh",
        "checks": [{"name": "generated-assets", "mode": mode}],
    }))
    (dst / "review-gate.sh").chmod(0o755)
    for f in (dst / "checks").glob("*.sh"):
        f.chmod(0o755)
    return dst


def _run_hook(hookdir, cwd, state_dir, session, agent):
    payload = {"cwd": str(cwd), "session_id": session, "agent_id": agent, "agent_type": "test"}
    env = dict(os.environ)
    env["REVIEW_GATE_STATE_DIR"] = str(state_dir)
    p = subprocess.run(
        ["bash", str(hookdir / "review-gate.sh")],
        input=json.dumps(payload).encode(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=cwd, env=env, timeout=30,
    )
    return p.returncode, p.stdout.decode(), p.stderr.decode()


def _write_generated_file(repo):
    f = repo / "generated.sh"
    f.write_text("#!/usr/bin/env bash\n# swissknifeman:generated\necho hi\n")
    return f


class FixtureSeedIsolationTests(unittest.TestCase):
    def test_plan_fixture_copies_are_independent_and_the_seed_is_not_mutated(self):
        from tests.plan_fixture import write_plan
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right, tempfile.TemporaryDirectory() as third:
            first, ids = write_plan(left, items=[("todo", ("implementation", "medium"))])
            second, other_ids = write_plan(right, items=[("todo", ("implementation", "medium"))])
            relative = "phases/P1/P1.1.json"
            expected = (second / relative).read_bytes()
            self.assertEqual(ids, other_ids)
            self.assertNotEqual((first / relative).stat().st_ino, (second / relative).stat().st_ino)
            (first / relative).write_text("broken on purpose")
            self.assertEqual((second / relative).read_bytes(), expected)
            clean, _ = write_plan(third, items=[("todo", ("implementation", "medium"))])
            self.assertEqual((clean / relative).read_bytes(), expected)
            self.assertEqual(json.loads(expected)["status"], "todo")



class TestReviewGate(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        _init_repo(self.repo)
        self.state_dir = self.tmp / "state"
        self.hookdir = _hookdir(self.tmp, self.state_dir)

    def tearDown(self):
        self._td.cleanup()

    def test_synthetic_violation_caught_with_file_line(self):
        _write_generated_file(self.repo)
        rc, out, err = _run_hook(self.hookdir, self.repo, self.state_dir, "sess-a", "agent-a")
        self.assertEqual(rc, 2)
        self.assertIn("generated.sh:2", err)

    def test_clean_diff_passes(self):
        rc, out, err = _run_hook(self.hookdir, self.repo, self.state_dir, "sess-b", "agent-b")
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        self.assertEqual(err.strip(), "")

    def test_third_consecutive_strict_downgrades_to_warn(self):
        _write_generated_file(self.repo)
        session, agent = "sess-c", "agent-c"
        rc1, _, err1 = _run_hook(self.hookdir, self.repo, self.state_dir, session, agent)
        rc2, _, err2 = _run_hook(self.hookdir, self.repo, self.state_dir, session, agent)
        rc3, out3, err3 = _run_hook(self.hookdir, self.repo, self.state_dir, session, agent)
        self.assertEqual(rc1, 2)
        self.assertEqual(rc2, 2)
        self.assertEqual(rc3, 0)
        self.assertIn("DOWNGRADE", out3)


def _plan_check_hookdir(tmp):
    dst = tmp / "hookdir"
    shutil.copytree(RG_SRC, dst)
    (dst / "env.ini").write_text("MODE=strict\n")
    (dst / "config.json").write_text(json.dumps({
        "version": 2,
        "check_command": "$REVIEW_GATE_DIR/checks/run-checks.sh",
        "checks": [{"name": "plan-check", "mode": "strict"}],
    }))
    (dst / "review-gate.sh").chmod(0o755)
    for f in (dst / "checks").glob("*.sh"):
        f.chmod(0o755)
    return dst


class TestPlanLintCheck(unittest.TestCase):
    """The plan-check runs `plan.py check` for changed plan dirs that hold a plan.json."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        _init_repo(self.repo)
        self.planner = partner_command("planner")
        if self.planner is None:
            self.skipTest("planner partner not found (set PLANNER_ROOT or PLANNER_PLAN_PY)")
        (self.repo / "plans").mkdir()
        created = subprocess.run(
            [*self.planner, "new", "--codename", "DEMO",
             "--title", "Demo", "--actor", "claude-code/x/high", "--message", "m"],
            cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.plan = next((self.repo / "plans").iterdir())
        self.state_dir = self.tmp / "state"
        self.hookdir = _plan_check_hookdir(self.tmp)

    def test_valid_v3_plan_passes(self):
        rc, _, err = _run_hook(self.hookdir, self.repo, self.state_dir, "s1", "a1")
        self.assertEqual((rc, err.strip()), (0, ""))

    def test_broken_plan_json_is_a_violation(self):
        data = json.loads((self.plan / "plan.json").read_text())
        data["status"] = "not-a-status"
        (self.plan / "plan.json").write_text(json.dumps(data))
        rc, _, err = _run_hook(self.hookdir, self.repo, self.state_dir, "s2", "a2")
        self.assertEqual(rc, 2)
        self.assertIn("plan.py check failed", err)

    def test_changed_plan_dir_without_plan_json_is_skipped(self):
        other = self.repo / "plans" / "OLD"
        other.mkdir()
        (other / "notes.md").write_text("not a v3 plan\n")
        rc, _, err = _run_hook(self.hookdir, self.repo, self.state_dir, "s3", "a3")
        self.assertEqual((rc, err.strip()), (0, ""))

    def test_planner_not_found_skips_the_check_with_a_note(self):
        if shutil.which("planner", path="/usr/bin:/bin"):
            self.skipTest("a planner command is installed in the system path")
        env = {k: v for k, v in os.environ.items() if k not in ("PLANNER_ROOT", "PLANNER_PLAN_PY")}
        env["PATH"] = "/usr/bin:/bin"
        proc = subprocess.run(["bash", str(self.hookdir / "checks" / "plan-check.sh")], cwd=self.repo,
                              env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("plan-check: planner not found (set PLANNER_ROOT)", proc.stderr)


if __name__ == "__main__":
    unittest.main()
