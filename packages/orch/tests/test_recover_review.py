import json
import subprocess
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, mock

from orch.conductor.application import recover_review
from orch.conductor.domain.stop import Stop
from orch.conductor.stages.review import revision_candidate


class RecoverReviewTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()
        git("init", "-q")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "fixture")
        (self.root / "base").write_text("base\n")
        git("add", "base")
        git("commit", "-qm", "base")
        self.base = git("rev-parse", "HEAD")
        (self.root / "candidate").write_text("candidate\n")
        git("add", "candidate")
        git("commit", "-qm", "candidate")
        self.head = git("rev-parse", "HEAD")
        candidate = revision_candidate(self.root, self.base, self.head)
        self.run_dir = self.root / ".runtime"
        (self.run_dir / "P1.1").mkdir(parents=True)
        artifacts = self.root / ".artifacts"
        artifacts.mkdir()
        (artifacts / "review-receipt.json").write_text(json.dumps({"run": "run", "item": "P1.1", "round": 1,
            "subject": "PLAN1.P1.1", "reviewer": {"provider": "antigravity", "model": "gemini-4-argon-high", "effort": "high"},
            "attempt_id": "att-old-run-P1.1", "candidate": candidate}))
        (artifacts / "review-verdict.json").write_text("original")
        self.piece = {"outcome": "done", "orch_run": "old-run", "corrections_used": 1, "steps": {
            "review.1": {"status": "done", "result": {"repaired_from_text": True, "base": self.base,
                         "candidate": candidate, "outside": {}, "findings": {"findings": []}}},
            "brief": {"result": {"artifacts_dir": ".artifacts"}},
            "commit": {"result": {"sha": self.head}}, "checks.2": {"result": []}}}
        self.state = {"status": "finished", "items": {"P1.1": self.piece}}
        self.store = mock.Mock(directory=self.run_dir)
        self.store.ownership.return_value = nullcontext()
        self.store.load.return_value = ({"plan": "PLAN1"}, self.state)
        self.options = {"scenario": "full", "options": {"reviewer": "antigravity/gemini-4-argon-high/high",
                        "fallback_routes": [], "skills": [], "limits": {"review_rounds": 2}}, "sources": {"reviewer": "item:P1.1"}}
        self.input_doc = {"provenance": {"kind": "plan", "plan_dir": "@plan"}}
        self.conductor = mock.Mock(project=self.root, settings=object())
        self.conductor._selected.return_value = {"provider": "antigravity", "model": "gemini-4-argon-high", "effort": "high"}
        self.conductor._reviewer_selector.return_value = (self.conductor._selected.return_value, None, "item:P1.1")
        self.conductor._admit.return_value = None
        def open_artifacts(item, _brief):
            item.artifacts = artifacts
        self.conductor._open_artifacts.side_effect = open_artifacts
        def review(item, number, _rows):
            self.assertEqual(number, 2)
            self.assertEqual(item.input_doc["provenance"]["base"], self.base)
            self.assertEqual(item.input_doc["provenance"]["head"], self.head)
            self.assertEqual(item.input_doc["provenance"]["kind"], "review")
            self.assertEqual(item.options["skills"], {})
            self.assertEqual(item.recovery_candidate["paths"], candidate["paths"])
            item.state["steps"]["review.2"] = {"status": "done", "result": {"session": "new-session",
                "candidate": candidate, "findings": {"verdict": "GREEN", "findings": [], "questions": []}}}
            return {"verdict": "GREEN", "findings": [], "questions": []}
        self.conductor._review.side_effect = review
        self.patches = [mock.patch.object(recover_review, "RunStore", return_value=self.store),
                        mock.patch.object(recover_review.records, "read", side_effect=lambda p, kind: self.options if kind == "item-options" else {"reviewer": {}}),
                        mock.patch.object(recover_review, "read_json", side_effect=lambda p: json.loads(p.read_text()) if p.exists() else self.input_doc),
                        mock.patch.object(recover_review.policies, "load", return_value={}),
                        mock.patch.object(recover_review.contract, "problems", return_value=[]),
                        mock.patch.object(recover_review.review_stage, "receipt_file")]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_adds_second_round_without_resetting_history_or_counters(self):
        old = self.piece["steps"]["review.1"]
        answer = recover_review.recover(self.conductor, "run", "P1.1", self.head)
        self.assertEqual(answer["attempt_id"], "att-old-run-P1.1")
        self.assertEqual(answer["round"], 2)
        self.assertIs(self.piece["steps"]["review.1"], old)
        self.assertEqual(self.piece["corrections_used"], 1)
        self.assertEqual(self.piece["review_rounds_used"], 2)
        self.assertTrue((self.run_dir / "P1.1/review-recovery/review-receipt.json").exists())
        self.conductor._review.assert_called_once()
        again = recover_review.recover(self.conductor, "run", "P1.1", self.head)
        self.assertEqual(again["round"], 2)
        self.conductor._review.assert_called_once()

    def test_refuses_changed_commit_or_spent_round_without_model_call(self):
        with self.assertRaises(Stop):
            recover_review.recover(self.conductor, "run", "P1.1", "wrong")
        self.piece["review_rounds_used"] = 2
        with self.assertRaises(Stop):
            recover_review.recover(self.conductor, "run", "P1.1", self.head)
        self.conductor._review.assert_not_called()

    def test_accepts_only_plan_metadata_beyond_original_candidate(self):
        self.input_doc["provenance"]["plan_dir"] = "plans/demo"
        (self.root / "plans/demo").mkdir(parents=True)
        (self.root / "plans/demo/state.json").write_text("{}\n")
        subprocess.run(["git", "add", "plans/demo/state.json"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "plan metadata"], cwd=self.root, check=True)
        self.head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()
        self.piece["steps"]["commit"]["result"]["sha"] = self.head
        self.assertEqual(recover_review.recover(self.conductor, "run", "P1.1", self.head)["round"], 2)

    def test_refuses_unrelated_product_path_in_commit(self):
        (self.root / "unrelated").write_text("not reviewed\n")
        subprocess.run(["git", "add", "unrelated"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "extra product"], cwd=self.root, check=True)
        self.head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()
        self.piece["steps"]["commit"]["result"]["sha"] = self.head
        with self.assertRaises(Stop):
            recover_review.recover(self.conductor, "run", "P1.1", self.head)
        self.conductor._review.assert_not_called()
