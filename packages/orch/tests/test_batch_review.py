"""scripts/batch-review.py: one review of the commits of a whole run, the reply kept in the run folder."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "batch-review.py"


class BatchReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        self.git("init", "-q", "-b", "main")
        for key, value in (("user.name", "T"), ("user.email", "t@example.invalid"), ("commit.gpgsign", "false")):
            self.git("config", key, value)
        (self.project / "lib").mkdir()
        (self.project / "lib" / "a.py").write_text("A = 1\n", encoding="utf-8")
        (self.project / "tests").mkdir()
        (self.project / "tests" / "test_a.py").write_text("T = 1\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        shas = {}
        for ref in ("W1", "W2"):
            (self.project / "lib" / f"{ref}.py").write_text(f"VALUE = '{ref}'\n", encoding="utf-8")
            (self.project / "tests" / f"test_{ref}.py").write_text("pass\n", encoding="utf-8")
            self.git("add", "-A")
            self.git("commit", "-q", "-m", ref)
            shas[ref] = self.git("rev-parse", "HEAD").strip()
        self.run_dir = self.project / ".swissknifeman" / "state" / "orch" / "conductor" / "cnd-test"
        self.run_dir.mkdir(parents=True)
        items = {ref: {"steps": {"commit": {"result": {"outcome": "committed", "sha": sha}}}} for ref, sha in shas.items()}
        (self.run_dir / "state.json").write_text(json.dumps({"items": items}), encoding="utf-8")

    def git(self, *args) -> str:
        return subprocess.run(["git", *args], cwd=self.project, capture_output=True, text=True, check=True).stdout

    def review(self, *extra) -> subprocess.CompletedProcess:
        fake = ["python3", "-c", "import sys,json; t=sys.stdin.read(); print(json.dumps({'type':'result','result':'## Findings\\nnone\\nSAW '+str(t.count('diff --git'))}))"]
        return subprocess.run([sys.executable, str(SCRIPT), "cnd-test", "--project", str(self.project), "--argv-json",
                               json.dumps(fake), *extra], capture_output=True, text=True, check=False)

    def test_one_review_reads_the_production_diff_of_every_commit_of_the_run(self):
        done = self.review()
        self.assertEqual(done.returncode, 0, done.stderr)
        text = (self.run_dir / "batch-review.md").read_text(encoding="utf-8")
        self.assertIn("## Findings", text)
        self.assertIn("SAW 2", text)  # lib/W1.py and lib/W2.py; the tests are left out

    def test_a_run_without_commits_is_refused(self):
        (self.run_dir / "state.json").write_text(json.dumps({"items": {}}), encoding="utf-8")
        done = self.review()
        self.assertEqual(done.returncode, 1)
        self.assertIn("BATCH_REVIEW_EMPTY", done.stderr)

    def test_dry_run_names_the_pieces_and_the_command_and_runs_nothing(self):
        done = self.review("--dry-run")
        info = json.loads(done.stdout)
        self.assertEqual(info["pieces"], ["W1", "W2"])
        self.assertFalse((self.run_dir / "batch-review.md").exists())


if __name__ == "__main__":
    unittest.main()
