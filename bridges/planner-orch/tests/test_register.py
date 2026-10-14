"""plan.py bridge planner-orch register / register-review: report → plan.py calls, receipt, idempotency, refusals.

``plan_calls`` is tested as a pure function; the CLI runs on a copy of planner's demo plan through the dispatcher.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import unittest

import bridge_fixture
import register
import register_review

REGISTRAR = "anthropic/claude-opus-5-5/high"
WORKER = "anthropic/claude-opus-5-5/xhigh"
UNIT_WORKER = "claude-code/claude-sonnet-5-5/high"
REPORT = {
    "summary": "Implemented the piece",
    "changed_paths": ["lib/a.py", "lib/b.py"],
    "checks_run": [{"id": "V1", "cmd": "python3 -m unittest", "exit": 0}],
    "evidence": [],
    "open_issues": [],
}
ALL_ISSUES = [
    {"text": "polish names later", "kind": "pending"},
    {"text": "used stdlib json instead of the helper", "kind": "deviation", "impact": "api", "next": "review"},
    {"text": "fixture repo was missing", "kind": "blocker"},
    {"text": "slow suite", "kind": "difficulty"},
    {"text": "UTC timestamps everywhere", "kind": "assumption"},
    {"text": "found an unrelated typo", "kind": "note"},
]
FINDINGS = {
    "verdict": "ATTENTION",
    "reviewer": {"route": "codex/gpt-5.5/high", "session": "s-42"},
    "findings": [{"severity": "major", "confidence": "high", "location": "lib/a.py:3",
                  "failure_scenario": "empty input crashes", "basis": "read the code"}],
    "date": "2026-10-06",
}


def args(ref="P2.1", status="done", **extra) -> argparse.Namespace:
    values = {"plan": "PLAN3", "ref": ref, "status": status, "actor": REGISTRAR, "executed_by": None,
              "attempt_id": None, "evidence": {}, "plans_root": None}
    values.update(extra)
    return argparse.Namespace(**values)


def report(**changes) -> dict:
    return {**json.loads(json.dumps(REPORT)), **changes}


def flag_values(argv: list[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, value in enumerate(argv) if value == flag]


class PlanCallsTests(unittest.TestCase):
    def refused(self, code, doc, **kw):
        with self.assertRaises(register.Refusal) as caught:
            register.plan_calls(doc, args(**kw))
        self.assertEqual(caught.exception.code, code)
        return str(caught.exception)

    def test_item_done_is_one_finish_with_notes_checks_and_identity(self):
        calls = register.plan_calls(report(), args(executed_by=WORKER, attempt_id="run-1"))
        self.assertEqual(len(calls), 1)
        finish = calls[0]
        self.assertEqual(finish[:5], ["finish", "PLAN3", "P2.1", "--status", "done"])
        self.assertEqual(flag_values(finish, "--notes"), ["Implemented the piece\nChanged: lib/a.py, lib/b.py"])
        self.assertEqual(flag_values(finish, "--check"), ["V1=0"])
        self.assertEqual(flag_values(finish, "--actor"), [REGISTRAR])
        self.assertEqual(flag_values(finish, "--executed-by"), [WORKER])
        self.assertEqual(flag_values(finish, "--attempt-id"), ["run-1"])

    def test_evidence_replaces_the_check_and_other_files_are_named_in_notes(self):
        doc = report(checks_run=[{"id": "V1", "cmd": "make", "exit": 0},
                                 {"id": "V2", "procedure": "look at it", "verdict": "fail"}],
                     evidence=["@plan/ev/V1.json", "logs/run.txt"])
        finish = register.plan_calls(doc, args(evidence={"V1": "@plan/ev/V1.json"}))[-1]
        self.assertEqual(flag_values(finish, "--check"), ["V2=1"])
        self.assertEqual(flag_values(finish, "--evidence"), ["V1=@plan/ev/V1.json"])
        self.assertTrue(flag_values(finish, "--notes")[0].endswith("\nEvidence: logs/run.txt"))

    def test_under_the_evidence_gate_claims_never_become_checks(self):
        doc = report(checks_run=[{"id": "V1", "cmd": "make", "exit": 0},
                                 {"id": "V2", "procedure": "look at it", "verdict": "pass"}])
        finish = register.plan_calls(doc, args(evidence={"V1": "@plan/ev/V1.json"}, gate="evidence"))[-1]
        self.assertEqual(flag_values(finish, "--check"), [])
        self.assertEqual(flag_values(finish, "--evidence"), ["V1=@plan/ev/V1.json"])
        without = register.plan_calls(doc, args(evidence={"V1": "@plan/ev/V1.json"}, gate=None))[-1]
        self.assertEqual(flag_values(without, "--check"), ["V2=0"])  # no gate: the previous behaviour

    def test_every_issue_kind_maps_to_log_then_finish(self):
        calls = register.plan_calls(report(open_issues=ALL_ISSUES),
                                    args(status="done_with_deviations", attempt_id="run-1"))
        logs, finish = calls[:-1], calls[-1]
        self.assertTrue(all(argv[0] == "log" for argv in logs))
        self.assertEqual(finish[0], "finish")
        self.assertEqual([flag_values(argv, "--type")[0] for argv in logs],
                         ["deviation", "blocker", "difficulty", "assumption", "note"])
        self.assertEqual(flag_values(logs[0], "--impact"), ["api"])
        self.assertEqual(flag_values(logs[0], "--next"), ["review"])
        self.assertEqual(flag_values(finish, "--deviation"), ["used stdlib json instead of the helper"])
        self.assertEqual(flag_values(finish, "--pending"), ["polish names later"])
        self.assertNotIn("--attempt-id", logs[0])

    def test_deviation_fields_reach_the_log_call_as_data(self):
        deviation = {"text": "edited docs/x.md", "kind": "deviation", "impact": "commit", "class": "write_set",
                     "outcome": "accepted", "severity": "low", "auto_fixable": False, "evidence": ["docs/x.md", "V1"]}
        calls = register.plan_calls(report(open_issues=[deviation, ALL_ISSUES[4]]),
                                    args(status="done_with_deviations", attempt_id="a"))
        data = json.loads(flag_values(calls[0], "--data")[0])
        self.assertEqual(data, {"class": "write_set", "outcome": "accepted", "severity": "low",
                                "auto_fixable": False, "evidence": ["docs/x.md", "V1"]})
        self.assertNotIn("--data", calls[1])  # an issue without the fields carries no data
        unit = register.plan_calls(report(open_issues=[dict(deviation, kind="difficulty")]),
                                   args(ref="P2.1/U1", status=None, attempt_id="u"))
        self.assertEqual(json.loads(flag_values(unit[0], "--data")[0])["class"], "write_set")

    def test_follow_up_and_owner_decision_deviations_leave_pending_entries_and_no_items(self):
        issues = [dict(ALL_ISSUES[0]),
                  {"text": "widen the write set", "kind": "deviation", "impact": "later items", "class": "write_set",
                   "outcome": "follow_up"},
                  {"text": "pick the wording", "kind": "deviation", "impact": "docs", "class": "docs",
                   "outcome": "owner_decision"},
                  {"text": "no class given", "kind": "deviation", "impact": "x", "outcome": "follow_up"},
                  {"text": "just recorded", "kind": "deviation", "impact": "x", "class": "docs", "outcome": "accepted"},
                  {"text": "a note", "kind": "note", "outcome": "follow_up"}]
        calls = register.plan_calls(report(open_issues=issues), args(status="done_with_deviations", attempt_id="a"))
        finish = calls[-1]
        self.assertEqual(flag_values(finish, "--pending"),
                         ["polish names later", "follow_up(write_set): widen the write set",
                          "owner_decision(docs): pick the wording", "follow_up(other): no class given"])
        self.assertEqual(flag_values(finish, "--deviation"), ["widen the write set", "pick the wording", "no class given",
                                                              "just recorded"])
        self.assertTrue(all(argv[0] in ("log", "finish") for argv in calls))  # no add-item, no other verb
        data = [json.loads(flag_values(argv, "--data")[0]) for argv in calls[:-1] if "--data" in argv]
        self.assertEqual([d["outcome"] for d in data], ["follow_up", "owner_decision", "follow_up", "accepted", "follow_up"])

    def test_deviation_fields_are_checked(self):
        for name, change in {"class": {"class": "typo"}, "severity": {"severity": "urgent"},
                             "outcome": {"outcome": "later"}, "auto-fixable": {"auto_fixable": "yes"},
                             "evidence-string": {"evidence": "a.py:1"}, "evidence-empty": {"evidence": []},
                             "evidence-blank": {"evidence": [""]}}.items():
            with self.subTest(name):
                issue = dict(ALL_ISSUES[1], **change)
                self.refused("REGISTER_REPORT_INVALID", report(open_issues=[issue]), attempt_id="a",
                             status="done_with_deviations")

    def test_escalation_goes_with_blocked(self):
        issues = [{"text": "owner must pick a license", "kind": "escalation"},
                  {"text": "and a name", "kind": "escalation"}]
        finish = register.plan_calls(report(open_issues=issues), args(status="blocked", attempt_id="a"))[-1]
        self.assertEqual(flag_values(finish, "--escalation"), ["owner must pick a license; and a name"])

    def test_unit_return_carries_changed_paths_and_names_checks_and_evidence(self):
        doc = report(evidence=["@plan/ev/V1.json"], open_issues=[{"text": "rename later", "kind": "pending"}])
        calls = register.plan_calls(doc, args(ref="P2.1/U1", status=None, attempt_id="w1",
                                              evidence={"V1": "@plan/ev/V1.json"}))
        log, ret = calls
        self.assertEqual(flag_values(log, "--type") + flag_values(log, "--summary"), ["note", "pending: rename later"])
        self.assertEqual(ret[:5], ["unit", "PLAN3", "P2.1", "U1", "return"])
        self.assertEqual(flag_values(ret, "--changed"), ["lib/a.py", "lib/b.py"])
        self.assertEqual(flag_values(ret, "--notes"),
                         ["Implemented the piece\nChecks: V1=0\nEvidence: V1=@plan/ev/V1.json"])
        self.assertNotIn("--evidence", ret)
        self.assertEqual(flag_values(ret, "--attempt-id"), ["w1"])

    def test_plans_root_reaches_every_call(self):
        calls = register.plan_calls(report(open_issues=ALL_ISSUES[1:2]),
                                    args(status="done_with_deviations", attempt_id="a", plans_root=Path("/p")))
        self.assertTrue(all(flag_values(argv, "--plans-root") == ["/p"] for argv in calls))

    def test_unclassified_issues_are_refused(self):
        for issue in ("plain string", {"text": "no kind"}, {"text": "odd", "kind": "todo"}, {"kind": "note"}):
            with self.subTest(issue=issue):
                self.refused("REGISTER_UNCLASSIFIED", report(open_issues=[issue]), attempt_id="a")

    def test_invalid_reports_are_refused(self):
        cases = {
            "not-object": [],
            "no-summary": report(summary=" "),
            "unknown-field": report(extra=1),
            "bad-check-id": report(checks_run=[{"id": "1", "cmd": "x", "exit": 0}]),
            "bool-exit": report(checks_run=[{"id": "V1", "cmd": "x", "exit": True}]),
            "mixed-check": report(checks_run=[{"id": "V1", "cmd": "x", "verdict": "pass"}]),
            "repeated-check": report(checks_run=[{"id": "V1", "cmd": "x", "exit": 0}] * 2),
            "bad-paths": report(changed_paths=[""]),
            "issue-extra": report(open_issues=[{"text": "t", "kind": "note", "why": "x"}]),
        }
        for name, doc in cases.items():
            with self.subTest(name):
                self.refused("REGISTER_REPORT_INVALID", doc, attempt_id="a")
        self.refused("REGISTER_REPORT_INVALID", report(), ref="P2")

    def test_status_must_match_the_issues(self):
        deviation, escalation = ALL_ISSUES[1], {"text": "owner decides", "kind": "escalation"}
        cases = [
            (report(open_issues=[deviation]), {"status": "done"}),
            (report(), {"status": "done_with_deviations"}),
            (report(open_issues=[escalation]), {"status": "done"}),
            (report(), {"status": "blocked"}),
            (report(), {"status": None}),
            (report(), {"ref": "P2.1/U1", "status": "blocked"}),
            (report(open_issues=[escalation]), {"ref": "P2.1/U1", "status": None}),
        ]
        for doc, kw in cases:
            with self.subTest(kw=kw, issues=doc["open_issues"]):
                self.refused("REGISTER_STATUS_MISMATCH", doc, attempt_id="a", **kw)

    def test_issues_need_an_attempt_id(self):
        message = self.refused("REGISTER_ATTEMPT_REQUIRED", report(open_issues=ALL_ISSUES[3:4]))
        self.assertIn("--attempt-id", message)


class CliCase(unittest.TestCase):
    """A fresh copy of the demo plan per test; P2.1 is in progress, P2.2 is not started."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.plan = str(bridge_fixture.demo_plan(self.dir))

    def plan_py(self, *argv):
        return bridge_fixture.plan_py(self.dir, *argv)

    def write(self, name, doc) -> str:
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def register(self, doc, ref="P2.1", *extra):
        done = self.plan_py("bridge", "planner-orch", "register", self.plan, ref, "--report", self.write("report.json", doc),
                            "--actor", REGISTRAR, *extra)
        return done.returncode, (json.loads(done.stdout) if done.stdout.strip() else None), done.stderr

    def get(self, ref):
        done = self.plan_py("--output", "json", "get", self.plan, ref)
        self.assertEqual(done.returncode, 0, done.stdout)
        return json.loads(done.stdout)["data"]["doc"]

    def events(self, item, *types):
        done = self.plan_py("--output", "json", "events", self.plan, "--item", item, "--type", ",".join(types))
        return json.loads(done.stdout)["data"]

    def journal(self) -> str:
        return (Path(self.plan) / "log.jsonl").read_text(encoding="utf-8")


class RegisterCliTests(CliCase):
    def test_done_with_deviations_records_every_field_and_returns_a_receipt(self):
        code, receipt, err = self.register(report(open_issues=ALL_ISSUES), "P2.1", "--status", "done_with_deviations",
                                           "--executed-by", WORKER, "--attempt-id", "run-1")
        self.assertEqual(code, 0, err)
        self.assertEqual(set(receipt), {"plan", "ref", "calls", "next"})
        self.assertEqual([c["result"] for c in receipt["calls"]], ["recorded"] * 6)
        self.assertTrue(receipt["next"])
        result = self.get("P2.1")["result"]
        self.assertEqual(result["notes"], "Implemented the piece\nChanged: lib/a.py, lib/b.py")
        self.assertEqual(result["deviations"], ["used stdlib json instead of the helper"])
        self.assertEqual(result["pending"], ["polish names later"])
        self.assertEqual(result["attempt_id"], "run-1")
        logged = {(e["type"], e["summary"]) for e in self.events("P2.1", *register.LOG_KINDS)}
        self.assertTrue({(i["kind"], i["text"]) for i in ALL_ISSUES if i["kind"] in register.LOG_KINDS} <= logged)

    def test_deviation_fields_land_in_the_journal_data(self):
        deviation = dict(ALL_ISSUES[1], **{"class": "write_set", "outcome": "follow_up", "evidence": ["V1"]})
        code, _, err = self.register(report(open_issues=[deviation]), "P2.1", "--status", "done_with_deviations",
                                     "--attempt-id", "run-d")
        self.assertEqual(code, 0, err)
        [event] = [e for e in self.events("P2.1", "deviation") if e["summary"] == deviation["text"]]
        self.assertEqual(event["data"], {"class": "write_set", "outcome": "follow_up", "evidence": ["V1"]})

    def test_a_follow_up_deviation_lands_in_result_pending_and_followups_lists_it(self):
        deviation = dict(ALL_ISSUES[1], **{"class": "write_set", "outcome": "follow_up"})
        code, _, err = self.register(report(open_issues=[deviation]), "P2.1", "--status", "done_with_deviations",
                                     "--attempt-id", "run-f")
        self.assertEqual(code, 0, err)
        entry = f"follow_up(write_set): {deviation['text']}"
        self.assertEqual(self.get("P2.1")["result"]["pending"], [entry])
        done = self.plan_py("--output", "json", "followups", self.plan, "--open")
        self.assertEqual(done.returncode, 0, done.stderr)
        [row] = json.loads(done.stdout)["data"]["followups"]
        self.assertEqual((row["item"], row["kind"], row["class"], row["status"]), ("P2.1", "follow_up", "write_set", "open"))

    def test_repeat_with_the_same_attempt_registers_once(self):
        argv = ("--status", "done_with_deviations", "--attempt-id", "run-1")
        self.assertEqual(self.register(report(open_issues=ALL_ISSUES), "P2.1", *argv)[0], 0)
        before = self.journal()
        code, receipt, err = self.register(report(open_issues=ALL_ISSUES), "P2.1", *argv)
        self.assertEqual(code, 0, err)
        self.assertEqual([c["result"] for c in receipt["calls"]], ["no-op"] * 6)
        self.assertEqual(self.journal(), before)
        self.assertEqual(len(self.events("P2.1", "finish")), 1)
        for issue in ALL_ISSUES[1:]:
            with self.subTest(issue=issue["text"]):
                same = [e for e in self.events("P2.1", issue["kind"]) if e["summary"] == issue["text"]]
                self.assertEqual(len(same), 1)

    def test_blocked_records_the_escalation(self):
        issues = [{"text": "owner must pick a license", "kind": "escalation"}]
        code, _, err = self.register(report(open_issues=issues), "P2.1", "--status", "blocked", "--attempt-id", "b")
        self.assertEqual(code, 0, err)
        item = self.get("P2.1")
        self.assertEqual((item["status"], item["result"]["escalation"]), ("blocked", "owner must pick a license"))

    def test_evidence_file_gives_the_check_result(self):
        doc = json.loads((bridge_fixture.PLANNER / "tests/engine/fixtures/evidence/cmd-pass.json").read_text("utf-8"))
        doc["subject"] = "PLAN3.P2.1"
        self.write(f"plans/{bridge_fixture.PLAN_NAME}/artifacts/evidence/V1.json", doc)
        code, receipt, err = self.register(report(evidence=["@plan/artifacts/evidence/V1.json"]), "P2.1",
                                           "--status", "done", "--evidence", "V1=@plan/artifacts/evidence/V1.json")
        self.assertEqual(code, 0, err)
        finish = receipt["calls"][-1]["argv"]
        self.assertNotIn("--check", finish)
        [check] = self.get("P2.1")["result"]["checks"]
        self.assertEqual((check["id"], check["exit"], check["evidence"]), ("V1", 0, "@plan/artifacts/evidence/V1.json"))

    def test_unit_return_and_its_repeat(self):
        unit = {"goal": "Piece", "files": ["lib/a.py"], "route": {"class": "implementation", "effort": "high"},
                "mode": "delegate"}
        self.assertEqual(self.plan_py("unit", self.plan, "P2.1", "add", "--title", "Piece",
                                      "--json", json.dumps(unit)).returncode, 0)
        done = self.plan_py("unit", self.plan, "P2.1", "U1", "dispatch", "--agent", UNIT_WORKER)
        self.assertEqual(done.returncode, 0, done.stderr)
        for expected in ("recorded", "no-op"):
            with self.subTest(expected):
                code, receipt, err = self.register(report(), "P2.1/U1", "--attempt-id", "w1")
                self.assertEqual(code, 0, err)
                self.assertEqual([c["result"] for c in receipt["calls"]], [expected])
        stored = self.get("P2.1/U1")
        self.assertEqual(stored["status"], "returned")
        self.assertEqual(stored["outcome"]["changed"], ["lib/a.py", "lib/b.py"])

    def test_dry_run_prints_argv_and_writes_nothing(self):
        before = self.journal()
        code, calls, err = self.register(report(open_issues=ALL_ISSUES), "P2.1", "--status", "done_with_deviations",
                                         "--attempt-id", "a", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertEqual([argv[0] for argv in calls], ["log"] * 5 + ["finish"])
        self.assertEqual(self.journal(), before)

    def test_core_refusal_stops_with_a_refused_receipt(self):
        code, receipt, _ = self.register(report(), "P2.2", "--status", "done")
        self.assertEqual(code, 1)
        self.assertEqual(receipt["calls"][-1]["result"], "refused")
        self.assertIn("NOT_STARTED", receipt["calls"][-1]["error"])
        self.assertNotIn("next", receipt)

    def test_bridge_refusal_writes_nothing(self):
        before = self.journal()
        code, receipt, err = self.register(report(open_issues=["untyped"]), "P2.1", "--status", "done",
                                           "--attempt-id", "a")
        self.assertEqual((code, receipt), (1, None))
        self.assertTrue(err.startswith("REGISTER_UNCLASSIFIED: "), err)
        self.assertEqual(self.journal(), before)


class RegisterReviewTests(CliCase):
    def review(self, findings, ref="P2.1", *extra):
        done = self.plan_py("bridge", "planner-orch", "register-review", self.plan, ref, "--findings",
                            self.write("findings.json", findings), "--actor", REGISTRAR, *extra)
        return done.returncode, (json.loads(done.stdout) if done.stdout.strip() else None), done.stderr

    def test_review_becomes_a_document_and_a_note(self):
        for expected in ("recorded", "no-op"):
            with self.subTest(expected):
                code, receipt, err = self.review(FINDINGS)
                self.assertEqual(code, 0, err)
                self.assertEqual([c["result"] for c in receipt["calls"]], [expected] * 2)
        doc = self.get("knowledge/review-P2-1-2026-10-06")
        self.assertEqual(doc["applies_to"], ["P2.1"])
        self.assertEqual([s["id"] for s in doc["sections"]], ["verdict", "findings"])
        self.assertIn("empty input crashes", doc["sections"][1]["text"])
        notes = [e["summary"] for e in self.events("P2.1", "note") if e["summary"].startswith("review ")]
        self.assertEqual(notes, ["review ATTENTION: @plan/knowledge/review-P2-1-2026-10-06.json; "
                                 "reviewer codex/gpt-5.5/high session s-42"])

    def test_phase_review_and_dry_run(self):
        before = self.journal()
        code, calls, err = self.review({**FINDINGS, "findings": []}, "P2", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertEqual([argv[0] for argv in calls], ["add-document", "log"])
        self.assertEqual(json.loads(calls[0][3])["sections"][1]["text"], "No findings.")
        self.assertEqual(self.journal(), before)

    def test_invalid_findings_are_refused(self):
        cases = [{**FINDINGS, "verdict": "OK"}, {**FINDINGS, "reviewer": {"route": "x"}},
                 {**FINDINGS, "date": "06.10.2026"}, {**FINDINGS, "findings": [{"severity": "major"}]},
                 {k: v for k, v in FINDINGS.items() if k != "date"}]
        for findings in cases:
            with self.subTest(findings=findings):
                code, receipt, err = self.review(findings)
                self.assertEqual((code, receipt), (1, None))
                self.assertTrue(err.startswith("REGISTER_FINDINGS_INVALID: "), err)
        self.assertEqual(self.review(FINDINGS, "P2.1/U1")[0], 1)

    def test_pure_calls_name_the_document(self):
        calls = register_review.plan_calls(FINDINGS, argparse.Namespace(plan="PLAN3", ref="P2", actor=REGISTRAR,
                                                                        plans_root=None))
        self.assertEqual(json.loads(calls[0][3])["id"], "review-P2-2026-10-06")
        self.assertEqual(calls[1][:6], ["log", "PLAN3", "P2", "--type", "note", "--summary"])


if __name__ == "__main__":
    unittest.main()
