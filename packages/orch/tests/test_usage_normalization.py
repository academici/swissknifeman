"""Provider-shaped usage, completeness of model attempts and replay-safe accounting."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import threading
import contextlib
from types import SimpleNamespace
import unittest
from unittest import mock

from orch.conductor import agents, process
from orch.conductor.application import review_plan
from orch.conductor.domain.item import Item
from orch.conductor.infrastructure import roles
from orch.conductor.policies import budget
from tests.test_conductor import ConductorCase, FIXTURES, GREEN, ROLES, executor_ok, report

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
ZERO = {"input": 0, "cached": 0, "output": 0}


class UsageNormalizationTests(unittest.TestCase):
    def test_three_provider_shapes(self):
        for provider, expected in (
                ("claude", {"input": 1200, "cached": 9000, "output": 100}),
                ("grok", {"input": 180608, "cached": 2912768, "output": 82166}),
                ("codex", {"input": 1000, "cached": 9000, "output": 100})):
            with self.subTest(provider=provider):
                data = (FIXTURE_DIR / "usage" / (provider + ".jsonl")).read_text(encoding="utf-8")
                parsed = process.parse_stream("jsonl", data)
                self.assertEqual(parsed["usage"], expected)
                self.assertIs(parsed["usage_complete"], True)
                self.assertEqual(process.parse_stream("jsonl", data), parsed)

    def test_grok_fixture_is_the_result_of_the_recorded_stream(self):
        stream = (FIXTURE_DIR / "grok/streaming-messages-json.jsonl").read_text(encoding="utf-8")
        result = next(json.loads(line) for line in stream.splitlines() if json.loads(line).get("type") == "result")
        self.assertEqual(json.loads((FIXTURE_DIR / "usage/grok.jsonl").read_text()), result)

    def test_invalid_counts_are_ignored_for_every_field(self):
        for field in ("input_tokens", "cached_input_tokens", "cache_read_input_tokens",
                      "cache_creation_input_tokens", "output_tokens"):
            for invalid in (-1, True, False, 1.5, "100", None, [], {}):
                with self.subTest(field=field, invalid=invalid):
                    self.assertEqual(process._usage({field: invalid}), ZERO)
        for invalid in (None, [], "usage", 5):
            self.assertEqual(process._usage(invalid), ZERO)

    def test_valid_counts_survive_invalid_neighbors(self):
        self.assertEqual(process._usage({"input_tokens": -1, "cache_creation_input_tokens": 7,
                                         "cache_read_input_tokens": 8, "output_tokens": True}),
                         {"input": 7, "cached": 8, "output": 0})
        self.assertEqual(process._usage({"input_tokens": True, "cached_input_tokens": 8, "output_tokens": 2}),
                         {"input": 0, "cached": 8, "output": 2})

    def test_codex_shape_subtracts_only_its_cache_and_clamps_at_zero(self):
        for total, cached, fresh in ((10000, 9000, 1000), (5, 8, 0), (5, 0, 5)):
            with self.subTest(total=total, cached=cached):
                self.assertEqual(process._usage({"input_tokens": total, "cached_input_tokens": cached,
                                                 "cache_creation_input_tokens": 500,
                                                 "cache_read_input_tokens": 700, "output_tokens": 3}),
                                 {"input": fresh, "cached": cached, "output": 3})

    def test_invalid_codex_cache_uses_the_claude_grok_shape(self):
        for cached in (True, False, 1.5, "9000", None):
            with self.subTest(cached=cached):
                self.assertEqual(process._usage({"input_tokens": 5, "cached_input_tokens": cached,
                                                 "cache_creation_input_tokens": 2,
                                                 "cache_read_input_tokens": 8, "output_tokens": 3}),
                                 {"input": 7, "cached": 8, "output": 3})

    def test_negative_integer_cache_identifies_codex_but_does_not_count(self):
        self.assertEqual(process._usage({"input_tokens": 5, "cached_input_tokens": -1,
                                         "cache_creation_input_tokens": 2, "cache_read_input_tokens": 8,
                                         "output_tokens": 3}), {"input": 5, "cached": 0, "output": 3})

    def test_codex_turns_are_normalized_before_they_are_summed(self):
        stream = '\n'.join(json.dumps({"type": "turn.completed", "usage": usage}) for usage in (
            {"input_tokens": 10000, "cached_input_tokens": 9000, "output_tokens": 100},
            {"input_tokens": 15000, "cached_input_tokens": 12000, "output_tokens": 200}))
        parsed = process.parse_stream("jsonl", stream)
        self.assertEqual(parsed["usage"], {"input": 4000, "cached": 21000, "output": 300})
        self.assertIs(parsed["usage_complete"], True)

    def test_missing_malformed_or_zero_terminal_usage_is_incomplete(self):
        for kind in ("result", "turn.completed"):
            for usage in (None, {}, [], {"input_tokens": 0, "output_tokens": 0},
                          {"input_tokens": True, "output_tokens": -3},
                          {"input_tokens": 100, "cached_input_tokens": 100, "output_tokens": 0}):
                with self.subTest(kind=kind, usage=usage):
                    parsed = process.parse_stream("jsonl", json.dumps({"type": kind, "usage": usage}))
                    self.assertIs(parsed["usage_complete"], False)
        self.assertIs(process.parse_stream("jsonl", '{"type":"thread.started"}')["usage_complete"], False)
        self.assertIsNone(process.parse_stream("text", "scout map")["usage_complete"])


class UsageAccountingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.item = Item("W1", "run-1", {}, Path(tmp.name), {})
        self.state = {"items": {"W1": self.item.state}}
        self.engine = SimpleNamespace(state=self.state, _local=threading.local(), _step_tokens={},
                                      _save=mock.Mock(), progress=SimpleNamespace(emit=mock.Mock()),
                                      store=SimpleNamespace(mutating=contextlib.nullcontext))
        self.engine._unmetered = lambda item: budget.unmetered(self.engine, item)  # bound on the Conductor
        self.start_agent("agent-1")

    def start_agent(self, agent):
        self.engine._local.agent = agents.start(
            self.item.directory, agent, role="executor", route={}, step="executor.1", attempt=1,
            prompt="prompt.md", parent=None, started_at="2026-10-20T00:00:00Z")

    def add(self, usage, complete=True, attempt=None):
        roles.add_tokens(self.engine, self.item, usage, usage_complete=complete, attempt=attempt)

    def test_same_agent_receipt_does_not_add_tokens_twice_after_state_reload(self):
        usage = {"input": 1000, "cached": 9000, "output": 100}
        self.add(usage)
        before = copy.deepcopy(self.state)
        self.add(usage)
        self.assertEqual(self.state, before)
        self.assertEqual(self.engine._step_tokens, usage)
        # A fresh handle reconstructed for a replay still sees the persisted agent id.
        self.state = json.loads(json.dumps(self.state))
        self.engine.state = self.state
        self.item.state = self.state["items"]["W1"]
        self.engine._step_tokens = {}
        self.start_agent("agent-1")
        self.add(usage)
        self.assertEqual(self.state, before)
        self.assertEqual(self.engine._step_tokens, ZERO)
        self.assertEqual(self.engine._local.agent["usage"], usage)

    def test_retries_of_one_agent_and_other_agents_each_count_once(self):
        usage = {"input": 10, "cached": 90, "output": 1}
        self.add(usage, attempt="streams/executor.1.jsonl")
        self.add(usage, attempt="streams/executor.1-a2.jsonl")
        self.add(usage, attempt="streams/executor.1-a2.jsonl")
        self.assertEqual(self.engine._local.agent["usage"], {"input": 20, "cached": 180, "output": 2})
        self.start_agent("agent-2")
        self.add(usage)
        for bucket in (self.state["tokens"], self.item.state["tokens"], self.engine._step_tokens):
            self.assertEqual(bucket, {"input": 30, "cached": 270, "output": 3})

    def test_later_read_of_a_growing_stream_replaces_its_previous_usage(self):
        self.add({"input": 10, "cached": 90, "output": 1}, False, "stream.jsonl")
        self.add({"input": 100, "cached": 900, "output": 10}, True, "stream.jsonl")
        self.assertEqual(self.state["tokens"], {"input": 100, "cached": 900, "output": 10})
        self.assertTrue(self.item.state["usage_incomplete"])
        self.assertEqual(self.engine.progress.emit.call_count, 1)

    def test_incomplete_attempt_is_sticky_and_emits_info_once(self):
        self.add(ZERO, False, "first.jsonl")
        self.add(ZERO, False, "first.jsonl")
        self.add({"input": 1}, True, "second.jsonl")
        self.state = json.loads(json.dumps(self.state))
        self.engine.state = self.state
        self.item.state = self.state["items"]["W1"]
        self.start_agent("agent-1")
        self.add(ZERO, False, "first.jsonl")
        self.assertIs(self.engine._local.agent["usage_complete"], False)
        self.start_agent("agent-2")
        self.add(ZERO, False)
        self.assertIs(self.item.state["usage_incomplete"], True)
        self.assertIs(self.engine._local.agent["usage_complete"], False)
        self.engine.progress.emit.assert_called_once_with(
            "info", item="W1", reason_code="BUDGET_UNMETERED",
            message="W1: a model attempt reported no usage; token limits cannot see it")

    def test_agent_usage_file_aggregates_completeness_without_changing_token_keys(self):
        self.add(ZERO, False, "failed.jsonl")
        self.add({"input": 10, "output": 2}, True, "success.jsonl")
        handle = self.engine._local.agent
        agents.finish(handle, exit_code=0, error=None, decisions=[], duration_s=1, stream="success.jsonl", lingered=False)
        self.assertEqual(json.loads((handle["directory"] / "usage.json").read_text()),
                         {"input": 10, "cached": 0, "output": 2, "usage_complete": False})
        self.assertEqual(self.engine._step_tokens, {"input": 10, "cached": 0, "output": 2})

    def test_text_transport_is_unmetered_without_marking_the_item_incomplete(self):
        self.add(ZERO, None)
        self.assertIsNone(self.engine._local.agent["usage_complete"])
        self.assertNotIn("usage_incomplete", self.item.state)
        self.engine.progress.emit.assert_not_called()

    def test_batch_agent_records_completeness_outside_a_step(self):
        handle = self.engine._local.agent
        self.engine.project = self.item.directory
        self.engine._agent_start = mock.Mock(return_value=handle)
        self.engine._agent_end = mock.Mock()
        self.engine._role_argv = mock.Mock(return_value=["fake"])
        self.engine._role_env = mock.Mock(return_value={})
        self.engine._relative = str
        self.engine._tokens = lambda item, usage, **kw: roles.add_tokens(self.engine, item, usage, **kw)
        run = process.RoleRun(exit=0, duration_s=1, usage_complete=False)
        with mock.patch.object(process, "run_role", return_value=run):
            review_plan.run_agent(self.engine, self.item, "review-strategist", "triager",
                                  {"transport": "jsonl", "provider": "fake"}, "prompt", self.item.directory / "raw", 30)
        self.assertTrue(self.item.state["usage_incomplete"])
        self.assertIs(handle["usage_complete"], False)


class UsageConductorTests(ConductorCase):
    def agent_usage(self, err):
        return {json.loads((path.parent / "request.json").read_text())["role"]: json.loads(path.read_text())
                for path in (self.run_dir(err) / "W1" / agents.AGENTS).glob("*/usage.json")}

    def test_zero_usage_marks_the_item_once_and_keeps_scout_null(self):
        self.script({"executor": [dict(executor_ok("W1"), usage={})], "reviewer": [dict(GREEN, usage={})]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIs(self.state(err)["items"]["W1"]["usage_incomplete"], True)
        self.assertEqual([(line["event"], line["message"]) for line in self.lines(err)
                          if line.get("reason_code") == "BUDGET_UNMETERED"],
                         [("info", "W1: a model attempt reported no usage; token limits cannot see it")])
        found = self.agent_usage(err)
        self.assertIsNone(found["context-scout"]["usage_complete"])
        self.assertIs(found["executor"]["usage_complete"], False)
        self.assertIs(found["reviewer"]["usage_complete"], False)

    def test_jsonl_without_a_terminal_result_marks_the_item_before_failure(self):
        import sys
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        argv["executor"] = [sys.executable, "-c", "import sys; sys.stdin.read(); print('{\"type\":\"thread.started\"}')"]
        self.write_config(argv)
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.assertTrue(self.state(err)["items"]["W1"]["usage_incomplete"])
        self.assertEqual(len([line for line in self.lines(err) if line.get("reason_code") == "BUDGET_UNMETERED"]), 1)
        self.assertIs(self.agent_usage(err)["executor"]["usage_complete"], False)

    def test_failed_attempt_followed_by_success_preserves_incompleteness_and_counts_the_retry(self):
        self.script({"executor": [{"exit": 1, "stderr": "boom", "usage": {}}, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        state = self.state(err)
        self.assertEqual(state["items"]["W1"]["steps"]["executor.1"]["tokens"]["input"], 100)
        self.assertEqual(state["tokens"]["input"], 200)
        self.assertIs(self.agent_usage(err)["executor"]["usage_complete"], False)

    def test_measured_roles_and_text_scout_do_not_emit_unmetered(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("usage_incomplete", self.state(err)["items"]["W1"])
        self.assertFalse([line for line in self.lines(err) if line.get("reason_code") == "BUDGET_UNMETERED"])

    def test_codex_cache_does_not_trigger_a_false_budget_beacon(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"limits": {"tokens_max": 1500}}}]}})
        self.script({"executor": [dict(executor_ok("W1"), usage={"input_tokens": 10000,
                                                                  "cached_input_tokens": 9000,
                                                                  "output_tokens": 100})], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.state(err)["tokens"], {"input": 1100, "cached": 9000, "output": 110})
        self.assertFalse([line for line in self.lines(err) if line.get("reason_code") == "BUDGET_OVER"])

    def test_unmetered_report_fixer_is_counted_separately(self):
        import sys
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES + ("report-fixer",)})
        broken = {"write": {"out/W1.txt": "ok\n"},
                  # a duplicate path is a form error the fixer mends without changing the meaning (a string exit 'zero'
                  # healed to 0 is a change of a check row: REPAIR_SEMANTIC_DRIFT, P3.1)
                  "result": report("W1", changed_paths=["out/W1.txt", "out/W1.txt"])}
        self.script({"executor": [broken], "reviewer": [GREEN],
                     "report-fixer": [{"result": report("W1"), "tag": "stage-report", "usage": {}}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        found = self.agent_usage(err)
        self.assertIs(found["executor"]["usage_complete"], True)
        self.assertIs(found["report-fixer"]["usage_complete"], False)
        self.assertTrue(self.state(err)["items"]["W1"]["usage_incomplete"])


if __name__ == "__main__":
    unittest.main()
