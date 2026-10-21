#!/usr/bin/env python3
"""bench-checks.py on a scratch git repository: pairs, worktree cleanup, exits, case census, workload, schema."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bench_checks", ROOT / "scripts" / "bench-checks.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

REPORT = ("python3 -c \"import json,os;p=os.environ['SKM_PAR_UNITTEST_REPORT'].replace('{pid}',str(os.getpid()));"
          "os.makedirs(os.path.dirname(p),exist_ok=True);key=open('marker').read().strip()+'%s';"
          "json.dump({'context':'local','inventory':[{'key':key,'id':key,'file':'f.py','context':'local'}],"
          "'attempts':[{'retry':False,'exit':0,'units':[key],'outcomes':[],'tests_run':1,'started':[key],'executed':1}],"
          "'requested_jobs':1,'effective_jobs':1,'elapsed_s':0.1},open(p,'w'))\"")
FAKE_AFFECTED = ("import json, sys\n"
                 "if '--json' in sys.argv:\n"
                 "    print(json.dumps({'commands': [{'folder': 'hub', 'argv': ['check', open('marker').read().strip()]}]}))\n")


def git(repo: Path, *argv: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *argv], cwd=repo, capture_output=True,
                          text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


class BenchCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(os.path.realpath(tmp.name)) / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / "packages" / "planner").mkdir(parents=True)
        (self.repo / "packages" / "planner" / "keep").write_text("x")
        (self.repo / "scripts" / "affected-tests.py").write_text(FAKE_AFFECTED)
        (self.repo / "marker").write_text("old\n")
        git(self.repo.parent, "init", "-q", str(self.repo))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "first")
        (self.repo / "marker").write_text("new\n")
        git(self.repo, "commit", "-q", "-am", "second")
        self.base = git(self.repo, "rev-parse", "HEAD~1")
        self.out = self.repo.parent / "out" / "bench.json"
        patch = mock.patch.object(bench, "ROOT", self.repo)
        patch.start()
        self.addCleanup(patch.stop)
        isolated = mock.patch.dict(os.environ, {"SKM_CHECK_RUN": "leak", "SKM_CHECK_ROUND": "9"})
        isolated.start()
        self.addCleanup(isolated.stop)

    def commands(self, *entries) -> str:
        path = self.repo.parent / "commands.json"
        path.write_text(json.dumps(list(entries)))
        return str(path)

    def run_bench(self, *argv: str, rev: str = "HEAD~1"):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = bench.main(["--before", rev, "--out", str(self.out), *argv])
        return code, err.getvalue()

    def document(self) -> dict:
        return json.loads(self.out.read_text(encoding="utf-8"))

    def worktrees(self) -> list:
        return [line for line in git(self.repo, "worktree", "list").splitlines()]


class DocumentTests(BenchCase):
    def test_two_pairs_make_a_document_that_follows_the_schema_and_leaves_no_worktree(self):
        commands = self.commands({"id": "quick", "cmd": "true"}, {"id": "slow", "cmd": "sleep 0.1"})
        code, err = self.run_bench("--commands-file", commands, "--label", "unit")
        self.assertEqual(0, code, err)
        doc = self.document()
        self.assertEqual([], bench.validate(doc))
        self.assertEqual(("urn:swissknifeman:hub:bench-checks:v1", "unit", self.base), (doc["$schema"], doc["label"], doc["before"]["rev"]))
        self.assertEqual("worktree", doc["after"]["rev"])
        self.assertEqual([1, 2], [pair["n"] for pair in doc["pairs"]])
        self.assertEqual([["before", "after"], ["after", "before"]], [pair["order"] for pair in doc["pairs"]])
        self.assertEqual(2, doc["pairs_run"])
        slow = next(row for row in doc["before"]["commands"] if row["id"] == "slow")
        self.assertEqual(2, len(slow["runs"]))
        self.assertGreaterEqual(slow["seconds"], 0.1)
        for name in ("quick", "slow"):
            before = next(row for row in doc["before"]["commands"] if row["id"] == name)["seconds"]
            after = next(row for row in doc["after"]["commands"] if row["id"] == name)["seconds"]
            if before:
                self.assertEqual(round(after / before, 3), doc["ratio"][name])
        self.assertEqual(2, len(doc["loadavg"]))
        self.assertGreaterEqual(doc["cpu_count"], 1)
        self.assertEqual(1, len(self.worktrees()), self.worktrees())
        self.assertEqual([], list(self.out.parent.glob("bench.json.*")))
        self.assertRegex(err, r"\[bench\] before true [0-9.]+ s exit 0")
        self.assertRegex(err, r"\[bench\] after sleep 0\.1 [0-9.]+ s exit 0")
        self.assertEqual(2, len(list((self.out.parent / "bench-logs").glob("before-*-quick.log"))))

    def test_the_base_is_measured_in_its_own_tree_and_a_non_zero_exit_is_recorded(self):
        code, err = self.run_bench("--commands-file", self.commands({"id": "base", "cmd": 'test "$(cat marker)" = old'}))
        self.assertEqual(0, code, err)
        doc = self.document()
        self.assertEqual(([0, 0], [1, 1]), (doc["before"]["commands"][0]["exits"], doc["after"]["commands"][0]["exits"]))
        self.assertEqual(2, doc["result"]["failed_runs"])
        self.assertIn("exited non-zero", doc["result"]["note"])
        self.assertEqual([], bench.validate(doc))
        self.assertEqual(1, len(self.worktrees()))

    def test_the_environment_is_the_same_for_both_sides_and_has_no_check_variables(self):
        script = ('test -z "$SKM_CHECK_RUN" && test -z "$SKM_CHECK_ROUND" && test "$SKM_TEST_JOBS" = 3 '
                  '&& test "$PLANNER_ROOT" = "$PWD/packages/planner"')
        with mock.patch.dict(os.environ, {"SKM_TEST_JOBS": "3"}):
            code, err = self.run_bench("--pairs", "1", "--commands-file", self.commands({"id": "env", "cmd": script}))
        self.assertEqual(0, code, err)
        doc = self.document()
        self.assertEqual(([0], [0], 3), (doc["before"]["commands"][0]["exits"], doc["after"]["commands"][0]["exits"], doc["jobs"]))

    def test_diagnostic_and_warm_commands_are_not_in_the_total(self):
        commands = self.commands({"id": "main", "cmd": "sleep 0.1"}, {"id": "diag", "cmd": "sleep 0.3", "diagnostic": True},
                                 {"id": "warm", "cmd": 'test -n "$SKM_CHECK_RUN"', "mode": "warm_reuse"})
        code, err = self.run_bench("--pairs", "1", "--commands-file", commands)
        self.assertEqual(0, code, err)
        doc = self.document()
        self.assertEqual(["main"], doc["total"]["counted"])
        self.assertLess(doc["total"]["before_s"], 0.3)
        self.assertEqual({"cold", "warm_reuse"}, {row["mode"] for row in doc["before"]["commands"]})
        warm = next(row for row in doc["after"]["commands"] if row["id"] == "warm")
        self.assertEqual([0], warm["exits"])

    def test_the_default_workload_is_one_cold_command_and_warm_adds_two(self):
        self.assertEqual(["cold"], [row["id"] for row in bench.default_commands(False)])
        self.assertIn("--no-cache", bench.default_commands(False)[0]["cmd"])
        warm = bench.default_commands(True)
        self.assertEqual(["cold", "warm_scheduling", "warm_reuse"], [row["id"] for row in warm])
        self.assertEqual(["cold", "warm_scheduling", "warm_reuse"], [row["mode"] for row in warm])
        self.assertTrue(all("--no-cache" not in row["cmd"] for row in warm[1:]))
        code, err = self.run_bench("--pairs", "1", "--warm", "--no-census")
        self.assertEqual(0, code, err)
        self.assertEqual(["cold", "warm_scheduling", "warm_reuse"], [row["id"] for row in self.document()["after"]["commands"]])
        self.assertEqual(["cold"], self.document()["total"]["counted"])


class CoverageTests(BenchCase):
    def test_workload_and_cases_are_compared_between_the_sides(self):
        command = REPORT % ""
        code, err = self.run_bench("--pairs", "1", "--commands-file", self.commands(
            {"id": "cases", "cmd": command + "; python3 scripts/affected-tests.py --run --tier all"}))
        self.assertEqual(0, code, err)
        doc = self.document()
        cases = doc["coverage"]["cases"]["cases"]
        self.assertEqual((True, False, 1, 1, 1, 1), (cases["comparable"], cases["equal"], cases["before_unique"],
                                                    cases["after_unique"], cases["only_before"], cases["only_after"]))
        self.assertEqual(["-local|old", "+local|new"], cases["sample"])
        self.assertFalse(doc["coverage"]["workload"]["equal"])
        self.assertEqual(["hub: check old"], doc["coverage"]["workload"]["before"])
        first = doc["pairs"][0]["results"][0]["cases"]
        self.assertEqual((True, 1, 1, 1, 1, {"local": 1}), (first["available"], first["files"], first["inventory"],
                                                            first["invocations"], first["executed"], first["contexts"]))
        self.assertEqual([], bench.validate(doc))

    def test_each_runner_keeps_its_own_report_and_equal_censuses_are_equal(self):
        (self.repo / "marker").write_text("old\n")  # the current tree is the base again
        one, two = REPORT % "-a", REPORT % "-b"
        code, err = self.run_bench("--pairs", "1", "--commands-file", self.commands({"id": "two", "cmd": f"{one}; {two}"}))
        self.assertEqual(0, code, err)
        doc = self.document()
        cases = doc["coverage"]["cases"]["two"]
        self.assertEqual((True, True, 2, 2), (cases["comparable"], cases["equal"], cases["before_unique"], cases["after_unique"]))
        self.assertEqual(2, doc["pairs"][0]["results"][0]["cases"]["files"])
        self.assertEqual(len(doc["pairs"][0]["results"][0]["cases"]["digest"]), 64)

    def test_a_side_without_reports_is_not_comparable_and_says_why(self):
        code, err = self.run_bench("--pairs", "1", "--commands-file", self.commands({"id": "plain", "cmd": "true"}))
        self.assertEqual(0, code, err)
        cases = self.document()["coverage"]["cases"]["plain"]
        self.assertEqual((False, None), (cases["comparable"], cases["equal"]))
        self.assertIn("no runner wrote a case report", cases["reason"])

    def test_a_runner_that_took_the_pid_placeholder_literally_is_not_comparable(self):
        literal = ("python3 -c \"import os;p=os.environ['SKM_PAR_UNITTEST_REPORT'];os.makedirs(os.path.dirname(p),exist_ok=True);"
                   "open(p,'w').write('{}')\"")
        code, err = self.run_bench("--pairs", "1", "--commands-file", self.commands({"id": "old", "cmd": literal}))
        self.assertEqual(0, code, err)
        cases = self.document()["coverage"]["cases"]["old"]
        self.assertFalse(cases["comparable"])
        self.assertIn("literally", cases["reason"])

    def test_a_non_affected_command_stands_for_itself(self):
        self.assertEqual(["true"], bench.workload("true", self.repo, dict(os.environ)))


class BenchErrorTests(BenchCase):
    def test_an_unknown_revision_is_exit_2_and_creates_nothing(self):
        code, err = self.run_bench(rev="no-such-rev")
        self.assertEqual(2, code)
        self.assertIn("BENCH_REV_INVALID", err)
        self.assertFalse(self.out.exists())
        self.assertEqual(1, len(self.worktrees()))

    def test_bad_pairs_and_bad_commands_are_exit_2(self):
        code, err = self.run_bench("--pairs", "4")
        self.assertEqual((2, True), (code, "BENCH_PAIRS_INVALID" in err))
        for text, expected in (("[]", "non-empty"), ('[{"cmd": ""}]', "needs a command"), ("{", "BENCH_COMMANDS_INVALID"),
                               ('[{"cmd": "x", "mode": "hot"}]', "mode")):
            with self.subTest(text=text):
                path = self.repo.parent / "bad.json"
                path.write_text(text)
                code, err = self.run_bench("--commands-file", str(path))
                self.assertEqual((2, True), (code, "BENCH_COMMANDS_INVALID" in err and expected in err))

    def test_the_worktree_is_removed_when_the_measurement_itself_fails(self):
        with mock.patch.object(bench, "measure", side_effect=bench.BenchError("BENCH_TEST", "boom")):
            code, err = self.run_bench()
        self.assertEqual((2, True), (code, "BENCH_TEST" in err))
        self.assertEqual(1, len(self.worktrees()))
        self.assertFalse((Path(tempfile_dir()) / f"skm-bench-{os.getpid()}").exists())
        with mock.patch.object(bench, "measure", side_effect=RuntimeError("crash")):
            with self.assertRaises(RuntimeError):
                self.run_bench()
        self.assertEqual(1, len(self.worktrees()))

    def test_a_timed_out_command_is_recorded_as_124(self):
        code, err = self.run_bench("--pairs", "1", "--timeout", "1", "--commands-file", self.commands({"id": "hang", "cmd": "sleep 30"}))
        self.assertEqual(0, code, err)
        row = self.document()["pairs"][0]["results"][0]
        self.assertEqual((124, True), (row["exit"], row["timed_out"]))


class CensusTests(BenchCase):
    def test_the_census_observes_one_run_per_side_and_the_gate_accepts_the_document(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "__init__.py").write_text("")
        (self.repo / ".gitignore").write_text("__pycache__/\n")
        (self.repo / "tests" / "test_t.py").write_text("import unittest\n\nclass T(unittest.TestCase):\n"
                                                      "    def test_a(self):\n        pass\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "tests")
        (self.repo / "tests" / "test_new.py").write_text("import unittest\n\nclass N(unittest.TestCase):\n"
                                                        "    def test_n(self):\n        pass\n")
        command = self.commands({"id": "cold", "cmd": "python3 -m unittest discover -s tests -t ."})
        code, err = self.run_bench("--pairs", "1", "--census", "--commands-file", command, rev="HEAD")
        self.assertEqual(0, code, err)
        doc = self.document()
        self.assertEqual([], bench.validate(doc))
        census = doc["census"]
        self.assertEqual(("observed", [], 2), (census["status"], census["problems"], census["workload_executions"]))
        self.assertTrue(census["transparency"]["ok"], census["transparency"])
        self.assertEqual((1, 2), (census["before"]["executions"], census["after"]["executions"]))
        self.assertEqual([{"side": "after", "why": "added: new file"}],
                         [{"side": d["side"], "why": d["why"]} for d in census["deltas"]])
        self.assertIs(True, census["conserved"])
        self.assertEqual({"before": 0, "after": 0}, {side: entry["exit"] for side, entry in census["exits"].items()})
        self.assertIs(True, doc["sources"]["stable"])
        self.assertEqual(2, doc["budget"]["observation_executions"])
        self.assertEqual(0, bench_census().main(["gate", str(self.out)]))
        self.assertIn("observation, excluded from timings", err)

    def test_a_failing_observation_leaves_the_verdict_unproven(self):
        command = self.commands({"id": "cold", "cmd": "false"})
        code, err = self.run_bench("--pairs", "1", "--census", "--commands-file", command)
        self.assertEqual(0, code, err)
        doc = self.document()
        self.assertEqual("unproven", doc["census"]["status"])
        self.assertIsNone(doc["census"]["conserved"])
        self.assertIsNone(doc["result"]["target_met"])
        self.assertEqual(0, bench_census().main(["gate", str(self.out)]))

    def test_the_default_workload_is_capped_at_six_executions(self):
        code, err = self.run_bench("--pairs", "3")
        self.assertEqual((2, True), (code, "BENCH_BUDGET_EXCEEDED" in err))
        self.assertEqual(6, bench.CAP)

    def test_the_timing_cache_of_the_owner_is_put_back(self):
        cache = TimingCacheProbe(self.repo)
        cache.write("durations.json", b'{"a": 1}')
        command = self.commands({"id": "cold", "cmd": "printf x > .git/affected-tests/durations.json; true"})
        code, err = self.run_bench("--pairs", "1", "--commands-file", command)
        self.assertEqual(0, code, err)
        self.assertEqual(b'{"a": 1}', cache.read("durations.json"))
        self.assertTrue(self.document()["timing_cache"]["restored_before_each_leg"])
        self.assertIn("durations.json", self.document()["timing_cache"]["files"])

    def test_a_cache_file_the_bench_created_is_removed_again(self):
        cache = TimingCacheProbe(self.repo)
        command = self.commands({"id": "cold", "cmd": "mkdir -p .git/affected-tests; printf x > .git/affected-tests/green.json"})
        code, err = self.run_bench("--pairs", "1", "--commands-file", command)
        self.assertEqual(0, code, err)
        self.assertIsNone(cache.read("green.json"))


class RecoveryTests(BenchCase):
    CMD = "python3 -m unittest discover -s tests -t ."

    def setUp(self):
        super().setUp()
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "__init__.py").write_text("")
        (self.repo / ".gitignore").write_text("__pycache__/\n")
        (self.repo / "tests" / "test_t.py").write_text("import unittest\n\nclass T(unittest.TestCase):\n"
                                                      "    def test_a(self):\n        pass\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "tests")
        self.rev = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "tests" / "test_new.py").write_text("import unittest\n\nclass N(unittest.TestCase):\n"
                                                        "    def test_n(self):\n        pass\n")
        self.state = self.out.with_name(self.out.stem + ".recovery")

    def evidence(self, **change) -> str:
        import hashlib
        python = bench.subprocess.run(["python3", "-c", "import platform;print(platform.python_version())"],
                                      capture_output=True, text=True).stdout.strip()
        doc = {"baseline": self.rev, "python": python, "jobs": 4,
               "legs": [{"side": side, "seconds": value, "exit": 0}
                        for side, value in (("before", 10.0), ("after", 5.0), ("after", 5.0), ("before", 10.0))],
               "relevant_inputs": {"marker": hashlib.sha256((self.repo / "marker").read_bytes()).hexdigest()}}
        doc.update(change)
        path = self.repo.parent / "evidence.json"
        path.write_text(json.dumps(doc))
        return str(path)

    def recover(self, *argv, evidence=None):
        return self.run_bench("--recovery-evidence", evidence or self.evidence(), "--recovery-command", self.CMD, *argv, rev=self.rev)

    def attempts(self):
        return json.loads((self.state / "attempts.json").read_text())

    def test_two_observations_reuse_the_four_timing_legs_and_a_later_invocation_runs_nothing(self):
        code, err = self.recover()
        self.assertEqual(0, code, err)
        doc = self.document()
        self.assertEqual([], bench.validate(doc))
        census = doc["census"]
        self.assertEqual(("observed", True, 2, 2), (census["status"], census["conserved"], census["workload_executions"],
                                                    len(census["attempts"])))
        self.assertEqual(0, doc["budget"]["timing_executions"])
        self.assertTrue(doc["timing_source"]["valid"], doc["timing_source"])
        self.assertEqual([10.0, 10.0], doc["before"]["commands"][0]["runs"])
        self.assertEqual((True, []), (doc["result"]["target_met"], doc["loadavg"]))
        self.assertIn("not recorded", doc["loadavg_reason"])
        self.assertEqual(0, bench_census().main(["gate", str(self.out)]))
        ledgers = sorted(str(p) for p in self.state.rglob("p*.jsonl"))
        self.assertTrue(ledgers)
        self.assertEqual(2, err.count("(observation, excluded from timings)"))
        code, err = self.recover()
        self.assertEqual(0, code, err)
        self.assertNotIn("observation, excluded", err)
        self.assertEqual(2, len(self.attempts()["attempts"]))
        self.assertEqual(ledgers, sorted(str(p) for p in self.state.rglob("p*.jsonl")))
        again = self.document()
        self.assertEqual((True, 0), (again["result"]["target_met"], again["census"]["new_workloads_this_invocation"]))
        self.assertEqual(census["digest"] if "digest" in census else None, again["census"].get("digest"))

    def test_relative_output_and_evidence_paths_work_although_every_child_changes_directory(self):
        evidence = self.evidence()
        previous = os.getcwd()
        os.chdir(self.repo.parent)
        self.addCleanup(os.chdir, previous)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = bench.main(["--before", self.rev, "--out", "rel-out/bench.json", "--recovery-evidence",
                               os.path.relpath(evidence), "--recovery-command", self.CMD])
        self.assertEqual(0, code, err.getvalue())
        doc = json.loads((self.repo.parent / "rel-out" / "bench.json").read_text(encoding="utf-8"))
        state = json.loads((self.repo.parent / "rel-out" / "bench.recovery" / "attempts.json").read_text(encoding="utf-8"))
        self.assertTrue(state["preflight"]["ok"], state["preflight"]["checks"])
        self.assertEqual(["complete", "complete"], [a["status"] for a in state["attempts"]])
        for path in (state["preflight"]["observer"]["user_site"], state["preflight"]["shim"]["bin"],
                     state["preflight"]["shim"]["obs"], *(a["ledger"] for a in state["attempts"])):
            self.assertTrue(os.path.isabs(path), path)
        self.assertEqual(("observed", True), (doc["census"]["status"], doc["census"]["conserved"]))
        self.assertEqual(os.path.relpath(evidence), doc["timing_source"]["evidence"])  # the data reference stays as given

    def test_a_relative_work_folder_reaches_children_as_absolute_paths(self):
        previous = os.getcwd()
        os.chdir(self.repo.parent)
        self.addCleanup(os.chdir, previous)
        probe = bench.preflight({"before": self.repo, "after": self.repo}, 4, Path("rel-work"))
        self.assertTrue(probe["ok"], probe["checks"])
        self.assertTrue(all(os.path.isabs(probe["shim"][name]) for name in ("bin", "obs")))
        self.assertTrue(os.path.isabs(probe["observer"]["user_site"]))
        self.assertEqual(5, probe["details"]["plain"]["executions"])

    def test_a_failed_preflight_without_any_attempt_may_run_again_and_keeps_its_receipt(self):
        with mock.patch.object(bench, "preflight", return_value={"ok": False, "checks": {"outcomes": False}, "details": {}}):
            code, err = self.recover()
        self.assertEqual(0, code, err)
        first = self.attempts()
        self.assertEqual(([], True), (first["attempts"], first["stopped"].startswith("the observer preflight")))
        code, err = self.recover()
        self.assertEqual(0, code, err)
        state = self.attempts()
        self.assertEqual(["complete", "complete"], [a["status"] for a in state["attempts"]])
        self.assertIsNone(state["stopped"])
        self.assertEqual(1, len(state["preflight_history"]))
        self.assertEqual({"outcomes": False}, state["preflight_history"][0]["preflight"]["checks"])
        self.assertTrue(state["preflight"]["ok"])
        self.assertEqual(True, self.document()["result"]["target_met"])

    def test_once_an_observation_started_a_stop_is_final_even_if_it_mentions_the_preflight(self):
        self.state.mkdir(parents=True)
        (self.state / "attempts.json").write_text(json.dumps({
            "cap": 2, "attempts": [{"n": 1, "side": "before", "status": "incomplete", "ledger": str(self.state / "ledger-before")}],
            "stopped": "the observer preflight did not hold: x", "preflight": None,
            "workload": {"before": [self.CMD], "after": [self.CMD]}, "expected": []}))
        code, err = self.recover()
        self.assertEqual(0, code, err)
        self.assertNotIn("observation, excluded", err)
        self.assertEqual(1, len(self.attempts()["attempts"]))
        self.assertNotIn("preflight_history", self.attempts())

    def test_the_first_incomplete_observation_stops_the_second(self):
        args = ["--recovery-evidence", self.evidence(), "--recovery-command", "python3 -m unittest nosuchmodule"]
        code, err = self.run_bench(*args, rev=self.rev)
        self.assertEqual(0, code, err)
        state = self.attempts()
        self.assertEqual(["incomplete"], [a["status"] for a in state["attempts"]])
        self.assertIn("before observation is incomplete", state["stopped"])
        doc = self.document()
        self.assertIsNone(doc["result"]["target_met"])
        self.assertEqual("unproven", doc["census"]["status"])
        code, _err = self.run_bench(*args, rev=self.rev)
        self.assertEqual(1, len(self.attempts()["attempts"]))  # no free retry in a later correction

    def test_a_failed_preflight_spends_no_observation(self):
        with mock.patch.object(bench, "preflight", return_value={"ok": False, "checks": {"transparent": False}, "details": {}}):
            code, err = self.recover()
        self.assertEqual(0, code, err)
        self.assertEqual([], self.attempts()["attempts"])
        self.assertIn("preflight did not hold", self.attempts()["stopped"])
        self.assertIsNone(self.document()["result"]["target_met"])
        self.assertNotIn("observation, excluded", err)

    def test_an_exhausted_cap_in_the_state_file_blocks_every_new_workload(self):
        self.state.mkdir(parents=True)
        (self.state / "attempts.json").write_text(json.dumps({
            "cap": 2, "attempts": [{"n": 1, "side": "before", "status": "started"}, {"n": 2, "side": "after", "status": "started"}],
            "stopped": None, "preflight": None, "workload": {"before": [self.CMD], "after": [self.CMD]}, "expected": []}))
        code, err = self.recover()
        self.assertEqual(0, code, err)
        self.assertNotIn("observation, excluded", err)
        self.assertEqual(2, len(self.attempts()["attempts"]))
        self.assertIsNone(self.document()["result"]["target_met"])

    def test_timing_reuse_needs_unchanged_relevant_inputs_a_matching_base_and_clean_legs(self):
        cases = {"inputs": {"relevant_inputs": {"marker": "0" * 64}},
                 "base": {"baseline": "1" * 40},
                 "exit": {"legs": [{"side": s, "seconds": 5.0, "exit": 1 if s == "after" else 0} for s in ("before", "after")]},
                 "python": {"python": "2.7.18"}}
        for name, change in cases.items():
            with self.subTest(name):
                shutil_rmtree(self.state)
                code, err = self.recover(evidence=self.evidence(**change))
                self.assertEqual(0, code, err)
                doc = self.document()
                self.assertFalse(doc["timing_source"]["valid"], doc["timing_source"])
                self.assertIsNone(doc["result"]["target_met"])
                self.assertEqual(0, bench_census().main(["gate", str(self.out)]))

    def test_unknown_source_identity_leaves_reuse_unproven_not_valid(self):
        shutil_rmtree(self.state)
        code, err = self.recover(evidence=self.evidence(relevant_inputs=None))
        self.assertEqual(0, code, err)
        doc = self.document()
        self.assertIsNone(doc["timing_source"]["valid"])
        self.assertIsNone(doc["result"]["target_met"])

    def test_bad_evidence_and_mixed_options_are_exit_2(self):
        path = self.repo.parent / "bad.json"
        for text in ("{", "[]", json.dumps({"legs": [{"side": "before", "seconds": 1.0, "exit": 0}]})):
            with self.subTest(text=text):
                path.write_text(text)
                code, err = self.recover(evidence=str(path))
                self.assertEqual((2, True), (code, "BENCH_RECOVERY_EVIDENCE_INVALID" in err))
        code, err = self.run_bench("--recovery-evidence", self.evidence(), "--warm", rev=self.rev)
        self.assertEqual((2, True), (code, "BENCH_RECOVERY_ARGS" in err))

    def test_evidence_shapes_are_read_by_content_and_unknown_stays_none(self):
        found = bench.normalize_evidence({"timings": {"before": [1.0, 2.0], "after": [0.5, 0.6]},
                                          "exits": {"before": [0, 0], "after": [0, 0]}, "jobs": 32})
        self.assertEqual(([1.0, 2.0], [0.5, 0.6], 32, None, None),
                         ([l["seconds"] for l in found["legs"]["before"]], [l["seconds"] for l in found["legs"]["after"]],
                          found["jobs"], found["rev"], found["source"]))
        found = bench.normalize_evidence({"pairs": [{"results": [{"side": "before", "seconds": 3.0, "exit": 0},
                                                                 {"side": "after", "seconds": 2.0, "exit": 0}]}],
                                          "sources": {"after": {"head": "a" * 40, "dirty_digest": "d"}}})
        self.assertEqual((1, 1, {"head": "a" * 40, "dirty_digest": "d"}), (len(found["legs"]["before"]), len(found["legs"]["after"]),
                                                                           found["source"]))

    def test_a_checkpoint_keeps_an_undecodable_path_character(self):
        probe = self.repo.parent / "sur.json"
        bench.write_atomic(probe, {"path": "caf\udcff/x"})
        self.assertEqual("caf\udcff/x", json.loads(probe.read_text(encoding="utf-8"))["path"])
        self.assertTrue(probe.read_bytes().isascii())


def shutil_rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)


class TimingCacheProbe:
    def __init__(self, repo):
        self.dir = repo / ".git" / "affected-tests"

    def write(self, name, data):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / name).write_bytes(data)

    def read(self, name):
        try:
            return (self.dir / name).read_bytes()
        except OSError:
            return None


def bench_census():
    spec = importlib.util.spec_from_file_location("bench_census", ROOT / "scripts" / "bench-census.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SchemaTests(unittest.TestCase):
    def test_the_schema_identity_and_required_fields(self):
        schema = json.loads((ROOT / "configs" / "schemas" / "bench-checks.schema.json").read_text(encoding="utf-8"))
        self.assertEqual("urn:swissknifeman:hub:bench-checks:v1", schema["$id"])
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertEqual("urn:swissknifeman:hub:bench-checks:v1", schema["properties"]["$schema"]["const"])
        for name in ("before", "after", "ratio", "cpu_count", "loadavg", "at", "pairs", "coverage"):
            self.assertIn(name, schema["required"])

    def test_a_document_missing_a_field_or_with_a_wrong_mode_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            with mock.patch.object(bench, "ROOT", repo):
                doc = {"$schema": bench.SCHEMA_ID}
                self.assertTrue(bench.validate(doc))
                self.assertTrue(any("required" in problem or "missing" in problem for problem in bench.validate(doc)))


def tempfile_dir() -> str:
    return tempfile.gettempdir()


if __name__ == "__main__":
    unittest.main()
