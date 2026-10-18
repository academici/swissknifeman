"""aicore.util.proc.run: a hang becomes return code 124, never TimeoutExpired."""
import subprocess
import sys
import unittest

from aicore.util import proc


class RunTests(unittest.TestCase):
    def test_a_finished_child_is_returned_as_is(self):
        done = proc.run([sys.executable, "-c", "print('ok')"], timeout=30, capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "ok"))

    def test_a_hung_child_is_killed_and_reported_as_124(self):
        done = proc.run([sys.executable, "-c", "import time; print('start', flush=True); time.sleep(30)"],
                        timeout=1, capture_output=True, text=True)
        self.assertEqual(done.returncode, proc.TIMEOUT_RETURNCODE)
        self.assertIn("timed out after 1s", done.stderr)
        self.assertIsInstance(done.stdout, str)

    def test_bytes_mode_keeps_bytes(self):
        done = proc.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1, capture_output=True)
        self.assertEqual(done.returncode, 124)
        self.assertIsInstance(done.stdout, bytes)
        self.assertIn(b"timed out", done.stderr)

    def test_check_raises_called_process_error_on_a_hang(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            proc.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1, check=True,
                     capture_output=True)
        self.assertEqual(caught.exception.returncode, 124)

    def test_timeout_is_required(self):
        with self.assertRaises(TypeError):
            proc.run([sys.executable, "-c", "pass"])


if __name__ == "__main__":
    unittest.main()
