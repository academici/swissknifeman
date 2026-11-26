"""Waiting for a decision (PLAN9 P7.5): a piece that waits for the answer to a question ends the run ``waiting`` (exit code 4,
Stop ``WAITING_DECISION``), ``continue`` and ``answer --continue`` go on with the answered pieces, and an escalation names
its class: ``decision`` becomes the question ``esc-<n>``, the others get a code of their own and never reach the advisor."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from orch.conductor import contract, engine, heal, records, runs
from orch.conductor.infrastructure.files import write_json
from tests.test_conductor import FIXTURES, GREEN, ROLES, ConductorCase, executor_ok, report
from tests.test_conductor_questions import ASK

ADVISOR = '[orch.conductor]\nquestions = "advisor"\n\n[orch.advisor]\nenabled = true\n'


def escalating(ref: str, escalation_class: str, text: str, **extra) -> dict:
    return {"result": report(ref, "blocked", changed_paths=[], checks_run=[], **extra, open_issues=[
        {"text": text, "kind": "escalation", "escalation_class": escalation_class}])}


def asks(ref: str) -> dict:
    return {"result": report(ref, "blocked", changed_paths=[], checks_run=[], questions=[dict(ASK)],
                             open_issues=[{"text": "needs an answer from the owner", "kind": "escalation"}])}


class WaitingCase(ConductorCase):
    def reopen(self, *refs) -> None:
        doc = self.source()
        for ref in refs or ("W1",):
            doc["items"][ref]["status"] = "todo"  # the source reopened the piece
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")

    def two_pieces(self) -> None:
        self.set_items({ref: {"options": [{"source": f"item:{ref}", "options": {"on_blocked": "report"}}]}
                        for ref in ("W1", "W2")})

    def answer(self, run: str, ref: str, *extra) -> tuple:
        return self.conduct("answer", "--run", run, "--item", ref, "--question", "Q1", "--option", "rename",
                            "--by", "owner", *extra)

    def status(self, run: str) -> dict:
        code, out, _ = self.conduct("status", "--run", run, "--json")
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def end(self, err: str) -> dict:
        return [line for line in self.lines(err) if line["event"] == "run.end"][-1]


class WaitingOutcomeTests(WaitingCase):
    def test_a_piece_that_waits_for_an_answer_ends_the_run_waiting_with_exit_4(self):
        self.script({"executor": [asks("W1"), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (4, ("waiting", "WAITING_DECISION")), err)
        run = self.run_dir(err)
        self.assertIn(f"orch conduct continue --run {run.name}", self.end(err)["message"])
        self.assertIn("W1 waits for an answer to Q1", self.end(err)["message"])
        state = self.state(err)
        self.assertEqual((state["status"], state["stop"]["code"]), ("waiting", "WAITING_DECISION"))
        waiting = state["items"]["W1"]["waiting"]
        self.assertEqual(waiting["question_ids"], ["Q1"])
        self.assertTrue(waiting["since"].endswith("Z"))
        for line in self.lines(err):
            self.assertEqual(contract.problems(line, "progress-line"), [], line)
        found = self.status(run.name)
        self.assertEqual(found["status"], "waiting")
        self.assertEqual(found["waiting"], [{"item": "W1", "question_ids": ["Q1"], "since": waiting["since"]}])
        listed = json.loads(self.conduct("runs", "--json")[1])["runs"]
        self.assertEqual([(row["run_id"], row["status"]) for row in listed], [(run.name, "waiting")])

    def test_on_blocked_report_goes_on_with_the_others_and_still_ends_waiting(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"on_blocked": "report"}}]}, "W2": {}})
        self.script({"executor": [asks("W1"), executor_ok("W2")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", "W2")
        self.assertEqual((code, self.outcome(err)), (4, ("waiting", "WAITING_DECISION")), err)
        self.assertEqual({ref: item["status"] for ref, item in self.source()["items"].items()},
                         {"W1": "blocked", "W2": "done"})
        self.assertEqual([row["item"] for row in self.status(self.run_dir(err).name)["waiting"]], ["W1"])

    def test_a_blocked_piece_without_a_question_stays_item_blocked_with_exit_1(self):
        blocked = report("W1", "blocked", changed_paths=[], checks_run=[],
                         open_issues=[{"text": "needs a decision", "kind": "escalation"}])
        self.script({"executor": [{"result": blocked}], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual(self.status(self.run_dir(err).name)["waiting"], [])
        self.assertNotIn("waiting", self.state(err)["items"]["W1"])

    def test_a_denied_question_is_a_refusal_not_a_wait(self):
        self.write_config(extra='[orch.conductor]\nquestions = "deny"\n')
        self.script({"executor": [asks("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertNotIn("waiting", self.state(err)["items"]["W1"])


class ContinueTests(WaitingCase):
    def blocked_run(self) -> tuple:
        self.script({"executor": [asks("W1"), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 4, err)
        return err, self.run_dir(err).name

    def test_answer_then_continue_finishes_the_piece_with_the_answer(self):
        _, run = self.blocked_run()
        code, out, _ = self.answer(run, "W1")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["next"], f"orch conduct continue --run {run} --item W1")
        self.reopen()
        code, _, err = self.conduct("continue", "--run", run, "--json-lines")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")
        self.assertIn("Answer: rename (by owner)", self.prompt("executor", 2))
        state = self.state(err)
        self.assertNotIn("waiting", state["items"]["W1"])
        self.assertEqual(state["status"], "finished")
        self.assertEqual(self.status(run)["waiting"], [])

    def test_continue_refuses_a_piece_whose_blocking_question_is_unanswered(self):
        err, run = self.blocked_run()
        before = (self.calls("executor"), self.state(err)["resumes"] if "resumes" in self.state(err) else 0)
        self.reopen()
        code, _, out_err = self.conduct("continue", "--run", run, "--json-lines")
        self.assertEqual(code, 1)
        self.assertIn("QUESTIONS_OPEN", out_err)
        self.assertIn("W1:Q1", out_err)
        self.assertEqual(self.calls("executor"), before[0])  # nothing was started
        state = json.loads((engine.runs_root(self.project) / run / engine.STATE_FILE).read_text())
        self.assertEqual((state["status"], state["items"]["W1"]["outcome"]), ("waiting", "blocked"))
        self.assertEqual(state.get("resumes", 0), before[1])

    def test_continue_names_a_piece_that_does_not_wait(self):
        _, run = self.blocked_run()
        code, _, err = self.conduct("continue", "--run", run, "--item", "W9")
        self.assertEqual(code, 1)
        self.assertIn("NOT_WAITING", err)

    def test_partial_continues_only_the_pieces_that_are_ready(self):
        self.two_pieces()
        self.script({"executor": [asks("W1"), asks("W2"), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", "W2")
        self.assertEqual((code, self.outcome(err)), (4, ("waiting", "WAITING_DECISION")), err)
        run = self.run_dir(err).name
        self.assertEqual(self.answer(run, "W1")[0], 0)
        self.reopen("W1")
        code, _, whole = self.conduct("continue", "--run", run, "--json-lines")
        self.assertEqual(code, 1)
        self.assertIn("W2:Q1", whole)
        self.assertNotIn("W1:Q1", whole)
        self.assertEqual(self.calls("executor"), 2)
        code, _, err = self.conduct("continue", "--run", run, "--partial", "--json-lines")
        self.assertEqual((code, self.outcome(err)), (4, ("waiting", "WAITING_DECISION")), err)
        self.assertEqual({ref: item["status"] for ref, item in self.source()["items"].items()},
                         {"W1": "done", "W2": "blocked"})
        self.assertEqual(self.calls("executor"), 3)
        self.assertEqual([row["item"] for row in self.status(run)["waiting"]], ["W2"])

    def test_answer_with_continue_is_one_command(self):
        _, run = self.blocked_run()
        self.reopen()
        code, out, err = self.answer(run, "W1", "--continue", "--json-lines")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["resolution"]["value"], "rename")
        self.assertEqual(self.outcome(err), ("finished", None), err)
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")
        self.assertIn("Answer: rename (by owner)", self.prompt("executor", 2))

    def test_answer_with_continue_does_not_continue_a_failed_answer(self):
        _, run = self.blocked_run()
        code, _, err = self.conduct("answer", "--run", run, "--item", "W1", "--question", "Q1", "--option", "nope",
                                    "--continue", "--json-lines")
        self.assertEqual(code, 1)
        self.assertIn("ANSWER_INVALID", err)
        self.assertEqual(self.calls("executor"), 1)

    def test_a_retry_removes_the_wait_and_a_settle_too(self):
        _, run = self.blocked_run()
        self.assertEqual(self.conduct("settle", "--run", run, "--item", "W1", "--outcome", "done", "--reason", "by hand")[0], 0)
        state = json.loads((engine.runs_root(self.project) / run / engine.STATE_FILE).read_text())
        self.assertNotIn("waiting", state["items"]["W1"])


class EscalationClassTests(WaitingCase):
    def advisor_on(self) -> None:
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "advisor")},
                          extra=ADVISOR)

    def test_a_decision_escalation_without_a_question_becomes_the_question_esc_1(self):
        self.script({"executor": [escalating("W1", "decision", "the flag is public: keep its name or rename it?"),
                                  executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (4, ("waiting", "WAITING_DECISION")), err)
        run = self.run_dir(err)
        saved = json.loads((run / "W1" / "questions.json").read_text())
        (entry,) = saved["questions"]
        self.assertEqual((entry["id"], entry["kind"], entry["status"], entry["blocking"], "options" in entry),
                         ("esc-1", "decision", "open", True, False))
        self.assertEqual(entry["text"], "the flag is public: keep its name or rename it?")
        self.assertEqual(records.check(saved, "questions", "questions.json"), saved)
        self.assertTrue([line for line in self.lines(err) if line.get("reason_code") == "QUESTION_QUEUED"])
        self.assertEqual(self.state(err)["items"]["W1"]["waiting"]["question_ids"], ["esc-1"])
        code, _, _ = self.conduct("answer", "--run", run.name, "--item", "W1", "--question", "esc-1", "--text", "rename it",
                                  "--by", "owner")
        self.assertEqual(code, 0)
        self.reopen()
        code, _, err = self.conduct("continue", "--run", run.name, "--json-lines")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertIn("Answer: rename it (by owner)", self.prompt("executor", 2))

    def test_the_synthetic_question_passes_the_gates_a_default_never_answers_it(self):
        self.write_config(extra='[orch.conductor]\nquestions = "defaults"\n')
        self.script({"executor": [escalating("W1", "decision", "keep or rename?"), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (4, ("waiting", "WAITING_DECISION")), err)
        self.assertEqual(self.state(err)["questions"]["W1"]["esc-1"]["status"], "open")

    def test_the_synthetic_question_is_asked_once_until_it_is_answered(self):
        self.script({"executor": [escalating("W1", "decision", "keep or rename?"),
                                  escalating("W1", "decision", "keep or rename?"),
                                  escalating("W1", "decision", "and the docs?")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 4, err)
        run = self.run_dir(err).name
        self.reopen()  # a retry without an answer asks nothing new
        code, _, err = self.conduct("resume", "--run", run, "--retry", "W1", "--json-lines")
        self.assertEqual(code, 4, err)
        self.assertEqual(sorted(self.state(err)["questions"]["W1"]), ["esc-1"])
        self.assertEqual(self.conduct("answer", "--run", run, "--item", "W1", "--question", "esc-1", "--text", "rename",
                                      "--by", "owner")[0], 0)
        self.reopen()  # the answer is given, and the executor escalates again: a new question
        code, _, err = self.conduct("continue", "--run", run, "--json-lines")
        self.assertEqual(code, 4, err)
        questions = self.state(err)["questions"]["W1"]
        self.assertEqual({name: entry["status"] for name, entry in questions.items()},
                         {"esc-1": "applied", "esc-2": "open"})
        self.assertEqual(self.state(err)["items"]["W1"]["waiting"]["question_ids"], ["esc-2"])

    def test_an_environment_escalation_is_a_block_with_its_code_and_no_advisor(self):
        self.advisor_on()
        self.script({"executor": [escalating("W1", "environment", "out/ is read-only in the sandbox")],
                     "advisor": [{"result": {}}], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual(self.calls("advisor"), 0)
        (text,) = [issue["text"] for issue in self.source()["items"]["W1"]["report"]["open_issues"]
                   if issue["kind"] == "escalation"]
        self.assertTrue(text.startswith("ENVIRONMENT_BLOCKED: out/ is read-only in the sandbox"), text)
        self.assertIn("orch.py doctor", text)
        self.assertIn("--allow-path", text)
        end = [line for line in self.lines(err) if line["event"] == "item.end"][-1]
        self.assertEqual(end["reason_code"], "ENVIRONMENT_BLOCKED")
        self.assertNotIn("escalation_class", json.dumps(self.source()["items"]["W1"]["report"]))  # the register body is closed
        self.assertFalse((self.run_dir(err) / "W1" / "questions.json").exists())

    def test_the_other_classes_get_their_code(self):
        for ref, (escalation_class, code) in zip(("W1", "W2", "W3"), (("pre_existing_red", "PRE_EXISTING_RED"),
                                                                       ("scope", "SCOPE_EXPANSION"),
                                                                       ("authority", "AUTHORITY_REQUIRED"))):
            with self.subTest(escalation_class=escalation_class):
                self.set_items({ref: {}})
                self.script({"executor": [escalating(ref, escalation_class, "V9 was red before the change")],
                             "reviewer": [GREEN]})
                (self.fake / "executor.count").unlink(missing_ok=True)
                self.git("add", "-A")
                self.git("commit", "-q", "--allow-empty", "-m", f"records of {ref}")
                code_, _, err = self.run_items(ref)
                self.assertEqual((code_, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
                end = [line for line in self.lines(err) if line["event"] == "item.end"][-1]
                self.assertEqual(end["reason_code"], code)
                self.assertTrue(end["message"].startswith(code + ":"), end)

    def test_an_own_code_of_the_executor_stays(self):
        self.script({"executor": [escalating("W1", "environment", "WRITE_PROTECTED_PATH: .claude/x -> staged")],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        end = [line for line in self.lines(err) if line["event"] == "item.end"][-1]
        self.assertEqual(end["reason_code"], "WRITE_PROTECTED_PATH")


class EscalationClassHealingTests(unittest.TestCase):
    """The repair of a report keeps ``escalation_class`` (it is a field of the issue, not text to fold) and never guesses it."""

    def doc(self, escalation_class):
        return {"status": "blocked", "summary": "s", "changed_paths": [], "checks_run": [], "evidence": [],
                "open_issues": [{"text": "the sandbox refuses", "kind": "escalation", "escalation_class": escalation_class}]}

    def test_a_valid_class_survives_the_repair_and_a_wrong_one_is_folded_into_the_text(self):
        fixed, _ = heal.heal("stage-report", self.doc("Environment"))
        self.assertEqual(fixed["open_issues"][0]["escalation_class"], "environment")
        self.assertEqual(contract.problems(fixed, "stage-report"), [])
        fixed, notes = heal.heal("stage-report", self.doc("sandbox"))
        issue = fixed["open_issues"][0]
        self.assertNotIn("escalation_class", issue)
        self.assertIn("escalation_class: sandbox", issue["text"])
        self.assertEqual(contract.problems(fixed, "stage-report"), [])
        self.assertTrue(notes)


class WaitingRunsTests(unittest.TestCase):
    def test_a_waiting_run_is_neither_orphaned_nor_pruned(self):
        summary = {"status": "waiting", "reason_code": "WAITING_DECISION", "items": []}
        self.assertEqual(runs.effective_status(Path("/nonexistent"), summary, {"lease": True}), summary)
        self.assertNotIn("waiting", runs.PRUNABLE)


class WaitingRecordsTests(unittest.TestCase):
    """save → load → resume of a state without ``waiting`` (written before P7.5) and with it (records/v1 state)."""

    BASE = {"$schema": "urn:swissknifeman:orch:records:state:v1", "claims": {}, "status": "stopped",
            "items": {"W1": {"steps": {}, "outcome": "blocked"}}, "tokens": {"input": 0, "output": 0}}

    def test_a_state_without_waiting_reads_and_a_state_with_it_round_trips(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            write_json(path, self.BASE)
            self.assertEqual(records.read(path, "state")["items"]["W1"].get("waiting"), None)
            waiting = json.loads(json.dumps(self.BASE))
            waiting["status"] = "waiting"
            waiting["items"]["W1"]["waiting"] = {"question_ids": ["Q1"], "since": "2026-10-23T12:00:00Z"}
            records.write(path, waiting, "state")
            self.assertEqual(records.read(path, "state")["items"]["W1"]["waiting"]["question_ids"], ["Q1"])

    def test_a_wait_without_questions_is_refused(self):
        broken = json.loads(json.dumps(self.BASE))
        broken["items"]["W1"]["waiting"] = {"question_ids": [], "since": "2026-10-23T12:00:00Z"}
        with self.assertRaises(engine.Stop):
            records.check(broken, "state", "state.json")


if __name__ == "__main__":
    unittest.main()
