import unittest

from core.tests.test_provider_config import catalog, config, layer
from skiller.config import provider_config_layer, resolve_provider_config


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
