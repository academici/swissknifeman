#!/usr/bin/env python3
"""The slash invocation template harness keeps for `run` workers equals the one the planner routing file declares.

harness may not read the planner routing file (module boundary), so it holds the template per invocation style;
this hub-level test is the only place that sees both and keeps them from drifting apart."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in ("packages/aicore/lib", "packages/harness/lib"):
    sys.path.insert(0, os.path.join(ROOT, path))

from harness.run import worker  # noqa: E402


class InvocationTemplateParity(unittest.TestCase):
    def test_slash_template_matches_the_planner_routing_file(self):
        with open(os.path.join(ROOT, "packages/planner/configs/command-routing.json"), encoding="utf-8") as handle:
            routing = json.load(handle)
        found = []

        def walk(node):
            if isinstance(node, dict):
                binding = node.get("invocation_binding")
                if isinstance(binding, dict) and "template" in binding:
                    found.append(binding["template"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(routing["mappings"]["claude-code"] if "mappings" in routing else routing)
        self.assertIn(worker._INVOCATION_TEMPLATES["slash"], found)

    def test_worker_resolves_the_claude_code_style(self):
        template, problem = worker._command_template()
        self.assertIsNone(problem)
        self.assertEqual(template, worker._INVOCATION_TEMPLATES["slash"])


if __name__ == "__main__":
    unittest.main()
