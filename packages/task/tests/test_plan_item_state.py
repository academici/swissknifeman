import tempfile
import unittest
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan
from task import journal, plan_item_state

class PlanItemStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = write_valid_plan(Path(self.tmp.name), "DEMO-V2", layout="v2")
    def tearDown(self): self.tmp.cleanup()
    def test_result_mapping_covers_sealed_enum(self):
        self.assertEqual(set(plan_item_state.RESULT_STATUS), set(journal.RESULT_VALUES))
    def test_generate_and_drift_check(self):
        targets = plan_item_state.build_states(self.plan)
        text = targets[0].read_text(encoding="utf-8")
        self.assertIn("projection: item-state", text)
        self.assertNotIn("routing", text.lower())
        self.assertEqual(plan_item_state.build_states(self.plan, check=True), targets)
        targets[0].write_text(text + "drift\n", encoding="utf-8")
        with self.assertRaises(plan_item_state.ItemStateError): plan_item_state.build_states(self.plan, check=True)
