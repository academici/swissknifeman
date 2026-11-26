"""An acceptance check never inherits the input of the conductor: a command that reads stdin (``docker buildx bake --file -``,
``cat``, a prompt) ends at once instead of waiting for a pipe that never closes."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
import unittest

from orch.conductor import checks


class CheckStdinTests(unittest.TestCase):
    def run_command(self, argv: list, timeout_s: int = 30) -> tuple:
        """``(exit, output, seconds)`` of a check run while the conductor's own stdin is an open pipe nobody writes to."""
        read_end, write_end = os.pipe()
        saved = os.dup(0)
        os.dup2(read_end, 0)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "out.log"
                began = time.monotonic()
                with log.open("wb") as out:
                    code = checks._run_command(argv, cwd=Path(tmp), out=out, timeout_s=timeout_s, warn_s=0)
                return code, log.read_text(encoding="utf-8"), time.monotonic() - began
        finally:
            os.dup2(saved, 0)
            for fd in (saved, read_end, write_end):
                os.close(fd)

    def test_a_check_that_reads_stdin_gets_end_of_file_at_once(self):
        code, output, seconds = self.run_command(["python3", "-c", "import sys; print(repr(sys.stdin.read()))"])
        self.assertEqual((code, output.strip()), (0, "''"))
        self.assertLess(seconds, 15)  # without the fix it waits for the 30 s ceiling and ends with 124

    def test_cat_does_not_wait_for_the_conductor(self):
        code, output, _ = self.run_command(["cat"])
        self.assertEqual((code, output), (0, ""))

    @unittest.skipUnless(os.path.exists("/proc/self/fd/0"), "needs /proc")
    def test_stdin_of_a_check_is_dev_null(self):
        code, output, _ = self.run_command(["python3", "-c", "import os; print(os.readlink('/proc/self/fd/0'))"])
        self.assertEqual((code, output.strip()), (0, os.devnull))


if __name__ == "__main__":
    unittest.main()
