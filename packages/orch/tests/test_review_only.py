"""Review-only conductor with fake roles: dirty worktree, receipt and compact stdout."""
import copy
import json

from orch import adhoc
from orch.conductor import contract, records
from tests.test_conductor import ConductorCase, GREEN, FINDING


class ReviewOnlyTests(ConductorCase):
    def test_dirty_worktree_is_reviewed_without_executor_checks_advisor_or_commit(self):
        base = self.git("rev-parse", "HEAD").strip()
        (self.project / "README.md").write_text("candidate\n")
        (self.project / "new.py").write_text("new\n")
        doc = adhoc.build_adhoc_input(None, [], review=base + "..WORKTREE", plan="T", item="W1")
        path = self.project.parent / "review.json"
        path.write_text(json.dumps(doc))
        findings = copy.deepcopy(FINDING["result"])
        findings["findings"][0]["location"] = "README.md:1"
        stream = "RAW_REVIEW_STREAM_" * 131072
        self.script({"reviewer": [{"result": findings, "stream": [stream]}], "triager": [{"result": {
            "confirmed": [{"finding": "F1", "reproduction": {"cmd": "test candidate", "exit": 1,
            "observed": "bad candidate"}, "fix": "repair"}], "rejected": []}}]})
        code, out, err = self.conduct("run", "--input", path, "--commit", "--json-lines")
        self.assertEqual((0, ("finished", None)), (code, self.outcome(err)), err)
        result = json.loads(out.splitlines()[-1])
        self.assertEqual(set(result), {"run", "receipt", "verdict", "open", "findings"})
        self.assertEqual([], contract.problems(result, "review-summary"))
        self.assertTrue(contract.problems(dict(result, stream="forbidden"), "review-summary"))
        receipt = json.loads((self.project / result["receipt"]).read_text())
        self.assertEqual(receipt["subject"], "T.W1")
        self.assertEqual(receipt["base"], base)
        self.assertEqual(set(receipt["candidate"]["paths"]), {"README.md", "new.py"})
        self.assertEqual(receipt["open"], {"blocker": 0, "major": 1})
        self.assertEqual(result["findings"][0]["id"], "F1")
        state = records.read(self.run_dir(err) / "state.json", "state")
        steps = state["items"][doc["input_id"]]["steps"]
        self.assertIn("review.1", steps)
        self.assertIn("triage.1", steps)
        self.assertIn("register", steps)
        self.assertFalse(any(name.startswith(("executor", "checks", "scout", "research", "advice", "commit"))
                             for name in steps))
        self.assertEqual(self.calls("executor"), 0)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), base)
        self.assertNotIn("RAW_REVIEW_STREAM_", out)
        self.assertLess(len(out), 2000)
        self.assertTrue(list(self.run_dir(err).glob("*/streams/review.1.jsonl")))

    def test_clean_review_has_input_subject_and_still_triages_once(self):
        doc = adhoc.build_adhoc_input(None, [], review="HEAD..WORKTREE")
        path = self.project.parent / "review.json"
        path.write_text(json.dumps(doc))
        self.script({"reviewer": [GREEN], "triager": [{"result": {"confirmed": [], "rejected": []}}]})
        code, out, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertEqual(code, 0, err)
        receipt = json.loads((self.project / json.loads(out.splitlines()[-1])["receipt"]).read_text())
        self.assertEqual(receipt["subject"], doc["input_id"])
        self.assertEqual(self.calls("triager"), 1)

    def test_equal_normalized_keys_do_not_hide_a_blocker_in_the_receipt(self):
        doc = adhoc.build_adhoc_input(None, [], review="HEAD..WORKTREE")
        path = self.project.parent / "review-collisions.json"
        path.write_text(json.dumps(doc))
        finding = dict(FINDING["result"]["findings"][0], location="README.md:1", severity="Blocker")
        other = dict(finding, id="F2", severity="Major")
        self.script({"reviewer": [{"result": {"verdict": "RED", "findings": [finding, other]}}],
                     "triager": [{"result": {"confirmed": [{"finding": row["id"],
                         "reproduction": {"cmd": "test case", "exit": 1, "observed": "failure"}, "fix": "repair"}
                         for row in (finding, other)], "rejected": []}}]})
        code, out, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertEqual(code, 0, err)
        result = json.loads(out.splitlines()[-1])
        self.assertEqual({"blocker": 1, "major": 1}, result["open"])
        self.assertEqual(["F1", "F2"], [row["id"] for row in result["findings"]])

    def test_named_head_reviews_committed_blobs_instead_of_dirty_worktree(self):
        base = self.git("rev-parse", "HEAD").strip()
        (self.project / "README.md").write_text("committed candidate\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "candidate")
        head = self.git("rev-parse", "HEAD").strip()
        blob = self.git("rev-parse", "HEAD:README.md").strip()
        (self.project / "README.md").write_text("different uncommitted content\n")
        doc = adhoc.build_adhoc_input(None, [], review=base + "..HEAD")
        path = self.project.parent / "review-head.json"
        path.write_text(json.dumps(doc))
        self.script({"reviewer": [GREEN], "triager": [{"result": {"confirmed": [], "rejected": []}}]})
        code, out, err = self.conduct("run", "--input", path, "--json-lines")
        self.assertEqual(code, 0, err)
        receipt = json.loads((self.project / json.loads(out.splitlines()[-1])["receipt"]).read_text())
        self.assertEqual(receipt["candidate"]["paths"], {"README.md": "100644 " + blob})
        self.assertEqual(receipt["candidate"]["head"], head)
        prompt = self.prompt("reviewer", 1)
        self.assertIn("+committed candidate", prompt)
        self.assertNotIn("+different uncommitted content", prompt)
