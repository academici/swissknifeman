"""Recording parity (PLAN2 R27): splitting instructions by role drops no plan-recording obligation.

Each row pins one obligation W1-W12 (knowledge/instruction-split §recording-obligations) to a phrase in the file
that now owns it. The report → plan map moved from orch's registrar role into this bridge (P7.3): its rows name
the bridge README and the register code. Rows owned by orch roles are read only when orch is found; the plan row
only in this monorepo. A dry run of ``register`` proves the map is executable, not only written down.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import bridge_fixture
import partner

TASK = bridge_fixture.TASK
BRIDGE = bridge_fixture.BRIDGE
ORCH = partner.find_orch_root()
REPO = TASK.parents[1]

PLAN_RUN = TASK / "commands/plan-run.md"
REFERENCES = TASK / "skills/plan-protocol/references"
REVIEWER_SELECTION = TASK / "references/reviewer-selection.md"
SCOUT = TASK / "lib/task/plan/scout.py"
PLAN2 = REPO / "plans/2026.10.05-№2-ORCH-PREP/plan.json"

BRIDGE_README = BRIDGE / "README.md"
REGISTER_PY = BRIDGE / "register.py"
REGISTER_REVIEW_PY = BRIDGE / "register_review.py"

REGISTRAR = ("orch", "roles/registrar.md")
EXECUTOR = ("orch", "roles/executor.md")
REVIEWER = ("orch", "roles/reviewer.md")

OBLIGATIONS = [
    # W1: finish with recorded acceptance checks.
    ("W1", PLAN_RUN, "plan.py finish"),
    ("W1", PLAN_RUN, "--check V1="),
    ("W1", BRIDGE_README, "--check V#=<exit>"),
    ("W1", BRIDGE_README, "--evidence V#=PATH"),
    ("W1", REGISTER_PY, '"--check"'),
    ("W1", REGISTER_PY, '"--evidence"'),
    ("W1", EXECUTOR, "`checks_run`"),
    # W2: finish notes with the item outcome.
    ("W2", PLAN_RUN, "--notes"),
    ("W2", BRIDGE_README, '--notes "<summary>'),
    ("W2", REGISTER_PY, '"--notes"'),
    # W3: deviation, escalation and pending notes.
    ("W3", PLAN_RUN, "--deviation"),
    ("W3", PLAN_RUN, "--escalation"),
    ("W3", REGISTER_PY, '"--deviation"'),
    ("W3", REGISTER_PY, '"--escalation"'),
    ("W3", REGISTER_PY, '"--pending"'),
    # W4: friction events; the executor reports, the bridge logs.
    ("W4", PLAN_RUN, "plan.py log"),
    ("W4", BRIDGE_README, "friction"),
    ("W4", BRIDGE_README, "log <plan> <item> --type"),
    ("W4", REGISTER_PY, '"log"'),
    ("W4", REGISTER_PY, '"--type"'),
    ("W4", EXECUTOR, "every plan-relevant surprise"),
    # W5: review verdict as a knowledge document plus a note event.
    ("W5", REFERENCES / "review-mode.md", "add-document"),
    ("W5", REFERENCES / "review-mode.md", "--type note"),
    ("W5", REGISTER_REVIEW_PY, '"add-document"'),
    ("W5", REGISTER_REVIEW_PY, '"note"'),
    ("W5", REVIEWER, "verdict"),
    # W6: actual reviewer and session in the note event.
    ("W6", REVIEWER_SELECTION, "actual reviewer/session"),
    ("W6", BRIDGE_README, "actual reviewer route and session"),
    # W7: unit return with changed paths and the integrator's decision.
    ("W7", PLAN_RUN, "accept|rework|reject"),
    ("W7", BRIDGE_README, "accept|rework|reject"),
    ("W7", REGISTER_PY, '"return"'),
    ("W7", REGISTER_PY, '"--changed"'),
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
    ("W11", BRIDGE_README, "Never manufacture evidence"),
    ("W11", REGISTRAR, "Never manufacture evidence"),
    ("W11", EXECUTOR, "Report a check that did not run"),
    # W12: raw research answers in the plan (a rule of this plan).
    ("W12", PLAN2, "@plan/research/"),
]

# Records that did not exist before the split (only additions, R27).
ADDITIONS = [
    ("executed_by", REGISTER_PY, '"--executed-by"'),
    ("attempt_id", REGISTER_PY, '"--attempt-id"'),
    ("check_evidence", REGISTER_PY, '"--evidence"'),
]

ISSUES = [{"text": f"{kind} issue", "kind": kind}
          for kind in ("pending", "deviation", "blocker", "difficulty", "assumption", "note")]
REPORT = {"summary": "done", "changed_paths": ["lib/a.py"], "evidence": ["@plan/ev/V1.json"], "open_issues": ISSUES,
          "checks_run": [{"id": "V1", "cmd": "make", "exit": 0}, {"id": "V2", "cmd": "make lint", "exit": 0}]}


def _resolve(owner) -> Path | None:
    """A path, or None when the owner (orch, this monorepo's plan) is not in this checkout."""
    if isinstance(owner, tuple):
        return ORCH / owner[1] if ORCH else None
    if owner == PLAN2 and not owner.is_file():
        return None
    return owner


class RecordParityTests(unittest.TestCase):
    def _assert_rows(self, rows):
        for key, owner, phrase in rows:
            path = _resolve(owner)
            name = "/".join(owner) if isinstance(owner, tuple) else owner.name
            with self.subTest(obligation=key, file=name, phrase=phrase):
                if path is None:
                    self.skipTest(f"{name} is not in this checkout")
                self.assertTrue(path.is_file(), f"{path} is missing")
                self.assertIn(phrase, path.read_text(encoding="utf-8"))

    def test_every_obligation_has_an_owner_phrase(self):
        self._assert_rows(OBLIGATIONS)

    def test_new_records_are_kept(self):
        self._assert_rows(ADDITIONS)

    def test_table_covers_w1_to_w12(self):
        self.assertEqual({key for key, _, _ in OBLIGATIONS}, {f"W{n}" for n in range(1, 13)})


class ExecutableParityTests(unittest.TestCase):
    """``register --dry-run`` on a report with every issue kind and evidence emits every mapped flag."""

    def dry_run(self, report, ref, *extra) -> list[list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            done = bridge_fixture.plan_py(tmp, "bridge", "orch", "register", "PLAN9", ref, "--report", str(path),
                                          "--actor", "codex/gpt-5.5/high", "--executed-by", "codex/gpt-5.5/high",
                                          "--attempt-id", "a1", "--dry-run", *extra)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_item_dry_run_emits_every_item_flag(self):
        calls = self.dry_run(REPORT, "P1.1", "--status", "done_with_deviations", "--evidence", "V1=@plan/ev/V1.json")
        flags = {token for argv in calls for token in argv if token.startswith("--")}
        self.assertLessEqual({"--notes", "--check", "--evidence", "--deviation", "--pending", "--type", "--summary",
                              "--actor", "--executed-by", "--attempt-id"}, flags)
        types = {argv[argv.index("--type") + 1] for argv in calls if argv[0] == "log"}
        self.assertEqual(types, {"deviation", "blocker", "difficulty", "assumption", "note"})
        self.assertEqual([argv[0] for argv in calls][-1], "finish")

    def test_blocked_dry_run_emits_escalation(self):
        report = {**REPORT, "open_issues": [{"text": "owner decides", "kind": "escalation"}]}
        calls = self.dry_run(report, "P1.1", "--status", "blocked")
        self.assertIn("--escalation", calls[-1])

    def test_unit_dry_run_emits_return_with_changed(self):
        calls = self.dry_run({**REPORT, "open_issues": []}, "P1.1/U1")
        self.assertEqual(calls[-1][:5], ["unit", "PLAN9", "P1.1", "U1", "return"])
        self.assertIn("--changed", calls[-1])


if __name__ == "__main__":
    unittest.main()
