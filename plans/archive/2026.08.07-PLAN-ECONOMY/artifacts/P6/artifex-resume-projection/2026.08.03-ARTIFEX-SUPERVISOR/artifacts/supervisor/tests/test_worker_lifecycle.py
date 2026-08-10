from __future__ import annotations

import sys
import unittest

from artifex import worker


class WorkerLifecycleTests(unittest.TestCase):
    def test_fresh_bounded_output_is_minimized(self):
        result = worker.run([sys.executable, "-c", "print('one')"], cwd=".", env={}, stdin=b"",
                            timeout_ms=1000, max_output_bytes=32, max_event_count=2)
        self.assertEqual(result["kind"], "success")
        self.assertEqual(result["process_count"], 1)
        self.assertIn("output_hash", result)
        self.assertNotIn("one", str(result))

    def test_overflow_and_timeout_are_closed(self):
        overflow = worker.run([sys.executable, "-c", "print('x' * 100)"], cwd=".", env={}, stdin=b"",
                              timeout_ms=1000, max_output_bytes=8, max_event_count=2)
        self.assertEqual(overflow["reason_code"], "BUDGET_OUTPUT_BYTES")
        timeout = worker.run([sys.executable, "-c", "import time; time.sleep(2)"], cwd=".", env={}, stdin=b"",
                             timeout_ms=10, max_output_bytes=32, max_event_count=2, kill_grace_seconds=0.05)
        self.assertEqual(timeout["reason_code"], "WALL_TIMEOUT")

    def test_transient_carrier_is_private_and_removable(self):
        fd, path = worker.transient_carrier(b"carrier")
        try:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
