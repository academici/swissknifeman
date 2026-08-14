import tempfile
import unittest
from pathlib import Path

from packages.task.tests.fixtures import write_valid_plan

from task import validation_admission


class ValidationAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan = write_valid_plan(self.root, "2026.08.13-№1-DEMO", layout="v2")
        self.spec = self.plan / "phases" / "P1" / "P1.1.md"

    def tearDown(self):
        self.temp.cleanup()

    def _validation(self, value):
        text = self.spec.read_text(encoding="utf-8")
        self.spec.write_text(
            text.replace("**Validation:** bash scripts/test.sh — зелёный.",
                         f"**Validation:** {value}"),
            encoding="utf-8",
        )

    def test_missing_literal_make_target_requires_local_repair(self):
        (self.root / "Makefile").write_text("test:\n\t@true\n", encoding="utf-8")
        self._validation("`make test-preflight`")

        report = validation_admission.inspect(self.plan, "P1.1")

        self.assertEqual(report["disposition"], "local-repair")
        self.assertEqual(report["checks"][0]["status"], "missing")
        decision = validation_admission.local_repair_decision(report)
        self.assertEqual(decision["action"], "repair-inline")
        self.assertFalse(decision["terminal"])

    def test_declared_make_target_is_available(self):
        (self.root / "Makefile").write_text(
            ".PHONY: test-preflight\ntest-preflight:\n\t@true\n", encoding="utf-8")
        self._validation("`make test-preflight`")

        report = validation_admission.inspect(self.plan, "P1.1")

        self.assertEqual(report["disposition"], "allow")
        self.assertEqual(report["checks"][0]["status"], "available")

    def test_dynamic_include_is_unknown_not_false_missing(self):
        (self.root / "Makefile").write_text("include $(TARGETS_FILE)\n", encoding="utf-8")
        self._validation("`make test-preflight`")

        report = validation_admission.inspect(self.plan, "P1.1")

        self.assertEqual(report["disposition"], "allow")
        self.assertEqual(report["checks"][0]["status"], "unknown")

    def test_non_make_validation_is_not_reinterpreted(self):
        report = validation_admission.inspect(self.plan, "P1.1")

        self.assertEqual(report["disposition"], "allow")
        self.assertEqual(report["checks"], [])


if __name__ == "__main__":
    unittest.main()
