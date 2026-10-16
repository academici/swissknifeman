import json
import tempfile
import unittest
from pathlib import Path

from aicore.provider.config import (
    CapabilitySupport, NativeExtension, ProviderConfigCatalog, ProviderConfigLayer)
from aicore.provider.manifest import default_manifest_path
from aicore.provider.values import (
    CapabilityId, ConfigSource, NativeExtensionId, ProviderId, SupportLevel)
from skiller.common import Env
from skiller.config import load_config, provider_config_layer, resolve_provider_config
from skiller.config import resolve_distribution_providers


def catalog():
    return ProviderConfigCatalog("1.0.0", (ProviderId.CLAUDE_CODE, ProviderId.CODEX),
        (CapabilitySupport(CapabilityId("instructions.project"), ProviderId.CLAUDE_CODE, SupportLevel.NATIVE),
         CapabilitySupport(CapabilityId("skills.repository"), ProviderId.CODEX, SupportLevel.NATIVE),
         CapabilitySupport(CapabilityId("hooks.lifecycle"), ProviderId.CODEX, SupportLevel.UNSUPPORTED)),
        (NativeExtension(NativeExtensionId("claude-code.fixture-native"), ProviderId.CLAUDE_CODE),
         NativeExtension(NativeExtensionId("codex.fixture-native"), ProviderId.CODEX)))


def config(selection):
    return {"contract_version": "1.0.0", "selection": selection}


def layer(kind, value, path=None):
    paths = {"operation": "/", "project": "/providers", "fleet-project": "/projects/0/providers", "fleet-defaults": "/providers/defaults"}
    carriers = {"operation": "operation", "project": ".swissknife.json", "fleet-project": "config.json", "fleet-defaults": "config.json"}
    return ProviderConfigLayer(ConfigSource(kind, f"{kind}:demo", carriers[kind], path or paths[kind]), value)


class TestProviderConfigAdapter(unittest.TestCase):
    def test_distribution_uses_root_manifest_projection(self):
        result = resolve_distribution_providers(
            {"providers": config({"codex": {"enabled": True}})}, project_id="manifest",
            manifest_path=default_manifest_path())
        self.assertTrue(next(row for row in result.effective
                             if row.provider_id.value == "codex").enabled)

    def test_project_adapter_uses_shared_projection(self):
        project = {"providers": config({"codex": {"enabled": True}})}
        result = resolve_provider_config(project, catalog(), project_id="demo")
        self.assertTrue(dict((x.provider_id.value, x.enabled) for x in result.effective)["codex"])
        self.assertEqual(provider_config_layer(project, "demo").source.id, "project:demo")

    def test_same_layers_match_core(self):
        project = {"providers": config({"codex": {"enabled": True}})}
        result = resolve_provider_config(project, catalog(), project_id="demo",
                                         fleet_defaults=layer("fleet-defaults", config({"codex": {"enabled": False}})))
        self.assertEqual(result.effective[1].enabled, True)

    def test_legacy_project_file_with_every_current_key_is_byte_preserving(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "registry"
            (root / "profiles").mkdir(parents=True)
            (root / "profiles" / "laravel-project.json").write_text("{}\n", encoding="utf-8")
            env = Env(root, home=Path(tmp) / "home")
            project = Path(tmp) / "project"
            project.mkdir()
            contents = {
                "project_type": "laravel-project", "buckets": ["php"], "exclude": ["devops"],
                "presets": [], "skills_path": ".claude/skills", "agent": "claude",
                "memory_brain": {"path": "/synthetic/brain"}, "coordinator_ignore": [],
                "shape": "backend", "stacks": ["python"], "skills_map": {}, "policy_profile": "base",
            }
            path = project / ".swissknife.json"
            raw = json.dumps(contents, indent=2) + "\n"
            path.write_text(raw, encoding="utf-8")
            loaded = load_config(env, project)
            result = resolve_provider_config(loaded, catalog(), project_id="legacy")
            self.assertEqual(path.read_text(encoding="utf-8"), raw)
            self.assertEqual([item.code for item in result.diagnostics], ["PCFG_LEGACY_DEFAULT_APPLIED"])
            self.assertEqual(provider_config_layer(loaded, "legacy"), None)

    def test_synthetic_protected_carriers_remain_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "registry"
            (root / "profiles").mkdir(parents=True)
            (root / "profiles" / "fixture.json").write_text("{}\n", encoding="utf-8")
            env = Env(root, home=Path(tmp) / "home")
            project = Path(tmp) / "project"
            project.mkdir()
            project_config = project / ".swissknife.json"
            project_config.write_bytes(b'{"project_type":"fixture"}\n')
            sentinels = {
                project_config: project_config.read_bytes(),
                Path(tmp) / "protected-plan" / "sentinel.txt": b"protected plan sentinel\n",
                Path(tmp) / "external-fleet" / "config.json": b"external fleet sentinel\n",
            }
            for path, content in sentinels.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            before = {path: path.read_bytes() for path in sentinels}

            loaded = load_config(env, project)
            result = resolve_provider_config(loaded, catalog(), project_id="fixture")

            self.assertEqual([item.code for item in result.diagnostics], ["PCFG_LEGACY_DEFAULT_APPLIED"])
            self.assertEqual({path: path.read_bytes() for path in sentinels}, before)
