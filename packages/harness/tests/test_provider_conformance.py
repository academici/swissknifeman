import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from harness.provider_audit import audit_package

PACKAGE = Path(__file__).resolve().parents[1]


class ProviderConformanceTests(unittest.TestCase):
    def test_independent_fixture_has_exact_inventory_and_stable_report(self):
        first, second = audit_package(PACKAGE), audit_package(PACKAGE)
        self.assertEqual(first.render(), second.render())
        self.assertTrue(first.green, first.render())
        report = first.as_dict()
        self.assertTrue(all(not row["missing"] and not row["extra"] and not row["duplicates"] for row in report["rows"]))

    def test_fixture_is_not_renderer_output_and_has_no_secret_or_full_access_default(self):
        fixture = (PACKAGE / "tests/fixtures_data/provider-harness-cases.json").read_text(encoding="utf-8")
        self.assertNotIn("real-token", fixture)
        self.assertNotIn("approval_policy", fixture)
        self.assertEqual(len(json.loads(fixture)["agent_roles"]), 44)

    def test_audit_is_no_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = tuple(root.rglob("*"))
            audit_package(PACKAGE)
            self.assertEqual(before, tuple(root.rglob("*")))


if __name__ == "__main__":
    unittest.main()
