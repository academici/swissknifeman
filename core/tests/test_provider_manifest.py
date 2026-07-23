import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core import (ProviderId, ProviderManifestError, SupportLevel,
                  load_provider_manifest, parse_provider_manifest,
                  provider_config_catalog, provider_manifest_canonical_bytes,
                  provider_manifest_sha256, provider_support_projection)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "configs" / "provider-capabilities.json"
APPROVED_CANONICAL_SHA256 = "4c479c697c708cfea8d36589c435338094d894bcf428687709987975b13b6ce1"
APPROVED_CARRIER_SHA256 = "32975d675cf252bba87b06aaee53bfe37e63a9a97dc74cb7a12a8a2b0c0394eb"


def manifest_value():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def assert_code(test, value, code):
    with test.assertRaises(ProviderManifestError) as caught:
        parse_provider_manifest(value)
    test.assertIn(code, {item.code for item in caught.exception.diagnostics})


class TestProviderManifest(unittest.TestCase):
    def test_approved_carrier_round_trips_with_distinct_canonical_and_carrier_hashes(self):
        raw = MANIFEST_PATH.read_bytes()
        manifest = parse_provider_manifest(raw, source_id=str(MANIFEST_PATH))
        self.assertEqual(provider_manifest_sha256(manifest), APPROVED_CANONICAL_SHA256)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), APPROVED_CARRIER_SHA256)
        self.assertEqual(raw, provider_manifest_canonical_bytes(manifest) + b"\n")
        self.assertEqual((len(manifest.providers), len(manifest.capabilities),
                          len(manifest.native_extensions)), (2, 35, 0))

    def test_contract_compatibility_accepts_v1_minor_and_rejects_next_major(self):
        compatible = manifest_value()
        compatible["contract_version"] = "1.7.3"
        manifest = parse_provider_manifest(compatible)
        self.assertEqual(manifest.contract_version, "1.7.3")
        self.assertEqual(json.loads(provider_manifest_canonical_bytes(manifest))[
            "contract_version"], "1.7.3")
        incompatible = manifest_value()
        incompatible["contract_version"] = "2.0.0"
        assert_code(self, incompatible, "MANIFEST_VERSION_UNSUPPORTED")

    def test_binding_round_trip_preserves_empty_and_pair_shaped_json_arrays(self):
        value = manifest_value()
        binding = value["capabilities"][6]["support"]["claude-code"]["binding"]
        binding["empty_array"] = []
        binding["pair_shaped_array"] = [["key", "value"]]
        canonical = json.loads(provider_manifest_canonical_bytes(
            parse_provider_manifest(value)))
        observed = canonical["capabilities"][6]["support"]["claude-code"]["binding"]
        self.assertEqual(observed["empty_array"], [])
        self.assertEqual(observed["pair_shaped_array"], [["key", "value"]])

    def test_noncanonical_supplied_provider_display_name_is_rejected(self):
        value = manifest_value()
        value["providers"][0]["display_name"] = "Changed display name"
        assert_code(self, value, "MANIFEST_PROVIDER_INVALID")

    def test_projection_is_complete_immutable_and_uses_unchanged_catalog(self):
        manifest = load_provider_manifest(MANIFEST_PATH)
        catalog = provider_config_catalog(manifest)
        self.assertEqual(catalog.catalog_version, "1.0.0")
        self.assertEqual(len(catalog.capability_support), 70)
        for provider in ProviderId:
            projection = provider_support_projection(manifest, provider)
            self.assertEqual(len(projection), 35)
            self.assertEqual(projection["skills.repository"], SupportLevel.NATIVE)
            with self.assertRaises(TypeError):
                projection["skills.repository"] = SupportLevel.UNSUPPORTED

    def test_loader_reads_only_supplied_path_and_is_no_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exact = root / "exact.json"
            sibling = root / "configs" / "provider-capabilities.json"
            sibling.parent.mkdir()
            sibling.write_bytes(MANIFEST_PATH.read_bytes())
            exact.write_text("{}\n", encoding="utf-8")
            before = {path: path.read_bytes() for path in (exact, sibling)}
            with self.assertRaises(ProviderManifestError):
                load_provider_manifest(exact)
            self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_duplicate_json_object_key_is_rejected(self):
        raw = MANIFEST_PATH.read_bytes().rstrip(b"\n")
        duplicate = raw[:-1] + b',"catalog_version":"1.0.0"}'
        assert_code(self, duplicate, "MANIFEST_SCHEMA_INVALID")

    def test_negative_validation_matrix_covers_frozen_contract(self):
        cases = []

        value = manifest_value(); value["providers"].append(copy.deepcopy(value["providers"][0]))
        cases.append(("duplicate-provider", value, "MANIFEST_PROVIDER_INVALID"))
        value = manifest_value(); value["capabilities"][0]["id"] = "Invalid ID"
        cases.append(("invalid-capability", value, "MANIFEST_CAPABILITY_INVALID"))
        value = manifest_value(); del value["capabilities"][0]["support"]["codex"]
        cases.append(("missing-matrix", value, "MANIFEST_SUPPORT_MATRIX_INVALID"))
        value = manifest_value(); value["capabilities"][0]["support"]["codex"]["level"] = "maybe"
        cases.append(("unknown-level", value, "MANIFEST_SUPPORT_LEVEL_INVALID"))

        value = manifest_value(); native = value["capabilities"][6]["support"]["claude-code"]
        del native["binding"]
        cases.append(("native-without-binding", value, "MANIFEST_SUPPORT_INVARIANT"))
        value = manifest_value(); native = value["capabilities"][6]["support"]["claude-code"]
        native["adapter_id"] = "fixture.adapter"
        cases.append(("native-with-adapter", value, "MANIFEST_SUPPORT_INVARIANT"))

        value = manifest_value(); adapted = value["capabilities"][0]["support"]["claude-code"]
        del adapted["adapter_id"]
        cases.append(("adapted-without-adapter", value, "MANIFEST_SUPPORT_INVARIANT"))
        value = manifest_value(); adapted = value["capabilities"][0]["support"]["claude-code"]
        adapted["limitations"] = []
        cases.append(("adapted-without-limitations", value, "MANIFEST_SUPPORT_INVARIANT"))

        value = manifest_value(); unsupported = value["capabilities"][0]["support"]["codex"]
        unsupported["binding"] = {"surface": "invented"}
        cases.append(("unsupported-with-binding", value, "MANIFEST_SUPPORT_INVARIANT"))
        value = manifest_value(); unsupported = value["capabilities"][0]["support"]["codex"]
        unsupported["diagnostic"] = "not available"
        cases.append(("unsupported-without-fail-closed", value, "MANIFEST_SUPPORT_INVARIANT"))

        value = manifest_value(); value["capabilities"][0]["support"]["codex"]["evidence"] = []
        cases.append(("missing-evidence", value, "MANIFEST_EVIDENCE_INVALID"))
        value = manifest_value(); value["capabilities"][0]["support"]["codex"]["autonomy"] = True
        cases.append(("collapsed-security-axis", value, "MANIFEST_SECURITY_AXES_COLLAPSED"))
        value = manifest_value(); value["contract_version"] = "2.0.0"
        cases.append(("unknown-contract-major", value, "MANIFEST_VERSION_UNSUPPORTED"))

        for name, value, code in cases:
            with self.subTest(case=name):
                assert_code(self, value, code)

    def test_native_extension_requires_owner_namespace_and_evidence(self):
        value = manifest_value()
        value["native_extensions"] = [{
            "id": "codex.fixture", "provider_id": "claude-code", "intent": "fixture",
            "binding": {"surface": "fixture"}, "evidence": [{
                "source": "fixture", "verified_at": "2026-07-22", "scope": "fixture",
                "claim": "fixture",
            }], "diagnostic": "fixture",
        }]
        assert_code(self, value, "MANIFEST_EXTENSION_INVALID")
        value = manifest_value()
        value["native_extensions"] = [{
            "id": "codex.fixture", "provider_id": "codex", "intent": "fixture",
            "binding": {"surface": "fixture"}, "evidence": [], "diagnostic": "fixture",
        }]
        assert_code(self, value, "MANIFEST_EVIDENCE_INVALID")


if __name__ == "__main__":
    unittest.main()
