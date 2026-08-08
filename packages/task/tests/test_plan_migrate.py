import json
import tempfile
import unittest
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan

from task import plan_migrate, plan_status


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
