"""gui-planner adapter through the aicore plugin protocol against a fake planner command line: every answer is
view-data/v1 of the declared view; board, graph, timeline, raw, empty and broken projects, failures."""
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
PLAN = "PLAN1"


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
        (self.home / "aicore-root").write_text(os.environ["AICORE_ROOT"], encoding="utf-8")  # for the model catalog
        manifest = load_manifest(BRIDGE / "extension.json")
        self.plugin = Registration(id=manifest.id, manifest_path=str(BRIDGE / "extension.json"), trusted=True,
                                   timeout_seconds=30, enabled=True, manifest=manifest, problem=None)

    def query(self, query_id, *, umbrella="umbrella-ok", params=None, context=None, project=True):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "SKM_UMBRELLA": str(FIXTURES / umbrella)}
        given = {"plan_id": PLAN, **(context or {})}
        return invoke_one(self.plugin, "gui:query", {"id": query_id, "context": given, "params": params or {}},
                          env=env, project=str(self.project) if project else None)

    def ok(self, query_id, **kwargs):
        result = self.query(query_id, **kwargs)
        self.assertEqual("ok", result.status, (result.code, result.error))
        self.assertEqual([], contracts.validate(result.output, "view-data"))
        self.assertEqual(RETURNS[query_id], result.output["view"])
        self.assertEqual([], floats(result.output), "the backend's canonical JSON has no floats")
        return result.output

    def calls(self):
        return [json.loads(line) for line in (self.home / "umbrella.log").read_text(encoding="utf-8").splitlines()]


class TestQueries(AdapterCase):
    def test_every_query_answers_its_view(self):
        for query_id in RETURNS:
            with self.subTest(query=query_id):
                self.ok(query_id, context={"item_id": "P2.2"}, params={"plan_id": PLAN, "item_id": "P2.2", "ref": "P2.2", "phase": "P2"})

    def test_plans_list_moves_the_progress_of_the_planner(self):
        out = self.ok("gui-planner.plans")
        row = out["rows"][0]
        self.assertEqual("2026.10.16-№1-DEMO", row["id"])
        self.assertEqual({"name": "Demo plan", "status": "active", "progress": 42, "phases": "1/2"}, row["cells"])
        self.assertEqual({"route": "gui-planner.overview", "params": {"plan_id": row["id"]}}, row["link"])
        self.assertEqual([["--output", "json", "plans"]], [c["argv"][1:] for c in self.calls()])
        self.assertEqual(str(self.project), self.calls()[0]["cwd"])

    def test_empty_project_and_broken_plan(self):
        self.assertEqual([], self.ok("gui-planner.plans", umbrella="umbrella-empty")["rows"])
        rows = self.ok("gui-planner.plans", umbrella="umbrella-broken")["rows"]
        self.assertEqual(2, len(rows))
        self.assertIn("unreadable: PLAN_INVALID", rows[0]["cells"]["name"])
        self.assertNotIn("link", rows[0])
        self.assertEqual("active", rows[1]["cells"]["status"])

    def test_overview(self):
        out = self.ok("gui-planner.overview")
        fields = {f["label"]: f["value"] for f in out["fields"]}
        self.assertEqual("PLAN1 2026.10.16-№1-DEMO", fields["Plan"])
        self.assertEqual("3/7 items, 1/2 phases closed", fields["Progress"])
        self.assertEqual("run-items: P2.1", fields["Next"])
        self.assertEqual(["Goal", "Context", "Rules"], [s["title"] for s in out["sections"]])
        self.assertEqual("- Rule one\n- Rule two", out["sections"][2]["markdown"])

    def test_phases(self):
        rows = {r["id"]: r for r in self.ok("gui-planner.phases")["rows"]}
        self.assertEqual({"phase": "P1", "title": "Phase P1", "design": "detailed", "result": "done", "progress": 100,
                          "items": "2/2"}, rows["P1"]["cells"])
        self.assertEqual(("open", "1/5"), (rows["P2"]["cells"]["result"], rows["P2"]["cells"]["items"]))
        self.assertEqual("gui-planner.board", rows["P2"]["link"]["route"])

    def test_board_has_a_column_per_status_and_other_for_unknown(self):
        columns = {c["id"]: c for c in self.ok("gui-planner.board")["columns"]}
        self.assertEqual(["todo", "in_progress", "blocked", "done", "done_with_deviations", "skipped", "other"],
                         list(columns))
        cards = {col: [c["id"] for c in columns[col]["cards"]] for col in columns}
        self.assertEqual({"todo": ["P2.1"], "in_progress": ["P2.2"], "blocked": ["P2.3"], "done": ["P1.1"],
                          "done_with_deviations": ["P2.5"], "skipped": ["P1.2"], "other": ["P2.4"]}, cards)
        statuses = {c["id"]: c["status"] for col in columns.values() for c in col["cards"]}
        self.assertEqual({"P1.1": "ok", "P1.2": "ok", "P2.1": "unknown", "P2.2": "warn", "P2.3": "fail", "P2.4": "unknown",
                          "P2.5": "ok"}, statuses)
        card = columns["in_progress"]["cards"][0]
        self.assertEqual(("P2", {"route": "gui-planner.item", "params": {"plan_id": PLAN, "item_id": "P2.2"}}),
                         (card["subtitle"], card["link"]))

    def test_board_without_other_and_filtered_by_phase(self):
        columns = self.ok("gui-planner.board", params={"phase": "P1"})["columns"]
        self.assertEqual(["todo", "in_progress", "blocked", "done", "done_with_deviations", "skipped"],
                         [c["id"] for c in columns])
        self.assertIn(["list", PLAN, "item", "--phase", "P1"], [c["argv"][3:] for c in self.calls()])

    def test_card_titles_are_plain_text(self):
        titles = [c["title"] for col in self.ok("gui-planner.board")["columns"] for c in col["cards"]]
        self.assertIn("Form red <script>alert(1)</script>", titles)  # kept as text: the host renders it as text
        self.assertFalse(any("\x1b" in t for t in titles))

    def test_graph_blocks_related_and_dropped_edges(self):
        out = self.ok("gui-planner.graph")
        self.assertEqual({"P1.1", "P1.2", "P2.1", "P2.2", "P2.3", "P2.4", "P2.5"}, {n["id"] for n in out["nodes"]})
        node = {n["id"]: n for n in out["nodes"]}["P2.2"]
        self.assertEqual(("P2", "warn"), (node["group"], node["status"]))
        edges = {(e["from"], e["to"], e["kind"]) for e in out["edges"]}
        self.assertEqual({("P1.1", "P1.2", "blocks"), ("P1.1", "P2.2", "blocks"), ("P2.1", "P2.2", "blocks"),
                          ("P2.2", "P2.3", "blocks"), ("P2.4", "P2.5", "blocks"), ("P2.3", "P2.1", "related")}, edges)
        self.assertEqual(len(out["edges"]), len(edges))

    def test_graph_of_one_phase_drops_edges_to_other_phases(self):
        out = self.ok("gui-planner.graph", params={"phase": "P2"})
        self.assertNotIn("P1.1", {n["id"] for n in out["nodes"]})
        self.assertNotIn(("P1.1", "P2.2"), {(e["from"], e["to"]) for e in out["edges"]})
        self.assertIn(("P2.1", "P2.2"), {(e["from"], e["to"]) for e in out["edges"]})

    def test_item(self):
        out = self.ok("gui-planner.item", context={"item_id": "P2.2"}, params={"item_id": "P2.2"})
        fields = {f["label"]: f["value"] for f in out["fields"]}
        self.assertEqual("implementation / medium", fields["Route"])
        self.assertEqual("requested / frontier / codex / gpt-x / high", fields["Review"])
        self.assertEqual(("in_progress", "P1.1, P2.1", "routine"), (fields["Status"], fields["Depends on"], fields["Authority"]))
        self.assertEqual(["Summary", "Why"], [s["title"] for s in out["sections"]])
        done = self.ok("gui-planner.item", context={"item_id": "P1.1"})
        result = [s for s in done["sections"] if s["title"] == "Result"][0]["markdown"]
        self.assertIn("All good.", result)
        self.assertIn("moved a file", result)
        self.assertIn("follow_up(docs): wording", result)

    def test_decisions(self):
        rows = {r["id"]: r["cells"] for r in self.ok("gui-planner.decisions")["rows"]}
        self.assertEqual({"id": "D1", "title": "Stack", "status": "accepted", "date": "2026-10-16"}, rows["D1"])
        self.assertIsNone(rows["D2"]["date"])

    def test_evidence_lists_checks_artifacts_and_is_empty_without_data(self):
        rows = self.ok("gui-planner.evidence", context={"item_id": "P1.1"})["rows"]
        self.assertEqual(["check", "artifact", "evidence"], [r["cells"]["kind"] for r in rows])
        self.assertEqual("exit 0", rows[0]["cells"]["outcome"])
        self.assertEqual([], self.ok("gui-planner.evidence", context={"item_id": "P2.1"})["rows"])

    def test_timeline_is_newest_first_and_skips_bad_timestamps(self):
        entries = self.ok("gui-planner.timeline")["entries"]
        self.assertEqual(["2026-10-16T11:00:00Z", "2026-10-16T10:00:00Z", "2026-10-16T09:00:00Z"],
                         [e["at"] for e in entries])
        self.assertEqual(("odd-type", "plan level note"), (entries[0]["kind"], entries[0]["title"]))
        self.assertNotIn("link", entries[0])
        self.assertEqual("actor orch/conductor", entries[1]["detail"])
        self.assertEqual("gui-planner.item", entries[1]["link"]["route"])
        only = self.ok("gui-planner.timeline", params={"item": "P1.1"})["entries"]
        self.assertEqual(2, len(only))
        self.assertTrue(any(["--item", "P1.1"] == c["argv"][-2:] for c in self.calls()))

    def test_raw_is_a_fenced_json_block_longer_than_any_backtick_run_of_the_content(self):
        out = self.ok("gui-planner.raw", params={"ref": "plan"})
        text = out["text"]
        self.assertTrue(text.startswith("File: `2026.10.16-№1-DEMO/plan.json` (read-only)\n\n````json\n"), text)
        self.assertTrue(text.endswith("\n````"))
        self.assertIn("Ship the demo.", text)
        path = self.ok("gui-planner.raw", params={"ref": "P2.2"})["text"]
        self.assertIn("`2026.10.16-№1-DEMO/phases/P2/P2.2.json`", path)
        self.assertIn("decisions/D1.json", self.ok("gui-planner.raw", params={"ref": "D1"})["text"])

    def test_raw_refuses_a_ref_outside_the_pattern(self):
        for ref in ("../etc", "knowledge/x", "P1.1/U1", "", None):
            with self.subTest(ref=ref):
                self.assertEqual("PLANNER_CONTEXT_MISSING", self.query("gui-planner.raw", params={"ref": ref}).code)


class TestFailures(AdapterCase):
    def test_planner_refusal_keeps_its_code(self):
        for query_id in ("gui-planner.overview", "gui-planner.board", "gui-planner.timeline"):
            with self.subTest(query=query_id):
                result = self.query(query_id, umbrella="umbrella-missing")
                self.assertEqual(("error", "PLAN_NOT_FOUND"), (result.status, result.code))

    def test_cli_failure_and_garbage_are_planner_cli_failed(self):
        for umbrella in ("umbrella-fail", "umbrella-garbage"):
            for query_id in ("gui-planner.plans", "gui-planner.overview"):
                with self.subTest(umbrella=umbrella, query=query_id):
                    result = self.query(query_id, umbrella=umbrella)
                    self.assertEqual(("error", "PLANNER_CLI_FAILED"), (result.status, result.code))
                    self.assertNotIn("\x1b", result.error)
                    self.assertNotIn("Traceback", result.error)

    def test_missing_umbrella_is_planner_unavailable(self):
        result = self.query("gui-planner.plans", umbrella="no-such-umbrella")
        self.assertEqual(("error", "PLANNER_UNAVAILABLE"), (result.status, result.code))

    def test_missing_context(self):
        self.assertEqual("PLANNER_CONTEXT_MISSING", self.query("gui-planner.overview", project=False).code)
        self.assertEqual("ok", self.query("gui-planner.plans", project=False).status)  # conformance probe
        self.assertEqual("PLANNER_CONTEXT_MISSING", self.query("gui-planner.item").code)  # no item_id
        self.assertEqual("PLANNER_CONTEXT_MISSING", self.query("gui-planner.board", context={"plan_id": "bad"}).code)
        self.assertEqual("PLANNER_CONTEXT_MISSING", self.query("gui-planner.board", params={"phase": "x"}).code)

    def test_unknown_query(self):
        self.assertEqual("PLANNER_UNKNOWN_QUERY", self.query("gui-planner.nope").code)


if __name__ == "__main__":
    unittest.main()
