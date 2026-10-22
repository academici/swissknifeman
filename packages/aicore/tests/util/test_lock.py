"""aicore.util.lock: flock with the samestat loop, timeouts, probe and the context manager."""
import fcntl
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from aicore.util import lock as lock_module
from aicore.util.lock import FileLock, LockTimeout, hold, lock_descriptor, probe_free

LIB = str(Path(lock_module.__file__).resolve().parents[2])


class LockTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        self.path = self.directory / "a.lock"

    def child(self, code):
        """A python child that prints READY once it runs ``code`` and then waits on stdin."""
        proc = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                env={**os.environ, "PYTHONPATH": LIB})
        self.addCleanup(lambda: (proc.kill(), proc.wait(timeout=10), proc.stdout.close(), proc.stdin.close()))
        self.assertEqual(b"READY\n", proc.stdout.readline())
        return proc

    def test_second_lock_in_one_process_is_refused(self):
        first, second = FileLock(self.path), FileLock(self.path)
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.release()
        self.assertTrue(second.acquire())
        second.release()
        self.assertTrue(self.path.exists(), "lock files are never removed")

    def test_acquire_twice_on_one_object_is_an_error(self):
        lock = FileLock(self.path)
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)
        with self.assertRaises(RuntimeError):
            lock.acquire()

    def test_a_killed_holder_frees_the_lock(self):
        proc = self.child("import sys; from aicore.util.lock import FileLock; "
                          f"l = FileLock({str(self.path)!r}); assert l.acquire(); print('READY', flush=True); "
                          "sys.stdin.read()")
        self.assertFalse(FileLock(self.path).acquire())
        proc.kill()
        proc.wait(timeout=10)
        mine = FileLock(self.path)
        self.assertTrue(mine.acquire())
        mine.release()

    def test_a_replaced_inode_is_locked_again_on_the_new_file(self):
        real = fcntl.flock
        old = self.path.with_suffix(".old")

        def replace(fd, flags):
            real(fd, flags)
            if not old.exists():
                self.path.rename(old)
                self.path.touch()

        lock = FileLock(self.path)
        with mock.patch.object(lock_module.fcntl, "flock", side_effect=replace):
            self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)
        self.assertTrue(os.path.samestat(os.fstat(lock.fd), self.path.stat()))

    def test_a_removed_file_is_recreated_and_locked(self):
        real = fcntl.flock
        calls = []

        def remove(fd, flags):
            real(fd, flags)
            if not calls:
                calls.append(1)
                self.path.unlink()

        lock = FileLock(self.path)
        with mock.patch.object(lock_module.fcntl, "flock", side_effect=remove):
            self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)
        self.assertTrue(self.path.exists())
        self.assertTrue(os.path.samestat(os.fstat(lock.fd), self.path.stat()))

    def test_a_symlink_is_refused(self):
        self.path.touch()
        link = self.directory / "link.lock"
        link.symlink_to(self.path)
        with self.assertRaises(OSError):
            FileLock(link).acquire()

    def test_timeout_expires(self):
        first = FileLock(self.path)
        self.assertTrue(first.acquire())
        self.addCleanup(first.release)
        started = time.monotonic()
        self.assertFalse(FileLock(self.path).acquire(blocking=True, timeout=0.15, poll=0.01))
        self.assertGreaterEqual(time.monotonic() - started, 0.15)
        with self.assertRaises(LockTimeout) as caught:
            with hold(self.path, timeout=0.05, poll=0.01):
                self.fail("entered a busy lock")
        self.assertEqual("LOCK_TIMEOUT", caught.exception.code)
        self.assertEqual(self.path, caught.exception.path)
        with self.assertRaises(LockTimeout) as caught:
            with FileLock(self.path).hold(timeout=0, code="MY_CODE"):
                self.fail("entered a busy lock")
        self.assertEqual("MY_CODE", caught.exception.code)

    def test_a_blocking_acquire_waits_for_the_release(self):
        first = FileLock(self.path)
        self.assertTrue(first.acquire())
        proc = self.child("import sys; from aicore.util.lock import FileLock; print('READY', flush=True); "
                          f"print(FileLock({str(self.path)!r}).acquire(blocking=True, timeout=10, poll=0.01), "
                          "flush=True)")
        time.sleep(0.1)
        first.release()
        self.assertEqual(b"True\n", proc.stdout.readline())

    def test_hold_releases_after_the_block_and_after_an_error(self):
        with hold(self.path, timeout=1) as held:
            self.assertIsNotNone(held.fd)
            self.assertFalse(FileLock(self.path).acquire())
        self.assertIsNone(held.fd)
        with self.assertRaises(ValueError):
            with hold(self.path, timeout=1):
                raise ValueError("boom")
        self.assertTrue(probe_free(self.path))

    def test_the_descriptor_is_closed_by_exec(self):
        lock = FileLock(self.path)
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)
        self.assertTrue(os.get_inheritable(lock.fd) is False)
        self.assertTrue(fcntl.fcntl(lock.fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC)

    def test_probe_free(self):
        missing = self.directory / "missing.lock"
        self.assertTrue(probe_free(missing))
        self.assertFalse(missing.exists(), "a probe never creates the file")
        self.path.touch()
        self.assertTrue(probe_free(self.path))
        with hold(self.path, timeout=1):
            self.assertFalse(probe_free(self.path))

    def test_probe_of_an_unreadable_file_is_unknown(self):
        if os.geteuid() == 0:
            self.skipTest("root reads everything")
        self.path.touch()
        os.chmod(self.path, 0)
        self.addCleanup(os.chmod, self.path, 0o600)
        self.assertIsNone(probe_free(self.path))

    def test_lock_descriptor(self):
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        other = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, fd)
        self.addCleanup(os.close, other)
        self.assertTrue(lock_descriptor(fd))
        self.assertFalse(lock_descriptor(other, timeout=0.05, poll=0.01))
        os.close(os.dup(fd))  # closing another copy does not release
        self.assertFalse(lock_descriptor(other))
        fcntl.flock(fd, fcntl.LOCK_UN)
        self.assertTrue(lock_descriptor(other))


if __name__ == "__main__":
    unittest.main()
