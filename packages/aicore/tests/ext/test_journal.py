"""aicore.ext.journal: appends under a lock, a torn tail, complete lines only, two processes."""
import json
import multiprocessing
import os
import stat
import unittest

from aicore.ext import journal
from aicore.ext.errors import ExtError

from tests.ext.support import TempCase


def _worker(directory, label, count):
    for index in range(count):
        journal.append(directory, json.dumps({"w": label, "i": index, "pad": "x" * 200}).encode())


class TestAppend(TempCase):
    def test_offsets_are_line_starts(self):
        first = journal.append(self.journal, b'{"a":1}')
        second = journal.append(self.journal, b'{"b":2}\n')
        self.assertEqual((first, second), (0, 8))
        self.assertEqual(journal.size(self.journal), 16)
        self.assertEqual(journal.read_at(self.journal, second), {"b": 2})
        self.assertEqual(journal.read_at(self.journal, first), {"a": 1})

    def test_files_and_modes(self):
        journal.append(self.journal, b"{}")
        self.assertEqual(stat.S_IMODE(os.stat(journal.journal_path(self.journal)).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(journal.lock_path(self.journal)).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.journal).st_mode), 0o700)

    def test_inner_newline_and_size_limit(self):
        with self.assertRaises(ValueError):
            journal.append(self.journal, b'{"a":\n1}')
        with self.assertRaises(ExtError) as caught:
            journal.append(self.journal, b"x" * journal.MAX_LINE)
        self.assertEqual(caught.exception.code, "JOURNAL_LINE_TOO_LARGE")
        self.assertEqual(journal.size(self.journal), 0)
        journal.append(self.journal, b"x" * (journal.MAX_LINE - 1))  # a full line with its newline fits
        with self.assertRaises(TypeError):
            journal.append(self.journal, "text")

    def test_torn_tail_becomes_a_broken_line_of_its_own(self):
        journal.append(self.journal, b'{"a":1}')
        with open(journal.journal_path(self.journal), "ab") as handle:
            handle.write(b'{"torn":')
        offset = journal.append(self.journal, b'{"c":3}')
        lines = list(journal.iter_lines(self.journal))
        self.assertEqual([line for _o, line, _p in lines], [b'{"a":1}', b'{"torn":', b'{"c":3}'])
        self.assertEqual(lines[2][0], offset)

    def test_busy_lock_is_reported(self):
        import fcntl
        journal.append(self.journal, b"{}")
        fd = os.open(journal.lock_path(self.journal), os.O_RDWR)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        with self.assertRaises(ExtError) as caught:
            journal.append(self.journal, b"{}", lock_timeout_s=0.2)
        self.assertEqual(caught.exception.code, "JOURNAL_LOCKED")
        self.assertEqual(len(list(journal.iter_lines(self.journal))), 1)

    def test_a_fork_by_another_thread_waits_and_does_not_keep_the_lock(self):
        """flock lives as long as any copy of the descriptor: a fork during append must not extend it."""
        import threading
        import warnings
        inside, release = threading.Event(), threading.Event()
        real_fsync = os.fsync
        children = []

        def paused_fsync(fd):
            inside.set()
            release.wait(10)
            real_fsync(fd)

        def forker():
            inside.wait(10)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                pid = os.fork()  # waits in the fork hook until the append is over
            if pid == 0:
                try:
                    import time
                    time.sleep(5)
                finally:
                    os._exit(0)
            children.append(pid)

        os.fsync = paused_fsync
        thread = threading.Thread(target=forker)
        thread.start()
        timer = threading.Timer(0.3, release.set)
        timer.start()
        try:
            journal.append(self.journal, b'{"a":1}')
        finally:
            os.fsync = real_fsync
            timer.cancel()
            release.set()
        thread.join(15)
        self.addCleanup(lambda: [(os.kill(pid, 9), os.waitpid(pid, 0)) for pid in children])
        self.assertEqual(len(children), 1)
        journal.append(self.journal, b'{"b":2}', lock_timeout_s=0.5)
        self.assertEqual(len(list(journal.iter_lines(self.journal))), 2)

    def test_directory_without_write_permission_raises_oserror(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores directory permissions")
        journal.append(self.journal, b"{}")
        os.chmod(self.journal, 0o500)
        self.addCleanup(os.chmod, self.journal, 0o700)
        os.chmod(journal.journal_path(self.journal), 0o400)
        self.addCleanup(os.chmod, journal.journal_path(self.journal), 0o600)
        with self.assertRaises(OSError):
            journal.append(self.journal, b"{}")

    def test_journal_dir(self):
        self.assertEqual(journal.journal_dir(self.project), self.project / ".swissknifeman" / "state")
        self.assertEqual(journal.journal_dir(None, env=self.env), self.tmp / "skm" / "state" / "events")


class TestReading(TempCase):
    def lines(self, start=0):
        return list(journal.iter_lines(self.journal, start))

    def test_missing_journal_is_empty(self):
        self.assertEqual(self.lines(), [])
        self.assertEqual(journal.size(self.journal), 0)
        self.assertIsNone(journal.read_at(self.journal, 0))

    def test_incomplete_last_line_is_not_returned(self):
        journal.append(self.journal, b'{"a":1}')
        with open(journal.journal_path(self.journal), "ab") as handle:
            handle.write(b'{"partial')
        self.assertEqual([line for _o, line, _p in self.lines()], [b'{"a":1}'])
        self.assertIsNone(journal.read_at(self.journal, 8))

    def test_too_long_and_empty_lines_are_problems(self):
        path = journal.journal_path(self.journal)
        path.parent.mkdir(parents=True)
        with open(path, "wb") as handle:
            handle.write(b'{"a":1}\n' + b"y" * (journal.MAX_LINE + 10) + b"\n\n" + b'{"z":1}\n')
        result = self.lines()
        self.assertEqual([entry[2] for entry in result], [None, "too-long", "empty", None])
        self.assertIsNone(result[1][1])
        self.assertEqual(result[3][1], b'{"z":1}')
        self.assertEqual(result[1][0], 8)

    def test_line_of_exactly_the_limit(self):
        path = journal.journal_path(self.journal)
        path.parent.mkdir(parents=True)
        body = b"q" * (journal.MAX_LINE - 1)
        with open(path, "wb") as handle:
            handle.write(body + b"\n" + (b"r" * journal.MAX_LINE) + b"\nlast\n")
        result = self.lines()
        self.assertEqual([entry[2] for entry in result], [None, "too-long", None])

    def test_lines_across_block_boundaries(self):
        for index in range(300):
            journal.append(self.journal, json.dumps({"i": index, "pad": "p" * 700}).encode())
        result = self.lines()
        self.assertEqual([json.loads(line)["i"] for _o, line, _p in result], list(range(300)))
        resume = result[150][0]
        self.assertEqual([json.loads(line)["i"] for _o, line, _p in self.lines(resume)], list(range(150, 300)))

    def test_start_beyond_the_snapshot_and_negative_start(self):
        journal.append(self.journal, b"{}")
        self.assertEqual(self.lines(10_000), [])
        with self.assertRaises(ValueError):
            self.lines(-1)

    def test_read_at_returns_none_for_non_objects(self):
        journal.append(self.journal, b"[1,2]")
        journal.append(self.journal, b"not json")
        self.assertIsNone(journal.read_at(self.journal, 0))
        self.assertIsNone(journal.read_at(self.journal, 6))


class TestConcurrentAppends(TempCase):
    def test_two_processes_write_400_whole_unique_lines(self):
        context = multiprocessing.get_context("fork")
        workers = [context.Process(target=_worker, args=(str(self.journal), label, 200)) for label in ("a", "b")]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(60)
            self.assertEqual(worker.exitcode, 0)
        entries = [json.loads(line) for _o, line, _p in journal.iter_lines(self.journal)]
        self.assertEqual(len(entries), 400)
        self.assertEqual(len({(entry["w"], entry["i"]) for entry in entries}), 400)
        for label in ("a", "b"):  # each writer's own order is kept
            self.assertEqual([entry["i"] for entry in entries if entry["w"] == label], list(range(200)))
        data = journal.journal_path(self.journal).read_bytes()
        self.assertTrue(data.endswith(b"\n"))
        self.assertEqual(data.count(b"\n"), 400)


if __name__ == "__main__":
    unittest.main()
