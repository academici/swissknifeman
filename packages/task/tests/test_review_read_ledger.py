"""Missing native reads retain absence evidence without aborting a deletion review."""
from pathlib import Path
import tempfile
import unittest

from task.review_sources import ReadLedger


class MissingReadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.ledger = ReadLedger(self.root)

    def observe(self, path):
        self.ledger.observe({"sessionUpdate": "tool_call", "title": "read_file",
                             "toolCallId": "deleted-file", "rawInput": {"target_file": str(path)}})

    def test_absent_source_is_recorded_and_verified_as_absent(self):
        self.observe(self.root / "removed.php")
        self.assertEqual(self.ledger.result()["reads"][0]["member"],
                         {"path": "removed.php", "sha256": None, "mode": None})
        self.ledger.verify()

    def test_reappearing_source_invalidates_absence_evidence(self):
        self.observe(self.root / "removed.php")
        (self.root / "removed.php").write_text("replacement")
        with self.assertRaisesRegex(ValueError, "REVIEW_DEPENDENCY_STALE"):
            self.ledger.verify()

    def test_directory_read_still_fails(self):
        with self.assertRaisesRegex(ValueError, "REVIEW_READ_UNVERIFIABLE"):
            self.observe(self.root)

    def test_missing_external_target_still_fails(self):
        (self.root / "escape").symlink_to(self.root.parent / "absent-external-source")
        with self.assertRaisesRegex(ValueError, "REVIEW_READ_UNVERIFIABLE"):
            self.observe(self.root / "escape")


if __name__ == "__main__":
    unittest.main()
