"""The work-source port: the plugin client (contract on both sides, unavailable and failing sources) and the cycle
``orch.py source claim|brief|prepare|register`` on a test plugin (run journal, deterministic run ids, events)."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
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
        self.assertEqual(worksource.problems({"op": "peek"}, "input"), ["/op: must be one of claim, brief, register, commit, release, note"])


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


if __name__ == "__main__":
    unittest.main()
