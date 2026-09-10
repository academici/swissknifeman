"""Regression coverage for the closed continue-first repair reducer."""
import json
import tempfile
import unittest
from pathlib import Path

from task import journal, plan_blocking, plan_repair, terminal_policy


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

    def test_post_validation_must_repeat_exact_original_carrier_green(self):
        value = record()
        self.assertFalse(plan_repair.post_validation_complete(value))
        value["post_validation"] = [carrier(command="focused test", result="green")]
        self.assertFalse(plan_repair.post_validation_complete(value))
        value["post_validation"] = [carrier(result="green")]
        self.assertTrue(plan_repair.post_validation_complete(value))

    def test_completed_repair_no_longer_blocks_a_future_continuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp)
            completed = record(post_validation=[carrier(result="green")])
            event = journal.new_entry(
                plan_id="2026.09.09-№1-DEMO", item_id="P2.1", command="plan-audit",
                actor="frontier/xhigh", result="local-repair")
            event.update({"repair_decision": completed,
                          "repair_digest": plan_repair.digest(completed),
                          "repair_action": "repair-in-current-attempt"})
            (plan / "journal.jsonl").write_text(
                json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
            self.assertIsNone(plan_repair.latest_action(plan, item_id="P2.1"))

    def test_terminal_close_waits_for_exact_post_repair_carrier(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "2026.09.09-№1-DEMO"
            phase = plan / "phases" / "P2"
            phase.mkdir(parents=True)
            (plan / "plan.md").write_text(
                "## 0. Meta\n\n| Поле | Значение |\n|:--|:--|\n| Layout | v2 |\n",
                encoding="utf-8")
            (phase / "P2.md").write_text("# P2\n", encoding="utf-8")
            (phase / "P2.1.md").write_text("### P2.1 — repair\n", encoding="utf-8")
            observed = record()
            observed_event = journal.new_entry(
                plan_id=plan.name, item_id="P2.1", command="plan-audit",
                actor="frontier/xhigh", result="local-repair")
            observed_event.update({"repair_decision": observed,
                                   "repair_digest": plan_repair.digest(observed),
                                   "repair_action": "repair-in-current-attempt"})
            (plan / "journal.jsonl").write_text(
                json.dumps(observed_event, ensure_ascii=False) + "\n", encoding="utf-8")
            validation = [{"carrier": "focused", "status": "green",
                           "evidence_ids": ["test:green"]}]
            with self.assertRaisesRegex(terminal_policy.TerminalPolicyError,
                                        "REPAIR_POST_VALIDATION_REQUIRED"):
                terminal_policy.build_decision(
                    plan, "P2.1", result="closed-green", validation=validation)
            completed = record(post_validation=[carrier(result="green")])
            completed_event = journal.new_entry(
                plan_id=plan.name, item_id="P2.1", command="plan-audit",
                actor="frontier/xhigh", result="local-repair")
            completed_event.update({"repair_decision": completed,
                                    "repair_digest": plan_repair.digest(completed),
                                    "repair_action": "repair-in-current-attempt"})
            with (plan / "journal.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(completed_event, ensure_ascii=False) + "\n")
            terminal_policy.build_decision(
                plan, "P2.1", result="closed-green", validation=validation)

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
