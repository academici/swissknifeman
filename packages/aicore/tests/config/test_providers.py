"""The ``providers`` table of the aicore config: provider selection of a project (project layer only)."""
import unittest

from aicore import config
from aicore.provider.config import routing_available
from aicore.config.units import foundation_root

from .support import Workspace

AICORE_SCHEMA = foundation_root() / "configs" / "config.schema.json"


class TestProvidersTable(Workspace):
    def setUp(self):
        super().setUp()
        self.schema = config.load_module_schema(AICORE_SCHEMA, "aicore")

    def resolve(self, **kwargs):
        return config.resolve("aicore", schema=self.schema, project=self.project, env=self.env, **kwargs)

    def test_defaults_and_empty_selection(self):
        resolved = self.resolve()
        self.assertEqual(resolved.get("providers.contract_version"), "1.0.0")
        self.assertEqual(resolved.get("providers.selection"), {})

    def test_selection_is_read_from_the_project_layer(self):
        self.write(self.project_file, "schema_version = 1\n[aicore.providers.selection.codex]\nenabled = true\n"
                                      "[aicore.providers.selection.claude-code]\nenabled = false\n")
        providers = self.resolve().get("providers")
        self.assertEqual(providers, {"contract_version": "1.0.0", "available": {}, "selection": {
            "codex": {"enabled": True}, "claude-code": {"enabled": False}}})

    def test_selection_is_refused_in_the_machine_layer(self):
        self.write(self.machine_file, "schema_version = 1\n[aicore.providers.selection.codex]\nenabled = true\n")
        with self.assertRaises(config.ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_LAYER_FORBIDDEN")

    def test_invalid_provider_id_and_value_are_refused(self):
        self.write(self.project_file, "schema_version = 1\n[aicore.providers.selection.Codex]\nenabled = true\n")
        with self.assertRaises(config.ConfigError):
            self.resolve()
        self.write(self.project_file, "schema_version = 1\n[aicore.providers.selection.codex]\nenabled = \"yes\"\n")
        with self.assertRaises(config.ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_TYPE")

    def test_edit_layer_file_sets_a_provider(self):
        result = config.edit_layer_file(self.project_file, "aicore", "providers.selection.codex.enabled", True,
                                        schema=self.schema, layer="project", project=self.project, env=self.env)
        self.assertTrue(result.changed)
        self.assertTrue(self.resolve().get("providers.selection.codex.enabled"))
        self.assertIn("[aicore.providers.selection.codex]", self.project_file.read_text(encoding="utf-8"))

    def test_available_defaults_to_enabled_without_an_entry(self):
        self.assertEqual(routing_available("codex", resolved=self.resolve()), (True, "defaults"))

    def test_machine_disables_a_provider_and_explain_shows_the_layer(self):
        self.write(self.machine_file, "schema_version = 1\n[aicore.providers.available.codex]\nenabled = false\n")
        resolved = self.resolve()
        self.assertEqual(routing_available("codex", resolved=resolved), (False, "machine"))
        self.assertEqual(routing_available("claude-code", resolved=resolved), (True, "defaults"))
        entry = resolved.explain("providers.available.codex.enabled")[0]
        self.assertEqual((entry.value, entry.layer), (False, "machine"))

    def test_invocation_and_flags_override_the_machine(self):
        self.write(self.machine_file, "schema_version = 1\n[aicore.providers.available.codex]\nenabled = false\n")
        invocation = self.write(self.root / "invocation.toml",
                                "schema_version = 1\n[aicore.providers.available.codex]\nenabled = true\n")
        self.assertEqual(routing_available("codex", resolved=self.resolve(config_file=invocation)), (True, "invocation"))
        flagged = self.resolve(flags={"providers.available.codex.enabled": "false"}, config_file=invocation)
        self.assertEqual(routing_available("codex", resolved=flagged), (False, "flags"))

    def test_available_is_refused_in_the_project_layer(self):
        self.write(self.project_file, "schema_version = 1\n[aicore.providers.available.codex]\nenabled = false\n")
        with self.assertRaises(config.ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_LAYER_FORBIDDEN")

    def test_available_does_not_change_selection(self):
        self.write(self.machine_file, "schema_version = 1\n[aicore.providers.available.codex]\nenabled = false\n")
        self.write(self.project_file, "schema_version = 1\n[aicore.providers.selection.codex]\nenabled = true\n")
        providers = self.resolve().get("providers")
        self.assertEqual(providers["selection"], {"codex": {"enabled": True}})
        self.assertEqual(providers["available"], {"codex": {"enabled": False}})

    def test_example_documents_the_table(self):
        text = (foundation_root() / "config.example.toml").read_text(encoding="utf-8")
        self.assertIn("[aicore.providers]", text)
        self.assertIn("[aicore.providers.selection]", text)
        self.assertIn("[aicore.providers.available]", text)


if __name__ == "__main__":
    unittest.main()
