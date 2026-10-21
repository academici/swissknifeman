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


class SchedulingAndEvidenceTests(unittest.TestCase):
    def setUp(self):
        import json
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.times, self.report = self.root / "timing.json", self.root / "report.json"
        self.env = {"SKM_PAR_UNITTEST_TIMES": str(self.times), "SKM_PAR_UNITTEST_REPORT": str(self.report)}

    def execute(self, files, jobs=2):
        import json
        suite(self.root, files)
        done = run(self.root / "tests", "-j", str(jobs), "-t", str(self.root), env=self.env)
        report = json.loads(self.report.read_text()) if self.report.exists() else None
        return done, report

    def test_heavy_class_splits_methods_and_records_all_original_ids(self):
        import json
        self.times.write_text(json.dumps({"tests.test_a.T": 120}))
        done, report = self.execute({"a": "    def test_a(self): pass\n    def test_b(self): pass\n"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(report["effective_jobs"], 2)
        self.assertEqual(sorted(a["units"] for a in report["attempts"]),
                         [["tests.test_a.T.test_a"], ["tests.test_a.T.test_b"]])
        timings = json.loads(self.times.read_text())
        self.assertTrue({"tests.test_a.T", "tests.test_a.T.test_a", "tests.test_a.T.test_b"} <= set(timings))
        self.assertAlmostEqual(timings["tests.test_a.T"], timings["tests.test_a.T.test_a"] + timings["tests.test_a.T.test_b"])
        self.assertEqual(len(report["inventory"]), 2)
        self.assertEqual(len([o for a in report["attempts"] for o in a["outcomes"]]), 2)

    def test_inherited_class_and_module_fixtures_are_not_split(self):
        import types
        from unittest import mock
        from aicore.util import par_unittest as par
        module = types.ModuleType("fixture_test")
        class Base(unittest.TestCase):
            @classmethod
            def setUpClass(cls): pass
        class Child(Base):
            def test_a(self): pass
        self.assertFalse(par._splittable(Child("test_a")))
        class Plain(unittest.TestCase):
            def test_a(self): pass
        Plain.__module__ = module.__name__
        with mock.patch.dict(sys.modules, {module.__name__: module}):
            for name in ("setUpModule", "tearDownModule", "load_tests"):
                setattr(module, name, lambda: None)
                self.assertFalse(par._splittable(Plain("test_a")), name)
                delattr(module, name)
            self.assertTrue(par._splittable(Plain("test_a")))

    def test_fixture_class_stays_one_unit_despite_old_heavy_time(self):
        import json
        self.times.write_text(json.dumps({"tests.test_a.T": 120}))
        body = "    @classmethod\n    def setUpClass(cls): pass\n    def test_a(self): pass\n    def test_b(self): pass\n"
        done, report = self.execute({"a": body, "b": "    def test_a(self): pass\n"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(["tests.test_a.T"], [a["units"] for a in report["attempts"]])

    def test_only_failed_parent_method_is_retried_and_clash_keeps_green_count(self):
        log, marker = self.root / "green", self.root / "failed-once"
        body = (f"    def test_green(self):\n        from pathlib import Path\n        p=Path({str(log)!r})\n"
                "        p.write_text(p.read_text()+'x' if p.exists() else 'x')\n"
                f"    def test_red(self):\n        from pathlib import Path\n        p=Path({str(marker)!r})\n"
                "        first=not p.exists()\n        p.touch()\n        with self.subTest(value=1):\n            self.assertFalse(first)\n")
        done, report = self.execute({"a": body, "b": "    def test_a(self): pass\n"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("CLASH", done.stderr)
        self.assertIn("Ran 3 tests", done.stderr)
        retry = [a for a in report["attempts"] if a["retry"]]
        self.assertEqual(retry[0]["units"], ["tests.test_a.T.test_red"])
        self.assertEqual(log.read_text(), "x")
        self.assertEqual(retry[0]["outcomes"][0]["outcome"], "passed")

    def test_unreadable_times_falls_back_to_counts_and_writes_override_atomically(self):
        import json
        self.times.write_text("{broken")
        done, report = self.execute({name: "    def test_a(self): pass\n" for name in "ab"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(report["effective_jobs"], 2)
        self.assertIn("tests.test_a.T", json.loads(self.times.read_text()))
        self.assertEqual([p for p in self.root.glob("timing.json.*") if p.suffix != ".lock"], [])

    def test_serial_and_parallel_keep_ids_outcomes_and_skip_reasons(self):
        import json
        files = {"a": "    def test_a(self): pass\n    @unittest.skip('fixture unavailable')\n    def test_b(self): pass\n",
                 "b": "    @unittest.expectedFailure\n    def test_a(self): self.fail('expected')\n"}
        done, parallel = self.execute(files)
        self.assertEqual(done.returncode, 0, done.stderr)
        done = run(self.root / "tests", "-j", "1", "-t", str(self.root), env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        serial = json.loads(self.report.read_text())
        self.assertEqual(serial["effective_jobs"], 1)
        self.assertEqual(sorted(i["key"] for i in parallel["inventory"]), sorted(i["key"] for i in serial["inventory"]))
        normalize = lambda r: sorted((o["id"], o["outcome"], o["reason"]) for a in r["attempts"] for o in a["outcomes"])
        self.assertEqual(normalize(parallel), normalize(serial))
        self.assertIn("fixture unavailable", str(serial))
        self.assertEqual(sum(a["executed"] for a in serial["attempts"]), 2)
        self.assertEqual(sum(a["executed"] for a in parallel["attempts"]), 2)

    def test_setup_error_and_worker_crash_retry_whole_shard(self):
        for phase in ("setup", "teardown", "crash"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmp:
                import json
                root = Path(tmp)
                fixture = "setUpClass" if phase == "setup" else "tearDownClass"
                body = (f"    @classmethod\n    def {fixture}(cls): raise RuntimeError('fixture failed')\n"
                        "    def test_a(self): pass\n") if phase != "crash" else (
                        "    def test_a(self):\n        import os\n        os._exit(9)\n")
                suite(root, {"a": body, "b": "    def test_a(self): pass\n"})
                report_path = root / "report.json"
                done = run(root / "tests", "-j", "2", "-t", str(root),
                           env={"SKM_PAR_UNITTEST_REPORT": str(report_path)})
                self.assertEqual(done.returncode, 1, done.stderr)
                self.assertIn("retry whole shard", done.stderr)
                report = json.loads(report_path.read_text())
                self.assertEqual([a["units"] for a in report["attempts"] if a["retry"]], [["tests.test_a.T"]])

    def test_custom_package_discovery_preserves_suite_run_and_does_not_split(self):
        import json
        suite(self.root, {"a": "    def test_a(self): pass\n    def test_b(self): pass\n"})
        init = self.root / "tests" / "__init__.py"
        init.write_text("import unittest\nfrom .test_a import T\n"
                        "class Custom(unittest.TestSuite):\n"
                        "    def run(self, result, debug=False):\n"
                        "        assert self.countTestCases() == 2\n"
                        "        return super().run(result, debug)\n"
                        "def load_tests(loader, tests, pattern):\n"
                        "    return Custom(loader.loadTestsFromTestCase(T))\n")
        self.times.write_text(json.dumps({"tests.test_a.T": 120}))
        done = run(self.root / "tests", "-j", "4", "-t", str(self.root), env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(self.report.read_text())["effective_jobs"], 1)

    def test_import_failure_is_never_a_successful_empty_retry(self):
        suite(self.root, {"a": "    def test_a(self): pass\n", "b": "    def test_b(self): pass\n"})
        (self.root / "tests" / "test_b.py").write_text("raise ImportError('missing fixture')\n")
        done = run(self.root / "tests", "-j", "2", "-t", str(self.root), env=self.env)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("missing fixture", done.stderr)
        self.assertNotIn("CLASH", done.stderr)

    def test_missing_worker_selection_fails_instead_of_running_zero_tests(self):
        suite(self.root, {"a": "    def test_a(self): pass\n"})
        done = run(self.root / "tests", "--worker", "-t", str(self.root), "--unit",
                   str(self.root / "tests/test_a.py") + "::tests.test_a.T.test_missing")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("selected tests are missing", done.stderr)

    def test_atomic_timing_merge_keeps_independent_concurrent_writers(self):
        import json
        from concurrent.futures import ThreadPoolExecutor
        from aicore.util import par_unittest as par
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: par._merge_times(self.times, {f"case{i}": float(i)}), range(12)))
        self.assertEqual(json.loads(self.times.read_text()), {f"case{i}": float(i) for i in range(12)})


if __name__ == "__main__":
    unittest.main()
