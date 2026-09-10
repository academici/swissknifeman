"""Tests for the deterministic layout-v2 owner status projection."""
import json
import tempfile
import unittest
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:  # direct discovery from packages/task remains supported
    from fixtures import write_valid_plan
from task import plan_status
from task.plan_lint import Diagnostics, lint_plan


class PlanStatusTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.plan_dir = write_valid_plan(Path(self._tmp.name), "DEMO-V2", layout="v2")

    def tearDown(self):
        self._tmp.cleanup()

    def test_generates_fresh_owner_view_without_volatile_plan_core_fields(self):
        target = plan_status.build_status(self.plan_dir)
        self.assertEqual(target, self.plan_dir / "status.md")
        self.assertEqual(plan_status.build_status(self.plan_dir, check=True), target)
        core = (self.plan_dir / "plan.md").read_text(encoding="utf-8")
        view = target.read_text(encoding="utf-8")
        self.assertNotIn("## 4.", core)
        self.assertNotIn("## 6.", core)
        self.assertNotIn("| Version |", core)
        self.assertIn("| Version | — |", view)
        self.assertIn("| Status | 🟢 Done |", view)

    def test_check_rejects_manual_status_view_drift(self):
        target = self.plan_dir / "status.md"
        target.write_text(target.read_text(encoding="utf-8") + "\nmanual drift\n", encoding="utf-8")
        with self.assertRaises(plan_status.StatusError):
            plan_status.build_status(self.plan_dir, check=True)

    def test_preserves_converter_version_marker(self):
        core = self.plan_dir / "plan.md"
        core.write_text(core.read_text(encoding="utf-8") + "\n<!-- migration-version: 7.2.1 -->\n", encoding="utf-8")
        plan_status.build_status(self.plan_dir)
        self.assertIn("| Version | 7.2.1 |", (self.plan_dir / "status.md").read_text(encoding="utf-8"))

    def test_phase_with_only_terminal_deviations_is_terminal(self):
        state = self.plan_dir / "phases" / "P1" / "P1.1.state.md"
        state.write_text(state.read_text(encoding="utf-8").replace(
            "**Status:** 🟢 Done", "**Status:** 🟠 Done with deviations"), encoding="utf-8")
        self.assertEqual(plan_status.status_model(self.plan_dir)["phases"][0]["status"],
                         "🟠 Done with deviations")

    def test_projects_continue_first_correction_outcome(self):
        event = {
            "ts": "2026-09-10T12:00:00Z", "item_id": "P1.1", "actor": "frontier/xhigh",
            "decision": {
                "signal_class": "producer-readiness", "scope_class": "item",
                "action": "repair-in-current-attempt", "recovered": True,
                "terminal": False, "reason_code": "PRODUCER_REPAIR_REQUIRED",
                "observed_mode": "stale-derived",
            },
        }
        with (self.plan_dir / "journal.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        model = plan_status.status_model(self.plan_dir)
        self.assertIn(
            ("routing", "P1.1", "stale-derived → repair-in-current-attempt", "—"),
            model["corrections"],
        )

    def test_owner_gated_terminal_block_close_projects_phase_deviations_without_rewriting_item(self):
        state = self.plan_dir / "phases" / "P1" / "P1.1.state.md"
        state.write_text(state.read_text(encoding="utf-8").replace(
            "**Status:** 🟢 Done", "**Status:** 🔴 Blocked").replace(
            "**Escalation Needed:** no", "**Escalation Needed:** yes"), encoding="utf-8")
        specification = self.plan_dir / "phases" / "P1" / "P1.1.md"
        specification.write_text(specification.read_text(encoding="utf-8") +
                                 "\n> 🔴 ESCALATION P1.1: historical terminal block retained.\n",
                                 encoding="utf-8")
        decisions = self.plan_dir / "decisions"
        (decisions / "D2-terminal-blocked-close.md").write_text(
            "---\n"
            "id: D2\n"
            "date: 2026-08-17\n"
            "status: accepted\n"
            "item: P1\n"
            "items: [P1, P1.1]\n"
            "supersedes: []\n"
            "superseded_by: null\n"
            "---\n\n"
            "## Решение\n\n"
            "`phase-close: terminal-blocked-deviations`\n\n"
            "## Почему\n\n"
            "test\n",
            encoding="utf-8",
        )
        event = {
            "ts": "2026-08-17T12:00:00Z", "plan_id": "DEMO-V2", "item_id": "P1",
            "command": "plan-close", "session_id": None, "run_id": None, "attempt": 1,
            "actor": "repository_owner", "friction": ["deviation"],
            "result": "closed-deviations", "cost_usd": None, "num_turns": None,
            "duration_ms": None, "note": "owner-gated terminal blocked phase closure",
            "decision": {
                "signal_class": "authority", "scope_class": "phase",
                "action": "phase-close-terminal-blocked-deviations", "recovered": False,
                "terminal": True, "owner_decision": "D2",
            },
        }
        with (self.plan_dir / "journal.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

        model = plan_status.status_model(self.plan_dir)
        self.assertEqual(model["phases"][0]["status"], "🟠 Done with deviations")
        self.assertIn("**Status:** 🔴 Blocked", state.read_text(encoding="utf-8"))
        plan_status.build_status(self.plan_dir)
        diagnostics = Diagnostics()
        lint_plan(self.plan_dir, diagnostics)
        self.assertEqual(diagnostics.errors, [])

    def test_mixed_terminal_and_not_started_items_are_in_progress_for_phase_and_plan(self):
        source_phase = self.plan_dir / "phases" / "P1"
        phase = self.plan_dir / "phases" / "P2"
        phase.mkdir()
        (phase / "P2.md").write_text(
            (source_phase / "P1.md").read_text(encoding="utf-8").replace("# P1", "# P2", 1),
            encoding="utf-8",
        )
        specification = (source_phase / "P1.1.md").read_text(encoding="utf-8")
        state = (source_phase / "P1.1.state.md").read_text(encoding="utf-8")
        (phase / "P2.1.md").write_text(specification.replace("P1.1", "P2.1"), encoding="utf-8")
        (phase / "P2.1.state.md").write_text(state, encoding="utf-8")
        (phase / "P2.2.md").write_text(specification.replace("P1.1", "P2.2"), encoding="utf-8")
        (phase / "P2.2.state.md").write_text(
            state.replace("**Status:** 🟢 Done", "**Status:** ⬜ Not started"), encoding="utf-8"
        )

        model = plan_status.status_model(self.plan_dir)

        self.assertEqual(next(phase for phase in model["phases"] if phase["id"] == "P2")["status"],
                         "🟡 In progress")
        self.assertEqual(model["meta"]["Status"], "🟡 In progress")

    def test_linter_reads_v2_meta_and_board_from_owner_view(self):
        diagnostics = Diagnostics()
        model = lint_plan(self.plan_dir, diagnostics)
        self.assertEqual(diagnostics.errors, [])
        self.assertEqual(model["meta"]["Status"], "🟢 Done")
        self.assertEqual(model["status_board"][0]["Phase"], "P1")

    def test_overlong_historical_note_projects_to_exact_line_pointer(self):
        journal = self.plan_dir / "journal.jsonl"
        entry = json.loads(journal.read_text(encoding="utf-8"))
        entry["note"] = "x" * 301
        raw = json.dumps(entry, ensure_ascii=False) + "\n"
        journal.write_text(raw, encoding="utf-8")

        plan_status.build_status(self.plan_dir)
        view = (self.plan_dir / "status.md").read_text(encoding="utf-8")
        self.assertIn("полный текст: journal.jsonl:1", view)
        self.assertNotIn("x" * 301, view)
        self.assertEqual(journal.read_text(encoding="utf-8"), raw)
