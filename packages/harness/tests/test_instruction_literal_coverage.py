"""D76 gate: every matrix-mandated literal is asserted by its own catalog record."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from harness.instructions import (
    CATALOG_VERSION, CONTRACT_VERSION, PROVIDERS, SCOPES,
    InstructionRequest, apply_instructions, check_instructions, load_catalog, package_file,
    plan_instructions, validate_catalog, validate_literal_coverage,
)


DATA = Path(__file__).resolve().parent / "fixtures_data/instruction-literal-coverage-v1.json"


def request(operation, root, **changes):
    base = InstructionRequest(
        CONTRACT_VERSION, CATALOG_VERSION, operation, SCOPES, PROVIDERS, str(root),
        (("source", "test-config"),), (("authority", "synthetic-temp-root"),))
    return replace(base, **changes)


def write_fixture(directory, payload):
    path = Path(directory) / "instruction-literal-coverage-v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class LiteralCoverageFixtureTests(unittest.TestCase):
    def test_fixture_envelope_tracks_current_compatibility_source(self):
        fixture = json.loads(DATA.read_text(encoding="utf-8"))
        self.assertEqual(set(fixture), {"contract_version", "fixture_version", "provenance",
                                        "literals"})
        self.assertEqual(fixture["contract_version"], CONTRACT_VERSION)
        provenance = fixture["provenance"]
        self.assertEqual(provenance["source"],
                         "packages/harness/tests/fixtures_data/instruction-compatibility-v1.json")
        self.assertEqual(provenance["source_hash_scope"], "file")
        self.assertEqual(provenance["literal_count"], len(fixture["literals"]))
        self.assertTrue(all(set(item) == {"semantic_id", "literal"} for item in fixture["literals"]))


class LiteralCoverageValidatorTests(unittest.TestCase):
    def test_live_catalog_is_fully_covered(self):
        self.assertEqual(validate_literal_coverage(load_catalog()), ())

    def test_missing_literal_yields_exactly_one_diagnostic(self):
        fixture = json.loads(DATA.read_text(encoding="utf-8"))
        fixture["literals"] = list(fixture["literals"])
        fixture["literals"][0] = {
            "semantic_id": fixture["literals"][0]["semantic_id"],
            "literal": "this literal is deliberately absent from every fragment body",
        }
        with tempfile.TemporaryDirectory() as temp:
            path = write_fixture(temp, fixture)
            with patch("harness.instructions.literal_coverage_path", return_value=path):
                diagnostics = validate_literal_coverage(load_catalog())
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].code, "INSTRUCTION_COMPATIBILITY_MISMATCH")
        self.assertEqual(diagnostics[0].semantic_id, fixture["literals"][0]["semantic_id"])
        self.assertEqual(diagnostics[0].observed, "matrix literal not asserted")

    def test_unknown_semantic_id_yields_exactly_one_diagnostic(self):
        fixture = json.loads(DATA.read_text(encoding="utf-8"))
        fixture["literals"] = [{"semantic_id": "root.does-not-exist", "literal": "anything"}]
        with tempfile.TemporaryDirectory() as temp:
            path = write_fixture(temp, fixture)
            with patch("harness.instructions.literal_coverage_path", return_value=path):
                diagnostics = validate_literal_coverage(load_catalog())
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].code, "INSTRUCTION_COMPATIBILITY_MISMATCH")
        self.assertEqual(diagnostics[0].observed, "unknown semantic id")

    def test_broken_envelope_yields_exactly_one_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            path = write_fixture(temp, {"literals": []})
            with patch("harness.instructions.literal_coverage_path", return_value=path):
                diagnostics = validate_literal_coverage(load_catalog())
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].code, "INSTRUCTION_COMPATIBILITY_MISMATCH")
        self.assertEqual(diagnostics[0].expected, "D76 literal coverage fixture schema")

    def test_unreadable_fixture_yields_exactly_one_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "does-not-exist.json"
            with patch("harness.instructions.literal_coverage_path", return_value=path):
                diagnostics = validate_literal_coverage(load_catalog())
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].code, "INSTRUCTION_COMPATIBILITY_MISMATCH")
        self.assertEqual(diagnostics[0].expected, "D76 literal coverage fixture")


class LiteralCoverageProvenanceTests(unittest.TestCase):
    """D81 equality gate: the recorded `source_sha256` must equal the hash of the
    RIGHT NOW extracted §2 section, independently of the literal set below it."""

    def _tampered(self, **overrides):
        fixture = json.loads(DATA.read_text(encoding="utf-8"))
        fixture["provenance"] = {**fixture["provenance"], **overrides}
        return fixture

    def test_tampered_recorded_hash_yields_exactly_one_diagnostic(self):
        fixture = self._tampered(source_sha256="0" * 64)
        with tempfile.TemporaryDirectory() as temp:
            path = write_fixture(temp, fixture)
            with patch("harness.instructions.literal_coverage_path", return_value=path):
                diagnostics = validate_literal_coverage(load_catalog())
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].code, "INSTRUCTION_PROVENANCE_INVALID")
        self.assertEqual(diagnostics[0].observation, "provenance-invalid")

    def test_unreadable_source_yields_diagnostic_not_exception(self):
        with patch("harness.instructions._literal_coverage_source_text",
                   side_effect=FileNotFoundError("boom")):
            diagnostics = validate_literal_coverage(load_catalog())
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].code, "INSTRUCTION_PROVENANCE_INVALID")

    def test_unknown_source_hash_scope_yields_exactly_one_diagnostic(self):
        fixture = self._tampered(source_hash_scope="unknown")
        with tempfile.TemporaryDirectory() as temp:
            path = write_fixture(temp, fixture)
            with patch("harness.instructions.literal_coverage_path", return_value=path):
                diagnostics = validate_literal_coverage(load_catalog())
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].code, "INSTRUCTION_PROVENANCE_INVALID")

    def test_current_fixture_source_edit_changes_provenance(self):
        source_path = package_file(json.loads(
            DATA.read_text(encoding="utf-8"))["provenance"]["source"])
        text = source_path.read_text(encoding="utf-8") + "\n<!-- P2.6 edit outside §2 -->\n"
        with patch("harness.instructions._literal_coverage_source_text", return_value=text):
            diagnostics = validate_literal_coverage(load_catalog())
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].code, "INSTRUCTION_PROVENANCE_INVALID")


class LiteralCoverageWiringTests(unittest.TestCase):
    def _clean_root(self, temp):
        root = Path(temp).resolve()
        planned = plan_instructions(request("plan", root))
        targets = tuple(action.target_path for action in planned.artifact_plan.actions)
        applied = apply_instructions(request("apply", root, authorized_target_paths=targets))
        self.assertTrue(applied.green)
        return root

    def test_check_instructions_is_red_when_coverage_is_red(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._clean_root(temp)
            with tempfile.TemporaryDirectory() as fixture_dir:
                path = write_fixture(fixture_dir, {"literals": []})
                with patch("harness.instructions.literal_coverage_path", return_value=path):
                    checked = check_instructions(request("check", root))
        self.assertFalse(checked.green)
        self.assertIn("INSTRUCTION_COMPATIBILITY_MISMATCH",
                      tuple(item.code for item in checked.diagnostics))

    def test_check_instructions_is_green_again_once_coverage_is_restored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self._clean_root(temp)
            checked = check_instructions(request("check", root))
        self.assertTrue(checked.green)

    def test_validate_catalog_and_plan_instructions_ignore_coverage(self):
        """The gate lives only in `check_instructions` — `validate_catalog`/`plan_instructions`
        stay green on an already-clean root even under a broken coverage fixture, or `apply`
        would deadlock on the very red verdict it is meant to repair."""
        with tempfile.TemporaryDirectory() as temp:
            root = self._clean_root(temp)
            with tempfile.TemporaryDirectory() as fixture_dir:
                path = write_fixture(fixture_dir, {"literals": []})
                with patch("harness.instructions.literal_coverage_path", return_value=path):
                    self.assertEqual(validate_catalog(load_catalog()), ())
                    planned = plan_instructions(request("plan", root))
        self.assertTrue(planned.green)


if __name__ == "__main__":
    unittest.main()
