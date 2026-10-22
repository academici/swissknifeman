"""orch on the shared aicore primitives (lock, time, durable write): same behaviour as the copies they replaced."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from aicore.util import io as aicore_io, lock as aicore_lock  # noqa: E402
from orch.conductor import agents, gates, observer, progress, questions  # noqa: E402
from orch.conductor.infrastructure import clock, lease  # noqa: E402


class SharedPrimitivesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        saved = os.environ.get("TZ")
        self.addCleanup(self._restore_zone, saved)

    @staticmethod
    def _restore_zone(saved):
        if saved is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = saved
        time.tzset()

    def zone(self, name):
        os.environ["TZ"] = name
        time.tzset()

    def test_the_lease_lock_is_the_aicore_one(self):
        self.assertIs(lease.FileLock, aicore_lock.FileLock)
        self.assertIs(lease.probe_free, aicore_lock.probe_free)

    def test_gates_wait_with_their_own_timeout_and_poll(self):
        file = self.directory / "orch" / "provider-gates.json"
        calls = []
        real = aicore_lock.FileLock.acquire

        def spy(self, blocking=False, timeout=None, poll=0.02):
            calls.append((blocking, timeout, poll))
            return real(self, blocking, timeout, poll)

        with mock.patch.object(aicore_lock.FileLock, "acquire", spy), mock.patch.object(gates, "LOCK_TIMEOUT_S", 3.5):
            with gates._Locked(file) as held:
                self.assertIsNotNone(held.fd)
        self.assertEqual([(True, 3.5, gates.LOCK_POLL_S)], calls)
        self.assertEqual(0.02, gates.LOCK_POLL_S)

    def test_a_busy_gates_lock_is_gates_locked(self):
        file = self.directory / "orch" / "provider-gates.json"
        file.parent.mkdir()
        holder = aicore_lock.FileLock(file.with_name(gates.LOCK_FILE))
        self.assertTrue(holder.acquire())
        self.addCleanup(holder.release)
        with mock.patch.object(gates, "LOCK_TIMEOUT_S", 0.1):
            with self.assertRaises(gates.GateError) as caught:
                gates._Locked(file).__enter__()
        self.assertEqual("GATES_LOCKED", caught.exception.code)

    def test_agent_records_are_written_durably(self):
        target = self.directory / "agents" / "a" / "request.json"
        with mock.patch.object(aicore_io.os, "fsync", wraps=os.fsync) as synced:
            agents._write(target, {"step": "é", "attempt": 1}, "agent-request")
        self.assertGreaterEqual(synced.call_count, 1)
        self.assertEqual('{\n  "$schema": "urn:swissknifeman:orch:records:agent-request:v1",\n  "attempt": 1,\n'
                         '  "step": "é"\n}\n', target.read_text(encoding="utf-8"))
        self.assertEqual([target.name], [path.name for path in target.parent.iterdir()])

    def test_times_do_not_depend_on_the_process_zone(self):
        results = set()
        for zone in ("America/New_York", "Asia/Tokyo"):
            self.zone(zone)
            results.add((observer._seconds("2024-01-01T12:00:00"),
                         observer._seconds("2024-01-01T12:00:00Z"),
                         observer._seconds("2024-01-01T13:00:00+01:00"),
                         questions._epoch("2024-01-01T12:00:00Z"),
                         progress._seconds("2024-01-01T12:00:00Z", "2024-01-01T12:01:30Z"),
                         gates._epoch("2024-01-01T12:00:00Z"),
                         clock.utc_stamp(1704110400),
                         ))
        self.assertEqual({(1704110400.0, 1704110400.0, 1704110400.0, 1704110400, 90, 1704110400.0,
                           "2024-01-01T12:00:00Z")}, results)

    def test_bad_times_keep_their_failures(self):
        with self.assertRaises(ValueError):
            observer._seconds("not a time")
        with self.assertRaises(ValueError):
            questions._epoch("not a time")
        with self.assertRaises(ValueError):
            progress._seconds("not a time", "2024-01-01T12:00:00Z")
        self.assertIsNone(gates._epoch("not a time"))
        self.assertIsNone(gates._epoch(5))

    def test_the_clock_keeps_its_formats(self):
        self.assertRegex(clock.utc_now(), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual("1970-01-01T00:00:00Z", clock.utc_stamp(0))


if __name__ == "__main__":
    unittest.main()
