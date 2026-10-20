"""Hard token admission and resumable raises on fake providers; no live model calls."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from aicore.config import ConfigError

from orch import settings
from orch.conductor import options
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.policies import budget
from tests.test_conductor import ConductorCase, GREEN, executor_ok


class HardBudgetTests(ConductorCase):
    def options_file(self, **limits):
        path = self.project.parent / "hard-options.json"
        path.write_text(json.dumps({"limits": limits}), encoding="utf-8")
        return path

    def capped(self, **limits):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        return self.run_items("W1", extra=("--options", self.options_file(**limits)))

    def resume(self, err, *extra):
        return self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines", *extra)

    def test_reaching_the_item_limit_preserves_done_executor_and_stops_before_next_model(self):
        code, _, err = self.capped(tokens_hard_max=110)
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        state = self.state(err)
        item = state["items"]["W1"]
        self.assertEqual(item["outcome"], "stopped")
        self.assertEqual(item["steps"]["executor.1"]["status"], "done")
        self.assertNotIn("review.1", item["steps"])
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (1, 0))
        self.assertEqual(self.source()["registered"], {})
        self.assertFalse(any(line.get("reason_code") == "ITEM_BLOCKED" for line in self.lines(err)))
        self.assertEqual(state["stop"]["message"],
                         f"W1 used 110 fresh tokens >= tokens_hard_max 110; needs_replan: split the item or raise the limit "
                         f"(conduct resume --run {self.run_dir(err).name} --raise-limit tokens_hard_max=<value>)")

    def test_run_limit_stops_before_the_second_piece_starts_model_steps(self):
        self.set_items({ref: {} for ref in ("W1", "W2")})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN]})
        path = self.options_file(run_tokens_hard_max=110)
        code, _, err = self.run_items("W1", "W2", extra=("--options", path, "--no-batch"))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        self.assertEqual(self.calls("executor"), 1)
        self.assertFalse([line for line in self.lines(err) if line.get("item") == "W2" and
                          line["event"] == "stage.start" and line.get("role") != "deterministic"])
        self.assertIn("run_tokens_hard_max 110", self.state(err)["stop"]["message"])

    def test_zero_limits_leave_the_budget_beacon_informational(self):
        code, _, err = self.capped(tokens_max=1, tokens_hard_max=0, run_tokens_hard_max=0)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("reviewer"), 1)
        self.assertTrue([line for line in self.lines(err) if line.get("reason_code") == "BUDGET_OVER"])

    def test_soft_target_above_hard_limit_is_options_invalid(self):
        code, _, err = self.capped(tokens_max=111, tokens_hard_max=110)
        self.assertEqual(code, 1)
        self.assertIn("OPTIONS_INVALID", err)
        self.assertEqual(self.calls("executor"), 0)

    def test_item_cannot_set_or_disable_a_run_cap_even_with_an_invocation_source_name(self):
        for value in (0, 10000):
            with self.subTest(value=value):
                self.set_items({"W1": {"options": [{"source": "invocation:--options",
                                                    "options": {"limits": {"run_tokens_hard_max": value}}}]}})
                code, _, err = self.run_items("W1")
                self.assertEqual((code, self.outcome(err)), (1, ("stopped", "OPTIONS_INVALID")), err)
                self.assertIn("run_tokens_hard_max is a run limit; set it in the configuration or --options", err)
                self.assertEqual(self.calls("executor"), 0)

    def test_resume_without_raise_stops_again_without_repeating_any_model(self):
        _, _, err = self.capped(tokens_hard_max=110)
        before = self.state(err)["items"]["W1"]["steps"]
        code, _, resumed = self.resume(err)
        self.assertEqual((code, self.outcome(resumed)), (1, ("stopped", "TOKEN_BUDGET")), resumed)
        self.assertEqual(self.state(resumed)["items"]["W1"]["steps"], before)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (1, 0))

    def test_raise_resumes_from_first_unfinished_step_and_records_provenance(self):
        _, _, err = self.capped(tokens_hard_max=110)
        path = self.run_dir(err) / "W1/options.json"
        before, stamp = path.read_bytes(), path.stat().st_mtime_ns
        executor = self.state(err)["items"]["W1"]["steps"]["executor.1"]
        code, _, resumed = self.resume(err, "--raise-limit", "tokens_hard_max=500")
        self.assertEqual((code, self.outcome(resumed)), (0, ("finished", None)), resumed)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (1, 1))
        self.assertEqual(self.state(resumed)["items"]["W1"]["steps"]["executor.1"], executor)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), (before, stamp))
        change, = self.state(resumed)["limit_raises"]
        self.assertEqual({key: change[key] for key in ("key", "from", "to", "by")},
                         {"key": "tokens_hard_max", "from": 110, "to": 500, "by": "invocation"})
        self.assertTrue(change["at"])
        self.assertEqual([line["event"] for line in self.lines(resumed) if line.get("reason_code") == "LIMIT_RAISED"], ["info"])

    def test_a_raise_of_the_piece_limit_holds_for_its_piece_only(self):
        def piece(ref, limit):
            item = Item(ref, "r", {}, Path("."), {})
            item.options = {"limits": {"tokens_hard_max": limit}}
            return item
        first, second = piece("W1", 500), piece("W2", 1000)
        run = SimpleNamespace(state={"limit_raises": [{"key": "tokens_hard_max", "from": 500, "to": 600, "item": "W1"}]},
                              run_doc={})
        self.assertEqual((budget.effective_limit(run, first, "tokens_hard_max"),
                          budget.effective_limit(run, second, "tokens_hard_max")), (600, 1000))
        run.state["limit_raises"].append({"key": "tokens_hard_max", "from": 600, "to": 0, "item": "W1"})
        self.assertEqual(budget.effective_limit(run, second, "tokens_hard_max"), 1000)  # not removed for W2 either
        legacy = SimpleNamespace(state={"limit_raises": [{"key": "tokens_hard_max", "from": 500, "to": 700}]}, run_doc={})
        self.assertEqual((budget.effective_limit(legacy, first, "tokens_hard_max"),
                          budget.effective_limit(legacy, second, "tokens_hard_max")), (700, 700))  # read as before

    def test_the_raise_record_names_the_stopped_piece(self):
        _, _, err = self.capped(tokens_hard_max=110)
        code, _, resumed = self.resume(err, "--raise-limit", "tokens_hard_max=500")
        self.assertEqual(code, 0, resumed)
        change, = self.state(resumed)["limit_raises"]
        self.assertEqual(change["item"], "W1")

    def test_the_run_records_its_catalogs_and_a_resume_names_the_changed_ones(self):
        """W5: provenance of the catalogs, not a stop: --frozen does not freeze them."""
        _, _, err = self.capped(tokens_hard_max=110)
        recorded = json.loads((self.run_dir(err) / "run.json").read_text())["catalog_digests"]
        self.assertEqual(set(recorded), {"launch", "models", "capabilities"})
        self.assertTrue(all(value.startswith("sha256:") or len(value) == 64 for value in recorded.values()), recorded)
        status = json.loads(self.conduct("status", "--run", self.run_dir(err).name, "--json")[1])
        self.assertEqual(status["catalog_digests"], recorded)
        code, _, same = self.resume(err)  # nothing changed: no beacon
        self.assertFalse([line for line in self.lines(same) if line.get("reason_code") == "CATALOG_CHANGED"])
        self.write_config(extra='[orch.launch.entries.executor_claude-code]\neffort = "xhigh"\n')
        code, _, resumed = self.resume(err, "--raise-limit", "tokens_hard_max=500")
        said = [line for line in self.lines(resumed) if line.get("reason_code") == "CATALOG_CHANGED"]
        self.assertEqual(len(said), 1, resumed)
        self.assertIn("launch", said[0]["message"])
        self.assertNotIn("models", said[0]["message"])

    def test_a_run_without_catalog_digests_resumes_as_before(self):
        _, _, err = self.capped(tokens_hard_max=110)
        path = self.run_dir(err) / "run.json"
        doc = json.loads(path.read_text())
        doc.pop("catalog_digests")
        path.write_text(json.dumps(doc), encoding="utf-8")
        code, _, resumed = self.resume(err, "--raise-limit", "tokens_hard_max=500")
        self.assertEqual(code, 0, resumed)
        self.assertFalse([line for line in self.lines(resumed) if line.get("reason_code") == "CATALOG_CHANGED"])

    def test_invalid_raises_are_atomic_and_do_not_change_state_or_journal(self):
        _, _, err = self.capped(tokens_hard_max=110)
        directory = self.run_dir(err)
        before = {name: (directory / name).read_bytes() for name in ("state.json", "progress.jsonl")}
        for values in (("tokens_hard_max=109",), ("tokens_hard_max=110",), ("tokens_max=200",),
                       ("tokens_hard_max=-1",), ("tokens_hard_max=1.5",), ("tokens_hard_max",),
                       ("tokens_hard_max=500", "run_tokens_hard_max=-1")):
            with self.subTest(values=values):
                args = [part for value in values for part in ("--raise-limit", value)]
                code, _, error = self.resume(err, *args)
                self.assertEqual(code, 1)
                self.assertIn("OPTIONS_INVALID", error)
                self.assertEqual({name: (directory / name).read_bytes() for name in before}, before)
        self.assertEqual(self.calls("executor"), 1)

    def test_repeatable_raises_can_explicitly_remove_both_limits(self):
        _, _, err = self.capped(tokens_hard_max=110, run_tokens_hard_max=110)
        code, _, resumed = self.resume(err, "--raise-limit", "tokens_hard_max=0", "--raise-limit", "run_tokens_hard_max=0")
        self.assertEqual(code, 0, resumed)
        self.assertEqual([(row["key"], row["from"], row["to"]) for row in self.state(resumed)["limit_raises"]],
                         [("tokens_hard_max", 110, 0), ("run_tokens_hard_max", 110, 0)])

    def test_later_raise_is_compared_to_the_prior_raise(self):
        _, _, err = self.capped(tokens_hard_max=110)
        code, _, resumed = self.resume(err, "--raise-limit", "tokens_hard_max=200")
        self.assertEqual((code, self.outcome(resumed)), (1, ("stopped", "TOKEN_BUDGET")), resumed)
        code, _, error = self.resume(resumed, "--raise-limit", "tokens_hard_max=150")
        self.assertEqual(code, 1)
        self.assertIn("effective value 200", error)
        code, _, resumed = self.resume(err, "--raise-limit", "tokens_hard_max=300")
        self.assertEqual(code, 0, resumed)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (1, 1))

    def test_run_cap_is_frozen_even_if_options_and_configuration_change_on_resume(self):
        _, _, err = self.capped(run_tokens_hard_max=110)
        run_path = self.run_dir(err) / "run.json"
        recorded = json.loads(run_path.read_text())["limits_run"]["run_tokens_hard_max"]
        self.assertEqual((recorded["value"], recorded["source"]), (110, "invocation:--options"))
        self.options_file(run_tokens_hard_max=0)
        self.write_config(extra="[orch.conductor.limits]\nrun_tokens_hard_max = 0\n")
        code, _, resumed = self.resume(err)
        self.assertEqual((code, self.outcome(resumed)), (1, ("stopped", "TOKEN_BUDGET")), resumed)
        code, _, resumed = self.resume(err, "--raise-limit", "run_tokens_hard_max=500")
        self.assertEqual(code, 0, resumed)
        self.assertEqual(json.loads(run_path.read_text())["limits_run"]["run_tokens_hard_max"], recorded)

    def test_machine_project_and_invocation_configuration_reach_the_cap_with_provenance(self):
        self.write_config(extra="[orch.conductor.limits]\ntokens_hard_max = 1000\nrun_tokens_hard_max = 110\n")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        recorded = json.loads((self.run_dir(err) / "run.json").read_text())["limits_run"]["run_tokens_hard_max"]
        self.assertEqual((recorded["value"], recorded["source"]), (110, "config:machine"))
        project_config = self.project / ".swissknifeman/config.toml"
        project_config.parent.mkdir(exist_ok=True)
        project_config.write_text("schema_version = 1\n[orch.conductor.limits]\nrun_tokens_hard_max = 220\n")
        resolved = settings.load(project=self.project)
        self.assertEqual(resolved.conductor["limits"]["run_tokens_hard_max"], 220)
        invocation = self.project.parent / "invocation.toml"
        invocation.write_text("schema_version = 1\n[orch.conductor.limits]\nrun_tokens_hard_max = 330\n")
        resolved = settings.load(project=self.project, config_file=invocation)
        self.assertEqual(resolved.conductor["limits"]["run_tokens_hard_max"], 330)

    def test_item_hard_cap_from_configuration_and_untrusted_item_options(self):
        self.write_config(extra="[orch.conductor.limits]\ntokens_hard_max = 110\n")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"limits": {"tokens_hard_max": 100}}}]}})
        code, _, err = self.run_items("W1", extra=("--adopt",))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        self.assertIn("tokens_hard_max 100", self.state(err)["stop"]["message"])

    def test_unmetered_usage_does_not_invent_a_budget_stop(self):
        self.script({"executor": [dict(executor_ok("W1"), usage={})], "reviewer": [dict(GREEN, usage={})]})
        code, _, err = self.run_items("W1", extra=("--options", self.options_file(tokens_hard_max=1, run_tokens_hard_max=1)))
        self.assertEqual(code, 0, err)
        self.assertTrue(self.state(err)["items"]["W1"]["usage_incomplete"])
        self.assertFalse([line for line in self.lines(err) if line.get("reason_code") == "TOKEN_BUDGET"])

    def test_run_cap_cannot_come_from_the_environment(self):
        with mock.patch.dict("os.environ", {"SKM_ORCH_CONDUCTOR__LIMITS__RUN_TOKENS_HARD_MAX": "110"}):
            with self.assertRaises(ConfigError) as caught:
                settings.load(project=self.project)
        self.assertIn("CONFIG_LAYER_FORBIDDEN", str(caught.exception))

    def test_a_failed_attempt_is_not_a_separate_hard_admission_boundary(self):
        self.script({"executor": [{"exit": 1, "stderr": "boom", "usage": {"input_tokens": 110}}, executor_ok("W1")],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--options", self.options_file(tokens_hard_max=110)))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertEqual(self.state(err)["items"]["W1"]["steps"]["executor.1"]["status"], "done")

    def test_a_model_step_is_denied_before_the_started_record_or_call(self):
        from orch.conductor import engine
        owner = engine.Conductor(project=self.project, settings=settings.load(project=self.project))
        owner.state = {"tokens": {"input": 110}}
        owner.run_id = "R"
        item = Item("W1", "source-run", {"tokens": {"input": 110}}, self.project, {})
        item.options = {"limits": {"tokens_hard_max": 110}}
        call = mock.Mock()
        with mock.patch.object(owner, "_start_step") as start:
            with self.assertRaises(Stop) as caught:
                owner._step(item, "executor.2", call, role="executor")
            self.assertEqual(caught.exception.code, "TOKEN_BUDGET")
            call.assert_not_called()
            start.assert_not_called()
        self.assertEqual(item.state["steps"], {})


class AdmissionTests(unittest.TestCase):
    def test_snapshot_does_not_validate_piece_limits_before_item_layers_merge(self):
        from orch.conductor.application import run_service
        owner = SimpleNamespace(conductor={"limits": {"tokens_max": 200, "tokens_hard_max": 100}},
                                settings=SimpleNamespace(resolved=None))
        self.assertEqual(run_service.limits_run(owner, None)["run_tokens_hard_max"]["value"], 0)
        resolved, _ = options.effective(owner.conductor, {},
                                       [{"source": "item:W1", "options": {"limits": {"tokens_hard_max": 300}}}])
        self.assertEqual(resolved["limits"]["tokens_hard_max"], 300)

    def test_run_usage_is_cumulative_and_cache_reads_do_not_count(self):
        item = Item("W2", "source-run", {"tokens": {"input": 10, "output": 1, "cached": 1000000}}, Path(), {})
        item.options = {"limits": {"tokens_hard_max": 12, "run_tokens_hard_max": 100}}
        owner = SimpleNamespace(state={"tokens": {"input": 90, "output": 10, "cached": 1000000}}, run_doc={}, run_id="R")
        budget.admit(owner, item, "item")
        with self.assertRaises(Stop) as caught:
            budget.admit(owner, item)
        self.assertEqual(caught.exception.code, "TOKEN_BUDGET")
        self.assertTrue(caught.exception.message.startswith("run R used 100 fresh tokens >= run_tokens_hard_max 100;"))

    def test_soft_and_hard_limits_validate_after_layers_merge(self):
        with self.assertRaises(options.OptionsError) as caught:
            options.effective({"limits": {"tokens_max": 200}}, {},
                              [{"source": "item:W1", "options": {"limits": {"tokens_hard_max": 100}}}])
        self.assertEqual(caught.exception.code, "OPTIONS_INVALID")


if __name__ == "__main__":
    unittest.main()
