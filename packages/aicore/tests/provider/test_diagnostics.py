from unittest import TestCase
from aicore.provider.diagnostics import render
from aicore.provider.status import StatusDiagnostic


class DiagnosticTests(TestCase):
    def test_renderer_is_value_free(self):
        self.assertEqual("PCP_STATUS_UNKNOWN", render(StatusDiagnostic("warning", "PCP_STATUS_UNKNOWN", "missing evidence", "codex.status"))["code"])
    def test_secret_like_fields_refuse(self):
        with self.assertRaisesRegex(ValueError, "REDACTION"):
            StatusDiagnostic("error", "PCP_X", "token=abc", "codex.status")
