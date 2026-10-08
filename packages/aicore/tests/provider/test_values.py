"""Focused contract tests for the immutable provider-domain API."""
from dataclasses import FrozenInstanceError, asdict
import unittest

from aicore.provider import values as values_module
from aicore.provider.values import (CapabilityId, CapabilityRequirement, ConfigProvenance,
                                    ConfigSource, DiagnosticSeverity, EffectiveProvider,
                                    NativeExtensionId, ProviderDecision, ProviderDiagnostic,
                                    ProviderId, ProviderSelection, SupportLevel)


class TestProviderDomain(unittest.TestCase):
    def setUp(self):
        self.source = ConfigSource("project", "project:demo", ".swissknife.json", "/providers")
        self.capability = CapabilityId("skills.repository")
        self.extension = NativeExtensionId("codex.fixture-native")

    def test_every_public_value_type_constructs_and_serializes(self):
        requirement = CapabilityRequirement(self.capability, (SupportLevel.NATIVE, SupportLevel.ADAPTED))
        capability_decision = ProviderDecision(self.capability, True)
        extension_decision = ProviderDecision(self.extension, False)
        selection = ProviderSelection(ProviderId.CODEX, None, (capability_decision,), (extension_decision,))
        effective = EffectiveProvider(ProviderId.CODEX, True, (capability_decision,), (extension_decision,))
        provenance = ConfigProvenance("/selection/codex/enabled", self.source,
                                      "/providers/selection/codex/enabled", True)
        diagnostic = ProviderDiagnostic(DiagnosticSeverity.ERROR, "PCFG_UNKNOWN_PROVIDER",
                                        "/providers/selection/chatgpt", self.source,
                                        context=(("provider", "chatgpt"),))
        self.assertEqual(requirement.accepted_levels, (SupportLevel.ADAPTED, SupportLevel.NATIVE))
        self.assertEqual(selection.enabled, None)
        self.assertTrue(effective.enabled)
        self.assertTrue(provenance.explicit)
        self.assertEqual(asdict(diagnostic)["code"], "PCFG_UNKNOWN_PROVIDER")

    def test_values_are_frozen_and_decisions_are_ordered(self):
        selection = ProviderSelection(
            ProviderId.CODEX, True,
            (ProviderDecision(CapabilityId("skills.repository"), False),
             ProviderDecision(CapabilityId("instructions.project"), True)),
        )
        with self.assertRaises(FrozenInstanceError):
            selection.enabled = False
        self.assertEqual([item.identifier.value for item in selection.capabilities],
                         ["instructions.project", "skills.repository"])

    def test_validation_rejects_invalid_normative_values(self):
        with self.assertRaises(ValueError):
            CapabilityId("Skills.Repository")
        with self.assertRaises(ValueError):
            NativeExtensionId("unknown.fixture")
        with self.assertRaises(TypeError):
            CapabilityRequirement(self.capability, [SupportLevel.NATIVE])
        with self.assertRaises(TypeError):
            ProviderSelection(ProviderId.CODEX, True, (ProviderDecision(self.extension, True),))
        with self.assertRaises(ValueError):
            ConfigSource("project", "project:demo", ".swissknife.json", "providers")
        with self.assertRaises(ValueError):
            ProviderDiagnostic(DiagnosticSeverity.INFO, "", "/", self.source)

    def test_exports_match_the_approved_public_surface(self):
        expected = {
            "ProviderId", "SupportLevel", "DiagnosticSeverity", "CapabilityId",
            "NativeExtensionId", "CapabilityRequirement", "ProviderDecision",
            "ProviderSelection", "EffectiveProvider", "ConfigSource", "ConfigProvenance",
            "ProviderDiagnostic", "ProviderAdapter",
        }
        self.assertTrue(all(hasattr(values_module, name) for name in expected))


if __name__ == "__main__":
    unittest.main()
