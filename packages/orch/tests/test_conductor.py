"""The conductor on fake providers and a fake work source: every role is ``tests/fixtures/conductor/fake_role.py``
(substituted argv, no real model), the work source is ``tests/fixtures/conductor/source`` (a plan in one JSON file).

Scenarios: green at once; red checks, a correction, green; a confirmed review finding, a correction and a second
review; a finding that does not reproduce; a blocked piece of work stops the run with a report; a stop and a resume
that does not repeat closed steps; a repeated registration is a no-op; and the stops of the run (dirty tree, route
below the minimum, budget, output outside the contract).
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from orch.conductor import cli, engine, gates, progress

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "conductor"
INPUT = ROOT / "fixtures" / "exec" / "v1" / "valid" / "execution-input" / "plan-bound.json"
ROLES = ("context-scout", "executor", "reviewer", "triager")


def check(ref: str, number: int = 1) -> dict:
    return {"id": f"V{number}", "cmd": f"test -f out/{ref}.txt", "expect": "exit 0", "kind": "acceptance"}


def report(ref: str, status: str = "done", **extra) -> dict:
    doc = {"status": status, "summary": f"made {ref}", "changed_paths": [f"out/{ref}.txt"],
           "checks_run": [{"id": "V1", "cmd": f"test -f out/{ref}.txt", "exit": 0}], "evidence": [],
           "open_issues": []}
    doc.update(extra)
    return doc


def executor_ok(ref: str) -> dict:
    return {"write": {f"out/{ref}.txt": "ok\n"}, "result": report(ref)}


GREEN = {"result": {"verdict": "GREEN", "findings": []}}
FINDING = {"result": {"verdict": "ATTENTION", "findings": [
    {"id": "F1", "severity": "Major", "confidence": "high", "location": "out/W1.txt:1",
     "failure_scenario": "the file says ok, the contract wants done", "basis": "input contract"}]}}


class ConductorCase(unittest.TestCase):
    scenario = "full"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.home, self.project, self.fake = base / "home", base / "project", base / "fake"
        self.project.mkdir()
        self.git("init", "-q", "-b", "main")
        for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"), ("commit.gpgsign", "false")):
            self.git("config", key, value)
        (self.project / ".gitignore").write_text(".swissknifeman/state/\n", encoding="utf-8")
        (self.project / "README.md").write_text("test\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.state_file = base / "source.json"
        self.script_file = base / "script.json"
        self.set_items({"W1": {}})
        self.script({})
        self.write_config()
        env = {"HOME": str(self.home), "SKM_HOME": str(self.home / "skm"), "SKM_AICORE_EVENTS__DELIVERY": "off",
               "FAKE_CS_STATE": str(self.state_file), "FAKE_CS_INPUT": str(INPUT),
               "FAKE_ROLE_SCRIPT": str(self.script_file), "FAKE_ROLE_STATE": str(self.fake),
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        cwd = Path.cwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, cwd)

    # ---------------------------------------------------------------- helpers

    def git(self, *args) -> str:
        return subprocess.run(["git", *args], cwd=self.project, capture_output=True, text=True, check=True).stdout

    def write_config(self, argv: dict | None = None, extra: str = "") -> None:
        config = self.home / "skm" / "config" / "config.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        roles = argv or {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        lines = ["schema_version = 1", "", "[orch]", 'work_source = "fake-cs"', "", "[orch.conductor.argv]"]
        lines += [f"{role} = {json.dumps(value)}" for role, value in roles.items()]
        lines += ["", "[aicore.plugins.fake-cs]", f"manifest = {json.dumps(str(FIXTURES / 'source' / 'extension.json'))}",
                  "trusted = true", "", extra]
        config.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def set_items(self, items: dict, **state) -> None:
        doc = {"order": list(items), "items": {}, "registered": {}, "commits": [], "calls": [], **state}
        for ref, fields in items.items():
            doc["items"][ref] = {"status": "todo", "title": f"Work {ref}", "scenario": self.scenario,
                                 "checks": [check(ref)], "write_set": [f"out/{ref}.txt"], **fields}
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")

    def source(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def script(self, answers: dict) -> None:
        self.script_file.write_text(json.dumps(answers), encoding="utf-8")

    def calls(self, role: str) -> int:
        counter = self.fake / f"{role}.count"
        return int(counter.read_text()) if counter.exists() else 0

    def prompt(self, role: str, number: int) -> str:
        return (self.fake / f"{role}-{number}.md").read_text(encoding="utf-8")

    def conduct(self, *argv) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main([str(item) for item in argv])
        return code, out.getvalue(), err.getvalue()

    def run_items(self, *items, extra=()) -> tuple:
        return self.conduct("run", "--plan", "T", "--items", *items, "--json-lines", *extra)

    def lines(self, err: str) -> list:
        return [json.loads(line) for line in err.splitlines() if line.startswith("{")]

    def run_dir(self, err: str) -> Path:
        run_id = self.lines(err)[0]["run"]
        return engine.runs_root(self.project) / run_id

    def state(self, err: str) -> dict:
        return json.loads((self.run_dir(err) / engine.STATE_FILE).read_text(encoding="utf-8"))

    def outcome(self, err: str) -> tuple:
        end = [line for line in self.lines(err) if line["event"] == "run.end"][-1]
        return end["outcome"], end.get("reason_code")


class HappyPathTests(ConductorCase):
    def test_green_at_once_registers_commits_and_reports(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, out, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        source = self.source()
        self.assertEqual(source["items"]["W1"]["status"], "done")
        self.assertEqual(source["items"]["W1"]["report"]["summary"], "made W1")
        self.assertNotIn("status", source["items"]["W1"]["report"])  # the status travels apart from the report
        self.assertEqual(source["items"]["W1"]["executed_by"]["provider"], "claude-code")
        self.assertEqual([commit["ref"] for commit in source["commits"]], ["W1"])
        self.assertIn("plans/T/artifacts/W1/", source["commits"][0]["paths"])
        self.assertEqual((self.calls("executor"), self.calls("reviewer"), self.calls("triager")), (1, 1, 0))
        # every stage printed its start and its end; the journal holds the same lines
        stages = [(line["event"], line.get("stage")) for line in self.lines(err) if line["event"].startswith("stage.")]
        for key in ("brief", "prepare", "scout", "executor.1", "checks.1", "review.1", "register", "commit"):
            self.assertIn(("stage.start", key), stages)
            self.assertIn(("stage.end", key), stages)
        journal = progress.read_lines(self.run_dir(err))
        self.assertEqual(journal, self.lines(err))
        from orch.conductor import contract
        for line in journal:
            self.assertEqual(contract.problems(line, "progress-line"), [], line)
        # the committed artifacts: stage-report, review verdict, evidence; the streams stay in the state folder
        artifacts = self.project / "plans/T/artifacts/W1"
        self.assertEqual(json.loads((artifacts / "stage-report.json").read_text())["status"], "done")
        verdict = json.loads((artifacts / "review-verdict.json").read_text())
        self.assertEqual((verdict["selector"], verdict["rounds"][0]["verdict"]), ("grok/grok-4.7/high", "GREEN"))
        self.assertTrue(verdict["rounds"][0]["stream"].startswith(".swissknifeman/state/orch/conductor/"))
        evidence = json.loads((artifacts / "evidence/V1.json").read_text())
        self.assertEqual((evidence["exit"], evidence["subject"], evidence["producer"]["kind"]), (0, "PLAN9.W1", "engine"))
        tracked = self.git("ls-files").split()
        self.assertTrue(all(not path.startswith(".swissknifeman/state/") for path in tracked))
        self.assertIn("plans/T/artifacts/W1/stage-report.json", tracked)
        report_dir = self.project / engine.REPORTS / self.run_dir(err).name
        observer = json.loads((report_dir / "observer.json").read_text())
        self.assertEqual(observer["items"][0]["outcome"], "done")
        self.assertIn("orch.run.finished", observer["events"])
        self.assertTrue((report_dir / "observer.md").read_text().startswith("# Observer report"))

    def test_the_executor_sees_the_brief_rules_and_scout_but_never_the_plan(self):
        self.set_items({"W1": {"options": [{"source": "phase:P1", "options": {"rules": ["phase rule"]}},
                                            {"source": "item:W1", "options": {"rules": ["item rule"]}}]}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        prompt = self.prompt("executor", 1)
        self.assertIn("Create the output of W1.", prompt)
        self.assertIn("- phase rule\n- item rule", prompt)
        self.assertIn("## Context map", prompt)
        self.assertIn("```stage-report", prompt)
        self.assertIn("[orch] <UTC time> W1 executor.1", prompt)
        self.assertNotIn("plan" + ".py", prompt)
        options = json.loads((self.run_dir(err) / "W1" / "options.json").read_text())
        self.assertEqual(options["sources"]["rules"], "item:W1")

    def test_batch_takes_the_ready_pieces_one_by_one(self):
        self.set_items({"W1": {}, "W2": {}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN]})
        code, _, err = self.conduct("run", "--plan", "T", "--batch", "--quiet")
        self.assertEqual(code, 0, err)
        self.assertEqual([commit["ref"] for commit in self.source()["commits"]], ["W1", "W2"])

    def test_scout_cache_is_reused_for_the_same_brief(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        self.assertEqual(self.run_items("W1")[0], 0)
        self.set_items({"W1": {}})
        self.git("reset", "-q", "--hard", "HEAD~1")
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("context-scout"), 1)
        scout = [line for line in self.lines(err) if line.get("stage") == "scout" and line["event"] == "stage.end"]
        self.assertEqual(scout[0]["verdict"], "cache")


class CorrectionTests(ConductorCase):
    def test_red_check_gets_one_correction_then_green(self):
        self.script({"executor": [{"result": report("W1")}, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertIn("These acceptance checks are red", self.prompt("executor", 2))
        verdicts = {line["stage"]: line.get("verdict") for line in self.lines(err) if line["event"] == "stage.end"}
        self.assertEqual((verdicts["checks.1"], verdicts["checks.2"]), ("red V1", "green"))
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")

    def test_project_instructions_can_be_kept_away_from_a_claude_code_role(self):
        eng = engine.Conductor.__new__(engine.Conductor)
        eng.env = {"PATH": "/bin"}
        item = type("I", (), {"options": {"instructions": {"isolate_roles": ["executor", "registrar"]}}})()
        env = eng._role_env(item, "executor", {"provider": "claude-code"})
        self.assertEqual((env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"], env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"]), ("1", "1"))
        self.assertEqual(env["PATH"], "/bin")
        self.assertEqual(eng._role_env(item, "reviewer", {"provider": "claude-code"}), {"PATH": "/bin"})
        self.assertEqual(eng._role_env(item, "executor", {"provider": "grok"}), {"PATH": "/bin"})
        self.assertEqual(eng._role_argv(item, "executor", {"provider": "claude-code", "argv": ["claude", "-p"]}),
                         ["claude", "-p", "--safe-mode"])
        self.assertEqual(eng._role_argv(item, "reviewer", {"provider": "claude-code", "argv": ["claude", "-p"]}), ["claude", "-p"])
        self.assertEqual(eng._role_argv(item, "executor", {"provider": "grok", "argv": ["grok"]}), ["grok"])

    def test_a_rejected_major_finding_is_kept_as_a_plan_note(self):
        eng = engine.Conductor.__new__(engine.Conductor)
        item = type("I", (), {"options": {"review": {"correct_min_severity": "Major"}}, "state": {}})()
        findings = {"findings": [
            {"id": "F1", "severity": "Major", "location": "a.py:1", "failure_scenario": "real defect"},
            {"id": "F2", "severity": "Minor", "location": "b.py:2", "failure_scenario": "small"}]}
        triage = {"confirmed": [], "rejected": [{"finding": "F1", "reason": "outside the write set"},
                                                {"finding": "F2", "reason": "not a defect"}]}
        eng._note_rejected(item, findings, triage)
        eng._note_rejected(item, findings, triage)
        notes = item.state["plan_notes"]
        self.assertEqual(len(notes), 1)
        self.assertIn("a.py:1", notes[0]["text"])
        self.assertIn("outside the write set", notes[0]["text"])

    def test_the_executor_is_told_to_run_only_the_tests_of_its_change_unless_asked_otherwise(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        self.assertEqual(self.run_items("W1")[0], 0)
        self.assertIn("The conductor runs these commands itself", self.prompt("executor", 1))
        self.assertNotIn("Run every acceptance check of the input yourself", self.prompt("executor", 1))
        self.assertIn("`test -f out/W1.txt`", self.prompt("executor", 1))
        self.set_items({"W2": {"options": [{"source": "item:W2", "options": {"checks": {"executor_runs_checks": True}}}]}})
        self.script({"executor": [executor_ok("W2")], "reviewer": [GREEN]})
        self.assertEqual(self.run_items("W2")[0], 0)
        self.assertIn("Run every acceptance check of the input yourself", self.prompt("executor", 2))
        self.assertNotIn("The conductor runs these commands itself", self.prompt("executor", 2))

    def overlapping(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {
            "checks": {"parallel": 2, "overlap_review": True}}}]}})

    def test_checks_overlap_the_first_review_when_green(self):
        self.overlapping()
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (1, 1))
        self.assertIn("at the same time", self.prompt("reviewer", 1))
        verdicts = {line["stage"]: line.get("verdict") for line in self.lines(err) if line["event"] == "stage.end"}
        self.assertEqual(verdicts["checks.1"], "green")

    def test_checks_overlap_the_review_after_a_correction_too(self):
        self.overlapping()
        repro = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": repro, "fix": "write done"}], "rejected": []}}
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [FINDING, GREEN], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("reviewer"), 2)
        self.assertIn("at the same time", self.prompt("reviewer", 2))
        self.assertIn("Pre-final audit", self.prompt("reviewer", 2))
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")

    def test_a_red_check_cancels_the_slow_overlapping_review_at_once(self):
        from orch.conductor import process
        old = process.POLL_S
        process.POLL_S = 0.2
        self.addCleanup(setattr, process, "POLL_S", old)
        self.overlapping()
        self.script({"executor": [{"result": report("W1")}, executor_ok("W1")],
                     "reviewer": [dict(GREEN, sleep=60), GREEN]})
        started = time.monotonic()
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertLess(time.monotonic() - started, 40)  # the 60 s review was cancelled, not awaited
        cancelled = [line for line in self.lines(err) if line.get("reason_code") == "REVIEW_CANCELLED"]
        self.assertEqual(len(cancelled), 1, err)
        self.assertEqual(self.calls("reviewer"), 2)

    def test_a_finished_review_is_kept_when_slow_checks_turn_red(self):
        slow = {"id": "V1", "cmd": "sleep 2; test -f out/W1.txt", "expect": "exit 0", "kind": "acceptance"}
        self.set_items({"W1": {"checks": [slow], "options": [{"source": "item:W1", "options": {
            "checks": {"parallel": 1, "overlap_review": True}}}]}})
        repro = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": repro, "fix": "write done"}], "rejected": []}}
        fixed = {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}
        self.script({"executor": [{"result": report("W1")}, fixed], "reviewer": [FINDING, GREEN], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        # one correction round for the red check AND the finding; the review is not repeated, only the pre-final audit runs
        self.assertEqual((self.calls("executor"), self.calls("reviewer"), self.calls("triager")), (2, 2, 1))
        correction = self.prompt("executor", 2)
        self.assertIn("These acceptance checks are red", correction)
        self.assertIn("write done", correction)
        self.assertIn("Pre-final audit", self.prompt("reviewer", 2))
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")

    def test_red_checks_drop_the_overlapping_review_and_repeat_it_after_the_correction(self):
        self.overlapping()
        self.script({"executor": [{"result": report("W1")}, executor_ok("W1")],
                     "reviewer": [dict(GREEN, sleep=5), GREEN]})  # slow: the red check cancels it before it finishes
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (2, 2))
        self.assertIn("at the same time", self.prompt("reviewer", 2))  # the repeated review overlaps the checks again
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")

    def test_red_after_the_correction_limit_blocks_and_stops(self):
        self.script({"executor": [{"result": report("W1")}]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual(self.calls("executor"), 2)
        item = self.source()["items"]["W1"]
        self.assertEqual(item["status"], "blocked")
        self.assertIn("CHECKS_RED", item["report"]["open_issues"][-1]["text"])
        self.assertEqual(self.source()["commits"], [])

    def test_confirmed_finding_is_corrected_and_reviewed_again(self):
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": {"cmd": "cat out/W1.txt", "exit": 0,
                                                                              "observed": "ok"},
                                            "fix": "write done instead of ok"}], "rejected": []}}
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [FINDING, GREEN], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer"), self.calls("triager")), (2, 2, 1))
        correction = self.prompt("executor", 2)
        self.assertIn("reproduced: `cat out/W1.txt`", correction)
        self.assertIn("fix: write done instead of ok", correction)
        self.assertIn("review round 2", self.prompt("reviewer", 2))
        verdict = json.loads((self.project / "plans/T/artifacts/W1/review-verdict.json").read_text())
        self.assertEqual([item["verdict"] for item in verdict["rounds"]], ["ATTENTION", "GREEN"])
        self.assertEqual(verdict["rounds"][0]["triage"]["confirmed"], ["F1"])
        self.assertIn("triage_reproduction", verdict["rounds"][0]["findings"][0])
        self.assertEqual((self.project / "out/W1.txt").read_text(), "done\n")

    def test_the_last_round_corrects_without_another_review_when_final_correction_is_on(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {
            "limits": {"review_rounds": 1}, "review": {"final_correction": True}}}]}})
        repro = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": repro, "fix": "write done"}], "rejected": []}}
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [FINDING], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (2, 1))
        item = self.source()["items"]["W1"]
        self.assertEqual(item["status"], "done")
        self.assertTrue(any("not reviewed again" in i["text"] for i in item["report"]["open_issues"]))

    def test_the_audit_after_a_correction_is_scoped_to_the_corrected_findings(self):
        repro = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": repro, "fix": "write done"}], "rejected": []}}
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [FINDING, GREEN], "triager": [triage]})
        self.assertEqual(self.run_items("W1")[0], 0)
        self.assertNotIn("Scope of this round", self.prompt("reviewer", 1))
        second = self.prompt("reviewer", 2)
        self.assertIn("Scope of this round", second)
        self.assertIn("F1 (Major, out/W1.txt:1)", second)
        self.assertIn("correction asked: write done", second)

    def test_a_confirmed_minor_finding_is_deferred_to_the_plan_without_a_correction(self):
        minor = {"result": {"verdict": "ATTENTION", "findings": [dict(FINDING["result"]["findings"][0], severity="Minor")]}}
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": {"cmd": "cat out/W1.txt", "exit": 0,
                                                                              "observed": "ok"}, "fix": "write done"}],
                             "rejected": []}}
        self.script({"executor": [executor_ok("W1")], "reviewer": [minor], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer"), self.calls("triager")), (1, 1, 1))
        item = self.source()["items"]["W1"]
        self.assertEqual(item["status"], "done")
        self.assertTrue(any(i["text"].startswith("deferred minor finding") for i in item["report"]["open_issues"]))

    def test_major_findings_are_corrected_minor_ones_deferred_and_the_audit_is_pre_final(self):
        mixed = {"result": {"verdict": "ATTENTION", "findings": [
            dict(FINDING["result"]["findings"][0]), dict(FINDING["result"]["findings"][0], id="F2", severity="Minor")]}}
        repro = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": repro, "fix": "major fix"},
                                           {"finding": "F2", "reproduction": repro, "fix": "minor fix"}], "rejected": []}}
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [mixed, GREEN], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (2, 2))
        self.assertIn("major fix", self.prompt("executor", 2))
        self.assertNotIn("minor fix", self.prompt("executor", 2))
        self.assertNotIn("Pre-final audit", self.prompt("reviewer", 1))
        self.assertIn("Pre-final audit", self.prompt("reviewer", 2))
        issues = self.source()["items"]["W1"]["report"]["open_issues"]
        self.assertEqual(sum(1 for i in issues if i["text"].startswith("deferred minor")), 1)

    def test_review_options_set_the_correction_floor_and_the_pre_final_audit(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {
            "review": {"correct_min_severity": "Minor", "pre_final": False}}}]}})
        mixed = {"result": {"verdict": "ATTENTION", "findings": [
            dict(FINDING["result"]["findings"][0], id="F2", severity="Minor")]}}
        repro = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}
        triage = {"result": {"confirmed": [{"finding": "F2", "reproduction": repro, "fix": "minor fix"}], "rejected": []}}
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [mixed, GREEN], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIn("minor fix", self.prompt("executor", 2))  # a Minor is corrected when the floor says so
        self.assertNotIn("Pre-final audit", self.prompt("reviewer", 2))  # pre_final off: a full review again

    def test_finding_that_does_not_reproduce_is_rejected_without_a_correction(self):
        triage = {"result": {"confirmed": [], "rejected": [{"finding": "F1", "reason": "the file is as specified",
                                                            "reproduction": {"cmd": "cat out/W1.txt", "exit": 0,
                                                                             "observed": "ok"}}]}}
        self.script({"executor": [executor_ok("W1")], "reviewer": [FINDING], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer"), self.calls("triager")), (1, 1, 1))
        verdict = json.loads((self.project / "plans/T/artifacts/W1/review-verdict.json").read_text())
        self.assertEqual(verdict["rounds"][0]["triage"]["rejected"][0]["finding"], "F1")
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")

    def test_a_deviation_survives_a_review_limit_block_and_registers(self):
        deviation = {"text": "touched a file outside the write set", "kind": "deviation", "impact": "none", "next": "none"}
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": {"cmd": "cat out/W1.txt", "exit": 0,
                                                                              "observed": "ok"}, "fix": "fix it"}],
                             "rejected": []}}
        done = dict(executor_ok("W1"), result=report("W1", "done_with_deviations", open_issues=[deviation]))
        self.script({"executor": [done, done], "reviewer": [FINDING], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        issues = self.source()["items"]["W1"]["report"]["open_issues"]
        self.assertTrue(any(i["text"].startswith("deviation: touched") for i in issues), issues)

    def test_findings_after_the_review_limit_block(self):
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": {"cmd": "cat out/W1.txt", "exit": 0,
                                                                              "observed": "ok"}, "fix": "fix it"}],
                             "rejected": []}}
        self.script({"executor": [executor_ok("W1")], "reviewer": [FINDING], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer"), self.calls("triager")), (2, 2, 2))
        self.assertIn("REVIEW_LIMIT", self.source()["items"]["W1"]["report"]["open_issues"][-1]["text"])


class StopTests(ConductorCase):
    def test_blocked_executor_stops_the_run_with_a_report(self):
        blocked = report("W1", "blocked", changed_paths=[], checks_run=[],
                         open_issues=[{"text": "needs the owner's API key", "kind": "escalation"}])
        self.script({"executor": [{"result": blocked}]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        item = self.source()["items"]["W1"]
        self.assertEqual((item["status"], item["report"]["open_issues"][0]["kind"]), ("blocked", "escalation"))
        self.assertEqual(self.calls("reviewer"), 0)
        report_md = (self.project / engine.REPORTS / self.run_dir(err).name / "observer.md").read_text()
        self.assertIn("W1 is blocked", report_md)

    def test_on_blocked_report_goes_on_with_the_next_piece(self):
        blocked = report("W1", "blocked", changed_paths=[], checks_run=[],
                         open_issues=[{"text": "needs a decision", "kind": "escalation"}])
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"on_blocked": "report"}}]}, "W2": {}})
        self.script({"executor": [{"result": blocked}, executor_ok("W2")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", "W2")
        self.assertEqual(code, 0, err)
        self.assertEqual({ref: item["status"] for ref, item in self.source()["items"].items()},
                         {"W1": "blocked", "W2": "done"})

    def test_a_missing_provider_stops_before_any_work(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        missing = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        missing["reviewer"] = [str(self.project / "no-such-grok")]
        self.write_config(missing)
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_UNAVAILABLE")), err)
        self.assertIn("reviewer", [line for line in self.lines(err) if line["event"] == "run.end"][0]["message"])
        self.assertEqual(self.calls("executor"), 0)  # the preflight: no hour of work before a role that cannot start
        self.write_config()
        code, _, err = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 1)

    def test_an_acp_role_stops_the_run_before_any_work(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        options = self.project.parent / "grok-executor.json"
        options.write_text(json.dumps({"stages": [{"role": "executor", "provider": "grok"}]}), encoding="utf-8")
        code, _, err = self.run_items("W1", extra=("--options", options))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TRANSPORT_UNSUPPORTED")), err)
        message = [line for line in self.lines(err) if line["event"] == "run.end"][0]["message"]
        self.assertIn("executor on grok", message)
        self.assertEqual(self.calls("executor"), 0)

    def test_a_stop_and_a_resume_repeat_no_closed_step(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        self.set_items({"W1": {}}, refuse=["register"])
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "REGISTER_REFUSED")), err)
        self.assertEqual(self.calls("executor"), 1)
        run_id = self.run_dir(err).name
        status = self.conduct("status", "--run", run_id, "--json")
        self.assertEqual(json.loads(status[1])["status"], "stopped")
        code, _, err = self.conduct("resume", "--run", run_id, "--json-lines")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual((self.calls("executor"), self.calls("context-scout"), self.calls("reviewer")), (1, 1, 1))
        skipped = [line["stage"] for line in self.lines(err) if line["event"] == "stage.skip"]
        self.assertEqual(skipped, ["brief", "prepare", "scout", "executor.1", "checks.1", "review.1"])
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")

    def test_a_repeated_registration_is_a_no_op(self):
        self.set_items({"W1": {}}, refuse=["commit"])
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "COMMIT_REFUSED")), err)
        run_dir = self.run_dir(err)
        state = json.loads((run_dir / engine.STATE_FILE).read_text())
        del state["items"]["W1"]["steps"]["register"]  # as if the run died between the source's answer and the record
        (run_dir / engine.STATE_FILE).write_text(json.dumps(state))
        code, _, err = self.conduct("resume", "--run", run_dir.name, "--json-lines")
        self.assertEqual(code, 0, err)
        registers = [call for call in self.source()["calls"] if call["op"] == "register"]
        self.assertEqual(len(registers), 2)
        verdict = [line for line in self.lines(err) if line.get("stage") == "register" and line["event"] == "stage.end"]
        self.assertTrue(verdict[0]["verdict"].startswith("no-op"), verdict)
        self.assertEqual([commit["ref"] for commit in self.source()["commits"]], ["W1"])

    def test_a_blocked_piece_can_be_retried_from_its_blocked_round(self):
        blocked = report("W1", "blocked", open_issues=[{"text": "needs a path outside the write set", "kind": "escalation"}])
        self.script({"executor": [{"result": blocked}, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        doc = self.source()
        doc["items"]["W1"]["status"] = "todo"  # the source reopened it
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        code, _, err = self.conduct("resume", "--run", self.run_dir(err).name, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 2)
        started = [line["stage"] for line in self.lines(err) if line["event"] == "stage.start"]
        self.assertIn("brief", started)  # the input is built again from the amended plan
        self.assertIn("executor.1", started)
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")

    def test_a_resume_does_not_count_the_closed_correction_rounds_again(self):
        repro = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": repro, "fix": "write done"}], "rejected": []}}
        self.set_items({"W1": {}}, refuse=["commit"])
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [FINDING, GREEN], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "COMMIT_REFUSED")), err)
        doc = self.source()
        doc["refuse"] = []
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        code, _, err = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)  # the old counter said REVIEW_LIMIT
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")

    def test_a_dirty_tree_stops_before_new_work(self):
        (self.project / "stray.txt").write_text("x", encoding="utf-8")
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "WORKTREE_DIRTY")), err)
        self.assertEqual([call["op"] for call in self.source()["calls"]], [])

    def test_a_route_below_the_minimum_stops_before_the_executor(self):
        self.set_items({"W1": {"route": {"class": "frontier", "effort": "high"}}})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ROUTE_UNDERSHOOT")), err)
        self.assertEqual(self.calls("executor"), 0)

    def test_a_spent_budget_is_a_beacon_not_a_stop(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"limits": {"tokens_max": 50}}}]}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        beacons = [line for line in self.lines(err) if line.get("reason_code") == "BUDGET_OVER"]
        self.assertEqual(len(beacons), 1)

    def test_cache_reads_are_not_counted_against_the_budget(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"limits": {"tokens_max": 500}}}]}})
        usage = {"input_tokens": 100, "cache_read_input_tokens": 90000, "output_tokens": 10}
        self.script({"executor": [dict(executor_ok("W1"), usage=usage)], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)

    def test_output_outside_the_contract_is_repeated_then_stops(self):
        self.script({"executor": [{"text": "no block here"}, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertNotIn("previous answer was rejected", self.prompt("executor", 1))
        self.assertIn("previous answer was rejected", self.prompt("executor", 2))
        repeats = [line for line in self.lines(err) if line["event"] == "info" and "repeating" in line["message"]]
        self.assertEqual(len(repeats), 1)
        self.set_items({"W2": {}})
        self.script({"executor": [{"text": "never a block"}]})
        code, _, err = self.run_items("W2")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ROLE_OUTPUT_INVALID")), err)

    def test_a_checks_run_entry_with_a_foreign_id_does_not_fail_the_report(self):
        foreign = report("W1", checks_run=[{"id": "V1", "cmd": "test -f out/W1.txt", "exit": 0},
                                           {"id": "unit-tests", "cmd": "bash test.sh", "exit": 0}])
        self.script({"executor": [dict(executor_ok("W1"), result=foreign)], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("executor")), (0, 1), err)
        issues = self.source()["items"]["W1"]["report"]["open_issues"]
        self.assertTrue(any("unit-tests" in issue["text"] for issue in issues), issues)

    def test_every_stage_has_its_own_repeats(self):
        self.script({"executor": [{"text": "no block here"}, executor_ok("W1")],
                     "reviewer": [{"text": "no block here"}, GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (2, 2))

    def test_an_empty_residual_risk_is_accepted(self):
        self.script({"executor": [executor_ok("W1")],
                     "reviewer": [{"result": {"verdict": "GREEN", "findings": [], "residual_risk": ""}}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)

    def test_invalid_options_of_the_source_stop(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"limits": {"review_rounds": 9}}}]}})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "OPTIONS_INVALID")), err)


REPRO = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}
TRIAGE_F1 = {"result": {"confirmed": [{"finding": "F1", "reproduction": REPRO, "fix": "write done"}], "rejected": []}}


class ScopeTests(ConductorCase):
    """The changed paths come from git after every executor round; paths outside the write set are a deviation."""

    def test_paths_outside_the_write_set_become_a_reviewed_deviation_and_are_committed(self):
        self.script({"executor": [{"write": {"out/W1.txt": "ok\n", "docs/extra.md": "x\n"}, "result": report("W1")}],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        item = self.source()["items"]["W1"]
        self.assertEqual(item["status"], "done_with_deviations")
        self.assertEqual(item["report"]["changed_paths"], ["docs/extra.md", "out/W1.txt"])
        self.assertTrue(any(i["kind"] == "deviation" and "docs/extra.md" in i["text"] for i in item["report"]["open_issues"]))
        self.assertIn("## Changed outside the write set", self.prompt("reviewer", 1))
        self.assertIn("`docs/extra.md`", self.prompt("reviewer", 1))
        self.assertIn("docs/extra.md", self.source()["commits"][0]["paths"])

    def test_scope_outside_block_stops_the_piece_right_after_the_executor(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"scope": {"outside": "block"}}}]}})
        self.script({"executor": [{"write": {"out/W1.txt": "ok\n", "docs/extra.md": "x\n"}, "result": report("W1")}]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (1, 0))
        self.assertIn("OUTSIDE_WRITE_SET", self.source()["items"]["W1"]["report"]["open_issues"][-1]["text"])

    def test_changed_paths_are_the_union_of_every_round_not_the_last_report(self):
        self.set_items({"W1": {"write_set": ["out/**"], "checks": [check("W1"), {"id": "V2", "cmd": "test -f out/b.txt",
                                                                                "expect": "exit 0", "kind": "acceptance"}]}})
        second = {"write": {"out/b.txt": "b\n"}, "result": report("W1", changed_paths=["out/b.txt"])}
        self.script({"executor": [executor_ok("W1"), second], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.source()["items"]["W1"]["report"]["changed_paths"], ["out/W1.txt", "out/b.txt"])
        self.assertEqual(self.git("status", "--porcelain", "--", "out").strip(), "")


class HealAndRepairTests(ConductorCase):
    def test_a_form_mismatch_is_healed_without_a_repeat(self):
        healed = report("W1", "done_with_deviations",
                        checks_run=[{"id": "V1", "cmd": "test -f out/W1.txt", "exit": "0"}],
                        open_issues=[{"text": "a gap", "kind": "Escalation"}])
        self.script({"executor": [dict(executor_ok("W1"), result=healed)], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("executor")), (0, 1), err)
        item = self.source()["items"]["W1"]
        self.assertEqual(item["status"], "done")
        kinds = [issue["kind"] for issue in item["report"]["open_issues"]]
        self.assertIn("difficulty", kinds)
        self.assertNotIn("escalation", kinds)
        self.assertTrue(any(line.get("reason_code") == "RESULT_HEALED" for line in self.lines(err)))

    def test_a_result_outside_the_contract_is_repaired_by_the_report_fixer_before_a_repeat(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role]
                           for role in ROLES + ("report-fixer",)})
        broken = {"write": {"out/W1.txt": "ok\n"},
                  "result": report("W1", checks_run=[{"id": "V1", "cmd": "test -f out/W1.txt", "exit": "zero"}])}
        self.script({"executor": [broken], "reviewer": [GREEN],
                     "report-fixer": [{"result": report("W1"), "tag": "stage-report"}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("report-fixer")), (1, 1))
        fixer = self.prompt("report-fixer", 1)
        self.assertIn("Never raise a status", fixer)
        self.assertIn("expected integer, got string", fixer)
        self.assertTrue(any(line.get("reason_code") == "RESULT_REPAIRED" for line in self.lines(err)))

    def test_without_a_repair_the_role_is_repeated_as_before(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"limits": {"repairs": 0}}}]}})
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role]
                           for role in ROLES + ("report-fixer",)})
        self.script({"executor": [{"text": "no block here"}, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("report-fixer")), (2, 0))


class SoftLimitTests(ConductorCase):
    def two_checks(self, **options):
        v2 = {"id": "V2", "cmd": "test -f out/two.txt", "expect": "exit 0", "kind": "acceptance"}
        self.set_items({"W1": {"write_set": ["out/**"], "checks": [check("W1"), v2],
                               "options": [{"source": "item:W1", "options": options}] if options else []}})

    def test_a_correction_round_runs_the_red_checks_first_by_default(self):
        self.two_checks()
        self.script({"executor": [{"write": {"out/two.txt": "2\n"}, "result": report("W1")}, {"result": report("W1")}],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        steps = self.state(err)["items"]["W1"]["steps"]
        first, second = (steps[f"checks.{n}"]["result"] for n in (1, 2))
        self.assertEqual([(row["id"], row["green"], bool(row.get("skipped"))) for row in first],
                         [("V1", False, False), ("V2", True, False)])
        self.assertEqual([(row["id"], row["green"], bool(row.get("skipped"))) for row in second],
                         [("V1", False, False), ("V2", False, True)])  # V1 is still red: V2 is not run again

    def test_red_first_off_runs_every_check_in_every_round(self):
        self.two_checks(checks={"red_first": False})
        self.script({"executor": [{"write": {"out/two.txt": "2\n"}, "result": report("W1")}, {"result": report("W1")}],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        second = self.state(err)["items"]["W1"]["steps"]["checks.2"]["result"]
        self.assertEqual([(row["id"], bool(row.get("skipped"))) for row in second], [("V1", False), ("V2", False)])

    def test_a_correction_that_makes_progress_goes_past_the_target(self):
        self.two_checks()
        self.script({"executor": [{"result": report("W1")}, {"write": {"out/two.txt": "2\n"}, "result": report("W1")},
                                  executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("executor"), 3)
        over = [line for line in self.lines(err) if line.get("reason_code") == "LIMIT_OVER"]
        self.assertEqual(len(over), 1, err)
        self.assertTrue(any("goes past the target" in i["text"] for i in self.source()["items"]["W1"]["report"]["open_issues"]))

    def test_the_ceiling_ends_even_a_progressing_fight(self):
        self.two_checks(limits={"ceiling_factor": 1})
        self.script({"executor": [{"result": report("W1")}, {"write": {"out/two.txt": "2\n"}, "result": report("W1")},
                                  executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertIn("ceiling", self.source()["items"]["W1"]["report"]["open_issues"][-1]["text"])

    def test_a_combined_review_correction_is_sent_once(self):
        slow = {"id": "V1", "cmd": "sleep 2; test -f out/W1.txt", "expect": "exit 0", "kind": "acceptance"}
        self.set_items({"W1": {"checks": [slow], "options": [{"source": "item:W1", "options": {
            "checks": {"overlap_review": True}, "limits": {"check_fixes": 2}}}]}})
        self.script({"executor": [{"result": report("W1")}, {"result": report("W1")}, executor_ok("W1")],
                     "reviewer": [FINDING, GREEN], "triager": [TRIAGE_F1]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIn("The review found these defects", self.prompt("executor", 2))
        self.assertNotIn("The review found these defects", self.prompt("executor", 3))


class BeaconTests(ConductorCase):
    def fast_polls(self):
        from orch.conductor import checks as checks_mod, process
        for module in (process, checks_mod):
            old = module.POLL_S
            module.POLL_S = 0.2
            self.addCleanup(setattr, module, "POLL_S", old)

    def test_a_silent_role_and_a_long_check_print_beacons_and_are_not_stopped(self):
        self.fast_polls()
        slow = {"id": "V1", "cmd": "sleep 2; test -f out/W1.txt", "expect": "exit 0", "kind": "acceptance"}
        self.set_items({"W1": {"checks": [slow], "options": [{"source": "item:W1", "options": {
            "limits": {"stage_idle_warn_s": 1, "check_warn_s": 1}}}]}})
        self.script({"executor": [dict(executor_ok("W1"), sleep=2.5)], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        codes = [line.get("reason_code") for line in self.lines(err) if line["event"] == "info"]
        self.assertIn("STAGE_IDLE", codes)
        self.assertIn("CHECK_SLOW", codes)
        idle = next(line for line in self.lines(err) if line.get("reason_code") == "STAGE_IDLE")
        self.assertIn("no output for", idle["message"])
        self.assertIn("no child process", idle["message"])  # the fake provider sleeps in its own process
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")


class RepositoryRulesTests(ConductorCase):
    def test_an_isolated_role_gets_the_module_rules_and_nothing_else_of_claude_md(self):
        (self.project / "CLAUDE.md").write_text("# Rules\n\n## root.module-folders\nEvery module is a folder. <!-- swissknifeman:marker --> <!-- semantic:x -->\n\n"
                                                "## root.quality\nQuality over speed.\n", encoding="utf-8")
        (self.project / "out").mkdir()
        (self.project / "out" / "CLAUDE.md").write_text("## out.module-boundaries\nImport only out.\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "rules")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        prompt = self.prompt("executor", 1)
        self.assertIn("## Repository rules", prompt)
        self.assertIn("Every module is a folder.", prompt)
        self.assertIn("Import only out.", prompt)
        self.assertNotIn("<!--", prompt.split("## Repository rules")[1].split("## Context map")[0])
        self.assertNotIn("Quality over speed", prompt)


class AdoptAndSettleTests(ConductorCase):
    def test_adopt_takes_over_an_earlier_attempt_inside_the_write_set(self):
        (self.project / "out").mkdir()
        (self.project / "out" / "W1.txt").write_text("half\n", encoding="utf-8")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--adopt",))
        self.assertEqual(code, 0, err)
        self.assertIn("A previous attempt at this piece of work is already in the working tree", self.prompt("executor", 1))
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")

    def test_adopt_allows_the_artifact_folder_of_the_piece(self):
        evidence = self.project / "plans/T/artifacts/W1/evidence"
        evidence.mkdir(parents=True)
        (evidence / "V1.json").write_text("{}\n", encoding="utf-8")  # left by the stopped attempt
        (self.project / "out").mkdir()
        (self.project / "out" / "W1.txt").write_text("half\n", encoding="utf-8")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--adopt",))
        self.assertEqual(code, 0, err)
        prompt = self.prompt("executor", 1)
        self.assertIn("out/W1.txt", prompt)
        self.assertNotIn("artifacts/W1/evidence", prompt.split("A previous attempt")[1].split("\n")[0])

    def test_adopt_refuses_changes_outside_the_write_set(self):
        (self.project / "stray.txt").write_text("x", encoding="utf-8")
        code, _, err = self.run_items("W1", extra=("--adopt",))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "WORKTREE_DIRTY")), err)
        self.assertEqual(self.calls("executor"), 0)
        # the stop came before any work: the claim is given back, so that a new run can claim the piece
        self.assertEqual((self.source()["items"]["W1"]["status"], self.source()["items"]["W1"].get("holder")), ("todo", None))
        self.assertIn("CLAIM_RELEASED", err)

    def test_release_command_gives_back_a_claim_the_source_kept(self):
        self.set_items({"W1": {}}, refuse=["release"])
        (self.project / "stray.txt").write_text("x", encoding="utf-8")
        code, _, err = self.run_items("W1", extra=("--adopt",))
        self.assertEqual(code, 1, err)
        self.assertIn("CLAIM_KEPT", err)
        self.assertEqual(self.source()["items"]["W1"]["status"], "in_progress")  # still held by the dead run
        run_id = self.run_dir(err).name
        code, _, err2 = self.conduct("release", "--run", run_id, "--item", "W1", "--reason", "the run died")
        self.assertEqual(code, 0, err2)
        self.assertEqual((self.source()["items"]["W1"]["status"], self.source()["items"]["W1"].get("holder")), ("todo", None))

    def test_release_refuses_a_piece_that_has_work_in_the_tree(self):
        self.script({"executor": [{"result": report("W1", "blocked", open_issues=[{"text": "x", "kind": "escalation"}])}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        code, _, err2 = self.conduct("release", "--run", self.run_dir(err).name, "--item", "W1")
        self.assertEqual(code, 1, err2)
        self.assertIn("RELEASE_WORK_BEGAN", err2)

    def test_settle_closes_a_piece_by_hand(self):
        blocked = report("W1", "blocked", open_issues=[{"text": "needs a decision", "kind": "escalation"}])
        self.script({"executor": [{"result": blocked}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        run_id = self.run_dir(err).name
        code, _, err2 = self.conduct("settle", "--run", run_id, "--item", "W1", "--outcome", "done",
                                     "--reason", "finished by the owner")
        self.assertEqual(code, 0, err2)
        state = json.loads((engine.runs_root(self.project) / run_id / engine.STATE_FILE).read_text())
        self.assertEqual(state["items"]["W1"]["outcome"], "done")
        self.assertEqual(state["items"]["W1"]["settled"][0]["reason"], "finished by the owner")
        code, out, _ = self.conduct("status", "--run", run_id, "--json")
        self.assertEqual([row["outcome"] for row in json.loads(out)["items"] if row["item"] == "W1"], ["done"])


class AmendedPlanTests(ConductorCase):
    def test_a_plan_amended_during_the_piece_reaches_the_next_round(self):
        state = self.source()
        state["items"]["W1"].update(status="in_progress", goal="Create the amended output of W1.")
        amend = {"result": report("W1"), "write": {str(self.state_file): json.dumps(state)}}  # the owner edits the plan
        self.script({"executor": [amend, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("amended output", self.prompt("executor", 1))
        self.assertIn("Create the amended output of W1.", self.prompt("executor", 2))
        self.assertTrue(any(line.get("reason_code") == "INPUT_REBUILT" for line in self.lines(err)), err)

class OverlapStopTests(ConductorCase):
    def test_finished_checks_are_kept_when_the_overlapping_review_fails(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"checks": {"overlap_review": True}}}]}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [{"exit": 3}]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ROLE_FAILED")), err)
        steps = self.state(err)["items"]["W1"]["steps"]
        self.assertEqual(steps["checks.1"]["status"], "done")

class SoloTests(ConductorCase):
    scenario = "scout-solo"

    def test_a_pack_without_review_runs_no_reviewer(self):
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("context-scout"), self.calls("reviewer")), (1, 0))
        self.assertFalse((self.project / "plans/T/artifacts/W1/review-verdict.json").exists())


class ClosingTests(ConductorCase):
    """A layer of the options that names the registrar adds the closing stage: a model records the result."""

    scenario = "full"
    NAMED = [{"source": "phase:P1", "options": {"stages": [{"role": "registrar", "model_class": "economy"}]}}]

    def setUp(self):
        super().setUp()
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES + ("registrar",)})
        self.set_items({"W1": {"options": self.NAMED}})

    def steps(self, err: str) -> dict:
        return self.state(err)["items"]["W1"]["steps"]

    def test_the_closer_runs_the_one_command_and_the_conductor_repeats_it_as_a_no_op(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN], "registrar": [{"run_command": True}]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("registrar"), 1)
        prompt = self.prompt("registrar", 1)
        self.assertIn("orch.py source register --run", prompt)
        self.assertNotIn("Plan-bound", prompt)  # the closer never sees the task
        steps = self.steps(err)
        self.assertEqual(steps["close"]["result"]["by"], "closer")
        self.assertEqual(steps["close"]["route"].split("/")[0], "claude-code")
        self.assertEqual(steps["register"]["result"]["outcome"], "no-op")
        self.assertIn("recorded by the closer", steps["register"]["verdict"])
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")
        self.assertEqual([commit["ref"] for commit in self.source()["commits"]], ["W1"])
        order = [line["stage"] for line in self.lines(err) if line["event"] == "stage.start"]
        self.assertLess(order.index("review.1"), order.index("close"))
        self.assertLess(order.index("close"), order.index("register"))

    def test_a_closer_that_fails_leaves_the_recording_to_the_conductor(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN], "registrar": [{"exit": 3}]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        steps = self.steps(err)
        self.assertEqual(steps["close"]["result"]["by"], "conductor")
        self.assertEqual(steps["close"]["result"]["reason_code"], "ROLE_FAILED")
        self.assertEqual(steps["register"]["result"]["outcome"], "recorded")
        self.assertNotIn("closer", steps["register"]["verdict"])
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")

    def test_without_a_named_registrar_nobody_closes_but_the_conductor(self):
        self.set_items({"W1": {}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("registrar"), 0)
        self.assertNotIn("close", self.steps(err))


class SandboxTests(ConductorCase):
    """The provider sandbox: a Claude Code role with Bash gets ``--settings`` with a ``sandbox`` block, a Codex route
    needs the sandbox to start; the probe is replaced, no bubblewrap is run."""
    UP = {"available": True, "reason": None, "checked": []}
    DOWN = {"available": False, "reason": "bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted", "checked": []}

    def stand_in(self, **extra) -> None:
        """An executor that looks like Claude Code with a shell (``--tools`` names Bash), run by the fake role."""
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        argv["executor"] += ["--tools", "Bash,Read,Edit", *extra.get("executor", [])]
        self.write_config(argv)

    def options(self, **instructions) -> Path:
        path = self.project.parent / "options.json"
        path.write_text(json.dumps({"instructions": instructions} if instructions else {}), encoding="utf-8")
        return path

    @staticmethod
    def extra(preview: dict, role: str) -> list:
        """The arguments the conductor adds to a role beside ``--safe-mode``."""
        return [arg for arg in preview["isolation_args"][role] if arg != "--safe-mode"]

    def preview(self, probe: dict, **instructions) -> dict:
        with mock.patch("orch.sandbox.probe", return_value=probe):
            code, out, err = self.conduct("run", "--plan", "T", "--batch", "--dry-run", "--scenario", "full",
                                          "--options", self.options(**instructions))
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_an_available_sandbox_adds_only_the_sandbox_block(self):
        self.stand_in()
        preview = self.preview(self.UP, sandbox_domains=["pypi.org"])
        args = self.extra(preview, "executor")
        self.assertEqual(args[0], "--settings")
        self.assertEqual(json.loads(args[1]), {"sandbox": {
            "enabled": True, "allowUnsandboxedCommands": False, "failIfUnavailable": True,
            "network": {"strictAllowlist": True, "allowedDomains": ["pypi.org"]}}})
        self.assertEqual(self.extra(preview, "reviewer"), [])  # no Bash in its stand-in argv
        self.assertEqual(preview["sandbox"], {"available": True, "reason": None})
        self.assertEqual(preview["network"]["executor"], {"declared": "none", "enforced": True, "by": "claude-sandbox"})

    def test_a_role_that_may_use_the_network_gets_no_allowlist(self):
        self.stand_in()
        with mock.patch.object(engine.Conductor, "declared_network", staticmethod(lambda role: "allowed")):
            args = self.extra(self.preview(self.UP), "executor")
        self.assertNotIn("network", json.loads(args[1])["sandbox"])

    def test_sandbox_off_adds_nothing(self):
        self.stand_in()
        preview = self.preview(self.UP, sandbox="off")
        self.assertEqual(self.extra(preview, "executor"), [])
        self.assertEqual(preview["network"]["executor"], {"declared": "none", "enforced": False, "by": None})
        self.assertTrue(any(w.startswith("executor: network is declared none") for w in preview["warnings"]))

    def test_an_unavailable_sandbox_is_reported_in_the_dry_run(self):
        self.stand_in()
        preview = self.preview(self.DOWN)
        self.assertEqual(preview["sandbox"], {"available": False, "reason": self.DOWN["reason"]})
        self.assertEqual(self.extra(preview, "executor"), [])
        self.assertFalse(preview["network"]["executor"]["enforced"])
        self.assertTrue(preview["warnings"])

    def test_require_names_the_stop_in_the_dry_run(self):
        self.stand_in()
        warnings = self.preview(self.DOWN, sandbox="require")["warnings"]
        self.assertTrue(any("SANDBOX_UNAVAILABLE" in warning for warning in warnings), warnings)

    def test_prefer_goes_on_and_says_so_once(self):
        self.stand_in()
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch("orch.sandbox.probe", return_value=self.DOWN):
            code, _, err = self.run_items("W1", extra=("--options", self.options()))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        partial = [line for line in self.lines(err) if line.get("reason_code") == "ISOLATION_PARTIAL"
                   and "sandbox unavailable" in line["message"]]
        self.assertEqual(len(partial), 1, err)

    def test_require_stops_before_any_work(self):
        self.stand_in()
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch("orch.sandbox.probe", return_value=self.DOWN):
            code, _, err = self.run_items("W1", extra=("--options", self.options(sandbox="require")))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "SANDBOX_UNAVAILABLE")), err)
        self.assertEqual(self.calls("executor"), 0)

    def test_require_without_a_shell_role_does_not_need_the_sandbox(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})  # no --tools: nothing to confine
        with mock.patch("orch.sandbox.probe", return_value=self.DOWN):
            code, _, err = self.run_items("W1", extra=("--options", self.options(sandbox="require")))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)

    def test_require_stops_when_the_claude_cli_cannot_take_settings(self):
        fake = self.project.parent / "bin" / "claude"
        fake.parent.mkdir()
        fake.write_text("#!/bin/sh\necho 'usage: claude -p --safe-mode'\n", encoding="utf-8")
        fake.chmod(0o755)
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        argv["executor"] = [str(fake), "--tools", "Bash,Read"]
        self.write_config(argv)
        with mock.patch("orch.sandbox.probe", return_value=self.UP):
            code, _, err = self.run_items("W1", extra=("--options", self.options(sandbox="require")))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "SANDBOX_UNAVAILABLE")), err)
        message = [line for line in self.lines(err) if line["event"] == "run.end"][0]["message"]
        self.assertIn("does not list --settings", message)
        self.assertEqual(self.calls("executor"), 0)

    def test_the_manifest_of_a_role_is_found_by_its_conductor_name(self):
        self.assertEqual(engine.Conductor.declared_network("context-scout"), "none")
        with mock.patch.object(engine, "ORCH_ROOT", self.project):  # no roles/ folder: the fallback
            self.assertEqual(engine.Conductor.declared_network("executor"), "none")
        manifest = self.project / "roles"
        manifest.mkdir()
        (manifest / "context-scout.json").write_text(json.dumps({"tools": {"network": "allowed"}}), encoding="utf-8")
        with mock.patch.object(engine, "ORCH_ROOT", self.project):
            self.assertEqual(engine.Conductor.declared_network("context-scout"), "allowed")

    def test_a_codex_route_is_unavailable_without_the_sandbox(self):
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        argv["executor"] += ["--sandbox", "workspace-write"]
        self.write_config(argv)
        options = self.project.parent / "codex.json"
        options.write_text(json.dumps({"stages": [{"role": "executor", "provider": "codex"}]}), encoding="utf-8")

        def preview(probe):
            with mock.patch("orch.sandbox.probe", return_value=probe):
                code, out, err = self.conduct("run", "--plan", "T", "--batch", "--dry-run", "--scenario", "full",
                                              "--options", options)
            self.assertEqual(code, 0, err)
            return json.loads(out)
        down = preview(self.DOWN)
        self.assertIs(down["available"]["executor"], False)
        self.assertTrue(down["unavailable"]["executor"].startswith("SANDBOX_UNAVAILABLE: bwrap"), down["unavailable"])
        self.assertEqual(down["network"]["executor"]["by"], None)
        up = preview(self.UP)
        self.assertIs(up["available"]["executor"], True)
        self.assertEqual(up["network"]["executor"], {"declared": "none", "enforced": True, "by": "codex-sandbox"})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch("orch.sandbox.probe", return_value=self.DOWN):
            code, _, err = self.run_items("W1", extra=("--options", options))
        self.assertEqual(self.calls("executor"), 0)
        self.assertEqual(self.outcome(err)[1], "SANDBOX_UNAVAILABLE", err)


def quota_failure(reset_in: int) -> dict:
    """Claude Code, usage limit: a rejected ``rate_limit_event`` (``resetsAt``) and a ``result`` with ``is_error``."""
    event = {"type": "rate_limit_event", "rate_limit_info": {
        "status": "rejected", "resetsAt": int(time.time()) + reset_in, "rateLimitType": "five_hour"}}
    return {"stream": [event], "is_error": True, "text": "You've hit your limit", "exit": 1}


def api_retry(category: str, status: int) -> dict:
    return {"type": "system", "subtype": "api_retry", "attempt": 1, "max_retries": 2, "retry_delay_ms": 500,
            "error_status": status, "error": category}


class ProviderErrorTests(ConductorCase):
    """A role that fails at the provider is decided by one ``retry.decide`` call (knowledge/provider-errors#flow): a repeat
    keeps the original prompt, a wait is a beacon, a fallback route is checked, a writing role continues, the stop has
    its own code."""

    FALLBACK = {"role": "executor", "provider": "codex", "model_class": "implementation"}

    def setUp(self):
        super().setUp()
        self.slept = []
        for name, value in (("sleep", self.slept.append), ("unit_random", lambda: 0.5)):
            patcher = mock.patch.object(engine, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def options(self, **layer) -> None:
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": layer}]}})

    def beacons(self, err: str, code: str) -> list:
        return [line for line in self.lines(err) if line.get("reason_code") == code]

    def gate_file(self) -> dict:
        return json.loads(gates.path().read_text(encoding="utf-8"))["gates"]

    def test_a_short_quota_wait_is_a_beacon_and_the_second_call_succeeds(self):
        self.script({"executor": [quota_failure(3), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 2)
        wait = self.beacons(err, "PROVIDER_WAIT")
        self.assertEqual(len(wait), 1, err)
        self.assertIn("quota", wait[0]["message"])
        self.assertTrue(1 <= sum(self.slept) <= 4, self.slept)
        self.assertNotIn("previous answer was rejected", self.prompt("executor", 2))
        self.assertEqual(self.prompt("executor", 2), self.prompt("executor", 1))
        self.assertEqual(self.gate_file()["claude-code"]["code"], "PROVIDER_QUOTA")  # the account quota is gated

    def test_a_far_reset_goes_to_the_declared_fallback_route(self):
        self.options(fallback_routes=[self.FALLBACK])
        self.script({"executor": [quota_failure(3600), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertEqual(self.slept, [])
        fallback = self.beacons(err, "ROUTE_FALLBACK")
        self.assertEqual(len(fallback), 1, err)
        self.assertIn("claude-code", fallback[0]["message"])
        self.assertIn("WAIT_TOO_LONG", fallback[0]["message"])
        routes = json.loads((self.run_dir(err) / "W1" / "routes.json").read_text())
        self.assertEqual(routes["executor"]["provider"], "codex")
        self.assertEqual(self.source()["items"]["W1"]["executed_by"]["provider"], "codex")

    def test_a_far_reset_without_a_fallback_stops_with_the_reset_time_and_gates_the_provider(self):
        self.script({"executor": [quota_failure(3600), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_QUOTA")), err)
        self.assertEqual(self.calls("executor"), 1)
        self.assertIn("resume after", err)
        self.assertIn("claude-code", self.gate_file())

    def test_a_gated_provider_goes_to_the_fallback_at_once_and_stops_without_one(self):
        gates.set_gate("claude-code", until=time.time() + 3600, code="PROVIDER_QUOTA", run_id="other", now=time.time())
        self.options(fallback_routes=[self.FALLBACK, dict(self.FALLBACK, role="triager")])
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual({line["role"] for line in self.beacons(err, "CAPACITY_GATED")}, {"executor", "triager"}, err)
        self.assertEqual(len(self.beacons(err, "ROUTE_FALLBACK")), 2, err)
        self.assertEqual(self.source()["items"]["W1"]["executed_by"]["provider"], "codex")
        self.set_items({"W2": {}})
        code, _, err = self.run_items("W2")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_QUOTA")), err)
        self.assertEqual(self.calls("executor"), 1)  # nothing was started on the gated provider

    def test_a_fallback_below_the_class_of_the_work_is_refused(self):
        self.options(fallback_routes=[dict(self.FALLBACK, model_class="economy")])
        self.script({"executor": [quota_failure(3600), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_QUOTA")), err)
        self.assertEqual(self.calls("executor"), 1)
        self.assertIn("ROUTE_UNDERSHOOT", err)
        self.assertEqual(self.beacons(err, "ROUTE_FALLBACK"), [])

    def test_a_missing_model_is_repeated_once_then_stops_as_model_unavailable(self):
        self.options(limits={"retries": 1})
        failed = {"is_error": True, "api_error_status": 404, "text": "model not found", "exit": 1}
        self.script({"executor": [failed, failed], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "MODEL_UNAVAILABLE")), err)
        self.assertEqual(self.calls("executor"), 2)

    def test_a_failed_authentication_stops_without_a_repeat(self):
        failed = {"stream": [api_retry("authentication_failed", 401)], "is_error": True, "text": "401", "exit": 1}
        self.script({"executor": [failed, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_AUTH")), err)
        self.assertEqual(self.calls("executor"), 1)

    def test_a_refusal_and_a_context_overflow_have_their_own_codes(self):
        self.options(stages=[{"role": "executor", "provider": "codex"}])
        failed = {"codex_failed": "stream error: reason: content_filter", "exit": 1}
        self.script({"executor": [failed, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_REFUSED")), err)
        self.assertEqual(self.calls("executor"), 1)
        self.set_items({"W2": {"options": [{"source": "item:W2", "options": {
            "stages": [{"role": "executor", "provider": "codex"}]}}]}})
        self.script({"executor": [{"codex_failed": "Codex ran out of room in the model's context window.", "exit": 1}]})
        code, _, err = self.run_items("W2")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_CONTEXT")), err)

    def test_a_codex_usage_limit_without_a_reset_stops_as_quota_and_an_error_event_is_no_failure(self):
        self.options(stages=[{"role": "executor", "provider": "codex"}])
        failed = {"codex_failed": "You\u2019ve hit your usage limit. Upgrade to Pro or try again later.", "exit": 1}
        self.script({"executor": [failed, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_QUOTA")), err)
        self.assertEqual(self.calls("executor"), 1)
        notice = {"codex": True, "stream": [{"type": "error", "message": "Reconnecting... 1/5"}], **executor_ok("W2")}
        self.set_items({"W2": {"options": [{"source": "item:W2", "options": {
            "stages": [{"role": "executor", "provider": "codex"}]}}]}})
        self.script({"executor": [notice], "reviewer": [GREEN]})
        code, _, err = self.run_items("W2")
        self.assertEqual(code, 0, err)

    def test_an_unknown_failure_is_repeated_once_with_the_original_prompt_then_fails(self):
        self.options(limits={"retries": 1})
        failed = {"exit": 1, "stderr": "something odd"}
        self.script({"executor": [failed, failed], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ROLE_FAILED")), err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertEqual(self.prompt("executor", 2), self.prompt("executor", 1))
        self.assertEqual(self.slept, [])  # the CLI did not repeat the request, so there is nothing to space out

    def test_after_the_cli_repeated_the_request_the_conductor_waits_before_it_repeats(self):
        failed = {"stream": [api_retry("server_error", 500), api_retry("server_error", 500)], "is_error": True,
                  "api_error_status": 500, "text": "overloaded", "exit": 1}
        self.script({"executor": [failed, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertEqual(sum(self.slept), 15)  # min(300, 30 * 2**0) * random (0.5)
        meta = self.state(err)["items"]["W1"]["steps"]["executor.1"]["result"]
        self.assertEqual(meta["api_retries"], 2)
        self.assertEqual(meta["decisions"][0]["action"], "retry")

    def test_a_writing_role_continues_over_the_changes_it_left(self):
        partial = {"write": {"out/W1.txt": "partial\n"}, "exit": 1, "stderr": "killed"}
        self.script({"executor": [partial, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        second = self.prompt("executor", 2)
        self.assertTrue(second.startswith(self.prompt("executor", 1)))
        self.assertIn("# The previous attempt failed and left changes", second)
        self.assertIn("out/W1.txt", second)
        self.assertNotIn("previous answer was rejected", second)
        self.assertEqual((self.project / "out/W1.txt").read_text(), "ok\n")

    def test_a_reconcile_does_not_repeat_past_the_retries_of_the_step(self):
        self.options(limits={"retries": 1})
        partial = {"write": {"out/W1.txt": "partial\n"}, "exit": 1}
        self.script({"executor": [partial], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ROLE_FAILED")), err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertTrue((self.project / "out/W1.txt").exists())  # the changes of the failed role stay

    def test_on_error_of_the_options_overrides_the_default_action(self):
        self.options(on_error={"unknown": {"action": "stop"}})
        self.script({"executor": [{"exit": 1}, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ROLE_FAILED")), err)
        self.assertEqual(self.calls("executor"), 1)

    def test_provider_wait_max_s_is_an_option(self):
        self.options(limits={"provider_wait_max_s": 1}, fallback_routes=[self.FALLBACK])
        self.script({"executor": [quota_failure(30), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(len(self.beacons(err, "ROUTE_FALLBACK")), 1, err)

    def test_a_role_that_starts_on_a_provider_gated_meanwhile_moves_or_stops(self):
        # the executor exhausts claude-code and moves to codex; the reviewer, chosen on claude-code at the start, must not
        # reopen the account that was just gated
        layer = {"reviewer": "claude-code/sonnet-5-5/high", "fallback_routes": [self.FALLBACK],
                 "limits": {"provider_wait_max_s": 60}}
        self.options(**layer)
        self.script({"executor": [quota_failure(3600), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_QUOTA")), err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (2, 0), err)

    def test_a_gate_in_force_routes_every_gated_role_at_the_start(self):
        gates.set_gate("claude-code", until=time.time() + 3600, code="PROVIDER_QUOTA", run_id="other", now=time.time())
        self.options(reviewer="claude-code/sonnet-5-5/high", fallback_routes=[
            self.FALLBACK, dict(self.FALLBACK, role="reviewer"), dict(self.FALLBACK, role="triager")])
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        gated = {line["role"] for line in self.beacons(err, "CAPACITY_GATED")}
        self.assertTrue({"executor", "reviewer"} <= gated, err)

    def test_a_role_waits_for_a_gate_that_ends_soon_instead_of_stopping(self):
        self.options(reviewer="claude-code/sonnet-5-5/high")
        self.script({"executor": [quota_failure(3), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("reviewer"), 1)
        self.assertGreaterEqual(len(self.beacons(err, "PROVIDER_WAIT")), 2, err)  # the executor's wait and the reviewer's

    def test_a_fallback_taken_by_a_role_survives_a_resume(self):
        self.options(stages=[{"role": "executor", "provider": "codex"}], limits={"retries": 1},
                     fallback_routes=[{"role": "executor", "provider": "claude-code", "model_class": "implementation"}])
        auth = {"stream": [api_retry("authentication_failed", 401)], "is_error": True, "text": "401", "exit": 1}
        self.script({"executor": [{"codex_failed": "You\u2019ve hit your usage limit. Try later.", "exit": 1}, auth,
                                  executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_AUTH")), err)
        run_id = self.run_dir(err).name
        code, _, err = self.conduct("resume", "--run", run_id, "--json-lines")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        routes = json.loads((engine.runs_root(self.project) / run_id / "W1" / "routes.json").read_text())
        self.assertEqual(routes["executor"]["provider"], "claude-code")
        self.assertEqual(self.source()["items"]["W1"]["executed_by"]["provider"], "claude-code")

    def test_a_fallback_must_pass_the_sandbox_rule_the_preflight_applies(self):
        eng = engine.Conductor.__new__(engine.Conductor)
        eng.settings = None  # no aicore configuration: every provider is routable
        item = engine.Item(ref="W1", orch_run="-", state={}, directory=Path(), claim={},
                           options={"instructions": {"sandbox": "require"}})
        route = {"role": "executor", "provider": "claude-code", "model_class": "implementation", "transport": "jsonl",
                 "argv": ["claude", "-p", "--tools", "Bash,Read"]}
        with mock.patch.object(engine.process, "available", return_value=True), \
                mock.patch.object(engine.sandbox, "probe", return_value={"available": True, "reason": ""}), \
                mock.patch.object(engine.Conductor, "_knows", return_value=False):
            problem = eng._admit(item, "executor", route)
        self.assertTrue(problem and problem.startswith("SANDBOX_UNAVAILABLE"), problem)

    def test_a_dry_run_marks_a_gated_provider_unavailable(self):
        gates.set_gate("claude-code", until=time.time() + 3600, code="PROVIDER_QUOTA", run_id="other", now=time.time())
        options = self.project.parent / "gated.json"
        options.write_text(json.dumps({"fallback_routes": [self.FALLBACK, dict(self.FALLBACK, role="triager")]}),
                           encoding="utf-8")
        code, out, err = self.conduct("run", "--plan", "T", "--batch", "--dry-run", "--scenario", "full", "--options", options)
        self.assertEqual(code, 0, err)
        preview = json.loads(out)
        self.assertEqual(preview["routes"]["executor"]["provider"], "codex")
        self.assertIs(preview["available"]["context-scout"], False)
        self.assertTrue(preview["unavailable"]["context-scout"].startswith("PROVIDER_QUOTA:"), preview["unavailable"])

    def test_a_provider_wait_is_the_beacon_status_shows(self):
        lines = [{"event": "run.start", "ts": "t"}, {"event": "stage.start", "item": "W1", "stage": "executor.1",
                                                      "role": "executor", "ts": "t"},
                 {"event": "info", "item": "W1", "reason_code": "PROVIDER_WAIT", "message": "waiting 800 s", "ts": "t"}]
        self.assertEqual(progress.summarize(lines)["beacon"]["reason_code"], "PROVIDER_WAIT")

    def test_a_wait_is_cut_short_by_a_cancel(self):
        eng = engine.Conductor.__new__(engine.Conductor)
        cancel = mock.Mock()
        cancel.is_set.side_effect = [False, False, True]
        with self.assertRaises(engine.Stop) as raised:
            eng._pause(30, cancel)
        self.assertEqual(raised.exception.code, "REVIEW_CANCELLED")
        self.assertEqual(len(self.slept), 2)  # looked at every second


class ReviewerFallbackTests(ConductorCase):
    """The reviewer of a run is grok by default; a review is too dear to lose when grok cannot start, is gated or fails, so
    ``fallback_routes`` has a default for it: claude-code, class frontier, effort high (a layer replaces it, ``[]`` ends it)."""

    def real_reviewer(self) -> None:
        """No command override for the reviewer: its route is the launch catalog's own (a grok command line)."""
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES if role != "reviewer"})

    def without_grok(self):
        return mock.patch.object(engine.process, "available", lambda argv: "grok" not in argv)

    def dry_run(self, layer=None) -> dict:
        args = ["run", "--plan", "T", "--batch", "--dry-run", "--scenario", "full"]
        if layer is not None:
            options = self.project.parent / "layer.json"
            options.write_text(json.dumps(layer), encoding="utf-8")
            args += ["--options", options]
        code, out, err = self.conduct(*args)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_the_default_is_claude_code_frontier_high_for_the_reviewer(self):
        preview = self.dry_run()
        self.assertEqual(preview["fallback_routes"], [{"role": "reviewer", "provider": "claude-code",
                                                       "model_class": "frontier", "effort": "high"}])
        self.assertEqual(preview["reviewer"], {"selector": "grok/grok-4.7/high", "source": "config:orch.conductor"})
        self.assertEqual((preview["gates"], preview["route_notes"]), ([], []))

    def test_a_reviewer_layer_is_named_in_the_preview(self):
        preview = self.dry_run({"reviewer": "codex/gpt-6-sol/high"})
        self.assertEqual(preview["reviewer"], {"selector": "codex/gpt-6-sol/high", "source": "invocation:--options"})

    def test_a_dry_run_without_grok_shows_the_fallback_reviewer(self):
        self.real_reviewer()
        with self.without_grok():
            preview = self.dry_run()
        self.assertEqual(preview["routes"]["reviewer"]["provider"], "claude-code")
        self.assertEqual((preview["routes"]["reviewer"]["model_class"], preview["routes"]["reviewer"]["effort"]),
                         ("frontier", "high"))
        self.assertIs(preview["available"]["reviewer"], True)
        note = preview["route_notes"][0]
        self.assertEqual((note["role"], note["reason_code"]), ("reviewer", "PROVIDER_UNAVAILABLE"))
        self.assertTrue(note["from"].startswith("grok/"), note)

    def test_an_empty_layer_ends_the_default_fallback(self):
        self.real_reviewer()
        with self.without_grok():
            preview = self.dry_run({"fallback_routes": []})
        self.assertEqual(preview["routes"]["reviewer"]["provider"], "grok")
        self.assertIs(preview["available"]["reviewer"], False)
        self.assertEqual(preview["route_notes"], [])

    def test_a_dry_run_lists_the_gates_in_force(self):
        gates.set_gate("grok", until=time.time() + 3600, code="PROVIDER_QUOTA", run_id="other", now=time.time())
        preview = self.dry_run()
        self.assertEqual([row["provider"] for row in preview["gates"]], ["grok"])
        self.assertEqual(preview["routes"]["reviewer"]["provider"], "claude-code")
        self.assertEqual(preview["route_notes"][0]["reason_code"], "CAPACITY_GATED")

    def test_a_gated_grok_reviews_on_claude_code(self):
        gates.set_gate("grok", until=time.time() + 3600, code="PROVIDER_QUOTA", run_id="other", now=time.time())
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("reviewer"), 1)
        fallback = [line for line in self.lines(err) if line.get("reason_code") == "ROUTE_FALLBACK"]
        self.assertEqual([line["role"] for line in fallback], ["reviewer"], err)
        self.assertIn("claude-code", fallback[0]["message"])
        routes = json.loads((self.run_dir(err) / "W1" / "routes.json").read_text())
        self.assertEqual(routes["reviewer"]["provider"], "claude-code")

    def test_a_failing_grok_reviewer_moves_to_claude_code_when_the_policy_says_so(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"on_error": {"unknown": {"action": "fallback_route"}}}}]}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [{"exit": 1}, GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("reviewer"), 2)
        fallback = [line for line in self.lines(err) if line.get("reason_code") == "ROUTE_FALLBACK"]
        self.assertEqual([line["role"] for line in fallback], ["reviewer"], err)
        routes = json.loads((self.run_dir(err) / "W1" / "routes.json").read_text())
        self.assertEqual(routes["reviewer"]["provider"], "claude-code")


class ProviderAvailabilityTests(ConductorCase):
    """``aicore.providers.available.<id>.enabled`` decides whether a role may be routed to a provider, independent of
    ``providers.selection``: a disabled provider is unavailable in the dry run, goes to a fallback route and stops the
    preflight when there is none."""

    CODEX_REVIEWER = {"reviewer": "codex/gpt-6-sol/high"}
    real_reviewer = ReviewerFallbackTests.real_reviewer
    dry_run = ReviewerFallbackTests.dry_run

    def disable(self, provider="codex", file=None) -> None:
        text = f"[aicore.providers.available.{provider}]\nenabled = false\n"
        if file is None:
            self.write_config(extra=text)
        else:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("schema_version = 1\n" + text, encoding="utf-8")

    def test_a_provider_off_on_the_machine_is_unavailable_with_its_layer(self):
        self.real_reviewer()
        self.disable()
        preview = self.dry_run(dict(self.CODEX_REVIEWER, fallback_routes=[]))
        self.assertIs(preview["available"]["reviewer"], False)
        self.assertEqual(preview["unavailable"]["reviewer"],
                         "PROVIDER_DISABLED: aicore.providers.available.codex.enabled = false (machine)")

    def test_a_disabled_provider_goes_to_the_fallback_route(self):
        self.real_reviewer()
        self.disable()
        preview = self.dry_run(self.CODEX_REVIEWER)
        self.assertEqual(preview["routes"]["reviewer"]["provider"], "claude-code")
        self.assertIs(preview["available"]["reviewer"], True)
        note = preview["route_notes"][0]
        self.assertEqual((note["role"], note["reason_code"]), ("reviewer", "PROVIDER_DISABLED"))
        self.assertTrue(note["from"].startswith("codex/"), note)

    def test_a_disabled_provider_without_a_fallback_stops_the_preflight(self):
        self.real_reviewer()
        self.disable()
        options = self.project.parent / "layer.json"
        options.write_text(json.dumps(dict(self.CODEX_REVIEWER, fallback_routes=[])), encoding="utf-8")
        code, out, err = self.run_items("W1", extra=("--options", options))
        self.assertEqual(self.outcome(err)[1], "PROVIDER_UNAVAILABLE", err)
        self.assertIn("PROVIDER_DISABLED", err)
        self.assertEqual(self.calls("executor"), 0)

    def test_the_project_cannot_enable_what_the_machine_disabled_and_selection_does_not_route(self):
        self.disable(file=self.project / ".swissknifeman" / "config.toml")
        code, out, err = self.conduct("run", "--plan", "T", "--batch", "--dry-run", "--scenario", "full")
        self.assertEqual(code, 1, out)
        self.assertIn("CONFIG_LAYER_FORBIDDEN", err)
        (self.project / ".swissknifeman" / "config.toml").write_text(
            "schema_version = 1\n[aicore.providers.selection.claude-code]\nenabled = false\n", encoding="utf-8")
        preview = self.dry_run()
        self.assertTrue(all(preview["available"].values()), preview["unavailable"])


class ProjectContextTests(ConductorCase):
    """The project is ``--project DIR``, else ``SKM_PROJECT_ROOT``, else the nearest ``.git`` or ``.swissknifeman``; the run
    records how it was found and where it was started."""

    def elsewhere(self) -> Path:
        other = self.project.parent / "elsewhere"
        other.mkdir()
        os.chdir(other)
        return other

    def setUp(self):
        super().setUp()
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})

    def run_doc(self, err: str) -> dict:
        return json.loads((self.run_dir(err) / engine.RUN_FILE).read_text(encoding="utf-8"))

    def test_without_a_project_the_run_is_refused_with_the_flag_named(self):
        other = self.elsewhere()
        code, out, err = self.conduct("run", "--plan", "T", "--items", "W1", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_CONTEXT_REQUIRED", err)
        self.assertIn("--project DIR", err)
        self.assertIn(str(other), err)

    def test_the_flag_names_the_project_from_anywhere_and_is_recorded(self):
        other = self.elsewhere()
        code, out, err = self.conduct("--project", self.project, "run", "--plan", "T", "--items", "W1", "--json-lines")
        self.assertEqual(self.outcome(err)[0], "finished", err)
        doc = self.run_doc(err)
        self.assertEqual((doc["project_resolution"], doc["working_directory"]), ("flag", str(other)))

    def test_the_environment_names_the_project(self):
        self.elsewhere()
        with mock.patch.dict(os.environ, {"SKM_PROJECT_ROOT": str(self.project)}):
            code, out, err = self.run_items("W1")
        self.assertEqual(self.run_doc(err)["project_resolution"], "environment", err)

    def test_a_marker_finds_the_project_from_a_subfolder(self):
        sub = self.project / "sub"
        sub.mkdir()
        os.chdir(sub)
        code, out, err = self.run_items("W1")
        doc = self.run_doc(err)
        self.assertEqual((doc["project_resolution"], doc["working_directory"]), ("git", str(sub)))

    def test_a_project_that_is_not_a_git_repository_is_refused(self):
        plain = self.project.parent / "plain"
        plain.mkdir()
        code, out, err = self.conduct("--project", plain, "status")
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_NOT_GIT", err)

    def test_a_missing_project_folder_is_no_project(self):
        code, out, err = self.conduct("--project", self.project.parent / "missing", "status")
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_CONTEXT_REQUIRED", err)


class PreviewAndStatusTests(ConductorCase):
    def test_dry_run_writes_nothing_and_shows_routes(self):
        code, out, err = self.conduct("run", "--plan", "T", "--batch", "--dry-run", "--scenario", "full")
        self.assertEqual(code, 0, err)
        preview = json.loads(out)
        self.assertEqual(preview["routes"]["reviewer"]["provider"], "grok")
        self.assertEqual(preview["routes"]["triager"]["model_class"], "implementation")
        self.assertFalse(engine.runs_root(self.project).exists())
        self.assertEqual(self.source()["calls"], [])

    def test_dry_run_marks_an_acp_route_unavailable_with_the_reason(self):
        options = self.project.parent / "grok-executor.json"
        options.write_text(json.dumps({"stages": [{"role": "executor", "provider": "grok"}]}), encoding="utf-8")
        code, out, err = self.conduct("run", "--plan", "T", "--batch", "--dry-run", "--scenario", "full",
                                      "--options", options)
        self.assertEqual(code, 0, err)
        preview = json.loads(out)
        self.assertEqual(preview["routes"]["executor"]["transport"], "acp")
        self.assertIs(preview["available"]["executor"], False)
        self.assertTrue(preview["unavailable"]["executor"].startswith("TRANSPORT_UNSUPPORTED:"), preview["unavailable"])
        self.assertTrue(preview["available"]["reviewer"])  # grok reviewer is jsonl under ro-run
        self.assertNotIn("reviewer", preview["unavailable"])

    def test_dry_run_names_a_missing_binary(self):
        missing = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        missing["reviewer"] = [str(self.project / "no-such-grok")]
        self.write_config(missing)
        code, out, err = self.conduct("run", "--plan", "T", "--batch", "--dry-run", "--scenario", "full")
        self.assertEqual(code, 0, err)
        preview = json.loads(out)
        self.assertIs(preview["available"]["reviewer"], False)
        self.assertTrue(preview["unavailable"]["reviewer"].startswith("PROVIDER_UNAVAILABLE: "), preview["unavailable"])

    def test_status_without_runs_is_refused(self):
        code, _, err = self.conduct("status")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("RUN_UNKNOWN"), err)

    def test_text_progress_is_one_line_per_event(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.conduct("run", "--plan", "T", "--items", "W1")
        self.assertEqual(code, 0, err)
        lines = err.strip().splitlines()
        self.assertTrue(any("executor.1  executor claude-code/" in line and "  start" in line for line in lines), err)
        self.assertTrue(any("review.1  reviewer grok/grok-4.7/high  end  GREEN 0 finding(s)" in line
                            for line in lines), err)
        code, out, _ = self.conduct("status")
        self.assertEqual(code, 0)
        self.assertIn("W1: done", out)


if __name__ == "__main__":
    unittest.main()
