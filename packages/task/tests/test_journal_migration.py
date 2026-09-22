"""Tests for the owner-gated sealed-journal migration boundary."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

try:
    from . import fixtures
except ImportError:
    import fixtures  # noqa: F401,E402

from task import journal, journal_migration  # noqa: E402


class TestJournalMigration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.plan_dir = fixtures.write_valid_plan(
            Path(self._tmp.name), plan_id="2026.09.21-MIGRATION")
        fixtures.write_decision_record(
            self.plan_dir, "D2", item_id="P1.1",
            decision="Разрешить точную миграцию sealed journal с preimage и manifest.")
        self.source_entry = journal.new_entry(
            plan_id=self.plan_dir.name, item_id="P1.1", command="plan-run",
            actor="model/high", result="no-op", note="legacy")
        for field in ("session_id", "run_id", "cost_usd", "num_turns", "duration_ms"):
            del self.source_entry[field]
        self.source = (json.dumps(
            self.source_entry, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        (self.plan_dir / "journal.jsonl").write_bytes(self.source)

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def _digest(value):
        return hashlib.sha256(value).hexdigest()

    def _manifest(self):
        target_entry = copy.deepcopy(self.source_entry)
        operations = []
        for field in ("session_id", "run_id", "cost_usd", "num_turns", "duration_ms"):
            operations.append({"op": "add", "path": f"/{field}", "value": None})
            target_entry[field] = None
        target = journal_migration._canonical_line(target_entry)
        manifest = {
            "schema_version": "journal-migration/v1",
            "migration_id": "fixture-1",
            "plan_id": self.plan_dir.name,
            "owner_decision": "D2",
            "actor": "owner",
            "reason": "repair historical required fields without guessing values",
            "source_sha256": self._digest(self.source),
            "target_sha256": self._digest(target),
            "preimage_path": "journal-migrations/fixture-1/journal.preimage.jsonl",
            "changes": [{
                "line": 1,
                "before_sha256": self._digest(self.source[:-1]),
                "after_sha256": self._digest(target[:-1]),
                "operations": operations,
            }],
        }
        path = self.plan_dir / "journal-migrations" / "fixture-1" / "manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path, target

    def test_apply_preserves_exact_preimage_and_is_idempotent(self):
        manifest, target = self._manifest()
        receipt = journal_migration.apply(self.plan_dir, manifest)
        preimage = self.plan_dir / receipt["preimage_path"]
        self.assertEqual(preimage.read_bytes(), self.source)
        self.assertEqual((self.plan_dir / "journal.jsonl").read_bytes(), target)
        self.assertEqual(receipt["changed_lines"], [1])
        self.assertEqual(journal_migration.apply(self.plan_dir, manifest), receipt)

    def test_source_hash_mismatch_fails_before_preimage_or_journal_write(self):
        manifest, _target = self._manifest()
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["source_sha256"] = "0" * 64
        manifest.write_text(json.dumps(value), encoding="utf-8")
        before = (self.plan_dir / "journal.jsonl").read_bytes()
        with self.assertRaisesRegex(journal_migration.JournalMigrationError, "source_sha256"):
            journal_migration.apply(self.plan_dir, manifest)
        self.assertEqual((self.plan_dir / "journal.jsonl").read_bytes(), before)
        self.assertFalse((manifest.parent / "journal.preimage.jsonl").exists())

    def test_unlisted_semantic_edit_is_rejected(self):
        manifest, _target = self._manifest()
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["changes"][0]["operations"] = [
            {"op": "replace", "path": "/result", "before": "no-op", "value": "closed-green"}
        ]
        manifest.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(journal_migration.JournalMigrationError, "allow-list"):
            journal_migration.apply(self.plan_dir, manifest)

    def test_owner_decision_must_be_accepted(self):
        manifest, _target = self._manifest()
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["owner_decision"] = "D999"
        manifest.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(journal_migration.JournalMigrationError, "accepted D#"):
            journal_migration.apply(self.plan_dir, manifest)

    def test_legacy_owner_decision_and_orphan_start_transitions_are_bounded(self):
        owner_decision = {
            "command": "owner-decision",
            "result": "decision-accepted",
            "decision": {"action": "owner-gate-grant"},
        }
        operations = [
            {"op": "replace", "path": "/command", "before": "owner-decision", "value": "plan-design"},
            {"op": "replace", "path": "/result", "before": "decision-accepted", "value": "no-op"},
            {"op": "add", "path": "/decision/signal_class", "value": "authority"},
            {"op": "add", "path": "/decision/scope_class", "value": "item"},
            {"op": "add", "path": "/decision/recovered", "value": False},
            {"op": "add", "path": "/decision/terminal", "value": False},
        ]
        for operation in operations:
            journal_migration._apply_operation(owner_decision, operation)
        self.assertEqual(owner_decision["command"], "plan-design")
        self.assertEqual(owner_decision["result"], "no-op")
        self.assertEqual(owner_decision["decision"]["signal_class"], "authority")

        orphan = {"result": "in-progress", "session_id": None, "run_id": None}
        journal_migration._apply_operation(orphan, {
            "op": "replace", "path": "/result", "before": "in-progress", "value": "no-op",
        })
        self.assertEqual(orphan["result"], "no-op")

    def test_identified_in_progress_run_cannot_be_reset(self):
        event = {"result": "in-progress", "session_id": "session", "run_id": "run"}
        operation = {
            "op": "replace", "path": "/result", "before": "in-progress", "value": "no-op",
        }
        with self.assertRaisesRegex(journal_migration.JournalMigrationError, "orphan in-progress"):
            journal_migration._apply_operation(event, operation)

    def test_legacy_friction_replacement_preserves_only_enum_semantics(self):
        event = {"friction": ["free-form historical note"]}
        journal_migration._apply_operation(event, {
            "op": "replace", "path": "/friction",
            "before": ["free-form historical note"], "value": ["deviation"],
        })
        self.assertEqual(event["friction"], ["deviation"])
        with self.assertRaisesRegex(journal_migration.JournalMigrationError, "legacy string"):
            journal_migration._allowed_operation({
                "op": "replace", "path": "/friction", "before": [], "value": ["deviation"],
            })


if __name__ == "__main__":
    unittest.main()
