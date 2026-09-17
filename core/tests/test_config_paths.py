"""Tests for core.config_paths shared config resolution."""
import unittest
from pathlib import Path

from core.config_paths import shared_config_path


class SharedConfigPathTests(unittest.TestCase):
    def test_root_command_routing_resolves(self):
        path = shared_config_path("command-routing")
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "command-routing.json")
        self.assertEqual(path.parent.name, "configs")

    def test_root_profile_catalog_resolves(self):
        path = shared_config_path("profile-catalog")
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "profile-catalog.json")

    def test_unknown_name_raises(self):
        with self.assertRaises(KeyError):
            shared_config_path("missing-config")


if __name__ == "__main__":
    unittest.main()
