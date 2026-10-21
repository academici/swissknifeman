"""Questions of the executor as saved decisions (P6.4, D11): queue, deny, defaults, answer, resume and the binding."""
from __future__ import annotations

import json
import copy
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from orch.contracts import REQUIRED_PART
from orch.conductor import contract, engine, prompts, questions
from orch.conductor.stages.execute import answer_digest
from orch.conductor.infrastructure.files import write_json
from tests.test_conductor import GREEN, ConductorCase, executor_ok, report

ASK = {"id": "Q1", "revision": 1, "kind": "decision", "text": "Keep the old flag name?",
       "options": [{"id": "keep", "label": "keep"}, {"id": "rename", "label": "rename"}], "blocking": True}


class ConcurrentQuestionsTests(unittest.TestCase):
    def test_an_owner_answer_survives_a_denial_computed_before_the_file_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            store = {}
            questions.record(store, [ASK], {"run": "cnd-one", "item": "W1", "step": "executor.1"}, "t")
            questions.save(directory, "cnd-one", "W1", store)
            store["Q1"]["status"] = "denied"
            questions.answer_file(directory, "Q1", option="rename", by="owner", now="t")
            questions.save(directory, "cnd-one", "W1", store)
            saved = questions.read(directory)["questions"][0]
            self.assertEqual(("answered", "rename", "owner"),
                             (saved["status"], saved.get("resolution", {}).get("value"),
                              saved.get("resolution", {}).get("by")))

    def test_an_owner_answer_wins_over_a_default_computed_before_the_file_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            store = {}
            questions.record(store, [dict(ASK, default="keep")], {"run": "cnd-one", "item": "W1", "step": "executor.1"}, "t")
            questions.save(directory, "cnd-one", "W1", store)
            questions.resolve_default(store["Q1"], "t")
            questions.answer_file(directory, "Q1", option="rename", by="owner", now="t")
            questions.save(directory, "cnd-one", "W1", store)
            saved = questions.read(directory)["questions"][0]
            self.assertEqual(("answered", "rename", "owner"),
                             (saved["status"], saved["resolution"]["value"], saved["resolution"]["by"]))
            questions.apply(store, None, "part", "t")
            questions.record(store, [dict(ASK, default="keep")],
                             {"run": "cnd-one", "item": "W1", "step": "executor.2"}, "t")
            self.assertEqual("applied", store["Q1"]["status"])
            self.assertEqual("rename", questions.answers_text(store)[0]["answer"])

    def test_answer_and_conductor_save_preserve_both_answers(self):
        root = Path(__file__).resolve().parents[1]
        bootstrap = "import sys; sys.path[:0]=" + repr([str(root / "lib"), str(root.parent / "aicore/lib")]) + "; "
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            store = {}
            questions.record(store, [ASK, dict(ASK, id="Q2")], {"run": "cnd-one", "item": "W1", "step": "executor.1"}, "t")
            stale = copy.deepcopy(store)
            write_json(questions.path(directory), questions.document("cnd-one", "W1", store))
            script = '''
from pathlib import Path
from orch.conductor import questions
from orch.conductor.infrastructure.lease import questions_lock
p=Path(sys.argv[1])
print('ready',flush=True)
sys.stdin.readline()
questions.answer_file(p,sys.argv[2],option='rename',by='owner',now='t')
print('answered',flush=True)
'''
            children = [subprocess.Popen([sys.executable, "-I", "-u", "-c", bootstrap + script, str(directory), name],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        for name in ("Q1", "Q2")]
            try:
                with questions.questions_lock(directory):
                    for child in children:
                        self.assertTrue(select.select([child.stdout], [], [], 10)[0])
                        self.assertEqual("ready", child.stdout.readline().strip())
                        child.stdin.write("go\n")
                        child.stdin.flush()
                for child in children:
                    out, err = child.communicate(timeout=15)
                    self.assertEqual(0, child.returncode, err)
                    self.assertEqual("answered", out.strip())
                # This state was read before either answer: saving it must merge the resolutions under the same lock.
                questions.save(directory, "cnd-one", "W1", stale)
                saved = questions.read(directory)["questions"]
                self.assertEqual(["rename", "rename"], [row["resolution"]["value"] for row in saved])
                self.assertEqual(["answered", "answered"], [row["status"] for row in saved])
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                    child.communicate(timeout=10)


def asking(*asked, status="blocked", **extra) -> dict:
    issues = [{"text": "needs an answer from the owner", "kind": "escalation"}] if status == "blocked" else []
    return {"result": report("W1", status, changed_paths=[], checks_run=[], open_issues=issues,
                             questions=list(asked), **extra)}


class QuestionTests(ConductorCase):
    def blocked_run(self, **question) -> tuple:
        self.script({"executor": [asking(dict(ASK, **question)), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        return err, self.run_dir(err)

    def reopen(self) -> None:
        doc = self.source()
        doc["items"]["W1"]["status"] = "todo"  # the source reopened the piece
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")

    def test_a_blocking_question_blocks_the_piece_and_is_saved_with_its_binding(self):
        err, directory = self.blocked_run()
        item = self.source()["items"]["W1"]
        self.assertEqual(item["status"], "blocked")
        texts = [issue["text"] for issue in item["report"]["open_issues"]]
        self.assertIn("QUESTION: Q1 Keep the old flag name?", texts)
        self.assertNotIn("questions", item["report"])  # the register body is the closed report fields only
        saved = json.loads((directory / "W1" / questions.FILE).read_text())
        entry = saved["questions"][0]
        self.assertEqual((saved["run"], saved["item"], entry["id"], entry["status"], entry["revision"]),
                         (directory.name, "W1", "Q1", "open", 1))
        input_doc = json.loads((directory / "W1" / "input.json").read_text())
        self.assertEqual(entry["binding"], {"run": directory.name, "item": "W1", "step": "executor.1",
                                             "input_digest": input_doc["digest"],
                                             "input_part_digest": answer_digest(input_doc)})
        self.assertEqual(self.state(err)["questions"]["W1"]["Q1"]["status"], "open")
        self.assertEqual(self.calls("reviewer"), 0)
        self.assertTrue([line for line in self.lines(err) if line.get("reason_code") == "QUESTION_QUEUED"])
        for line in self.lines(err):
            self.assertEqual(contract.problems(line, "progress-line"), [], line)

    def test_answer_and_resume_finish_the_piece_and_the_executor_sees_the_answer(self):
        err, directory = self.blocked_run()
        run = directory.name
        code, out, _ = self.conduct("questions", "--run", run, "--json")
        listed = json.loads(out)["questions"]
        self.assertEqual((code, [(row["item"], row["id"], row["overdue"]) for row in listed]), (0, [("W1", "Q1", False)]))
        code, out, _ = self.conduct("answer", "--run", run, "--item", "W1", "--question", "Q1", "--option", "rename",
                                    "--by", "owner")
        self.assertEqual(code, 0, out)
        resolution = json.loads(out)["resolution"]
        self.assertEqual((resolution["value"], resolution["by"]), ("rename", "owner"))
        self.reopen()
        code, _, err2 = self.conduct("resume", "--run", run, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(err2)), (0, ("finished", None)), err2)
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")
        prompt = self.prompt("executor", 2)
        self.assertIn("\n# Answers\n\n", prompt)
        self.assertIn("Keep the old flag name?", prompt)
        self.assertIn("Answer: rename (by owner)", prompt)
        self.assertNotIn("\n# Answers\n", self.prompt("executor", 1))
        self.assertEqual(self.state(err2)["questions"]["W1"]["Q1"]["status"], "applied")
        self.assertEqual(self.conduct("questions", "--run", run)[1].strip(), "no open questions")

    def test_a_changed_input_makes_the_answer_stale_and_the_question_is_asked_again(self):
        err, directory = self.blocked_run()
        run = directory.name
        self.conduct("answer", "--run", run, "--item", "W1", "--question", "Q1", "--option", "keep")
        doc = self.source()  # the plan was amended: the brief has another digest
        doc["items"]["W1"]["status"] = "todo"
        doc["items"]["W1"]["checks"][0]["cmd"] = "test -s out/W1.txt"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        self.script({"executor": [asking(dict(ASK)), asking(dict(ASK)), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err2 = self.conduct("resume", "--run", run, "--retry", "W1", "--json-lines")
        stale = [line for line in self.lines(err2) if line.get("reason_code") == "QUESTION_STALE"]
        self.assertEqual(len(stale), 1, err2)
        self.assertIn("revision 2", stale[0]["message"])
        self.assertEqual(code, 1)  # the executor asked again: blocked again
        entry = self.state(err2)["questions"]["W1"]["Q1"]
        self.assertEqual((entry["status"], entry["revision"]), ("open", 2))
        self.assertNotIn("resolution", entry)
        self.assertEqual(entry["stale_resolution"]["value"], "keep")
        self.assertNotIn("\n# Answers\n", self.prompt("executor", 2))

    def test_context_changes_preserve_the_answer_on_retry(self):
        input_doc = json.loads(Path(os.environ["FAKE_CS_INPUT"]).read_text())
        source_input = self.project.parent / "source-input.json"
        source_input.write_text(json.dumps(input_doc))
        with mock.patch.dict(os.environ, {"FAKE_CS_INPUT": str(source_input)}):
            err, directory = self.blocked_run()
            original = json.loads((directory / "W1/input.json").read_text())
            questions.answer_file(directory / "W1", "Q1", option="rename", by="owner", now="2026-10-22T00:00:00Z")
            input_doc["provenance"]["source_digest"] = "b" * 64
            input_doc["lessons"] = [{"type": "note", "summary": "The blocked outcome was registered.",
                                     "ts": "2026-10-22T00:00:00Z"}]
            source_input.write_text(json.dumps(input_doc))
            self.reopen()
            code, _, resumed = self.conduct("resume", "--run", directory.name, "--retry", "W1", "--json-lines")
        current = json.loads((directory / "W1/input.json").read_text())
        self.assertNotEqual(original["digest"], current["digest"])
        self.assertEqual(answer_digest(original), answer_digest(current))
        self.assertEqual((code, self.outcome(resumed)), (0, ("finished", None)), resumed)
        codes = [line.get("reason_code") for line in self.lines(resumed)]
        self.assertIn("QUESTION_ANSWERED", codes)
        self.assertNotIn("QUESTION_STALE", codes)
        self.assertIn("Answer: rename (by owner)", self.prompt("executor", 2))

    def test_resume_without_retry_stops_for_a_persisted_owner_answer(self):
        _, directory = self.blocked_run()
        questions.answer_file(directory / "W1", "Q1", option="rename", by="owner", now="2026-10-22T00:00:00Z")
        saved = questions.read(directory / "W1")["questions"][0]
        self.assertEqual(saved["status"], "open")  # the real answer command leaves consumption to resume --retry
        code, _, resumed = self.conduct("resume", "--run", directory.name, "--json-lines")
        self.assertEqual((code, self.outcome(resumed)), (1, ("stopped", "QUESTION_ANSWERED_NOT_RETRIED")), resumed)
        state = self.state(resumed)
        self.assertEqual(state["stop"]["code"], "QUESTION_ANSWERED_NOT_RETRIED")
        beacons = [line for line in self.lines(resumed) if line["event"] == "info"
                   and line.get("reason_code") == "QUESTION_ANSWERED_NOT_RETRIED"]
        self.assertEqual(len(beacons), 1)
        self.assertIn(f"orch conduct resume --run {directory.name} --retry W1", beacons[0]["message"])
        self.assertEqual(self.calls("executor"), 1)
        self.assertEqual(questions.read(directory / "W1")["questions"][0], saved)
        # Older writers may have persisted the intermediate answered status instead.
        document = questions.read(directory / "W1")
        document["questions"][0]["status"] = "answered"
        write_json(questions.path(directory / "W1"), document)
        code, _, legacy = self.conduct("resume", "--run", directory.name, "--json-lines")
        self.assertEqual((code, self.outcome(legacy)), (1, ("stopped", "QUESTION_ANSWERED_NOT_RETRIED")), legacy)
        self.reopen()
        code, _, retried = self.conduct("resume", "--run", directory.name, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(retried)), (0, ("finished", None)), retried)
        self.assertIn("Answer: rename (by owner)", self.prompt("executor", 2))

    def test_legacy_binding_survives_save_load_and_resume(self):
        _, directory = self.blocked_run()
        state_path = directory / engine.STATE_FILE
        state = json.loads(state_path.read_text())
        state["questions"]["W1"]["Q1"]["binding"].pop("input_part_digest")
        write_json(state_path, state)
        document = questions.read(directory / "W1")
        document["questions"][0]["binding"].pop("input_part_digest")
        write_json(questions.path(directory / "W1"), document)
        questions.answer_file(directory / "W1", "Q1", option="keep", by="owner", now="2026-10-22T00:00:00Z")
        self.reopen()
        code, _, resumed = self.conduct("resume", "--run", directory.name, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(resumed)), (0, ("finished", None)), resumed)
        self.assertIn("Answer: keep (by owner)", self.prompt("executor", 2))

    def test_an_answer_waiting_for_retry_is_only_a_beacon_when_other_work_starts(self):
        self.set_items({"W1": {}, "W2": {}})
        self.script({"executor": [asking(dict(ASK)), executor_ok("W2")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", "W2", extra=("--no-batch",))
        self.assertEqual(code, 1, err)
        directory = self.run_dir(err)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "keep blocked fixture records before other work")
        questions.answer_file(directory / "W1", "Q1", option="rename", by="owner", now="2026-10-22T00:00:00Z")
        code, _, resumed = self.conduct("resume", "--run", directory.name, "--json-lines")
        self.assertEqual((code, self.outcome(resumed)), (0, ("finished", None)), resumed)
        self.assertTrue(any(line.get("reason_code") == "QUESTION_ANSWERED_NOT_RETRIED" for line in self.lines(resumed)))
        self.assertEqual(self.source()["items"]["W2"]["status"], "done")

    def test_an_answer_needs_an_open_question_and_a_valid_option(self):
        err, directory = self.blocked_run()
        run = directory.name
        base = ["answer", "--run", run, "--item", "W1"]
        code, _, text = self.conduct(*base, "--question", "Q9", "--text", "x")
        self.assertEqual(code, 1)
        self.assertIn("QUESTION_UNKNOWN", text)
        code, _, text = self.conduct(*base, "--question", "Q1", "--option", "nope")
        self.assertEqual(code, 1)
        self.assertIn("ANSWER_INVALID", text)
        code, _, text = self.conduct(*base, "--question", "Q1", "--text", "free")
        self.assertEqual(code, 1)  # a decision with options takes one of them
        self.assertIn("ANSWER_INVALID", text)

    def test_an_answer_that_looks_like_a_secret_is_refused(self):
        from orch.conductor import questions as questions_mod
        doc = {"item": "W1", "questions": [{"id": "Q1", "revision": 1, "kind": "credential", "text": "token?",
                                            "blocking": True, "status": "open"}]}
        with self.assertRaises(questions_mod.QuestionError) as caught:
            questions_mod.answer(doc, "Q1", text="use ghp_" + "a" * 36, by="owner", now="t")
        self.assertEqual(caught.exception.code, "ANSWER_INVALID")
        self.assertNotIn("resolution", doc["questions"][0])
        entry = questions_mod.answer(doc, "Q1", text="it is in the env var GH_TOKEN", by="owner", now="t")
        self.assertEqual(entry["resolution"]["value"], "it is in the env var GH_TOKEN")

    def test_deny_blocks_without_waiting_for_an_answer(self):
        self.write_config(extra='[orch.conductor]\nquestions = "deny"')
        self.script({"executor": [asking(dict(ASK))]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        texts = [issue["text"] for issue in self.source()["items"]["W1"]["report"]["open_issues"]]
        self.assertIn("QUESTION_DENIED: Q1 Keep the old flag name?", texts)
        self.assertEqual(self.state(err)["questions"]["W1"]["Q1"]["status"], "denied")
        self.assertEqual(self.conduct("questions", "--run", self.run_dir(err).name)[1].strip(), "no open questions")

    def test_defaults_answers_once_by_policy_and_the_round_is_repeated(self):
        self.write_config(extra='[orch.conductor]\nquestions = "defaults"')
        self.script({"executor": [asking(dict(ASK, default="keep")), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertIn("Answer: keep (by policy)", self.prompt("executor", 2))
        stages = [line["stage"] for line in self.lines(err) if line["event"] == "stage.start"]
        self.assertIn("executor.1-q1", stages)
        entry = self.state(err)["questions"]["W1"]["Q1"]
        self.assertEqual((entry["status"], entry["resolution"]["by"]), ("applied", "policy"))
        self.assertEqual(entry["resolution"]["authority"], {
            "mode": "defaults", "gate": ["destructive", "public-api", "scope-expansion", "security"],
            "code_categories": [], "confidence": None})
        saved = questions.read(self.run_dir(err) / "W1")["questions"][0]
        self.assertEqual(saved["resolution"]["authority"], entry["resolution"]["authority"])

    def test_approval_and_credential_are_owner_only_in_every_question_mode(self):
        for mode in ("queue", "deny", "defaults", "advisor"):
            for kind in ("approval", "credential"):
                with self.subTest(mode=mode, kind=kind):
                    # Each run has its own item: no reopen or reused policy answer can hide a resolution.
                    self.set_items({"W1": {}})
                    self.write_config(extra=f'[orch.conductor]\nquestions = "{mode}"\n')
                    self.script({"executor": [asking(dict(ASK, kind=kind, default="keep"))]})
                    code, _, err = self.run_items("W1")
                    self.assertEqual(code, 1, err)
                    entry = self.state(err)["questions"]["W1"]["Q1"]
                    self.assertEqual(entry["status"], "open")
                    self.assertNotIn("resolution", entry)
                    self.assertTrue(any(line.get("reason_code") == "QUESTION_OWNER_ONLY" for line in self.lines(err)), err)
                    self.assertEqual(self.calls("advisor"), 0)
                    # The artifact file is evidence committed by a later successful run; keep this fixture clean.
                    self.git("add", "-A")
                    self.git("commit", "-q", "--allow-empty", "-m", "question fixture")

    def test_resolve_default_never_answers_owner_only_kinds(self):
        for kind in ("approval", "credential"):
            entry = dict(ASK, kind=kind, default="keep", status="open")
            before = copy.deepcopy(entry)
            self.assertFalse(questions.resolve_default(entry, "t"))
            self.assertEqual(entry, before)

    def test_defaults_record_the_effective_gate_and_code_categories(self):
        self.write_config(extra='[orch.conductor]\nquestions = "defaults"\n'
                                '[orch.advisor]\nhuman_gate_extra = ["other"]\n')
        self.set_items({"W1": {"write_set": ["out/W1.txt", "src/auth/check.py"]}})
        self.script({"executor": [asking(dict(ASK, default="keep")), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.state(err)["questions"]["W1"]["Q1"]["resolution"]["authority"], {
            "mode": "defaults", "gate": ["destructive", "other", "public-api", "scope-expansion", "security"],
            "code_categories": ["security"], "confidence": None})

    def test_defaults_answers_a_question_only_once(self):
        self.write_config(extra='[orch.conductor]\nquestions = "defaults"')
        again = asking(dict(ASK, default="keep"))
        self.script({"executor": [again, again, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual(self.calls("executor"), 2)  # not a third time
        self.assertEqual(self.state(err)["questions"]["W1"]["Q1"]["status"], "open")  # it waits for a person now

    def test_a_question_the_executor_asks_again_after_the_policy_answered_it_is_queued(self):  # review F1
        self.write_config(extra='[orch.conductor]\nquestions = "defaults"')
        again = asking(dict(ASK, default="keep"))
        self.script({"executor": [again, again, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("executor")), (1, 2), err)
        entry = self.state(err)["questions"]["W1"]["Q1"]
        self.assertEqual((entry["status"], entry["stale_resolution"]["by"]), ("open", "policy"))
        run = self.run_dir(err).name
        self.assertIn("W1 Q1", self.conduct("questions", "--run", run)[1])
        self.assertEqual(self.conduct("answer", "--run", run, "--item", "W1", "--question", "Q1", "--option", "rename")[0], 0)

    def test_a_retry_after_a_policy_round_goes_on_from_the_round_that_stopped(self):  # review F2
        self.write_config(extra='[orch.conductor]\nquestions = "defaults"')
        second = asking(dict(ASK, id="Q2", text="Which name?"))
        self.script({"executor": [asking(dict(ASK, default="keep")), second, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("executor")), (1, 2), err)
        run = self.run_dir(err).name
        self.conduct("answer", "--run", run, "--item", "W1", "--question", "Q2", "--option", "rename")
        self.reopen()
        code, _, err2 = self.conduct("resume", "--run", run, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.calls("executor")), (0, 3), err2)  # not a fourth: executor.1 was not repeated
        started = [line["stage"] for line in self.lines(err2) if line["event"] == "stage.start"]
        self.assertIn("executor.1-q1", started)
        self.assertNotIn("executor.1", started)
        self.assertIn("Answer: rename (by", self.prompt("executor", 3))

    def test_an_answered_question_is_not_overdue(self):  # review F5
        err, directory = self.blocked_run()
        self.conduct("answer", "--run", directory.name, "--item", "W1", "--question", "Q1", "--option", "keep")
        file = directory / "W1" / questions.FILE
        saved = json.loads(file.read_text())
        saved["questions"][0]["asked_at"] = "2020-01-01T00:00:00Z"
        file.write_text(json.dumps(saved))
        row = questions.listing(directory, 2_000_000_000)[0]
        self.assertEqual((row["answered"], row["overdue"]), (True, False))

    def test_defaults_without_a_default_queue_the_question(self):
        self.write_config(extra='[orch.conductor]\nquestions = "defaults"')
        self.script({"executor": [asking(dict(ASK))]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("executor")), (1, 1), err)
        self.assertEqual(self.state(err)["questions"]["W1"]["Q1"]["status"], "open")

    def test_a_question_that_does_not_block_is_an_assumption_and_the_work_goes_on(self):
        soft = {"id": "Q2", "revision": 1, "kind": "clarification", "text": "Which timeout?", "blocking": False,
                "assumed": "30", "risk": "low"}
        answer = executor_ok("W1")
        answer["result"] = dict(answer["result"], questions=[soft])
        self.script({"executor": [answer], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        issues = self.source()["items"]["W1"]["report"]["open_issues"]
        self.assertEqual([(issue["kind"], issue["text"]) for issue in issues],
                         [("assumption", "question Q2: Which timeout? — assumed: 30")])
        self.assertEqual(self.state(err)["questions"]["W1"]["Q2"]["status"], "assumed")

    def test_a_blocking_question_in_a_report_that_is_not_blocked_is_repaired_or_repeated(self):
        wrong = executor_ok("W1")
        wrong["result"] = dict(wrong["result"], questions=[dict(ASK)])
        self.script({"executor": [wrong, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.calls("executor")), (0, 2), err)

    def test_the_overdue_question_is_marked_by_questions_and_the_observer(self):
        err, directory = self.blocked_run()
        options = directory / "W1" / "options.json"
        doc = json.loads(options.read_text())
        doc["options"]["limits"]["question_warn_s"] = 1
        options.write_text(json.dumps(doc))
        file = directory / "W1" / questions.FILE
        saved = json.loads(file.read_text())
        saved["questions"][0]["asked_at"] = "2020-01-01T00:00:00Z"
        file.write_text(json.dumps(saved))
        code, out, _ = self.conduct("questions", "--run", directory.name)
        self.assertIn("OVERDUE", out)
        self.assertEqual(code, 0)
        from orch.conductor import observer
        built = observer.build(directory, self.project)
        self.assertTrue(built["open_questions"][0]["overdue"])
        self.assertTrue([text for text in built["proposals"] if "question_warn_s" in text])
        self.assertIn("## Open questions", observer.markdown(built))


class PromptAndContractTests(unittest.TestCase):
    def test_the_stage_report_text_tells_when_to_ask(self):
        text = prompts.CONTRACT_TEXT["stage-report"]
        self.assertIn("`questions`", text)
        self.assertIn("blocking", text)

    def test_the_answers_section_lists_each_answer_and_who_gave_it(self):
        section = prompts._answers([{"id": "Q1", "text": "Which?", "answer": "a", "by": "owner"},
                                    {"id": "Q2", "text": "How many?", "answer": {"n": 3}, "by": "policy"}])
        self.assertTrue(section.startswith("# Answers"))
        self.assertIn('Answer: {"n": 3} (by policy)', section)

    def test_report_problems_name_a_blocking_question_in_a_done_report_and_repeated_ids(self):
        doc = report("W1", questions=[dict(ASK), dict(ASK)])
        found = engine.report_problems(doc)
        self.assertTrue([text for text in found if "blocking question" in text])
        self.assertTrue([text for text in found if "repeats" in text])

    def test_binding_pure_functions(self):
        store = {}
        binding = {"run": "r", "item": "W1", "step": "executor.1", "input_digest": "d1"}
        questions.record(store, [dict(ASK)], binding, "2026-10-14T10:00:00Z")
        self.assertEqual(store["Q1"]["status"], "open")
        store["Q1"]["resolution"] = {"value": "keep", "by": "o", "at": "2026-10-14T10:01:00Z"}
        store["Q1"]["status"] = "answered"
        self.assertEqual(questions.apply(store, "d2", "part", "2026-10-14T10:02:00Z"), ([], ["Q1"]))
        self.assertEqual((store["Q1"]["status"], store["Q1"]["revision"]), ("stale", 2))
        # asked again on the new input: the revision never goes back
        questions.record(store, [dict(ASK)], dict(binding, step="executor.1", input_digest="d2"), "2026-10-14T10:03:00Z")
        self.assertEqual((store["Q1"]["status"], store["Q1"]["revision"]), ("open", 2))

    def test_legacy_records_apply_only_when_the_full_digest_matches(self):
        for digest, expected in (("old", (["Q1"], [])), ("new", ([], ["Q1"]))):
            with self.subTest(digest=digest):
                store = {}
                questions.record(store, [ASK], {"step": "executor.1", "input_digest": "old"}, "t")
                store["Q1"].update(status="answered", resolution={"value": "keep", "by": "owner", "at": "t"})
                self.assertEqual(questions.apply(store, digest, "part", "t"), expected)

    def test_every_required_part_invalidates_an_answer(self):
        original = {key: "before" for key in REQUIRED_PART}
        for key in REQUIRED_PART:
            with self.subTest(key=key):
                store = {}
                questions.record(store, [ASK], {"step": "executor.1", "input_digest": "same",
                                                "input_part_digest": answer_digest(original)}, "t")
                store["Q1"].update(status="answered", resolution={"value": "keep", "by": "owner", "at": "t"})
                amended = dict(original, **{key: "after"})
                self.assertEqual(questions.apply(store, "same", answer_digest(amended), "t"), ([], ["Q1"]))


if __name__ == "__main__":
    unittest.main()
