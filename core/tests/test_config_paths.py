"""Tests for core.config_paths shared config resolution."""
import tempfile
import unittest
from pathlib import Path

from core.config_paths import _PATHS, shared_config_path


class SharedConfigPathTests(unittest.TestCase):
    def test_command_routing_resolves_to_task(self):
        path = shared_config_path("command-routing")
        self.assertTrue(path.is_file())
        self.assertTrue(str(path).endswith("packages/task/configs/command-routing.json"))

    def test_profile_catalog_resolves_to_harness(self):
        path = shared_config_path("profile-catalog")
        self.assertTrue(path.is_file())
        self.assertTrue(
            str(path).endswith("packages/harness/configs/common/profile-catalog.json")
        )

    def test_all_names_exist(self):
        for name in _PATHS:
            with self.subTest(name=name):
                self.assertTrue(shared_config_path(name).is_file())

    def test_repo_root_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, rel in _PATHS.items():
                self.assertEqual(shared_config_path(name, repo_root=root), root / rel)

    def test_unknown_name_raises(self):
        with self.assertRaises(KeyError):
            shared_config_path("missing-config")


if __name__ == "__main__":
    unittest.main()
