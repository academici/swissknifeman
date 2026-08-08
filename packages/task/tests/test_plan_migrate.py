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
        self.source = write_valid_plan(self.root, plan_migrate.SELF_HOST_PLAN_ID)
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
"""
        (self.source / "plan.md").write_text(plan, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_dry_run_is_read_only_and_output_is_v2(self):
        before = (self.source / "plan.md").read_bytes()
        output = self.root / "output"
        result = plan_migrate.migrate_safely(self.source, dry_run=True, output=output)
        self.assertEqual(before, (self.source / "plan.md").read_bytes())
        self.assertEqual(result["inventory"]["missing"], [])
        self.assertTrue((output / "phases" / "P1" / "P1.1.md").is_file())
        self.assertTrue((output / "phases" / "P1" / "P1.1.state.md").is_file())
        self.assertIn("| Layout | v2 |", (output / "plan.md").read_text(encoding="utf-8"))
        self.assertIn("| Version | 0.1.0 |", (output / "status.md").read_text(encoding="utf-8"))
        self.assertEqual(plan_status.build_status(output, check=True), output / "status.md")
        before_second_run = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
        plan_migrate.migrate(output)
        self.assertEqual(before_second_run, {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()})

    def test_requires_both_dry_run_and_output_for_non_self_host(self):
        foreign = self.root / "FOREIGN"
        self.source.rename(foreign)
        with self.assertRaisesRegex(plan_migrate.MigrationError, "inplace-конвертер"):
            plan_migrate.migrate_safely(foreign)
        with self.assertRaisesRegex(plan_migrate.MigrationError, "требует явный --output"):
            plan_migrate.migrate_safely(foreign, dry_run=True)

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

    def test_dry_run_materializes_legacy_blocked_journal_state(self):
        journal.append(self.source, journal.new_entry(
            plan_id=plan_migrate.SELF_HOST_PLAN_ID, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="blocked",
        ))
        output = self.root / "blocked-output"
        plan_migrate.migrate_safely(self.source, dry_run=True, output=output)
        spec = (output / "phases" / "P1" / "P1.1.md").read_text(encoding="utf-8")
        state = (output / "phases" / "P1" / "P1.1.state.md").read_text(encoding="utf-8")
        self.assertIn("> 🔴 ESCALATION P1.1: migrated legacy blocked state", spec)
        self.assertIn("**Escalation Needed:** yes", state)
