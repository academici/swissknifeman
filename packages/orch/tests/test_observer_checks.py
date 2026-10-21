"""Observer checks table, proposals and the timeline checks: synthetic run folders, no provider and no suite."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from orch.conductor import cli, observer, progress
from orch.conductor.infrastructure.files import RUN_FILE, runs_root



def script(module, name):  # the module id is data of the observer rule, not a dependency of this module
    return f"bash packages/{module}/scripts/{name}.sh"


VALIDATE = script("orch", "validate")
AFFECTED = "python3 scripts/affected-tests.py --run"
FULL = script("orch", "test")


def line(ts: str, event: str, **fields) -> str:
    return json.dumps({"ts": ts, "event": event, "run": "cnd-checks", **fields})


def row(check_id: str, cmd: str, green: bool = True, seconds: float = 1.0, **extra) -> dict:
    return {"id": check_id, "kind": "acceptance", "cmd": cmd, "exit": 0 if green else 1, "green": green,
            "seconds": seconds, **extra}


def skipped(check_id: str, cmd: str, reason: str = "fail_fast") -> dict:
    return {"id": check_id, "kind": "acceptance", "skipped": True, "skip_reason": reason, "green": False,
            "evidence": None, "cmd": cmd}


def reused(check_id: str, cmd: str, original: int = 40) -> dict:
    return row(check_id, cmd, seconds=0, reused=True, reused_from=f"run:{check_id}", original_seconds=original)


class ObserverChecksCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(os.path.realpath(self.tmp.name))
        (self.project / ".git").mkdir()

    def run_dir(self, state: dict, lines=None, inputs=None, options=None) -> Path:
        directory = runs_root(self.project) / "cnd-checks"
        directory.mkdir(parents=True)
        (directory / RUN_FILE).write_text(json.dumps({"items": []}), encoding="utf-8")
        journal = lines if lines is not None else [line("2026-10-21T10:00:00Z", "run.start")]
        (directory / "progress.jsonl").write_text("\n".join(journal) + "\n", encoding="utf-8")
        (directory / "state.json").write_text(json.dumps(state), encoding="utf-8")
        for ref, checks in (inputs or {}).items():
            (directory / ref).mkdir(exist_ok=True)
            (directory / ref / "input.json").write_text(json.dumps({"acceptance": {"checks": checks}}), encoding="utf-8")
        for ref, doc in (options or {}).items():
            (directory / ref).mkdir(exist_ok=True)
            (directory / ref / "options.json").write_text(json.dumps({"options": doc}), encoding="utf-8")
        return directory

    def state(self, **steps) -> dict:
        return {"status": "finished", "items": {"W1": {"steps": {
            key: {"status": "done", "result": rows} for key, rows in steps.items()}}}}

    def build(self, *args, **kwargs) -> dict:
        return observer.build(self.run_dir(*args, **kwargs), self.project)

    def proposals(self, report: dict) -> str:
        return "\n".join(report["proposals"])


class ChecksByCommandTests(ObserverChecksCase):
    def test_a_row_is_counted_by_what_it_did(self):
        state = self.state(**{
            "checks.1": [row("V1", "cmd-a", green=False, seconds=3.0), skipped("V2", "cmd-b"),
                         reused("V3", "cmd-c")],
            "checks.2": [row("V1", "cmd-a", seconds=2.0), row("V2", "cmd-b", seconds=4.0)]})
        report = self.build(state)
        table = {entry["cmd"]: entry for entry in report["checks_by_command"]}
        a, b, c = table["cmd-a"], table["cmd-b"], table["cmd-c"]
        self.assertEqual((a["runs"], a["executed"], a["invocations"], a["seconds"], a["red"], a["retried"]),
                         (2, 2, 2, 5.0, 1, 1))
        self.assertEqual((b["runs"], b["executed"], b["skipped"], b["seconds"], b["red"], b["retried"]), (2, 1, 1, 4.0, 0, 0))
        self.assertEqual((c["runs"], c["executed"], c["reused"], c["seconds"], c["saved_s"], c["reused_from"]),
                         (1, 0, 1, 0.0, 40, ["run:V3"]))
        self.assertEqual((a["ids"], a["contexts"], a["items"]), (["V1"], ["local"], ["W1"]))
        self.assertEqual(["cmd-a", "cmd-b", "cmd-c"], [entry["cmd"] for entry in report["checks_by_command"]])

    def test_contexts_are_named_and_not_merged(self):
        state = self.state(**{"checks.1": [row("V1", "python3 scripts/ecosystem-units.py standalone orch"),
                                           row("V2", "bash scripts/test-bridges.sh"),
                                           row("V3", "bash scripts/smoke-installed.sh"), row("V4", "true")]})
        table = {entry["ids"][0]: entry["contexts"] for entry in self.build(state)["checks_by_command"]}
        self.assertEqual({"V1": ["standalone"], "V2": ["partner"], "V3": ["installed"], "V4": ["local"]}, table)

    def test_attempt_steps_count_and_manual_procedures_do_not(self):
        state = self.state(**{"checks.1": [row("V1", "cmd-a"), {"id": "V2", "kind": "acceptance", "procedure": "look",
                                                                   "green": True}]})
        state["items"]["W1"]["attempts"] = [{"n": 1, "steps": {"checks.1": {"status": "done", "result": [
            row("V1", "cmd-a", green=False)]}}}]
        table = self.build(state)["checks_by_command"]
        self.assertEqual([("cmd-a", 2, 1)], [(entry["cmd"], entry["runs"], entry["red"]) for entry in table])

    def test_old_and_empty_states_have_an_empty_table(self):
        for state in ({}, {"items": {"W1": {"steps": {"checks.1": {"status": "done"}}}}},
                      {"items": {"W1": {"steps": {"checks.1": {"result": "bad"}}}}}):
            with self.subTest(state=state):
                self.tearDown_run()
                report = self.build(state)
                self.assertEqual(([], {"duplicate_modules": [], "phase_after_red": [], "executor_runs_checks": []}),
                                 (report["checks_by_command"], report["check_findings"]))
                self.assertIn("schema", report)

    def tearDown_run(self):
        import shutil
        shutil.rmtree(runs_root(self.project), ignore_errors=True)

    def test_markdown_has_the_table_and_keeps_the_old_lines(self):
        report = self.build(self.state(**{"checks.1": [row("V1", "cmd-a", seconds=2.5)]}))
        text = observer.markdown(report)
        self.assertIn("## Checks by command", text)
        self.assertIn("| `cmd-a` | V1 | local | 1 | 1 | 2.5 | 0 | 0 | 0 | 0 |", text)
        self.assertIn("- Red checks: none", text)
        self.assertIn("## Proposals", text)


class RedChecksTests(ObserverChecksCase):
    def journal(self, verdict: str) -> list:
        return [line("2026-10-21T10:00:00Z", "run.start"),
                line("2026-10-21T10:00:01Z", "stage.start", item="W1", stage="checks.1", role="deterministic"),
                line("2026-10-21T10:00:05Z", "stage.end", item="W1", stage="checks.1", role="deterministic",
                     verdict=verdict, duration_s=4)]

    def test_skipped_and_reused_rows_are_not_failures(self):
        state = self.state(**{"checks.1": [row("V1", "cmd-a", green=False), skipped("V2", "cmd-b"),
                                           reused("V3", "cmd-c")]})
        report = self.build(state, lines=self.journal("red V1,V2,V3"))
        self.assertEqual({"V1": 1}, report["red_checks"])
        self.assertIn("Checks V1 went red", self.proposals(report))
        self.assertNotIn("V2", report["proposals"][0])

    def test_a_journal_without_state_rows_keeps_its_verdict(self):
        report = self.build({"status": "finished"}, lines=self.journal("red V1,V2"))
        self.assertEqual({"V1": 1, "V2": 1}, report["red_checks"])

    def test_no_red_proposal_when_only_skipped_rows_were_named(self):
        report = self.build(self.state(**{"checks.1": [skipped("V2", "cmd-b")]}), lines=self.journal("red V2"))
        self.assertEqual({}, report["red_checks"])
        self.assertNotIn("went red", self.proposals(report))

    def test_the_red_proposal_names_diagnostics_and_not_a_rerun_of_everything(self):
        report = self.build(self.state(**{"checks.1": [row("V1", "cmd-a", green=False)]}), lines=self.journal("red V1"))
        text = self.proposals(report)
        self.assertIn("new or failing diagnostics", text)
        self.assertIn("conductor keeps the named acceptance checks", text)
        self.assertNotIn("before reporting", text)


class ProposalTests(ObserverChecksCase):
    def duplicates(self, *cmds, **steps):
        rows = [row(f"V{number}", cmd) for number, cmd in enumerate(cmds, 1)]
        return self.build(self.state(**{"checks.1": rows}))

    def test_validate_and_affected_tests_of_one_module_in_one_round(self):
        report = self.duplicates(VALIDATE, AFFECTED)
        self.assertEqual([{"item": "W1", "module": "orch", "cmds": [VALIDATE, AFFECTED]}],
                         report["check_findings"]["duplicate_modules"])
        self.assertIn(f"item W1 runs the tests of orch twice ({VALIDATE}, {AFFECTED})", self.proposals(report))

    def test_validate_next_to_the_full_script_and_a_subset_next_to_the_full_one(self):
        self.assertEqual(1, len(self.duplicates(VALIDATE, FULL)["check_findings"]["duplicate_modules"]))
        self.tearDown_run()
        self.assertEqual(1, len(self.duplicates(FULL, f"{FULL} -p 'test_a.py'")["check_findings"]["duplicate_modules"]))

    def tearDown_run(self):
        import shutil
        shutil.rmtree(runs_root(self.project), ignore_errors=True)

    def test_no_duplicate_for_a_skipping_validate_other_modules_subsets_or_contexts(self):
        cases = [("SKM_VALIDATE_SKIP_TESTS=1 " + VALIDATE, AFFECTED), (VALIDATE, script("planner", "test")),
                 (f"{FULL} -p 'a.py'", f"{FULL} -p 'b.py'"), (VALIDATE, "python3 scripts/ecosystem-units.py standalone orch"),
                 (VALIDATE, AFFECTED + " --tier full")]
        for number, cmds in enumerate(cases):
            with self.subTest(case=number):
                self.tearDown_run()
                self.assertEqual([], self.duplicates(*cmds)["check_findings"]["duplicate_modules"])

    def test_no_duplicate_when_one_of_the_pair_was_skipped_or_reused(self):
        state = self.state(**{"checks.1": [row("V1", VALIDATE), skipped("V2", AFFECTED), reused("V3", FULL)]})
        self.assertEqual([], self.build(state)["check_findings"]["duplicate_modules"])

    def test_no_duplicate_across_rounds(self):
        state = self.state(**{"checks.1": [row("V1", VALIDATE)], "checks.2": [row("V2", AFFECTED)]})
        self.assertEqual([], self.build(state)["check_findings"]["duplicate_modules"])

    def test_phase_checks_after_a_red_item_check(self):
        inputs = {"W1": [{"id": "V1", "cmd": "a"}, {"id": "V2", "cmd": "b", "cadence": "phase"}]}
        state = self.state(**{"checks.1": [row("V1", "a", green=False), row("V2", "b")]})
        report = self.build(state, inputs=inputs)
        self.assertEqual([{"item": "W1", "step": "checks.1"}], report["check_findings"]["phase_after_red"])
        self.assertIn("phase checks of W1 ran after a red item check", self.proposals(report))

    def test_phase_checks_skipped_after_red_or_run_after_green_are_fine(self):
        inputs = {"W1": [{"id": "V1", "cmd": "a"}, {"id": "V2", "cmd": "b", "cadence": "phase"}]}
        for rows in ([row("V1", "a", green=False), skipped("V2", "b", "phase_after_red")],
                     [row("V1", "a"), row("V2", "b", green=False)]):
            with self.subTest(rows=rows):
                self.tearDown_run()
                report = self.build(self.state(**{"checks.1": rows}), inputs=inputs)
                self.assertEqual([], report["check_findings"]["phase_after_red"])

    def test_phase_rule_needs_the_cadence_of_the_input(self):
        state = self.state(**{"checks.1": [row("V1", "a", green=False), row("V2", "b")]})
        self.assertEqual([], self.build(state)["check_findings"]["phase_after_red"])

    def test_executor_runs_checks_true(self):
        report = self.build(self.state(), options={"W1": {"checks": {"executor_runs_checks": True}}})
        self.assertEqual(["W1"], report["check_findings"]["executor_runs_checks"])
        self.assertIn("checks.executor_runs_checks is true: the executor and the conductor run the same checks",
                      self.proposals(report))
        self.tearDown_run()
        report = self.build(self.state(), options={"W1": {"checks": {"executor_runs_checks": False}}})
        self.assertEqual([], report["check_findings"]["executor_runs_checks"])


class GroupReviewRegressionTests(ObserverChecksCase):
    def test_current_run_group_findings_are_shown_and_never_inferred_clean(self):
        group = {"format": "findings", "error": None, "counts": {"Blocker": 1, "Major": 2, "Minor": 0},
                 "refs": ["P2.1", "P2.2"], "file": "group-review-1.md", "followup": "fix.json"}
        state = dict(self.state(), group_reviews={"1": group})
        report = self.build(state)
        self.assertEqual({"Blocker": 1, "Major": 2}, report["findings_by_severity"])
        self.assertEqual({"1": group}, report["group_reviews"])
        self.assertEqual({"confirmed": 0, "rejected": 0}, report["triage"])
        self.assertIn("Review findings: Blocker 1, Major 2", observer.markdown(report))
        self.tearDown_run()
        broken = dict(self.state(), group_reviews={"1": dict(group, format="malformed")})
        report = self.build(broken)
        self.assertEqual(["1"], report["incomplete_group_reviews"])
        self.assertIn("Review findings: unavailable", observer.markdown(report))

    def tearDown_run(self):
        import shutil
        shutil.rmtree(runs_root(self.project), ignore_errors=True)


class TimelineChecksTests(ObserverChecksCase):
    LINES = [line("2026-10-21T10:00:00Z", "run.start"),
             line("2026-10-21T10:00:01Z", "stage.start", item="W1", stage="executor.1", role="executor"),
             line("2026-10-21T10:00:11Z", "stage.end", item="W1", stage="executor.1", role="executor", verdict="ok"),
             line("2026-10-21T10:00:12Z", "stage.start", item="W1", stage="checks.1", role="deterministic"),
             line("2026-10-21T10:00:30Z", "stage.end", item="W1", stage="checks.1", role="deterministic",
                  verdict="red V1"),
             line("2026-10-21T10:00:31Z", "run.end")]

    def rows(self):
        return [row("V1", "cmd-a", green=False, seconds=12.4), skipped("V2", "cmd-b"), reused("V3", "cmd-c", 12)]

    def test_a_checks_interval_carries_the_rows_and_others_do_not(self):
        lines = [json.loads(text) for text in self.LINES]
        plain = progress.timeline(lines)
        self.assertTrue(all("checks" not in interval for interval in plain))
        found = progress.timeline(lines, state=self.state(**{"checks.1": self.rows()}))
        self.assertNotIn("checks", found[0])
        checks = found[1]["checks"]
        self.assertEqual(["V1", "V2", "V3"], [entry["id"] for entry in checks])
        self.assertEqual((12.4, False, False, False), (checks[0]["seconds"], checks[0]["green"], checks[0]["skipped"],
                                                       checks[0]["reused"]))
        self.assertEqual(("fail_fast", True), (checks[1]["skip_reason"], checks[1]["skipped"]))
        self.assertEqual((True, "run:V3", 12), (checks[2]["reused"], checks[2]["reused_from"], checks[2]["original_seconds"]))
        self.assertEqual([True, False, False], [entry["executed"] for entry in checks])

    def test_a_missing_or_partial_state_gives_no_rows_and_no_error(self):
        lines = [json.loads(text) for text in self.LINES]
        for state in ({}, {"items": {"W1": "x"}}, {"items": {"W1": {"steps": {"checks.1": {"result": None}}}}}):
            self.assertEqual([], progress.timeline(lines, state=state)[1]["checks"])

    def conduct(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--project", str(self.project), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_the_command_prints_json_and_text_under_the_interval(self):
        self.run_dir(self.state(**{"checks.1": self.rows()}), lines=self.LINES)
        code, out, err = self.conduct("timeline", "--run", "cnd-checks", "--json")
        self.assertEqual(0, code, err)
        intervals = json.loads(out)["intervals"]
        self.assertEqual(["V1", "V2", "V3"], [entry["id"] for entry in intervals[1]["checks"]])
        code, out, err = self.conduct("timeline", "--run", "cnd-checks")
        self.assertEqual(0, code, err)
        text = out.splitlines()
        under = text.index(next(entry for entry in text if "checks.1" in entry))
        self.assertEqual(["  - V1 12.4 s red", "  - V2 skipped (fail_fast)", "  - V3 reused (12 s)"], text[under + 1:under + 4])
        self.assertTrue(text[0].endswith("W1 executor.1: done, 10 s (ok)"), text[0])

    def test_a_run_without_state_prints_the_old_lines_only(self):
        directory = self.run_dir({}, lines=self.LINES)
        (directory / "state.json").unlink()
        code, out, err = self.conduct("timeline", "--run", "cnd-checks")
        self.assertEqual(0, code, err)
        self.assertEqual(2, len(out.splitlines()))


if __name__ == "__main__":
    unittest.main()
