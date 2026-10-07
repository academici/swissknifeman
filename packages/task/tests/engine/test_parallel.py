"""parallel: footprint, conflict, wait graph and the ``dependency_deadlock`` check."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task.plan import check, parallel, store  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
