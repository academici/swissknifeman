"""Tests assert_safe_replace_target/atomic_write_text (P8.7) — 4 target class + tmp-cleanup.

aicore tests/test_util.py already covers creating parents/indent/mode/tmp-cleanup when
os.replace-falling; here is ONLY a new goal invariant (do not duplicate)."""
import os
import tempfile
import unittest
from pathlib import Path

from unittest import mock
import threading

from aicore.util import io
from aicore.util.io import assert_safe_replace_target, atomic_write_text, durable_replace


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


class TestDurableWrites(unittest.TestCase):
    def test_a_folder_fsync_io_error_is_raised_and_an_unsupported_one_is_not(self):
        import errno
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "doc.json"
            real = os.fsync

            def failing(code):
                def fsync(handle):
                    if os.path.isdir(f"/proc/self/fd/{handle}") or Path(os.readlink(f"/proc/self/fd/{handle}")).is_dir():
                        raise OSError(code, os.strerror(code))
                    return real(handle)
                return fsync
            with mock.patch.object(io.os, "fsync", failing(errno.EIO)):
                with self.assertRaises(OSError):  # the rename may not be on disk: never acknowledged
                    durable_replace(target, b"{}\n")
            with mock.patch.object(io.os, "fsync", failing(errno.EINVAL)):
                durable_replace(target, b"{}\n")  # a filesystem that cannot fsync a folder
            self.assertEqual(b"{}\n", target.read_bytes())

    """One primitive under atomic_write_text and durable_replace: unique temp, no link followed, fsync, umask."""

    def test_the_file_and_its_folder_are_fsynced(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(io.os, "fsync", wraps=os.fsync) as fsync:
            atomic_write_text(Path(tmp) / "f.txt", "new")
            self.assertEqual(2, fsync.call_count)  # the temporary file, then the folder after the rename

    def test_a_planted_temp_symlink_is_never_written_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = Path(tmp) / "victim.txt"
            victim.write_text("SECRET")
            (Path(tmp) / "f.txt.tmp").symlink_to(victim)  # the old fixed temp name
            atomic_write_text(Path(tmp) / "f.txt", "new")
            self.assertEqual("SECRET", victim.read_text())
            self.assertEqual("new", (Path(tmp) / "f.txt").read_text())

    def test_concurrent_writers_of_one_file_never_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "state.json"
            bodies = [str(n) * 200_000 for n in range(8)]
            threads = [threading.Thread(target=atomic_write_text, args=(target, body)) for body in bodies]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertIn(target.read_text(), bodies)
            self.assertEqual([], list(Path(tmp).glob("*.tmp")))

    def test_permissions_follow_the_umask_unless_mode_or_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.umask(0o022)
            try:
                atomic_write_text(Path(tmp) / "plain.txt", "x")
                durable_replace(Path(tmp) / "private.json", b"{}")
            finally:
                os.umask(old)
            self.assertEqual(0o644, (Path(tmp) / "plain.txt").stat().st_mode & 0o777)
            self.assertEqual(0o600, (Path(tmp) / "private.json").stat().st_mode & 0o777)


if __name__ == "__main__":
    unittest.main()
