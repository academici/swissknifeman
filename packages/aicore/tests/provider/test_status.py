from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.provider.status import ProviderStatusRow, StatusDiagnostic, aggregate, write_adapter_status


class StatusTests(TestCase):
    digest = "a" * 64

    def test_aggregate_preserves_both_provider_rows(self):
        rows = (ProviderStatusRow("codex", True, self.digest, True, "fresh"), ProviderStatusRow("claude-code", True, self.digest, True, "drifted"))
        result = aggregate(rows)
        self.assertEqual("drifted", result["status"])
        self.assertEqual(["claude-code", "codex"], result["selected_provider_ids"])

    def test_error_and_cross_provider_writer_fail_closed(self):
        row = ProviderStatusRow("codex", True, self.digest, True, "fresh", (StatusDiagnostic("error", "PCP_X", "safe", "codex.status"),))
        self.assertEqual("error", row.status)
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "CROSS_PROVIDER"):
                write_adapter_status(Path(directory) / "status.json", writer_provider_id="claude-code", row=row)
