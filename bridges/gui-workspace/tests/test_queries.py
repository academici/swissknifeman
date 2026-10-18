"""gui-workspace adapter through the aicore plugin protocol: against a fake workspace command line (fixtures) and one
scenario against the real one (init -> attach -> overview) in a throwaway SKM_HOME and SKM_WORKSPACE_ROOT."""
import importlib
import json
import os
import shutil
import subprocess
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


class AdapterCase(unittest.TestCase):
    def setUp(self):
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.home, True)
        manifest = load_manifest(BRIDGE / "extension.json")
        self.plugin = Registration(id=manifest.id, manifest_path=str(BRIDGE / "extension.json"), trusted=True,
                                   timeout_seconds=30, enabled=True, manifest=manifest, problem=None)
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.home),
                    "SKM_WORKSPACE_MODULE_ROOT": str(FIXTURES / "module")}

    def query(self, query_id, **extra):
        env = {**self.env, **{k: v for k, v in extra.items() if not k.startswith("FAKE_")}}
        (self.home / "fake.json").write_text(json.dumps({k: v for k, v in extra.items() if k.startswith("FAKE_")}))
        return invoke_one(self.plugin, "gui:query", {"id": query_id, "context": {}, "params": {}}, env=env)

    def ok(self, query_id, **extra):
        result = self.query(query_id, **extra)
        self.assertEqual("ok", result.status, (result.code, result.error))
        self.assertEqual([], contracts.validate(result.output, "view-data"))
        self.assertEqual(RETURNS[query_id], result.output["view"])
        return result.output


class TestQueries(AdapterCase):
    def test_every_query_answers_its_view(self):
        for query_id in RETURNS:
            with self.subTest(query=query_id):
                self.ok(query_id)

    def test_overview_metrics(self):
        metrics = {m["id"]: (m["value"], m["status"]) for m in self.ok("gui-workspace.overview")["metrics"]}
        self.assertEqual((2, "ok"), metrics["projects"])
        self.assertEqual((1, "warn"), metrics["bound"])
        self.assertEqual((2, "warn"), metrics["dirty"])
        self.assertEqual((1, "ok"), metrics["ahead"])
        self.assertEqual((1, "ok"), metrics["remote"])
        self.assertEqual((1, "warn"), metrics["publish"])

    def test_overview_publish_block_is_a_failure(self):
        metrics = {m["id"]: (m["value"], m["status"]) for m in
                   self.ok("gui-workspace.overview", FAKE_PUBLISH="block")["metrics"]}
        self.assertEqual((2, "fail"), metrics["publish"])

    def test_projects_merge_list_and_status(self):
        rows = {row["id"]: row["cells"] for row in self.ok("gui-workspace.projects")["rows"]}
        self.assertEqual({"name": "alpha", "status": "active", "bound": "yes", "paths": "/work/alpha", "paths_json": '["/work/alpha"]',
                          "plans_store": "workspace", "plans": 3}, rows["p-alpha"])
        self.assertEqual(("no", "-", "legacy"), (rows["p-beta"]["bound"], rows["p-beta"]["paths"],
                                                 rows["p-beta"]["plans_store"]))

    def test_migration_rows_and_actions(self):
        rows = {row["id"]: row for row in self.ok("gui-workspace.migration")["rows"]}
        self.assertEqual("warn", rows["/work/alpha"]["status"])
        self.assertEqual({"command": "gui-workspace.migrate-plan", "input": {"project": "/work/alpha"}},
                         rows["/work/alpha"]["repair"])
        self.assertEqual("ok", rows["/work/clean"]["status"])
        self.assertNotIn("repair", rows["/work/clean"])
        self.assertEqual("fail", rows["/work/bad"]["status"])

    def test_sync_shows_target_and_publish_report(self):
        rows = {row["id"]: row for row in self.ok("gui-workspace.sync")["rows"]}
        self.assertIn("https://example.com/team/plans.git", rows["push-target"]["detail"])
        self.assertIn("branch main", rows["push-target"]["detail"])
        self.assertEqual("warn", rows["publish"]["status"])
        self.assertEqual("fail", rows["last-operation"]["status"])
        blocked = self.ok("gui-workspace.sync", FAKE_PUBLISH="block")["rows"]
        self.assertEqual(["fail"], [row["status"] for row in blocked if row["id"].startswith("fail-")])

    def test_sync_without_remote_offers_no_push(self):
        rows = {row["id"]: row for row in self.ok("gui-workspace.sync", FAKE_BARE="1")["rows"]}
        self.assertEqual("warn", rows["push-target"]["status"])
        self.assertNotIn("repair", rows["push-target"])

    def test_conflicts(self):
        rows = self.ok("gui-workspace.conflicts")["rows"]
        self.assertEqual(2, len(rows))
        self.assertEqual({"path": "projects/p-alpha/plans/a/plan.json", "project": "p-alpha", "plan": "a",
                          "ref": "plan.json", "decision": "local"}, rows[0]["cells"])
        self.assertEqual("-", rows[1]["cells"]["decision"])

    def test_userinfo_in_an_answer_is_refused(self):
        for query_id in RETURNS:
            with self.subTest(query=query_id):
                if query_id == "gui-workspace.migration":
                    continue  # does not read the status
                result = self.query(query_id, FAKE_LEAK="1")
                self.assertEqual("error", result.status)
                self.assertNotIn("token123", json.dumps([result.code, result.error]))

    def test_cli_failure_and_missing_cli(self):
        result = self.query("gui-workspace.overview", SKM_WORKSPACE_MODULE_ROOT=str(self.home))
        self.assertEqual("error", result.status)
        self.env.pop("SKM_WORKSPACE_MODULE_ROOT")
        result = self.query("gui-workspace.overview")
        self.assertEqual("error", result.status)

    def test_unknown_query(self):
        self.assertEqual("error", self.query("gui-workspace.nope").status)


class TestRealCli(AdapterCase):
    """init -> attach -> overview with the real workspace command line."""

    def setUp(self):
        super().setUp()
        module = os.environ.get("SKM_WORKSPACE_MODULE_ROOT")
        if not module or not (Path(module) / "bin" / "workspace").is_file() or not shutil.which("git"):
            self.skipTest("the workspace module or git is not available")
        self.env.update({"SKM_WORKSPACE_MODULE_ROOT": module, "SKM_HOME": str(self.home / "skm"),
                         "SKM_WORKSPACE_ROOT": str(self.home / "ws")})
        for name in ("AICORE_ROOT", "GIT_CONFIG_GLOBAL"):
            if os.environ.get(name):
                self.env[name] = os.environ[name]
        self.proc_env = {**os.environ, **self.env}
        self.proc_env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})

    def cli(self, *args):
        done = subprocess.run([str(Path(self.env["SKM_WORKSPACE_MODULE_ROOT"]) / "bin" / "workspace"), *args, "--json"],
                              env=self.proc_env, capture_output=True, text=True, timeout=120)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def test_init_attach_overview(self):
        project = self.home / "proj"
        project.mkdir()
        self.assertTrue(self.cli("init")["root"])
        self.assertTrue(self.cli("project", "attach", "--project", str(project), "--yes")["project_id"])
        metrics = {m["id"]: m["value"] for m in self.ok("gui-workspace.overview")["metrics"]}
        self.assertEqual((1, 1), (metrics["projects"], metrics["bound"]))
        rows = self.ok("gui-workspace.projects")["rows"]
        self.assertEqual(1, len(rows))
        self.assertEqual("yes", rows[0]["cells"]["bound"])


if __name__ == "__main__":
    unittest.main()
