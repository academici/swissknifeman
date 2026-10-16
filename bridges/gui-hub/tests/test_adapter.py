"""gui-hub adapter through the aicore plugin protocol against a fake hub command line: every answer is view-data/v1
of the declared view; layers, repairs and failures."""
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


class AdapterCase(unittest.TestCase):
    def setUp(self):
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.home, True)
        for project in ("alpha", "beta", "gamma", "delta"):
            (self.home / "fleet" / project).mkdir(parents=True)
        manifest = load_manifest(BRIDGE / "extension.json")
        self.plugin = Registration(id=manifest.id, manifest_path=str(BRIDGE / "extension.json"), trusted=True,
                                   timeout_seconds=30, enabled=True, manifest=manifest, problem=None)

    def query(self, query_id, *, umbrella="umbrella-ok", project=None):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "SKM_UMBRELLA": str(FIXTURES / umbrella)}
        return invoke_one(self.plugin, "gui:query", {"id": query_id, "context": {}, "params": {}}, env=env,
                          project=str(project) if project else None)

    def ok(self, query_id, **kwargs):
        result = self.query(query_id, **kwargs)
        self.assertEqual("ok", result.status, (result.code, result.error))
        self.assertEqual([], contracts.validate(result.output, "view-data"))
        self.assertEqual(RETURNS[query_id], result.output["view"])
        return result.output


class TestQueries(AdapterCase):
    def test_every_query_answers_its_view(self):
        for query_id in RETURNS:
            with self.subTest(query=query_id):
                self.ok(query_id, project=self.home / "fleet" / "alpha")

    def test_fleet_moves_fields_without_computing(self):
        rows = {row["id"]: row["cells"] for row in self.ok("gui-hub.fleet")["rows"]}
        self.assertEqual({"name": "Beta", "status": "partial", "trusted": "yes", "skills": 3, "packs": 2, "fixes": 1},
                         rows["beta"])
        self.assertEqual(("connected", "no", 0), (rows["delta"]["status"], rows["delta"]["trusted"], rows["delta"]["fixes"]))

    def test_fleet_summary(self):
        metrics = {m["id"]: (m["value"], m["status"]) for m in self.ok("gui-hub.fleet-summary")["metrics"]}
        self.assertEqual({"projects": (4, "ok"), "connected": (1, "ok"), "with_fixes": (3, "warn"),
                          "memory": (0, "warn")}, metrics)

    def test_layers_of_a_project(self):
        rows = self.ok("gui-hub.layers", project=self.home / "fleet" / "beta")["rows"]
        self.assertEqual(["skills", "agents", "mcp", "memory"], [row["id"] for row in rows])
        mcp = rows[2]
        self.assertEqual(("fail", {"command": "gui-hub.sync", "input": {"cap": "mcp"}}), (mcp["status"], mcp["repair"]))
        self.assertEqual({"ok"}, {row["status"] for row in rows if row["id"] != "mcp"})

    def test_only_allowlisted_sync_fixes_offer_a_repair(self):
        rows = {row["id"]: row for row in self.ok("gui-hub.layers", project=self.home / "fleet" / "gamma")["rows"]}
        self.assertEqual({"command": "gui-hub.sync", "input": {"cap": "agent-pack"}}, rows["agents"]["repair"])
        self.assertEqual(("fail", "something odd"), (rows["other"]["status"], rows["other"]["detail"]))
        self.assertNotIn("repair", rows["other"])
        alpha = {row["id"]: row for row in self.ok("gui-hub.layers", project=self.home / "fleet" / "alpha")["rows"]}
        self.assertEqual("fail", alpha["memory"]["status"])
        self.assertNotIn("repair", alpha["memory"])  # `maind start` is not a sync of the allowlist

    def test_project_not_in_maind_and_symlinked_root(self):
        outside = self.home / "elsewhere"
        outside.mkdir()
        rows = self.ok("gui-hub.layers", project=outside)["rows"]
        self.assertEqual([("project", "unknown")], [(row["id"], row["status"]) for row in rows])
        link = self.home / "link"
        link.symlink_to(self.home / "fleet" / "beta")
        rows = self.ok("gui-hub.layers", project=link)["rows"]
        self.assertEqual("fail", rows[2]["status"])

    def test_doctor_status_outside_the_enum_is_unknown_and_text_is_clean(self):
        rows = {row["id"]: row for row in self.ok("gui-hub.doctor")["rows"]}
        self.assertEqual(("ok", "warn", "skip", "unknown"), tuple(rows[c]["status"] for c in
                                                                  ("aicore.ext", "maind.memory", "orch.sandbox", "odd.check")))
        self.assertEqual("maind · maind.memory", rows["maind.memory"]["label"])
        self.assertNotIn("\x1b", rows["odd.check"]["detail"])

    def test_units(self):
        rows = {row["id"]: row["cells"] for row in self.ok("gui-hub.units")["rows"]}
        self.assertEqual({"kind": "bridge", "version": "0.1.0", "stability": "alpha", "destination": "hub"},
                         rows["gui-hub"])


class TestFailures(AdapterCase):
    def test_cli_failure_and_garbage_are_hub_cli_failed(self):
        for umbrella in ("umbrella-fail", "umbrella-garbage"):
            with self.subTest(umbrella=umbrella):
                result = self.query("gui-hub.fleet", umbrella=umbrella)
                self.assertEqual(("error", "HUB_CLI_FAILED"), (result.status, result.code))
                self.assertNotIn("\x1b", result.error)
                self.assertNotIn("Traceback", result.error)

    def test_missing_hub_is_hub_unavailable(self):
        result = self.query("gui-hub.units", umbrella="no-such-umbrella")
        self.assertEqual(("error", "HUB_UNAVAILABLE"), (result.status, result.code))

    def test_unknown_query_and_layers_without_project(self):
        self.assertEqual("HUB_UNKNOWN_QUERY", self.query("gui-hub.nope").code)
        self.assertEqual("HUB_CONTEXT_MISSING", self.query("gui-hub.layers").code)


if __name__ == "__main__":
    unittest.main()
