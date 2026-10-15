"""One executor session for the pieces of a run (``session.executor``): the executor of the next piece, and of every
correction round, resumes the session of the previous executor (``--resume``), and the first prompt names the pieces
of the run; ``per-item`` (``--no-single-session``) starts a fresh session each time."""
from __future__ import annotations

import json
import unittest

from orch.conductor import options, prompts
from tests.test_conductor import GREEN, ConductorCase, executor_ok
from tests.test_conductor_prompts import fixture


class SessionOptionsTests(unittest.TestCase):
    def test_shared_is_the_default(self):
        self.assertEqual(options.DEFAULTS["session"], {"executor": "shared"})

    def test_a_layer_can_choose_per_item_and_a_bad_value_is_refused(self):
        merged = options.merge(options.DEFAULTS, {"session": {"executor": "per-item"}})
        self.assertEqual(merged["session"]["executor"], "per-item")
        from orch.conductor import contract
        self.assertEqual(contract.problems({"session": {"executor": "per-item"}}, "run-options"), [])
        self.assertTrue(contract.problems({"session": {"executor": "forever"}}, "run-options"))
        self.assertTrue(contract.problems({"session": {"reviewer": "shared"}}, "run-options"))


class BatchBlockTests(unittest.TestCase):
    def test_no_note_is_no_block_and_a_note_is_a_supporting_run_rules_block(self):
        plain = prompts.executor(fixture("adhoc"), item="W1", step="executor.1")
        noted = prompts.executor(fixture("adhoc"), item="W1", step="executor.1", batch="## Run batch\n\nW1, W2")
        self.assertEqual(len(noted), len(plain) + 1)
        block = [b for b in noted if b.text.startswith("## Run batch")][0]
        self.assertEqual((block.kind, block.origin), ("run_rules", "conductor"))


class SharedSessionTests(ConductorCase):
    def argv(self, number: int) -> list:
        return json.loads((self.fake / f"executor-{number}.argv").read_text(encoding="utf-8"))

    def two_items(self):
        self.set_items({"W1": {}, "W2": {}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN, GREEN]})

    def test_the_second_piece_resumes_the_session_of_the_first(self):
        self.two_items()
        code, _, err = self.run_items("W1", "W2")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertNotIn("--resume", self.argv(1))
        self.assertEqual(self.argv(2)[self.argv(2).index("--resume") + 1], "executor-session-1")
        self.assertEqual(self.state(err)["executor_session"], "executor-session-2")

    def test_the_prompts_name_the_run_and_say_whether_the_session_is_resumed(self):
        self.two_items()
        self.run_items("W1", "W2")
        first, second = self.prompt("executor", 1), self.prompt("executor", 2)
        self.assertIn("## Run batch", first)
        self.assertIn("W1, W2", first)
        self.assertIn("You start with W1", first)
        self.assertIn("You are resuming it", second)

    def test_per_item_starts_a_fresh_session_and_adds_no_note(self):
        self.two_items()
        code, _, err = self.run_items("W1", "W2", extra=("--no-single-session",))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("--resume", self.argv(2))
        self.assertNotIn("## Run batch", self.prompt("executor", 1))
        self.assertNotIn("executor_session", self.state(err))

    def test_one_piece_alone_has_no_note_and_no_resume(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("## Run batch", self.prompt("executor", 1))
        self.assertNotIn("--resume", self.argv(1))


if __name__ == "__main__":
    unittest.main()
