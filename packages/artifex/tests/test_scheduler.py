from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from artifex import authority, scheduler, store


ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "plans" / ("2026" + ".08.03-ARTIFEX-SUPERVISOR")
CASES = PLAN / "artifacts/P1/supervisor-run-cases-v1.json"


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runs = Path(self.temp.name) / "runs"
        self.runs.mkdir()
        cases = json.loads(CASES.read_text(encoding="utf-8"))
        self.store = store.RunStore.create(self.runs, "run-001", {
            "schema_version": "supervisor-run-v1", "contract_version": "1.0.0", "run_id": "run-001",
            "repository_root_hash": "a" * 64, "base_commit": "b" * 64, "plan_id": "plan",
            "plan_hash": "c" * 64, "mandate_hash": "d" * 64, "acceptance_hash": "e" * 64,
            "created_at": "2026-08-04T00:00:00Z", "redaction_policy_hash": "f" * 64,
        }, rules=cases["state_rules"], states=set(cases["declared"]["states"]), events=set(cases["declared"]["events"]))
        self.frozen = authority.load_frozen_authority(PLAN)
        self.tick = 0
        with self.store.acquire_writer():
            self.store.append_event(self.payload("freeze_run", None))

    def tearDown(self):
        self.temp.cleanup()

    def now(self):
        self.tick += 1
        return f"2026-08-04T00:00:{self.tick:02d}Z"

    def payload(self, event, slice_value):
        state = self.store.replay()["state"] or "CREATED"
        return {
            "ts": self.now(), "run_id": "run-001", "slice_id": None if slice_value is None else slice_value["slice_id"],
            "attempt": None if slice_value is None else slice_value["attempt"], "event": event,
            "state_before": state, "state_after": self.store.rules[state]["on"].get(event, "ACCEPTED"),
            "idempotency_key": None if slice_value is None else slice_value["idempotency_key"],
            "input_hashes": {}, "evidence": {}, "redaction": {},
        }

    def slice(self, name="slice-a", *, retry_count=0, dependencies=None, read_only=False):
        base = copy.deepcopy(self.frozen.cases["base_input"])
        base.update({"operation": "integrate_owned_delta", "requested_class": "AUTO-FIX", "retry_count": retry_count})
        return {
            "slice_id": name, "attempt": 1, "idempotency_key": ("1" if name == "slice-a" else "2") * 64,
            "dependencies": dependencies or [], "read_only": read_only, "worktree_isolated": False,
            "budget": {"attempts": 2, "tokens": 10, "cost": 10, "duration": 10, "turns": 10},
            "used": {"attempts": 0, "tokens": 0, "cost": 0, "duration": 0, "turns": 0},
            "input_hashes": {"slice": "a" * 64}, "authority_input": base,
        }

    def make(self, *, activity=None, validate=None):
        return scheduler.Scheduler(self.store, self.frozen, now=self.now, activity=activity, validate=validate)

    def test_ready_selection_is_dependency_ordered_and_write_serialized(self):
        first, second = self.slice("slice-a"), self.slice("slice-b", dependencies=["slice-a"])
        self.assertEqual(["slice-a"], [row["slice_id"] for row in scheduler.ready_set([second, first], set())])
        self.assertEqual(["slice-b"], [row["slice_id"] for row in scheduler.ready_set([second, first], {"slice-a"})])
        readers = [self.slice("slice-a", read_only=True), self.slice("slice-b", read_only=True)]
        self.assertEqual(2, len(scheduler.ready_set(readers, set())))

    def test_intent_precedes_activity_and_success_requires_validation(self):
        calls = []
        def activity(value):
            calls.append(self.store.replay()["state"])
            return {"kind": "success", "exit": "OK"}
        result = self.make(activity=activity, validate=lambda *_: True).schedule([self.slice()])
        self.assertEqual("accepted", result["status"])
        self.assertEqual(["INTENT_DURABLE"], calls)
        self.assertEqual(["freeze_run", "append_intent", "boundary_started", "append_observation", "validation_green"],
                         [row["event"] for row in self.store.replay()["records"]])

    def test_default_port_refuses_without_external_boundary(self):
        result = self.make().schedule([self.slice()])
        self.assertEqual("provider_unavailable", result["status"])
        self.assertEqual(["freeze_run", "append_intent", "provider_unavailable"],
                         [row["event"] for row in self.store.replay()["records"]])

    def test_retry_cap_maps_to_frozen_budget_transition_without_intent_or_activity(self):
        calls = []
        result = self.make(activity=lambda value: calls.append(value)).schedule([self.slice(retry_count=2)])
        self.assertEqual("budget_exhausted", result["status"])
        self.assertFalse(result["decision"]["allowed"])
        self.assertEqual("RETRY_BUDGET_EXHAUSTED", result["decision"]["reason_code"])
        self.assertEqual("BUDGET_EXHAUSTED", self.store.replay()["state"])
        self.assertEqual([], calls)
        self.assertEqual(["freeze_run", "budget_exhausted"], [row["event"] for row in self.store.replay()["records"]])
        with self.assertRaisesRegex(scheduler.SchedulerRefusal, "BUDGET_LIMIT"):
            self.make().schedule([self.slice("slice-b")])
        self.assertEqual("READY", self.make().owner_decision(self.slice(), "continue")["status"])
        self.assertEqual("ABORTED", self.make().owner_decision(self.slice(), "abort")["status"])

    def test_budget_and_reconcile_outcomes_stay_in_frozen_cells(self):
        limited = self.slice()
        limited["used"]["tokens"] = 10
        self.assertEqual("budget_exhausted", self.make().schedule([limited])["status"])
        self.assertEqual("BUDGET_EXHAUSTED", self.store.replay()["state"])

        self.temp.cleanup()
        self.setUp()
        value = self.slice()
        with self.store.acquire_writer():
            self.store.append_event(self.payload("append_intent", value))
            self.store.append_event(self.payload("boundary_started", value))
        self.assertEqual("INCIDENT", self.make().reconcile(value, "third")["status"])

    def test_no_effect_and_exact_postimage_reconcile_without_retry_guessing(self):
        value = self.slice()
        with self.store.acquire_writer():
            self.store.append_event(self.payload("append_intent", value))
        self.assertEqual("ROLLED_BACK", self.make().reconcile(value, "preimage")["status"])

        self.temp.cleanup()
        self.setUp()
        value = self.slice()
        with self.store.acquire_writer():
            self.store.append_event(self.payload("append_intent", value))
            self.store.append_event(self.payload("boundary_started", value))
        self.assertEqual("ACCEPTED", self.make(validate=lambda *_: True).reconcile(value, "postimage")["status"])

    def test_source_drift_and_failed_envelopes_do_not_become_budget_events(self):
        drifting = self.slice()
        drifting["authority_input"]["source_set_current"] = False
        result = self.make().schedule([drifting])
        self.assertEqual("owner_attention", result["status"])
        self.assertEqual("SOURCE_DRIFT", result["decision"]["reason_code"])
        self.assertEqual(["freeze_run"], [row["event"] for row in self.store.replay()["records"]])

        for malformed in ("timeout", "quota", "schema"):
            self.temp.cleanup()
            self.setUp()
            with self.subTest(kind=malformed):
                with self.assertRaisesRegex(scheduler.SchedulerRefusal, "UNKNOWN_SCHEMA_VERSION"):
                    self.make(activity=lambda _, kind=malformed: {"kind": kind}).schedule([self.slice()])
                self.assertEqual("INTENT_DURABLE", self.store.replay()["state"])

    def test_invalid_activity_and_wrong_transition_fail_closed(self):
        with self.assertRaisesRegex(scheduler.SchedulerRefusal, "UNKNOWN_SCHEMA_VERSION"):
            self.make(activity=lambda _: {"kind": "quota"}).schedule([self.slice()])
        self.assertEqual("INTENT_DURABLE", self.store.replay()["state"])
        with self.store.acquire_writer():
            with self.assertRaises(store.StoreRefusal):
                self.store.append_event(self.payload("validation_green", self.slice()))
        self.assertEqual("INTENT_DURABLE", self.store.replay()["state"])


if __name__ == "__main__":
    unittest.main()
