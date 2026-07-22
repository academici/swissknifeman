import json
import tempfile
import unittest
from pathlib import Path

from analyst.events import append_event, events_path, read_events
from analyst.runs import migrate_legacy, normalize


class ProviderReaderTests(unittest.TestCase):
    def test_explicit_reader_normalizes_distinct_provider_provenance(self):
        claude = normalize("claude-code", 2, {"schema": 2, "session_id": "s", "generated_at": "2026-07-22T00:00:00Z", "tools": {"total": 1}, "bash": {}}, project_id="p", raw_ref="local:c")
        codex = normalize("codex", 1, {"schema": 1, "session_id": "s", "occurred_at": "2026-07-22T00:00:00Z", "metrics": {"usage": 1}}, project_id="p", raw_ref="local:x")
        self.assertEqual((claude["provider_id"], codex["provider_id"]), ("claude-code", "codex"))
        with self.assertRaisesRegex(ValueError, "ANALYTICS_UNKNOWN_PROVIDER"):
            normalize("other", 1, {}, project_id="p", raw_ref="local:z")

    def test_append_and_copy_verify_migration_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "legacy.json"
            legacy.write_text(json.dumps({"schema": 2, "session_id": "s", "generated_at": "2026-07-22T00:00:00Z", "tools": {"total": 1}, "bash": {}}), encoding="utf-8")
            before = legacy.read_bytes()
            self.assertTrue(migrate_legacy(root, project_id="p", source=legacy, operation="plan")["would_copy"])
            self.assertTrue(migrate_legacy(root, project_id="p", source=legacy, operation="apply")["copied"])
            self.assertEqual(len(read_events(root)), 1)
            self.assertFalse(migrate_legacy(root, project_id="p", source=legacy, operation="apply")["would_copy"])
            self.assertEqual(legacy.read_bytes(), before)
            self.assertTrue(events_path(root).is_file())


if __name__ == "__main__":
    unittest.main()
