#!/usr/bin/env python3
"""The real shell entry points reject unknown selectors before starting tests."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HUB = Path(__file__).resolve().parents[1]


class RunnerArgumentsTests(unittest.TestCase):
    def invoke(self, module, args):
        with tempfile.TemporaryDirectory(prefix="skm-runner-args-") as folder:
            root = Path(folder)
            binary = root / "bin"
            binary.mkdir()
            record = root / "calls"
            python = binary / "python3"
            python.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$*" >> "$SKM_TEST_ARG_PROBE"\n'
                'if [ "$1" != "-c" ]; then printf "Ran 1 tests in 0.001s\\nOK\\n"; fi\n'
            )
            python.chmod(0o755)
            env = dict(os.environ, PATH=str(binary) + os.pathsep + os.defpath,
                       HOME=str(root), SKM_TEST_ARG_PROBE=str(record),
                       AICORE_ROOT=str(HUB / "packages/aicore"))
            result = subprocess.run(["/bin/bash", str(HUB / "packages" / module / "scripts/test.sh"), *args],
                                    cwd=root, env=env, capture_output=True, text=True, timeout=10)
            return result, record.read_text() if record.exists() else ""

    def test_unsupported_arguments_never_start_python(self):
        for module in ("aicore", "skiller"):
            for args in (("-p", "test_one.py"), ("--pattern=test_one.py",),
                         ("unexpected",), ("-v", "-p", "test_one.py"), ("-v", "-v")):
                with self.subTest(module=module, args=args):
                    result, calls = self.invoke(module, args)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("usage: scripts/test.sh [-v]", result.stderr)
                    self.assertEqual(calls, "", calls)

    def test_documented_arguments_preserve_the_test_invocation(self):
        for module in ("aicore", "skiller"):
            for args in ((), ("-v",)):
                with self.subTest(module=module, args=args):
                    result, calls = self.invoke(module, args)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("discover -s tests", calls)
                    self.assertEqual(" -v" in calls, bool(args), calls)
                    self.assertIn("Ran 1 tests", result.stdout)


if __name__ == "__main__":
    unittest.main()
