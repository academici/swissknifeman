import json
import tempfile
import unittest
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan

from task import plan_migrate, plan_status
from task import journal


class PlanMigrateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source = write_valid_plan(self.root, "MIGRATION-FIXTURE")
        plan = (self.source / "plan.md").read_text(encoding="utf-8")
        plan += """\n## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-08-08 | Решение | Почему |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-08-08 | test | update |

## Обсуждение

Обсуждение.

## Historical Audit

Этот свободный исторический текст не имеет v2 runtime-carrier, но не должен исчезнуть.
"""
        (self.source / "plan.md").write_text(plan, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_dry_run_is_read_only_and_output_is_v2(self):
        before = (self.source / "plan.md").read_bytes()
        journal_before = (self.source / "journal.jsonl").read_text(encoding="utf-8")
        phase_before = {path.relative_to(self.source): path.read_bytes()
                        for path in (self.source / "phases").glob("P*.md")}
        output = self.root / "output"
        result = plan_migrate.migrate_safely(self.source, dry_run=True, output=output)
        self.assertEqual(before, (self.source / "plan.md").read_bytes())
        self.assertEqual(result["inventory"]["missing"], [])
        self.assertTrue((output / "phases" / "P1" / "P1.1.md").is_file())
        self.assertTrue((output / "phases" / "P1" / "P1.1.state.md").is_file())
        self.assertIn("| Layout | v2 |", (output / "plan.md").read_text(encoding="utf-8"))
        self.assertIn("| Version | 0.1.0 |", (output / "status.md").read_text(encoding="utf-8"))
        archive = output / "artifacts" / "migration-source-v1"
        manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest, result["source_archive"])
        self.assertEqual((archive / "plan.md").read_bytes(), before)
        self.assertNotIn("Этот свободный исторический текст",
                         (output / "plan.md").read_text(encoding="utf-8"))
        for relative, payload in phase_before.items():
            self.assertEqual((archive / relative).read_bytes(), payload)
        self.assertEqual((archive / "journal.jsonl").read_text(encoding="utf-8"), journal_before)
        self.assertIn("Layout v2 migration activation", (output / "journal.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(plan_status.build_status(output, check=True), output / "status.md")
        before_second_run = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
        plan_migrate.migrate(output)
        self.assertEqual(before_second_run, {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()})

    def test_v2_refuses_a_drifted_source_archive(self):
        output = self.root / "output"
        plan_migrate.migrate_safely(self.source, dry_run=True, output=output)
        (output / "artifacts" / "migration-source-v1" / "plan.md").write_text(
            "повреждено\n", encoding="utf-8")
        with self.assertRaisesRegex(plan_migrate.MigrationError, "архив исходника миграции повреждён"):
            plan_migrate.migrate(output)

    def test_requires_dry_run_and_output_for_every_source(self):
        with self.assertRaisesRegex(plan_migrate.MigrationError, "inplace-конвертер"):
            plan_migrate.migrate_safely(self.source)
        with self.assertRaisesRegex(plan_migrate.MigrationError, "требует явный --output"):
            plan_migrate.migrate_safely(self.source, dry_run=True)

    def test_output_inventory_has_all_item_ids(self):
        output = self.root / "output"
        plan_migrate.migrate_safely(self.source, dry_run=True, output=output)
        inventory = json.loads((output / "artifacts" / "p2-migration-inventory.json").read_text(encoding="utf-8"))
        self.assertEqual(inventory["item_ids"], ["P1.1"])
        self.assertEqual(inventory["missing"], [])

    def test_dry_run_preserves_absent_legacy_discussion(self):
        plan_path = self.source / "plan.md"
        plan_path.write_text(plan_path.read_text(encoding="utf-8").replace(
            "\n## Обсуждение\n\nОбсуждение.\n", "\n"), encoding="utf-8")
        output = self.root / "without-discussion"
        result = plan_migrate.migrate_safely(self.source, dry_run=True, output=output)
        discussion = [row for row in result["inventory"]["elements"]
                      if row["kind"] == "discussion"]
        self.assertEqual(discussion, [{"kind": "discussion", "present": False, "value": ""}])
        self.assertFalse((output / "decisions" / "legacy-discussion.md").exists())

    def test_dry_run_accepts_english_legacy_decision_headers(self):
        plan_path = self.source / "plan.md"
        plan_path.write_text(plan_path.read_text(encoding="utf-8").replace(
            "| D# | Дата | Решение | Почему |", "| D# | Date | Decision | Why |"), encoding="utf-8")
        output = self.root / "english-decisions"
        plan_migrate.migrate_safely(self.source, dry_run=True, output=output)
        self.assertTrue((output / "decisions" / "D1-legacy.md").is_file())

    def test_routing_comma_lists_are_split_without_other_cell_drift(self):
        cells = (
            "P0.1–P0.3, P0.5",
            "P1.1–P1.5, P6.1–P6.3",
            "P3.1, P3.3–P3.8",
            "P5.2–P5.3, P6.4–P6.5",
        )
        header = (
            "| Batch | Items | Model class/effort | Exec | Review | Почему |\n"
            "|:--|:--|:--|:--|:--|:--|"
        )
        source_rows = [
            f"| B{index} | {cell} | implementation/high | manual | full | keep bytes {index} |"
            for index, cell in enumerate(cells, start=1)
        ]

        rendered = plan_migrate._normalize_routing_rows(
            "\n".join((header, *source_rows)))

        expected_rows = []
        for index, cell in enumerate(cells, start=1):
            expected_rows.extend(
                f"| B{index} | {token.strip()} | implementation/high | manual | full | keep bytes {index} |"
                for token in cell.split(",")
            )
        self.assertEqual(rendered, "\n".join((header, *expected_rows)))

    def test_routing_comma_list_rejects_non_grammar_tokens(self):
        invalid = (
            "обсудить P1.1, P1.2",
            "P1.1, later",
            "P1.1–P2.1, P2.2",
            "P1.3–P1.1, P1.4",
            "P1.1,",
        )
        for cell in invalid:
            with self.subTest(cell=cell):
                body = (
                    "| Batch | Items | Model class/effort | Exec | Review | Почему |\n"
                    "|:--|:--|:--|:--|:--|:--|\n"
                    f"| B1 | {cell} | implementation/high | manual | full | test |"
                )
                with self.assertRaisesRegex(plan_migrate.MigrationError, "нельзя безопасно разбить"):
                    plan_migrate._normalize_routing_rows(body)

    def test_dry_run_materializes_legacy_blocked_journal_state(self):
        journal.append(self.source, journal.new_entry(
            plan_id=self.source.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="blocked",
        ))
        output = self.root / "blocked-output"
        plan_migrate.migrate_safely(self.source, dry_run=True, output=output)
        spec = (output / "phases" / "P1" / "P1.1.md").read_text(encoding="utf-8")
        state = (output / "phases" / "P1" / "P1.1.state.md").read_text(encoding="utf-8")
        self.assertIn("> 🔴 ESCALATION P1.1: migrated legacy blocked state", spec)
        self.assertIn("**Escalation Needed:** yes", state)
