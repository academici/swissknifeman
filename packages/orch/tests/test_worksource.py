"""The work-source port: the plugin client (contract on both sides, unavailable and failing sources) and the cycle
``orch.py source claim|brief|prepare|register`` on a test plugin (run journal, deterministic run ids, events)."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from aicore.ext import events as aicore_events
from aicore.state import blobs

from orch import contracts, journal, worksource
from orch.cli import main, run_id_of, submission_id

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "fixtures" / "work-source" / "fake"
INPUT = ROOT / "fixtures" / "exec" / "v1" / "valid" / "execution-input" / "plan-bound.json"
MODEL_CATALOG = ROOT / "fixtures" / "model-catalog" / "test.json"
ACTOR = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}
CLAIM = {"plan": "P", "run_id": "run-1", "submission_id": "sub-1", "actor": ACTOR}


class SourceCase(unittest.TestCase):
    registered = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.home, self.project = base / "home", base / "project"
        (self.project / ".git").mkdir(parents=True)
        config = self.home / "skm" / "config" / "config.toml"
        config.parent.mkdir(parents=True)
        text = "schema_version = 1\n\n[orch]\nwork_source = \"fake-source\"\n"
        if self.registered:
            text += ("\n[aicore.plugins.fake-source]\n"
                     f"manifest = {json.dumps(str(FAKE / 'extension.json'))}\ntrusted = true\n")
        config.write_text(text, encoding="utf-8")
        self.marks = base / "marks.jsonl"
        self.env = {"HOME": str(self.home), "SKM_HOME": str(self.home / "skm"), "SKM_AICORE_EVENTS__DELIVERY": "off",
                    "FAKE_WS_MODE": "ok", "FAKE_WS_INPUT": str(INPUT), "FAKE_WS_MARKS": str(self.marks)}
        patcher = mock.patch.dict(os.environ, self.env)
        patcher.start()
        self.addCleanup(patcher.stop)
        cwd = Path.cwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, cwd)

    def mode(self, mode: str) -> None:
        os.environ["FAKE_WS_MODE"] = mode

    def source(self) -> worksource.PluginWorkSource:
        return worksource.PluginWorkSource("fake-source", project=self.project)

    def cli(self, *argv) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(item) for item in argv])
        return code, out.getvalue(), err.getvalue()

    def types(self) -> list:
        stored, problems = aicore_events.read_events(self.project)
        self.assertEqual(problems, [])
        return [event.type for event in stored]

    def events(self, event_type: str) -> list:
        return [event for event in aicore_events.read_events(self.project)[0] if event.type == event_type]


class ClientTests(SourceCase):
    def test_a_valid_answer_is_returned(self):
        answer = self.source().claim(**CLAIM)
        self.assertEqual((answer["status"], answer["attempt_id"]), ("claimed", "att-run-1-W1"))

    def test_an_answer_outside_the_contract_is_a_failure_of_the_source(self):
        self.mode("invalid")
        with self.assertRaises(worksource.WorkSourceError) as caught:
            self.source().claim(**CLAIM)
        self.assertEqual(caught.exception.code, "WORK_SOURCE_FAILED")
        self.assertIn("/status", caught.exception.message)

    def test_a_crashing_plugin_is_a_failure_of_the_source(self):
        self.mode("crash")
        with self.assertRaises(worksource.WorkSourceError) as caught:
            self.source().claim(**CLAIM)
        self.assertEqual(caught.exception.code, "WORK_SOURCE_FAILED")

    def test_a_request_outside_the_contract_never_leaves(self):
        with self.assertRaises(worksource.WorkSourceError) as caught:
            self.source().claim(plan="P", run_id="run-1", submission_id="not-a-submission", actor=ACTOR)
        self.assertEqual(caught.exception.code, "INPUT_INVALID")
        self.assertEqual(worksource.problems({"op": "peek"}, "input"), ["/op: must be one of claim, brief, register, commit, release, note, research, decision, readiness"])


class ReadinessTests(SourceCase):
    """The optional operation ``readiness``: the contract on both sides, a source without it, the file source, the CLI
    verb and the conductor helper ``source_readiness``."""

    LANE = {"kind": "run-items", "items": ["W1"], "phase": "P1", "message": None}

    def test_readiness_is_an_operation_of_the_contract(self):
        self.assertIn("readiness", worksource.OPS)
        self.assertEqual(worksource.problems({"op": "readiness", "collection": "P"}, "input"), [])
        self.assertTrue(worksource.problems({"op": "readiness", "collection": "P", "ref": "W1"}, "input"))
        self.assertTrue(worksource.problems({"op": "readiness"}, "input"))
        ok = {"op": "readiness", "outcome": "ok", "phases": [{"id": "P1", "status": "stale", "digest": "sha256:" + "a" * 64}],
              "next": self.LANE}
        self.assertEqual(worksource.problems(ok, "output"), [])
        for spoiled in ({**ok, "phases": [{"id": "P1", "status": "approved", "digest": "sha256:" + "a" * 64}]},
                        {**ok, "phases": [{"id": "P1", "status": "ready", "digest": "a" * 64}]},
                        {**ok, "next": {"kind": "run-items", "items": ["W1"]}}, {**ok, "outcome": "unsupported"}):
            self.assertTrue(worksource.problems(spoiled, "output"), spoiled)

    def test_the_answer_of_the_source_is_returned(self):
        answer = self.source().readiness(collection="P", plans_root="plans")
        self.assertEqual((answer["outcome"], answer["next"]), ("ok", self.LANE))
        (sent,) = [json.loads(line) for line in self.marks.read_text().splitlines()]
        self.assertEqual(sent, {"op": "readiness", "collection": "P", "plans_root": "plans"})

    def test_an_answer_outside_the_contract_is_a_failure_of_the_source(self):
        self.mode("invalid")
        with self.assertRaises(worksource.WorkSourceError) as caught:
            self.source().readiness(collection="P")
        self.assertEqual(caught.exception.code, "WORK_SOURCE_FAILED")
        self.assertIn("/phases/0/status", caught.exception.message)

    def test_a_source_without_the_operation_is_refused_unsupported(self):
        self.mode("no-readiness")
        answer = self.source().readiness(collection="P")
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "READINESS_UNSUPPORTED"))
        self.assertIn("OP_UNSUPPORTED", answer["message"])
        self.assertEqual(worksource.problems(answer, "output"), [])
        self.mode("crash")  # a crash is not "unsupported"
        with self.assertRaises(worksource.WorkSourceError) as caught:
            self.source().readiness(collection="P")
        self.assertEqual(caught.exception.code, "WORK_SOURCE_FAILED")

    def test_the_file_source_refuses_readiness(self):
        from orch.worksource_file import FileWorkSource
        answer = FileWorkSource(INPUT, project=self.project).readiness(collection=str(INPUT))
        self.assertEqual((answer["op"], answer["outcome"], answer["reason_code"]),
                         ("readiness", "refused", "READINESS_UNSUPPORTED"))
        code, out, err = self.cli("source", "readiness", "--input", INPUT)
        self.assertEqual((code, err, json.loads(out)["reason_code"]), (1, "", "READINESS_UNSUPPORTED"))

    def test_the_cli_prints_the_answer_and_writes_no_run(self):
        code, out, err = self.cli("source", "readiness", "--plan", "P", "--plans-root", "plans")
        self.assertEqual((code, err, json.loads(out)["outcome"]), (0, "", "ok"))
        self.mode("no-readiness")
        code, out, _ = self.cli("source", "readiness", "--plan", "P")
        self.assertEqual((code, json.loads(out)["reason_code"]), (1, "READINESS_UNSUPPORTED"))
        self.mode("invalid")
        code, out, err = self.cli("source", "readiness", "--plan", "P")
        self.assertEqual((code, out, err.split(":")[0]), (1, "", "WORK_SOURCE_FAILED"))
        self.assertEqual(self.types(), [])  # read-only: no run, no event

    def owner(self) -> SimpleNamespace:
        from orch.conductor.infrastructure import work_source
        owner = SimpleNamespace(project=self.project, project_resolution=None, config_file=None, env=None)
        owner._orch = lambda *args: work_source.run_orch(owner, *args)
        patcher = mock.patch.object(work_source, "ORCH_TRANSPORT", work_source.inprocess_transport)
        patcher.start()
        self.addCleanup(patcher.stop)
        return owner

    def test_source_readiness_returns_the_checked_answer_and_never_raises(self):
        from orch.conductor.infrastructure import work_source
        owner = self.owner()
        answer = work_source.source_readiness(owner, "P", plans_root="plans")
        self.assertEqual((answer["outcome"], answer["phases"][0]["status"], answer["next"]), ("ok", "ready", self.LANE))
        self.mode("no-readiness")
        self.assertEqual(work_source.source_readiness(owner, "P")["reason_code"], "READINESS_UNSUPPORTED")
        self.mode("invalid")
        answer = work_source.source_readiness(owner, "P")
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "WORK_SOURCE_FAILED"))
        self.assertIn("/phases/0/status", answer["message"])

    def test_source_readiness_refuses_an_ok_without_phases_or_next_and_an_unavailable_source(self):
        from orch.conductor.infrastructure import work_source
        owner = self.owner()
        os.environ["FAKE_WS_READINESS"] = json.dumps({"op": "readiness", "outcome": "ok", "phases": []})
        answer = work_source.source_readiness(owner, "P")
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "WORK_SOURCE_FAILED"))
        self.assertIn("needs phases and next", answer["message"])
        del os.environ["FAKE_WS_READINESS"]
        lost = SimpleNamespace(_orch=lambda *args: (3, None, "WORK_SOURCE_UNAVAILABLE: no work source"))
        self.assertEqual(work_source.source_readiness(lost, "P"),
                         {"op": "readiness", "outcome": "refused", "reason_code": "WORK_SOURCE_UNAVAILABLE",
                          "message": "WORK_SOURCE_UNAVAILABLE: no work source"})
        silent = SimpleNamespace(_orch=lambda *args: (1, None, ""))
        self.assertEqual(work_source.source_readiness(silent, "P")["reason_code"], "WORK_SOURCE_FAILED")

    def test_the_conductor_fake_source_answers_what_the_test_set(self):
        import subprocess
        import sys
        plugin = ROOT / "tests" / "fixtures" / "conductor" / "source" / "plugin.py"
        state_file = Path(self.tmp.name) / "cs-state.json"

        def ask(state: dict) -> dict:
            state_file.write_text(json.dumps(state), encoding="utf-8")
            request = {"protocol": "1", "op": "invoke", "request_id": "r" * 32, "context": {"project_root": str(self.project)},
                       "input": {"op": "readiness", "collection": "T"}}
            done = subprocess.run([sys.executable, str(plugin)], input=json.dumps(request), capture_output=True, text=True,
                                  env={**os.environ, "FAKE_CS_STATE": str(state_file),
                                       "AICORE_ROOT": str(ROOT.parent / "aicore")}, check=True, timeout=60)
            return json.loads(done.stdout)
        items = {"order": ["T1", "T2"], "items": {"T1": {"status": "done"}, "T2": {"status": "todo"}}}
        answer = ask(dict(items))["output"]
        self.assertEqual(worksource.problems(answer, "output"), [])
        self.assertEqual(answer["next"], {"kind": "run-items", "items": ["T2"], "phase": None, "message": None})
        given = {"phases": [{"id": "P1", "status": "missing", "digest": "sha256:" + "b" * 64}],
                 "next": {"kind": "audit-phase", "items": [], "phase": "P1", "message": "readiness missing"}}
        answer = ask({**items, "readiness": given})["output"]
        self.assertEqual((answer["phases"], answer["next"]), (given["phases"], given["next"]))
        self.assertEqual(ask({**items, "no_readiness": True})["error"]["code"], "OP_UNSUPPORTED")
        self.assertEqual(ask({**items, "refuse": ["readiness"]})["output"]["reason_code"], "READINESS_TEST_REFUSAL")


class UnregisteredTests(SourceCase):
    registered = False

    def test_no_registration_is_unavailable(self):
        with self.assertRaises(worksource.WorkSourceError) as caught:
            self.source().claim(**CLAIM)
        self.assertEqual(caught.exception.code, "WORK_SOURCE_UNAVAILABLE")

    def test_the_cli_exits_3_without_a_source(self):
        code, out, err = self.cli("source", "claim", "--plan", "P", "--actor", "claude-code/claude-opus-5-5")
        self.assertEqual((code, out), (3, ""))
        self.assertTrue(err.startswith("WORK_SOURCE_UNAVAILABLE: "), err)


class CycleTests(SourceCase):
    def claim(self, *extra) -> dict:
        code, out, err = self.cli("source", "claim", "--plan", "P", "--actor", "claude-code/claude-opus-5-5/high",
                                  *extra)
        self.assertEqual((code, err), (0, ""), out)
        return json.loads(out)

    def run_dir(self, run_id: str) -> Path:
        return journal.run_dir(run_id, project=self.project)

    def test_release_hands_the_claim_back_and_writes_a_receipt(self):
        run_id = self.claim()["run_id"]
        code, out, err = self.cli("source", "release", "--run", run_id, "--reason", "the tree was dirty")
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(json.loads(out), {"op": "release", "outcome": "released", "message": "the tree was dirty"})
        self.assertEqual(journal.read_doc(self.run_dir(run_id), "receipts/release.json")["outcome"], "released")
        code, _, err = self.cli("source", "release", "--run", "run-unknown")
        self.assertEqual((code, err.split(":")[0]), (1, "RUN_UNKNOWN"))

    def decision_file(self, name: str = "Q1") -> Path:
        path = Path(self.tmp.name) / f"{name.replace('/', '_')}-decision.json"
        path.write_text(json.dumps({
            "question": {"id": name, "revision": 1, "kind": "decision", "text": "Keep?", "options": [{"id": "keep"}]},
            "question_key": "qk-" + "a" * 16, "question_digest": "a" * 64,
            "resolution": {"value": "keep", "by": "owner"}, "authority": "owner", "rationale": "Answered by owner: keep",
            "evidence": ["x/questions.json"]}), encoding="utf-8")
        return path

    def test_decision_goes_to_the_source_with_the_run_and_writes_a_receipt_per_question(self):
        run_id = self.claim()["run_id"]
        code, out, err = self.cli("source", "decision", "--run", run_id, "--ref", "W1", "--file", self.decision_file("Q1"),
                                  "--actor", "orch/conductor")
        self.assertEqual((code, err, json.loads(out)), (0, "", {"op": "decision", "outcome": "recorded", "decision_id": "D1"}))
        sent = [json.loads(line) for line in self.marks.read_text().splitlines() if '"decision"' in line]
        (given,) = sent
        self.assertEqual((given["collection"], given["ref"], given["run_id"], given["attempt_id"], given["actor"]),
                         ("P", "W1", run_id, f"att-{run_id}-W1", {"provider": "orch", "model": "conductor"}))
        self.assertEqual(given["question_key"], "qk-" + "a" * 16)
        self.cli("source", "decision", "--run", run_id, "--file", self.decision_file("esc/2"))
        directory = self.run_dir(run_id)
        self.assertEqual(journal.read_doc(directory, "receipts/decision-Q1.json")["outcome"], "recorded")
        self.assertEqual(journal.read_doc(directory, "receipts/decision-esc-2.json")["outcome"], "recorded")
        self.assertEqual(journal.read_doc(directory, "receipts/decision-Q1-request.json")["parameters"]["ref"], "W1")

    def test_a_source_without_the_decision_operation_answers_unsupported(self):
        run_id = self.claim()["run_id"]
        self.mode("no-decision")
        code, out, err = self.cli("source", "decision", "--run", run_id, "--file", self.decision_file())
        answer = json.loads(out)
        self.assertEqual((code, answer["op"], answer["outcome"]), (1, "decision", "unsupported"), err)
        self.assertIn("OP_UNSUPPORTED", answer["message"])
        self.assertEqual(journal.read_doc(self.run_dir(run_id), "receipts/decision-Q1.json")["outcome"], "unsupported")

    def test_decision_refuses_another_piece_a_request_outside_the_contract_and_an_unknown_run(self):
        run_id = self.claim()["run_id"]
        code, _, err = self.cli("source", "decision", "--run", run_id, "--ref", "W9", "--file", self.decision_file())
        self.assertEqual((code, err.split(":")[0]), (1, "INPUT_INVALID"))
        broken = Path(self.tmp.name) / "broken.json"
        broken.write_text(json.dumps({"question": {"id": "Q1"}}), encoding="utf-8")
        code, _, err = self.cli("source", "decision", "--run", run_id, "--file", broken)
        self.assertEqual((code, err.split(":")[0]), (1, "INPUT_INVALID"))
        code, _, err = self.cli("source", "decision", "--run", "run-unknown", "--file", self.decision_file())
        self.assertEqual((code, err.split(":")[0]), (1, "RUN_UNKNOWN"))

    def test_claim_writes_the_run_and_a_repeat_is_the_same_run(self):
        first = self.claim()
        expected_sub = submission_id("P", [], ACTOR)
        self.assertEqual((first["submission_id"], first["run_id"]), (expected_sub, run_id_of(expected_sub)))
        self.assertTrue(first["run_id"].startswith("run-") and len(first["run_id"]) == 28)
        doc = journal.read_doc(self.run_dir(first["run_id"]), "run.json")
        self.assertEqual(doc, {"run_id": first["run_id"], "submission_id": expected_sub, "plugin": "fake-source",
                               "plan": "P", "plans_root": None, "ref": "W1",
                               "attempt_id": f"att-{first['run_id']}-W1", "scenario": "solo",
                               "session": first["run_id"]})
        self.assertEqual(self.claim(), first)
        self.assertEqual(self.types(), ["orch.run.started"])  # the repeat starts nothing new
        sent = [json.loads(line) for line in self.marks.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([request.get("items") for request in sent], [None, ["W1"]])  # the repeat asks for its item
        started = self.events("orch.run.started")[0]
        self.assertEqual(started.data["source"], {"plugin": "fake-source", "ref": "W1"})
        other = self.claim("--item", "W2")
        self.assertNotEqual(other["run_id"], first["run_id"])
        self.assertEqual(self.claim("--submission-id", "sub-own")["run_id"], run_id_of("sub-own"))

    def test_a_blocked_claim_exits_1_and_is_refused(self):
        self.mode("blocked")
        code, out, _err = self.cli("source", "claim", "--plan", "P", "--actor", "claude-code/claude-opus-5-5")
        self.assertEqual(code, 1)
        answer = json.loads(out)
        self.assertEqual(answer["reason_code"], "ITEM_OWNED")
        self.assertIsNone(journal.read_doc(self.run_dir(answer["run_id"]), "run.json"))
        refused = self.events("orch.run.refused")
        self.assertEqual([(e.data["step"], e.data["reason_codes"]) for e in refused], [("claim", ["ITEM_OWNED"])])

    def test_brief_prepare_register(self):
        run_id = self.claim()["run_id"]
        directory = self.run_dir(run_id)
        code, out, err = self.cli("source", "brief", "--run", run_id)
        self.assertEqual((code, err), (0, ""), out)
        brief = json.loads(out)
        self.assertEqual(journal.read_doc(directory, "run.json")["input_ref"], brief["input_ref"])
        self.assertTrue(blobs.blob_path(brief["input_ref"], project=self.project).is_file())

        code, out, err = self.cli("source", "prepare", "--run", run_id, "--provider", "claude-code", "--binding",
                                  "claude-only", "--model-catalog", MODEL_CATALOG)
        self.assertEqual((code, err), (0, ""), out)
        plan = journal.read_doc(directory, "launch-plan.json")
        self.assertEqual(plan, json.loads(out))
        self.assertEqual([i for i in contracts.validate(plan, "launch-plan") if i.level == "error"], [])
        self.assertEqual(plan["submission_id"], journal.read_doc(directory, "run.json")["submission_id"])

        report = self.project / "report.json"
        report.write_text(json.dumps({"summary": "done"}), encoding="utf-8")
        code, out, err = self.cli("source", "register", "--run", run_id, "--report", report, "--status", "done",
                                  "--evidence", "V1=ev/V1.json", "--actor", "claude-code/claude-opus-5-5")
        self.assertEqual((code, err), (0, ""), out)
        answer = json.loads(out)
        self.assertEqual(journal.read_doc(directory, "receipts/register.json"), answer)
        sent = answer["receipt"]["input"]
        self.assertEqual((sent["attempt_id"], sent["evidence"], sent["executed_by"]),
                         (f"att-{run_id}-W1", {"V1": "ev/V1.json"}, sent["registrar"]))
        self.assertEqual(self.types(), ["orch.run.started", "orch.run.stage.finished", "orch.run.finished"])
        finished = self.events("orch.run.finished")[0].data
        self.assertEqual((finished["outcome"], finished["gate"], finished["ref"]), ("done", "pass", "W1"))

    def test_a_refused_registration_exits_1_and_is_refused(self):
        run_id = self.claim()["run_id"]
        self.mode("refuse")
        report = self.project / "report.json"
        report.write_text(json.dumps({"summary": "done"}), encoding="utf-8")
        code, out, _err = self.cli("source", "register", "--run", run_id, "--report", report, "--status", "done",
                                   "--actor", "claude-code/claude-opus-5-5")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["reason_code"], "REGISTER_EVIDENCE_MISSING")
        refused = self.events("orch.run.refused")[0].data
        self.assertEqual((refused["step"], refused["reason_codes"]), ("register", ["REGISTER_EVIDENCE_MISSING"]))
        self.assertNotIn("orch.run.finished", self.types())

    def test_prepare_needs_a_brief_and_an_unknown_run_is_refused(self):
        run_id = self.claim()["run_id"]
        code, _out, err = self.cli("source", "prepare", "--run", run_id, "--provider", "claude-code")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("RUN_NOT_BRIEFED: "), err)
        self.assertEqual(self.events("orch.run.refused")[0].data["reason_codes"], ["RUN_NOT_BRIEFED"])
        code, _out, err = self.cli("source", "brief", "--run", "run-" + "0" * 24)
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("RUN_UNKNOWN: "), err)

    def test_usage_errors_exit_2(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(["source", "claim", "--plan", "P", "--actor", "no-model"])
        self.assertEqual(caught.exception.code, 2)


class ConductorCommitTests(unittest.TestCase):
    def test_the_message_of_a_commit_reaches_the_conductor(self):
        from types import SimpleNamespace
        from orch.conductor.infrastructure import work_source
        answer = {"op": "commit", "outcome": "committed", "sha": "abc1234",
                  "message": "left outside, not the work of this piece: ideas/x.md"}
        owner = SimpleNamespace(_orch=lambda *args: (0, answer, ""))
        kept = work_source.commit(owner, SimpleNamespace(orch_run="run-1"), ["a.py"])
        self.assertEqual(kept, {"outcome": "committed", "sha": "abc1234", "message": answer["message"]})
        owner = SimpleNamespace(_orch=lambda *args: (0, {"op": "commit", "outcome": "committed", "sha": "abc1234"}, ""))
        self.assertNotIn("message", work_source.commit(owner, SimpleNamespace(orch_run="run-1"), ["a.py"]))


class RegisterReportTests(unittest.TestCase):
    """work-source/v1 register-report: the schema and the rules in code (orch.worksource_report)."""

    def test_the_schema_and_the_semantics(self):
        from orch.worksource_report import report_problems, report_semantics
        valid = {"summary": " s ", "changed_paths": ["a.py"], "evidence": [],
                 "checks_run": [{"id": "V1", "cmd": "make", "exit": 0}, {"id": "V2", "procedure": "look", "verdict": "pass"}],
                 "open_issues": [{"text": "t", "kind": "deviation", "class": "docs", "outcome": "accepted",
                                  "impact": "i", "evidence": ["a.py:1"]}]}
        self.assertEqual(report_problems(valid), [])
        twice = dict(valid, checks_run=[{"id": "V1", "cmd": "make", "exit": 0}, {"id": "V1", "cmd": "lint", "exit": 1}])
        self.assertEqual(worksource.problems(twice, "register-report"), [])  # uniqueness is not a schema rule
        self.assertEqual(report_semantics(twice), ["/checks_run/1/id: repeats V1"])
        blank = dict(valid, summary=" ", open_issues=[{"text": "t", "kind": "note", "next": " "}])
        self.assertEqual(worksource.problems(blank, "register-report"), [])  # \S of the schema is ASCII
        self.assertEqual(report_semantics(blank), ["/summary: is blank", "/open_issues/0/next: is blank"])
        self.assertTrue(worksource.problems(dict(valid, status="done"), "register-report"))
        with self.assertRaises(worksource.schema.SchemaProfileError):
            worksource.problems(valid, "not-a-kind")

    def test_the_refusal_code_follows_the_order_of_the_plan_source(self):
        from orch.worksource_report import refusal_code, report_problems

        def code(report):
            return refusal_code(report, report_problems(report))
        self.assertEqual(code({"summary": "s", "open_issues": ["a string"]}), "REGISTER_UNCLASSIFIED")
        self.assertEqual(code({"summary": "s", "open_issues": [{"text": "t", "kind": "todo"}]}), "REGISTER_UNCLASSIFIED")
        self.assertEqual(code({"summary": "s", "open_issues": [{"text": "t", "kind": "note", "why": "x"}]}),
                         "REGISTER_REPORT_INVALID")
        self.assertEqual(code({"summary": "s", "open_issues": [{"text": "t", "kind": "note", "why": "x"}, {"kind": "note"}]}),
                         "REGISTER_REPORT_INVALID")
        self.assertEqual(code({"summary": " ", "open_issues": [{"kind": "note"}]}), "REGISTER_REPORT_INVALID")


class WorkspaceOutputAuthorityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.project = self.base / "project"
        self.project.mkdir()
        self.one = self.base / "workspace/plan/artifacts/one"
        self.two = self.base / "workspace/plan/artifacts/two"
        self.other = self.base / "workspace/other-plan/artifacts/two"
        for directory in (self.one, self.two, self.other):
            directory.mkdir(parents=True)

    def command(self, output_dirs):
        from orch.conductor.infrastructure import launch_plan
        from orch.conductor.policies import authority
        guard = ROOT / "scripts/ro-run.py"
        argv = ["python3", str(guard), "--no-default-rw", "--rw", str(self.project), "--rw", "/dev", "--", "true"]
        route = {"provider": "antigravity", "argv": argv}
        envelope = authority.compute("executor", route, access="confined", sandbox={}, isolation={},
                                     declared_network="none", sandbox_domains=[], extra_paths=[], transcripts=None,
                                     project=str(self.project), home=str(self.base), writes=True, output_dirs=output_dirs)
        built = launch_plan.argv_from(envelope, route, [], shared=False, project=str(self.project))
        return envelope, built

    def test_output_grant_excludes_siblings_and_refuses_symlink_escape(self):
        from orch.conductor.infrastructure import launch_plan
        envelope, built = self.command([str(self.one)])
        self.assertIn({"path": str(self.one), "why": "output"}, envelope["write_roots"])
        self.assertEqual(built[built.index("--rw-strict") + 1], str(self.one))
        if launch_plan.landlock_abi() < 3:
            self.skipTest("Landlock ABI 3 required for truncation confinement")
        script = ("from pathlib import Path; import sys\n"
                  "Path(sys.argv[1]).write_text('ok')\n"
                  "for path in sys.argv[2:]:\n"
                  " try: Path(path).write_text('bad')\n"
                  " except PermissionError: continue\n"
                  " raise SystemExit(9)\n")
        command = built[:built.index("--") + 1] + [sys.executable, "-c", script, str(self.one / "ok"),
                                                   str(self.two / "bad"), str(self.other / "bad")]
        done = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse((self.two / "bad").exists())
        self.one.rename(self.one.with_name("saved"))
        self.one.symlink_to(self.other, target_is_directory=True)
        done = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("RO_RUN_RW_ESCAPE", done.stderr)

    def test_resumed_first_executor_refreshes_revoked_and_replaced_output(self):
        from orch.conductor.domain.stop import Stop
        from orch.conductor.infrastructure import launch_plan, work_source as conductor_source

        doc = json.loads(INPUT.read_text(encoding="utf-8"))
        stored = blobs.put_json(doc, sensitivity="normal", name="brief-W1", project=self.project)
        cached = {"artifacts_dir": ".swissknifeman/orch-artifacts/run/W1", "output_write_dirs": [str(self.one)]}
        saved = {"steps": {"brief": {"status": "done", "result": cached}, "executor.1": {"status": "started"}}}
        state_path = self.base / "saved-state.json"
        for replacement in (False, True):
            with self.subTest(replacement=replacement):
                state_path.write_text(json.dumps(saved), encoding="utf-8")
                item = SimpleNamespace(ref="W1", orch_run="run-a", directory=self.project, input_doc=doc,
                                       state=json.loads(state_path.read_text()), policy={})
                expected = [str(self.two)] if replacement else []
                answer = {"op": "brief", "input_ref": stored, "input_id": "brief@123", "digest": "a" * 64,
                          "reused": False, "artifact_id": "brief-W1-123456789abc", "output_write_dirs": expected}
                ask = mock.Mock(return_value=(0, answer, ""))
                owner = SimpleNamespace(project=self.project, _orch=ask,
                                        _save=lambda: state_path.write_text(json.dumps(item.state), encoding="utf-8"))
                conductor_source.open_artifacts(owner, item, item.state["steps"]["brief"]["result"])
                self.assertEqual(ask.call_count, 1)
                self.assertEqual(item.output_write_dirs, expected)
                self.assertEqual(json.loads(state_path.read_text())["steps"]["brief"]["result"]["output_write_dirs"], expected)
                envelope, built = self.command(item.output_write_dirs)
                self.assertNotIn(str(self.one), [root["path"] for root in envelope["write_roots"]])
                self.assertNotIn(str(self.one), built)
                self.assertEqual([built[i + 1] for i, arg in enumerate(built[:-1]) if arg == "--rw-strict"], expected)
                if launch_plan.landlock_abi() >= 3:
                    code = ("from pathlib import Path; import sys\n"
                            "try: Path(sys.argv[1]).write_text('bad')\n"
                            "except PermissionError: pass\n"
                            "else: raise SystemExit(9)\n"
                            "if len(sys.argv)>2: Path(sys.argv[2]).write_text('ok')\n")
                    args = [str(self.one / "bad")] + ([str(self.two / "ok")] if replacement else [])
                    done = subprocess.run(built[:built.index("--") + 1] + [sys.executable, "-c", code, *args],
                                          capture_output=True, text=True)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertFalse((self.one / "bad").exists())
                failed = SimpleNamespace(project=self.project, _orch=lambda *args: (1, None, "refused"))
                retry = SimpleNamespace(ref="W1", orch_run="run-a", state=json.loads(json.dumps(saved)))
                with self.assertRaises(Stop):
                    conductor_source.open_artifacts(failed, retry, retry.state["steps"]["brief"]["result"])
                retry.state["steps"]["brief"]["result"]["output_write_dirs"] = []
                with self.assertRaises(Stop):
                    conductor_source.open_artifacts(failed, retry, retry.state["steps"]["brief"]["result"])
                failed._orch = lambda *args: (0, {"input_ref": "invalid"}, "")
                with mock.patch.object(conductor_source.blobs, "read_bytes", return_value=json.dumps(doc).encode()), self.assertRaises(Stop):
                    conductor_source.open_artifacts(failed, retry, retry.state["steps"]["brief"]["result"])


class ConductorBriefTests(unittest.TestCase):
    """The conductor reads the stored brief as exec/v1 before it writes ``input.json`` (BRIEF_INVALID)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        self.item = SimpleNamespace(orch_run="run-1", ref="W1", directory=self.project / "run" / "W1",
                                    input_doc={"digest": "sha256:old"})
        self.emitted = []

    def owner(self, doc) -> SimpleNamespace:
        stored = blobs.put_json(doc, sensitivity="normal", name="brief-W1", project=self.project)
        answer = {"op": "brief", "input_ref": stored, "input_id": doc.get("input_id", "x") if isinstance(doc, dict) else "x"}
        return SimpleNamespace(_orch=lambda *args: (0, answer, ""), project=self.project, run_id="run-1",
                               progress=SimpleNamespace(emit=lambda *a, **k: self.emitted.append(k)))

    def test_a_brief_outside_exec_v1_stops_before_input_json(self):
        from orch.conductor.domain.stop import Stop
        from orch.conductor.infrastructure import work_source
        spoiled = {**json.loads(INPUT.read_text(encoding="utf-8")), "verify": "a field verify() does not look at"}
        with self.assertRaises(Stop) as caught:
            work_source.brief(self.owner(spoiled), self.item)
        self.assertEqual(caught.exception.code, "BRIEF_INVALID")
        self.assertIn("/verify", caught.exception.message)
        self.assertFalse((self.item.directory / "input.json").exists())
        with self.assertRaises(Stop) as caught:
            work_source.brief(self.owner(["not", "an", "object"]), self.item)
        self.assertEqual(caught.exception.code, "BRIEF_INVALID")

    def test_a_valid_brief_passes_and_a_spoiled_refresh_keeps_the_earlier_input(self):
        from orch.conductor.infrastructure import work_source
        self.assertEqual(work_source.input_errors(json.loads(INPUT.read_text(encoding="utf-8"))), [])
        spoiled = {**json.loads(INPUT.read_text(encoding="utf-8")), "verify": "x"}
        work_source.refresh_input(self.owner(spoiled), self.item)
        self.assertEqual([entry["reason_code"] for entry in self.emitted], ["INPUT_REFRESH_FAILED"])
        self.assertEqual(self.item.input_doc, {"digest": "sha256:old"})
        self.assertFalse((self.item.directory / "input.json").exists())


class ConductorFinishTests(unittest.TestCase):
    """``finish`` checks the register-report body before it writes it (REGISTER_REPORT_INVALID: a conductor defect)."""

    def finish(self, report):
        from orch.conductor.stages import finish
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        item = SimpleNamespace(ref="W1", directory=Path(tmp.name), state={"steps": {}, "autofixed": []})
        written = []
        owner = SimpleNamespace(
            _correction_settle=lambda item, report: report, _settle_pending=lambda report, rows: report,
            _changed=lambda item: [], _outside=lambda item: [],
            _autofix_issues=lambda item, report: [], _notes=lambda item: [], _questions=lambda item: {},
            _write_artifact=lambda item, name, doc: written.append(name), _deviation_recorded=lambda item, issue: None,
            _beacon_event=lambda *args: None,
            _register_args=mock.Mock(side_effect=AssertionError("registered")))
        return finish.finish(owner, item, report, []), item, written

    def test_a_body_outside_register_report_stops_before_it_is_written(self):
        from orch.conductor.domain.stop import Stop
        report = {"status": "done", "summary": "s", "changed_paths": [], "checks_run": [], "evidence": [],
                  "open_issues": [{"text": "slow", "kind": "difficulty", "evidence": []}]}  # a stage-report allows []
        with self.assertRaises(Stop) as caught:
            self.finish(report)
        self.assertEqual(caught.exception.code, "REGISTER_REPORT_INVALID")
        self.assertIn("W1: the register-report is outside work-source/v1 register-report: /open_issues/0/evidence",
                      caught.exception.message)
        twice = dict(report, checks_run=[{"id": "V1", "cmd": "make", "exit": 0}] * 2, open_issues=[])
        with self.assertRaises(Stop) as caught:
            self.finish(twice)
        self.assertIn("repeats V1", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
