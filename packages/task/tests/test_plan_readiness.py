import unittest

from task import plan_readiness


class PlanReadinessTest(unittest.TestCase):
    def readiness(self, **changes):
        value = {
            "schema_version": "producer-readiness/v1", "producer_item": "P2.2",
            "consumer_item": "P2.3", "mode": "nonempty-candidates", "roots": ["packages/task"],
            "command": "python3 verify.py", "candidate_count": 1,
            "candidate_paths_sha256": "a" * 64, "source_commit": "a" * 40,
            "predicate": "declared paths", "exclusions": [],
        }
        value.update(changes)
        return value

    def test_nonempty_and_decided_empty_are_the_only_valid_modes(self):
        plan_readiness.validate_readiness(self.readiness())
        empty = self.readiness(mode="empty-by-decision", candidate_count=0,
                               owner_decision="D7", exclusions=["approved no-op"])
        plan_readiness.validate_readiness(empty)
        with self.assertRaises(plan_readiness.ReadinessError):
            plan_readiness.validate_readiness(self.readiness(candidate_count=0))

    def test_directive_is_exact_and_projection_is_digest_bound(self):
        directive = plan_readiness.directive(
            "`producer-readiness/v1`: consumer=P2.3; modes=nonempty-candidates|empty-by-decision.")
        self.assertEqual(directive["consumer_item"], "P2.3")
        projection = plan_readiness.terminal_projection(self.readiness())
        self.assertEqual(projection["mode"], "nonempty-candidates")
        self.assertEqual(len(projection["digest"]), 64)

    def test_fix_branch_requires_a_declared_target(self):
        record = {"schema_version": "fix-branch/v1", "origin_item": "P2.2", "owner": "task",
                  "scope": "repair", "priority": "priority", "rollback": "revert",
                  "validation": "python -m unittest", "target_item": "P2.3", "resume_item": "P2.3"}
        plan_readiness.validate_fix_branch(record, declared_items=("P2.3",))
        with self.assertRaises(plan_readiness.ReadinessError):
            plan_readiness.validate_fix_branch(record, declared_items=("P2.4",))

    def test_reentry_and_priority_fix_are_closed(self):
        plan_readiness.validate_reentry({
            "schema_version": "phase-reentry-justification/v1", "phase_id": "P2",
            "trigger": "terminal-evidence-invalid", "evidence_ids": ["journal:4"],
            "origin_item": "P2.2", "resume_item": "P2.3",
        })
        with self.assertRaises(plan_readiness.ReadinessError):
            plan_readiness.validate_reentry({
                "schema_version": "phase-reentry-justification/v1", "phase_id": "P2",
                "trigger": "stale-view", "evidence_ids": ["journal:4"],
                "origin_item": "P2.2", "resume_item": "P2.3",
            })
