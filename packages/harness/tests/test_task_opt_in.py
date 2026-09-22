"""Task routing must not become resident through provider rule projections."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from harness.cursor_render import assert_rule_frontmatter, plan_cursor_rules
from harness.instructions import default_request, plan_instructions
import tempfile


class TaskOptInTests(unittest.TestCase):
    def test_compact_roots_retain_claude_package_guidance(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = plan_instructions(default_request("plan", Path(temporary)))
        self.assertIsNotNone(result.artifact_plan, result.diagnostics)
        for target in result.targets:
            if target.scope_id == "root":
                self.assertNotIn("root.plan-lifecycle", target.ordered_semantic_ids)
                self.assertNotIn("root.ecosystem-identity", target.ordered_semantic_ids)
        package = next(target for target in result.targets
                       if target.scope_id == "task" and target.provider_id == "claude-code")
        self.assertIn("task.engineering-invariants", package.ordered_semantic_ids)

    def test_cursor_task_routing_is_manual_without_automatic_triggers(self):
        path = ".cursor/rules/swissknifeman-router.mdc"
        content = plan_cursor_rules()[path]
        metadata = content.decode().split("---", 2)[1]
        self.assertIn("alwaysApply: false", metadata)
        self.assertNotIn("description:", metadata)
        self.assertNotIn("globs:", metadata)
        assert_rule_frontmatter(path, content)
        with self.assertRaisesRegex(ValueError, "router-trigger"):
            assert_rule_frontmatter(path, content.replace(b"alwaysApply: false", b"alwaysApply: true"))


if __name__ == "__main__":
    unittest.main()
