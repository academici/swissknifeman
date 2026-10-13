"""The parallel ``unittest discover`` runner: same verdict as plain unittest, shards, clash detection."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[2] / "lib"


def run(directory, *args, env=None):
    return subprocess.run([sys.executable, "-m", "aicore.util.par_unittest", "discover", "-s", str(directory), *args],
                          cwd=directory, env=dict(os.environ, PYTHONPATH=str(LIB), **(env or {})),
                          capture_output=True, text=True)


def suite(root, files):
    (root / "tests").mkdir()
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    for name, body in files.items():
        (root / "tests" / f"test_{name}.py").write_text("import unittest\nclass T(unittest.TestCase):\n" + body, encoding="utf-8")


class ParallelUnittestTests(unittest.TestCase):
    def test_a_green_suite_reports_the_total_and_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite(root, {name: "    def test_a(self):\n        pass\n    def test_b(self):\n        pass\n" for name in "abc"})
            done = run(root / "tests", "-j", "3", "-t", str(root))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("Ran 6 tests", done.stderr)
            self.assertIn("OK", done.stderr)

    def test_a_failing_test_fails_the_run_and_is_shown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite(root, {"ok": "    def test_a(self):\n        pass\n",
                         "bad": "    def test_b(self):\n        self.assertEqual(1, 2)\n"})
            done = run(root / "tests", "-j", "2", "-t", str(root))
            self.assertEqual(done.returncode, 1, done.stderr)
            self.assertIn("FAILED", done.stderr)
            self.assertIn("test_b", done.stderr)

    def test_each_worker_has_its_own_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = ("    def test_home(self):\n        import os, pathlib\n"
                    "        marker = pathlib.Path(os.environ['HOME']) / 'seen'\n"
                    "        self.assertFalse(marker.exists())\n        marker.write_text('x')\n")
            suite(root, {"one": body, "two": body.replace("test_home", "test_home2")})
            done = run(root / "tests", "-j", "2", "-t", str(root))
            self.assertEqual(done.returncode, 0, done.stderr)

    def test_one_job_falls_back_to_plain_unittest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite(root, {"a": "    def test_a(self):\n        pass\n", "b": "    def test_b(self):\n        pass\n"})
            done = run(root / "tests", "-j", "1", "-t", str(root))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("Ran 2 tests", done.stderr)


if __name__ == "__main__":
    unittest.main()
