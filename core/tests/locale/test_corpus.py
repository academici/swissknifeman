import json
from pathlib import Path
import tempfile
import unittest

from core.locale.corpus import CorpusError, apply_row, check_ledger, inventory, review_markdown, rollback_row, sha256_prefixed, verify_batch


def row(path="skills/example/SKILL.md", *, status="admitted"):
    source = b"English source\n"
    return {
        "id": "skill.example", "carrier_id": "semantic.skill", "owner": "skiller",
        "cwd": "packages/skiller", "source_path": path, "source_locale": "en",
        "source_preimage_sha256": sha256_prefixed(source), "immutable_tokens": ["SKILL.md"],
        "author": "author", "renderer": "renderer",
        "reviews": [{"locale": "en", "reviewer": "english-reviewer", "outcome": "pass"}, {"locale": "ru", "reviewer": "russian-reviewer", "outcome": "pass"}],
        "generated_owner": "skiller registry", "status": status,
        "rollback": {"id": "rollback-skill-example", "backup": "skill.example.preimage"},
        "apply": {"text": "English source with SKILL.md\n"},
    }


def ledger(rows):
    return {"$schema": "urn:swissknifeman:locale-corpus:v1", "contract_version": "1.0.0", "source_locale": "en", "overlay_locales": ["ru"], "carrier_classes": ["semantic.skill"], "inventory_roots": [], "rows": rows}


class CorpusTests(unittest.TestCase):
    def test_admitted_row_and_deterministic_projection(self):
        report = check_ledger(ledger([row()]), root=Path.cwd())
        self.assertTrue(report.ok)
        self.assertEqual(review_markdown(ledger([row()])), review_markdown(ledger([row()])))

    def test_review_and_generated_rows_refuse(self):
        self.assertIn("AUTHORING_SELF_REVIEW", check_ledger(ledger([row() | {"reviews": [{"locale": "en", "reviewer": "author", "outcome": "pass"}, {"locale": "ru", "reviewer": "russian-reviewer", "outcome": "pass"}]}]), root=Path.cwd()).errors)
        self.assertIn("OVERLAY_GENERATED_EDIT_FORBIDDEN", check_ledger(ledger([row(".agents/skills/example/SKILL.md")]), root=Path.cwd()).errors)

    def test_apply_rechecks_preimage_and_rollback_recovers_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "skills/example/SKILL.md"
            source.parent.mkdir(parents=True)
            source.write_text("English source\n", encoding="utf-8")
            data = ledger([row()])
            backup = apply_row(data, "skill.example", root=root, checkpoint_dir=root / "checkpoints")
            self.assertTrue(backup.is_file())
            self.assertEqual(source.read_text(encoding="utf-8"), "English source with SKILL.md\n")
            rollback_row(data, "skill.example", root=root, checkpoint_dir=root / "checkpoints")
            self.assertEqual(source.read_text(encoding="utf-8"), "English source\n")

    def test_batch_rejects_self_review_and_resume_skip(self):
        data = ledger([row()])
        batch = {"$schema": "urn:swissknifeman:locale-corpus-batch:v1", "row_ids": ["skill.example"], "author": "author", "reviewer": {"reviewer": "author", "verdict": "pass"}, "review_round": 1, "commits": ["abc"], "commands": [{"exit_code": 0}], "rollback": {"id": "r", "backup": "b"}, "resume_cursor": "wrong"}
        errors = verify_batch(batch, data)
        self.assertIn("AUTHORING_SELF_REVIEW", errors)
        self.assertIn("LOCALE_BATCH_RESUME_SKIP", errors)

    def test_inventory_is_extension_aware_and_no_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "skills").mkdir()
            (root / "skills/example.md").write_text("x", encoding="utf-8")
            (root / "skills/ignore.txt").write_text("x", encoding="utf-8")
            data = ledger([]) | {"inventory_roots": ["skills"]}
            self.assertEqual(inventory(data, root=root), [{"path": "skills/example.md", "classification": "unadmitted"}])

    def test_apply_refuses_non_admitted_or_foreign_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = ledger([row(status="planned")])
            with self.assertRaisesRegex(CorpusError, "NOT_ADMITTED"):
                apply_row(data, "skill.example", root=Path(temporary), checkpoint_dir=Path(temporary) / "checkpoints")
