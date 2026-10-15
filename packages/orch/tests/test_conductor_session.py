"""One executor session for the pieces of a run (``session.executor``): the executor of the next piece, and of every
correction round, resumes the session of the previous executor (``--resume``), and the first prompt names the pieces
of the run; ``per-item`` (``--no-batch``) starts a fresh session each time."""
from __future__ import annotations

import json
import unittest
from unittest import mock

from orch.conductor import engine, options, prompts
import sys

from tests.test_conductor import FIXTURES, GREEN, ROLES, ConductorCase, executor_ok
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

    def with_no_persistence(self):
        roles = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        roles["executor"].append("--no-session-persistence")  # what the launch catalog gives the executor
        self.write_config(argv=roles)
        self.two_items()

    def test_a_shared_executor_keeps_its_session_on_disk(self):
        self.with_no_persistence()
        code, _, err = self.run_items("W1", "W2")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("--no-session-persistence", self.argv(1))

    def test_per_item_leaves_the_flag_as_the_catalog_has_it(self):
        self.with_no_persistence()
        code, _, err = self.run_items("W1", "W2", extra=("--no-batch",))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertIn("--no-session-persistence", self.argv(1))

    def test_the_prompts_name_the_run_and_say_whether_the_session_is_resumed(self):
        self.two_items()
        self.run_items("W1", "W2")
        first, second = self.prompt("executor", 1), self.prompt("executor", 2)
        self.assertIn("## Run batch", first)
        self.assertIn("`W1`", first)
        self.assertIn("`W2`", first)
        self.assertIn("You start with W1", first)
        self.assertIn("You are resuming that session", second)

    def test_per_item_starts_a_fresh_session_and_adds_no_note(self):
        self.two_items()
        code, _, err = self.run_items("W1", "W2", extra=("--no-batch",))
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




class OptionsCopyTests(ConductorCase):
    def test_the_options_file_is_kept_with_the_run(self):
        options_file = self.project.parent / "opts.json"
        options_file.write_text(json.dumps({"rules": ["keep it short"]}), encoding="utf-8")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--options", options_file))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        kept = self.run_dir(err) / "options.json"
        self.assertEqual(json.loads(kept.read_text(encoding="utf-8")), {"rules": ["keep it short"]})


class ReviewFixesTests(unittest.TestCase):
    def test_every_role_that_reads_the_repository_is_isolated_by_default(self):
        for role in ("researcher", "advisor", "executor", "reviewer"):
            self.assertIn(role, options.DEFAULTS["instructions"]["isolate_roles"])

    def test_the_catalog_lets_the_researcher_and_the_advisor_query_with_an_invocation_config(self):
        from pathlib import Path
        catalog = (Path(__file__).resolve().parents[1] / "configs" / "launch-catalog.json").read_text(encoding="utf-8")
        self.assertEqual(catalog.count("Bash(python3 *orch.py --config * research query *)"), 2)

    def test_a_skills_choice_is_dropped_with_the_retry(self):
        import inspect
        self.assertIn('"skills_checked"', inspect.getsource(engine.Conductor._retry))


class SessionConfigTests(unittest.TestCase):
    def test_the_machine_config_layer_sets_the_default_and_a_run_option_overrides_it(self):
        layer = options.config_layer({"session_executor": "per-item"})
        self.assertEqual(layer["session"], {"executor": "per-item"})
        self.assertNotIn("session", options.config_layer({}))
        merged, sources = options.effective({"session_executor": "per-item"}, {}, [])
        self.assertEqual(merged["session"]["executor"], "per-item")
        merged, _ = options.effective({"session_executor": "per-item"}, {},
                                      [{"source": "plan", "options": {"session": {"executor": "shared"}}}])
        self.assertEqual(merged["session"]["executor"], "shared")




class ClaimAllTests(ConductorCase):
    def statuses_at_the_first_piece(self, *extra) -> dict:
        self.set_items({"W1": {}, "W2": {}, "W3": {}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2"), executor_ok("W3")], "reviewer": [GREEN] * 3})
        seen, original = {}, engine.Conductor._piece

        def spy(conductor, answer):
            if not seen:
                seen.update({ref: doc["status"] for ref, doc in self.source()["items"].items()})
            return original(conductor, answer)

        with mock.patch.object(engine.Conductor, "_piece", spy):
            code, _, err = self.run_items("W1", "W2", "W3", extra=extra)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        return seen

    def test_all_pieces_of_a_batch_are_in_progress_before_the_first_one_starts(self):
        self.assertEqual(self.statuses_at_the_first_piece(), {"W1": "in_progress", "W2": "in_progress", "W3": "in_progress"})

    def test_no_batch_takes_them_one_at_a_time(self):
        self.assertEqual(self.statuses_at_the_first_piece("--no-batch"),
                         {"W1": "in_progress", "W2": "todo", "W3": "todo"})

    def test_a_piece_that_waits_for_an_earlier_one_is_claimed_when_its_turn_comes(self):
        self.set_items({"W1": {}, "W2": {}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN] * 2})
        original, calls = engine.Conductor._claim, []

        def waiting(conductor, key, asked):
            calls.append(key)
            if key.endswith("W2") and len(calls) == 2:  # the claim-all pass: W1 is not done yet
                raise engine.Stop("CLAIM_BLOCKED", "W2: DEPENDENCY_NOT_READY: W2 waits for W1")
            return original(conductor, key, asked)

        with mock.patch.object(engine.Conductor, "_claim", waiting):
            code, _, err = self.run_items("W1", "W2")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertEqual(calls.count("item-W2"), 2)  # blocked once, claimed again at its turn

    def test_the_prompt_lists_every_piece_with_its_title_and_state(self):
        self.statuses_at_the_first_piece()
        first, second = self.prompt("executor", 1), self.prompt("executor", 2)
        self.assertIn("- `W1` — Work W1 (this piece)", first)
        self.assertIn("- `W2` — Work W2 (next)", first)
        self.assertIn("- `W1` — Work W1 (done and committed)", second)
        self.assertIn("- `W3` — Work W3 (next)", second)


class ClaimActorTests(ConductorCase):
    def test_the_claim_names_the_executor_class_the_run_was_started_with(self):
        options_file = self.project.parent / "o.json"
        options_file.write_text(json.dumps({"stages": [{"role": "executor", "model_class": "frontier"}]}), encoding="utf-8")
        eng = engine.Conductor.__new__(engine.Conductor)
        eng.run_doc, eng.directory = {"options_file": str(options_file)}, self.project
        self.assertEqual(eng._invocation_executor_class(), "frontier")
        eng.run_doc = {"options_file": str(self.project.parent / "gone.json")}
        self.assertIsNone(eng._invocation_executor_class())


class FenceTests(ConductorCase):
    def test_the_project_fence_is_the_default_and_the_executor_is_told_it_may_report_instead_of_block(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        prompt = self.prompt("executor", 1)
        self.assertIn("## Write fence of this run", prompt)
        self.assertIn("it is not a fence", prompt)

    def test_the_plan_fence_leaves_the_prompt_as_it_was(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--fence", "plan"))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("Write fence of this run", self.prompt("executor", 1))

    def test_an_extra_path_is_named_in_the_prompt_and_given_to_the_filesystem_guard(self):
        extra = self.project.parent / "shared-docs"
        extra.mkdir()
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--fence", "plan", "--allow-path", str(extra)))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertIn(f"`{extra}`", self.prompt("executor", 1))

    def test_ro_run_gets_one_rw_per_extra_path_before_the_separator(self):
        eng = engine.Conductor.__new__(engine.Conductor)
        item = type("I", (), {"options": {"scope": {"extra_paths": ["/data/a", "~/b"]}}})()
        argv = ["python3", "/x/ro-run.py", "--rw", "/p", "--", "claude", "-p"]
        out = eng._extra_write_dirs(item, "executor", argv)
        self.assertEqual(out[:5], ["python3", "/x/ro-run.py", "--rw", "/p", "--rw"])
        self.assertEqual(out[out.index("--"):], ["--", "claude", "-p"])
        self.assertEqual(out.count("--rw"), 3)
        self.assertEqual(eng._extra_write_dirs(item, "reviewer", argv), argv)
        self.assertEqual(eng._extra_write_dirs(item, "executor", ["claude", "-p"]), ["claude", "-p"])


if __name__ == "__main__":
    unittest.main()
