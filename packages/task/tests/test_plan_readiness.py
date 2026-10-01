import unittest
import json
import tempfile
from pathlib import Path

from task import journal, plan_readiness

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan


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
            (plan / "plan.md").write_text("## 0. Meta\n\n| Field | Meaning |\n|:--|:--|\n| Layout | v2 |\n", encoding="utf-8")
            (phase / "P2.md").write_text("# P2\n\n### P2.2 — producer\n\n**Deliverables:** `producer-readiness/v1`: consumer=P2.3; modes=nonempty-candidates|empty-by-decision.\n", encoding="utf-8")
            (phase / "P2.2.md").write_text("# P2.2\n", encoding="utf-8")
            # Minimal fixture has no parseable full item; validate the builder's additive API.
            decision = terminal_policy.build_decision(plan, "P2.2", result="closed-green", validation=[{"carrier": "test", "status": "green", "evidence_ids": ["test:ok"]}], producer_readiness=self.readiness())
            self.assertEqual(decision["producer_readiness"]["consumer_item"], "P2.3")

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

    def test_empty_readiness_requires_one_accepted_owner_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp)
            (plan / "decisions").mkdir()
            empty = self.readiness(mode="empty-by-decision", candidate_count=0,
                                   owner_decision="D7", exclusions=["approved no-op"])
            with self.assertRaisesRegex(plan_readiness.ReadinessError, "accepted owner"):
                plan_readiness.validate_readiness(empty, plan_dir=plan)
            (plan / "decisions" / "D7-empty.md").write_text(
                "---\nid: D7\nstatus: accepted\n---\n", encoding="utf-8")
            plan_readiness.validate_readiness(empty, plan_dir=plan)

    def test_correction_reducer_continues_verified_and_repairs_missing(self):
        expected = {
            "approved-no-op": "continue-current",
            "valid-output": "continue-current",
            "stale-derived": "repair-in-current-attempt",
            "missing-or-corrupt": "repair-in-current-attempt",
            "contract-conflict": "gather-evidence",
        }
        for observed_mode, action in expected.items():
            with self.subTest(observed_mode=observed_mode):
                self.assertEqual(plan_readiness.correction_decision(
                    observed_mode=observed_mode)["action"], action)
        with self.assertRaisesRegex(plan_readiness.ReadinessError, "forbids re-entry"):
            plan_readiness.correction_decision(
                observed_mode="approved-no-op",
                reentry={
                    "schema_version": "phase-reentry-justification/v1", "phase_id": "P2",
                    "trigger": "owner-decision-change", "evidence_ids": ["D7"],
                    "origin_item": "P2.2", "resume_item": "P2.3",
                },
            )

    def test_terminal_phase_design_requires_reentry_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp)
            phase = plan / "phases" / "P2"
            phase.mkdir(parents=True)
            (plan / "plan.md").write_text(
                "## 0. Meta\n\n| Field | Meaning |\n|:--|:--|\n| Layout | v2 |\n",
                encoding="utf-8")
            (plan / "journal.jsonl").write_text("", encoding="utf-8")
            (phase / "P2.md").write_text("# P2\n", encoding="utf-8")
            (phase / "P2.1.md").write_text("### P2.1 — done\n", encoding="utf-8")
            (phase / "P2.1.state.md").write_text("**Status:** 🟢 Done\n", encoding="utf-8")
            with self.assertRaisesRegex(plan_readiness.ReadinessError,
                                        "PHASE_REENTRY_UNJUSTIFIED"):
                plan_readiness.validate_design_target(plan, "P2")
            reentry = {
                "schema_version": "phase-reentry-justification/v1", "phase_id": "P2",
                "trigger": "terminal-evidence-invalid", "evidence_ids": ["audit:P2"],
                "origin_item": "P2.1", "resume_item": "P2.1",
            }
            decision = plan_readiness.correction_decision(
                observed_mode="contract-conflict", reentry=reentry)
            event = journal.new_entry(
                plan_id="DEMO", item_id="P2", command="plan-audit",
                actor="frontier/xhigh", result="local-repair", decision=decision)
            (plan / "journal.jsonl").write_text(
                json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
            plan_readiness.validate_design_target(plan, "P2")

    def test_generated_design_handoff_rejects_a_detailed_unfinished_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), "READY-PHASE", layout="v2")
            state = plan / "phases" / "P1" / "P1.1.state.md"
            state.write_text(state.read_text(encoding="utf-8").replace(
                "🟢 Done", "⬜ Not started"), encoding="utf-8")
            with self.assertRaisesRegex(plan_readiness.ReadinessError, "PLAN_DESIGN_NOT_NEEDED"):
                plan_readiness.validate_design_handoff_target(plan, "P1")

    def test_generated_design_handoff_accepts_a_skeleton_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), "SKELETON-PHASE", layout="v2")
            state = plan / "phases" / "P1" / "P1.1.state.md"
            state.write_text(state.read_text(encoding="utf-8").replace(
                "🟢 Done", "⬜ Not started"), encoding="utf-8")
            index = plan / "phases" / "P1" / "P1.md"
            index.write_text(index.read_text(encoding="utf-8")
                             + "\n> SKELETON — not detailed\n", encoding="utf-8")
            plan_readiness.validate_design_handoff_target(plan, "P1")

    def test_design_accepts_backlog_only_skeleton_but_rejects_missing_target(self):
        from task import plan_layout

        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), "BACKLOG-PHASE", layout="v2")
            backlog = plan / "backlog"
            backlog.mkdir()
            target = backlog / "P2.md"
            target.write_text("# P2\n\n> SKELETON — not detailed\n", encoding="utf-8")
            for validator in (plan_readiness.validate_design_target,
                              plan_readiness.validate_design_handoff_target):
                with self.subTest(validator=validator.__name__):
                    validator(plan, "P2")
                    with self.assertRaises(plan_layout.PlanLayoutError):
                        validator(plan, "P3")
                    target.write_text("# P2\n", encoding="utf-8")
                    with self.assertRaises(plan_layout.PlanLayoutError):
                        validator(plan, "P2")
                    target.write_text("# P2\n\n> SKELETON — not detailed\n", encoding="utf-8")

    def test_all_three_reentry_triggers_reduce_to_reopen(self):
        for trigger in ("owner-decision-change", "terminal-evidence-invalid",
                        "safety-or-authority-boundary"):
            with self.subTest(trigger=trigger):
                reentry = {
                    "schema_version": "phase-reentry-justification/v1", "phase_id": "P2",
                    "trigger": trigger, "evidence_ids": [f"evidence:{trigger}"],
                    "origin_item": "P2.2", "resume_item": "P2.3",
                }
                self.assertEqual(plan_readiness.correction_decision(
                    observed_mode="contract-conflict", reentry=reentry)["action"],
                    "reopen-phase")

    def test_priority_fix_binds_exact_declared_dispatch_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp)
            branch = {
                "schema_version": "fix-branch/v1", "origin_item": "P2.2", "owner": "task",
                "scope": "bounded repair", "priority": "priority", "rollback": "revert",
                "validation": "python3 -m unittest", "target_item": "P3.1",
                "resume_item": "P2.3",
            }
            decision = plan_readiness.correction_decision(
                observed_mode="contract-conflict", fix_branch=branch,
                declared_items=("P3.1",))
            event = journal.new_entry(
                plan_id="DEMO", item_id="P2.2", command="plan-audit",
                actor="frontier/xhigh", result="local-repair", decision=decision)
            (plan / "journal.jsonl").write_text(
                json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
            plan_readiness.validate_execution_target(plan, ["P3.1"])
            with self.assertRaisesRegex(plan_readiness.ReadinessError,
                                        "PRIORITY_FIX_TARGET_MISMATCH"):
                plan_readiness.validate_execution_target(plan, ["P2.3"])
            with (plan / "journal.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(journal.new_entry(
                    plan_id="DEMO", item_id="P3.1", command="plan-run",
                    actor="implementation/high", result="in-progress")) + "\n")
            self.assertIsNone(plan_readiness.latest_correction(plan))

    def test_correction_decision_cannot_terminalize_an_item(self):
        from task import terminal_policy
        decision = plan_readiness.correction_decision(observed_mode="valid-output")
        with self.assertRaisesRegex(terminal_policy.TerminalPolicyError,
                                    "READINESS_DECISION_NONTERMINAL"):
            terminal_policy.validate_entry({
                "item_id": "P2.2", "command": "plan-run", "result": "closed-green",
                "decision": decision,
            })
