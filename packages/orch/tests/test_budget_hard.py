"""Hard token admission and resumable raises on fake providers; no live model calls."""
from __future__ import annotations

import contextlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from aicore.config import ConfigError

from orch import policies, settings
from orch.conductor import options
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import work_source
from orch.conductor.application import budget_service as budget
from tests.test_conductor import ConductorCase, FIXTURES, GREEN, ROLES, executor_ok


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
        """Both hard limits 0: an attempt without usage is a BUDGET_UNMETERED beacon only, as before (limits.unmetered
        acts only while a hard limit is in force)."""
        self.script({"executor": [dict(executor_ok("W1"), usage={})], "reviewer": [dict(GREEN, usage={})]})
        code, _, err = self.run_items("W1", extra=("--options", self.options_file(tokens_max=1)))
        self.assertEqual(code, 0, err)
        self.assertTrue(self.state(err)["items"]["W1"]["usage_incomplete"])
        self.assertTrue([line for line in self.lines(err) if line.get("reason_code") == "BUDGET_UNMETERED"])
        self.assertFalse([line for line in self.lines(err) if line.get("reason_code", "").startswith("TOKEN_BUDGET")])
        self.assertNotIn("charged", self.state(err)["items"]["W1"]["tokens"])

    def test_unmetered_usage_under_a_hard_limit_stops_and_a_resume_with_charge_goes_on(self):
        self.script({"executor": [dict(executor_ok("W1"), usage={})], "reviewer": [dict(GREEN, usage={})]})
        path = self.options_file(tokens_hard_max=1000000)
        code, _, err = self.run_items("W1", extra=("--options", path))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET_UNMETERED")), err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (1, 0))
        self.assertIn("limits.unmetered", self.state(err)["stop"]["message"])
        code, _, again = self.resume(err)  # the policy did not change: it stops again, no model is called
        self.assertEqual((code, self.outcome(again)), (1, ("stopped", "TOKEN_BUDGET_UNMETERED")), again)
        self.assertEqual(self.calls("executor"), 1)
        self.options_file(tokens_hard_max=1000000, unmetered="charge")  # the options file of the run is read again
        code, _, resumed = self.resume(err)
        self.assertEqual((code, self.outcome(resumed)), (0, ("finished", None)), resumed)
        self.assertEqual(self.calls("reviewer"), 1)

    def two_pieces(self, **limits):
        """W1's final attempt (its review) reports no usage; W2 follows."""
        self.set_items({ref: {} for ref in ("W1", "W2")})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [dict(GREEN, usage={}), GREEN]})
        return self.run_items("W1", "W2", extra=("--options", self.options_file(**limits), "--no-batch"))

    def test_unknown_usage_of_an_earlier_piece_stops_the_next_one_under_a_run_wide_limit(self):
        code, _, err = self.two_pieces(run_tokens_hard_max=1000000)
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET_UNMETERED")), err)
        self.assertEqual(self.calls("executor"), 1)  # W2 never reached its provider
        self.assertEqual(self.state(err)["usage_unmetered"], ["W1"])
        self.assertNotIn("W2", self.state(err)["items"])
        self.assertIn("W1", self.state(err)["stop"]["message"])
        code, _, again = self.resume(err)  # the run keeps the unknown usage: a resume stops again before any model call
        self.assertEqual((code, self.outcome(again)), (1, ("stopped", "TOKEN_BUDGET_UNMETERED")), again)
        self.assertEqual(self.calls("executor"), 1)
        self.options_file(run_tokens_hard_max=1000000, unmetered="charge")
        code, _, resumed = self.resume(err)
        self.assertEqual((code, self.outcome(resumed)), (0, ("finished", None)), resumed)
        self.assertEqual(self.calls("executor"), 2)

    def test_a_charged_attempt_is_accounted_and_does_not_enter_the_run_wide_unknown(self):
        code, _, err = self.two_pieces(run_tokens_hard_max=1000000, unmetered="charge")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("usage_unmetered", self.state(err))
        self.assertGreaterEqual(self.state(err)["tokens"]["charged"], 50000)

    def test_charge_counts_a_fixed_amount_per_attempt_without_usage_and_admission_sees_the_sum(self):
        self.script({"executor": [{"exit": 1, "stderr": "boom", "usage": {}}, dict(executor_ok("W1"), usage={})],
                     "reviewer": [GREEN]})
        path = self.options_file(tokens_hard_max=90000, unmetered="charge", unmetered_charge_tokens=50000)
        code, _, err = self.run_items("W1", extra=("--options", path))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        self.assertEqual(self.calls("executor"), 2)  # 50000 < 90000 admitted the second attempt; 100000 stops the next call
        item = self.state(err)["items"]["W1"]
        self.assertEqual((item["tokens"]["input"], item["tokens"]["charged"]), (100000, 100000))
        self.assertEqual(self.state(err)["tokens"]["charged"], 100000)
        self.assertEqual(self.calls("reviewer"), 0)

    def test_a_replayed_receipt_is_charged_once_and_no_hard_limit_charges_nothing(self):
        item = Item("W1", "source-run", {}, Path(), {})
        item.options = {"limits": {"tokens_hard_max": 90000, "unmetered": "charge", "unmetered_charge_tokens": 7}}
        owner = SimpleNamespace(state={}, run_doc={}, _step_tokens={"input": 0, "output": 0}, _save=mock.Mock(),
                                store=SimpleNamespace(mutating=contextlib.nullcontext))
        for _ in range(2):
            budget.charge_unmetered(owner, item, "streams/executor.jsonl")
        budget.charge_unmetered(owner, item, "streams/executor-a2.jsonl")
        self.assertEqual((item.state["tokens"], owner.state["tokens"]["charged"], owner._step_tokens["input"]),
                         ({"input": 14, "output": 0, "charged": 14}, 14, 14))
        item.options["limits"]["tokens_hard_max"] = 0
        budget.charge_unmetered(owner, item, "streams/other.jsonl")
        self.assertEqual(item.state["tokens"]["input"], 14)

    def test_repair_does_not_start_after_the_limit_is_reached(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES + ("report-fixer",)})
        self.script({"executor": [{"text": "no block here", "usage": {"input_tokens": 110}}],
                     "report-fixer": [{"result": executor_ok("W1")["result"], "tag": "stage-report"}]})
        code, _, err = self.run_items("W1", extra=("--options", self.options_file(tokens_hard_max=110)))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        self.assertEqual((self.calls("executor"), self.calls("report-fixer")), (1, 0))

    def run_with_policy(self, **budgets):
        """A run of W1 under the ``full`` policy with these ``budgets`` (a fixture policy: the pack on disk is not edited)."""
        real = policies.load

        def load(policy_id, *args, **kwargs):
            found = real(policy_id, *args, **kwargs)
            return {**found, "budgets": {**found.get("budgets", {}), **budgets}}
        with mock.patch.object(policies, "load", load):
            return self.run_items("W1")

    def test_stage_tokens_max_stops_the_repeat_of_a_step_that_already_spent_it(self):
        self.script({"executor": [{"exit": 1, "stderr": "boom", "usage": {"input_tokens": 120}}, executor_ok("W1")],
                     "reviewer": [GREEN]})
        code, _, err = self.run_with_policy(stage_tokens_max=100)
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        self.assertEqual(self.calls("executor"), 1)
        self.assertIn("budgets.stage_tokens_max 100", self.state(err)["stop"]["message"])
        self.assertIn("executor.1", self.state(err)["stop"]["message"])

    def test_stage_tokens_max_not_reached_stops_nothing(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_with_policy(stage_tokens_max=1000)
        self.assertEqual(code, 0, err)

    def test_a_brief_over_brief_max_bytes_stops_before_the_first_role(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_with_policy(brief_max_bytes=10)
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "BRIEF_TOO_LARGE")), err)
        self.assertEqual((self.calls("context-scout"), self.calls("executor")), (0, 0))
        self.assertRegex(self.state(err)["stop"]["message"], r"W1: execution-input is \d+ bytes > budgets.brief_max_bytes 10")

    def test_the_full_policy_takes_a_brief_with_a_300_kb_context_pack(self):
        loaded = policies.load("full", settings.load(project=self.project), warn=lambda message: None)
        self.assertEqual(loaded["budgets"]["brief_max_bytes"], 1048576)
        item = Item("W1", "r", {}, Path("."), {})
        item.policy = loaded
        item.input_doc = {"digest": "d", "context_pack": {"content": "x" * 300 * 1024}}
        work_source.check_brief_size(item)  # no Stop
        item.policy = {**loaded, "budgets": {"brief_max_bytes": 1000}}
        with self.assertRaises(Stop) as caught:
            work_source.check_brief_size(item)
        self.assertEqual(caught.exception.code, "BRIEF_TOO_LARGE")
        item.policy = {}
        work_source.check_brief_size(item)  # a policy without budgets has no limit

    def test_run_cap_cannot_come_from_the_environment(self):
        with mock.patch.dict("os.environ", {"SKM_ORCH_CONDUCTOR__LIMITS__RUN_TOKENS_HARD_MAX": "110"}):
            with self.assertRaises(ConfigError) as caught:
                settings.load(project=self.project)
        self.assertIn("CONFIG_LAYER_FORBIDDEN", str(caught.exception))

    def test_a_failed_attempt_is_a_hard_admission_boundary(self):
        """I10: admission runs before every provider call, so the repeat of a failed attempt that reached the limit does
        not start (it did before P3.4, when only the stage boundary was checked)."""
        self.script({"executor": [{"exit": 1, "stderr": "boom", "usage": {"input_tokens": 110}}, executor_ok("W1")],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--options", self.options_file(tokens_hard_max=110)))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        self.assertEqual(self.calls("executor"), 1)
        self.assertEqual(self.state(err)["items"]["W1"]["steps"]["executor.1"]["status"], "stopped")

    def test_a_model_step_is_denied_before_the_started_record_or_call(self):
        from orch.conductor import engine
        owner = engine.Conductor(project=self.project, settings=settings.load(project=self.project))
        owner.state = {"tokens": {"input": 110}}
        owner.run_id = "R"
        owner.store = SimpleNamespace(mutating=contextlib.nullcontext)  # no run folder here: the lock is not under test
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

    def owner(self, **state):
        import threading
        saved = []
        owner = SimpleNamespace(state={"tokens": {"input": 10, "output": 1}, **state}, run_doc={}, run_id="R",
                                store=SimpleNamespace(mutating=threading.RLock), _save=lambda: saved.append(1),
                                progress=SimpleNamespace(emit=lambda *args, **kwargs: None), saved=saved)
        return owner

    def piece(self, ref, **limits):
        item = Item(ref, "source-run", {}, Path(), {})
        item.options = {"limits": limits}
        return item

    def test_an_unmetered_attempt_of_one_piece_stops_every_later_admission_under_a_run_wide_limit(self):
        owner = self.owner()
        first, second = self.piece("A", run_tokens_hard_max=1000), self.piece("B", run_tokens_hard_max=1000)
        budget.unmetered(owner, first, "attempt-1")  # A's final attempt reported no usage
        self.assertEqual(owner.state["usage_unmetered"], ["A"])
        self.assertTrue(owner.saved)
        self.assertNotIn("usage_incomplete", second.state)
        for scope in ("all", "attempt"):
            with self.subTest(scope=scope), self.assertRaises(Stop) as caught:
                budget.admit(owner, second, scope)
            self.assertEqual(caught.exception.code, "TOKEN_BUDGET_UNMETERED")
            self.assertIn("A:", caught.exception.message)
        budget.admit(owner, second, "item")  # the piece and run scopes ask only for the tokens they count
        budget.admit(owner, second, "run")

    def test_the_run_wide_unknown_is_not_consulted_without_a_run_limit_or_under_charge(self):
        owner = self.owner(usage_unmetered=["A"])
        budget.admit(owner, self.piece("B", tokens_hard_max=1000))  # a piece limit alone: B owes nothing to A's attempt
        budget.admit(owner, self.piece("B"))
        owner.run_doc = {"limits_run": {"run_tokens_hard_max": {"value": 1000}}}
        budget.admit(owner, self.piece("B", unmetered="charge"))  # charge: the caller accounts for what it cannot see
        with self.assertRaises(Stop):
            budget.admit(owner, self.piece("B"))

    def test_the_unknown_of_the_run_is_recorded_once_and_a_charged_attempt_is_not_unknown(self):
        owner = self.owner()
        piece = self.piece("A", run_tokens_hard_max=1000)
        budget.unmetered(owner, piece, "a1")
        budget.unmetered(owner, piece, "a2")
        self.assertEqual(owner.state["usage_unmetered"], ["A"])
        owner = self.owner()
        charging = self.piece("C", run_tokens_hard_max=1000, unmetered="charge")
        charging.state["tokens"] = {"input": 0, "output": 0}
        budget.unmetered(owner, charging, "c1")
        self.assertNotIn("usage_unmetered", owner.state)
        self.assertEqual(owner.state["tokens"]["charged"], budget.DEFAULT_CHARGE)

    def test_soft_and_hard_limits_validate_after_layers_merge(self):
        with self.assertRaises(options.OptionsError) as caught:
            options.effective({"limits": {"tokens_max": 200}}, {},
                              [{"source": "item:W1", "options": {"limits": {"tokens_hard_max": 100}}}])
        self.assertEqual(caught.exception.code, "OPTIONS_INVALID")


if __name__ == "__main__":
    unittest.main()
