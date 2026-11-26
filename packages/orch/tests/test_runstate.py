from __future__ import annotations

import json
from pathlib import Path
import unittest

from orch import contracts
from orch.port import PortError, RunState

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "77492587d30e5c55384a8d8fecb924ef144942ea5ddf605d3262722d7a67d1d6"
INSTRUCTIONS = "1" * 64
ROUTE = {"class": "implementation", "effort": "high"}


def trace(name):
    lines = (ROOT / "fixtures/traces" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def event(seq, kind, attempt=1, stage="primary", **extra):
    doc = {
        "$schema": "urn:swissknifeman:orch:exec:run-event:v1", "contract_version": "exec/v1",
        "run_id": "synthetic-run", "stage_id": stage, "attempt": attempt, "seq": seq,
        "ts": f"2026-10-05T17:00:{seq:02d}Z", "kind": kind,
    }
    doc.update(extra)
    return doc


def fold(events, close=False):
    state = RunState("synthetic-run")
    for doc in events:
        state.apply(doc)
    if close:
        state.close()
    return state


def result(state, stage="primary"):
    return state.stage_result(stage, role="executor", requested_route=ROUTE, input_digest=DIGEST,
                              instructions_digest=INSTRUCTIONS)


class RunStateTests(unittest.TestCase):
    def assert_port_error(self, code, state, doc):
        before = state.stages()
        with self.assertRaises(PortError) as caught:
            state.apply(doc)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(state.stages(), before)  # a rejected event changes nothing

    def assert_valid_result(self, doc):
        issues = [i for i in contracts.validate(doc, "stage-result") if i.level == "error"]
        self.assertEqual(issues, [])

    def test_ok_trace_completes_with_reported_usage(self):
        state = fold(trace("native-claude-code-ok"))
        stage = state.stages()["primary"]
        self.assertEqual((stage["status"], stage["attempt"], stage["last_seq"]), ("completed", 1, 4))
        self.assertEqual(stage["errors"], [])
        doc = result(state)
        self.assert_valid_result(doc)
        self.assertEqual(doc["usage"], {"status": "reported", "input_tokens": 100, "output_tokens": 25})
        self.assertEqual(doc["hashes"]["input"], DIGEST)
        self.assertEqual(doc["route"]["observed"],
                         {"provider": "claude-code", "model": "synthetic-model", "effort": "high", "source": "event"})

    def test_identical_duplicate_is_ignored(self):
        events = trace("native-claude-code-ok")
        state = fold(events[:3])
        before = state.stages()
        state.apply(events[1])
        state.apply(events[2])
        self.assertEqual(state.stages(), before)
        for doc in events[3:]:
            state.apply(doc)
        self.assertEqual(state.stages()["primary"]["status"], "completed")

    def test_duplicate_seq_with_other_content_is_seq_order(self):
        state = fold([event(0, "started"), event(1, "output")])
        self.assert_port_error("SEQ_ORDER", state, event(1, "completed"))

    def test_decreasing_seq_is_seq_order(self):
        state = fold([event(0, "started"), event(5, "output")])
        self.assert_port_error("SEQ_ORDER", state, event(3, "output"))

    def test_foreign_run_is_run_unknown(self):
        state = fold([event(0, "started")])
        self.assert_port_error("RUN_UNKNOWN", state, dict(event(1, "output"), run_id="other-run"))

    def test_invalid_event_is_input_invalid(self):
        state = fold([event(0, "started")])
        self.assert_port_error("INPUT_INVALID", state, event(1, "finished"))
        self.assert_port_error("INPUT_INVALID", state, event(1, "output", attempt=0))

    def test_event_after_terminal_of_same_attempt(self):
        state = fold([event(0, "started"), event(1, "completed")])
        self.assert_port_error("AFTER_TERMINAL", state, event(2, "output"))
        self.assert_port_error("AFTER_TERMINAL", state, event(2, "completed"))

    def test_late_event_of_previous_attempt_is_after_terminal(self):
        state = fold([event(0, "started"), event(1, "failed"), event(2, "started", attempt=2)])
        self.assert_port_error("AFTER_TERMINAL", state, event(3, "output", attempt=1))

    def test_late_started_of_terminal_attempt_is_after_terminal(self):
        for kind in ("failed", "timeout", "quota_block", "auth_block", "unknown_outcome",
                     "completed", "cancelled"):
            with self.subTest(kind=kind):
                state = fold([event(0, "started"), event(1, kind)])
                self.assert_port_error("AFTER_TERMINAL", state, event(2, "started"))
                if kind not in ("completed", "cancelled"):
                    state.apply(event(2, "started", attempt=2))
                    self.assert_port_error("AFTER_TERMINAL", state, event(3, "started", attempt=1))
                    state.apply(event(3, "failed", attempt=2))
                    self.assert_port_error("AFTER_TERMINAL", state, event(4, "started", attempt=1))

    def test_grok_unknown_trace_closes_as_unknown_outcome(self):
        state = fold(trace("native-grok-unknown"))
        self.assertEqual(state.stages()["primary"]["status"], "running")
        state.close()
        stage = state.stages()["primary"]
        self.assertEqual(stage["status"], "unknown_outcome")
        self.assertEqual(stage["errors"], [{"class": "transport", "message": "stream ended without terminal event"}])
        doc = result(state)
        self.assert_valid_result(doc)
        self.assertEqual(doc["status"], "unknown_outcome")
        self.assertEqual(doc["usage"], {"status": "unknown"})
        self.assertNotIn("finished_at", doc)  # no terminal event, no invented time

    def test_codex_quota_is_quota_blocked_not_failed(self):
        state = fold(trace("native-codex-quota"), close=True)
        doc = result(state)
        self.assert_valid_result(doc)
        self.assertEqual(doc["status"], "quota_blocked")
        self.assertEqual([e["class"] for e in doc["errors"]], ["quota"])
        self.assertEqual(doc["usage"], {"status": "unknown"})

    def test_provider_error_keeps_running(self):
        state = fold([event(0, "started"), event(1, "provider_error", summary="overloaded",
                                                 raw_ref={"path": "raw/primary.jsonl", "line": 3})])
        stage = state.stages()["primary"]
        self.assertEqual(stage["status"], "running")
        self.assertEqual(stage["errors"], [{"class": "provider", "message": "overloaded",
                                            "raw_ref": "raw/primary.jsonl"}])

    def test_retry_after_failed_starts_attempt_two(self):
        state = fold([event(0, "started"), event(1, "failed"), event(2, "started", attempt=2)])
        stage = state.stages()["primary"]
        self.assertEqual((stage["status"], stage["attempt"], stage["errors"]), ("running", 2, []))

    def test_retry_rules(self):
        cases = [
            ("attempt 3 after completed", [event(0, "started"), event(1, "completed")],
             event(2, "started", attempt=3), "AFTER_TERMINAL"),
            ("attempt 2 after completed", [event(0, "started"), event(1, "completed")],
             event(2, "started", attempt=2), "AFTER_TERMINAL"),
            ("retry after cancelled", [event(0, "started"), event(1, "cancelled")],
             event(2, "started", attempt=2), "AFTER_TERMINAL"),
            ("attempt skipped", [event(0, "started"), event(1, "timeout")],
             event(2, "started", attempt=3), "INPUT_INVALID"),
            ("retry while running", [event(0, "started")], event(1, "started", attempt=2), "INPUT_INVALID"),
            ("first attempt is not 1", [], event(0, "started", attempt=2), "INPUT_INVALID"),
            ("event before started", [], event(0, "output"), "INPUT_INVALID"),
            ("future attempt", [event(0, "started")], event(1, "output", attempt=2), "INPUT_INVALID"),
        ]
        for name, prefix, doc, code in cases:
            with self.subTest(name):
                self.assert_port_error(code, fold(prefix), doc)

    def test_terminal_kinds_map_to_statuses(self):
        expected = {
            "quota_block": "quota_blocked", "auth_block": "auth_blocked", "timeout": "timeout",
            "cancelled": "cancelled", "failed": "failed", "completed": "completed",
            "unknown_outcome": "unknown_outcome",
        }
        for kind, status in expected.items():
            with self.subTest(kind=kind):
                state = fold([event(0, "started"), event(1, kind)])
                self.assertEqual(state.stages()["primary"]["status"], status)
                self.assert_valid_result(result(state))

    def test_usage_without_data_is_unknown(self):
        state = fold([event(0, "started"), event(1, "completed")])
        doc = result(state)
        self.assertEqual(doc["usage"], {"status": "unknown"})
        self.assert_valid_result(doc)

    def test_usage_comes_from_last_completed_only(self):
        usage = {"usage": {"input_tokens": 7, "output_tokens": 3}}
        state = fold([event(0, "started"), event(1, "output", data=usage), event(2, "completed")])
        self.assertEqual(result(state)["usage"], {"status": "unknown"})
        state = fold([event(0, "started"), event(1, "failed", data=usage), event(2, "started", attempt=2),
                      event(3, "completed", attempt=2, data={"usage": {"input_tokens": 9}})])
        self.assertEqual(result(state)["usage"], {"status": "reported", "input_tokens": 9})

    def test_usage_is_detached_from_applied_event(self):
        completed = event(1, "completed", data={"usage": {"input_tokens": 7, "output_tokens": 3}})
        state = fold([event(0, "started"), completed])
        expected = result(state)
        completed["data"]["usage"]["input_tokens"] = 999
        del completed["data"]["usage"]["output_tokens"]
        self.assertEqual(result(state), expected)
        state.apply(event(1, "completed", data={"usage": {"input_tokens": 7, "output_tokens": 3}}))
        self.assertEqual(result(state), expected)
        self.assert_port_error("SEQ_ORDER", state, completed)

    def test_stages_are_independent(self):
        state = fold([event(0, "started", stage="scout"), event(1, "completed", stage="scout"),
                      event(2, "started"), event(3, "output")], close=True)
        stages = state.stages()
        self.assertEqual(stages["scout"]["status"], "completed")
        self.assertEqual(stages["primary"]["status"], "unknown_outcome")

    def test_stage_result_requires_terminal_stage(self):
        state = fold([event(0, "started")])
        for stage in ("primary", "missing"):
            with self.subTest(stage=stage), self.assertRaises(PortError) as caught:
                result(state, stage)
            self.assertEqual(caught.exception.code, "INPUT_INVALID")

    def test_stages_returns_copies(self):
        state = fold([event(0, "started"), event(1, "provider_error")])
        state.stages()["primary"]["errors"].append({"class": "task", "message": "x"})
        self.assertEqual(len(state.stages()["primary"]["errors"]), 1)


def error_doc(error_class="provider_internal", **extra):
    return dict({"class": error_class, "code": "UPSTREAM_FAILURE", "retryable": True,
                 "safe_message": "provider failed"}, **extra)


class EventIdentityTests(unittest.TestCase):
    def rejected(self, code, state, doc):
        before = state.stages()
        with self.assertRaises(PortError) as caught:
            state.apply(doc)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(state.stages(), before)

    def test_event_id_repeat_is_ignored(self):
        started = event(0, "started", event_id="evt-1")
        state = fold([started, event(1, "output", event_id="evt-2")])
        before = state.stages()
        state.apply(started)
        self.assertEqual(state.stages(), before)

    def test_event_id_with_other_content_is_conflict_before_seq_rules(self):
        state = fold([event(0, "started", event_id="evt-1"), event(1, "output", event_id="evt-2")])
        self.rejected("EVENT_CONFLICT", state, event(2, "output", event_id="evt-2"))
        self.rejected("EVENT_CONFLICT", state, event(0, "started", event_id="evt-1", summary="changed"))

    def test_seq_rules_remain_for_events_with_other_ids(self):
        state = fold([event(0, "started", event_id="evt-1")])
        self.rejected("SEQ_ORDER", state, event(0, "started", event_id="evt-9"))

    def test_older_epoch_is_stale(self):
        state = fold([event(0, "started", owner_epoch=2)])
        self.rejected("STALE_EPOCH", state, event(1, "output", owner_epoch=1))
        state.apply(event(1, "output", owner_epoch=2))
        state.apply(event(2, "output", owner_epoch=3))
        self.rejected("STALE_EPOCH", state, event(3, "output", owner_epoch=2))

    def test_event_without_epoch_is_not_fenced(self):
        state = fold([event(0, "started", owner_epoch=5)])
        state.apply(event(1, "output"))
        self.assertEqual(state.stages()["primary"]["last_seq"], 1)

    def test_rejected_event_does_not_advance_the_epoch(self):
        state = fold([event(0, "started", owner_epoch=1), event(1, "completed", owner_epoch=1)])
        self.rejected("AFTER_TERMINAL", state, event(2, "output", owner_epoch=9))
        state.apply(event(2, "started", stage="other", owner_epoch=1))  # epoch 9 never fenced the owner
        self.assertEqual(state.stages()["other"]["status"], "running")

    def test_replay_of_old_epoch_event_is_ignored_not_stale(self):
        old = event(1, "output", owner_epoch=1, event_id="evt-1")
        state = fold([event(0, "started", owner_epoch=1), old, event(2, "output", owner_epoch=2)])
        state.apply(old)

    def test_foreign_version_is_kept_and_not_applied(self):
        foreign = dict(event(5, "output"), contract_version="exec/v2", unknown_field=True)
        state = fold([event(0, "started")])
        before = state.stages()
        state.apply(foreign)
        state.apply(foreign)
        self.assertEqual(state.stages(), before)
        self.assertEqual(state.foreign(), [foreign, foreign])
        state.foreign()[0]["kind"] = "changed"
        self.assertEqual(state.foreign()[0]["kind"], "output")
        foreign["kind"] = "later"
        self.assertEqual(state.foreign()[0]["kind"], "output")

    def test_foreign_version_does_not_consume_seq_or_id(self):
        state = fold([event(0, "started")])
        state.apply(dict(event(1, "output", event_id="evt-1"), contract_version="exec/v2"))
        state.apply(event(1, "output", event_id="evt-1"))
        self.assertEqual(state.stages()["primary"]["last_seq"], 1)

    def test_missing_contract_version_is_invalid_not_foreign(self):
        doc = event(1, "output")
        del doc["contract_version"]
        state = fold([event(0, "started")])
        self.rejected("INPUT_INVALID", state, doc)
        self.assertEqual(state.foreign(), [])

    def test_normalized_error_is_kept_in_stage_errors(self):
        error = error_doc("quota", code="USAGE_LIMIT", retry_after_s=60)
        state = fold([event(0, "started"), event(1, "quota_block", error=error)])
        record = state.stages()["primary"]["errors"][0]
        self.assertEqual((record["class"], record["error"]), ("quota", error))
        error["code"] = "CHANGED"
        self.assertEqual(state.stages()["primary"]["errors"][0]["error"]["code"], "USAGE_LIMIT")

    def test_failed_event_with_error_records_a_stage_error(self):
        state = fold([event(0, "started"), event(1, "failed", error=error_doc("authentication", code="BAD_KEY"))])
        record = state.stages()["primary"]["errors"][0]
        self.assertEqual(record["class"], "auth")
        self.assertEqual(record["message"], "provider failed")
        for name in ("completed", "failed"):  # a failed event without an error keeps the old behaviour
            self.assertEqual(fold([event(0, "started"), event(1, name)]).stages()["primary"]["errors"], [])

    def test_stage_result_does_not_alias_the_recorded_error(self):
        state = fold([event(0, "started"), event(1, "failed", error=error_doc("authentication", code="BAD"))])
        result(state)["errors"][0]["error"]["code"] = "MUTATED"
        self.assertEqual(state.stages()["primary"]["errors"][0]["error"]["code"], "BAD")
        self.assertEqual(result(state)["errors"][0]["error"]["code"], "BAD")

    def test_stage_result_with_normalized_error_is_valid(self):
        state = fold([event(0, "started"), event(1, "timeout", error=error_doc("timeout", code="NO_ANSWER"))])
        doc = result(state)
        self.assertEqual(doc["errors"][0]["error"]["class"], "timeout")
        self.assertEqual([i for i in contracts.validate(doc, "stage-result") if i.level == "error"], [])


if __name__ == "__main__":
    unittest.main()
