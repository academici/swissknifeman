import json
import tempfile
import unittest
from pathlib import Path

from core.tests.test_provider_config import catalog, config, layer
from skiller.common import Env
from skiller.config import load_config, provider_config_layer, resolve_provider_config


class TestProviderConfigAdapter(unittest.TestCase):
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
