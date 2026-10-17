"""The review plan of a batch (review.strategy): chosen before the first piece, carried out after the last piece of a group."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from tests.test_conductor import GREEN, ConductorCase, executor_ok, report

REVIEW = "## Findings\n[Major] out/W3.txt:1 - a defect\nScenario: x -> y\nFix: z\n## Checked and fine\n- a\n"


def answer(mode, groups, effort="medium"):
    return {"text": "```json\n" + json.dumps({"mode": mode, "groups": groups, "reviewer": {"effort": effort},
                                              "reason": "test"}) + "\n```\n"}


class ReviewPlanTests(ConductorCase):
    def batch(self, *, triager=None, options=None, items=("W1", "W2", "W3")):
        self.set_items({ref: {} for ref in items})
        self.script({"executor": [executor_ok(ref) for ref in items], "reviewer": [GREEN] * 3 if not triager else [{"text": REVIEW}],
                     **({"triager": [triager]} if triager else {})})
        extra = ()
        if options:
            path = self.project.parent / "opts.json"
            path.write_text(json.dumps(options), encoding="utf-8")
            extra = ("--options", path)
        code, _, err = self.run_items(*items, extra=extra)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        return err

    def plan_of(self, err):
        return self.state(err).get("review_strategy")

    def events(self, err, code):
        return [line for line in self.lines(err) if line.get("reason_code") == code]

    def test_the_strategist_picks_one_review_for_the_whole_batch(self):
        err = self.batch(triager=answer("single", [["W1", "W2", "W3"]]))
        plan = self.plan_of(err)
        self.assertEqual((plan["mode"], plan["groups"], plan["source"]), ("single", [["W1", "W2", "W3"]], "model"))
        self.assertEqual(self.calls("reviewer"), 1)  # one review of the group, none per piece
        self.assertEqual(self.calls("triager"), 1)
        kept = self.state(err)["group_reviews"]["1"]
        self.assertEqual((kept["refs"], kept["counts"]["Major"]), (["W1", "W2", "W3"], 1))
        self.assertTrue((self.run_dir(err) / "group-review-1.md").is_file())
        self.assertTrue(self.events(err, "GROUP_REVIEW"))
        self.assertTrue(self.events(err, "REVIEW_STRATEGY"))

    def test_a_reply_in_another_format_is_a_failed_review_not_a_clean_one(self):
        self.set_items({r: {} for r in ("W1", "W2", "W3")})
        self.script({"executor": [executor_ok(r) for r in ("W1", "W2", "W3")], "reviewer": [{"text": "Looks fine to me."}],
                     "triager": [answer("single", [["W1", "W2", "W3"]])]})
        code, _, err = self.run_items("W1", "W2", "W3")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.state(err)["group_reviews"]["1"]["format"], "malformed")
        self.assertFalse(self.events(err, "GROUP_REVIEW"))
        self.assertTrue(self.events(err, "GROUP_REVIEW_FAILED"))

    def test_major_findings_come_with_a_ready_followup_input(self):
        err = self.batch(triager=answer("single", [["W1", "W2", "W3"]]))
        kept = self.state(err)["group_reviews"]["1"]
        self.assertEqual(kept["format"], "findings")
        path = self.project / kept["followup"]
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["provenance"]["kind"], "review_followup")
        self.assertEqual(doc["scope"]["include"], ["out/W3.txt"])
        self.assertIn("[Major] out/W3.txt:1 - a defect", doc["goal"])
        message = self.events(err, "GROUP_REVIEW")[0]["message"]
        self.assertIn("orch conduct run --input", message)

    def test_an_effort_named_by_the_reviewer_option_beats_the_strategy(self):
        from orch.conductor import options as opts
        from orch.conductor.application import review_plan
        named = opts.parse_selector("codex/gpt-6.1-sol/high")
        self.assertEqual(review_plan.reviewer_effort(named, "medium"), "high")
        self.assertEqual(review_plan.reviewer_effort(opts.parse_selector("codex/gpt-6.1-sol"), "medium"), "medium")

    def test_the_strategy_beacon_announces_the_effort_the_group_review_runs_at(self):
        from types import SimpleNamespace
        from orch.conductor.application import review_plan
        catalog = SimpleNamespace(conductor={})
        self.assertEqual(review_plan.group_effort(catalog, "codex/gpt-6.1-sol/xhigh", "medium"), "xhigh")
        self.assertEqual(review_plan.group_effort(catalog, "codex/gpt-6.1-sol", "medium"), "medium")
        fixed = SimpleNamespace(conductor={"argv": {"reviewer": ["fake"]}})
        self.assertEqual(review_plan.group_effort(fixed, "codex/gpt-6.1-sol/xhigh", "medium"), "medium")

    def test_the_followup_asks_no_more_effort_than_the_executor_of_the_run_has(self):
        import tempfile
        from types import SimpleNamespace
        from orch.conductor.application import review_plan
        read = {"findings": [{"severity": "Major", "location": "a.py:1", "text": "a.py:1 - a defect"}]}
        for effort, expected in (("medium", "medium"), (None, "high")):
            with tempfile.TemporaryDirectory() as folder:
                owner = SimpleNamespace(directory=Path(folder), progress=SimpleNamespace(emit=lambda *a, **k: None),
                                        _relative=lambda path: str(path))
                target = review_plan.followup_input(owner, 1, ["W1"], read, effort)
                doc = json.loads(Path(target).read_text(encoding="utf-8"))
                self.assertEqual(doc["route"]["minimum"], {"class": "implementation", "effort": expected})

    def test_a_group_whose_commits_changed_no_production_code_is_not_sent_to_the_reviewer(self):
        from unittest import mock
        from orch.conductor import review_batch
        self.set_items({r: {} for r in ("W1", "W2", "W3")})
        self.script({"executor": [executor_ok(r) for r in ("W1", "W2", "W3")], "reviewer": [GREEN],
                     "triager": [answer("single", [["W1", "W2", "W3"]])]})
        with mock.patch.object(review_batch, "INCLUDE", ["nowhere-in-the-project"]):  # the commits touch nothing it names
            code, _, err = self.run_items("W1", "W2", "W3")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("reviewer"), 0)
        self.assertEqual(self.state(err)["group_reviews"]["1"]["error"], "EMPTY_DIFF")
        self.assertTrue(self.events(err, "GROUP_REVIEW_FAILED"))

    def test_a_resume_between_groups_keeps_the_plan_and_reviews_each_group_once(self):
        blocked = report("W3", "blocked", open_issues=[{"text": "needs a decision", "kind": "escalation"}])
        self.set_items({r: {} for r in ("W1", "W2", "W3")})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2"), {"result": blocked}, executor_ok("W3")],
                     "reviewer": [{"text": REVIEW}, {"text": REVIEW}],
                     "triager": [answer("groups", [["W1", "W2"], ["W3"]])]})
        code, _, err = self.run_items("W1", "W2", "W3")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual(sorted(self.state(err)["group_reviews"]), ["1"])  # the first group was read before the stop
        doc = self.source()
        doc["items"]["W3"]["status"] = "todo"  # the source reopened the blocked piece
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        code, _, err2 = self.conduct("resume", "--run", self.run_dir(err).name, "--retry", "W3", "--json-lines")
        self.assertEqual(code, 0, err2)
        state = json.loads((self.run_dir(err) / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(state["group_reviews"]), ["1", "2"])
        self.assertEqual((self.calls("triager"), self.calls("reviewer")), (1, 2))  # not asked, not read again

    def test_a_batch_review_replaces_the_review_of_each_piece_even_when_dynamic_review_is_on(self):
        err = self.batch(triager=answer("single", [["W1", "W2", "W3"]]),
                         options={"review": {"dynamic": True, "dynamic_threshold": 0}})
        self.assertEqual(self.calls("reviewer"), 1)  # the group review only: no per-piece review was added by the risk score
        self.assertEqual(self.plan_of(err)["mode"], "single")

    def test_groups_are_reviewed_after_the_last_piece_of_each_group(self):
        err = self.batch(triager=answer("groups", [["W1", "W2"], ["W3"]], "high"))
        self.assertEqual(sorted(self.state(err)["group_reviews"]), ["1", "2"])
        self.assertEqual(self.state(err)["group_reviews"]["1"]["refs"], ["W1", "W2"])
        self.assertEqual(self.state(err)["group_reviews"]["2"]["effort"], "high")

    def test_an_unsound_answer_falls_back_to_the_rules(self):
        self.script({"executor": [executor_ok(r) for r in ("W1", "W2", "W3")], "reviewer": [{"text": REVIEW}],
                     "triager": [{"text": "I would just review everything"}]})
        self.set_items({r: {} for r in ("W1", "W2", "W3")})
        code, _, err = self.run_items("W1", "W2", "W3")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        plan = self.plan_of(err)
        self.assertEqual(plan["source"], "rules")
        self.assertTrue(self.events(err, "STRATEGIST_UNSOUND"))

    def test_strategist_rules_asks_no_model(self):
        err = self.batch(options={"review": {"strategist": "rules"}})
        self.assertEqual(self.plan_of(err)["source"], "rules")
        self.assertEqual(self.calls("triager"), 0)

    def test_none_reviews_nothing_and_each_keeps_the_review_of_every_piece(self):
        err = self.batch(options={"review": {"strategy": "none"}})
        self.assertEqual((self.plan_of(err)["mode"], self.calls("reviewer")), ("none", 0))

    def test_each_is_the_review_of_every_piece_as_before(self):
        err = self.batch(options={"review": {"strategy": "each"}})
        self.assertEqual((self.plan_of(err)["mode"], self.calls("reviewer")), ("each", 3))

    def test_one_piece_is_reviewed_as_configured_and_no_group_review_runs(self):
        self.set_items({"W1": {}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("group_reviews", self.state(err))
        self.assertEqual(self.calls("reviewer"), 1)


if __name__ == "__main__":
    unittest.main()
