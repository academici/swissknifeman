"""Next plan identity: day ordinal and repository-wide Short ID over live + archive plans."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fixtures  # noqa: F401 — puts lib/ on sys.path

from task import plan_numbering

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "plan-id.py"


def make_plan(root: Path, name: str, short_id: str | None = None, archived: bool = False):
    base = root / "archive" / name if archived else root / name
    base.mkdir(parents=True)
    meta = "| Field | Value |\n|:--|:--|\n"
    if short_id:
        meta += f"| Short ID | {short_id} |\n"
    (base / "plan.md").write_text(f"# {name}\n\n## 1. Meta\n\n{meta}", encoding="utf-8")


class PlanNumberingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "plans"
        self.root.mkdir()

    def test_empty_repository_starts_at_one(self):
        result = plan_numbering.next_identity(self.root, date="2026.10.01", codename="DEMO-NEW")
        self.assertEqual((result["ordinal"], result["short_id"]), (1, "PLAN1"))
        self.assertEqual(result["plan_id"], "2026.10.01-№1-DEMO-NEW")
        self.assertEqual(result["title_prefix"], "План №1 —")

    def test_missing_plans_directory_is_an_empty_repository(self):
        result = plan_numbering.next_identity(self.root / "absent", date="2026.10.01")
        self.assertEqual((result["ordinal"], result["short_id"], result["plan_id"]), (1, "PLAN1", None))

    def test_ordinal_increments_within_the_date_across_live_and_archive(self):
        make_plan(self.root, "2026.10.01-№1-DEMO-A")
        make_plan(self.root, "2026.10.01-№3-DEMO-B", archived=True)
        make_plan(self.root, "2026.09.30-№7-DEMO-OTHER-DAY")
        self.assertEqual(plan_numbering.next_identity(self.root, date="2026.10.01")["ordinal"], 4)
        self.assertEqual(plan_numbering.next_identity(self.root, date="2026.10.02")["ordinal"], 1)

    def test_short_id_is_global_max_plus_one_including_archive(self):
        make_plan(self.root, "2026.09.01-№1-DEMO-A", "PLAN2")
        make_plan(self.root, "2026.08.01-№1-DEMO-OLD", "PLAN9", archived=True)
        make_plan(self.root, "2026.08.02-DEMO-LEGACY")
        result = plan_numbering.next_identity(self.root, date="2026.10.01")
        self.assertEqual(result["short_id"], "PLAN10")
        self.assertEqual(result["scanned"]["plans"], 3)
        self.assertEqual(result["scanned"]["with_short_id"], 2)

    def test_live_and_archive_copies_of_one_plan_count_once(self):
        make_plan(self.root, "2026.10.01-№1-DEMO-A", "PLAN1")
        make_plan(self.root, "2026.10.01-№1-DEMO-A", "PLAN1", archived=True)
        result = plan_numbering.next_identity(self.root, date="2026.10.01")
        self.assertEqual((result["ordinal"], result["short_id"], result["scanned"]["plans"]), (2, "PLAN2", 1))

    def test_legacy_undated_ordinal_ids_do_not_count_as_ordinals(self):
        make_plan(self.root, "2026.10.01-DEMO-LEGACY")
        self.assertEqual(plan_numbering.next_identity(self.root, date="2026.10.01")["ordinal"], 1)

    def test_existing_plan_id_collision_and_bad_input_are_typed(self):
        make_plan(self.root, "2026.10.01-№1-DEMO-A")
        for kwargs, code in (({"date": "2026-10-01"}, "PLAN_NUMBER_DATE_INVALID"),
                             ({"date": "2026.10.01", "codename": "bad name"}, "PLAN_NUMBER_CODENAME_INVALID")):
            with self.assertRaises(plan_numbering.NumberingError) as caught:
                plan_numbering.next_identity(self.root, **kwargs)
            self.assertEqual(caught.exception.code, code)
        # The allocator never proposes an existing id: the next ordinal is free by construction.
        self.assertEqual(plan_numbering.next_identity(self.root, date="2026.10.01", codename="DEMO-A")["plan_id"],
                         "2026.10.01-№2-DEMO-A")

    def test_cli_prints_json_and_finds_plans_from_a_nested_directory(self):
        make_plan(self.root, "2026.10.01-№1-DEMO-A", "PLAN1")
        nested = self.root.parent / "src" / "deep"
        nested.mkdir(parents=True)
        done = subprocess.run([sys.executable, str(SCRIPT), "--date", "2026.10.01", "--codename", "DEMO-NEXT"],
                              cwd=nested, capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        value = json.loads(done.stdout)
        self.assertEqual((value["plan_id"], value["short_id"]), ("2026.10.01-№2-DEMO-NEXT", "PLAN2"))
        bad = subprocess.run([sys.executable, str(SCRIPT), "--date", "bad"], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stderr)["error"], "PLAN_NUMBER_DATE_INVALID")


if __name__ == "__main__":
    unittest.main()
