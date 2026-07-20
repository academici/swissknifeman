import unittest

from core import (CapabilityId, CapabilitySupport, ConfigSource, NativeExtension,
                  NativeExtensionId, ProviderConfigCatalog, ProviderConfigLayer,
                  ProviderId, SupportLevel, effective_projection,
                  resolve_provider_config)


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


class TestProviderConfigResolution(unittest.TestCase):
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
