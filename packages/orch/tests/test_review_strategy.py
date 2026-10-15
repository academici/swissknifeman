"""The review strategy of a batch: the facts, the rules' choice, and the check of a strategist's answer."""
from __future__ import annotations

import unittest

from orch.conductor.policies import review_strategy as strategy


def piece(ref, *paths, route=None, title=None):
    return {"ref": ref, "title": title or f"piece {ref}", "goal": "g", "include": [], "write_set": list(paths),
            "route": route or {"class": "implementation", "effort": "medium"}, "checks": 1}


class RulesTests(unittest.TestCase):
    def test_a_chain_on_the_same_folders_is_one_review(self):
        pieces = [piece(f"P12.{i}", "packages/orch/lib/orch/events.py", "packages/orch/tests/**") for i in range(1, 4)]
        chosen = strategy.rules(pieces)
        self.assertEqual((chosen["mode"], chosen["groups"]), ("single", [["P12.1", "P12.2", "P12.3"]]))

    def test_a_long_chain_is_cut_into_groups_of_at_most_four(self):
        pieces = [piece(f"P1.{i}", "packages/orch/lib/x.py") for i in range(1, 7)]
        chosen = strategy.rules(pieces)
        self.assertEqual(chosen["mode"], "groups")
        self.assertEqual([len(group) for group in chosen["groups"]], [4, 2])

    def test_uncoupled_pieces_are_reviewed_each(self):
        chosen = strategy.rules([piece("A", "packages/orch/x.py"), piece("B", "packages/skiller/y.py"),
                                 piece("C", "docs/z.md")])
        self.assertEqual((chosen["mode"], chosen["groups"]), ("each", [["A"], ["B"], ["C"]]))

    def test_the_foundation_and_a_frontier_piece_are_read_alone(self):
        pieces = [piece("A", "packages/orch/a.py"), piece("B", "packages/aicore/lib/b.py", "packages/orch/b.py"),
                  piece("C", "packages/orch/c.py"), piece("D", "packages/orch/d.py", route={"class": "frontier", "effort": "high"})]
        self.assertEqual(strategy.rules(pieces)["groups"], [["A"], ["B"], ["C"], ["D"]])

    def test_security_wording_raises_the_effort(self):
        chosen = strategy.rules([piece("A", "packages/orch/redact.py", title="redact secrets"), piece("B", "packages/orch/b.py")])
        self.assertEqual(chosen["reviewer"]["effort"], "high")

    def test_one_piece_and_no_piece(self):
        self.assertEqual(strategy.rules([piece("A", "x")])["mode"], "each")
        self.assertEqual(strategy.rules([])["mode"], "none")


class AnswerTests(unittest.TestCase):
    refs = ["A", "B", "C"]

    def test_a_sound_answer_in_a_fence_is_taken(self):
        text = '```json\n{"mode": "groups", "groups": [["A", "B"], ["C"]], "reviewer": {"effort": "high"}, "reason": "r"}\n```'
        chosen = strategy.check(strategy.parse(text), self.refs)
        self.assertEqual((chosen["mode"], chosen["groups"], chosen["reviewer"], chosen["source"]),
                         ("groups", [["A", "B"], ["C"]], {"effort": "high"}, "model"))

    def test_an_answer_that_is_not_a_partition_in_order_is_refused(self):
        for answer in ({"mode": "groups", "groups": [["A"], ["C"]]}, {"mode": "groups", "groups": [["B", "A"], ["C"]]},
                       {"mode": "single", "groups": [["A"], ["B", "C"]]}, {"mode": "each", "groups": [["A", "B"], ["C"]]},
                       {"mode": "groups", "groups": [["A", "B", "C", "A", "B"]]}, {"mode": "weird", "groups": [self.refs]},
                       {"mode": "single", "groups": [self.refs], "reviewer": {"effort": "extreme"}}):
            self.assertIsNone(strategy.check(answer, self.refs), answer)

    def test_none_needs_no_groups_and_garbage_is_not_json(self):
        self.assertEqual(strategy.check({"mode": "none"}, self.refs)["groups"], [])
        self.assertIsNone(strategy.parse("I would review all of it"))

    def test_the_prompt_names_every_piece_and_the_answer_format(self):
        text = strategy.prompt([piece("A", "x"), piece("B", "y")], strategy.rules([piece("A", "x"), piece("B", "y")]))
        for needle in ('"ref": "A"', '"ref": "B"', "```json", "`groups`"):
            self.assertIn(needle.replace("```json", "fenced `json`"), text.replace("```json", "fenced `json`"))


if __name__ == "__main__":
    unittest.main()
