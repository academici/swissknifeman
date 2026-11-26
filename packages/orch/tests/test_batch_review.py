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
        items = {ref: {"steps": {"commit": {"status": "done", "result": {"outcome": "committed", "sha": sha}}}} for ref, sha in shas.items()}
        (self.run_dir / "state.json").write_text(json.dumps({"items": items}), encoding="utf-8")

    def git(self, *args) -> str:
        return subprocess.run(["git", *args], cwd=self.project, capture_output=True, text=True, check=True).stdout

    def review(self, *extra) -> subprocess.CompletedProcess:
        fake = ["python3", "-c", "import sys,json; t=sys.stdin.read(); d={'verdict':'GREEN','findings':[], "
                "'residual_risk':'SAW '+str(t.count('diff --git'))}; "
                "print(json.dumps({'type':'result','result':'```json review-findings\\n'+json.dumps(d)+'\\n```'}))"]
        return subprocess.run([sys.executable, str(SCRIPT), "cnd-test", "--project", str(self.project), "--argv-json",
                               json.dumps(fake), *extra], capture_output=True, text=True, check=False)

    def test_one_review_reads_production_and_tests_of_every_commit_of_the_run(self):
        done = self.review()
        self.assertEqual(done.returncode, 0, done.stderr)
        text = (self.run_dir / "batch-review.md").read_text(encoding="utf-8")
        self.assertIn("json review-findings", text)
        self.assertIn("SAW 4", text)  # both implementation and tests of W1 and W2
        measured = json.loads((self.run_dir / "batch-review.json").read_text(encoding="utf-8"))
        self.assertEqual((measured["returncode"], measured["pieces"]), (0, ["W1", "W2"]))
        self.assertGreaterEqual(measured["seconds"], 0)
        self.assertIn('"type": "result"', (self.run_dir / "streams" / "batch-review.jsonl").read_text(encoding="utf-8"))
        self.assertIn("BATCH_REVIEW:", done.stderr)

    def major_review(self) -> subprocess.CompletedProcess:
        doc = {"verdict": "ATTENTION", "findings": [{"id": "F1", "severity": "Major", "confidence": "high",
                                                    "location": "lib/W1.py:1", "failure_scenario": "empty input crashes",
                                                    "basis": "correctness"}]}
        reply = json.dumps({"type": "result", "result": "```json review-findings\n" + json.dumps(doc) + "\n```"})
        fake = ["python3", "-c", f"import sys; sys.stdin.read(); print({reply!r})"]
        return subprocess.run([sys.executable, str(SCRIPT), "cnd-test", "--project", str(self.project), "--argv-json",
                               json.dumps(fake)], capture_output=True, text=True, check=False)

    def test_a_major_finding_writes_a_followup_input_that_names_the_group_and_its_last_session(self):
        fingerprint = {"provider": "claude-code", "project": "/p", "worktree": "/p", "role": "executor", "item": "W2",
                       "attempt_id": "att-2", "instructions_digest": "sha256:" + "1" * 64, "authority_digest": "",
                       "isolation_home": "", "base": "abc"}
        state = json.loads((self.run_dir / "state.json").read_text(encoding="utf-8"))
        state["executor_sessions"] = {"W2": {"session": "s2", "provider": "claude-code", "fingerprint": fingerprint}}
        (self.run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        done = self.major_review()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("BATCH_REVIEW_FOLLOWUP:", done.stderr)
        from orch import contracts
        from orch.conductor.infrastructure import sessions
        doc = json.loads((self.run_dir / "batch-review.followup.json").read_text(encoding="utf-8"))
        self.assertEqual([issue for issue in contracts.validate(doc, "execution-input") if issue.level == "error"], [])
        ref = doc["provenance"]["session_ref"]
        self.assertEqual((ref["run"], ref["item"], ref["items"], ref["session"], ref["provider"]),
                         ("cnd-test", "W2", ["W1", "W2"], "s2", "claude-code"))
        self.assertEqual(ref["fingerprint_digest"], sessions.identity_digest(fingerprint))

    def test_a_followup_without_a_kept_session_still_names_the_group(self):
        done = self.major_review()
        self.assertEqual(done.returncode, 0, done.stderr)
        ref = json.loads((self.run_dir / "batch-review.followup.json").read_text(encoding="utf-8"))["provenance"]["session_ref"]
        self.assertEqual(ref, {"run": "cnd-test", "item": "W2", "items": ["W1", "W2"]})

    def test_a_green_review_writes_no_followup(self):
        self.assertEqual(self.review().returncode, 0)
        self.assertFalse((self.run_dir / "batch-review.followup.json").exists())

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


class BatchJSONTests(unittest.TestCase):
    def test_markdown_is_malformed_and_closed_json_supplies_counts(self):
        from orch.conductor.review_batch import verdict
        self.assertEqual(verdict("## Findings\nnone")["format"], "malformed")
        finding = {"id": "F1", "severity": "Major", "confidence": "high", "location": "a.py:1",
                   "failure_scenario": "empty input crashes", "basis": "correctness"}
        def reply(doc):
            return "```json review-findings\n" + json.dumps(doc) + "\n```"
        doc = {"verdict": "ATTENTION", "findings": [finding]}
        self.assertEqual(verdict(reply(doc))["counts"], {"Blocker": 0, "Major": 1, "Minor": 0})
        finding["unexpected"] = "no"
        self.assertEqual(verdict(reply(doc))["format"], "malformed")
        self.assertEqual(verdict("```json review-findings\n{}\n```")["format"], "malformed")


if __name__ == "__main__":
    unittest.main()
