from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from orch.conductor.application import restore_reviewer
from orch.conductor.domain.stop import Stop


class RestoreReviewerTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.folder = self.project / "run"
        self.folder.mkdir()
        (self.folder / "P1.1").mkdir()
        (self.project / "evidence").mkdir()
        self.state = {"status": "stopped", "items": {"P1.1": {
            "route_overrides": {"reviewer": {"provider": "antigravity", "model_class": "frontier"}},
            "steps": {"checks.2": {"verdict": "green", "result": [{"green": True, "evidence": "evidence/V1.json"}]},
                      "review.1": {"status": "started"}}, "corrections_used": 1}}}
        self.store = mock.Mock(directory=self.folder)
        self.store.ownership.return_value = nullcontext()
        self.store.load.return_value = ({}, self.state)
        self.options = {"options": {"reviewer": "antigravity/gemini-4-argon-high/high", "fallback_routes": []},
                        "sources": {"reviewer": "item:P1.1"}}
        self.evidence = {"exit": 0, "candidate": {"head": "base", "dirty_digest": "digest"}}
        self.patches = [mock.patch.object(restore_reviewer, "RunStore", return_value=self.store),
                        mock.patch.object(restore_reviewer.records, "read", return_value=self.options),
                        mock.patch.object(restore_reviewer, "read_json", side_effect=lambda p: self.evidence if p.name == "V1.json" else {"review_mode": "requested"}),
                        mock.patch.object(restore_reviewer.contracts, "validate", return_value=[]),
                        mock.patch.object(restore_reviewer.progress, "read_lines", return_value=[{"item": "P1.1", "reason_code": "ROUTE_UPGRADED"}]),
                        mock.patch.object(restore_reviewer.progress, "Progress"),
                        mock.patch.object(restore_reviewer.checks, "head", return_value="base"),
                        mock.patch.object(restore_reviewer.checks, "dirty_digest", return_value="digest")]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_restores_only_override_and_preserves_attempts(self):
        receipt = restore_reviewer.restore(self.project, "run", "P1.1", "digest")
        item = self.state["items"]["P1.1"]
        self.assertNotIn("reviewer", item["route_overrides"])
        self.assertEqual(item["corrections_used"], 1)
        self.assertEqual(item["steps"]["review.1"]["status"], "started")
        self.assertEqual(receipt["previous"]["model_class"], "frontier")
        self.assertTrue((self.folder / "P1.1/route-restorations/1.json").is_file())
        self.store.save.assert_called_once()

    def test_refuses_changed_candidate_or_completed_review(self):
        for case in ("digest", "review"):
            with self.subTest(case=case):
                if case == "review":
                    self.state["items"]["P1.1"]["steps"]["review.1"]["status"] = "done"
                with self.assertRaises(Stop):
                    restore_reviewer.restore(self.project, "run", "P1.1", "wrong" if case == "digest" else "digest")
                self.assertIn("reviewer", self.state["items"]["P1.1"]["route_overrides"])
        self.store.save.assert_not_called()
