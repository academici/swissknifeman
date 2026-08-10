from __future__ import annotations

import unittest

from artifex import cli


class ProviderIntegrationTests(unittest.TestCase):
    def test_dispatch_provider_selection_is_explicit_and_bounded(self):
        parser = cli.build_parser()
        prefix = ["--repo-root", ".", "--plan-dir", "plan", "--runs-root", "runs", "dispatch", "--run-id", "r", "--admission", "a"]
        omitted = parser.parse_args(prefix)
        self.assertIsNone(omitted.provider)
        selected = parser.parse_args([*prefix, "--provider", "claude-code"])
        self.assertEqual("claude-code", selected.provider)


if __name__ == "__main__":
    unittest.main()
