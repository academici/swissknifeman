"""parallel: footprint, conflict, wait graph and the ``dependency_deadlock`` check."""
import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import check, cli, lifecycle, parallel, schema, store  # noqa: E402
from planner.plan.model import PlanError  # noqa: E402

try:
    from . import demo
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import demo


class ParallelCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.plans = Path(tmp.name) / "plans"
        self.plans.mkdir()
        self.root = demo.make_demo_plan(self.plans)

    def plan(self):
        return store.load_plan(self.root)

    def edit(self, rel, change):
        demo.rewrite(self.root, rel, change)

    def add_phase(self, phase_id, items, depends_on=None):
        """Phase ``phase_id`` with todo items ``<phase>.<n>``; ``items`` maps item id -> its depends_on."""
        phase = copy.deepcopy(demo.fixture("phase-e2"))
        phase.update(id=phase_id, items=list(items),
                     batches=[{"id": "B1", "items": list(items), "mode": "recommended"}])
        if depends_on is not None:
            phase["depends_on"] = depends_on
        demo.write_doc(self.root / "phases" / phase_id / "phase.json", phase, "phase")
        for item_id, deps in items.items():
            item = copy.deepcopy(demo.fixture("item-e3"))
            item.update(id=item_id, title=f"Item {item_id}", status="todo", depends_on=deps, related=[],
                        decisions=[], artifacts=[], result=None)
            demo.write_doc(self.root / "phases" / phase_id / f"{item_id}.json", item, "item")
        self.edit("plan.json", lambda d: d.update(phases=[*d["phases"], phase_id]))

    def deadlock_issues(self):
        return [i for i in check.check(self.plan()) if i.code == "dependency_deadlock"]

    def cycle_issues(self):
        return [i for i in check.check(self.plan()) if i.code == "cycle"]


class FootprintTests(ParallelCase):
    def test_task_files_paths_in_declaration_order_without_duplicates(self):
        self.edit("phases/P1/P1.1.json", lambda d: d.update(task_files=[
            {"path": "b.py", "change": "modify"}, {"path": "a.py", "change": "create"},
            {"path": "b.py", "change": "modify"}]))
        self.assertEqual(parallel.footprint(self.plan(), "P1.1"), ["b.py", "a.py"])

    def test_missing_or_empty_task_files_is_unknown_not_empty(self):
        self.edit("phases/P1/P1.1.json", lambda d: d.pop("task_files", None))
        self.assertIsNone(parallel.footprint(self.plan(), "P1.1"))
        self.edit("phases/P1/P1.2.json", lambda d: d.update(task_files=[]))
        self.assertIsNone(parallel.footprint(self.plan(), "P1.2"))

    def test_malformed_entries_are_ignored(self):
        self.edit("phases/P1/P1.1.json", lambda d: d.update(task_files=[{"path": 3}, "x", {"path": "ok.py"}]))
        self.assertEqual(parallel.footprint(self.plan(), "P1.1"), ["ok.py"])
        self.edit("phases/P1/P1.2.json", lambda d: d.update(task_files="nope"))
        self.assertIsNone(parallel.footprint(self.plan(), "P1.2"))


class ConflictTests(unittest.TestCase):
    def test_directory_prefix_overlaps_inner_file(self):
        found = parallel.conflict(["lib/x/"], ["lib/x/y.py"])
        self.assertEqual(found.reason, "task_files_overlap")
        self.assertEqual(found.pairs, [("lib/x/", "lib/x/y.py")])

    def test_double_star_overlaps_below_prefix(self):
        self.assertTrue(parallel.conflict(["lib/**"], ["lib/a/b.py"]))

    def test_disjoint_globs_have_no_conflict(self):
        self.assertIsNone(parallel.conflict(["a/*.py"], ["a/b.md"]))
        self.assertIsNone(parallel.conflict(["lib/a.py"], ["lib/b.py", "tests/a.py"]))

    def test_unknown_footprint_conflicts_with_everything(self):
        for left, right in ((None, ["a.py"]), (["a.py"], None), (None, None)):
            found = parallel.conflict(left, right)
            self.assertEqual((found.reason, found.pairs), ("footprint_unknown", []))

    def test_predicate_is_symmetric(self):
        pairs = [(["lib/x/"], ["lib/x/y.py"]), (["a/*.py"], ["a/b.md"]), (["**"], ["z.py"])]
        for left, right in pairs:
            self.assertEqual(bool(parallel.conflict(left, right)), bool(parallel.conflict(right, left)))

    def test_pairs_follow_footprint_order(self):
        found = parallel.conflict(["a.py", "lib/"], ["lib/x.py", "a.py"])
        self.assertEqual(found.pairs, [("a.py", "a.py"), ("lib/", "lib/x.py")])


class WaitGraphTests(ParallelCase):
    def test_item_and_phase_edges(self):
        self.add_phase("P2", {"P2.1": ["P1.2"], "P2.2": []})
        graph = parallel.wait_graph(self.plan())
        self.assertEqual(graph["P1.1"], set())
        self.assertEqual(graph["P1.2"], {"P1.1"})
        self.assertEqual(graph["P2.1"], {"P1.1", "P1.2"})  # explicit item + every item of the default phase dep
        self.assertEqual(graph["P2.2"], {"P1.1", "P1.2"})
        edges = parallel.wait_edges(self.plan())
        self.assertEqual(edges[("P2.1", "P1.2")], {"item", "phase:P1"})
        self.assertEqual(edges[("P2.2", "P1.1")], {"phase:P1"})

    def test_empty_phase_dependency_leaves_only_item_edges(self):
        self.add_phase("P2", {"P2.1": ["P1.1"], "P2.2": []}, depends_on=[])
        graph = parallel.wait_graph(self.plan())
        self.assertEqual(graph["P2.1"], {"P1.1"})
        self.assertEqual(graph["P2.2"], set())


class DeadlockTests(ParallelCase):
    def test_mixed_cycle_is_reported_once_with_phase_marker(self):
        self.add_phase("P2", {"P2.1": ["P3.1"]})
        self.add_phase("P3", {"P3.1": []}, depends_on=["P2"])
        hits = self.deadlock_issues()
        self.assertEqual(len(hits), 1, hits)
        self.assertEqual(hits[0].message, "P2.1 -> P3.1 -> (phase P2) -> P2.1 never becomes ready")
        self.assertTrue(hits[0].where.endswith("P2.1.json"), hits[0].where)
        self.assertEqual(self.cycle_issues(), [])

    def test_chain_without_a_cycle_is_fine(self):
        self.add_phase("P2", {"P2.1": []})
        self.add_phase("P3", {"P3.1": ["P2.1"]}, depends_on=["P2"])
        self.assertEqual(self.deadlock_issues(), [])

    def test_item_dependency_across_phases_with_parallel_phases_is_fine(self):
        self.add_phase("P2", {"P2.1": []}, depends_on=[])
        self.add_phase("P3", {"P3.1": ["P2.1"]}, depends_on=[])
        self.assertEqual(self.deadlock_issues(), [])

    def test_pure_item_cycle_is_only_a_cycle(self):
        self.edit("phases/P1/P1.1.json", lambda d: d.update(depends_on=["P1.2"]))
        self.assertEqual(self.deadlock_issues(), [])
        self.assertEqual(len(self.cycle_issues()), 1)

    def test_pure_phase_cycle_is_only_a_cycle(self):
        self.edit("phases/P1/P1.2.json", lambda d: d.update(depends_on=[]))
        self.add_phase("P2", {"P2.1": []})
        self.edit("phases/P1/phase.json", lambda d: d.update(depends_on=["P2"]))
        self.assertEqual(self.deadlock_issues(), [])
        self.assertTrue(self.cycle_issues())

    def test_item_dependency_inside_a_phase_cycle_is_also_a_deadlock(self):
        self.add_phase("P2", {"P2.1": []})
        self.edit("phases/P1/phase.json", lambda d: d.update(depends_on=["P2"]))
        self.assertTrue(self.cycle_issues())
        self.assertTrue(self.deadlock_issues())  # P1.2 waits for P1.1 and for P2, which waits for P1

    def test_item_waiting_for_its_own_phase(self):
        self.edit("phases/P1/phase.json", lambda d: d.update(depends_on=["P1"]))
        self.assertTrue(self.cycle_issues())  # P1 -> P1 is a phase cycle
        hits = self.deadlock_issues()  # and P1.2 -> P1.1 (item) closes through the phase edge
        self.assertEqual(len(hits), 1, hits)
        self.assertEqual(hits[0].message, "P1.1 -> (phase P1) -> P1.2 -> P1.1 never becomes ready")

    def test_item_dependency_on_a_later_phase_that_waits_for_the_phase(self):
        self.add_phase("P2", {"P2.1": []})
        self.edit("phases/P1/P1.1.json", lambda d: d.update(depends_on=["P2.1"]))
        hits = self.deadlock_issues()
        self.assertEqual(len(hits), 1, hits)
        self.assertEqual(hits[0].message, "P1.1 -> P2.1 -> (phase P1) -> P1.1 never becomes ready")

    def test_order_is_deterministic_and_multiple_cycles_are_listed(self):
        self.add_phase("P2", {"P2.1": ["P3.1"], "P2.2": ["P3.2"]})
        self.add_phase("P3", {"P3.1": [], "P3.2": []}, depends_on=["P2"])
        first = [i.message for i in self.deadlock_issues()]
        self.assertEqual(len(first), 2, first)
        self.assertEqual(first, sorted(first, key=lambda m: m.split(" ")[0]))
        self.assertEqual(first, [i.message for i in self.deadlock_issues()])

    def test_broken_references_never_raise(self):
        self.edit("phases/P1/P1.2.json", lambda d: d.update(depends_on=["P9.9", 3, None]))
        self.edit("phases/P1/phase.json", lambda d: d.update(depends_on=["P7", 5]))
        self.assertEqual(self.deadlock_issues(), [])


class ReadySetTests(ParallelCase):
    """``ready_set`` over a plan whose P1 is closed; P2 is detailed with two items, P3 a skeleton."""

    def setUp(self):
        super().setUp()
        self.edit("phases/P1/P1.2.json", lambda d: d.update(status="done"))
        self.edit("phases/P1/phase.json", lambda d: d.update(closed={"at": "2026-10-05T11:00:00Z", "result": "done",
                                                                      "summary": "closed"}))
        self.add_phase("P2", {"P2.1": [], "P2.2": []}, depends_on=["P1"])
        self.footprints({"P2.1": ["a/x.py"], "P2.2": ["b/y.py"]})
        self.add_phase("P3", {}, depends_on=["P1"])
        self.edit("phases/P3/phase.json", lambda d: d.update(design="skeleton"))

    def footprints(self, mapping):
        for item_id, paths in mapping.items():
            phase_id = item_id.split(".")[0]
            self.edit(f"phases/{phase_id}/{item_id}.json", lambda d, p=paths: d.update(
                task_files=[{"path": x, "change": "modify"} for x in p] if p else None))
            if not paths:
                self.edit(f"phases/{phase_id}/{item_id}.json", lambda d: d.pop("task_files", None))

    def ready(self, limit, **kw):
        return parallel.ready_set(self.plan(), limit, **kw)

    def lane_items(self, ready):
        return [lane["items"] or lane["phase"] for lane in ready.lanes]

    def test_wide_limit_names_both_items_and_the_design_phase(self):
        ready = self.ready(3)
        self.assertEqual(self.lane_items(ready), [["P2.1"], ["P2.2"], "P3"])
        self.assertEqual([lane["lane"] for lane in ready.lanes], ["L1", "L2", "L3"])
        self.assertEqual([lane["kind"] for lane in ready.lanes], ["run-items", "run-items", "design-phase"])
        self.assertEqual(ready.lanes[0]["command"], f"planner:plan-run {self.plan().plan['id']} P2.1")
        self.assertEqual(ready.lanes[0]["launch"]["codex"], "$ " + ready.lanes[0]["command"])
        self.assertEqual(ready.lanes[0]["batch"], "B1")
        self.assertEqual(ready.lanes[2]["route"], None)
        self.assertEqual((ready.running, ready.conflicts, ready.deferred), ([], [], []))

    def test_small_limit_defers_the_rest(self):
        ready = self.ready(2)
        self.assertEqual(self.lane_items(ready), [["P2.1"], ["P2.2"]])
        self.assertEqual(ready.deferred, ["P3"])
        one = self.ready(1)
        self.assertEqual(one.deferred, ["P2.2", "P3"])

    def test_plan_max_parallel_caps_the_limit(self):
        self.edit("plan.json", lambda d: d.update(orchestration={"max_parallel": 1}))
        ready = self.ready(5)
        self.assertEqual((ready.limit, len(ready.lanes)), (1, 1))

    def test_overlapping_task_files_become_a_conflict(self):
        self.footprints({"P2.2": ["a/"]})
        ready = self.ready(3)
        self.assertEqual(self.lane_items(ready), [["P2.1"], "P3"])
        self.assertEqual(ready.conflicts, [{"item": "P2.2", "with": "P2.1", "reason": "task_files_overlap",
                                            "paths": [["a/", "a/x.py"]]}])

    def test_unknown_footprint_conflicts_with_everything(self):
        self.footprints({"P2.2": None})
        ready = self.ready(3)
        self.assertEqual(self.lane_items(ready), [["P2.1"], "P3"])
        self.assertEqual(ready.conflicts, [{"item": "P2.2", "with": "P2.1", "reason": "footprint_unknown",
                                            "paths": []}])

    def test_conflicting_lane_does_not_use_a_slot(self):
        self.footprints({"P2.2": ["a/x.py"]})
        ready = self.ready(2)
        self.assertEqual(self.lane_items(ready), [["P2.1"], "P3"])
        self.assertEqual(ready.deferred, [])

    def test_running_item_takes_a_slot_and_its_footprint(self):
        self.edit("phases/P2/P2.1.json", lambda d: d.update(status="in_progress"))
        self.footprints({"P2.2": ["a/"]})
        ready = self.ready(2)
        self.assertEqual(ready.running, [{"item": "P2.1", "phase": "P2"}])
        self.assertEqual(self.lane_items(ready), ["P3"])
        self.assertEqual(ready.conflicts[0]["with"], "P2.1")
        self.assertEqual(ready.waiting, [])

    def test_running_items_reduce_slots(self):
        self.edit("phases/P2/P2.1.json", lambda d: d.update(status="in_progress"))
        ready = self.ready(2)
        self.assertEqual(self.lane_items(ready), [["P2.2"]])
        self.assertEqual(ready.deferred, ["P3"])
        saturated = self.ready(1)
        self.assertEqual((saturated.lanes, saturated.deferred), ([], ["P2.2", "P3"]))

    def test_running_batch_waits_when_every_member_runs(self):
        for item_id in ("P2.1", "P2.2"):
            self.edit(f"phases/P2/{item_id}.json", lambda d: d.update(status="in_progress"))
        ready = self.ready(4)
        self.assertEqual(self.lane_items(ready), ["P3"])
        self.assertIn({"phase": "P2", "item": None, "reason": "batch B1 running"}, ready.waiting)

    def test_phase_waits_for_an_open_dependency_and_a_blocked_one(self):
        self.add_phase("P4", {"P4.1": []}, depends_on=["P2"])
        self.footprints({"P4.1": ["c/z.py"]})
        self.assertIn({"phase": "P4", "item": None, "reason": "P2"}, self.ready(4).waiting)
        self.edit("phases/P1/phase.json", lambda d: d["closed"].update(result="blocked"))
        waiting = self.ready(4).waiting
        self.assertIn({"phase": "P2", "item": None, "reason": "phase P1 is closed as blocked"}, waiting)

    def test_item_dependency_and_gate_wait_per_item(self):
        self.edit("phases/P2/P2.2.json", lambda d: d.update(depends_on=["P2.1"]))
        ready = self.ready(4)
        self.assertEqual(self.lane_items(ready), [["P2.1"], "P3"])
        self.assertIn({"phase": "P2", "item": "P2.2", "reason": "P2.1"}, ready.waiting)
        self.edit("phases/P2/P2.1.json", lambda d: d.update(authority={"kind": "owner_gate", "gate": "G1"}))
        gated = self.ready(4)
        self.assertIn({"phase": "P2", "item": "P2.1", "reason": "gate G1"}, gated.waiting)
        self.assertEqual(self.ready(4, granted={"G1"}).lanes[0]["items"], ["P2.1"])

    def test_required_batch_is_one_lane_or_one_wait(self):
        self.edit("phases/P2/phase.json", lambda d: d["batches"][0].update(mode="required"))
        ready = self.ready(4)
        self.assertEqual(self.lane_items(ready), [["P2.1", "P2.2"], "P3"])
        self.edit("phases/P2/P2.2.json", lambda d: d.update(authority={"kind": "owner_gate", "gate": "G2"}))
        blocked = self.ready(4)
        self.assertEqual(self.lane_items(blocked), ["P3"])
        self.assertIn({"phase": "P2", "item": None, "reason": "gate G2"}, blocked.waiting)

    def test_required_batch_lane_conflicts_on_any_member(self):
        self.edit("phases/P2/phase.json", lambda d: d["batches"][0].update(mode="required"))
        self.edit("phases/P2/P2.1.json", lambda d: d.update(status="todo"))
        self.add_phase("P5", {"P5.1": []}, depends_on=["P1"])
        self.footprints({"P5.1": ["b/"]})
        ready = self.ready(4)
        self.assertEqual(self.lane_items(ready), [["P2.1", "P2.2"], "P3"])
        self.assertEqual(ready.conflicts, [{"item": "P5.1", "with": "P2.2", "reason": "task_files_overlap",
                                            "paths": [["b/", "b/y.py"]]}])

    def test_sequential_phase_waits_on_running_and_offers_one_lane(self):
        self.edit("phases/P2/phase.json", lambda d: d.update(orchestration={"strategy": "sequential"}))
        ready = self.ready(4)
        self.assertEqual(self.lane_items(ready), [["P2.1"], "P3"])
        self.assertIn({"phase": "P2", "item": "P2.2", "reason": "P2 is sequential; P2.1 first"}, ready.waiting)
        self.edit("phases/P2/P2.1.json", lambda d: d.update(status="in_progress"))
        busy = self.ready(4)
        self.assertEqual(self.lane_items(busy), ["P3"])
        self.assertIn({"phase": "P2", "item": None, "reason": "P2 is sequential; running P2.1"}, busy.waiting)

    def test_terminal_phase_waits_for_reconcile(self):
        for item_id in ("P2.1", "P2.2"):
            self.edit(f"phases/P2/{item_id}.json", lambda d: d.update(status="done"))
        reason = f"P2 closure: plan.py reconcile {self.plan().plan['id']}"
        self.assertIn({"phase": "P2", "item": None, "reason": reason}, self.ready(4).waiting)

    def test_paused_plan_has_no_lanes(self):
        self.edit("plan.json", lambda d: d.update(status="paused", pause={"reason": "freeze"}))
        ready = self.ready(4)
        self.assertEqual((ready.lanes, ready.running), ([], []))
        self.assertEqual(ready.waiting, [{"phase": None, "item": None, "reason": "paused: freeze"}])
        self.assertEqual(ready.render(), "no ready lanes\nwaiting: paused: freeze")

    def test_next_is_carried_over_unchanged(self):
        self.assertEqual(self.ready(4).next, lifecycle.next(self.plan()).as_dict())

    def test_limit_must_be_a_positive_integer(self):
        for bad in (0, -1, True, "2", None):
            with self.subTest(bad=bad), self.assertRaises(PlanError) as caught:
                parallel.ready_set(self.plan(), bad)
            self.assertEqual(caught.exception.code, "LIMIT_INVALID")

    def test_result_validates_against_read_ready(self):
        self.edit("phases/P2/P2.1.json", lambda d: d.update(status="in_progress"))
        self.footprints({"P2.2": ["a/"]})
        data = json.loads(json.dumps(self.ready(2).as_dict()))
        self.assertEqual(schema.validate(data, "read-ready"), [])
        data["lanes"][0]["extra"] = 1
        self.assertTrue(schema.validate(data, "read-ready"))

    def test_text_rendering(self):
        self.edit("phases/P2/P2.1.json", lambda d: d.update(status="in_progress"))
        self.footprints({"P2.2": ["a/"]})
        plan_id = self.plan().plan["id"]
        self.assertEqual(self.ready(2).render(), "\n".join([
            f"L1 design-phase: planner:plan-design {plan_id} P3", "running P2.1", "conflict P2.2 ~ P2.1: a/ / a/x.py"]))
        self.assertEqual(self.ready(1).render().splitlines()[0], "no ready lanes")
        self.assertIn("deferred P3", self.ready(1).render())  # the running P2.1 fills the only slot

    def test_footprint_unknown_text(self):
        self.footprints({"P2.2": None})
        self.assertIn("conflict P2.2 ~ P2.1: footprint unknown", self.ready(3).render())


class ReadOnlyTests(ParallelCase):
    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main([str(a) for a in argv])
        return code, out.getvalue(), err.getvalue()

    def test_next_parallel_writes_nothing(self):
        before = self.snapshot()
        for args in (["--parallel", "3"], ["--parallel", "3", "--json"]):
            code, out, _ = self.run_cli("next", self.root, *args)
            self.assertEqual(code, 0)
            self.assertTrue(out)
        self.assertEqual(self.snapshot(), before)

    def test_next_without_flag_is_the_old_output(self):
        for state in ("todo", "in_progress", "done"):
            self.edit("phases/P1/P1.2.json", lambda d, s=state: d.update(status=s))
            plan = self.plan()
            action = lifecycle.next(plan)
            route = action.route
            code, out, _ = self.run_cli("next", self.root)
            self.assertEqual((code, out), (0, action.exact + (f"  ({route['class']}/{route['effort']})" if route else "") + "\n"))
            code, out, _ = self.run_cli("next", self.root, "--json")
            self.assertEqual((code, json.loads(out)), (0, action.as_dict()))

    def test_json_output_is_the_read_ready_document(self):
        code, out, _ = self.run_cli("next", self.root, "--parallel", "2", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(schema.validate(data, "read-ready"), [])
        self.assertEqual(data["next"], lifecycle.next(self.plan()).as_dict())
        code, out, _ = self.run_cli("--output", "json", "next", self.root, "--parallel", "2", "--json")
        self.assertEqual(json.loads(out)["data"], data)

    def test_parallel_zero_is_refused_with_the_code(self):
        before = self.snapshot()
        code, out, err = self.run_cli("next", self.root, "--parallel", "0")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("LIMIT_INVALID", err)
        code, out, _ = self.run_cli("--output", "json", "next", self.root, "--parallel", "-2")
        self.assertEqual(json.loads(out)["error"]["code"], "LIMIT_INVALID")
        self.assertEqual(self.snapshot(), before)

    def test_text_output_starts_with_the_first_lane(self):
        self.edit("phases/P1/P1.1.json", lambda d: d.update(status="done"))
        code, out, _ = self.run_cli("next", self.root, "--parallel", "2")
        self.assertEqual(code, 0)
        self.assertEqual(out, f"L1 run-items: planner:plan-run {self.plan().plan['id']} P1.2  (implementation/medium)\n")


if __name__ == "__main__":
    unittest.main()
