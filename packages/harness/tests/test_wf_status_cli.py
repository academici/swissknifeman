"""Internal documentation."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.wf_status import project_slug  # noqa: E402

PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # packages/harness
HUB_ROOT = PACKAGE_ROOT.parents[1]
HARNESS_BIN = PACKAGE_ROOT / "bin" / "harness"
SWISSKNIFEMAN_BIN = HUB_ROOT / "bin" / "swissknifeman"
FIXTURE_DIR = PACKAGE_ROOT / "tests" / "fixtures" / "wf_run"
RUN_ID = "wf_run"
FAKE_PROJECT = "/tmp/fake-wf-status-project"


def _build_config_tree(config_dir, project=FAKE_PROJECT, session="session-1"):
    """Internal documentation."""
    slug = project_slug(project)
    session_dir = Path(config_dir) / "projects" / slug / session
    run_dir = session_dir / "subagents" / "workflows" / RUN_ID
    scripts_dir = session_dir / "workflows" / "scripts"
    run_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy(FIXTURE_DIR / "journal.jsonl", run_dir / "journal.jsonl")
    for meta in FIXTURE_DIR.glob("agent-*.meta.json"):
        shutil.copy(meta, run_dir / meta.name)
    for script in (FIXTURE_DIR / "scripts").glob("*.js"):
        shutil.copy(script, scripts_dir / script.name)
    return run_dir


def _run(cmd, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


class HarnessWfStatusCliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.config_dir = self.tmp / "cc-config"
        _build_config_tree(self.config_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_status_run_prints_expected_report(self):
        proc = _run([str(HARNESS_BIN), "wf", "status", "--run", RUN_ID],
                    {"CLAUDE_CONFIG_DIR": str(self.config_dir)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"run: {RUN_ID}", proc.stdout)
        self.assertIn("name: p1-4-auth-security-review", proc.stdout)
        self.assertIn("Review", proc.stdout)
        self.assertIn("Verify", proc.stdout)
        self.assertIn("started=2 done=1 inflight=1", proc.stdout)
        self.assertNotIn("Traceback", proc.stdout)

    def test_status_run_json_is_valid(self):
        proc = _run([str(HARNESS_BIN), "wf", "status", "--run", RUN_ID, "--json"],
                    {"CLAUDE_CONFIG_DIR": str(self.config_dir)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["run_id"], RUN_ID)
        self.assertEqual(data["started"], 2)
        self.assertEqual(data["done"], 1)
        self.assertFalse(data["degraded"])

    def test_status_project_filter_finds_run(self):
        proc = _run(
            [str(HARNESS_BIN), "wf", "status", "--project", FAKE_PROJECT, "--json"],
            {"CLAUDE_CONFIG_DIR": str(self.config_dir)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["run_id"], RUN_ID)

    def test_status_no_runs_found_is_honest_not_error(self):
        empty_cfg = self.tmp / "empty-cc-config"
        proc = _run([str(HARNESS_BIN), "wf", "status"], {"CLAUDE_CONFIG_DIR": str(empty_cfg)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("runs not found", proc.stdout)
        self.assertNotIn("Traceback", proc.stdout)

    @unittest.skipUnless(SWISSKNIFEMAN_BIN.is_file(), "the hub launcher is not around this module")
    def test_swissknifeman_wf_facade_reaches_harness(self):
        proc = _run(
            [str(SWISSKNIFEMAN_BIN), "wf", "status", "--run", RUN_ID],
            {"CLAUDE_CONFIG_DIR": str(self.config_dir)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"run: {RUN_ID}", proc.stdout)

    @unittest.skipUnless(SWISSKNIFEMAN_BIN.is_file(), "the hub launcher is not around this module")
    def test_swissknifeman_help_mentions_wf(self):
        proc = _run([str(SWISSKNIFEMAN_BIN), "--help"], {})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("wf", proc.stdout)

    @unittest.skipUnless(SWISSKNIFEMAN_BIN.is_file(), "the hub launcher is not around this module")
    def test_swissknifeman_env_doctor_still_works(self):

        proc = _run([str(SWISSKNIFEMAN_BIN), "env", "doctor"], {})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("harness doctor:", proc.stdout)


if __name__ == "__main__":
    unittest.main()
