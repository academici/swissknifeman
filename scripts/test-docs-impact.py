#!/usr/bin/env python3
"""P8.4 docs-impact gate conformance tests."""
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
    """Number of classes (packages), which did not have enough dockets - not the number of report lines."""
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
        entries = [("M", "packages/planner/commands/plan-run.md")]
        self.assertEqual(missing_count(entries), 1)
        entries_with_docs = entries + [("M", "docs/planner/index.md")]
        self.assertEqual(missing_count(entries_with_docs), 0)

    def test_f_non_surface_paths_are_never_triggers(self):
        entries = [
            ("A", "packages/maind/tests/test_x.py"),
            ("A", "plans/DEMO-1/research/99.md"),
            ("A", "CHANGELOG.md"),
            ("A", "packages/skiller/skills/general/plan-protocol/SKILL.md"),
        ]
        self.assertEqual(missing_count(entries), 0)

    def test_g_escape_hatch_trailer_suppresses_failure_and_prints_reason(self):
        entries = [("A", "packages/maind/lib/maind/x.py")]
        os.environ["DOCS_NOT_NEEDED"] = "refactoring without changing behavior"
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

    def test_foundation_docs_credit_aicore_only(self):
        entries = [
            ("A", "packages/aicore/lib/aicore/x.py"),
            ("A", "docs/architecture/decisions/0099-x.md"),
        ]
        self.assertEqual(missing_count(entries), 0)
        entries = [
            ("A", "packages/maind/lib/maind/x.py"),
            ("A", "docs/architecture/decisions/0099-x.md"),
        ]
        self.assertEqual(missing_count(entries), 1)

    def test_a_package_removed_as_a_whole_needs_no_docs(self):
        entries = [("D", "packages/gone/lib/gone/x.py"), ("D", "packages/gone/bin/gone")]
        needed, credited = docs_impact.classify(entries, exists=lambda path: False)
        self.assertIn("pkg:gone", credited)
        needed, credited = docs_impact.classify(entries, exists=lambda path: True)  # the folder is still there
        self.assertNotIn("pkg:gone", credited)
        mixed = entries + [("A", "packages/gone/lib/gone/y.py")]
        needed, credited = docs_impact.classify(mixed, exists=lambda path: False)
        self.assertNotIn("pkg:gone", credited)

    def test_the_worktree_mode_reads_uncommitted_and_untracked_changes(self):
        import subprocess
        import sys
        done = subprocess.run([sys.executable, str(ROOT / "scripts/docs-impact.py"), "--base", "HEAD", "--worktree"],
                              cwd=ROOT, capture_output=True, text=True)
        self.assertIn(done.returncode, (0, 1), done.stderr)
        self.assertTrue(done.stdout.startswith("docs-impact:"), done.stdout)


if __name__ == "__main__":
    unittest.main()
