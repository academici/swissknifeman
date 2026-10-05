"""v3 plan model: ID patterns, refs, ordering, statuses and phase worst-of."""
import sys
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task.plan import model  # noqa: E402


class IdPatternTests(unittest.TestCase):
    def test_item_phase_decision_ids(self):
        self.assertTrue(model.ITEM_ID.fullmatch("P1.12"))
        self.assertTrue(model.PHASE_ID.fullmatch("P08"))
        self.assertTrue(model.DECISION_ID.fullmatch("D4"))
        for bad in ("P1", "P1.", "p1.1", "P1.1\n", "P1.1.2", " P1.1"):
            self.assertIsNone(model.ITEM_ID.fullmatch(bad), bad)
        self.assertIsNone(model.PHASE_ID.fullmatch("P1.1"))
        self.assertIsNone(model.DECISION_ID.fullmatch("D"))

    def test_plan_and_short_ids(self):
        self.assertTrue(model.PLAN_ID.fullmatch("2026.10.05-№1-TASK-PLAN-JSON"))
        for legacy in ("LEGACY-PLAN", "FLEX-2", "LOQUM-DEV", "AGENTOOLS", "2026.07.17-AXIOMA-ORCHESTRA"):
            self.assertTrue(model.PLAN_ID.fullmatch(legacy), legacy)
        for bad in ("2026.10.05-№1-x", "legacy", "-LEGACY", "LEGACY-", "A/B"):
            self.assertIsNone(model.PLAN_ID.fullmatch(bad), bad)
        self.assertTrue(model.SHORT_ID.fullmatch("PLAN7"))
        self.assertIsNone(model.SHORT_ID.fullmatch("PLAN0"))
        self.assertIsNone(model.SHORT_ID.fullmatch("PLAN"))

    def test_ascii_digits_only(self):
        self.assertIsNone(model.ITEM_ID.fullmatch("P١.١"))  # Arabic-Indic digits


class RefTests(unittest.TestCase):
    def test_parse_local_and_qualified_refs(self):
        self.assertEqual(model.parse_ref("P2"), model.Ref(None, None, "P2", "phase"))
        self.assertEqual(model.parse_ref("P2.3"), model.Ref(None, None, "P2.3", "item"))
        self.assertEqual(model.parse_ref("D4"), model.Ref(None, None, "D4", "decision"))
        self.assertEqual(model.parse_ref("PLAN7.P2.3"), model.Ref(None, "PLAN7", "P2.3", "item"))
        self.assertEqual(model.parse_ref("PLAN7.D4"), model.Ref(None, "PLAN7", "D4", "decision"))
        self.assertEqual(model.parse_ref("swissknifeman:PLAN7.P2.3"),
                         model.Ref("swissknifeman", "PLAN7", "P2.3", "item"))

    def test_malformed_refs_raise(self):
        for bad in ("", "X1", "PLAN7", "PLAN7.", "repo:P1", "P1.2.3", "P1\n", None, 5):
            with self.subTest(bad):
                with self.assertRaises(ValueError):
                    model.parse_ref(bad)

    def test_item_phase(self):
        self.assertEqual(model.item_phase("P1.2"), "P1")
        self.assertEqual(model.item_phase("P12.30"), "P12")
        for bad in ("P1", "D1", "P1.2.3", ""):
            with self.assertRaises(ValueError):
                model.item_phase(bad)


class SortKeyTests(unittest.TestCase):
    def test_numeric_order(self):
        ids = ["P1.10", "P1.2", "P10", "P2", "P1.9", "P1"]
        self.assertEqual(sorted(ids, key=model.id_sort_key), ["P1", "P1.2", "P1.9", "P1.10", "P2", "P10"])

    def test_other_prefixes_and_errors(self):
        self.assertEqual(sorted(["D10", "D2"], key=model.id_sort_key), ["D2", "D10"])
        self.assertLess(model.id_sort_key("B1"), model.id_sort_key("D1"))
        for bad in ("", "1", "P", "P1.", "p1"):
            with self.assertRaises(ValueError):
                model.id_sort_key(bad)


class StatusTests(unittest.TestCase):
    def test_statuses_compare_with_json_strings(self):
        self.assertIn("done", model.TERMINAL)
        self.assertEqual(model.ItemStatus("blocked"), "blocked")
        self.assertEqual({s.value for s in model.ItemStatus},
                         {"todo", "in_progress", "done", "done_with_deviations", "blocked", "skipped"})

    def test_terminal_and_satisfying(self):
        self.assertEqual({s.value for s in model.SATISFYING}, {"done", "done_with_deviations", "skipped"})
        self.assertEqual({s.value for s in model.TERMINAL}, {"done", "done_with_deviations", "blocked", "skipped"})
        self.assertNotIn("blocked", model.SATISFYING)
        self.assertTrue(model.SATISFYING <= model.TERMINAL)

    def test_labels_cover_every_status(self):
        self.assertEqual(set(model.STATUS_LABEL), set(model.ItemStatus))
        self.assertEqual(model.STATUS_LABEL["done"], "🟢 Done")
        self.assertEqual(model.STATUS_LABEL["skipped"], "⛔ Skipped by decision")

    def test_class_and_effort_order(self):
        self.assertEqual(model.CLASS_ORDER, ("economy", "implementation", "frontier"))
        self.assertEqual(model.EFFORT_ORDER, ("low", "medium", "high", "xhigh", "max", "ultra"))


class PhaseStatusTests(unittest.TestCase):
    def test_open_while_anything_is_not_terminal(self):
        self.assertIsNone(model.phase_status(["done", "todo"]))
        self.assertIsNone(model.phase_status(["done", "in_progress"]))
        self.assertIsNone(model.phase_status([]))

    def test_worst_of(self):
        self.assertEqual(model.phase_status(["done", "done"]), "done")
        self.assertEqual(model.phase_status(["done", "done_with_deviations"]), "done_with_deviations")
        self.assertEqual(model.phase_status(["done_with_deviations", "blocked", "done"]), "blocked")
        self.assertEqual(model.phase_status(["skipped", "done"]), "done")
        self.assertEqual(model.phase_status(["skipped", "skipped"]), "skipped")

    def test_unknown_status_raises(self):
        with self.assertRaises(ValueError):
            model.phase_status(["done", "finished"])


if __name__ == "__main__":
    unittest.main()
