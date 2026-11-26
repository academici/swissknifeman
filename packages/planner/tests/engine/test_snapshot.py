"""Import/export and orchestration contracts across a real plan graph."""
import copy
import json
from pathlib import Path
import shutil
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from planner.plan import check, context, ops, snapshot, units, views
from planner.plan.model import PlanError
try:
    from .test_units import UnitCase
except ImportError:
    from test_units import UnitCase


class SnapshotTests(UnitCase):
    def test_snapshot_round_trip_and_evidence_preservation(self):
        value = snapshot.export(self.load())
        target = self.plans / "2026.10.07-№2-COPY"
        value["plan"]["id"], value["plan"]["short_id"] = target.name, "PLAN2"
        target.mkdir()
        (target / "evidence.txt").write_text("existing evidence")
        (target / ".ignore").write_text("private/\n")
        restored = snapshot.import_snapshot(target, value)
        self.assertEqual(snapshot.export(restored), value)
        self.assertEqual(views.render_all(restored, check=True), [])
        self.assertEqual((target / "evidence.txt").read_text(), "existing evidence")
        self.assertIn("private/\n", (target / ".ignore").read_text())
        self.assertIn("*.md\n", (target / ".ignore").read_text())
        self.assertEqual((target / ".gitattributes").read_text(), "log.jsonl merge=union\n")
        self.assertEqual([i for i in check.check(restored) if i.level == "error"], [])
        with self.assertRaises(PlanError) as caught:
            snapshot.import_snapshot(target, value)
        self.assertEqual(caught.exception.code, "PLAN_EXISTS")

    def test_invalid_import_does_not_change_existing_files(self):
        value = snapshot.export(self.load())
        value["items"][0]["depends_on"] = ["P99.1"]
        before = self.tree()
        with self.assertRaises(PlanError):
            snapshot.import_snapshot(self.root, value, replace=True)
        self.assertEqual(self.tree(), before)

    def test_duplicate_ids_and_escaping_paths_are_refused(self):
        value = snapshot.export(self.load())
        for change in (lambda v: v["items"].append(copy.deepcopy(v["items"][0])),
                       lambda v: v["items"][0].update(task_files=[{"path": "../escape", "change": "any"}])):
            probe = copy.deepcopy(value)
            change(probe)
            with self.assertRaises(PlanError):
                snapshot.import_snapshot(self.root, probe, replace=True)

    def test_failed_publish_restores_the_previous_directory(self):
        value, before = snapshot.export(self.load()), self.tree()
        original = snapshot.os.replace
        def fail(source, target):
            if Path(source).name == self.root.name and Path(source).parent.name.startswith(".snapshot-"):
                raise OSError("simulated publication failure")
            original(source, target)
        with mock.patch.object(snapshot.os, "replace", side_effect=fail):
            with self.assertRaises(OSError):
                snapshot.import_snapshot(self.root, value, replace=True)
        self.assertEqual(self.tree(), before)

    def test_transaction_refuses_bad_graph_and_accepts_coordinated_edits(self):
        before = self.tree()
        with self.assertRaises(PlanError):
            ops.apply(self.root, [{"ref": "P1.1", "patch": {"depends_on": ["P1.2"]}},
                                  {"ref": "P1.2", "patch": {"depends_on": ["P1.1"]}}])
        self.assertEqual(self.tree(), before)
        ops.apply(self.root, [{"ref": "P1.1", "patch": {"guidance": "full instructions"}},
                              {"ref": "P1.2", "patch": {"depends_on": ["P1.1"]}}])
        self.assertEqual(self.load().items["P1.1"]["guidance"], "full instructions")

    def test_missing_views_do_not_block_json_execution(self):
        shutil.rmtree(self.root / "views")
        self.assertEqual([i for i in check.check(self.load()) if i.level == "error"], [])
        self.assertEqual(context.collect(self.load(), "P1.1")["item"]["id"], "P1.1")

    def test_import_preserves_legacy_id_without_inventing_short_id(self):
        value = snapshot.export(self.load())
        target = self.plans / "FLEX-2"
        value["plan"]["id"], value["plan"]["short_id"] = target.name, None
        restored = snapshot.import_snapshot(target, value)
        self.assertEqual(restored.plan["id"], "FLEX-2")
        self.assertIsNone(restored.plan["short_id"])
        self.assertEqual(context.collect(restored, "P1.1")["ref"], "FLEX-2.P1.1")
        self.assertEqual([i for i in check.check(restored) if i.level == "error"], [])

    def test_proposed_decision_is_distinct_and_requires_a_complete_proposal(self):
        value = snapshot.export(self.load())
        decision = {"$schema": "urn:swissknifeman:task:plan:decision:v1", "id": "D1",
                    "title": "Publication identity", "date": "2026-10-05", "status": "proposed",
                    "decision": "Keep the release private.",
                    "rationale": "Public identity has not been accepted.",
                    "actor": {"provider": "codex", "model": "gpt-6"}}
        value["decisions"].append(decision)
        restored = snapshot.import_snapshot(self.plans / "2026.10.07-№2-PROPOSAL",
                                            {**value, "plan": {**value["plan"],
                                                               "id": "2026.10.07-№2-PROPOSAL",
                                                               "short_id": "PLAN2"}})
        self.assertEqual(restored.decisions[decision["id"]]["status"], "proposed")
        broken = snapshot.export(restored)
        broken["decisions"][0].pop("rationale")
        broken["plan"]["id"], broken["plan"]["short_id"] = "2026.10.07-№3-BROKEN", "PLAN3"
        with self.assertRaises(PlanError):
            snapshot.import_snapshot(self.plans / "2026.10.07-№3-BROKEN", broken)


class OrchestrationTests(UnitCase):
    def test_prepare_then_read_only_review_and_exact_route(self):
        self.add("Prepare", {"files": [], "kind": "preparation", "route": {"class": "economy", "effort": "low"}})
        self.add("Review", {"files": [], "kind": "review", "depends_on": ["U1"],
                            "route": {"class": "frontier", "effort": "max", "provider": "codex", "model": "selected",
                                      "settings": {"fresh_context": True}}})
        self.assertEqual([d["ref"] for d in units.ready(self.load(), "P1.1")], ["P1.1/U1"])
        units.dispatch(self.root, "P1.1", "U1", "claude-code/haiku/low")
        units.return_unit(self.root, "P1.1", "U1", notes="prepared")
        units.accept(self.root, "P1.1", "U1")
        self.assertEqual(units.ready(self.load(), "P1.1")[0]["kind"], "review")
        self.refused("ROUTE_MISMATCH", units.dispatch, "P1.1", "U2", "codex/other/max")
        path = units.dispatch(self.root, "P1.1", "U2", "codex/selected/max")
        self.assertEqual(json.loads(path.read_text())["unit"]["route"]["settings"], {"fresh_context": True})

    def test_sequential_policy_and_nested_children(self):
        ops.set_plan(self.root, {"orchestration": {"strategy": "sequential"}})
        self.add("One", {"files": []})
        self.add("Two", {"files": []})
        self.assertEqual([d["ref"] for d in units.ready(self.load(), "P1.1")], ["P1.1/U1"])
        self.add("Child", {"files": [], "parent": "U1"})
        self.assertEqual([d["ref"] for d in units.ready(self.load(), "P1.1")], ["P1.1/U3"])
        self.refused("UNIT_INVALID", units.add_unit, "P1.1", "Bad", {"files": [], "parent": "U99"})

    def test_unstarted_units_block_completion(self):
        self.add("Still owed", {"files": []})
        self.refused("UNITS_OPEN", __import__('planner.plan.lifecycle', fromlist=['finish']).finish,
                     "P1.1", "done", checks={"V1": 0})
