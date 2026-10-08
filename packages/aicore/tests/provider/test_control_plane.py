import unittest

from aicore.provider.values import (CapabilityId, ConfigSource, NativeExtensionId, ProviderId,
                                    SupportLevel)
from aicore.provider.config import (CapabilitySupport, NativeExtension, ProviderConfigCatalog,
                                    ProviderConfigLayer, resolve_provider_config)
from aicore.provider.control_plane import (canonical_desired_bytes, parse_desired_snapshot,
                                           resolve_desired_snapshot)


def catalog():
    return ProviderConfigCatalog(
        "1.0.0", (ProviderId.CLAUDE_CODE, ProviderId.CODEX),
        (CapabilitySupport(CapabilityId("instructions.project"), ProviderId.CLAUDE_CODE, SupportLevel.NATIVE),),
        (NativeExtension(NativeExtensionId("claude-code.fixture-native"), ProviderId.CLAUDE_CODE),),
    )


def layer(selection):
    return ProviderConfigLayer(
        ConfigSource("project", "project:demo", ".swissknife.json", "/providers"),
        {"contract_version": "1.0.0", "selection": selection},
    )


class TestDesiredSnapshot(unittest.TestCase):
    def test_snapshot_is_deterministic_and_immutable(self):
        config = resolve_provider_config(
            catalog=catalog(),
            project=layer({"codex": {"enabled": True}, "claude-code": {
                "capabilities": {"instructions.project": True}}}),
        )
        first = resolve_desired_snapshot(project_id="demo", config=config, catalog=catalog())
        second = resolve_desired_snapshot(project_id="demo", config=config, catalog=catalog())
        self.assertIsNotNone(first.desired)
        self.assertEqual(first.desired, second.desired)
        self.assertEqual(canonical_desired_bytes(first.desired), canonical_desired_bytes(second.desired))
        self.assertEqual(tuple(first.desired.to_dict()["selection"]), ("claude-code", "codex"))

    def test_parser_rejects_digest_and_provenance_mismatches(self):
        config = resolve_provider_config(catalog=catalog(), project=layer({"codex": {"enabled": True}}))
        snapshot = resolve_desired_snapshot(project_id="demo", config=config, catalog=catalog()).desired
        self.assertIsNotNone(snapshot)
        value = snapshot.to_dict()
        self.assertEqual(parse_desired_snapshot(value, providers=catalog().providers), snapshot)
        value["semantic_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "semantic_digest"):
            parse_desired_snapshot(value, providers=catalog().providers)

    def test_refuses_config_errors_and_provider_set_drift(self):
        invalid = resolve_provider_config(catalog=catalog(), project=layer({"unknown": {"enabled": True}}))
        result = resolve_desired_snapshot(project_id="demo", config=invalid, catalog=catalog())
        self.assertIsNone(result.desired)
        self.assertEqual(result.diagnostics[0].code, "PCP_SCHEMA_INVALID")

        config = resolve_provider_config(catalog=catalog(), project=layer({"codex": {"enabled": True}}))
        narrowed = ProviderConfigCatalog("1.0.0", (ProviderId.CLAUDE_CODE,), (), ())
        result = resolve_desired_snapshot(project_id="demo", config=config, catalog=narrowed)
        self.assertIsNone(result.desired)
        self.assertEqual(result.diagnostics[0].code, "PCP_PROVIDER_SET_MISMATCH")

    def test_no_filesystem_or_environment_access_is_needed(self):
        config = resolve_provider_config(catalog=catalog(), project=layer({"codex": {"enabled": True}}))
        result = resolve_desired_snapshot(project_id="demo", config=config, catalog=catalog())
        self.assertIsNotNone(result.desired)
