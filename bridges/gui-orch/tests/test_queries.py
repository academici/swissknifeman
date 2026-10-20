"""gui-orch adapter through the aicore plugin protocol against a fake orch command line: every answer is view-data/v1 of
the declared view; runs, run, items, report (path rules), questions, sandbox, empty projects and failures."""
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "SKM_UMBRELLA": str(FIXTURES / umbrella),
               "AICORE_ROOT": os.environ["AICORE_ROOT"]}
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
        self.assertEqual(["cnd-new", "cnd-old", "cnd-bad", "cnd-orphaned"], [row["id"] for row in out["rows"]])
        new = out["rows"][0]
        self.assertEqual({"run": "cnd-new", "status": "warn", "reason": "-", "created": "2026-10-17T09:00:00Z",
                          "items": "P2.1, P2.2", "resumes": 1,
                          "owner": "pid 123 on test-host since 2026-10-17T09:00:00Z (run)"}, new["cells"])
        self.assertEqual({"route": "gui-orch.run", "params": {"run_id": "cnd-new"}}, new["link"])
        self.assertEqual("unknown", out["rows"][2]["cells"]["status"])
        self.assertEqual("warn", out["rows"][3]["cells"]["status"])
        self.assertIn("RUN_ORPHANED: no live conductor", out["rows"][3]["cells"]["reason"])
        self.assertEqual(4, out["total"])
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
        self.assertEqual(("warn", "1200 in, 340 out"), (fields["Status"], fields["Tokens"]))
        self.assertEqual("running", fields["State"])
        self.assertIn("pid 123 on test-host", fields["Owner"])
        self.assertIn("P2.2 executor.1 executor", fields["Now"])
        self.assertNotIn("actions", out)
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


class TestObservability(AdapterCase):
    def test_orphaned_and_stopped_runs_offer_resume_and_no_stale_owner(self):
        for state in ("orphaned", "stopped"):
            run_id = f"cnd-{state}"
            out = self.ok("gui-orch.run", params={"run_id": run_id})
            fields = {field["label"]: field["value"] for field in out["fields"]}
            self.assertEqual(("warn", "-"), (fields["Status"], fields["Owner"]))
            self.assertEqual([{"command": "gui-orch.resume", "input": {"run_id": run_id}}], out["actions"])
            if state == "orphaned":
                self.assertEqual("RUN_ORPHANED: no live conductor holds the run; resume continues it", fields["Detail"])

    def test_routes_keep_used_and_available_now_separate_and_whitelisted(self):
        out = self.ok("gui-orch.routes", params={"run_id": RUN, "item": "P2.1"})
        self.assertEqual("ok", out["rows"][0]["status"])
        self.assertIn("used: codex/recorded-model", out["rows"][0]["detail"])
        self.assertIn("available now: claude-code/current-model", out["rows"][0]["detail"])
        self.assertNotIn("PRIVATE_", json.dumps(out))
        self.assertEqual(["orch", "route", "explain", "--role", "executor", "--run", RUN, "--item", "P2.1", "--json"],
                         self.calls()[-1]["argv"])
        unknown = self.ok("gui-orch.routes", params={"run_id": RUN, "item": "P2.2"})
        self.assertIn("used: unknown", unknown["rows"][0]["detail"])

    def test_prompt_is_only_metadata_with_short_digests_and_budget_totals(self):
        out = self.ok("gui-orch.prompt", params={"run_id": RUN, "item": "P2.1", "step": "executor.1-q2"})
        fields = {field["label"]: field["value"] for field in out["fields"]}
        self.assertEqual("origin: claim; tokens: 42; sha256: " + "a" * 12, fields["input"])
        self.assertEqual("not applicable", fields["Excluded skill"])
        self.assertEqual((42, 0, 0), tuple(fields[name] for name in ("core", "supporting", "retrieval")))
        self.assertNotIn("PRIVATE_", json.dumps(out))
        self.assertNotIn("a" * 13, json.dumps(out))
        self.assertEqual(["orch", "conduct", "prompt", "explain", "--run", RUN, "--item", "P2.1",
                          "--step", "executor.1-q2", "--json"], self.calls()[-1]["argv"])

    def test_traversal_params_are_refused_by_host_and_adapter_before_cli(self):
        inputs = importlib.import_module("gui.core.inputs")
        errors = importlib.import_module("gui.errors")
        query = next(query for query in GUI_DOC["queries"] if query["id"] == "gui-orch.prompt")
        for step in ("../x", "a/b", "executor.1/../../x", "executor.1\n", "A"):
            params = {"run_id": RUN, "item": "P2.1", "step": step}
            with self.subTest(step=step), self.assertRaises(errors.GuiError):
                inputs.validate(query["params"], params, str(self.project), pointer="/params")
            self.refused(query["id"], "ORCH_CONTEXT_MISSING", params=params)
        self.refused(query["id"], "ORCH_CONTEXT_MISSING", params={"run_id": RUN, "item": "../x", "step": "scout"})
        self.assertEqual([], self.calls())

    def test_budget_has_ids_numeric_values_valid_statuses_and_incomplete_warning(self):
        out = self.ok("gui-orch.budget", params={"run_id": RUN})
        metrics = {metric["id"]: metric for metric in out["metrics"]}
        self.assertEqual(1540, metrics["run"]["value"])
        self.assertIn("no limit", metrics["run"]["label"])
        self.assertEqual("warn", metrics["item.0.tokens_max"]["status"])
        self.assertEqual("ok", metrics["item.0.tokens_hard_max"]["status"])
        self.assertEqual("warn", metrics["item.1.tokens_hard_max"]["status"])
        self.assertEqual("warn", metrics["usage_incomplete"]["status"])
        self.assertIn("totals may be understated", metrics["usage_incomplete"]["label"])
        self.assertEqual(len(metrics), len(out["metrics"]))

    def test_gates_are_cli_data_with_only_known_provider_repair(self):
        out = self.ok("gui-orch.gates")
        row = out["rows"][0]
        self.assertEqual(("codex", "warn"), (row["id"], row["status"]))
        self.assertEqual({"command": "gui-orch.gates-clear", "input": {"provider": "codex"}}, row["repair"])
        self.assertEqual(["orch", "conduct", "gates", "--json"], self.calls()[0]["argv"])
        result = self.query("gui-orch.gates-clear")
        self.assertEqual("ORCH_UNKNOWN_QUERY", result.code)

    def test_display_redacts_before_cutting_and_removes_ansi(self):
        sys.path.insert(0, str(BRIDGE))
        self.addCleanup(sys.path.remove, str(BRIDGE))
        adapter = importlib.import_module("adapter")
        token = "sk-" + "A" * 70
        self.assertEqual("‹redacted›", adapter.safe_text(token, 64))
        self.assertEqual("‹redacted›", adapter.safe_text("\x1b[31m" + token + "\x1b[0m", 64))
        long = adapter.safe_text(token + " " + "x" * 800, 64)
        self.assertEqual(64, len(long))
        self.assertNotIn("sk-", long)
        self.assertEqual("‹redacted›", adapter.md_text(token))
        with mock.patch.object(adapter, "orch_json", return_value={"gates": [{"provider": token, "code": token}]}):
            out = adapter.gates(str(self.project), 10)
        self.assertNotIn(token[:20], json.dumps(out))
        self.assertNotIn("repair", out["rows"][0])
        with mock.patch.object(adapter, "orch_json", return_value={}):
            out = adapter.budget(str(self.project), 10, context={}, params={"run_id": RUN})
        self.assertEqual("unknown", out["metrics"][0]["status"])
        self.assertEqual([], contracts.validate(out, "view-data"))
        with mock.patch.object(adapter, "orch_json", return_value={"blocks": [
                {"kind": "input", "origin": {"text": "PRIVATE"}, "sha256": {"text": "PRIVATE"}}]}):
            out = adapter.prompt(str(self.project), 10, context={}, params={"run_id": RUN, "item": "P2.1", "step": "scout"})
        self.assertNotIn("PRIVATE", json.dumps(out))
        with mock.patch.object(adapter, "orch_json", return_value={"items": [
                {"item": "A" * 64, "tokens": {"input": 1}}, {"item": "A" * 63 + "B", "tokens": {"input": 2}}]}):
            out = adapter.budget(str(self.project), 10, context={}, params={"run_id": RUN})
        self.assertEqual(len(out["metrics"]), len({metric["id"] for metric in out["metrics"]}))
        self.assertTrue(all(len(metric["label"]) <= 64 for metric in out["metrics"]))
        self.assertTrue(all("limit unknown" in metric["label"] for metric in out["metrics"]))

    def test_prompt_and_routes_never_show_a_secret_of_the_environment_the_argv_or_a_block(self):
        """W6: a secret in the environment, in the argv of a route and in the text of a prompt block stays out of the
        answers of ``prompt`` and ``routes``: the projection takes named fields only and redacts what it shows."""
        sys.path.insert(0, str(BRIDGE))
        self.addCleanup(sys.path.remove, str(BRIDGE))
        adapter = importlib.import_module("adapter")
        env_secret = "envsecret-" + "Q" * 30
        argv_secret = "sk-" + "B" * 60
        block_secret = "ghp_" + "C" * 36
        route = {"provider": "codex", "model": env_secret, "effort": "high", "class": "frontier",
                 "argv": ["codex", "--api-key", argv_secret], "env": {"OPENAI_API_KEY": env_secret}}
        status = {"items": [{"item": "P2.1", "routes": {"executor": route, "reviewer": dict(route, argv=[argv_secret])}}]}
        explained = {"available_now": {"available": False, "route": route,
                                       "stop": {"code": "PROVIDER_QUOTA", "message": f"gated {env_secret} {argv_secret}"}}}

        def fake(args, root, timeout_s):
            return explained if args[:2] == ["route", "explain"] else status

        with mock.patch.dict(os.environ, {"MY_SERVICE_TOKEN": env_secret}), \
                mock.patch.object(adapter, "orch_json", side_effect=fake):
            out = adapter.routes(str(self.project), 10, context={}, params={"run_id": RUN, "item": "P2.1"})
        shown = json.dumps(out)
        for secret in (env_secret, argv_secret):
            self.assertNotIn(secret[:16], shown)
        self.assertEqual([], contracts.validate(out, "view-data"))
        manifest = {"blocks": [{"kind": "input", "origin": f"file:{env_secret}", "tokens": 10, "sha256": "a" * 64,
                                "text": f"use {block_secret} and {argv_secret}", "argv": [argv_secret]},
                               {"kind": "stub", "origin": block_secret, "tokens": 1, "sha256": "b" * 64}],
                    "excluded": [{"kind": "skill", "reason": f"too big {block_secret}"}],
                    "budgets": {"core": {"tokens": 11}}}
        with mock.patch.dict(os.environ, {"MY_SERVICE_TOKEN": env_secret}), \
                mock.patch.object(adapter, "orch_json", return_value=manifest):
            out = adapter.prompt(str(self.project), 10, context={}, params={"run_id": RUN, "item": "P2.1", "step": "executor.1"})
        shown = json.dumps(out)
        for secret in (env_secret, argv_secret, block_secret):
            self.assertNotIn(secret[:16], shown)
        self.assertEqual([], contracts.validate(out, "view-data"))

    def test_the_timeline_comes_from_the_orch_cli_newest_first(self):
        out = self.ok("gui-orch.timeline", params={"run_id": RUN})
        self.assertEqual(["conduct", "timeline", "--run", RUN, "--json"], self.calls()[-1]["argv"][1:])
        self.assertEqual([entry["kind"] for entry in out["entries"]], ["step.open", "step.done", "step.interrupted"])
        self.assertEqual([entry["title"] for entry in out["entries"]][1:], ["P2.1 executor.1", "P2.1 executor.1"])
        self.assertIn("no end", out["entries"][0]["detail"])
        self.assertIn("299 s", out["entries"][2]["detail"])
        self.assertNotIn("sk-TTTT", json.dumps(out))  # the detail is redacted
        self.ok("gui-orch.timeline", params={"run_id": RUN, "item": "P2.1"})
        self.assertEqual(["--item", "P2.1"], self.calls()[-1]["argv"][5:7])

    def test_isolated_plugin_locates_redaction_via_the_hub_registry(self):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home),
               "SKM_UMBRELLA": str(FIXTURES / "umbrella-ok"), "FAKE_AICORE_ROOT": os.environ["AICORE_ROOT"]}
        request = {"protocol": "1", "op": "invoke", "point": "gui:query", "context": {"project_root": str(self.project)},
                   "input": {"id": "gui-orch.runs", "params": {}}}
        result = subprocess.run([sys.executable, "-I", str(BRIDGE / "adapter.py")], input=json.dumps(request),
                                text=True, capture_output=True, env=env, cwd=str(self.project), timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        doc = json.loads(result.stdout)
        self.assertEqual("ok", doc["status"])
        self.assertEqual([], contracts.validate(doc["output"], "view-data"))
        self.assertIn(["units", "list", "--json"], [call["argv"] for call in self.calls()])


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
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "SKM_UMBRELLA": str(FIXTURES / "umbrella-ok"),
               "AICORE_ROOT": os.environ["AICORE_ROOT"]}
        result = invoke_one(self.plugin, "gui:command", {"id": "gui-orch.resume", "context": {}, "input": {}}, env=env,
                            project=str(self.project))
        self.assertEqual("error", result.status)

    def test_every_declared_query_is_answered(self):
        for query in GUI_DOC["queries"]:
            values = {"run_id": RUN, "item": "P2.1", "step": "executor.1"}
            params = {p["name"]: values[p["name"]] for p in query.get("params", []) if p["required"]}
            with self.subTest(query=query["id"]):
                self.ok(query["id"], params=params)

    def test_example_input_of_the_manifest_works_without_a_project(self):
        manifest = json.loads((BRIDGE / "extension.json").read_text(encoding="utf-8"))
        result = self.query(manifest["example_input"]["id"], project=False, params=manifest["example_input"]["params"])
        self.assertEqual("ok", result.status, (result.code, result.error))


if __name__ == "__main__":
    unittest.main()
