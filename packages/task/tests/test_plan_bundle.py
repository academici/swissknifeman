import filecmp
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task import plan_bundle


class PlanBundleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = Path(self.tmp.name) / "plan-v2"
        shutil.copytree(Path(__file__).parent / "data" / "plan-v2", self.plan)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lifted_schema_is_byte_identical(self):
        root = Path(__file__).resolve().parents[3]
        self.assertTrue(filecmp.cmp(root / "packages/task/configs/bundle-v1.schema.json",
                                     root / "plans/2026.08.07-PLAN-ECONOMY/root/contracts/bundle-v1.schema.json",
                                     shallow=False))

    def test_build_is_deterministic_and_check_is_byte_fresh(self):
        one = plan_bundle.render(self.plan, "P1.1")
        two = plan_bundle.render(self.plan, "P1.1")
        self.assertEqual(one, two)
        target = plan_bundle.build(self.plan, "P1.1")
        self.assertEqual(target.read_text(encoding="utf-8"), one)
        plan_bundle.build(self.plan, "P1.1", check=True)
        target.write_bytes(target.read_bytes() + b" ")
        with self.assertRaises(plan_bundle.BundleError):
            plan_bundle.build(self.plan, "P1.1", check=True)

    def test_unresolvable_is_atomic_and_names_raw_declaration(self):
        target = plan_bundle.build(self.plan, "P1.1")
        expected = target.read_bytes()
        spec = self.plan / "phases/P1/P1.1.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace("brief/00-brief.md", "missing.md"), encoding="utf-8")
        with self.assertRaisesRegex(plan_bundle.BundleError, r"unresolvable_entry: .*missing\.md"):
            plan_bundle.build(self.plan, "P1.1")
        self.assertEqual(target.read_bytes(), expected)
