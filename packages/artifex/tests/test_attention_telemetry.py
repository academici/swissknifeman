from __future__ import annotations

import copy
import unittest

from artifex import authority, telemetry


class AttentionTelemetryTests(unittest.TestCase):
    def decision(self, *, identifier: str, attention: str = "batched", dependencies=None) -> dict:
        reason = "PROTECTED_SECURITY" if attention == "immediate" else "OWNER_REQUIRED_BY_MANDATE"
        decision = {
            "decision_id": identifier, "operation": "dispatch_worker", "requested_class": "OWNER",
            "resolved_class": "OWNER", "allowed": False, "reason_code": reason, "attention": attention,
            "controlling_sources": ["authority-policy"], "source_set_hash": "a" * 64,
            "mandate_hash": "b" * 64, "selected_alternative": None, "rejected_alternatives": ["unsafe"],
            "intent_sequence": 1, "side_effect_authorized": False, "blast_radius": "one-slice",
            "rollback": "owner-directed", "affected_slices": [identifier],
            "no_decision_consequence": "writes-blocked", "blocking_dependencies": list(dependencies or []),
        }
        authority.validate_record(decision)
        return decision

    def record(self, sequence: int, decision: dict, *, event="append_intent") -> dict:
        return {"seq": sequence, "record_hash": f"{sequence:064x}", "event": event,
                "slice_id": decision["affected_slices"][0], "attempt": 1, "state_after": "OWNER",
                "evidence": {"authority_decision": decision}}

    def test_dedup_immediate_and_dependency_order_are_replay_stable(self):
        first = self.decision(identifier="root")
        child = self.decision(identifier="child", dependencies=[telemetry._stable_id(first)])
        immediate = self.decision(identifier="security", attention="immediate")
        packet = telemetry.project([self.record(1, child), self.record(2, first), self.record(3, first), self.record(4, immediate)])
        self.assertEqual(1, len(packet["queue"]["immediate"]))
        self.assertEqual(2, len(packet["queue"]["batched"]))
        self.assertEqual(["root", "child"], [row["decision_id"] for row in packet["queue"]["batched"]])
        self.assertEqual("security", packet["queue"]["immediate"][0]["decision_id"])

    def test_owner_resolution_removes_the_finding_from_the_open_queue(self):
        decision = self.decision(identifier="resolved")
        resolution = self.record(2, decision, event="owner_decision_continue")
        resolution["evidence"] = {"owner": "continue", "attention_resolution": {
            "decision_id": "resolved", "outcome": "resolved",
        }}
        packet = telemetry.project([self.record(1, decision, event="authority_attention"), resolution])
        self.assertEqual([], packet["queue"]["batched"])
        self.assertEqual("resolved", packet["closed_attention"][0]["status"])

    def test_unknown_provider_and_caps_are_not_suppressed(self):
        decision = self.decision(identifier="provider")
        record = self.record(1, decision, event="provider_unavailable")
        record["evidence"]["observation"] = {"kind": "provider_unavailable", "reason_code": "PROVIDER_UNAVAILABLE"}
        packet = telemetry.project([record])
        self.assertEqual("PROVIDER_UNAVAILABLE", packet["unknown_reasons"]["seq:1:provider"])
        another = copy.deepcopy(record)
        another["seq"] = 2
        another["record_hash"] = f"{2:064x}"
        another["evidence"]["authority_decision"]["decision_id"] = "provider-2"
        another["evidence"]["authority_decision"]["affected_slices"] = ["provider-2"]
        with self.assertRaises(telemetry.TelemetryRefusal):
            telemetry.project([record, another], max_items=1)


if __name__ == "__main__":
    unittest.main()
