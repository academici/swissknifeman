"""gui-orch adapter through the aicore plugin protocol against a fake orch command line: every answer is view-data/v1 of
the declared view; runs, run, items, report (path rules), questions, sandbox, empty projects and failures."""
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from aicore.ext.plugins import Registration, invoke_one, load_manifest

# The GUI host is a partner of this bridge: found through SKM_GUI_ROOT (scripts/test.sh), never imported statically.
sys.path.insert(0, str(Path(os.environ["SKM_GUI_ROOT"]) / "lib"))
contracts = importlib.import_module("gui.contracts")

BRIDGE = Path(__file__).resolve().parents[1]
FIXTURES = BRIDGE / "tests" / "fixtures"
GUI_DOC = json.loads((BRIDGE / "gui.json").read_text(encoding="utf-8"))
RETURNS = {query["id"]: query["returns"] for query in GUI_DOC["queries"]}
RUN = "cnd-new"
SKM_GUI_LIB = Path(os.environ["SKM_GUI_ROOT"]) / "lib"


def floats(value, path="$"):
    """Paths of the float numbers in a JSON value: the backend refuses to canonicalize them."""
    if isinstance(value, float):
        return [path]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in floats(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in floats(v, f"{path}[{i}]")]
    return []


class AdapterCase(unittest.TestCase):
    def setUp(self):
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.project = self.home / "project"
        self.project.mkdir()
        manifest = load_manifest(BRIDGE / "extension.json")
        self.plugin = Registration(id=manifest.id, manifest_path=str(BRIDGE / "extension.json"), trusted=True,
                                   timeout_seconds=30, enabled=True, manifest=manifest, problem=None)

    def query(self, query_id, *, umbrella="umbrella-ok", params=None, context=None, project=True):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "SKM_UMBRELLA": str(FIXTURES / umbrella)}
        return invoke_one(self.plugin, "gui:query", {"id": query_id, "context": context or {}, "params": params or {}},
                          env=env, project=str(self.project) if project else None)

    def ok(self, query_id, **kwargs):
        result = self.query(query_id, **kwargs)
        self.assertEqual("ok", result.status, (result.code, result.error))
        self.assertEqual([], contracts.validate(result.output, "view-data"))
        self.assertEqual(RETURNS[query_id], result.output["view"])
        self.assertEqual([], floats(result.output), "the backend's canonical JSON has no floats")
        return result.output

    def refused(self, query_id, code, **kwargs):
        result = self.query(query_id, **kwargs)
        self.assertEqual(("error", code), (result.status, result.code), result.error)
        return result

    def calls(self):
        log = self.home / "umbrella.log"
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


class TestRuns(AdapterCase):
    def test_runs_table(self):
        out = self.ok("gui-orch.runs")
        self.assertEqual(["cnd-new", "cnd-old", "cnd-bad"], [row["id"] for row in out["rows"]])
        new = out["rows"][0]
        self.assertEqual({"run": "cnd-new", "status": "running", "reason": "-", "created": "2026-10-17T09:00:00Z",
                          "items": "P2.1, P2.2", "resumes": 1}, new["cells"])
        self.assertEqual({"route": "gui-orch.run", "params": {"run_id": "cnd-new"}}, new["link"])
        self.assertEqual("unreadable", out["rows"][2]["cells"]["status"])
        self.assertEqual(3, out["total"])
        call = self.calls()[0]
        self.assertEqual(["orch", "conduct", "runs", "--json"], call["argv"])
        self.assertEqual(str(self.project), call["cwd"])

    def test_latest_is_one_row(self):
        out = self.ok("gui-orch.latest")
        self.assertEqual(["cnd-new"], [row["id"] for row in out["rows"]])
        self.assertEqual(["orch", "conduct", "runs", "--json", "--limit", "1"], self.calls()[0]["argv"])

    def test_empty_project_and_no_project(self):
        self.assertEqual([], self.ok("gui-orch.runs", umbrella="umbrella-empty")["rows"])
        self.assertEqual([], self.ok("gui-orch.latest", umbrella="umbrella-empty")["rows"])
        before = len(self.calls())
        self.assertEqual([], self.ok("gui-orch.runs", project=False)["rows"])
        self.assertEqual(before, len(self.calls()), "no project: the CLI is not called")

    def test_failures_keep_a_code_and_no_ansi(self):
        result = self.refused("gui-orch.runs", "ORCH_CLI_FAILED", umbrella="umbrella-fail")
        self.assertNotIn("\x1b", result.error.get("message", "") if isinstance(result.error, dict) else str(result.error))
        self.refused("gui-orch.runs", "ORCH_CLI_FAILED", umbrella="umbrella-garbage")
        self.refused("gui-orch.runs", "ORCH_UNAVAILABLE", umbrella="umbrella-does-not-exist")


class TestRun(AdapterCase):
    def test_detail_of_a_run(self):
        out = self.ok("gui-orch.run", params={"run_id": RUN})
        fields = {field["label"]: field["value"] for field in out["fields"]}
        self.assertEqual(("running", "1200 in, 340 out"), (fields["Status"], fields["Tokens"]))
        self.assertIn("P2.2 executor.1 executor", fields["Now"])
        self.assertEqual([{"command": "gui-orch.resume", "input": {"run_id": RUN}}], out["actions"])
        self.assertEqual({"Items", "Agents"}, {section["title"] for section in out["sections"]})
        self.assertEqual(["orch", "conduct", "status", "--run", RUN, "--json"], self.calls()[0]["argv"])

    def test_run_id_comes_from_the_context_too_and_is_checked_before_the_cli(self):
        self.ok("gui-orch.run", context={"run_id": RUN})
        before = len(self.calls())
        for bad in ("../x", "cnd-", "run-1", "cnd-a b", "cnd-a;b", "--run"):
            with self.subTest(bad=bad):
                self.refused("gui-orch.run", "ORCH_CONTEXT_MISSING", params={"run_id": bad})
        self.refused("gui-orch.run", "ORCH_CONTEXT_MISSING")
        self.assertEqual(before, len(self.calls()), "a malformed id never reaches the CLI")

    def test_unknown_run(self):
        self.refused("gui-orch.run", "ORCH_RUN_NOT_FOUND", params={"run_id": "cnd-zzz"})
        self.refused("gui-orch.items", "ORCH_RUN_NOT_FOUND", umbrella="umbrella-missing", params={"run_id": RUN})

    def test_items_table_maps_outcomes(self):
        out = self.ok("gui-orch.items", params={"run_id": RUN})
        status = {row["id"]: row["status"] for row in out["rows"]}
        self.assertEqual({"P2.1": "ok", "P2.2": "warn", "P2.3": "fail", "P2.4": "warn", "P2.5": "unknown"}, status)
        blocked = next(row for row in out["rows"] if row["id"] == "P2.3")
        self.assertIn("REVIEW_FAILED", blocked["detail"])
        self.assertIn("review.1", blocked["detail"])


class TestReport(AdapterCase):
    def test_report_is_read_from_the_reports_folder(self):
        out = self.ok("gui-orch.report", params={"run_id": RUN})
        self.assertIn("# Observer report", out["text"])
        self.assertEqual(["orch", "conduct", "observe", "--run", RUN], self.calls()[0]["argv"])
        self.assertTrue((self.project / ".swissknifeman" / "orch" / "reports" / RUN / "observer.md").is_file())

    def test_a_path_outside_the_reports_folder_is_refused_and_not_read(self):
        result = self.refused("gui-orch.report", "ORCH_CLI_FAILED", umbrella="umbrella-escape", params={"run_id": RUN})
        self.assertNotIn("SECRET", json.dumps(result.error))

    def test_a_symlinked_report_is_refused(self):
        self.refused("gui-orch.report", "ORCH_CLI_FAILED", umbrella="umbrella-symlink", params={"run_id": RUN})

    def test_traversal_by_run_id_never_reaches_the_cli(self):
        self.refused("gui-orch.report", "ORCH_CONTEXT_MISSING", params={"run_id": "cnd-../../etc"})
        self.assertEqual([], self.calls())

    def test_a_report_of_another_run_is_refused(self):
        from adapter import OrchError, _report_path  # noqa: PLC0415 - the adapter is the unit under test

        other = self.project / ".swissknifeman" / "orch" / "reports" / "cnd-old"
        other.mkdir(parents=True)
        (other / "observer.md").write_text("x", encoding="utf-8")
        with self.assertRaises(OrchError):
            _report_path(str(other / "observer.md"), str(self.project), RUN)
        with self.assertRaises(OrchError):
            _report_path(None, str(self.project), RUN)


class TestQuestionsAndSandbox(AdapterCase):
    def test_questions(self):
        out = self.ok("gui-orch.questions")
        self.assertEqual(["P2.3:Q1", "P2.4:Q2"], [row["id"] for row in out["rows"]])
        first, second = out["rows"][0]["cells"], out["rows"][1]["cells"]
        self.assertEqual(("open", "yes", 120), (first["state"], first["overdue"], first["age_s"]))
        self.assertNotIn("\x1b", first["question"])
        self.assertEqual("answered, waits for resume", second["state"])
        self.assertEqual(["orch", "conduct", "questions", "--json"], self.calls()[0]["argv"])
        self.ok("gui-orch.questions", params={"run_id": RUN})
        self.assertEqual(["orch", "conduct", "questions", "--json", "--run", RUN], self.calls()[1]["argv"])

    def test_no_run_means_no_questions(self):
        self.assertEqual([], self.ok("gui-orch.questions", umbrella="umbrella-empty")["rows"])
        self.refused("gui-orch.questions", "ORCH_RUN_NOT_FOUND", umbrella="umbrella-missing", params={"run_id": RUN})
        self.assertEqual([], self.ok("gui-orch.questions", project=False)["rows"])

    def test_sandbox_rows_are_the_orch_checks_with_the_caption(self):
        out = self.ok("gui-orch.sandbox")
        self.assertEqual(["orch.sandbox", "orch.conductor-gitignore", "scope"], [row["id"] for row in out["rows"]])
        sandbox = out["rows"][0]
        self.assertEqual("warn", sandbox["status"])
        self.assertIn("Operation not permitted", sandbox["detail"])
        self.assertNotIn("\x1b", sandbox["detail"])
        self.assertIn("GUI plugin processes are not sandboxed", out["rows"][-1]["detail"])
        self.assertEqual(["orch", "doctor", "--json"], self.calls()[0]["argv"])

    def test_unknown_query_and_command_points(self):
        self.refused("gui-orch.nope", "ORCH_UNKNOWN_QUERY")
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "SKM_UMBRELLA": str(FIXTURES / "umbrella-ok")}
        result = invoke_one(self.plugin, "gui:command", {"id": "gui-orch.resume", "context": {}, "input": {}}, env=env,
                            project=str(self.project))
        self.assertEqual("error", result.status)

    def test_every_declared_query_is_answered(self):
        for query in GUI_DOC["queries"]:
            params = {"run_id": RUN} if any(p["name"] == "run_id" and p["required"] for p in query.get("params", [])) else {}
            with self.subTest(query=query["id"]):
                self.ok(query["id"], params=params)

    def test_example_input_of_the_manifest_works_without_a_project(self):
        manifest = json.loads((BRIDGE / "extension.json").read_text(encoding="utf-8"))
        result = self.query(manifest["example_input"]["id"], project=False, params=manifest["example_input"]["params"])
        self.assertEqual("ok", result.status, (result.code, result.error))


if __name__ == "__main__":
    unittest.main()
