import json
import tempfile
import unittest
from pathlib import Path

from aicore.provider.values import (CapabilityId, ConfigSource, NativeExtensionId, ProviderId,
                                    SupportLevel)
from aicore.provider.config import (CapabilitySupport, NativeExtension, ProviderConfigCatalog,
                                    ProviderConfigLayer, effective_projection,
                                    resolve_provider_config)
from aicore.provider.manifest import (default_manifest_path, load_provider_manifest,
                                      provider_config_catalog)


def catalog():
    return ProviderConfigCatalog("1.0.0", (ProviderId.CLAUDE_CODE, ProviderId.CODEX),
        (CapabilitySupport(CapabilityId("instructions.project"), ProviderId.CLAUDE_CODE, SupportLevel.NATIVE),
         CapabilitySupport(CapabilityId("skills.repository"), ProviderId.CODEX, SupportLevel.NATIVE),
         CapabilitySupport(CapabilityId("hooks.lifecycle"), ProviderId.CODEX, SupportLevel.UNSUPPORTED)),
        (NativeExtension(NativeExtensionId("claude-code.fixture-native"), ProviderId.CLAUDE_CODE),
         NativeExtension(NativeExtensionId("codex.fixture-native"), ProviderId.CODEX)))


def layer(kind, value, path=None):
    paths = {"operation": "/", "project": "/providers", "fleet-project": "/projects/0/providers", "fleet-defaults": "/providers/defaults"}
    carriers = {"operation": "operation", "project": ".swissknife.json", "fleet-project": "config.json", "fleet-defaults": "config.json"}
    return ProviderConfigLayer(ConfigSource(kind, f"{kind}:demo", carriers[kind], path or paths[kind]), value)


def config(selection):
    return {"contract_version": "1.0.0", "selection": selection}


COMPATIBILITY_CASES = (
    ("C1", {}, {"claude-code": True, "codex": False}, ["PCFG_LEGACY_DEFAULT_APPLIED"]),
    ("C2", {"fleet_defaults": config({"claude-code": {"enabled": True}})},
     {"claude-code": True, "codex": False}, []),
    ("C3", {"fleet_project": config({"codex": {"enabled": True}})},
     {"claude-code": True, "codex": True}, []),
    ("C4", {"project": config({"claude-code": {"enabled": False}})},
     {"claude-code": False, "codex": False}, []),
    ("C5", {"operation": config({"codex": {"enabled": True}})},
     {"claude-code": True, "codex": True}, []),
    ("C6", {"project": config({"claude-code": {"enabled": True}})},
     {"claude-code": True, "codex": False}, []),
    ("C7", {"project": config({"claude-code": {"enabled": False}, "codex": {"enabled": True}})},
     {"claude-code": False, "codex": True}, []),
    ("C8", {"project": config({"claude-code": {"enabled": True}, "codex": {"enabled": True}})},
     {"claude-code": True, "codex": True}, []),
    ("C9", {"fleet_defaults": config({"codex": {"enabled": True}}),
             "project": config({"codex": {"enabled": False}})},
     {"claude-code": True, "codex": False}, []),
)


def compatibility_layers(case_layers):
    return {kind: layer(kind.replace("_", "-"), value)
            for kind, value in case_layers.items()}


class TestProviderConfigResolution(unittest.TestCase):
    def test_root_manifest_projection_resolves_supported_and_unsupported(self):
        projected = provider_config_catalog(load_provider_manifest(
            default_manifest_path()))
        accepted = resolve_provider_config(
            catalog=projected,
            project=layer("project", config({"codex": {
                "capabilities": {"skills.repository": True}}})))
        rejected = resolve_provider_config(
            catalog=projected,
            project=layer("project", config({"codex": {
                "capabilities": {"workflows.status": True}}})))
        self.assertIsNotNone(accepted.effective)
        self.assertEqual(rejected.diagnostics[0].code, "PCFG_CAPABILITY_UNSUPPORTED")

    def test_synthetic_protected_carriers_remain_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            carriers = {
                root / "repository" / "config.json": (
                    b'{"providers":{"contract_version":"1.0.0","selection":'
                    b'{"codex":{"enabled":true}}}}\n'
                ),
                root / "protected-plan" / "sentinel.txt": b"protected plan sentinel\n",
                root / "external-fleet" / "config.json": b"external fleet sentinel\n",
            }
            for path, content in carriers.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            before = {path: path.read_bytes() for path in carriers}

            project = json.loads((root / "repository" / "config.json").read_text(encoding="utf-8"))
            result = resolve_provider_config(
                catalog=catalog(),
                project=layer("project", project["providers"]),
            )

            self.assertTrue(effective_projection(result)["codex"]["enabled"])
            self.assertEqual({path: path.read_bytes() for path in carriers}, before)

    def test_legacy_default_is_distinct_and_sorted(self):
        result = resolve_provider_config(catalog=catalog())
        self.assertEqual(effective_projection(result)["claude-code"]["enabled"], True)
        self.assertFalse(result.provenance[0].explicit)
        self.assertEqual([item.code for item in result.diagnostics], ["PCFG_LEGACY_DEFAULT_APPLIED"])

    def test_compound_precedence_and_provenance(self):
        result = resolve_provider_config(catalog=catalog(),
            fleet_defaults=layer("fleet-defaults", config({"codex": {"enabled": False, "capabilities": {"skills.repository": False}}})),
            fleet_project=layer("fleet-project", config({"codex": {"enabled": True}})),
            project=layer("project", config({"codex": {"capabilities": {"skills.repository": False}}})),
            operation=layer("operation", config({"codex": {"capabilities": {"skills.repository": True}}})))
        self.assertEqual(effective_projection(result)["codex"], {"enabled": True, "capabilities": {"skills.repository": True}, "native_extensions": {}})
        winners = {item.effective_path: item.source.kind for item in result.provenance}
        self.assertEqual(winners["/selection/codex/capabilities/skills.repository"], "operation")

    def test_invalid_ids_fail_closed_in_stable_order(self):
        result = resolve_provider_config(catalog=catalog(), project=layer("project", config({"chatgpt": {"enabled": True}, "codex": {"capabilities": {"hooks.lifecycle": True, "unknown": False}}})))
        self.assertIsNone(result.effective)
        self.assertEqual([item.code for item in result.diagnostics], ["PCFG_UNKNOWN_PROVIDER", "PCFG_CAPABILITY_UNSUPPORTED", "PCFG_UNKNOWN_CAPABILITY"])

    def test_input_is_not_mutated_and_duplicate_fleet_fails_closed(self):
        data = config({"codex": {"enabled": False}})
        fleet = layer("fleet-project", data)
        result = resolve_provider_config(catalog=catalog(), fleet_project=(fleet, fleet))
        self.assertEqual(data["selection"]["codex"]["enabled"], False)
        self.assertIsNone(result.effective)
        self.assertEqual(result.diagnostics[0].code, "PCFG_DUPLICATE_FLEET_PROJECT")

    def test_canonical_compatibility_case_table(self):
        for case_id, supplied, expected, diagnostic_codes in COMPATIBILITY_CASES:
            with self.subTest(case=case_id):
                result = resolve_provider_config(catalog=catalog(), **compatibility_layers(supplied))
                self.assertEqual(
                    {key: value["enabled"] for key, value in effective_projection(result).items()},
                    expected,
                )
                self.assertEqual([item.code for item in result.diagnostics], diagnostic_codes)

    def test_all_layers_preserve_leaf_provenance_and_explicit_disable(self):
        result = resolve_provider_config(
            catalog=catalog(),
            fleet_defaults=layer("fleet-defaults", config({"claude-code": {"enabled": True}, "codex": {"enabled": False}})),
            fleet_project=layer("fleet-project", config({"codex": {"enabled": True}})),
            project=layer("project", config({"codex": {"enabled": False}})),
            operation=layer("operation", config({"codex": {"enabled": True}})),
        )
        winners = {item.effective_path: (item.source.kind, item.explicit) for item in result.provenance}
        self.assertEqual(winners["/selection/claude-code/enabled"], ("fleet-defaults", True))
        self.assertEqual(winners["/selection/codex/enabled"], ("operation", True))

    def test_negative_table_is_fail_closed_and_deterministic(self):
        cases = (
            ("C10", config({"chatgpt": {"enabled": False}}), "PCFG_UNKNOWN_PROVIDER"),
            ("C11", config({"codex": {"capabilities": {"hooks.lifecycle": True}}}), "PCFG_CAPABILITY_UNSUPPORTED"),
            ("C12", config({"codex": {"enabled": "true"}}), "PCFG_SCHEMA_INVALID"),
            ("C13", config({"codex": {"enabled": True, "options": {}}}), "PCFG_UNKNOWN_FIELD"),
            ("C14", config({"codex": {"capabilities": {"skills.unknown": False}}}), "PCFG_UNKNOWN_CAPABILITY"),
            ("C15", config({"claude-code": {"native_extensions": {"codex.fixture-native": False}}}), "PCFG_EXTENSION_PROVIDER_MISMATCH"),
        )
        for case_id, value, code in cases:
            with self.subTest(case=case_id):
                result = resolve_provider_config(catalog=catalog(), project=layer("project", value))
                self.assertIsNone(result.effective)
                self.assertEqual(result.diagnostics[0].code, code)

    def test_available_key_is_accepted_and_validated(self):
        merged = {"contract_version": "1.0.0", "available": {"codex": {"enabled": False}}}
        result = resolve_provider_config(catalog=catalog(), fleet_defaults=layer("fleet-defaults", merged))
        self.assertEqual(result.diagnostics, ())  # availability alone is a complete layer; selection is unaffected
        self.assertEqual(effective_projection(result)["codex"]["enabled"], False)
        both = {**config({"codex": {"enabled": True}}), "available": {"codex": {"enabled": False}}}
        result = resolve_provider_config(catalog=catalog(), project=layer("project", both))
        self.assertTrue(effective_projection(result)["codex"]["enabled"])
        cases = (
            ({"chatgpt": {"enabled": False}}, "PCFG_UNKNOWN_PROVIDER"),
            ({"codex": {"enabled": "no"}}, "PCFG_SCHEMA_INVALID"),
            ({"codex": {"auth": "x"}}, "PCFG_UNKNOWN_FIELD"),
            ({}, "PCFG_SCHEMA_INVALID"),
        )
        for available, code in cases:
            with self.subTest(available=available):
                result = resolve_provider_config(catalog=catalog(), project=layer(
                    "project", {**config({"codex": {"enabled": True}}), "available": available}))
                self.assertIsNone(result.effective)
                self.assertEqual(result.diagnostics[0].code, code)
