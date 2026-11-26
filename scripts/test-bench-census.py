#!/usr/bin/env python3
"""bench-census.py: the execution observer, the ledger reader, source-backed deltas, the verdict rule and the gate."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bench_census", ROOT / "scripts" / "bench-census.py")
census = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)

SUITE = '''import unittest

class T(unittest.TestCase):
    def test_pass(self):
        pass

    @unittest.skip("not today")
    def test_skip(self):
        pass

    def test_sub(self):
        for n in (1, 2):
            with self.subTest(n=n):
                self.assertTrue(n == 1)

    def test_fail(self):
        self.fail("boom")

    @unittest.expectedFailure
    def test_xfail(self):
        self.fail("expected")
'''


class ObservedCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(os.path.realpath(tmp.name))
        self.tree = self.tmp / "tree"
        (self.tree / "packages" / "mod" / "tests").mkdir(parents=True)
        (self.tree / "packages" / "mod" / "tests" / "__init__.py").write_text("")
        (self.tree / "packages" / "mod" / "tests" / "test_x.py").write_text(SUITE)
        self.base = self.tmp / "userbase"
        self.env = dict(os.environ)
        self.env.pop("PYTHONPATH", None)
        self.provenance = census.install_observer(self.base, self.env)

    def run_tests(self, *argv, ledger="ledger", context=None, python_path=None, tree=None):
        tree = tree or self.tree
        folder = self.tmp / ledger
        env = census.census_env(self.env, self.base, folder, tree)
        if context:
            env["SKM_TEST_CONTEXT"] = context
        if python_path is not None:
            env["PYTHONPATH"] = python_path
        done = subprocess.run(["python3", "-m", "unittest", *argv], cwd=tree / "packages" / "mod",
                              env=env, capture_output=True, text=True, timeout=120)
        return done, folder


class ObserverTests(ObservedCase):
    def test_outcomes_skips_subtests_and_context_are_recorded_from_real_execution(self):
        done, folder = self.run_tests("tests.test_x", context="standalone")
        self.assertNotEqual(0, done.returncode)
        summary = census.read_ledger(folder, self.tree)
        self.assertEqual({"error": 0, "failed": 2, "passed": 1, "skipped": 1, "expected_failure": 1},
                         {"error": 0, **summary["outcomes"]})
        self.assertEqual({"not today": 1}, summary["skips"])
        self.assertEqual(5, summary["executions"])
        self.assertEqual({"standalone": 5}, summary["contexts"])
        self.assertEqual({"packages/mod": 5}, summary["units"])
        self.assertEqual(0, summary["unmatched_starts"])
        keys = sorted(key.split("|", 1)[1] for _ctx, key in summary["_keys"])
        self.assertIn("packages/mod/tests/test_x.py|T|test_sub", keys)
        self.assertGreaterEqual(summary["subtest_failures"], 1)

    def test_it_is_transparent_the_result_is_the_same_with_and_without_it(self):
        plain = subprocess.run(["python3", "-m", "unittest", "tests.test_x"], cwd=self.tree / "packages" / "mod",
                               env=self.env, capture_output=True, text=True, timeout=120)
        seen, _folder = self.run_tests("tests.test_x")
        pick = lambda done: [line for line in done.stderr.splitlines() if line.startswith(("Ran ", "OK", "FAILED"))]  # noqa: E731
        self.assertEqual(pick(plain), pick(seen))
        self.assertEqual(plain.returncode, seen.returncode)
        self.assertEqual(plain.stdout, seen.stdout)

    def test_it_survives_a_runner_that_replaces_pythonpath(self):
        done, folder = self.run_tests("tests.test_x.T.test_pass", python_path="/nonexistent:lib")
        self.assertEqual(0, done.returncode, done.stderr)
        summary = census.read_ledger(folder, self.tree)
        self.assertEqual((1, 1), (summary["activations"], summary["executions"]))

    def test_discovery_is_not_execution(self):
        _done, folder = self.run_tests("tests.test_x.T.test_pass")  # the module defines five tests, one is run
        self.assertEqual(1, census.read_ledger(folder, self.tree)["executions"])

    def test_a_repeated_run_is_a_duplicate_execution_not_a_second_case(self):
        self.run_tests("tests.test_x.T.test_pass", ledger="twice")
        self.run_tests("tests.test_x.T.test_pass", ledger="twice")
        summary = census.read_ledger(self.tmp / "twice", self.tree)
        self.assertEqual((2, 1, 1), (summary["executions"], summary["unique"], summary["duplicates"]))

    def test_the_same_case_in_two_contexts_is_two_cases(self):
        self.run_tests("tests.test_x.T.test_pass", ledger="ctx", context="local")
        self.run_tests("tests.test_x.T.test_pass", ledger="ctx", context="standalone")
        summary = census.read_ledger(self.tmp / "ctx", self.tree)
        self.assertEqual((2, {"local": 1, "standalone": 1}), (summary["unique"], summary["contexts"]))

    def test_the_par_unittest_driver_activates_in_its_workers(self):
        suite = self.tree / "packages" / "mod"
        env = census.census_env(dict(self.env, PYTHONPATH=str(ROOT / "packages" / "aicore" / "lib")), self.base,
                                self.tmp / "par", self.tree)
        done = subprocess.run(["python3", "-m", "aicore.util.par_unittest", "discover", "-s", "tests", "-t", ".", "-j", "2",
                               "-p", "test_x.py"], cwd=suite, env=env, capture_output=True, text=True, timeout=180)
        summary = census.read_ledger(self.tmp / "par", self.tree)
        self.assertGreaterEqual(summary["activations"], 1, done.stderr[-500:])
        self.assertEqual(5, summary["unique"], done.stderr[-500:])

    def test_the_provenance_names_the_interpreter_and_the_observer_bytes(self):
        self.assertEqual(census.sha256_text(census.OBSERVER), self.provenance["observer_sha256"])
        self.assertTrue(Path(self.provenance["user_site"], "usercustomize.py").is_file())
        self.assertTrue(self.provenance["python"])


class ShimAndSurrogateTests(ObservedCase):
    def test_the_digest_and_the_ledger_survive_an_undecodable_path_character(self):
        self.assertEqual(64, len(census.sha256_text("a\udcffb")))
        folder = self.tmp / "sur"
        folder.mkdir()
        (folder / "p1.jsonl").write_text(
            '{"ev":"activate","pid":1,"cwd":"x","ctx":""}\n'
            '{"ev":"s","id":"t.A.a","file":"/x/te\\udcffst.py","cls":"A","m":"a"}\n'
            '{"ev":"e","id":"t.A.a","o":"passed","r":"","sub":0}\n')
        summary = census.read_ledger(folder, self.tree)
        self.assertEqual(1, summary["executions"])
        text = json.dumps(census.public(summary), ensure_ascii=True)  # a lossless, ASCII-only checkpoint
        self.assertEqual(summary["digest"], json.loads(text)["digest"])

    def test_the_shim_activates_after_pythonpath_was_replaced_and_never_wraps_twice(self):
        shim = census.install_shim(self.tmp / "shim", subprocess.run(["python3", "-c", "import sys;print(sys.executable)"],
                                                                  capture_output=True, text=True).stdout.strip())
        env = census.census_env(self.env, self.base, self.tmp / "both", self.tree, shim)
        env["PYTHONPATH"] = "/nonexistent"
        done = subprocess.run(["bash", "-c", "PYTHONPATH=lib:x python3 -m unittest tests.test_x.T.test_pass"],
                              cwd=self.tree / "packages" / "mod", env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(0, done.returncode, done.stderr)
        summary = census.read_ledger(self.tmp / "both", self.tree)
        self.assertEqual(1, summary["executions"])  # user site AND shim loaded the observer; one wrapper only

    def test_relative_arguments_become_absolute_paths_for_children(self):
        previous = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, previous)
        provenance = census.install_observer(Path("rel-base"), self.env)
        shim = census.install_shim(Path("rel-shim"), provenance["python"])
        env = census.census_env(self.env, Path("rel-base"), Path("rel-ledger"), Path("tree"), shim)
        for name in ("PYTHONUSERBASE", "SKM_CENSUS_DIR", "SKM_CENSUS_ROOT"):
            self.assertTrue(os.path.isabs(env[name]), (name, env[name]))
        self.assertTrue(env["PATH"].startswith(str(self.tmp / "rel-shim" / "bin")))
        self.assertTrue(os.path.isabs(provenance["user_site"]))
        # a child that changes directory still loads the observer from the user base
        folder = self.tree / "packages" / "mod"
        done = subprocess.run(["python3", "-m", "unittest", "tests.test_x.T.test_pass"], cwd=folder, env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(1, census.read_ledger(self.tmp / "rel-ledger", self.tree)["executions"])

    def test_completeness_names_every_gap(self):
        _done, folder = self.run_tests("tests.test_x.T.test_pass")
        summary = census.read_ledger(folder, self.tree)
        self.assertEqual([], census.complete(summary, ["packages/mod"]))
        self.assertEqual(3, len(census.complete(dict(summary, unmatched_starts=1), ["packages/mod", "packages/x"], 2)))


class LedgerTests(ObservedCase):
    def test_a_start_without_an_end_and_garbage_stay_unknown(self):
        folder = self.tmp / "partial"
        folder.mkdir()
        (folder / "p1.jsonl").write_text(
            '{"ev":"activate","pid":1,"cwd":"x","ctx":""}\n'
            '{"ev":"s","id":"t.A.a","file":null,"cls":"A","m":"a"}\n'
            'not json\n')
        summary = census.read_ledger(folder, self.tree)
        self.assertEqual((0, 1, 1), (summary["executions"], summary["unmatched_starts"], summary["unreadable_lines"]))
        document = census.compare(summary, summary, self.tree, "HEAD", self.tree, [])
        self.assertIsNone(document["conserved"])
        self.assertTrue(any("no observed execution" in text for text in document["unknown"]))

    def test_a_unit_without_any_observed_test_is_unknown_not_zero(self):
        _done, folder = self.run_tests("tests.test_x.T.test_pass")
        summary = census.read_ledger(folder, self.tree)
        self.assertEqual(["packages/other"], census.missing_units(summary, ["packages/mod", "packages/other"]))
        document = census.compare(summary, summary, self.tree, "HEAD", self.tree, ["packages/mod", "packages/other"])
        self.assertIsNone(document["conserved"])

    def test_an_empty_ledger_folder_is_unknown(self):
        (self.tmp / "none").mkdir()
        summary = census.read_ledger(self.tmp / "none", self.tree)
        self.assertEqual(0, summary["executions"])
        self.assertIsNone(census.compare(summary, summary, self.tree, "HEAD", self.tree, [])["conserved"])


def git(repo, *argv):
    done = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *argv], cwd=repo, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


class DeltaTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(os.path.realpath(tmp.name))
        git(self.repo, "init", "-q", ".")
        self.test = self.repo / "packages" / "mod" / "tests" / "test_x.py"
        self.test.parent.mkdir(parents=True)
        self.test.write_text("import unittest\nclass T(unittest.TestCase):\n    def test_old(self): pass\n"
                             "    def test_kept(self): pass\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        self.rev = git(self.repo, "rev-parse", "HEAD")

    def summary(self, *methods, ctx="local"):
        keys = {(ctx, f"packages/mod|packages/mod/tests/test_x.py|T|{m}") for m in methods}
        rows = [{"key": k, "ctx": c, "o": "passed", "sub": 0, "unit": "packages/mod"} for c, k in keys]
        return {"_keys": keys, "_rows": rows, "executions": len(rows), "unique": len(keys), "duplicates": 0, "outcomes": {"passed": len(rows)},
                "units": {"packages/mod": len(rows)}, "unmatched_starts": 0, "unreadable_lines": 0, "activations": 1,
                "processes": {}, "skips": {}, "contexts": {ctx: len(keys)}, "subtest_failures": 0, "digest": "d"}

    def source_without_old(self):
        self.test.write_text("import unittest\nclass T(unittest.TestCase):\n    def test_kept(self): pass\n"
                             "    def test_new(self): pass\n")

    def test_added_and_removed_methods_are_described_but_a_removal_is_not_a_coverage_proof(self):
        self.source_without_old()
        document = census.compare(self.summary("test_old", "test_kept"), self.summary("test_kept", "test_new"),
                                  self.repo, self.rev, self.repo, ["packages/mod"])
        reasons = {delta["key"].rsplit("|", 1)[1]: (delta["why"], delta["coverage"]) for delta in document["deltas"]}
        self.assertEqual({"test_old": ("removed: method gone (renamed or deleted)", "unproven"),
                          "test_new": ("added: new method", "added")}, reasons)
        self.assertEqual(0, document["unexplained"])
        self.assertIsNone(document["conserved"])  # the lexical disappearance is an observation, not a replacement mapping
        self.assertEqual((1, 0, ["local|packages/mod|packages/mod/tests/test_x.py|T|test_old"]),
                         (document["removals"]["total"], document["removals"]["mapped"], document["removals"]["unmapped"]))

    def test_a_deleted_negative_without_a_replacement_cannot_be_conserved(self):
        self.test.write_text("import unittest\nclass T(unittest.TestCase):\n    def test_kept(self): pass\n")
        document = census.compare(self.summary("test_old", "test_kept"), self.summary("test_kept"), self.repo, self.rev, self.repo,
                                  ["packages/mod"])
        self.assertIsNone(document["conserved"])
        self.assertEqual(1, len(document["removals"]["unmapped"]))

    def test_an_explicit_justified_mapping_to_a_case_that_ran_and_passed_restores_conservation(self):
        self.source_without_old()
        old = "local|packages/mod|packages/mod/tests/test_x.py|T|test_old"
        new = "local|packages/mod|packages/mod/tests/test_x.py|T|test_new"

        def run(entry):
            return census.compare(self.summary("test_old", "test_kept"), self.summary("test_kept", "test_new"), self.repo,
                                  self.rev, self.repo, ["packages/mod"], mappings={old: entry} if entry is not None else None)
        document = run({"replacement": new, "reason": "test_old was renamed to test_new with the same assertions"})
        self.assertEqual((True, 1, []), (document["conserved"], document["removals"]["mapped"], document["removals"]["unmapped"]))
        self.assertEqual("mapped", next(d for d in document["deltas"] if d["key"] == old)["coverage"])
        for entry in (None, {"replacement": new, "reason": ""}, {"replacement": new}, {"reason": "x"},
                      {"replacement": "local|packages/mod|nowhere.py|T|test_x", "reason": "moved"},
                      {"replacement": [new, "local|ghost"], "reason": "partly"}, "test_new"):
            with self.subTest(entry=entry):
                self.assertIsNone(run(entry)["conserved"])

    def test_a_replacement_that_did_not_pass_is_no_mapping(self):
        self.source_without_old()
        after = self.summary("test_kept", "test_new")
        for row in after["_rows"]:
            if row["key"].endswith("test_new"):
                row["o"] = "skipped"
        old = "local|packages/mod|packages/mod/tests/test_x.py|T|test_old"
        new = "local|packages/mod|packages/mod/tests/test_x.py|T|test_new"
        document = census.compare(self.summary("test_old", "test_kept"), after, self.repo, self.rev, self.repo,
                                  ["packages/mod"], mappings={old: {"replacement": new, "reason": "renamed"}})
        self.assertIsNone(document["conserved"])

    def test_unknown_primary_outcomes_never_prove_conservation(self):
        for outcome in ("unknown", None, "", "weird"):
            with self.subTest(outcome=outcome):
                base, after = self.summary("test_kept"), self.summary("test_kept")
                for summary in (base, after):
                    summary["_rows"][0]["o"] = outcome
                    summary["outcomes"] = {outcome or "none": 1}
                document = census.compare(base, after, self.repo, self.rev, self.repo, ["packages/mod"])
                self.assertIsNone(document["conserved"])
                self.assertEqual(2, sum("unknown primary outcome" in text for text in document["unknown"]))

    def test_one_unknown_outcome_is_enough_and_only_aggregate_counts_also_count(self):
        base, after = self.summary("test_kept"), self.summary("test_kept")
        after["outcomes"] = {"unknown": 1}
        self.assertIsNone(census.compare(base, after, self.repo, self.rev, self.repo, ["packages/mod"])["conserved"])
        base, after = self.summary("test_kept"), self.summary("test_kept")
        after["_rows"][0]["o"] = "unknown"
        document = census.compare(base, after, self.repo, self.rev, self.repo, ["packages/mod"])
        self.assertEqual((None, 1), (document["conserved"], sum("after:" in text for text in document["unknown"])))

    def test_an_unexplained_delta_is_false_even_with_a_removal_to_map(self):
        self.source_without_old()
        document = census.compare(self.summary("test_old", "test_kept", "test_ghost"), self.summary("test_kept", "test_new"),
                                  self.repo, self.rev, self.repo, ["packages/mod"])
        self.assertEqual((1, False), (document["unexplained"], document["conserved"]))

    def test_a_case_that_vanished_without_a_source_change_is_unexplained(self):
        document = census.compare(self.summary("test_old", "test_kept"), self.summary("test_kept"), self.repo, self.rev,
                                  self.repo, ["packages/mod"])
        self.assertEqual((1, False), (document["unexplained"], document["conserved"]))

    def test_a_failing_side_or_a_changed_outcome_is_not_conserved(self):
        base, after = self.summary("test_kept"), self.summary("test_kept")
        after["_rows"][0]["o"] = "failed"
        after["outcomes"] = {"failed": 1}
        document = census.compare(base, after, self.repo, self.rev, self.repo, ["packages/mod"])
        self.assertEqual((False, ["after"]), (document["conserved"], document["failed_sides"]))

    def test_equal_sides_are_conserved(self):
        document = census.compare(self.summary("test_kept"), self.summary("test_kept"), self.repo, self.rev, self.repo,
                                  ["packages/mod"])
        self.assertEqual((True, []), (document["conserved"], document["unknown"]))


def doc(before, after, *, failed=0, equal=True, conserved=None, stable=None, target=None):
    out = {"result": {"target_met": target, "failed_runs": failed}, "total": {"counted": ["cold"]},
           "before": {"commands": [{"id": "cold", "runs": before}]}, "after": {"commands": [{"id": "cold", "runs": after}]},
           "coverage": {"workload": {"equal": equal}}}
    if conserved is not None:
        out["census"] = {"conserved": conserved, "before": {"executions": 3}, "after": {"executions": 3},
                         "exits": {"before": {"exit": 0}, "after": {"exit": 0}}, "workload_executions": 2}
    if stable is not None:
        out["sources"] = {"stable": stable}
    return out


class VerdictTests(unittest.TestCase):
    def test_exactly_two_thirds_with_a_conserved_census_is_met(self):
        self.assertIs(True, census.decide(doc([3.0, 3.0], [2.0, 2.0], conserved=True)))

    def test_just_above_two_thirds_is_not_met_even_without_a_census(self):
        self.assertIs(False, census.decide(doc([300.0], [200.01])))
        self.assertIs(False, census.decide(doc([300.0], [250.0], conserved=True)))

    def test_within_the_ratio_but_no_conserved_census_is_unproven(self):
        for conserved in (None, False):
            with self.subTest(conserved=conserved):
                self.assertIsNone(census.decide(doc([3.0], [1.0], conserved=conserved)))

    def test_failed_runs_a_different_workload_or_a_moving_source_give_no_verdict(self):
        self.assertIsNone(census.decide(doc([3.0], [1.0], failed=2, conserved=True)))
        self.assertIsNone(census.decide(doc([3.0], [1.0], equal=False, conserved=True)))
        self.assertIsNone(census.decide(doc([3.0], [1.0], conserved=True, stable=False)))
        self.assertIsNone(census.decide(doc([3.0, 3.0], [1.0], conserved=True)))
        self.assertIsNone(census.decide(doc([0.0], [0.0], conserved=True)))


class GateTests(unittest.TestCase):
    def check(self, document):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bench.json"
            path.write_text(json.dumps(document))
            return census.gate(path), census.main(["gate", str(path)])

    def test_a_true_verdict_with_failed_runs_or_no_census_cannot_pass(self):
        problems, code = self.check(doc([3.0], [1.0], failed=2, target=True))
        self.assertEqual(1, code)
        self.assertTrue(any("measured runs failed" in text for text in problems))
        problems, code = self.check(doc([3.0], [1.0], target=True))
        self.assertEqual(1, code)
        self.assertTrue(any("without a conserved execution census" in text for text in problems))

    def test_honest_documents_pass(self):
        for document in (doc([3.0], [1.0], target=None), doc([3.0], [2.5], target=False),
                         doc([3.0], [1.0], conserved=True, target=True), doc([3.0], [1.0], failed=2, target=None)):
            with self.subTest(document=document["result"]):
                self.assertEqual(([], 0), self.check(document))

    def test_a_dishonest_false_or_a_conserved_census_without_ledgers_is_refused(self):
        self.assertEqual(1, self.check(doc([3.0], [1.0], conserved=True, target=False))[1])
        broken = doc([3.0], [1.0], conserved=True, target=True)
        broken["census"]["after"]["executions"] = 0
        self.assertEqual(1, self.check(broken)[1])

    def test_a_conserved_census_needs_successful_exits_and_at_most_two_observations(self):
        for change in ({"exits": {"before": {"exit": 0}, "after": {"exit": 1}}}, {"workload_executions": 3}):
            with self.subTest(change=change):
                broken = doc([3.0], [1.0], conserved=True, target=True)
                broken["census"].update(change)
                self.assertEqual(1, self.check(broken)[1])

    def test_an_unreadable_file_and_a_wrong_command_are_refused(self):
        self.assertEqual(1, census.main(["gate", "/nonexistent/bench.json"]))
        self.assertEqual(2, census.main([]))


if __name__ == "__main__":
    unittest.main()
