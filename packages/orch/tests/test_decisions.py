"""The life cycle of decisions (P7.6, D10): an answered question becomes a decision of the work source after register
(``source decision``, DECISION_NOT_RECORDED when the source cannot take it), and the same question of the same piece
asked again is answered by the accepted decision (QUESTION_REUSED) unless its meaning changed (QUESTION_REUSE_REFUSED)."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from orch import worksource
from orch.conductor import questions, records
from orch.worksource_file import FileWorkSource
from tests.test_conductor import GREEN, INPUT, ConductorCase, executor_ok
from tests.test_conductor_questions import ASK, asking


class DecisionCase(ConductorCase):
    def messages(self, err: str, code: str) -> list:
        return [line.get("message", "") for line in self.lines(err) if line.get("reason_code") == code]

    def reopen(self, holder: bool = False) -> None:
        doc = self.source()
        doc["items"]["W1"]["status"] = "todo"
        if holder:  # another run takes the piece
            doc["items"]["W1"]["holder"] = None
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")

    def configure_source(self, **fields) -> None:
        doc = self.source()
        doc.update(fields)
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")

    def answered_run(self, option: str = "rename", ask: dict = ASK) -> tuple:
        """The question is asked, answered by the owner and applied by a retry; the piece is done and registered."""
        self.script({"executor": [asking(dict(ask)), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 4, err)
        run = self.run_dir(err).name
        code, _, _ = self.conduct("answer", "--run", run, "--item", "W1", "--question", ask["id"], "--option", option,
                                  "--by", "owner")
        self.assertEqual(code, 0)
        self.reopen()
        code, _, err = self.conduct("resume", "--run", run, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        return run, err

    def decisions_asked(self) -> list:
        return [call for call in self.source()["calls"] if call["op"] == "decision"]

    def plant(self, entry: dict, decision: str = "rename: rename", **over) -> dict:
        """An accepted decision in the next brief of W1, as the planner bridge carries one."""
        planted = {"ref": "D9", "loaded": True, "title": "W1 Q1", "status": "accepted", "decision": decision,
                   "rationale": "earlier", "question_key": questions.question_key("W1", entry),
                   "question_digest": questions.question_digest("W1", entry), **over}
        doc = self.source()
        doc["items"]["W1"]["decisions"] = [planted]
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        return planted


class RecordTests(DecisionCase):
    def test_an_answered_question_becomes_one_decision_after_register_with_its_key(self):  # (a), (e)
        self.answered_run()
        (asked,) = self.decisions_asked()
        entry = dict(ASK)
        self.assertEqual((asked["question_key"], asked["question_digest"]),
                         (questions.question_key("W1", entry), questions.question_digest("W1", entry)))
        self.assertEqual((asked["ref"], asked["authority"], asked["resolution"]["value"], asked["resolution"]["by"]),
                         ("W1", "owner", "rename", "owner"))
        self.assertEqual((asked["question"]["id"], asked["question"]["kind"], asked["question"]["options"]),
                         ("Q1", "decision", ASK["options"]))
        self.assertIn("Answered by owner: rename: rename", asked["rationale"])
        self.assertTrue(asked["evidence"][0].endswith("W1/questions.json"), asked["evidence"])
        self.assertEqual(self.source()["items"]["W1"]["decisions"][0]["decision"], "rename: rename")

    def test_the_decision_is_asked_only_after_register_never_when_the_answer_is_given(self):  # (e)
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")], "reviewer": [GREEN]})
        _, _, err = self.run_items("W1")
        run = self.run_dir(err).name
        self.conduct("answer", "--run", run, "--item", "W1", "--question", "Q1", "--option", "keep", "--by", "owner")
        self.assertEqual(self.decisions_asked(), [])  # the answer alone writes nothing
        self.reopen()
        self.conduct("resume", "--run", run, "--retry", "W1", "--json-lines")
        ops = [call["op"] for call in self.source()["calls"]]
        registered = max(index for index, op in enumerate(ops) if op == "register")
        self.assertEqual([index for index, op in enumerate(ops) if op == "decision"], [registered + 1])
        self.assertLess(registered, ops.index("commit"))

    def test_a_blocked_piece_records_nothing_even_with_an_applied_answer(self):
        self.script({"executor": [asking(dict(ASK)), asking(dict(ASK, id="Q2", text="Rename the module too?"))],
                     "reviewer": [GREEN]})
        _, _, err = self.run_items("W1")
        run = self.run_dir(err).name
        self.conduct("answer", "--run", run, "--item", "W1", "--question", "Q1", "--option", "keep", "--by", "owner")
        self.reopen()
        code, _, err = self.conduct("resume", "--run", run, "--retry", "W1", "--json-lines")
        self.assertEqual(code, 4, err)
        self.assertEqual(self.decisions_asked(), [])  # Q2 waits: a decision now would make its answer stale

    def test_a_source_without_the_operation_loses_the_decision_not_the_piece(self):  # (d), (p)
        self.configure_source(no_decision=True)
        run, err = self.answered_run()
        (said,) = self.messages(err, "DECISION_NOT_RECORDED")
        self.assertIn("Q1", said)
        self.assertIn("unsupported", said)
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")
        kept = self.run_dir(err) / "W1" / "decisions" / "Q1.json"
        self.assertEqual(json.loads(kept.read_text())["question"]["id"], "Q1")  # the request stays in the run

    def test_a_refusal_of_the_source_is_the_same_info(self):
        self.configure_source(refuse=["decision"])
        run, err = self.answered_run()
        (said,) = self.messages(err, "DECISION_NOT_RECORDED")
        self.assertIn("DECISION_TEST_REFUSAL", said)
        self.assertEqual(self.outcome(err), ("finished", None))

    def test_policy_defaults_and_reused_decisions_are_not_recorded(self):
        self.write_config(extra='[orch.conductor]\nquestions = "defaults"\n')
        self.script({"executor": [asking(dict(ASK, default="keep")), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.decisions_asked(), [])

    def test_the_receipt_of_the_decision_is_kept_per_question(self):
        run, err = self.answered_run()
        receipts = self.run_dir(err).parent.parent  # the run folder of the source CLI is under the project state
        found = list(Path(self.project).rglob("receipts/decision-Q1.json"))
        self.assertTrue(found, receipts)
        self.assertEqual(json.loads(found[0].read_text())["outcome"], "recorded")


class ReuseTests(DecisionCase):
    def reuse_run(self, ask: dict = ASK, script=None) -> tuple:
        self.reopen(holder=True)
        for counter in self.fake.glob("*.count"):  # the scripted roles answer from their first answer again
            counter.unlink()
        self.script(script or {"executor": [asking(dict(ask)), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        return code, err

    def test_the_same_question_in_a_new_run_is_answered_by_the_decision_without_a_stop(self):  # (b)
        self.answered_run()
        code, err = self.reuse_run()
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        (said,) = self.messages(err, "QUESTION_REUSED")
        self.assertIn("Q1", said)
        self.assertIn("D1", said)
        entry = self.state(err)["questions"]["W1"]["Q1"]
        self.assertEqual((entry["status"], entry["resolution"]["value"], entry["resolution"]["by"]),
                         ("applied", "rename", "decision:D1"))
        self.assertEqual(entry["question_key"], questions.question_key("W1", ASK))
        self.assertIn("Answer: rename (by decision:D1)", self.prompt("executor", 2))
        self.assertEqual(len(self.decisions_asked()), 1)  # a reused answer is not recorded again
        for line in self.lines(err):  # the entry with its key is a records/v1 document
            self.assertIsNotNone(line)
        document = records.read(self.run_dir(err) / "W1" / questions.FILE, "questions")
        self.assertEqual(document["questions"][0]["question_digest"], questions.question_digest("W1", ASK))

    def test_an_approval_is_never_reused(self):  # (c)
        approval = dict(ASK, id="Q2", kind="approval", options=[{"id": "yes", "label": "yes"}])
        self.plant(approval, decision="yes: yes")
        code, err = self.reuse_run(approval, {"executor": [asking(dict(approval))]})
        self.assertEqual(code, 4, err)
        self.assertEqual(self.messages(err, "QUESTION_REUSED"), [])
        self.assertEqual(self.state(err)["questions"]["W1"]["Q2"]["status"], "open")

    def test_a_number_that_changed_is_another_question(self):  # (q)
        before = dict(ASK, id="Q3", kind="clarification", text="Retry at most 30 times?", options=[])
        after = dict(before, text="Retry at most 300 times?")
        self.assertNotEqual(questions.question_key("W1", before), questions.question_key("W1", after))
        self.plant(before, decision="30")
        code, err = self.reuse_run(after, {"executor": [asking(dict(after))]})
        self.assertEqual(code, 4, err)
        self.assertEqual(self.messages(err, "QUESTION_REUSED"), [])
        self.assertEqual(self.messages(err, "QUESTION_REUSE_REFUSED"), [])  # nothing names this question

    def test_the_same_option_ids_with_another_definition_are_another_question(self):  # (r)
        other = dict(ASK, options=[{"id": "keep", "label": "keep both names"}, {"id": "rename", "label": "rename"}])
        self.assertNotEqual(questions.question_key("W1", ASK), questions.question_key("W1", other))
        self.plant(ASK)
        code, err = self.reuse_run(other, {"executor": [asking(dict(other))]})
        self.assertEqual(code, 4, err)
        self.assertEqual(self.messages(err, "QUESTION_REUSED"), [])

    def test_a_value_that_is_no_option_of_the_question_is_refused(self):  # (s)
        self.plant(ASK, decision="delete everything")
        code, err = self.reuse_run(ASK, {"executor": [asking(dict(ASK))]})
        self.assertEqual(code, 4, err)
        (said,) = self.messages(err, "QUESTION_REUSE_REFUSED")
        self.assertIn("reason: value", said)
        self.assertEqual(self.state(err)["questions"]["W1"]["Q1"]["status"], "open")

    def test_a_key_without_the_digest_is_refused(self):
        planted = self.plant(ASK)
        doc = self.source()
        del doc["items"]["W1"]["decisions"][0]["question_digest"]
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        code, err = self.reuse_run(ASK, {"executor": [asking(dict(ASK))]})
        self.assertEqual(code, 4, err)
        (said,) = self.messages(err, "QUESTION_REUSE_REFUSED")
        self.assertIn("reason: digest", said)
        self.assertEqual(planted["status"], "accepted")

    def test_a_decision_that_is_not_accepted_is_not_used(self):
        self.plant(ASK, status="proposed")
        code, err = self.reuse_run(ASK, {"executor": [asking(dict(ASK))]})
        self.assertEqual(code, 4, err)
        self.assertEqual(self.messages(err, "QUESTION_REUSED"), [])

    def test_a_reused_answer_that_the_executor_asks_again_goes_to_the_owner(self):
        self.plant(ASK)
        code, err = self.reuse_run(ASK, {"executor": [asking(dict(ASK)), asking(dict(ASK))]})
        self.assertEqual(code, 4, err)
        self.assertEqual(len(self.messages(err, "QUESTION_REUSED")), 1)
        self.assertEqual(self.state(err)["questions"]["W1"]["Q1"]["status"], "open")


class KeyTests(unittest.TestCase):
    def test_the_key_is_stable_and_follows_the_meaning(self):
        key = questions.question_key("W1", ASK)
        self.assertRegex(key, r"^qk-[0-9a-f]{16}$")
        self.assertTrue(questions.question_digest("W1", ASK).startswith(key[3:]))
        spaced = dict(ASK, text="Keep  the old\nflag name?", id="Q9", revision=4, blocking=False)
        self.assertEqual(questions.question_key("W1", spaced), key)  # whitespace, id, revision and flags are no meaning
        reordered = dict(ASK, options=list(reversed(ASK["options"])))
        self.assertEqual(questions.question_key("W1", reordered), key)
        self.assertNotEqual(questions.question_key("W2", ASK), key)  # another piece
        self.assertNotEqual(questions.question_key("W1", dict(ASK, text="keep the old flag name?")), key)  # case counts
        self.assertNotEqual(questions.question_key("W1", dict(ASK, kind="clarification")), key)
        self.assertNotEqual(questions.question_key("W1", dict(ASK, answer_schema={"type": "string"})), key)

    def test_reusable_value_reads_an_option_or_checks_the_schema(self):
        self.assertEqual(questions.reusable_value(ASK, "rename: rename"), (True, "rename"))
        self.assertEqual(questions.reusable_value(ASK, "keep"), (True, "keep"))
        self.assertEqual(questions.reusable_value(ASK, "renamed"), (False, None))
        number = {"id": "Q", "kind": "clarification", "text": "How many?", "answer_schema": {"type": "integer", "minimum": 1}}
        self.assertEqual(questions.reusable_value(number, "3"), (True, 3))
        self.assertEqual(questions.reusable_value(number, "0"), (False, None))
        self.assertEqual(questions.reusable_value(number, "many"), (False, None))

    def test_a_decision_with_the_digest_of_the_question_under_another_key_is_the_key_reason(self):
        decision = {"status": "accepted", "decision": "keep", "question_key": "qk-" + "0" * 16,
                    "question_digest": questions.question_digest("W1", ASK), "ref": "D1"}
        self.assertEqual(questions.reusable("W1", dict(ASK), [decision]), (None, None, "key"))

    def test_a_document_without_the_new_fields_still_reads_and_one_with_them_passes(self):
        old = {"run": "cnd-1", "item": "W1", "questions": [{
            "id": "Q1", "revision": 1, "kind": "decision", "text": "t", "blocking": True, "status": "open",
            "binding": {"step": "executor.1"}, "asked_at": "2026-10-24T00:00:00Z"}]}
        self.assertEqual(records.problems(old, "questions"), [])
        new = json.loads(json.dumps(old))
        new["questions"][0].update(question_key=questions.question_key("W1", new["questions"][0]),
                                   question_digest=questions.question_digest("W1", new["questions"][0]))
        self.assertEqual(records.problems(new, "questions"), [])
        new["questions"][0]["question_key"] = "qk-short"
        self.assertNotEqual(records.problems(new, "questions"), [])


class FileSourceTests(unittest.TestCase):
    def request(self, doc: dict, **over) -> dict:
        return {"collection": "input", "ref": doc["input_id"], "run_id": "run-1",
                "question": {"id": "Q1", "revision": 1, "kind": "decision", "text": "Keep?",
                             "options": [{"id": "keep", "label": "keep"}]},
                "question_key": "qk-" + "a" * 16, "question_digest": "a" * 64,
                "resolution": {"value": "keep", "by": "owner"}, "authority": "owner", "rationale": "Answered by owner: keep",
                "evidence": ["x/questions.json"], **over}

    def test_the_file_source_appends_to_decisions_json_and_a_repeat_changes_nothing(self):  # (f)
        doc = json.loads(INPUT.read_text())
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            source = FileWorkSource(INPUT, project=project)
            first = source.decision(**self.request(doc))
            self.assertEqual(first["outcome"], "recorded")
            target = project / ".swissknifeman" / "orch-artifacts" / "run-1" / doc["input_id"] / "decisions.json"
            body = target.read_text()
            self.assertEqual(json.loads(body)[0]["question_key"], "qk-" + "a" * 16)
            self.assertEqual(source.decision(**self.request(doc))["outcome"], "no-op")
            self.assertEqual(target.read_text(), body)
            other = source.decision(**self.request(doc, question_key="qk-" + "b" * 16))
            self.assertEqual(other["outcome"], "recorded")
            self.assertEqual(len(json.loads(target.read_text())), 2)

    def test_a_request_outside_the_contract_never_reaches_the_source(self):
        doc = json.loads(INPUT.read_text())
        with tempfile.TemporaryDirectory() as temporary:
            source = FileWorkSource(INPUT, project=Path(temporary))
            with self.assertRaises(worksource.WorkSourceError) as caught:
                source.decision(**self.request(doc, authority="policy"))
            self.assertEqual(caught.exception.code, "INPUT_INVALID")
            with self.assertRaises(worksource.WorkSourceError):
                source.decision(**self.request(doc, question_key="qk-1"))


if __name__ == "__main__":
    unittest.main()
