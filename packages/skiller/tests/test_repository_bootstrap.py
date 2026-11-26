"""Host bootstrap relocation and fail-closed carrier validation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from skiller.host import Host
from skiller.publication import render_repository_bootstrap_projections
from skiller.registry import check_drift
from tests.test_codex_publication import _build_isolated_bootstrap_fixture


class BootstrapConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo, self.package = _build_isolated_bootstrap_fixture(Path(temporary.name))
        self.path = self.repo / "configs/repository-bootstrap-skills.json"
        self.config = json.loads(self.path.read_text())
        self.host = Host(root=self.repo, bootstrap="configs/repository-bootstrap-skills.json")

    def write(self):
        self.path.write_text(json.dumps(self.config))

    def render(self):
        return render_repository_bootstrap_projections(
            repo_root=self.repo, package_root=self.package, host=self.host)

    def test_all_carrier_paths_reject_absolute_traversal_and_symlink_escape(self):
        outside = self.repo.parent / (self.repo.name + "-missing")
        (self.repo / "escape").symlink_to(outside)
        for bad in ("/tmp/canon", "../canon", "escape/canon", "", "a\\b"):
            for carrier in ("canonical", "class_b", "lock_path"):
                with self.subTest(path=bad, carrier=carrier):
                    config = json.loads(self.path.read_text())
                    try:
                        if carrier == "canonical":
                            config["identities"][0]["canonical"] = bad
                        elif carrier == "class_b":
                            config["class_b"][0]["canonical"] = bad
                        else:
                            config[carrier] = bad
                        self.path.write_text(json.dumps(config))
                        with self.assertRaises(ValueError):
                            self.render()
                    finally:
                        self.write()

    def test_names_duplicates_and_missing_versions_fail_closed(self):
        cases = [
            ("unit_version", ""), ("schema_version", True),
            ("identities", [self.config["identities"][0]] * 2),
            ("identities", [{"identity": "../alpha", "canonical": "bootstrap/skills/alpha/SKILL.md"}]),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                config = dict(self.config, **{key: value})
                self.path.write_text(json.dumps(config))
                with self.assertRaises(ValueError):
                    self.render()
        self.write()
        self.config["class_b"][0]["identity"] = "../beta"
        self.write()
        with self.assertRaises(ValueError):
            self.render()

    def test_missing_or_mismatched_canon_fails_before_writing(self):
        canon = self.repo / self.config["identities"][0]["canonical"]
        canon.write_text("---\nname: wrong\ndescription: Test\n---\n")
        with self.assertRaisesRegex(ValueError, "frontmatter name"):
            self.render()
        self.config["identities"][0]["canonical"] = "missing/SKILL.md"
        self.write()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.render()
        self.assertFalse((self.repo / ".agents").exists())

    def test_registry_selects_host_bootstrap_and_preserves_standalone(self):
        from tests.fixtures import make_registry
        # Synthetic package catalog, with the host-owned carriers outside that package.
        root, env = make_registry(self.repo / "registry-fixture")
        with mock.patch("skiller.registry.load_host", return_value=self.host):
            from skiller.registry import _has_repository_bootstrap_config
            self.assertTrue(_has_repository_bootstrap_config(root))
        with mock.patch("skiller.registry.load_host", return_value=Host.empty()):
            self.assertFalse(_has_repository_bootstrap_config(root))
            # No host bootstrap: normal standalone drift checking needs no canon.
            drift = check_drift(env)
        self.assertTrue(drift)
        self.assertFalse(any("bootstrap" in path for path in drift))


if __name__ == "__main__":
    unittest.main()
