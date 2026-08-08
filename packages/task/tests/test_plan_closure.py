import shutil
import tempfile
import unittest
from pathlib import Path
import sys

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task import plan_closure, plan_layout


class PlanClosureTest(unittest.TestCase):
    def _fixture(self, root):
        source = Path(__file__).parent / "data" / "plan-v2"
        target = Path(root) / "plan-v2"
        shutil.copytree(source, target)
        return target

    def test_terminal_closure_is_deterministic_and_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._fixture(tmp)
            target = plan_closure.build_closure(plan, "P0")
            expected = target.read_bytes()
            self.assertIn(b"# \xd0\x97\xd0\xb0\xd0\xba\xd1\x80\xd1\x8b\xd1\x82\xd0\xb8\xd0\xb5 \xd1\x84\xd0\xb0\xd0\xb7\xd1\x8b P0", expected)
            self.assertIn(b"[D1](../../decisions/D1-fixture.md)", expected)
            self.assertEqual(plan_closure.build_closure(plan, "P0", check=True), target)
            self.assertEqual(expected, target.read_bytes())

    def test_live_phase_refuses_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._fixture(tmp)
            with self.assertRaisesRegex(plan_closure.ClosureError, "терминальной"):
                plan_closure.build_closure(plan, "P1")

    def test_live_reader_slots_exclude_terminal_phase_but_auditor_keeps_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._fixture(tmp)
            live = [slot for reader in ("executor", "designer", "owner")
                    for slot in plan_layout.slots(plan, reader)]
            self.assertFalse([slot for slot in live if "/P0/" in str(slot.path)])
            audited = plan_layout.slots(plan, "auditor")
            self.assertTrue(any("/P0/" in str(slot.path) for slot in audited))


if __name__ == "__main__":
    unittest.main()
