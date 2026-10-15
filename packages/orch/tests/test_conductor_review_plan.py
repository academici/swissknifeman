"""The review plan of a batch (review.strategy): chosen before the first piece, carried out after the last piece of a group."""
from __future__ import annotations

import json
import unittest

from tests.test_conductor import GREEN, ConductorCase, executor_ok

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
