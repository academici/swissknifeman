"""Diagnostic parity of the public coordinator on the v2-only carrier."""
import tempfile
import unittest
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan

from task import plan_lint
from task.plan_lint_checks import engine


class TestDiagnosticParity(unittest.TestCase):
    def test_public_surface_matches_split_engine_on_v2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plans = (write_valid_plan(root, "DEMO-V2", layout="v2"),)
            for plan_dir in plans:
                public_diag = plan_lint.Diagnostics()
                engine_diag = plan_lint.Diagnostics()
                plan_lint.lint_plan(plan_dir, public_diag)
                engine.lint_plan(plan_dir, engine_diag)
                self.assertEqual(public_diag.normalized_keys(root),
                                 engine_diag.normalized_keys(root))
        print("DIAGNOSTIC-PARITY-OK v2-fixture")


if __name__ == "__main__":
    unittest.main()
