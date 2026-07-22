import unittest
from pathlib import Path

from core.provider import (CapabilityId, CapabilityRequirement, EffectiveProvider,
                           NativeExtensionId, ProviderDecision, ProviderId, SupportLevel)
from core.provider_artifact import (ArtifactAdapterIdentity, ArtifactRenderRequest,
                                    ArtifactSource, ArtifactTarget)
from core.provider_lock import ArtifactLock, LOCK_SCHEMA_VERSION
from core.provider_config import CapabilitySupport, NativeExtension, ProviderConfigCatalog
from core.provider_registry import (AdapterCatalog, AdapterDescriptor, RegistrySeverity)
from core.provider_manifest import load_provider_manifest, provider_config_catalog


class ProviderRegistryTests(unittest.TestCase):
    def setUp(self):
        self.skills = CapabilityId("skills.repository")
        self.hooks = CapabilityId("hooks.lifecycle")
        self.codex_extension = NativeExtensionId("codex.fixture-native")
        self.catalog = ProviderConfigCatalog(
            "1.0.0", (ProviderId.CLAUDE_CODE, ProviderId.CODEX),
            (CapabilitySupport(self.skills, ProviderId.CLAUDE_CODE, SupportLevel.NATIVE),
             CapabilitySupport(self.skills, ProviderId.CODEX, SupportLevel.ADAPTED),
             CapabilitySupport(self.hooks, ProviderId.CLAUDE_CODE, SupportLevel.NATIVE)),
            (NativeExtension(self.codex_extension, ProviderId.CODEX),))

    def _descriptor(self, provider=ProviderId.CODEX, kind="skills.catalog", *,
                    requirements=None, optional=(), extensions=(), calls=None):
        identity = ArtifactAdapterIdentity(
            f"fixture.{provider.value}", "1.0.0", provider, "1.0.0",
            requirements if requirements is not None else (CapabilityRequirement(
                self.skills, (SupportLevel.NATIVE, SupportLevel.ADAPTED)),))

        def renderer(_request):
            if calls is not None:
                calls.append("rendered")
            return b"fixture bytes\n"

        return AdapterDescriptor(kind, identity, renderer, optional, extensions)

    def _effective(self, provider=ProviderId.CODEX, *, enabled=True, capabilities=(), extensions=()):
        return EffectiveProvider(provider, enabled, capabilities, extensions)

    def test_input_permutations_produce_one_canonical_catalog_order(self):
        claude = self._descriptor(ProviderId.CLAUDE_CODE)
        codex = self._descriptor(ProviderId.CODEX)
        left = AdapterCatalog((codex, claude))
        right = AdapterCatalog((claude, codex))
        self.assertEqual(left.descriptors, right.descriptors)

    def test_root_manifest_projection_gates_level_before_render(self):
        root = Path(__file__).resolve().parents[2]
        catalog = provider_config_catalog(load_provider_manifest(
            root / "configs/provider-capabilities.json"))
        descriptor = self._descriptor(requirements=(CapabilityRequirement(
            self.skills, (SupportLevel.ADAPTED,)),))
        result = AdapterCatalog((descriptor,)).select(
            provider_id=ProviderId.CODEX, artifact_kind="skills.catalog",
            capability_catalog=catalog, effective_provider=self._effective())
        self.assertEqual(result.diagnostics[0].code, "REGISTRY_CAPABILITY_LEVEL_REJECTED")

    def test_duplicate_adapter_key_fails_closed_with_structured_diagnostic(self):
        descriptor = self._descriptor()
        result = AdapterCatalog((descriptor, descriptor)).select(
            provider_id=ProviderId.CODEX, artifact_kind="skills.catalog",
            capability_catalog=self.catalog, effective_provider=self._effective())
        self.assertIsNone(result.selection)
        self.assertEqual(result.diagnostics[0].severity, RegistrySeverity.ERROR)
        self.assertEqual(result.diagnostics[0].code, "REGISTRY_DUPLICATE_ADAPTER")

    def test_unknown_provider_and_artifact_have_distinct_diagnostics(self):
        registry = AdapterCatalog((self._descriptor(),))
        unknown_provider = registry.select(
            provider_id=ProviderId.CLAUDE_CODE, artifact_kind="skills.catalog",
            capability_catalog=ProviderConfigCatalog("1.0.0", (ProviderId.CODEX,), (), ()),
            effective_provider=self._effective(ProviderId.CLAUDE_CODE))
        unknown_artifact = registry.select(
            provider_id=ProviderId.CODEX, artifact_kind="hooks.catalog",
            capability_catalog=self.catalog, effective_provider=self._effective())
        self.assertEqual(unknown_provider.diagnostics[0].code, "REGISTRY_UNKNOWN_PROVIDER")
        self.assertEqual(unknown_artifact.diagnostics[0].code, "REGISTRY_UNKNOWN_ARTIFACT_KIND")

    def test_missing_or_denied_required_capability_blocks_selection(self):
        missing = AdapterCatalog((self._descriptor(requirements=(CapabilityRequirement(
            self.hooks, (SupportLevel.NATIVE,)),)),)).select(
            provider_id=ProviderId.CODEX, artifact_kind="skills.catalog",
            capability_catalog=self.catalog, effective_provider=self._effective())
        denied = AdapterCatalog((self._descriptor(),)).select(
            provider_id=ProviderId.CODEX, artifact_kind="skills.catalog",
            capability_catalog=self.catalog, effective_provider=self._effective(
                capabilities=(ProviderDecision(self.skills, False),)))
        self.assertEqual(missing.diagnostics[0].code, "REGISTRY_CAPABILITY_MISSING")
        self.assertEqual(denied.diagnostics[0].code, "REGISTRY_CAPABILITY_DENIED")

    def test_optional_capability_does_not_block_and_is_omitted_when_unsupported(self):
        descriptor = self._descriptor(optional=(CapabilityRequirement(
            self.hooks, (SupportLevel.NATIVE,)),))
        result = AdapterCatalog((descriptor,)).select(
            provider_id=ProviderId.CODEX, artifact_kind="skills.catalog",
            capability_catalog=self.catalog, effective_provider=self._effective())
        self.assertIsNotNone(result.selection)
        self.assertEqual(result.selection.effective_capabilities,
                         descriptor.identity.capability_requirements)

    def test_native_extension_isolated_to_declaring_adapter(self):
        declaring = self._descriptor(extensions=(self.codex_extension,))
        silent = self._descriptor(kind="skills.other")
        effective = self._effective(extensions=(ProviderDecision(self.codex_extension, True),))
        selected = AdapterCatalog((declaring, silent)).select(
            provider_id=ProviderId.CODEX, artifact_kind="skills.catalog",
            capability_catalog=self.catalog, effective_provider=effective)
        other = AdapterCatalog((declaring, silent)).select(
            provider_id=ProviderId.CODEX, artifact_kind="skills.other",
            capability_catalog=self.catalog, effective_provider=effective)
        self.assertEqual(selected.selection.enabled_native_extensions, (self.codex_extension,))
        self.assertEqual(other.selection.enabled_native_extensions, ())

    def test_refusal_never_calls_renderer(self):
        calls = []
        descriptor = self._descriptor(calls=calls)
        registry = AdapterCatalog((descriptor,))
        refused = registry.select(
            provider_id=ProviderId.CODEX, artifact_kind="missing.kind",
            capability_catalog=self.catalog, effective_provider=self._effective())
        request = self._request(descriptor.identity)
        with self.assertRaisesRegex(ValueError, "refused"):
            registry.plan_render(refused, request)
        self.assertEqual(calls, [])

    def test_selected_identity_propagates_to_render_and_lock(self):
        descriptor = self._descriptor()
        registry = AdapterCatalog((descriptor,))
        selected = registry.select(
            provider_id=ProviderId.CODEX, artifact_kind="skills.catalog",
            capability_catalog=self.catalog, effective_provider=self._effective())
        rendered = registry.plan_render(selected, self._request(descriptor.identity))
        lock = ArtifactLock(LOCK_SCHEMA_VERSION, (rendered.provenance,))
        self.assertEqual(rendered.provenance.adapter_id, descriptor.identity.adapter_id)
        self.assertEqual(lock.records[0].adapter_version, descriptor.identity.adapter_version)

    def _request(self, identity):
        return ArtifactRenderRequest(
            "fixture.artifact", (ArtifactSource(
                "fixture.source", "source.md",
                "sha256:" + "a" * 64),),
            ArtifactTarget("generated/fixture.txt", ("whole-file", ())), identity, (), {},
            lambda _request: b"caller bytes")


if __name__ == "__main__":
    unittest.main()
