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

    def test_terminal_builder_accepts_declared_readiness(self):
        from task import terminal_policy
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp)
            phase = plan / "phases" / "P2"
            phase.mkdir(parents=True)
            (plan / "plan.md").write_text("## 0. Meta\n\n| Поле | Значение |\n|:--|:--|\n| Layout | v2 |\n", encoding="utf-8")
            (phase / "P2.md").write_text("# P2\n\n### P2.2 — producer\n\n**Deliverables:** `producer-readiness/v1`: consumer=P2.3; modes=nonempty-candidates|empty-by-decision.\n", encoding="utf-8")
            (phase / "P2.2.md").write_text("# P2.2\n", encoding="utf-8")
            # Minimal fixture has no parseable full item; validate the builder's additive API.
            decision = terminal_policy.build_decision(plan, "P2.2", result="closed-green", validation=[{"carrier": "test", "status": "green", "evidence_ids": ["test:ok"]}], producer_readiness=self.readiness())
            self.assertEqual(decision["producer_readiness"]["consumer_item"], "P2.3")

    def test_archive_contract_has_no_brain_precondition(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "commands" / "plan-close.md").read_text(encoding="utf-8")
        archive = source.split("## Режим `archive <ID>`", 1)[1].split("## Delivery receipt", 1)[0]
        self.assertIn("не разрешает, не ищет и не вызывает Brain", archive)
        self.assertNotIn("синк\n   зеркала в Brain", archive)

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
