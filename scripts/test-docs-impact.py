#!/usr/bin/env python3
"""P8.4 docs-impact gate conformance tests (2026.07.25-ECO-OPT)."""
from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("docs_impact", ROOT / "scripts/docs-impact.py")
docs_impact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(docs_impact)


def missing_count(entries):
    """Число классов (пакетов), которым не хватило доков — не число строк отчёта."""
    needed, credited = docs_impact.classify(entries)
    return len([klass for klass in needed if klass not in credited])


class DocsImpactTests(unittest.TestCase):
    def test_a_new_surface_file_without_docs_is_red(self):
        entries = [("A", "packages/maind/lib/maind/x.py")]
        self.assertEqual(missing_count(entries), 1)

    def test_b_new_surface_file_with_own_package_docs_is_green(self):
        entries = [
            ("A", "packages/maind/lib/maind/x.py"),
            ("A", "packages/maind/docs/y.md"),
        ]
        self.assertEqual(missing_count(entries), 0)

    def test_c_docs_of_a_different_package_do_not_credit(self):
        entries = [
            ("A", "packages/maind/lib/maind/x.py"),
            ("A", "packages/harness/docs/y.md"),
        ]
        self.assertEqual(missing_count(entries), 1)

    def test_d_editing_existing_lib_body_is_not_a_trigger(self):
        entries = [("M", "packages/maind/lib/maind/x.py")]
        self.assertEqual(missing_count(entries), 0)

    def test_e_editing_command_body_is_an_interface_trigger(self):
        entries = [("M", "packages/task/commands/plan-exec.md")]
        self.assertEqual(missing_count(entries), 1)
        entries_with_docs = entries + [("M", "docs/task/index.md")]
        self.assertEqual(missing_count(entries_with_docs), 0)

    def test_f_non_surface_paths_are_never_triggers(self):
        entries = [
            ("A", "packages/maind/tests/test_x.py"),
            ("A", "plans/2026.07.25-ECO-OPT/research/99.md"),
            ("A", "CHANGELOG.md"),
            ("A", "packages/skiller/skills/general/plan-protocol/SKILL.md"),
        ]
        self.assertEqual(missing_count(entries), 0)

    def test_g_escape_hatch_trailer_suppresses_failure_and_prints_reason(self):
        entries = [("A", "packages/maind/lib/maind/x.py")]
        os.environ["DOCS_NOT_NEEDED"] = "рефакторинг без изменения поведения"
        try:
            self.assertIsNotNone(docs_impact.escape_reason(None))
            code = docs_impact.run(entries, range_args=None)
        finally:
            del os.environ["DOCS_NOT_NEEDED"]
        self.assertEqual(code, 0)

    def test_g_empty_trailer_is_not_an_escape(self):
        entries = [("A", "packages/maind/lib/maind/x.py")]
        os.environ.pop("DOCS_NOT_NEEDED", None)
        code = docs_impact.run(entries, range_args=None)
        self.assertEqual(code, 1)

    def test_h_rename_of_a_surface_file_without_docs_is_red(self):
        entries = docs_impact.parse_name_status(
            "R100\tpackages/maind/lib/maind/old.py\tpackages/maind/lib/maind/new.py"
        )
        self.assertEqual(missing_count(entries), 1)

    def test_credited_package_docs_do_not_leak_across_classes(self):
        entries = [
            ("A", "packages/maind/lib/maind/x.py"),
            ("A", "packages/harness/lib/harness/y.py"),
            ("A", "packages/maind/docs/z.md"),
        ]
        self.assertEqual(missing_count(entries), 1)


if __name__ == "__main__":
    unittest.main()
