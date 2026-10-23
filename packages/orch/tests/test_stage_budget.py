"""Durable per-step stage budgets: a logical step keeps its known fresh usage across resume, retry, repair and
fallback, and overlapping steps do not share a counter or a label."""
from __future__ import annotations

import json
import threading
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from orch import policies, settings
from orch.conductor import agents, engine, process
from orch.conductor.application import review_plan
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import roles
from orch.conductor.infrastructure.files import RunStore
from orch.conductor.application import budget_service as budget
from tests.test_conductor import FIXTURES, GREEN, ROLES, ConductorCase, executor_ok
import sys


def _bind(owner):
    owner._bind_stage = lambda item, key: budget.bind_stage(owner, item, key)
    owner._restore_stage = budget.restore_stage
    owner._stage_bucket = lambda: budget.stage_bucket(owner)
    owner._stage_key = lambda: budget.stage_key(owner)
    owner._remember_stage = lambda item, bucket: budget.remember_stage(owner, item, bucket)
    owner._stage_slots = {}
    owner._local = threading.local()
    owner._step_tokens = {"input": 0, "output": 0}
    owner._current_step = None


class StageBudgetRunTests(ConductorCase):
    def run_with_policy(self, **budgets):
        real = policies.load

        def load(policy_id, *args, **kwargs):
            found = real(policy_id, *args, **kwargs)
            return {**found, "budgets": {**found.get("budgets", {}), **budgets}}

        with mock.patch.object(policies, "load", load):
            return self.run_items("W1")

    def test_an_interrupted_step_does_not_admit_another_call_on_resume(self):
        self.script({"executor": [{"exit": 1, "stderr": "boom", "usage": {"input_tokens": 5}}, executor_ok("W1")],
                     "reviewer": [GREEN]})
        real = policies.load

        def load(policy_id, *args, **kwargs):
            found = real(policy_id, *args, **kwargs)
            return {**found, "budgets": {**found.get("budgets", {}), "stage_tokens_max": 4}}

        with mock.patch.object(policies, "load", load):
            code, _, err = self.run_items("W1")
            self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
            self.assertEqual(self.calls("executor"), 1)
            self.assertIn("executor.1", self.state(err)["stop"]["message"])
            self.assertGreaterEqual(self.state(err)["items"]["W1"]["stage_usage"]["executor.1"]["input"], 5)
            code, _, again = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")
        self.assertEqual((code, self.outcome(again)), (1, ("stopped", "TOKEN_BUDGET")), again)
        self.assertEqual(self.calls("executor"), 1)

    def test_a_repair_of_the_same_stage_cannot_reset_the_stage_budget(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role]
                           for role in ROLES + ("report-fixer",)})
        self.script({"executor": [{"text": "no block here", "usage": {"input_tokens": 50}}],
                     "report-fixer": [{"result": executor_ok("W1")["result"], "tag": "stage-report"}]})
        code, _, err = self.run_with_policy(stage_tokens_max=40)
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TOKEN_BUDGET")), err)
        self.assertEqual((self.calls("executor"), self.calls("report-fixer")), (1, 0))

    def test_stage_cap_zero_does_not_stop_a_call(self):
        self.script({"executor": [dict(executor_ok("W1"), usage={"input_tokens": 100000})], "reviewer": [GREEN]})
        code, _, err = self.run_with_policy(stage_tokens_max=0)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 1)


class StageSlotTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.item = Item("W1", "run-1", {}, self.root / "item", {})
        self.item.directory.mkdir()
        self.item.options = {"limits": {}}
        self.item.policy = {"budgets": {"stage_tokens_max": 4}}
        self.state = {"items": {"W1": self.item.state}, "tokens": {"input": 0, "output": 0}}
        self.owner = mock.Mock()
        self.owner.state = self.state
        self.owner.run_doc = {}
        self.owner.run_id = "cnd-stage"
        store = RunStore(self.root, "cnd-stage")
        store.create({"run_id": "cnd-stage"})
        store.save(self.state)
        self.owner.store = store
        self.owner._save = lambda: store.save(self.state)
        self.owner.progress = mock.Mock()
        _bind(self.owner)

    def add(self, usage, attempt, complete=True):
        roles.add_tokens(self.owner, self.item, usage, usage_complete=complete, attempt=attempt)

    def test_cold_receipt_recovery_and_slot_publication_hold_the_store_lock(self):
        from tests.test_run_store_lock import CountingLock
        lock = self.owner.store.lock = CountingLock()
        case = self

        class Guarded(dict):
            def values(self):
                case.assertTrue(lock.owned(), "cold receipt read outside I2")
                return super().values()

            def __setitem__(self, key, value):
                case.assertTrue(lock.owned(), "stage publication outside I2")
                super().__setitem__(key, value)

        self.item.state["usage_by_agent"] = Guarded({
            "agent-1": {"attempt-1": {"step": "executor.1", "input": 5, "output": 2}}})
        self.item.state = Guarded(self.item.state)
        self.owner._stage_slots = Guarded()
        budget.bind_stage(self.owner, self.item, "executor.1")
        self.assertEqual(self.item.state["stage_usage"]["executor.1"], {"input": 5, "cached": 0, "output": 2})
        self.assertIs(self.owner._stage_slots[(self.item.ref, "executor.1")],
                      self.item.state["stage_usage"]["executor.1"])

    def test_rebind_keeps_retry_repair_and_fallback_on_the_same_stage(self):
        budget.bind_stage(self.owner, self.item, "executor.1")
        self.add({"input": 5, "output": 0}, "streams/executor.1.jsonl")
        budget.bind_stage(self.owner, self.item, "executor.1")  # resume, or the same step's next attempt
        with self.assertRaises(Stop) as caught:
            budget.admit(self.owner, self.item, "attempt")
        self.assertIn("executor.1", caught.exception.message)
        self.assertIn("stage_tokens_max 4", caught.exception.message)
        budget.bind_stage(self.owner, self.item, "executor.2")
        budget.admit(self.owner, self.item, "attempt")  # a new logical step starts at zero
        self.assertEqual(self.item.state["stage_usage"]["executor.1"]["input"], 5)
        self.assertEqual(int(budget.stage_bucket(self.owner).get("input", 0)), 0)

    def test_cap_zero_and_a_missing_budget_do_not_apply(self):
        budget.bind_stage(self.owner, self.item, "executor.1")
        self.add({"input": 50, "output": 0}, "streams/executor.1.jsonl")
        for policy in ({"budgets": {"stage_tokens_max": 0}}, {}, {"budgets": {}}):
            self.item.policy = policy
            budget.admit(self.owner, self.item, "attempt")

    def test_overlapping_steps_keep_separate_amounts_and_labels(self):
        self.item.policy = {"budgets": {"stage_tokens_max": 4}}
        budget.bind_stage(self.owner, self.item, "checks.1")
        budget.bind_stage(self.owner, self.item, "review.1")
        gate = threading.Barrier(2)
        seen = {}
        failures = []

        def work(step, amount):
            try:
                budget.bind_stage(self.owner, self.item, step)
                gate.wait(5)
                roles.add_tokens(self.owner, self.item, {"input": amount, "output": 0}, usage_complete=True,
                                 attempt=f"streams/{step}.jsonl")
                gate.wait(5)
                try:
                    budget.admit(self.owner, self.item, "attempt")
                    refused = None
                except Stop as stop:
                    refused = stop.message
                seen[step] = (budget.stage_key(self.owner), budget.stage_bucket(self.owner).get("input"), refused)
            except Exception as error:  # noqa: BLE001 — reported once the threads join
                failures.append(error)
                gate.abort()

        threads = [threading.Thread(target=work, args=args) for args in (("checks.1", 3), ("review.1", 7))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertEqual(failures, [])
        self.assertEqual(seen["checks.1"][0], "checks.1")
        self.assertEqual(seen["review.1"][0], "review.1")
        self.assertEqual(seen["checks.1"][1], 3)
        self.assertEqual(seen["review.1"][1], 7)
        self.assertIsNone(seen["checks.1"][2])
        self.assertIn("review.1", seen["review.1"][2])
        self.assertNotIn("checks.1", seen["review.1"][2])
        self.assertEqual(self.state["tokens"]["input"], 10)

    def test_replaying_a_receipt_does_not_double_count(self):
        agents.start(self.item.directory, "agent-1", role="executor", route={"provider": "codex"}, step="executor.1",
                     attempt=1, prompt="prompt.md", parent=None, started_at="2026-10-20T00:00:00Z")
        self.owner._local.agent = {"id": "agent-1", "usage": {"input": 0, "cached": 0, "output": 0}}
        budget.bind_stage(self.owner, self.item, "executor.1")
        usage = {"input": 5, "cached": 1, "output": 2}
        self.add(usage, "streams/executor.1.jsonl")
        self.add(usage, "streams/executor.1.jsonl")
        self.assertEqual(self.item.state["stage_usage"]["executor.1"]["input"], 5)
        self.add({"input": 8, "cached": 1, "output": 2}, "streams/executor.1.jsonl")
        self.assertEqual(self.item.state["stage_usage"]["executor.1"]["input"], 8)
        saved = json.loads(json.dumps(self.state))
        self.owner.state = saved
        self.item.state = saved["items"]["W1"]
        self.owner._stage_slots = {}
        budget.bind_stage(self.owner, self.item, "executor.1")
        self.owner._local.agent = {"id": "agent-1", "usage": {"input": 0, "cached": 0, "output": 0}}
        budget.bind_stage(self.owner, self.item, "executor.1")
        self.add({"input": 8, "cached": 1, "output": 2}, "streams/executor.1.jsonl")
        self.assertEqual(self.item.state["stage_usage"]["executor.1"]["input"], 8)
        self.assertEqual(saved["tokens"]["input"], 8)

    def test_group_review_and_strategist_use_their_own_stage(self):
        project = self.root / "project"
        project.mkdir()
        cond = engine.Conductor(project=project, settings=settings.load(project=project), mode="quiet")
        store = RunStore(project, "cnd-stage")
        store.create({"run_id": "cnd-stage", "items": ["W1"]})
        state = {"status": "running", "items": {"W1": {"steps": {}}}, "tokens": {"input": 0, "output": 0}}
        cond._open("cnd-stage", {"run_id": "cnd-stage", "items": ["W1"]}, state, store)
        directory = store.directory / "W1"
        item = Item("W1", "cnd-stage", state["items"]["W1"], directory, {})
        item.options = {"limits": {}, "stages": []}
        item.policy = {"budgets": {"stage_tokens_max": 100}}
        budget.bind_stage(cond, item, "executor.1")
        route = {"provider": "codex", "model": "m", "effort": "low", "model_class": "economy", "transport": "text",
                 "argv": ["fake"]}
        cond._role_argv = lambda *args, **kwargs: ["fake"]
        cond._role_env = lambda *args, **kwargs: {}
        raw = directory / "streams" / "group.jsonl"

        def run_of(amount):
            return process.RoleRun(exit=0, duration_s=0.1, usage={"input": amount, "cached": 0, "output": 1},
                                   usage_complete=True, text="ok")

        with mock.patch.object(process, "run_role", return_value=run_of(9)):
            review_plan.run_agent(cond, item, "group-review-1", "reviewer", route, "prompt", raw, 30)
        self.assertEqual(budget.stage_key(cond), "executor.1")
        self.assertEqual(int(budget.stage_bucket(cond).get("input", 0)), 0)
        self.assertEqual(item.state["stage_usage"]["group-review-1"]["input"], 9)
        self.assertNotIn("executor.1", item.state["stage_usage"])
        raw = directory / "streams" / "strategist.txt"
        with mock.patch.object(process, "run_role", return_value=run_of(4)):
            review_plan.run_agent(cond, item, "review-strategist", "triager", route, "prompt", raw, 30)
        self.assertEqual(budget.stage_key(cond), "executor.1")
        self.assertEqual(item.state["stage_usage"]["review-strategist"]["input"], 4)
        self.assertEqual(item.state["stage_usage"]["group-review-1"]["input"], 9)


if __name__ == "__main__":
    unittest.main()
