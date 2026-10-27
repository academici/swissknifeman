"""Interrupted fresh-context metadata and physical launch admissions. No provider process/model is started."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from orch.conductor import agents, options, records
from orch.conductor.application import fresh_context, run_service
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock, launch_budget, roles
from orch.conductor.infrastructure.files import write_json
from orch.settings import ORCH_ROOT


class FreshContextTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.directory = self.root / "run"
        self.piece = self.directory / "W1"
        self.piece.mkdir(parents=True)
        self.options = copy.deepcopy(options.DEFAULTS)
        self.options.update(session={"executor": "per-item", "max_idle_s": 0}, fallback_routes=[])
        self.route = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}
        self.envelope = json.loads((ORCH_ROOT / "fixtures/conductor/v1/valid/authority-envelope/claude-executor.json").read_text())
        item = {"outcome": "stopped", "retried": "2026-01-01T00:00:00Z", "retries_used": 2,
                "stage_usage": {"executor.1": {"input": 100, "cached": 200, "output": 30}},
                "tokens": {"input": 100, "output": 30}, "usage_incomplete": True,
                "attempts": [{"n": 1, "retried_at": "2026-01-01T00:00:00Z", "steps": {"executor.1": {"role": "executor"}}}],
                "steps": {"brief": {"status": "done", "result": {"input_path": "old-input"}},
                          "prepare": {"status": "done", "result": {}},
                          "executor.1": {"status": "stopped", "code": "ROLE_FAILED", "ended": "2026-01-02T00:00:00Z"}}}
        self.owner = SimpleNamespace(directory=self.directory, run_doc={"run_id": "test", "items": ["W1"]},
                                     state={"status": "stopped", "agents": 8, "items": {"W1": item}, "claims": {},
                                            "tokens": {"input": 100, "output": 30}, "usage_unmetered": ["W1"]})
        lock = threading.RLock()
        self.owner.store = SimpleNamespace(mutating=lambda: lock,
                                          save_run=lambda doc: records.write(self.directory / "run.json", doc, "run"))
        self.owner._save = lambda: records.write(self.directory / "state.json", self.owner.state, "state")
        self.owner._tree_mark = lambda: "same-head-and-product-bytes"
        self.owner.progress = SimpleNamespace(emit=lambda *a, **k: None)
        self.owner._save()
        self.owner.store.save_run(self.owner.run_doc)
        records.write(self.piece / "options.json", {"options": self.options}, "item-options")
        write_json(self.piece / "input.json", {"old": "full canonical input"})
        (self.piece / "streams").mkdir()
        (self.piece / "streams/executor.1.jsonl").write_text("original stopped native stream\n")
        self.new_options = self.root / "new-options.json"
        self.new_options.write_text(json.dumps(records.options_layer({**self.options, "rules": ["fresh current canonical contract"]})))
        for number in range(1, 9):
            handle = agents.start(self.piece, f"agent-test-{number}", role="executor", route=self.route,
                                  step="executor.1", attempt=1 if number < 4 else 2, prompt="old", parent=None,
                                  started_at=f"2026-01-01T00:00:{number:02}Z")
            agents.write_authority(handle, 1 if number < 4 else 2, self.envelope)

    def prepare(self, ceiling=9):
        fresh_context.prepare(self.owner, ["W1"], self.new_options, ceiling)

    def current(self):
        return Item("W1", "workrun", self.owner.state["items"]["W1"], self.piece, {}, options=copy.deepcopy(self.options))

    def agent(self, number):
        handle = agents.start(self.piece, f"agent-test-{number}", role="executor", route=self.route,
                              step="executor.1", attempt=1, prompt="new", parent=None, started_at=clock.utc_now())
        self.owner.state["agents"] = max(self.owner.state["agents"], number)
        return handle

    def admission(self, item, handle, **changes):
        with self.owner.store.mutating():
            return launch_budget.record_launch(self.owner, item, handle, changes.get("role", "executor"),
                                              changes.get("route", self.route), changes.get("attempt", 1), self.envelope)

    def test_fresh_context_rebuilds_input_but_preserves_every_counter_and_unfinished_evidence(self):
        before = copy.deepcopy(self.owner.state)
        self.prepare()
        state = self.owner.state["items"]["W1"]
        self.assertEqual(state["steps"], {})
        self.assertEqual(state["stage_usage"], before["items"]["W1"]["stage_usage"])
        self.assertEqual(state["retries_used"], 2)
        self.assertTrue(state["usage_incomplete"])
        self.assertEqual(self.owner.state["usage_unmetered"], ["W1"])
        self.assertEqual(self.owner.state["agents"], 8)
        self.assertEqual(state["attempts"][0], before["items"]["W1"]["attempts"][0])
        original = state["attempts"][1]["steps"]["executor.1"]["original_step"]
        self.assertEqual(original, before["items"]["W1"]["steps"]["executor.1"])
        self.assertEqual((self.piece / "attempts/2/streams/executor.1.jsonl").read_text(), "original stopped native stream\n")
        snapshot = Path(self.owner.run_doc["options_file"])
        self.assertEqual(snapshot.read_bytes(), self.new_options.read_bytes())
        self.assertEqual(len(launch_budget.inventory(self.piece)["launches"]), 8)

    def test_ceiling_counts_eight_old_launches_and_refuses_a_tenth_without_process_start(self):
        self.prepare()
        item = self.current()
        self.admission(item, self.agent(9))
        with mock.patch.object(roles.process, "run_role") as process:
            with self.assertRaises(Stop) as caught:
                self.admission(item, self.agent(10))
            self.assertEqual(caught.exception.code, "MODEL_LAUNCH_CEILING")
            process.assert_not_called()
        self.assertEqual(len(launch_budget.inventory(self.piece, pending_since="2026-01-01")["launches"]), 9)

    def test_two_concurrent_admissions_cannot_overrun_the_physical_ceiling(self):
        self.prepare()
        item = self.current()
        handles = [self.agent(9), self.agent(10)]
        def start(handle):
            try:
                self.admission(item, handle)
                return "admitted"
            except Stop as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(start, handles)), ["admitted", "MODEL_LAUNCH_CEILING"])

    def test_route_stage_role_budget_candidate_and_history_changes_fail_closed(self):
        for kind in ("route", "stage", "role", "budget", "candidate", "history", "snapshot"):
            with self.subTest(kind=kind):
                # Each negative gets a separate isolated fixture and no provider call.
                fixture = FreshContextTests()
                fixture.setUp()
                try:
                    fixture.prepare()
                    item = fixture.current()
                    handle = fixture.agent(9)
                    args = {}
                    if kind == "route": args["route"] = {**fixture.route, "model": "fallback-model"}
                    if kind == "stage": handle["step"] = "executor.2"
                    if kind == "role": args["role"] = "report-fixer"
                    if kind == "budget": item.options["limits"]["retries"] += 1
                    if kind == "candidate": fixture.owner._tree_mark = lambda: "changed"
                    if kind == "snapshot": Path(fixture.owner.run_doc["options_file"]).write_text("{}")
                    if kind == "history": (fixture.piece / "agents/agent-test-1/request.json").unlink()
                    with self.assertRaises(Stop): fixture.admission(item, handle, **args)
                    self.assertFalse((handle["directory"] / "authority/a1.json").exists())
                finally:
                    fixture.doCleanups()

    def test_ambiguous_same_second_different_actor_fails_before_changes(self):
        path = self.piece / "agents/agent-test-1/request.json"
        request = records.read(path, "agent-request")
        request["role"] = "context-scout"
        request["step"] = "scout"
        request["started_at"] = "2026-01-01T00:00:08Z"
        records.write(path, request, "agent-request")
        with self.assertRaises(Stop) as caught:
            self.prepare()
        self.assertEqual(caught.exception.code, "FRESH_CONTEXT_NOT_INTERRUPTED")
        self.assertFalse((self.piece / "fresh-context").exists())

    def test_new_options_cannot_change_budgets_or_assignment_before_any_write(self):
        for key in ("limits", "stages"):
            proposed = copy.deepcopy(records.options_layer(self.options))
            proposed[key] = {**proposed[key], "retries": 99} if key == "limits" else [{"role": "executor", "model": "other"}]
            self.new_options.write_text(json.dumps(proposed))
            with self.assertRaises(Stop): self.prepare()
            self.assertFalse((self.piece / "fresh-context").exists())

    def test_plain_retry_still_keeps_its_idempotent_early_return(self):
        before = copy.deepcopy(self.owner.state)
        run_service.retry(self.owner, "W1")
        self.assertEqual(self.owner.state, before)

    def test_crash_after_state_save_recovers_the_frozen_options_pointer(self):
        self.prepare()
        expected = self.owner.run_doc["options_file"]
        self.owner.run_doc["options_file"] = "old"
        fresh_context.activate(self.owner)
        self.assertEqual(self.owner.run_doc["options_file"], expected)


from tests.test_conductor import ConductorCase, executor_ok


class FreshContextLifecycleTests(ConductorCase):
    scenario = "solo"

    def test_native_resume_preserves_physical_history_and_rebuilds_one_fresh_executor(self):
        options_path = self.project.parent / "initial-options.json"
        options_path.write_text(json.dumps({"session": {"executor": "per-item"}, "limits": {"retries": 0}, "fallback_routes": [], "stages": [{"role": "executor"}]}))
        self.script({"executor": [{"exit": 3}, executor_ok("W1")]})
        code, _, stopped = self.run_items("W1", extra=("--options", options_path))
        self.assertEqual((code, self.outcome(stopped)), (1, ("stopped", "ROLE_FAILED")), stopped)
        directory = self.run_dir(stopped)
        before = self.state(stopped)
        self.assertEqual(self.calls("executor"), 1)
        baseline = json.loads((directory / "W1" / "options.json").read_text())["options"]
        self.assertEqual(baseline.get("session", {}).get("executor"), "per-item", baseline)
        self.assertFalse(baseline.get("fallback_routes"), baseline)
        amended = records.options_layer({**baseline, "rules": ["fresh scoped instruction"]})
        next_options = self.project.parent / "fresh-options.json"
        next_options.write_text(json.dumps(amended))
        denied, _, denial = self.conduct("resume", "--run", directory.name, "--retry", "W1", "--fresh-context",
                                        "--options", next_options, "--model-launch-ceiling", "1", "--json-lines")
        self.assertEqual(denied, 1, denial)
        self.assertIn("MODEL_LAUNCH_CEILING", denial)
        self.assertEqual(self.calls("executor"), 1)
        code, _, resumed = self.conduct("resume", "--run", directory.name, "--retry", "W1", "--fresh-context",
                                        "--options", next_options, "--model-launch-ceiling", "2", "--json-lines")
        self.assertEqual(code, 0, resumed)
        self.assertEqual(self.outcome(resumed), ("finished", None), resumed)
        after = self.state(resumed)
        self.assertEqual(self.calls("executor"), 2)
        self.assertEqual(after["agents"], before["agents"] + 1)
        self.assertIn("fresh scoped instruction", self.prompt("executor", 2))
        self.assertEqual(len(launch_budget.inventory(directory / "W1")["launches"]), 2)
        self.assertTrue((directory / "W1" / "attempts/1/streams/executor.1.jsonl").is_file())
