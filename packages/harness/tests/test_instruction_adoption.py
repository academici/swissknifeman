"""P1.4 adoption-mode tests: every target is synthetic and temporary (no live self-host)."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from core.provider.artifact import sha256_digest
from core.provider.lock import parse_lock
from harness.instructions import (
    CATALOG_VERSION, CONTRACT_VERSION, InstructionRequest, InstructionValidationError,
    adopt_instructions, check_instructions, rollback_adoption,
)


def request(operation, root, **changes):
    base = InstructionRequest(
        CONTRACT_VERSION, CATALOG_VERSION, operation, ("root",), ("codex",), str(root),
        (("config_id", "test-config"), ("source", "contract-fixture")),
        (("authority", "synthetic-temp-root"),),
    )
    return replace(base, **changes)


def snapshot(root):
    return tuple((path.relative_to(root).as_posix(), path.read_bytes())
                 for path in sorted(root.rglob("*")) if path.is_file())


def diagnostic_codes(result):
    return tuple(item.code for item in result.diagnostics)


def write_mapping(directory, target_path, covered_spans):
    path = directory / "mapping.json"
    path.write_text(json.dumps({target_path: {"covered_spans": list(covered_spans)}}),
                    encoding="utf-8")
    return path


class AdoptionTests(unittest.TestCase):
    TARGET = "AGENTS.md"

    def _seed(self, root):
        raw = (b"legacy root guidance, pre-canon\n"
               b"more legacy prose that the canon now expresses\n"
               b"CUSTOM: local note the owner wrote by hand\n")
        (root / self.TARGET).write_bytes(raw)
        return raw

    def test_successful_adopt_writes_managed_blocks_lock_and_preserves_uncovered_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            raw = self._seed(root)
            boundary = raw.index(b"CUSTOM:")
            preimage_dir = root / "preimage"
            preimage_dir.mkdir()
            mapping_path = write_mapping(root, self.TARGET, [[0, boundary]])
            result = adopt_instructions(request(
                "adopt", root, authorized_target_paths=(self.TARGET,),
                owner_decision="D999", mapping_path=str(mapping_path),
                preimage_destination=str(preimage_dir)))
            self.assertTrue(result.green, diagnostic_codes(result))
            self.assertEqual(result.targets[0].action, "adopt")
            self.assertEqual(result.targets[0].observation, "clean")
            written = (root / self.TARGET).read_bytes()
            self.assertTrue(written.startswith(
                b"<!-- swissknifeman:instructions:root:codex:common:begin -->"))
            self.assertTrue(written.endswith(raw[boundary:]))
            preimage_files = list(preimage_dir.glob("*.preimage"))
            self.assertEqual(len(preimage_files), 1)
            self.assertEqual(preimage_files[0].read_bytes(), raw)
            lock = parse_lock((root / ".swissknifeman/provider-artifacts.lock.json").read_bytes())
            record = next(item for item in lock.records if item.target_path == self.TARGET)
            adoption = dict(record.semantic_metadata)["adoption"]
            self.assertEqual(adoption["owner_decision"], "D999")
            self.assertEqual(adoption["mapping_path"], str(mapping_path))
            self.assertEqual(adoption["pre_image_hash"], sha256_digest(raw))
            self.assertEqual(adoption["pre_image_path"],
                             preimage_files[0].relative_to(root).as_posix())

    def test_refuses_target_that_is_not_ownership_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            preimage_dir = root / "preimage"
            preimage_dir.mkdir()
            mapping_path = write_mapping(root, self.TARGET, [[0, 1]])
            before = snapshot(root)
            result = adopt_instructions(request(
                "adopt", root, authorized_target_paths=(self.TARGET,),
                owner_decision="D999", mapping_path=str(mapping_path),
                preimage_destination=str(preimage_dir)))
            self.assertFalse(result.green)
            self.assertIn("INSTRUCTION_WRITE_FORBIDDEN", diagnostic_codes(result))
            self.assertEqual(snapshot(root), before)

    def test_refuses_incomplete_mapping_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self._seed(root)
            preimage_dir = root / "preimage"
            preimage_dir.mkdir()
            mapping_path = write_mapping(root, self.TARGET, [])
            before = snapshot(root)
            result = adopt_instructions(request(
                "adopt", root, authorized_target_paths=(self.TARGET,),
                owner_decision="D999", mapping_path=str(mapping_path),
                preimage_destination=str(preimage_dir)))
            self.assertFalse(result.green)
            self.assertIn("INSTRUCTION_WRITE_FORBIDDEN", diagnostic_codes(result))
            self.assertEqual(snapshot(root), before)
            self.assertFalse((root / ".swissknifeman/provider-artifacts.lock.json").exists())

    def test_refuses_mapping_that_covers_only_whitespace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            raw = self._seed(root)
            preimage_dir = root / "preimage"
            preimage_dir.mkdir()
            newline_index = raw.index(b"\n")
            mapping_path = write_mapping(root, self.TARGET, [[newline_index, newline_index + 1]])
            before = snapshot(root)
            result = adopt_instructions(request(
                "adopt", root, authorized_target_paths=(self.TARGET,),
                owner_decision="D999", mapping_path=str(mapping_path),
                preimage_destination=str(preimage_dir)))
            self.assertFalse(result.green)
            self.assertIn("INSTRUCTION_WRITE_FORBIDDEN", diagnostic_codes(result))
            self.assertEqual(snapshot(root), before)

    def test_no_write_on_missing_owner_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self._seed(root)
            preimage_dir = root / "preimage"
            preimage_dir.mkdir()
            mapping_path = write_mapping(root, self.TARGET, [[0, 5]])
            before = snapshot(root)
            result = adopt_instructions(request(
                "adopt", root, authorized_target_paths=(self.TARGET,),
                owner_decision=None, mapping_path=str(mapping_path),
                preimage_destination=str(preimage_dir)))
            self.assertFalse(result.green)
            self.assertIn("INSTRUCTION_WRITE_FORBIDDEN", diagnostic_codes(result))
            self.assertEqual(snapshot(root), before)

    def test_second_check_after_adopt_is_clean_and_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            raw = self._seed(root)
            boundary = raw.index(b"CUSTOM:")
            preimage_dir = root / "preimage"
            preimage_dir.mkdir()
            mapping_path = write_mapping(root, self.TARGET, [[0, boundary]])
            adopted = adopt_instructions(request(
                "adopt", root, authorized_target_paths=(self.TARGET,),
                owner_decision="D999", mapping_path=str(mapping_path),
                preimage_destination=str(preimage_dir)))
            self.assertTrue(adopted.green)
            first = check_instructions(request("check", root)).as_dict()
            second = check_instructions(request("check", root)).as_dict()
            self.assertEqual(first, second)
            self.assertTrue(first["green"])
            self.assertTrue(all(item["observation"] == "clean" for item in first["targets"]))

    def test_repeat_adopt_of_already_adopted_target_refuses(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            raw = self._seed(root)
            boundary = raw.index(b"CUSTOM:")
            preimage_dir = root / "preimage"
            preimage_dir.mkdir()
            mapping_path = write_mapping(root, self.TARGET, [[0, boundary]])
            first = adopt_instructions(request(
                "adopt", root, authorized_target_paths=(self.TARGET,),
                owner_decision="D999", mapping_path=str(mapping_path),
                preimage_destination=str(preimage_dir)))
            self.assertTrue(first.green)
            second = adopt_instructions(request(
                "adopt", root, authorized_target_paths=(self.TARGET,),
                owner_decision="D999", mapping_path=str(mapping_path),
                preimage_destination=str(preimage_dir)))
            self.assertFalse(second.green)
            self.assertIn("INSTRUCTION_WRITE_FORBIDDEN", diagnostic_codes(second))

    def test_rollback_restores_preimage_byte_for_byte_and_drops_lock_record(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            raw = self._seed(root)
            boundary = raw.index(b"CUSTOM:")
            preimage_dir = root / "preimage"
            preimage_dir.mkdir()
            mapping_path = write_mapping(root, self.TARGET, [[0, boundary]])
            adopted = adopt_instructions(request(
                "adopt", root, authorized_target_paths=(self.TARGET,),
                owner_decision="D999", mapping_path=str(mapping_path),
                preimage_destination=str(preimage_dir)))
            self.assertTrue(adopted.green)
            restored = rollback_adoption(root, self.TARGET)
            self.assertEqual(restored, raw)
            self.assertEqual((root / self.TARGET).read_bytes(), raw)
            lock_path = root / ".swissknifeman/provider-artifacts.lock.json"
            lock = parse_lock(lock_path.read_bytes()) if lock_path.is_file() else None
            self.assertTrue(lock is None or not any(
                item.target_path == self.TARGET for item in lock.records))
            reverted = check_instructions(request("check", root))
            self.assertEqual(reverted.targets[0].observation, "ownership-conflict")

    def test_rollback_without_adoption_record_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self._seed(root)
            with self.assertRaises(InstructionValidationError):
                rollback_adoption(root, self.TARGET)


if __name__ == "__main__":
    unittest.main()
