"""The parallel unittest runner: workers do not share HOME, TMPDIR or SKM state, and a clash is warned or failed."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

LIB = Path(__file__).resolve().parents[1] / "lib"

SUITE = textwrap.dedent('''
    import os, time, unittest
    from pathlib import Path
    OUT = Path(os.environ["PAR_OUT"])

    class First(unittest.TestCase):
        def test_where(self):
            (OUT / "first").write_text(os.environ["HOME"] + "|" + os.environ["TMPDIR"] + "|" + os.environ["SKM_HOME"])
            self.assertTrue((Path(os.environ["SKM_HOME"]) / "config.toml").is_file())
            self.assertEqual(os.environ["SKM_TEST_JOBS"], "1")
            if os.environ.get("PAR_RACE"):
                (OUT / "busy").write_text("x")
                time.sleep(2)
                (OUT / "busy").unlink()

    class Second(unittest.TestCase):
        def test_where(self):
            (OUT / "second").write_text(os.environ["HOME"] + "|" + os.environ["TMPDIR"] + "|" + os.environ["SKM_HOME"])
            if os.environ.get("PAR_RACE"):
                time.sleep(0.7)
                self.assertFalse((OUT / "busy").exists(), "a race with First")
''')


class ParallelRunnerTests(unittest.TestCase):
    def run_suite(self, *extra, race=False):
        tmp = Path(tempfile.mkdtemp(prefix="par-test-"))
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(tmp)]))
        (tmp / "tests").mkdir()
        (tmp / "tests" / "test_pair.py").write_text(SUITE, encoding="utf-8")
        home, out = tmp / "home", tmp / "out"
        (home / "skm").mkdir(parents=True)
        (home / "skm" / "config.toml").write_text("schema_version = 1\n", encoding="utf-8")
        out.mkdir()
        env = dict(os.environ, HOME=str(home), SKM_HOME=str(home / "skm"), PAR_OUT=str(out), PYTHONPATH=str(LIB),
                   **({"PAR_RACE": "1"} if race else {}))
        env.pop("SKM_TEST_CLASH", None)
        env["SKM_TEST_CONTEXT"] = "partner"
        env["SKM_PAR_UNITTEST_REPORT"] = str(out / "report.json")
        done = subprocess.run([sys.executable, "-m", "aicore.util.par_unittest", "discover", "-s", "tests", "-t", "tests",
                               "-j", "2", *extra], cwd=tmp, env=env, capture_output=True, text=True)
        return done, out, home

    def test_each_worker_has_its_own_home_tmpdir_and_a_copy_of_the_skm_state(self):
        done, out, home = self.run_suite()
        self.assertEqual(done.returncode, 0, done.stderr)
        first, second = (out / "first").read_text().split("|"), (out / "second").read_text().split("|")
        for left, right in zip(first, second):
            self.assertNotEqual(left, right)
        self.assertNotEqual(first[0], str(home))
        self.assertTrue(first[2].startswith(first[0]))  # SKM_HOME moved into the worker's own HOME

    def test_context_and_original_ids_are_kept_in_the_report(self):
        import json
        done, out, _ = self.run_suite()
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads((out / "report.json").read_text())
        self.assertEqual(report["context"], "partner")
        self.assertEqual(sorted(c["id"] for c in report["inventory"]),
                         ["test_pair.First.test_where", "test_pair.Second.test_where"])
        self.assertEqual((report["requested_jobs"], report["effective_jobs"]), (2, 2))

    def test_a_clash_is_warned_by_default_and_failed_when_asked(self):
        done, _, _ = self.run_suite(race=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("CLASH", done.stderr)
        done, _, _ = self.run_suite("--clash", "fail", race=True)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("CLASH", done.stderr)


if __name__ == "__main__":
    unittest.main()
