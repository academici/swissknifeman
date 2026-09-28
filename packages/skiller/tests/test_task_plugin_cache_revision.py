"""Regression: task plugin cache keys must track attested publication bytes."""
import json
import re
import unittest
from pathlib import Path

from skiller.release_attestation import Source, _release_unit_policy, _expected_plugin_version, check_transition, version_errors


REPO_ROOT = Path(__file__).resolve().parents[3]


class TaskPluginCacheRevisionTests(unittest.TestCase):
    def test_task_version_owner_is_umbrella_not_frozen_explicit(self):
        policy = _release_unit_policy(Source(REPO_ROOT))
        rule = policy["plugins"]["task"]
        self.assertEqual(rule["version_owner"], "umbrella")
        self.assertNotIn("expected_version", rule)

    def test_live_task_surfaces_match_umbrella_and_command_routing(self):
        source = Source(REPO_ROOT)
        changelog = source.read("CHANGELOG.md").decode()
        headings = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.M)
        self.assertTrue(headings, "CHANGELOG must contain a released umbrella version")
        umbrella = headings[0]
        routing = source.json("packages/task/configs/command-routing.json")
        self.assertEqual(routing["plugin_version"], umbrella)
        codex_manifest = source.json("packages/task/.codex-plugin/plugin.json")
        claude_manifest = source.json("packages/task/.claude-plugin/plugin.json")
        self.assertEqual(codex_manifest["version"], umbrella)
        self.assertEqual(claude_manifest["version"], umbrella)
        expected, version_source = _expected_plugin_version(
            source, _release_unit_policy(source), "task", umbrella)
        self.assertEqual(expected, umbrella)
        self.assertEqual(version_source, "umbrella")

    def test_post_release_byte_change_requires_version_bump(self):
        old = {"units": [{"id": "task", "version": "0.24.11", "tree_digest": "a",
                          "providers": {"codex": {"tree_digest": "a"}}}]}
        new = {"units": [{"id": "task", "version": "0.24.11", "tree_digest": "b",
                          "providers": {"codex": {"tree_digest": "b"}}}]}
        self.assertEqual(check_transition(old, new), ["RELEASE_IMMUTABLE_TUPLE: task@0.24.11"])
        bumped = {"units": [{"id": "task", "version": "0.24.12", "tree_digest": "b",
                             "providers": {"codex": {"tree_digest": "b"}}}]}
        self.assertEqual(check_transition(old, bumped), [])

    def test_stale_manifest_version_is_rejected_by_version_errors(self):
        value = {"units": [{
            "id": "task", "version": "0.24.4", "expected_version": "0.24.11",
            "version_source": "umbrella", "required_providers": ["claude-code", "codex"],
            "provider_versions": {"claude-code": "0.24.4", "codex": "0.24.4"},
            "providers": {"claude-code": {}, "codex": {}},
        }]}
        errors = version_errors(value)
        self.assertIn(
            "RELEASE_EXPECTED_VERSION_MISMATCH: task expected 0.24.11 from umbrella, got 0.24.4",
            errors)
        self.assertIn(
            "RELEASE_VERSION_SURFACE_MISMATCH: task codex=0.24.4, expected 0.24.11",
            errors)


if __name__ == "__main__":
    unittest.main()
