import json
import hashlib
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

    def test_source_bytes_hash_order_and_redaction_fail_closed(self):
        raw = {"schema": 1, "session_id": "s", "occurred_at": "2026-07-22T00:00:00Z",
               "metrics": {"usage": 1}}
        source = json.dumps(raw, separators=(",", ":"), sort_keys=False).encode()
        declared = hashlib.sha256(source).hexdigest()
        first = normalize("codex", 1, raw, project_id="p", raw_ref="local:source",
                          source_bytes=source, declared_sha256=declared)
        reordered = {"metrics": {"usage": 1}, "occurred_at": raw["occurred_at"],
                     "session_id": "s", "schema": 1}
        second = normalize("codex", 1, reordered, project_id="p", raw_ref="local:source",
                           source_bytes=source, declared_sha256=declared)
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(first["provenance"]["sha256"], declared)
        with self.assertRaisesRegex(ValueError, "ANALYTICS_CORRUPT_EVENT"):
            normalize("codex", 1, raw, project_id="p", raw_ref="local:source",
                      source_bytes=source, declared_sha256="0" * 64)
        for invalid in (
            dict(raw, prompt="secret"),
            dict(raw, metrics={"usage": {"nested": 1}}),
            dict(raw, metrics={"unknown": 1}),
        ):
            with self.assertRaisesRegex(ValueError, "ANALYTICS_REDACTION_FAILED"):
                normalize("codex", 1, invalid, project_id="p", raw_ref="local:source")
        with self.assertRaisesRegex(ValueError, "ANALYTICS_MISSING_PROVENANCE"):
            normalize("codex", 1, raw, project_id="p", raw_ref="local:../source")

    def test_migration_modes_are_no_write_until_apply_and_conflict_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "legacy.json"
            legacy.write_text(json.dumps({"schema": 2, "session_id": "s",
                "generated_at": "2026-07-22T00:00:00Z", "tools": {"total": 1}, "bash": {}}), encoding="utf-8")
            before = legacy.read_bytes()
            for operation in ("plan", "dry-run", "check"):
                self.assertTrue(migrate_legacy(root, project_id="p", source=legacy, operation=operation)["would_copy"])
                self.assertFalse(events_path(root).exists())
                self.assertEqual(legacy.read_bytes(), before)
            migrate_legacy(root, project_id="p", source=legacy, operation="apply")
            stored = json.loads(events_path(root).read_text(encoding="utf-8"))
            stored["provenance"]["sha256"] = "0" * 64
            events_path(root).write_text(json.dumps(stored) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ANALYTICS_MIGRATION_CONFLICT"):
                migrate_legacy(root, project_id="p", source=legacy, operation="apply")


if __name__ == "__main__":
    unittest.main()
