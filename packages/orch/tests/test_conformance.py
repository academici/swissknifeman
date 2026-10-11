"""Engine conformance: the catalogue lists every scenario, covered ones point at real proof and pass."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from orch import conformance
from orch.bindings import BINDINGS

from tests.test_cli_prepare import INPUT, MODEL_CATALOG, POLICY, CliCase

ROOT = Path(__file__).resolve().parents[1]
# The scenario list of the conformance requirement: runtime kit, agent kit and the three golden traces.
REQUIRED = {
    "resubmit-same-submission", "crash-during-effect", "nonzero-after-partial-changes", "stale-owner",
    "lock-expiry", "cancel-race", "restart-while-waiting", "full-history-replay", "unknown-version-event",
    "write-confinement", "workspace-permissions", "stdout-stderr-framing", "child-process-cleanup",
    "golden-native-claude-code-ok", "golden-native-codex-quota", "golden-native-grok-unknown",
}
PROCESS_SCENARIOS = {"workspace-permissions", "stdout-stderr-framing", "child-process-cleanup"}


def catalogue() -> dict:
    return json.loads(conformance.CATALOGUE.read_text(encoding="utf-8"))


class CatalogueTests(unittest.TestCase):
    def test_the_catalogue_is_valid(self):
        self.assertEqual(conformance.check_catalogue(catalogue()), [])

    def test_it_lists_every_required_scenario_and_nothing_else(self):
        self.assertEqual({item["id"] for item in catalogue()["scenarios"]}, REQUIRED)

    def test_golden_traces_of_the_fixtures_are_all_listed(self):
        listed = {item["ref"] for item in catalogue()["scenarios"] if item["id"].startswith("golden-")}
        self.assertEqual(listed, {p.relative_to(ROOT).as_posix() for p in (ROOT / "fixtures/traces").glob("*.jsonl")})

    def test_process_scenarios_are_declared_with_the_engine_reason(self):
        for item in catalogue()["scenarios"]:
            if item["id"] in PROCESS_SCENARIOS:
                with self.subTest(item["id"]):
                    self.assertEqual(set(item["bindings"].values()), {"declared"})
                    self.assertIn("execution engine", item["reason"])

    def test_every_binding_is_named_in_every_scenario(self):
        for item in catalogue()["scenarios"]:
            self.assertEqual(set(item["bindings"]), set(BINDINGS), item["id"])

    def test_covered_never_points_at_a_missing_file_or_test(self):
        doc = catalogue()
        for index, field, value in ((0, "ref", "tests.test_conformance.Nope.test_nope"),
                                    (1, "ref", "conformance/traces/missing.jsonl")):
            broken = copy.deepcopy(doc)
            broken["scenarios"][index][field] = value
            with self.subTest(value=value):
                issues = conformance.check_catalogue(broken)
                self.assertEqual([i["scenario"] for i in issues], [broken["scenarios"][index]["id"]])
                self.assertIn("does not exist", issues[0]["message"])

    def test_declared_and_not_applicable_need_a_reason(self):
        broken = catalogue()
        del next(item for item in broken["scenarios"] if item["id"] == "lock-expiry")["reason"]
        self.assertEqual([i["message"] for i in conformance.check_catalogue(broken)],
                         ["declared and n/a need a reason"])

    def test_structural_errors_are_reported(self):
        for doc in (None, {"schema_version": "x"}, {"schema_version": conformance.SCHEMA_VERSION, "scenarios": []}):
            self.assertTrue(conformance.check_catalogue(doc))
        broken = catalogue()
        broken["scenarios"].append(copy.deepcopy(broken["scenarios"][0]))
        broken["scenarios"][0]["bindings"].pop("cao")
        messages = [i["message"] for i in conformance.check_catalogue(broken)]
        self.assertIn("duplicate id", messages)
        self.assertTrue(any(m.startswith("bindings must name exactly") for m in messages))


class RunTests(unittest.TestCase):
    def test_every_covered_scenario_passes_on_every_binding(self):
        rows = conformance.run()
        self.assertEqual([row for row in rows if row["status"] == "fail"], [])
        self.assertEqual(len(rows), len(REQUIRED) * len(BINDINGS))

    def test_binding_filters_the_rows(self):
        for name in BINDINGS:
            with self.subTest(binding=name):
                rows = conformance.run(name)
                self.assertEqual({row["binding"] for row in rows}, {name})
                self.assertEqual({row["scenario"] for row in rows}, REQUIRED)

    def test_declared_and_not_applicable_rows_carry_their_reason(self):
        rows = {(row["scenario"], row["binding"]): row for row in conformance.run()}
        self.assertEqual(rows["lock-expiry", "native"]["status"], "n/a")
        self.assertIn("time-to-live", rows["lock-expiry", "native"]["reason"])
        self.assertEqual(rows["child-process-cleanup", "cao"]["status"], "declared")
        self.assertEqual(rows["stale-owner", "cao"]["status"], "pass")
        self.assertIsNone(rows["stale-owner", "cao"]["reason"])

    def test_unknown_binding_is_refused(self):
        with self.assertRaises(conformance.ConformanceError):
            conformance.run("nope")

    def test_a_trace_that_does_not_match_its_expectation_fails(self):
        trace = ROOT / "conformance/traces/stale-owner.jsonl"
        self.assertEqual(conformance.run_trace(trace, {"error": "STALE_EPOCH", "stages": {"primary": "running"}}), [])
        fields = [d["field"] for d in conformance.run_trace(trace, {"stages": {"primary": "completed"}})]
        self.assertEqual(fields, ["error", "stages.primary"])

    def test_a_decision_follows_the_failure_and_the_stage_inputs(self):
        trace = ROOT / "conformance/traces/nonzero-after-partial-changes.jsonl"
        expect = {"stages": {"primary": "failed"}, "inputs": {"stage_writes": True, "worktree_dirty": True},
                  "decision": "reconcile"}
        self.assertEqual(conformance.run_trace(trace, expect), [])
        expect["inputs"] = {"stage_writes": True}
        expect["decision"] = "reconcile"
        self.assertEqual([d["field"] for d in conformance.run_trace(trace, expect)], ["decision"])

    def test_a_failing_test_reference_is_reported(self):
        name = "tests.test_conformance.ScenarioTargets.test_fails_only_when_asked"
        self.assertEqual(conformance.run_test(name), [])
        with mock.patch.dict(os.environ, {"ORCH_CONFORMANCE_FAIL": "1"}):
            difference = conformance.run_test(name)
        self.assertEqual([d["field"] for d in difference], ["test"])

    def test_an_invalid_catalogue_file_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conformance" / "scenarios.json"
            path.parent.mkdir()
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(conformance.ConformanceError) as caught:
                conformance.run(path=path)
            self.assertTrue(caught.exception.issues)
            path.write_text("not json", encoding="utf-8")
            with self.assertRaises(conformance.ConformanceError):
                conformance.load(path)


class ConformanceCli(CliCase):
    def test_json_lists_the_rows_of_one_binding(self):
        code, out, err = self.run_cli("conformance", "--binding", "claude-only", "--json")
        self.assertEqual((code, err), (0, ""))
        rows = json.loads(out)
        self.assertEqual({row["binding"] for row in rows}, {"claude-only"})
        self.assertEqual({row["status"] for row in rows}, {"pass", "declared", "n/a"})

    def test_text_names_status_binding_scenario_and_reason(self):
        code, out, _ = self.run_cli("conformance", "--binding", "native")
        self.assertEqual(code, 0)
        self.assertIn("PASS\tnative\tstale-owner", out)
        self.assertIn("DECLARED\tnative\tchild-process-cleanup\tneeds the execution engine", out)

    def test_every_binding_without_a_filter(self):
        code, out, _ = self.run_cli("conformance", "--json")
        self.assertEqual(code, 0)
        self.assertEqual({row["binding"] for row in json.loads(out)}, set(BINDINGS))

    def test_an_unknown_binding_is_refused_by_the_parser(self):
        with self.assertRaises(SystemExit):
            self.run_cli("conformance", "--binding", "nope")

    def test_a_failing_scenario_exits_1(self):
        original = conformance.run_test
        conformance.run_test = lambda name, root=conformance.ROOT: [{"field": "test", "expected": "pass", "actual": "x"}]
        self.addCleanup(setattr, conformance, "run_test", original)
        code, _, err = self.run_cli("conformance", "--binding", "native")
        self.assertEqual(code, 1)
        self.assertIn("test: expected", err)


class ScenarioTargets(CliCase):
    """Tests that scenarios of the catalogue point at."""

    def test_resubmission_keeps_run_id_and_digest(self):
        plans = []
        for name in ("one", "two"):
            code, out, err = self.run_cli(
                "prepare", "--provider", "claude-code", "--input", INPUT, "--policy", POLICY,
                "--out", self.root / name, "--dry-run", "--model-catalog", MODEL_CATALOG,
                "--submission-id", "sub-1")
            self.assertEqual((code, err), (0, ""))
            plans.append(json.loads(out))
        keys = ("run_id", "input_digest", "submission_id")
        self.assertEqual({key: plans[0].get(key) for key in keys}, {key: plans[1].get(key) for key in keys})
        self.assertEqual(plans[0]["submission_id"], "sub-1")

    def test_fails_only_when_asked(self):
        if os.environ.get("ORCH_CONFORMANCE_FAIL"):
            self.fail("requested by the runner test")


if __name__ == "__main__":
    unittest.main()
