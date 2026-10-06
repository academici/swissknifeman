"""Recording parity (PLAN2 R27): splitting instructions by role drops no plan-recording obligation.

Each row pins one obligation W1-W12 (knowledge/instruction-split §recording-obligations) to a phrase
in the file that now owns it. Task files are read as text; orch never imports Task.
"""
from __future__ import annotations

from pathlib import Path
import unittest

ORCH = Path(__file__).resolve().parents[1]
TASK = ORCH.parent / "task"
REPO = ORCH.parents[1]

ROLES = ORCH / "roles"
PLAN_RUN = TASK / "commands/plan-run.md"
REFERENCES = TASK / "skills/plan-protocol/references"
REVIEWER_SELECTION = TASK / "references/reviewer-selection.md"
SCOUT = TASK / "lib/task/plan/scout.py"
PLAN2 = REPO / "plans/2026.10.05-№2-ORCH-PREP/plan.json"

REGISTRAR = ROLES / "registrar.md"
EXECUTOR = ROLES / "executor.md"
REVIEWER = ROLES / "reviewer.md"

OBLIGATIONS = [
    # W1: finish with recorded acceptance checks.
    ("W1", PLAN_RUN, "plan.py finish"),
    ("W1", PLAN_RUN, "--check V1="),
    ("W1", REGISTRAR, "--check V#="),
    ("W1", REGISTRAR, "--evidence V#="),
    ("W1", EXECUTOR, "`checks_run`"),
    # W2: finish notes with the item outcome.
    ("W2", PLAN_RUN, "--notes"),
    ("W2", REGISTRAR, '--notes "<summary>"'),
    # W3: deviation, escalation and pending notes.
    ("W3", PLAN_RUN, "--deviation"),
    ("W3", PLAN_RUN, "--escalation"),
    ("W3", REGISTRAR, "--deviation"),
    ("W3", REGISTRAR, "--escalation"),
    ("W3", REGISTRAR, "--pending"),
    # W4: friction events; the executor reports, the registrar logs.
    ("W4", PLAN_RUN, "plan.py log"),
    ("W4", REGISTRAR, "friction"),
    ("W4", REGISTRAR, "plan.py log <plan> <item> --type"),
    ("W4", EXECUTOR, "every plan-relevant surprise"),
    # W5: review verdict as a knowledge document plus a note event.
    ("W5", REFERENCES / "review-mode.md", "add-document"),
    ("W5", REFERENCES / "review-mode.md", "--type note"),
    ("W5", REGISTRAR, "plan.py add-document"),
    ("W5", REGISTRAR, "--type note"),
    ("W5", REVIEWER, "verdict"),
    # W6: actual reviewer and session in the note event.
    ("W6", REVIEWER_SELECTION, "actual reviewer/session"),
    ("W6", REGISTRAR, "actual reviewer route and session"),
    # W7: unit return with changed paths and the integrator's decision.
    ("W7", PLAN_RUN, "accept|rework|reject"),
    ("W7", REGISTRAR, "return --changed"),
    ("W7", REGISTRAR, "accept|rework|reject"),
    ("W7", EXECUTOR, "`changed_paths`"),
    # W8: one scoped commit per item by the coordinator.
    ("W8", PLAN_RUN, "One scoped commit"),
    ("W8", EXECUTOR, "`result_contract.commit_owner` is the coordinator"),
    # W9: the scout run logs one event (code).
    ("W9", SCOUT, 'store.new_event("scout"'),
    # W10: design decisions and long reasoning stay in plan JSON.
    ("W10", REFERENCES / "design-mode.md", "add-decision"),
    ("W10", REFERENCES / "design-mode.md", "`decide`"),
    # W11: no manufactured evidence.
    ("W11", REFERENCES / "common-principles.md", "Never manufacture evidence"),
    ("W11", REGISTRAR, "Never manufacture evidence"),
    ("W11", EXECUTOR, "Report a check that did not run"),
    # W12: raw research answers in the plan (a rule of this plan).
    ("W12", PLAN2, "@plan/research/"),
]

# Records that did not exist before the split (only additions, R27).
ADDITIONS = [
    ("executed_by", REGISTRAR, "--executed-by"),
    ("attempt_id", REGISTRAR, "--attempt-id"),
    ("check_evidence", REGISTRAR, "--evidence"),
]


def _present(path: Path) -> bool:
    """Task and the plan may be absent when orch is used outside this monorepo; the roles never are."""
    if path.is_relative_to(TASK):
        return TASK.is_dir()
    if path == PLAN2:
        return path.is_file()
    return True


class RecordParityTests(unittest.TestCase):
    def _assert_rows(self, rows):
        for key, path, phrase in rows:
            with self.subTest(obligation=key, file=str(path.relative_to(REPO)), phrase=phrase):
                if not _present(path):
                    self.skipTest(f"{path.relative_to(REPO)} is not in this checkout")
                self.assertTrue(path.is_file(), f"{path} is missing")
                self.assertIn(phrase, path.read_text(encoding="utf-8"))

    def test_every_obligation_has_an_owner_phrase(self):
        self._assert_rows(OBLIGATIONS)

    def test_new_records_are_kept(self):
        self._assert_rows(ADDITIONS)

    def test_table_covers_w1_to_w12(self):
        self.assertEqual({key for key, _, _ in OBLIGATIONS}, {f"W{n}" for n in range(1, 13)})


if __name__ == "__main__":
    unittest.main()
