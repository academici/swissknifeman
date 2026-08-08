import tempfile
import unittest
from pathlib import Path
import sys

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task import plan_projection


class PlanProjectionTest(unittest.TestCase):
    def test_inputs_hash_is_order_independent_and_content_sensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = root / "a.md", root / "b.md"
            first.write_text("a", encoding="utf-8")
            second.write_text("b", encoding="utf-8")
            one = plan_projection.inputs_sha256((first, second), root=root)
            self.assertEqual(one, plan_projection.inputs_sha256((second, first), root=root))
            second.write_text("changed", encoding="utf-8")
            self.assertNotEqual(one, plan_projection.inputs_sha256((first, second), root=root))

    def test_check_compares_regenerated_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "view.md"
            plan_projection.write_or_check(path, "expected\n", check=False)
            self.assertFalse(plan_projection.write_or_check(path, "expected\n", check=True))
            path.write_text("manual edit\n", encoding="utf-8")
            with self.assertRaises(plan_projection.ProjectionError):
                plan_projection.write_or_check(path, "expected\n", check=True)
