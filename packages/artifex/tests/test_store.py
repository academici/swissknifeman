from __future__ import annotations

import copy
import json
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path

from artifex import store


ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "plans" / ("2026" + ".08.03-ARTIFEX-SUPERVISOR") / "artifacts/P1/supervisor-run-cases-v1.json"


def _contend(run_dir: str, rules: dict, states: set[str], events: set[str], queue) -> None:
    candidate = store.RunStore.open(run_dir, rules=rules, states=states, events=events)
    try:
        candidate.acquire_writer()
    except store.StoreRefusal as exc:
        queue.put(exc.reason)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runs = self.root / "runs"
        self.runs.mkdir()
        self.cases = json.loads(CASES.read_text(encoding="utf-8"))
        self.rules = self.cases["state_rules"]
        self.states = set(self.cases["declared"]["states"])
        self.events = set(self.cases["declared"]["events"])
        self.identity = {
            "schema_version": "supervisor-run-v1", "contract_version": "1.0.0", "run_id": "run-001",
            "repository_root_hash": "a" * 64, "base_commit": "b" * 64, "plan_id": "plan",
            "plan_hash": "c" * 64, "mandate_hash": "d" * 64, "acceptance_hash": "e" * 64,
            "created_at": "2026-08-04T00:00:00Z", "redaction_policy_hash": "f" * 64,
        }
        self.run = store.RunStore.create(self.runs, "run-001", self.identity, rules=self.rules,
                                         states=self.states, events=self.events)

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, index: int) -> dict:
        payload = copy.deepcopy(self.cases["journal_fixture"]["payloads"][index])
        payload["run_id"] = "run-001"
        return payload

    def seed(self, count: int = 5) -> None:
        with self.run.acquire_writer():
            for index in range(count):
                self.run.append_event(self.payload(index))

    @staticmethod
    def rechain(records: list[dict]) -> None:
        previous = store.ZERO_HASH
        for sequence, record in enumerate(records, 1):
            record["seq"] = sequence
            record["prev_hash"] = previous
            record["record_hash"] = store.record_hash(record)
            previous = record["record_hash"]

    def test_canonical_replay_and_snapshot(self):
        self.seed()
        replay = self.run.replay()
        self.assertEqual(5, replay["seq"])
        self.assertEqual("ACCEPTED", replay["state"])
        built = self.run.rebuild_snapshot()
        self.assertEqual(5, built["snapshot"]["seq"])
        self.assertIn(built["capability"]["directory_fsync"], {"observed", "unsupported"})

    def test_all_frozen_journal_mutations_refuse(self):
        self.seed()
        raw = self.run.events_path.read_bytes()
        for case in self.cases["journal_mutations"]:
            if case["mutation"] == "none":
                continue
            with self.subTest(case=case["id"]):
                records = [json.loads(line) for line in raw.splitlines()]
                mutation = case["mutation"]
                if mutation == "bad_record_hash": records[1]["record_hash"] = "f" * 64
                elif mutation == "bad_prev_hash": records[1]["prev_hash"] = "e" * 64
                elif mutation == "sequence_gap": records[1]["seq"] += 2
                elif mutation == "reorder": records[1], records[2] = records[2], records[1]
                elif mutation == "duplicate": records.insert(2, copy.deepcopy(records[1]))
                elif mutation == "unknown_key": records[1]["unexpected"] = True
                elif mutation == "unknown_version": records[1]["schema_version"] = "v2"
                elif mutation == "unknown_event": records[1]["event"] = "unknown"
                elif mutation == "unknown_state": records[1]["state_after"] = "unknown"
                elif mutation == "illegal_transition": records[1]["event"] = "validation_green"; records[1]["state_after"] = "ACCEPTED"
                elif mutation == "observation_without_intent":
                    records = [records[0], records[3]]
                    records[1]["state_before"] = "READY"
                elif mutation == "idempotency_collision": records[2]["slice_id"] = "other"
                if mutation in {"unknown_key", "unknown_version", "unknown_event", "unknown_state", "illegal_transition", "observation_without_intent", "idempotency_collision"}:
                    self.rechain(records)
                mutated = b"".join(store.canonical_bytes(record) + b"\n" for record in records)
                if mutation == "truncate": mutated = raw[:-2]
                self.run.events_path.write_bytes(mutated)
                with self.assertRaises(store.StoreRefusal) as raised:
                    self.run.replay()
                self.assertEqual(case["expected"], raised.exception.reason)
                self.run.events_path.write_bytes(raw)

    def test_lock_is_nonblocking_and_metadata_bound(self):
        with self.run.acquire_writer():
            queue = multiprocessing.Queue()
            process = multiprocessing.Process(target=_contend, args=(str(self.run.run_dir), self.rules, self.states, self.events, queue))
            process.start(); process.join(5)
            self.assertEqual(0, process.exitcode)
            self.assertEqual("LOCK_HELD", queue.get(timeout=1))
        self.assertFalse(self.run.lock_path.exists())

    def test_append_crash_cuts_are_not_accepted(self):
        for stage in ("append_write", "append_flush", "append_fsync", "append_reopen", "append_verify"):
            with self.subTest(stage=stage):
                candidate = store.RunStore.create(self.runs, f"run-{stage}", {**self.identity, "run_id": f"run-{stage}"}, rules=self.rules, states=self.states, events=self.events)
                payload = self.payload(0); payload["run_id"] = f"run-{stage}"
                with candidate.acquire_writer():
                    with self.assertRaises(store.InjectedFailure):
                        candidate.append_event(payload, fault_at=stage)

    def test_snapshot_cuts_and_corruption_never_heal_journal(self):
        self.seed()
        for stage in ("temp_write", "temp_flush", "temp_fsync", "replace", "directory_fsync"):
            with self.subTest(stage=stage):
                with self.assertRaises(store.InjectedFailure):
                    self.run.rebuild_snapshot(fault_at=stage)
                self.assertEqual(5, self.run.replay()["seq"])
        self.run.snapshot_path.write_text("not-json", encoding="utf-8")
        self.assertEqual("ACCEPTED", self.run.replay()["state"])

    def test_run_identity_and_path_refusals(self):
        with self.assertRaisesRegex(store.StoreRefusal, "RUN_IDENTITY_MISMATCH"):
            store.RunStore.create(self.runs, "../escape", self.identity, rules=self.rules, states=self.states, events=self.events)
        self.run.run_path.unlink()
        self.run.run_path.symlink_to(self.root / "outside")
        with self.assertRaisesRegex(store.StoreRefusal, "RUN_IDENTITY_MISMATCH"):
            self.run.replay()


if __name__ == "__main__":
    unittest.main()
