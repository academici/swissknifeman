"""The advisor (P10.4): advice/v1, the three triggers (a blocking question under questions = advisor, red checks past the
check_fixes allowance, a Major finding the triager rejected), the human gate, max_rounds and the agent run's causation.
The advisor is a fake role (tests/fixtures/conductor/fake_role.py) that answers the scripted advice."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from orch import settings
from orch.conductor import contract, engine, prompts
from orch.conductor.stages import advice as advice_stage
from tests.test_conductor import FINDING, FIXTURES, GREEN, ROLES, ConductorCase, executor_ok, report, reproduced
from tests.test_conductor_questions import ASK, asking

ENABLED = '[orch.conductor]\nquestions = "advisor"\n\n[orch.advisor]\nenabled = true\n'


def advice(ref: str, recommendation: str = "keep", **extra) -> dict:
    """A scripted answer of the advisor: two options, ``recommendation`` chosen; ``extra`` overrides the fields."""
    doc = {"problem_ref": ref,
           "options": [{"id": "keep", "text": "Keep the old flag name", "pros": ["no break"], "cons": ["two names"]},
                       {"id": "rename", "text": "Rename the flag", "pros": ["one name"], "cons": ["breaks callers"]}],
           "recommendation": recommendation, "confidence": "high", "sources": ["README.md"], "needs_owner": False}
    doc.update(extra)
    return {"result": doc}


class AdvisorCase(ConductorCase):
    def setUp(self):
        super().setUp()
        self.configure(ENABLED)

    def configure(self, extra: str) -> None:
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "advisor")},
                          extra=extra)

    def messages(self, err: str, code: str) -> list:
        return [line.get("message", "") for line in self.lines(err) if line.get("reason_code") == code]

    def reopen(self) -> None:
        doc = self.source()
        doc["items"]["W1"]["status"] = "todo"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")

    def escalations(self) -> list:
        return [issue["text"] for issue in self.source()["items"]["W1"]["report"]["open_issues"]
                if issue["kind"] == "escalation"]


class QuestionTriggerTests(AdvisorCase):
    def test_advice_that_needs_no_owner_answers_the_question_by_advisor(self):
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")], "advisor": [advice("question:Q1@1")],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual((self.calls("advisor"), self.calls("executor")), (1, 2))
        entry = self.state(err)["questions"]["W1"]["Q1"]
        self.assertEqual((entry["status"], entry["resolution"]["value"], entry["resolution"]["by"]),
                         ("applied", "keep", "advisor"))
        self.assertEqual(entry["resolution"]["authority"], {
            "mode": "advisor", "gate": ["destructive", "public-api", "scope-expansion", "security"],
            "code_categories": [], "confidence": "high"})
        self.assertIn("Answer: keep (by advisor)", self.prompt("executor", 2))
        self.assertEqual(len(self.messages(err, "QUESTION_ADVISED")), 1)
        saved = json.loads((self.project / "plans/T/artifacts/W1/advice-1.json").read_text())
        self.assertEqual(contract.problems(saved, "advice"), [])
        self.assertEqual(saved["recommendation"], "keep")
        self.assertIn("plans/T/artifacts/W1/advice-1.json", self.source()["commits"][0]["paths"])  # the records, file by file

    def test_the_prompt_of_the_advisor_names_the_problem_the_evidence_and_the_result_block(self):
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")], "advisor": [advice("question:Q1@1")],
                     "reviewer": [GREEN]})
        self.run_items("W1")
        prompt = self.prompt("advisor", 1)
        self.assertIn("# Advisor", prompt)
        self.assertIn("`problem_ref`: `question:Q1@1`", prompt)
        self.assertIn("Keep the old flag name?", prompt)
        self.assertIn("- `rename`: rename", prompt)
        self.assertIn("## Report of the executor", prompt)
        self.assertIn("```advice", prompt)

    def test_the_agent_run_of_the_advisor_names_the_problem_as_its_causation(self):
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")], "advisor": [advice("question:Q1@1")],
                     "reviewer": [GREEN]})
        _, _, err = self.run_items("W1")
        rows = [json.loads(path.read_text()) for path in sorted((self.run_dir(err) / "W1" / "agents").glob("*/request.json"))]
        by_role = {row["role"]: row for row in rows}
        self.assertEqual((by_role["advisor"]["causation"], by_role["advisor"]["step"]), ("question:Q1@1", "advice.1"))
        self.assertEqual(by_role["executor"]["causation"], by_role["executor"]["step"])  # the others keep the step

    def test_advice_that_needs_the_owner_queues_the_question_with_the_advice(self):
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")],
                     "advisor": [advice("question:Q1@1", needs_owner=True, confidence="low")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        (text,) = [text for text in self.escalations() if text.startswith("QUESTION: Q1")]
        self.assertIn("advisor, plans/T/artifacts/W1/advice-1.json: recommends keep, low confidence", text)
        self.assertIn("for the owner: advisor: the advisor says only the owner can decide", text)
        entry = self.state(err)["questions"]["W1"]["Q1"]
        self.assertEqual(entry["status"], "open")
        self.assertEqual(entry["advice"]["recommendation"], "keep")
        self.assertEqual(self.calls("executor"), 1)

    def test_the_owner_answers_and_the_resume_applies_it_without_a_second_advice(self):
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")],
                     "advisor": [advice("question:Q1@1", needs_owner=True)], "reviewer": [GREEN]})
        _, _, err = self.run_items("W1")
        run = self.run_dir(err).name
        code, _, _ = self.conduct("answer", "--run", run, "--item", "W1", "--question", "Q1", "--option", "rename",
                                  "--by", "owner")
        self.assertEqual(code, 0)
        self.reopen()
        code, _, err2 = self.conduct("resume", "--run", run, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(err2)), (0, ("finished", None)), err2)
        self.assertEqual(self.calls("advisor"), 1)
        self.assertIn("Answer: rename (by owner)", self.prompt("executor", 2))

    def test_a_category_of_the_human_gate_is_held_even_when_the_owner_is_not_needed(self):
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")],
                     "advisor": [advice("question:Q1@1", category="public-api")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        (text,) = [text for text in self.escalations() if text.startswith("QUESTION: Q1")]
        self.assertIn("category public-api is held by orch.advisor.human_gate", text)
        self.assertEqual(self.state(err)["questions"]["W1"]["Q1"]["status"], "open")

    def test_an_emptied_human_gate_lets_the_advice_through(self):
        self.configure(ENABLED + "human_gate = []\n")
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")],
                     "advisor": [advice("question:Q1@1", category="security")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)

    def test_a_recommendation_outside_the_options_of_the_question_is_held(self):
        weird = advice("question:Q1@1", "other")
        weird["result"]["options"].append({"id": "other", "text": "Something else", "pros": [], "cons": []})
        self.script({"executor": [asking(dict(ASK))], "advisor": [weird]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        (text,) = [text for text in self.escalations() if text.startswith("QUESTION: Q1")]
        self.assertIn("is not one of the options of the question", text)

    def test_an_approval_is_the_owners_and_is_not_asked_of_the_advisor(self):
        self.script({"executor": [asking(dict(ASK, id="Q2", kind="approval", options=[{"id": "yes", "label": "yes"}]))]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("advisor")), (1, 0), err)
        self.assertIn("QUESTION: Q2 Keep the old flag name?", self.escalations())

    def test_advisor_mode_without_enabled_queues_the_question(self):
        self.configure('[orch.conductor]\nquestions = "advisor"\n')
        self.script({"executor": [asking(dict(ASK))]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("advisor")), (1, 0), err)
        self.assertEqual(len(self.messages(err, "ADVISOR_DISABLED")), 1)
        self.assertEqual(self.state(err)["questions"]["W1"]["Q1"]["status"], "open")

    def test_enabled_without_the_advisor_mode_leaves_questions_to_the_queue(self):
        self.configure("[orch.advisor]\nenabled = true\n")
        self.script({"executor": [asking(dict(ASK))]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("advisor")), (1, 0), err)

    def test_max_rounds_ends_the_advice_and_the_next_question_is_queued(self):
        self.configure(ENABLED + "max_rounds = 1\n")
        second = dict(ASK, id="Q2", text="Rename the module too?")
        self.script({"executor": [asking(dict(ASK)), asking(second)], "advisor": [advice("question:Q1@1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("advisor")), (1, 1), err)
        self.assertEqual(len(self.messages(err, "ADVISOR_LIMIT")), 1)
        self.assertIn("QUESTION: Q2 Rename the module too?", self.escalations())
        self.assertEqual(self.state(err)["questions"]["W1"]["Q1"]["resolution"]["by"], "advisor")

    def test_the_advisor_that_fails_leaves_the_question_queued(self):
        self.script({"executor": [asking(dict(ASK))], "advisor": [{"text": "no block here"}] * 5})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual(len(self.messages(err, "ADVISOR_FAILED")), 1)
        self.assertEqual(self.state(err)["questions"]["W1"]["Q1"]["status"], "open")


class GateTriggerTests(AdvisorCase):
    def project_advisor(self, text: str) -> None:
        path = self.project / ".swissknifeman" / "config.toml"
        path.parent.mkdir(exist_ok=True)
        path.write_text("schema_version = 1\n" + text, encoding="utf-8")
        self.git("add", ".swissknifeman/config.toml")
        self.git("commit", "-q", "-m", "project advisor configuration")

    def held(self, recommendation: dict, expected: str, write=None) -> dict:
        asked = asking(dict(ASK))
        if write:
            asked["write"] = write
        self.script({"executor": [asked], "advisor": [recommendation]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("executor"), self.calls("advisor")), (1, 1, 1), err)
        entry = self.state(err)["questions"]["W1"]["Q1"]
        self.assertEqual(entry["status"], "open")
        self.assertNotIn("resolution", entry)
        self.assertIn(expected, entry["advice"]["held"])
        self.assertTrue(any(expected in text for text in self.messages(err, "ADVICE_HELD")), err)
        return entry

    def test_a_project_can_add_a_gate_for_other(self):
        self.project_advisor('[orch.advisor]\nhuman_gate_extra = ["other"]\n')
        self.held(advice("question:Q1@1", category="other"), "advisor: category other")

    def test_a_project_empty_extra_does_not_remove_a_machine_gate(self):
        self.configure(ENABLED + 'human_gate_extra = ["other"]\n')
        self.project_advisor('[orch.advisor]\nhuman_gate_extra = []\n')
        self.held(advice("question:Q1@1", category="other"), "advisor: category other")

    def test_a_project_unset_extra_does_not_remove_a_machine_gate(self):
        self.configure(ENABLED + 'human_gate_extra = ["other"]\n')
        self.project_advisor('[orch]\n_unset = ["advisor.human_gate_extra"]\n')
        self.held(advice("question:Q1@1", category="other"), "advisor: category other")

    def test_low_confidence_is_held_even_with_an_empty_gate(self):
        self.configure(ENABLED + "human_gate = []\n")
        self.held(advice("question:Q1@1", confidence="low"),
                  "confidence low is below orch.advisor.min_confidence medium")

    def test_a_project_low_threshold_cannot_weaken_machine_high(self):
        self.configure(ENABLED + 'human_gate = []\nmin_confidence = "high"\n')
        self.project_advisor('[orch.advisor]\nmin_confidence = "low"\n')
        self.held(advice("question:Q1@1", confidence="medium"),
                  "confidence medium is below orch.advisor.min_confidence high")

    def test_a_security_path_overrules_the_models_other_category(self):
        self.set_items({"W1": {"write_set": ["out/W1.txt", "src/auth/check.py"]}})
        self.held(advice("question:Q1@1", category="other"), "code: security (src/auth/check.py)",
                  {"src/auth/check.py": "changed\n"})

    def test_a_public_api_in_the_write_set_is_held_before_it_changes(self):
        self.set_items({"W1": {"write_set": ["out/W1.txt", "src/cli.py"]}})
        self.held(advice("question:Q1@1", category="other"), "code: public-api (src/cli.py)")

    def test_automatic_advice_records_code_categories_even_when_the_gate_is_empty(self):
        self.configure(ENABLED + "human_gate = []\n")
        self.set_items({"W1": {"write_set": ["out/W1.txt", "src/auth/check.py"]}})
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")],
                     "advisor": [advice("question:Q1@1", confidence="medium")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.state(err)["questions"]["W1"]["Q1"]["resolution"]["authority"], {
            "mode": "advisor", "gate": [], "code_categories": ["security"], "confidence": "medium"})

    def test_a_path_outside_the_write_set_is_held(self):
        self.held(advice("question:Q1@1", category="other"), "code: scope-expansion (out/extra.txt)",
                  {"out/extra.txt": "changed\n"})


class GateReadingTests(unittest.TestCase):
    def conductor(self, gate, changed=(), write_set=(), outside=(), patterns=None, minimum="medium"):
        return SimpleNamespace(settings=SimpleNamespace(conductor={"risk": {"patterns": patterns or {}}}),
                               _advisor_cfg=lambda: {"human_gate": gate, "min_confidence": minimum},
                               _changed=lambda item: list(changed), _outside=lambda item: list(outside),
                               progress=mock.Mock()), SimpleNamespace(ref="W1", input_doc={"scope": {"write_set": list(write_set)}})

    def test_code_categories_use_the_configured_patterns_independently_of_weights(self):
        conductor, item = self.conductor(["security", "public-api", "scope-expansion"],
                                        changed=["custom/protected.py", "custom/schema.json", "extra.py"],
                                        write_set=["custom/command.py"], outside=["extra.py"],
                                        patterns={"security": ["custom/protected.py"], "schema": ["custom/schema.json"],
                                                  "public_cli": ["custom/command.py"]})
        self.assertEqual(advice_stage.code_categories(conductor, item), {"security", "public-api", "scope-expansion"})
        _, held = advice_stage.reading(conductor, advice("q", category="other")["result"], item)
        for reason in ("code: security", "code: public-api", "code: scope-expansion"):
            self.assertIn(reason, held)

    def test_confidence_at_the_threshold_passes_and_below_it_is_held(self):
        for threshold, confidence, expected in (("medium", "medium", False), ("high", "high", False),
                                                 ("high", "medium", True), ("medium", "low", True)):
            with self.subTest(threshold=threshold, confidence=confidence):
                conductor, item = self.conductor([], minimum=threshold)
                _, held = advice_stage.reading(conductor, advice("q", confidence=confidence)["result"], item)
                self.assertEqual(bool(held), expected)


class RedChecksTriggerTests(AdvisorCase):
    def red(self):
        return {"result": report("W1")}  # writes nothing: the check stays red

    def test_the_spent_allowance_gets_one_more_correction_round_by_the_advice(self):
        self.script({"executor": [self.red(), self.red(), executor_ok("W1")], "advisor": [advice("checks:2", "keep")],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual((self.calls("executor"), self.calls("advisor")), (3, 1))
        third = self.prompt("executor", 3)
        self.assertIn("These acceptance checks are red", third)
        self.assertIn("# Advice", third)
        self.assertIn("Chosen way: keep — Keep the old flag name (chosen by advisor", third)
        self.assertNotIn("# Advice", self.prompt("executor", 2))
        self.assertIn("## Red acceptance checks", self.prompt("advisor", 1))
        self.assertIn("Keep the old flag name", self.state(err)["items"]["W1"]["advice_fix"]["2"])  # kept for a replay of the round

    def test_advice_that_needs_the_owner_blocks_with_a_question_and_the_owner_choice_makes_the_round(self):
        self.script({"executor": [self.red(), self.red(), executor_ok("W1")],
                     "advisor": [advice("checks:2", needs_owner=True, category="scope-expansion")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        (text,) = [text for text in self.escalations() if text.startswith("QUESTION: orch-advice-1")]
        self.assertIn("recommends keep", text)
        self.assertEqual(self.calls("executor"), 2)
        run = self.run_dir(err).name
        self.assertIn("orch-advice-1", self.conduct("questions", "--run", run)[1])
        self.conduct("answer", "--run", run, "--item", "W1", "--question", "orch-advice-1", "--option", "rename", "--by", "owner")
        self.reopen()
        code, _, err2 = self.conduct("resume", "--run", run, "--retry", "W1", "--json-lines")
        self.assertEqual(code, 0, err2)
        self.assertEqual((code, self.outcome(err2)), (0, ("finished", None)), err2)
        self.assertEqual(self.calls("advisor"), 1)
        self.assertIn("Chosen way: rename — Rename the flag (chosen by owner", self.prompt("executor", 3))

    def test_without_the_advisor_the_red_checks_block_as_before(self):
        self.configure("")
        self.script({"executor": [self.red(), self.red()]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("advisor"), self.calls("executor")), (1, 0, 2), err)
        self.assertIn("CHECKS_RED", self.source()["items"]["W1"]["report"]["open_issues"][-1]["text"])

    def test_max_rounds_zero_blocks_the_red_checks_without_advice(self):
        self.configure("[orch.advisor]\nenabled = true\nmax_rounds = 0\n")
        self.script({"executor": [self.red(), self.red()]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("advisor")), (1, 0), err)
        self.assertIn("CHECKS_RED", self.source()["items"]["W1"]["report"]["open_issues"][-1]["text"])

    def test_advice_does_not_loop_past_max_rounds(self):
        self.script({"executor": [self.red()] * 4, "advisor": [advice("checks:2"), advice("checks:3"), advice("checks:4")]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("advisor"), self.calls("executor")), (1, 2, 4), err)
        self.assertIn("CHECKS_RED", self.source()["items"]["W1"]["report"]["open_issues"][-1]["text"])


class RejectedFindingTriggerTests(AdvisorCase):
    REPRO = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}

    def setUp(self):
        super().setUp()
        patcher = reproduced(0)  # the rerun of a rejection sees the exit the triager reported
        patcher.start()
        self.addCleanup(patcher.stop)

    def rejecting(self) -> dict:
        return {"result": {"confirmed": [], "rejected": [
            {"finding": "F1", "reason": "the file is as the input says", "reproduction": self.REPRO}]}}

    def confirming(self) -> dict:
        return {"result": {"confirmed": [{"finding": "F1", "reproduction": self.REPRO, "fix": "write done"}],
                           "rejected": []}}

    def test_a_rejected_major_finding_is_triaged_again_with_the_advice(self):
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [FINDING, GREEN], "triager": [self.rejecting(), self.confirming()],
                     "advisor": [advice("findings:1", "confirm", options=[
                         {"id": "confirm", "text": "Confirm F1", "pros": ["the reviewer is right"], "cons": []},
                         {"id": "keep-rejection", "text": "Keep the rejection", "pros": [], "cons": ["a real defect stays"]}])]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual((self.calls("triager"), self.calls("advisor"), self.calls("executor")), (2, 1, 2))
        self.assertNotIn("## Advice", self.prompt("triager", 1))
        again = self.prompt("triager", 2)
        self.assertIn("## Advice", again)
        self.assertIn("Chosen way: confirm — Confirm F1 (chosen by advisor", again)
        self.assertIn("reproduced: `cat out/W1.txt`", self.prompt("executor", 2))  # the repeated triage stands for the round
        self.assertIn("## Triage of the findings", self.prompt("advisor", 1))
        verdict = json.loads((self.project / "plans/T/artifacts/W1/review-verdict.json").read_text())
        self.assertEqual(verdict["rounds"][0]["triage"]["confirmed"], ["F1"])
        stages = [line["stage"] for line in self.lines(err) if line["event"] == "stage.end"]
        self.assertIn("triage.1-a", stages)

    def test_a_minor_rejection_is_not_a_disagreement_worth_advice(self):
        minor = {"result": {"verdict": "ATTENTION", "findings": [dict(FINDING["result"]["findings"][0], severity="Minor")]}}
        self.script({"executor": [executor_ok("W1")], "reviewer": [minor],
                     "triager": [{"result": {"confirmed": [], "rejected": [{"finding": "F1", "reason": "not a defect"}]}}]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("advisor")), (0, 0), err)

    def test_advice_that_needs_the_owner_blocks_the_piece_with_a_question(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [FINDING], "triager": [self.rejecting()],
                     "advisor": [advice("findings:1", needs_owner=True, category="destructive")]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertTrue([text for text in self.escalations() if text.startswith("QUESTION: orch-advice-1")])
        self.assertEqual(self.calls("triager"), 1)

    def test_the_owner_choice_is_applied_to_the_repeated_triage_after_the_resume(self):
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [FINDING, GREEN], "triager": [self.rejecting(), self.confirming()],
                     "advisor": [advice("findings:1", needs_owner=True)]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        run = self.run_dir(err).name
        self.conduct("answer", "--run", run, "--item", "W1", "--question", "orch-advice-1", "--option", "rename", "--by", "owner")
        self.reopen()
        code, _, err2 = self.conduct("resume", "--run", run, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(err2)), (0, ("finished", None)), err2)
        self.assertEqual((self.calls("advisor"), self.calls("reviewer"), self.calls("triager")), (1, 2, 2))
        self.assertIn("Chosen way: rename — Rename the flag (chosen by owner", self.prompt("triager", 2))

    def test_without_the_advisor_the_rejection_stands(self):
        self.configure("")
        self.script({"executor": [executor_ok("W1")], "reviewer": [FINDING], "triager": [self.rejecting()]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("advisor"), self.calls("triager")), (0, 0, 1), err)


class ContractAndConfigTests(unittest.TestCase):
    def test_the_recommendation_must_be_an_option_and_the_problem_the_one_asked(self):
        doc = advice("question:Q1@1")["result"]
        self.assertEqual(contract.advice_problems("question:Q1@1", doc), [])
        self.assertEqual(len(contract.advice_problems("question:Q2@1", doc)), 1)
        self.assertEqual(len(contract.advice_problems("question:Q1@1", dict(doc, recommendation="nope"))), 1)
        doc["options"].append(dict(doc["options"][0]))
        self.assertIn("/options: id keep repeats", contract.advice_problems("question:Q1@1", doc))

    def test_the_advice_is_a_contract_kind_with_its_own_result_text(self):
        self.assertIn("advice", contract.KINDS)
        self.assertEqual(prompts.RESULT_KINDS["advisor"], "advice")
        self.assertIn("```advice", prompts.CONTRACT_TEXT["advice"])

    def test_advice_texts_say_who_chose_and_do_not_widen_the_scope(self):
        doc = advice("checks:2")["result"]
        option = doc["options"][0]
        text = prompts.advice_correction(doc, option, by="owner", problem="red")
        self.assertIn("chosen by owner", text)
        self.assertIn("does not widen `scope.write_set`", text)
        self.assertIn("Sources: README.md", text)

    def test_the_defaults_of_orch_advisor(self):
        found = settings.defaults().advisor
        self.assertEqual(found, {"enabled": False, "max_rounds": 2,
                                 "human_gate": ["destructive", "public-api", "scope-expansion", "security"],
                                 "min_confidence": "medium"})

    def test_questions_advisor_is_a_value_of_the_config(self):
        schema = json.loads((engine.ORCH_ROOT / "configs" / "config.schema.json").read_text())
        self.assertIn("advisor", schema["properties"]["conductor"]["properties"]["questions"]["enum"])


if __name__ == "__main__":
    unittest.main()
