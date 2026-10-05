from __future__ import annotations

import unittest

from artifex import authority
from support import FIXTURE_PLAN as PLAN


class ItemRunnableTests(unittest.TestCase):
    ITEM = {"status": "todo", "depends_on": ["P1.1"], "authority": {"kind": "routine"}}

    def test_runnable_when_status_dependencies_and_authority_hold(self):
        self.assertTrue(authority.item_runnable(self.ITEM, done=frozenset({"P1.1"})))
        self.assertTrue(authority.item_runnable({**self.ITEM, "status": "in_progress"}, done=frozenset({"P1.1"})))

    def test_each_failed_fact_makes_the_item_not_runnable(self):
        done = frozenset({"P1.1"})
        self.assertFalse(authority.item_runnable(self.ITEM))
        self.assertFalse(authority.item_runnable({**self.ITEM, "status": "done"}, done=done))
        gated = {**self.ITEM, "authority": {"kind": "owner_gate", "gate": "RELEASE", "scope": "tag"}}
        self.assertFalse(authority.item_runnable(gated, done=done))
        self.assertTrue(authority.item_runnable(gated, done=done, granted_gates=frozenset({"RELEASE"})))


class AuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen = authority.load_frozen_authority(PLAN)
        cls.bank = cls.frozen.cases
        cls.base = cls.bank["base_input"]

    def assert_case(self, case_id: str, mutations: list[dict], expected: dict | str):
        record = authority.evaluate(authority.mutate(self.base, mutations), self.frozen, case_id)
        expected_values = expected if isinstance(expected, dict) else {"reason_code": expected}
        if "allowed" not in expected_values and record["reason_code"] not in {
            "AUTO_LEGAL", "ROUTINE_CHOICE_SELECTED", "AUTO_FIX_BOUNDED",
        }:
            expected_values = {**expected_values, "resolved_class": "OWNER", "allowed": False}
        for key, value in expected_values.items():
            self.assertEqual(value, record[key], f"{case_id}: {key}")
        self.assertEqual(record["allowed"], record["side_effect_authorized"], case_id)
        authority.validate_record(record)
        return record

    def test_frozen_inputs_are_versioned_and_hash_pinned(self):
        self.assertEqual("1.0.0", self.bank["contract_version"])
        self.assertEqual("authority-policy-cases-v1", self.bank["schema_version"])
        self.assertEqual(64, len(self.frozen.contract_hash))
        self.assertEqual(64, len(self.frozen.case_bank_hash))
        self.assertEqual(64, len(self.frozen.mandate_hash))
        self.assertEqual(64, len(self.frozen.source_set_hash))

    def test_exact_operation_and_routine_parity(self):
        for row in self.bank["operation_class_cases"]:
            with self.subTest(case=row["id"]):
                self.assert_case(row["id"], [
                    {"path": ["operation"], "value": row["operation"]},
                    {"path": ["requested_class"], "value": row["requested_class"]},
                ], row["expected"])
        for row in self.bank["routine_positive_cases"]:
            alternatives = [
                {"id": row["selected"], "rank": [1, 0, 0, 0, 0, -3, 20]},
                {"id": f"new-{row['operation']}", "rank": [2, 1, 0, 0, 1, -2, 30]},
            ]
            with self.subTest(case=row["id"]):
                self.assert_case(row["id"], [
                    {"path": ["operation"], "value": row["operation"]},
                    {"path": ["requested_class"], "value": "AUTO"},
                    {"path": ["alternatives"], "value": alternatives},
                ], {
                    "resolved_class": "AUTO", "allowed": True,
                    "reason_code": "ROUTINE_CHOICE_SELECTED", "attention": "none",
                    "selected_alternative": row["selected"],
                })

    def test_every_frozen_predicate_and_narrowing_mutation_fails_closed(self):
        for section in ("predicate_cases", "narrowing_cases"):
            for row in self.bank[section]:
                for operation in authority.OPERATIONS:
                    for requested in authority.ACTION_CLASSES:
                        mutations = list(row["mutations"]) + [{"path": ["operation"], "value": operation}]
                        if row.get("dimension") != "action_class":
                            mutations.append({"path": ["requested_class"], "value": requested})
                        case_id = f"{row['id']}:{operation}:{requested}"
                        with self.subTest(case=case_id):
                            self.assert_case(case_id, mutations, row["expected"])

    def test_operation_predicates_auto_fix_and_precedence_cases(self):
        for row in self.bank["operation_predicate_cases"]:
            for requested in authority.ACTION_CLASSES:
                case_id = f"{row['id']}:{requested}"
                with self.subTest(case=case_id):
                    self.assert_case(case_id, [
                        {"path": ["operation"], "value": row["operation"]},
                        {"path": ["requested_class"], "value": requested},
                        {"path": ["operation_context", row["predicate"]], "value": False},
                    ], "OPERATION_PRECONDITION_FAILED")
        for row in self.bank["auto_fix_cases"]:
            with self.subTest(case=row["id"]):
                self.assert_case(row["id"], [
                    {"path": ["operation"], "value": "integrate_owned_delta"},
                    {"path": ["requested_class"], "value": "AUTO-FIX"},
                    *row["mutations"],
                ], row["expected"])
        for row in self.bank["precedence_cases"]:
            with self.subTest(case=row["id"]):
                self.assert_case(row["id"], [{"path": ["authority_sources"], "value": row["sources"]}], row["expected"])

    def test_multifault_unknown_and_legacy_compatibility_banks(self):
        for section in ("precedence_multifault_cases", "unknown_cases"):
            for row in self.bank[section]:
                with self.subTest(case=row["id"]):
                    self.assert_case(row["id"], row["mutations"], row["expected"])
        for case in self.frozen.p0_cases["cases"]:
            with self.subTest(case=case["id"]):
                record = authority.evaluate(authority.normalize_legacy(self.base, case), self.frozen, f"legacy:{case['id']}")
                for key, value in case["expected"].items():
                    self.assertEqual(value, record[key], f"{case['id']}: {key}")

    def test_totality_and_owner_attention_are_closed(self):
        unknown = authority.evaluate(
            authority.mutate(self.base, [{"path": ["operation"], "value": "unknown"}]),
            self.frozen, "unknown",
        )
        self.assertEqual("UNKNOWN_OPERATION", unknown["reason_code"])
        self.assertEqual("OWNER", unknown["resolved_class"])
        self.assertEqual("batched", unknown["attention"])
        immediate = self.assert_case("security", [{"path": ["security"], "value": True}], "PROTECTED_SECURITY")
        self.assertEqual("immediate", immediate["attention"])
        self.assertFalse(immediate["side_effect_authorized"])
        self.assertEqual(set(authority.DECISION_KEYS), set(immediate))

    def test_attention_packet_fields_are_closed_and_slice_bound(self):
        record = self.assert_case("packet", [
            {"path": ["requested_class"], "value": "OWNER"},
            {"path": ["blast_radius"], "value": "slice:alpha"},
            {"path": ["rollback"], "value": "rollback:alpha"},
            {"path": ["affected_slices"], "value": ["alpha"]},
            {"path": ["no_decision_consequence"], "value": "block:alpha"},
            {"path": ["blocking_dependencies"], "value": ["prepare"]},
        ], "OWNER_REQUIRED_BY_MANDATE")
        self.assertEqual("slice:alpha", record["blast_radius"])
        self.assertEqual("rollback:alpha", record["rollback"])
        self.assertEqual(["alpha"], record["affected_slices"])
        self.assertEqual("block:alpha", record["no_decision_consequence"])
        self.assertEqual(["prepare"], record["blocking_dependencies"])


if __name__ == "__main__":
    unittest.main()
