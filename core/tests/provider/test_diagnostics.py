import unittest
from core.provider.diagnostics import render
from core.provider.status import StatusDiagnostic


class DiagnosticTests(unittest.TestCase):
    def test_machine_fields_are_preserved(self):
        self.assertEqual(render(StatusDiagnostic("info", "PCP_OK", "safe", "provider"))["code"], "PCP_OK")
