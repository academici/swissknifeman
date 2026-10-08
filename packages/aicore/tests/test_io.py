"""Tests assert_safe_replace_target/atomic_write_text (P8.7) — 4 target class + tmp-cleanup.

aicore tests/test_util.py already covers creating parents/indent/mode/tmp-cleanup when
os.replace-falling; here is ONLY a new goal invariant (do not duplicate)."""
import os
import tempfile
import unittest
from pathlib import Path

from aicore.util.io import assert_safe_replace_target, atomic_write_text


class TestAssertSafeReplaceTarget(unittest.TestCase):
    def test_missing_target_is_norm(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "nope.txt"
            assert_safe_replace_target(p)  # should not throw

    def test_regular_file_is_norm(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            p.write_text("x")
            assert_safe_replace_target(p)  # should not throw

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.txt"
            real.write_text("x")
            link = Path(tmp) / "link.txt"
            link.symlink_to(real)
            with self.assertRaises(OSError) as ctx:
                assert_safe_replace_target(link)
            self.assertIn("link", str(ctx.exception))

    def test_hardlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.txt"
            real.write_text("x")
            hard = Path(tmp) / "hard.txt"
            os.link(real, hard)
            with self.assertRaises(OSError) as ctx:
                assert_safe_replace_target(hard)
            self.assertIn("st_nlink", str(ctx.exception))


class TestAtomicWriteTextTargetCheck(unittest.TestCase):
    def test_write_rejects_symlink_target_and_cleans_tmp(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.txt"
            real.write_text("original")
            link = Path(tmp) / "link.txt"
            link.symlink_to(real)
            with self.assertRaises(OSError):
                atomic_write_text(link, "new")
            self.assertEqual(list(Path(tmp).rglob("*.tmp")), [])
            # the target was not replaced - the silent unbinding of the symlink did not occur
            self.assertEqual(real.read_text(), "original")

    def test_write_check_target_false_allows_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.txt"
            real.write_text("original")
            link = Path(tmp) / "link.txt"
            link.symlink_to(real)
            atomic_write_text(link, "new", check_target=False)
            # os.replace(tmp, link) replaces the link itself with regular-file - expected
            # point switch behavior, no default invariant regress
            self.assertFalse(link.is_symlink())
            self.assertEqual(link.read_text(), "new")

    def test_write_regular_target_unchanged_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            p.write_text("old")
            atomic_write_text(p, "new")
            self.assertEqual(p.read_text(), "new")

    def test_write_missing_target_unchanged_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            atomic_write_text(p, "new")
            self.assertEqual(p.read_text(), "new")


if __name__ == "__main__":
    unittest.main()
