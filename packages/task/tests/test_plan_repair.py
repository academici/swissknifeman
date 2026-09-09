"""Regression coverage for the closed continue-first repair reducer."""
import unittest

from task import plan_blocking, plan_repair


def carrier(command="phpstan analyse", result="red", marker="a"):
    return {"command": command, "digest": marker * 64, "result": result}


def record(**overrides):
    red = carrier()
    value = {
        "schema_version": "repair-decision/v1",
        "plan_id": "2026.09.09-№1-DEMO",
        "item_id": "P2.1",
        "origin": "validation",
        "original_carrier": red,
        "baseline": {"reproduced": True, "carrier": carrier(result="red", marker="b")},
        "candidate": {"delta_proved": False, "evidence_ids": []},
        "affected_paths": [{"path": "packages/harness/test.py", "owner_item": "P2.2", "declared_file": False}],
        "bounded_diff": {"files_changed": 2, "max_files": 3, "reversible": True},
        "material_surface": {"public": False, "frozen": False, "security": False, "schema": False,
                             "dependency": False, "authority": False, "irreversible": False,
                             "product": False, "test_topology": False},
        "pre_validation": [red],
        "post_validation": [],
        "evidence_ids": ["fixture:incident"],
        "design": None,
    }
    value.update(overrides)
    return value


class RepairDecisionTests(unittest.TestCase):
    def test_phpstan_clean_baseline_is_same_attempt_repair(self):
        decision = plan_repair.evaluate(record())
        self.assertEqual(decision["action"], "repair-in-current-attempt")
        self.assertEqual(decision["reason_code"], "CLEAN_BASELINE_WITHOUT_CANDIDATE_DELTA")
        self.assertTrue(decision["post_validation_required"])

    def test_runner_topology_outside_files_is_bounded_repair(self):
        value = record(baseline={"reproduced": False, "carrier": None})
        decision = plan_repair.evaluate(value)
        self.assertEqual(decision["action"], "repair-in-current-attempt")
        self.assertEqual(decision["reason_code"], "BOUNDED_NONMATERIAL_REPAIR")

    def test_checkpoint_requires_design_evidence_for_material_surface(self):
        value = record(origin="checkpoint", baseline={"reproduced": False, "carrier": None})
        value["material_surface"]["public"] = True
        self.assertEqual(plan_repair.evaluate(value)["action"], "gather-evidence")
        value["design"] = {"decision_question": "API version?", "evidence_gap": "consumer impact",
                           "alternatives": ["keep", "break"], "expected_artifact": "D42"}
        self.assertEqual(plan_repair.evaluate(value)["action"], "design-required")

    def test_exact_original_carrier_must_be_preserved(self):
        value = record()
        value["pre_validation"] = [carrier(command="focused test")]
        with self.assertRaises(plan_repair.RepairDecisionError):
            plan_repair.validate(value)

    def test_public_security_and_authority_surfaces_fail_closed(self):
        for axis in ("public", "security", "authority"):
            with self.subTest(axis=axis):
                value = record(baseline={"reproduced": False, "carrier": None})
                value["material_surface"][axis] = True
                self.assertEqual(plan_repair.evaluate(value)["action"], "gather-evidence")

    def test_block_reducer_consumes_qualified_repair_without_reclassification(self):
        repair = record()
        candidate = {
            "schema_version": "block-candidate/v1", "plan_id": repair["plan_id"], "item_id": repair["item_id"],
            "signal_class": "safety-risk", "scope_class": "safety", "external": False,
            "scope_coverage": "outside-scope", "boundary_evidence": ["finding:real"],
            "executor_actor": "executor", "evidence_ids": ["evidence:one"], "resolutions_tried": [],
            "rag": {"required": False, "status": "not-required", "evidence_ids": []}, "review": None,
            "repair_decision": repair, "repair_digest": plan_repair.digest(repair),
        }
        self.assertEqual(plan_blocking.evaluate(candidate)["action"], "repair-in-current-attempt")
