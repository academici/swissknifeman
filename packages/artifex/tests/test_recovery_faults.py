from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from artifex import faults, scheduler, store
from support import FIXTURE_PLAN


CASES = FIXTURE_PLAN / "artifacts/P1/supervisor-run-cases-v1.json"


class RecoveryFaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runs = Path(self.temp.name) / "runs"; self.runs.mkdir()
        bank = json.loads(CASES.read_text(encoding="utf-8"))
        self.rules, self.states, self.events = bank["state_rules"], set(bank["declared"]["states"]), set(bank["declared"]["events"])

    def tearDown(self):
        self.temp.cleanup()

    def make_run(self, name="recovery"):
        return store.RunStore.create(self.runs, name, {
            "schema_version": "supervisor-run-v1", "contract_version": "1.0.0", "run_id": name,
            "repository_root_hash": "a" * 64, "base_commit": "b" * 64, "plan_id": "plan",
            "plan_hash": "c" * 64, "mandate_hash": "d" * 64, "acceptance_hash": "e" * 64,
            "created_at": "2026-08-05T00:00:00Z", "redaction_policy_hash": "f" * 64,
        }, rules=self.rules, states=self.states, events=self.events)

    @staticmethod
    def payload(run, event, *, key=None):
        replay = run.replay(); state = replay["state"] or "CREATED"
        return {"ts": "2026-08-05T00:00:00Z", "run_id": run.run_dir.name, "slice_id": "slice" if key else None,
                "attempt": 1 if key else None, "event": event, "state_before": state,
                "state_after": run.rules[state]["on"][event], "idempotency_key": key,
                "input_hashes": {}, "evidence": {}, "redaction": {"status": "clean"}}

    def unresolved(self, name="recovery", *, active=False):
        run = self.make_run(name)
        key = "1" * 64
        with run.acquire_writer():
            run.append_event(self.payload(run, "freeze_run"))
            run.append_event(self.payload(run, "append_intent", key=key))
            if active:
                run.append_event(self.payload(run, "boundary_started", key=key))
        return run, {"slice_id": "slice", "attempt": 1, "idempotency_key": key}

    @staticmethod
    def inspection(*, observed="a", partial=False, backup=None, orphan=True, calls=0):
        return {"preimage_hash": "a" * 64, "postimage_hash": "b" * 64,
                "observed_hash": observed * 64, "partial": partial, "backup": backup,
                "orphan_verified": orphan, "external_call_count": calls}

    def test_every_fault_cut_is_a_fresh_child_and_never_claims_a_second_call(self):
        for cut in faults.CUT_POINTS:
            with self.subTest(cut=cut):
                crash = faults.crash_at(cut)
                self.assertEqual((True, 97), (crash.reached, crash.exit_code))
                decision = store.recovery_decision(self.inspection(calls=0))
                self.assertEqual(("preimage", True), (decision["observed"], decision["retry"]))

    def test_exact_postimage_validates_without_rerun_and_partial_rolls_back(self):
        run, slice_value = self.unresolved("post", active=True)
        recovered = scheduler.Scheduler(run, None, now=lambda: "2026-08-05T00:00:00Z", validate=lambda *_: True)
        post = recovered.reconcile_verified(slice_value, self.inspection(observed="b", calls=1))
        self.assertEqual(("ACCEPTED", "validate_without_rerun", False),
                         (post["status"], post["recovery"]["reason"], post["recovery"]["retry"]))
        run, slice_value = self.unresolved("partial", active=True)
        partial = scheduler.Scheduler(run, None, now=lambda: "2026-08-05T00:00:00Z").reconcile_verified(
            slice_value, self.inspection(partial=True, backup="verified", calls=1))
        self.assertEqual(("ROLLED_BACK", "whole_slice_rollback", True),
                         (partial["status"], partial["recovery"]["reason"], partial["recovery"]["retry"]))

    def test_unknown_missing_backup_and_duplicate_counter_become_incidents(self):
        for name, inspection in (("missing", self.inspection(partial=True, backup="missing", calls=1)),
                                 ("ambiguous", self.inspection(orphan=False)),
                                 ("duplicate", self.inspection(calls=2))):
            with self.subTest(name=name):
                run, slice_value = self.unresolved(name, active=True)
                if name == "duplicate":
                    with self.assertRaisesRegex(store.StoreRefusal, "POSTIMAGE_THIRD_STATE"):
                        store.recovery_decision(inspection)
                    continue
                result = scheduler.Scheduler(run, None, now=lambda: "2026-08-05T00:00:00Z").reconcile_verified(slice_value, inspection)
                self.assertEqual("INCIDENT", result["status"])


if __name__ == "__main__":
    unittest.main()
