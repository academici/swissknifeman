"""Effective-source diagnostics read no plan files: unmeasured items are a named `unknown`."""
import tempfile
import unittest
from pathlib import Path

from skiller.doctor import (
    _capability_gap_diagnostic,
    _effective_carrier_set_document,
    _trace_quality_diagnostic,
)


class StandaloneDiagnosticsCase(unittest.TestCase):
    def test_capability_gap_is_unknown_without_any_repo_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            diagnostic = _capability_gap_diagnostic(Path(tmp))
        self.assertEqual(diagnostic["status"], "unknown")
        self.assertEqual(diagnostic["next_command"], "skiller doctor --provider-distribution")
        self.assertNotIn("plans/", diagnostic["source"])

    def test_trace_quality_is_unknown_and_cites_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            diagnostic = _trace_quality_diagnostic(Path(tmp))
        self.assertEqual(diagnostic["status"], "unknown")
        self.assertNotIn("plans/", diagnostic["source"])
        self.assertIn("analyst", diagnostic["next_command"])

    def test_carrier_set_names_the_fixture_without_a_plan_path(self):
        doc = _effective_carrier_set_document({"positive_maps": {"codex": {"a": ["root:codex"]}}},
                                              commit_sha="deadbeef")
        self.assertEqual(doc["providers"]["codex"]["fixture_unit_set"], "fixture-unit-set.json")
        self.assertEqual(doc["providers"]["codex"]["identities"],
                         [{"identity": "a", "carriers": ["root:codex"]}])


if __name__ == "__main__":
    unittest.main()
