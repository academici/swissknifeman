"""``conduct.py run --input FILE``: work outside a plan, served by the built-in file source (P6.1).

The roles are the fake roles of ``test_conductor``; the work source of the plan side (``fake-cs``) is only asked for
the journal note of support work and must otherwise stay untouched.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import unittest

from orch import adhoc, cli as orch_cli, journal
from orch.conductor import engine
from orch.contracts import canonical_digest, validate
from orch.worksource import WorkSourceError, problems
from orch.worksource_file import FileWorkSource
from tests.test_conductor import ConductorCase, GREEN, report


def adhoc_report(**extra) -> dict:
    return {**report("adhoc", **extra), "checks_run": [{"id": "V1", "cmd": "test -f out/adhoc.txt", "exit": 0}]}


EXECUTOR = {"write": {"out/adhoc.txt": "ok\n"}, "result": adhoc_report()}


class InputCase(ConductorCase):
    def write_input(self, provenance: dict | None = None, **kwargs) -> Path:
        doc = adhoc.build_adhoc_input("Make out/adhoc.txt", ["out/adhoc.txt"], checks=["V1=test -f out/adhoc.txt"],
                                      provenance=provenance, **kwargs)
        path = self.project.parent / "input.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        self.input_doc = doc
        return path

    def orch(self, *argv) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = orch_cli.main(["--project", str(self.project), *[str(item) for item in argv]])
        return code, out.getvalue(), err.getvalue()

    def run_input(self, path: Path, *extra) -> tuple:
        return self.conduct("run", "--input", path, "--json-lines", "--scenario", "full", *extra)

    def artifacts(self, err: str) -> Path:
        run = json.loads((self.run_dir(err) / "state.json").read_text())["items"][self.input_doc["input_id"]]["orch_run"]
        return self.project / ".swissknifeman" / "orch-artifacts" / run / self.input_doc["input_id"]


class FileSourceRunTests(InputCase):
    def test_an_input_runs_without_a_plan_and_keeps_its_records_in_orch_artifacts(self):
        path = self.write_input()
        self.script({"executor": [EXECUTOR], "reviewer": [GREEN]})
        code, _, err = self.run_input(path)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        run = json.loads((self.run_dir(err) / engine.RUN_FILE).read_text())
        self.assertEqual((run["plan"], run["source"]), (str(path), {"kind": "file", "path": str(path), "commit": False}))
        self.assertEqual(run["items"], [self.input_doc["input_id"]])
        folder = self.artifacts(err)
        self.assertEqual(json.loads((folder / "stage-report.json").read_text())["status"], "done")
        self.assertEqual(json.loads((folder / "evidence/V1.json").read_text())["exit"], 0)
        self.assertFalse((self.project / "plans").exists())
        self.assertEqual(self.source()["calls"], [])  # the plugin source was never asked

    def test_by_default_nothing_is_committed_the_changes_stay_in_the_tree(self):
        path = self.write_input()
        self.script({"executor": [EXECUTOR], "reviewer": [GREEN]})
        before = self.git("rev-parse", "HEAD")
        code, _, err = self.run_input(path)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertIn("out/", self.git("status", "--porcelain"))
        commit = [line for line in self.lines(err) if line.get("stage") == "commit" and line["event"] == "stage.end"]
        self.assertTrue(all("no-op" in (line.get("verdict") or "") for line in commit), commit)

    def test_commit_takes_the_changed_paths_with_an_adhoc_message(self):
        path = self.write_input()
        self.script({"executor": [EXECUTOR], "reviewer": [GREEN]})
        code, _, err = self.run_input(path, "--commit")
        self.assertEqual(code, 0, err)
        subject = self.git("log", "-1", "--format=%s").strip()
        self.assertEqual(subject, f"adhoc({self.input_doc['input_id']}): Make out/adhoc.txt")
        self.assertIn("out/adhoc.txt", self.git("show", "--name-only", "--format=", "HEAD"))
        self.assertNotIn("out/", self.git("status", "--porcelain"))
        # W4: the artifact folder of the file source holds local records, never committed with the work
        self.assertFalse([line for line in self.git("show", "--name-only", "--format=", "HEAD").splitlines()
                          if "orch-artifacts" in line])
        self.assertTrue(list((self.project / ".swissknifeman/orch-artifacts").glob("*/*/stage-report.json")))

    def test_a_repeated_registration_is_a_no_op(self):
        path = self.write_input()
        self.script({"executor": [EXECUTOR], "reviewer": [GREEN]})
        code, _, err = self.run_input(path)
        self.assertEqual(code, 0, err)
        run = self.state(err)["items"][self.input_doc["input_id"]]["orch_run"]
        report_file = self.run_dir(err) / safe(self.input_doc["input_id"]) / "register-report.json"
        done = self.orch("source", "register", "--run", run, "--report", report_file, "--status", "done",
                         "--actor", "orch/conductor", "--evidence", f"V1={self.artifacts(err) / 'evidence/V1.json'}")
        self.assertEqual((done[0], json.loads(done[1])["outcome"]), (0, "no-op"), done)

    def test_plan_and_input_exclude_each_other_and_an_input_takes_no_items(self):
        path = self.write_input()
        for argv in (("--plan", "T", "--input", path), ("--input", path, "--items", "W1"), ("--input", path, "--ready"),
                     ("--plan", "T"), ("--commit", "--plan", "T", "--items", "W1")):
            with self.assertRaises(SystemExit) as stop:
                self.conduct("run", *argv)
            self.assertEqual(stop.exception.code, 2, argv)

    def test_an_input_outside_exec_v1_stops_before_any_work(self):
        path = self.write_input()
        doc = json.loads(path.read_text())
        doc["goal"] = ""
        path.write_text(json.dumps(doc), encoding="utf-8")
        code, _, err = self.run_input(path)
        self.assertEqual(code, 1)
        self.assertIn("INPUT_INVALID", err)
        self.assertEqual(self.calls("executor"), 0)

    def test_an_unreadable_input_is_refused_with_its_path(self):
        code, _, err = self.run_input(self.project / "nowhere.json")
        self.assertEqual(code, 1)
        self.assertIn("INPUT_INVALID", err)
        self.assertIn("nowhere.json", err)

    def test_the_gate_refuses_missing_and_red_evidence_and_a_blocked_piece_needs_none(self):
        path = self.write_input()
        source = FileWorkSource(path, project=self.project)
        fields = {"plan": str(path), "ref": self.input_doc["input_id"], "run_id": "run-x", "attempt_id": "att-run-x-a",
                  "report": {"summary": "s"}, "registrar": {"provider": "orch", "model": "conductor"},
                  "executed_by": {"provider": "claude-code", "model": "m"}}
        missing = source.register(status="done", evidence={}, **fields)
        self.assertEqual((missing["outcome"], missing["gate"]["verdict"], missing["reason_code"]),
                         ("refused", "missing", "REGISTER_EVIDENCE_MISSING"))
        red = self.project / "red.json"
        red.write_text(json.dumps({"check_id": "V1", "exit": 1}), encoding="utf-8")
        refused = source.register(status="done", evidence={"V1": str(red)}, **fields)
        self.assertEqual((refused["outcome"], refused["gate"]["checks"], refused["reason_code"]),
                         ("refused", {"V1": 1}, "REGISTER_EVIDENCE_RED"))
        blocked = source.register(status="blocked", evidence={}, **fields)
        self.assertEqual((blocked["outcome"], blocked["gate"]["verdict"]), ("recorded", "none"))
        self.assertEqual(source.register(status="blocked", evidence={}, **fields)["outcome"], "no-op")

    def test_a_report_outside_register_report_is_refused_with_the_codes_of_the_plan_source(self):
        path = self.write_input()
        source = FileWorkSource(path, project=self.project)
        fields = {"plan": str(path), "ref": self.input_doc["input_id"], "run_id": "run-x", "attempt_id": "att-run-x-a",
                  "registrar": {"provider": "orch", "model": "conductor"},
                  "executed_by": {"provider": "claude-code", "model": "m"}}
        twice = [{"id": "V1", "cmd": "make", "exit": 0}, {"id": "V1", "cmd": "make lint", "exit": 1}]
        cases = [({"summary": "s", "status": "done"}, "REGISTER_REPORT_INVALID", "/status"),
                 ({"summary": "s", "checks_run": twice}, "REGISTER_REPORT_INVALID", "repeats V1"),
                 ({"summary": " "}, "REGISTER_REPORT_INVALID", "/summary: is blank"),
                 ({"summary": "s", "open_issues": [{"text": "no kind"}]}, "REGISTER_UNCLASSIFIED", "/open_issues/0"),
                 ({"summary": "s", "open_issues": [{"text": " ", "kind": "note"}]}, "REGISTER_UNCLASSIFIED", "/text"),
                 ({"summary": "s", "open_issues": [{"text": "t", "kind": "note", "evidence": []}]},
                  "REGISTER_REPORT_INVALID", "/open_issues/0/evidence")]
        for body, code, where in cases:
            with self.subTest(report=body):
                answer = source.register(status="blocked", evidence={}, report=body, **fields)
                self.assertEqual((answer["outcome"], answer["reason_code"], answer["gate"]["verdict"]),
                                 ("refused", code, "none"))
                self.assertIn(where, answer["message"])
        self.assertFalse((self.project / ".swissknifeman" / "orch-artifacts" / "run-x").exists())

    def test_a_changed_input_is_refused_at_brief(self):
        path = self.write_input()
        source = FileWorkSource(path, project=self.project)
        doc = json.loads(path.read_text())
        doc["goal"] = "Something else"
        doc["digest"] = canonical_digest(doc)
        doc["input_id"] = "adhoc@" + doc["digest"][:12]
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(WorkSourceError) as stop:
            source.brief(plan=str(path), ref=self.input_doc["input_id"], run_id="run-x")
        self.assertEqual(stop.exception.code, "INPUT_CHANGED")


class SupportProvenanceTests(InputCase):
    def test_plan_support_registers_a_note_through_the_plan_source(self):
        path = self.write_input(adhoc.support_provenance("phase_support", plan="T", phase="P1"))
        self.script({"executor": [EXECUTOR], "reviewer": [GREEN]})
        code, _, err = self.run_input(path)
        self.assertEqual(code, 0, err)
        notes = self.source()["notes"]
        self.assertEqual([(note["collection"], note["refs"]) for note in notes], [("T", ["P1"])])
        self.assertIn("phase_support", notes[0]["text"])
        self.assertIn("made adhoc", notes[0]["text"])

    def test_a_refused_note_is_a_beacon_not_a_stop(self):
        path = self.write_input(adhoc.support_provenance("plan_support", plan="T"))
        self.set_items({"W1": {}}, refuse=["note"])
        self.script({"executor": [EXECUTOR], "reviewer": [GREEN]})
        code, _, err = self.run_input(path)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        beacons = [line for line in self.lines(err) if line.get("reason_code") == "WORK_SOURCE_NO_NOTE"]
        self.assertEqual(len(beacons), 1, err)
        self.assertEqual(self.source().get("notes", []), [])

    def test_other_provenance_kinds_write_no_note(self):
        path = self.write_input(adhoc.support_provenance("research", plan="T", question="why"))
        self.script({"executor": [EXECUTOR], "reviewer": [GREEN]})
        code, _, err = self.run_input(path)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.source().get("notes", []), [])


class ReviewFindingsTests(InputCase):
    """Findings of the grok-4.7 review of P6.1–P6.3, each with the reproduction of the reviewer."""

    def git_repo(self) -> Path:
        return self.project

    def test_a_commit_takes_literally_named_paths_only(self):  # F2
        path = self.write_input()
        (self.project / "item1.txt").write_text("tracked\n", encoding="utf-8")
        self.git("add", "item1.txt")
        self.git("commit", "-q", "-m", "tracked")
        (self.project / "item1.txt").write_text("foreign change\n", encoding="utf-8")  # unstaged work of the owner
        (self.project / "item[1].txt").write_text("mine\n", encoding="utf-8")
        source = FileWorkSource(path, project=self.project, commit=True)
        answer = source.commit(plan=str(path), ref=self.input_doc["input_id"], run_id="run-x", attempt_id="att-run-x-a",
                               paths=["item[1].txt"])
        self.assertEqual(answer["outcome"], "committed")
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(), ["item[1].txt"])
        self.assertIn(" M item1.txt", self.git("status", "--porcelain"))

    def test_an_input_id_that_is_not_one_path_component_is_refused(self):  # F3
        path = self.write_input()
        doc = json.loads(path.read_text())
        doc["input_id"] = "a/../../../OUTSIDE@" + "0" * 12
        doc["digest"] = canonical_digest(doc)
        doc["input_id"] = "a/../../../OUTSIDE@" + doc["digest"][:12]
        path.write_text(json.dumps(doc), encoding="utf-8")
        code, _, err = self.run_input(path)
        self.assertEqual(code, 1)
        self.assertIn("INPUT_INVALID", err)
        self.assertFalse((self.project.parent / "OUTSIDE").exists() or list(self.project.parent.glob("OUTSIDE*")))

    def test_the_register_receipt_stays_inside_work_source_v1(self):  # F4
        path = self.write_input(adhoc.support_provenance("phase_support", plan="T", phase="P1"))
        self.script({"executor": [EXECUTOR], "reviewer": [GREEN]})
        code, _, err = self.run_input(path)
        self.assertEqual(code, 0, err)
        run = self.state(err)["items"][self.input_doc["input_id"]]["orch_run"]
        receipts = journal.run_dir(run, project=self.project) / "receipts"
        self.assertEqual(problems(json.loads((receipts / "register.json").read_text()), "output"), [])
        self.assertEqual(json.loads((receipts / "note.json").read_text()), {"outcome": "recorded"})

    def test_a_refused_commit_leaves_the_index_as_it_was(self):  # F5
        path = self.write_input()
        hook = self.project / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        (self.project / "wanted.txt").write_text("x\n", encoding="utf-8")
        source = FileWorkSource(path, project=self.project, commit=True)
        answer = source.commit(plan=str(path), ref=self.input_doc["input_id"], run_id="run-x", attempt_id="att-run-x-a",
                               paths=["wanted.txt"])
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "COMMIT_REFUSED"))
        self.assertEqual(self.git("diff", "--cached", "--name-only").strip(), "")
        self.assertIn("?? wanted.txt", self.git("status", "--porcelain"))


class ProvenanceKindTests(unittest.TestCase):
    def test_every_kind_builds_a_valid_input(self):
        fields = {"plan_support": {"plan": "P"}, "phase_support": {"plan": "P", "phase": "P6"},
                  "review_followup": {"item": "P6.1", "finding": "F1"}, "deviation_fix": {"plan": "P", "item": "P6.1", "event": "e1"},
                  "research": {"question": "why"}, "advisor": {"plan": "P", "item": "P6.1", "question": "how"}}
        for kind, given in fields.items():
            doc = adhoc.build_adhoc_input("Goal", ["a"], checks=["V1=true"], provenance=adhoc.support_provenance(kind, **given))
            self.assertEqual([i for i in validate(doc, "execution-input") if i.level == "error"], [], kind)
            self.assertEqual(doc["provenance"]["kind"], kind)

    def test_a_missing_or_foreign_field_is_a_usage_mistake(self):
        for kind, given in (("phase_support", {"plan": "P"}), ("deviation_fix", {"plan": "P"}),
                            ("research", {"item": "P6.1"}), ("nothing", {})):
            with self.assertRaises(adhoc.AdhocError) as stop:
                adhoc.support_provenance(kind, **given)
            self.assertEqual(stop.exception.code, "USAGE", kind)

    def test_review_and_provenance_exclude_each_other(self):
        with self.assertRaises(adhoc.AdhocError):
            adhoc.build_adhoc_input("g", ["a"], review="a..b", provenance=adhoc.support_provenance("research"))

    def test_an_unknown_kind_is_outside_the_schema(self):
        doc = adhoc.build_adhoc_input("Goal", ["a"], checks=["V1=true"])
        doc["provenance"] = {"kind": "research", "request": "no such field"}
        self.assertTrue([i for i in validate(doc, "execution-input") if i.level == "error"])


def safe(text: str) -> str:
    return engine.safe(text)


if __name__ == "__main__":
    unittest.main()
