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
import unittest
from unittest import mock

from orch.conductor import cli, engine, progress

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

    def test_the_executor_is_told_to_run_only_the_tests_of_its_change_unless_asked_otherwise(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        self.assertEqual(self.run_items("W1")[0], 0)
        self.assertIn("This replaces the instruction above to run every acceptance check yourself", self.prompt("executor", 1))
        self.assertIn("The conductor runs these commands itself", self.prompt("executor", 1))
        self.assertIn("`test -f out/W1.txt`", self.prompt("executor", 1))
        self.set_items({"W2": {"options": [{"source": "item:W2", "options": {"checks": {"executor_runs_checks": True}}}]}})
        self.script({"executor": [executor_ok("W2")], "reviewer": [GREEN]})
        self.assertEqual(self.run_items("W2")[0], 0)
        self.assertNotIn("This replaces the instruction above", self.prompt("executor", 2))

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

    def test_red_checks_drop_the_overlapping_review_and_repeat_it_after_the_correction(self):
        self.overlapping()
        self.script({"executor": [{"result": report("W1")}, executor_ok("W1")], "reviewer": [GREEN, GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (2, 2))
        self.assertNotIn("at the same time", self.prompt("reviewer", 2))
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

    def test_a_stop_and_a_resume_repeat_no_closed_step(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        missing = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        missing["reviewer"] = [str(self.project / "no-such-grok")]
        self.write_config(missing)
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_UNAVAILABLE")), err)
        self.assertEqual(self.calls("executor"), 1)
        run_id = self.run_dir(err).name
        status = self.conduct("status", "--run", run_id, "--json")
        self.assertEqual(json.loads(status[1])["status"], "stopped")
        self.write_config()
        code, _, err = self.conduct("resume", "--run", run_id, "--json-lines")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual((self.calls("executor"), self.calls("context-scout"), self.calls("reviewer")), (1, 1, 1))
        skipped = [line["stage"] for line in self.lines(err) if line["event"] == "stage.skip"]
        self.assertEqual(skipped, ["brief", "prepare", "scout", "executor.1", "checks.1"])
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

    def test_an_exhausted_budget_stops(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"limits": {"tokens_max": 50}}}]}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "BUDGET_EXHAUSTED")), err)

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


class PreviewAndStatusTests(ConductorCase):
    def test_dry_run_writes_nothing_and_shows_routes(self):
        code, out, err = self.conduct("run", "--plan", "T", "--batch", "--dry-run", "--scenario", "full")
        self.assertEqual(code, 0, err)
        preview = json.loads(out)
        self.assertEqual(preview["routes"]["reviewer"]["provider"], "grok")
        self.assertEqual(preview["routes"]["triager"]["model_class"], "implementation")
        self.assertFalse(engine.runs_root(self.project).exists())
        self.assertEqual(self.source()["calls"], [])

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
