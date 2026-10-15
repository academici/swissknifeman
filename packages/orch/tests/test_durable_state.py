"""The files of a run survive a crash and say clearly when they did not: JSON is replaced through a unique temporary
file with fsync, a torn or foreign file stops with ``STATE_CORRUPT`` naming it, and the run folders are the owner's only."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest

from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import files


class DurableStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_concurrent_writers_of_one_file_never_leave_a_torn_or_temporary_file(self):
        target = self.root / "state.json"
        errors = []

        def write(n: int) -> None:
            try:
                for i in range(30):
                    files.write_json(target, {"writer": n, "i": i, "pad": "x" * 2000})
            except Exception as error:  # noqa: BLE001 - the test collects any failure of a thread
                errors.append(error)

        threads = [threading.Thread(target=write, args=(n,)) for n in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(set(files.read_json(target)), {"writer", "i", "pad"})
        self.assertEqual([path.name for path in self.root.iterdir()], ["state.json"])

    def test_a_torn_file_stops_with_state_corrupt_naming_it(self):
        target = self.root / "state.json"
        target.write_text('{"steps": {', encoding="utf-8")
        with self.assertRaises(Stop) as caught:
            files.read_json(target)
        self.assertEqual(caught.exception.code, "STATE_CORRUPT")
        self.assertIn(str(target), str(caught.exception))
        self.assertIsNone(files.read_json(self.root / "missing.json"))

    def test_a_symlinked_target_is_refused(self):
        real = self.root / "real.json"
        real.write_text("{}", encoding="utf-8")
        (self.root / "state.json").symlink_to(real)
        with self.assertRaises(OSError):
            files.write_json(self.root / "state.json", {"a": 1})
        self.assertEqual(real.read_text(encoding="utf-8"), "{}")

    def test_the_run_folders_are_private(self):
        store = files.RunStore.__new__(files.RunStore)
        store.directory = self.root / "conductor" / "cnd-1"
        store.create({"run_id": "cnd-1"})
        for folder in (store.directory, store.directory.parent):
            self.assertEqual(stat.S_IMODE(os.stat(folder).st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()
