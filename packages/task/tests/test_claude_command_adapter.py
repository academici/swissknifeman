"""Focused byte-compatibility tests for the named Claude command projection."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from task.command_catalog import build_command_catalog
from task.command_render import (apply_claude_command_plan, mapping_from_catalog,
                                 plan_claude_command_render,
                                 render_claude_invocation)


REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_ROOT = REPO_ROOT / "packages/task/commands"
ROUTING_PATH = REPO_ROOT / "packages/task/configs/command-routing.json"
PLUGIN_PATH = REPO_ROOT / "packages/task/.claude-plugin/plugin.json"
GOLDEN_ROOT = REPO_ROOT / "packages/task/tests/fixtures_data/claude-command-golden"


class ClaudeCommandAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build_command_catalog(COMMAND_ROOT, ROUTING_PATH)
        cls.mapping = mapping_from_catalog(cls.catalog, "claude-code")
        cls.support = dict(cls.mapping.capability_bindings)
        cls.plugin_bytes = PLUGIN_PATH.read_bytes()

    def render(self, **kwargs):
        values = {"plugin_bytes": self.plugin_bytes}
        values.update(kwargs)
        return plan_claude_command_render(
            self.catalog, self.mapping, self.support, **values)

    def test_independent_golden_equals_the_committed_claude_surface(self):
        expected_names = {
            record.command_id.removeprefix("task:") + ".md"
            for record in self.catalog.records
        }
        golden_names = {path.name for path in (GOLDEN_ROOT / "commands").glob("*.md")}
        self.assertEqual(golden_names, expected_names)
        for record in self.catalog.records:
            name = record.command_id.removeprefix("task:") + ".md"
            self.assertEqual((GOLDEN_ROOT / "commands" / name).read_bytes(),
                             (COMMAND_ROOT / name).read_bytes())
        self.assertEqual((GOLDEN_ROOT / "plugin.json").read_bytes(), self.plugin_bytes)

    def test_invocations_and_projection_bytes_are_exact(self):
        for record in self.catalog.records:
            self.assertEqual(
                render_claude_invocation(record, "payload", self.mapping),
                f"/{record.command_id} payload")
        plan = self.render()
        self.assertTrue(plan.ok, plan.diagnostics)
        expected = {
            "packages/task/.claude-plugin/plugin.json": GOLDEN_ROOT / "plugin.json",
            **{
                record.source.path: GOLDEN_ROOT / "commands" /
                (record.command_id.removeprefix("task:") + ".md")
                for record in self.catalog.records
            },
        }
        self.assertEqual({artifact.path for artifact in plan.artifacts}, set(expected))
        for artifact in plan.artifacts:
            self.assertEqual(artifact.managed_bytes, expected[artifact.path].read_bytes())

    def test_two_runs_are_identical_and_canonical_check_is_empty(self):
        first, second = self.render(), self.render()
        self.assertEqual(first.artifacts, second.artifacts)
        self.assertEqual(first.diagnostics, second.diagnostics)
        self.assertEqual(apply_claude_command_plan(REPO_ROOT, first, check=True), ())

    def test_write_uses_the_same_plan_and_stays_inside_temporary_root(self):
        plan = self.render()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected_paths = tuple(artifact.path for artifact in plan.artifacts)
            self.assertEqual(apply_claude_command_plan(root, plan, check=True), expected_paths)
            self.assertEqual(tuple(root.rglob("*")), ())
            self.assertEqual(apply_claude_command_plan(root, plan, check=False), expected_paths)
            written = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*") if path.is_file()
            }
            self.assertEqual(set(written), set(expected_paths))
            self.assertEqual(written,
                             {artifact.path: artifact.managed_bytes
                              for artifact in plan.artifacts})
            self.assertEqual(apply_claude_command_plan(root, plan, check=True), ())

    def test_mapping_capability_frontmatter_and_plugin_drift_fail_before_write(self):
        cases = []
        classes = dict(self.mapping.class_selectors)
        classes["frontier"] = ()
        cases.append(plan_claude_command_render(
            self.catalog, replace(self.mapping, class_selectors=tuple(classes.items())),
            self.support, plugin_bytes=self.plugin_bytes))

        support = dict(self.support)
        support.pop("skills.repository")
        cases.append(plan_claude_command_render(
            self.catalog, self.mapping, support, plugin_bytes=self.plugin_bytes))

        plugin = json.loads(self.plugin_bytes)
        plugin["commands"] = ["./other"]
        cases.append(plan_claude_command_render(
            self.catalog, self.mapping, self.support,
            plugin_bytes=(json.dumps(plugin) + "\n").encode()))

        with tempfile.TemporaryDirectory() as temporary:
            command_root = Path(temporary) / "commands"
            shutil.copytree(COMMAND_ROOT, command_root)
            path = command_root / "fix.md"
            path.write_bytes(path.read_bytes().replace(b"model: sonnet", b"model: opus", 1))
            drift_catalog = build_command_catalog(command_root, ROUTING_PATH)
            cases.append(plan_claude_command_render(
                drift_catalog, mapping_from_catalog(drift_catalog, "claude-code"),
                self.support, plugin_bytes=self.plugin_bytes))

        expected_codes = {
            "CMD_MAPPING_MISSING", "CMD_CAPABILITY_UNSUPPORTED", "CMD_SOURCE_DRIFT"
        }
        for plan in cases:
            self.assertFalse(plan.ok)
            self.assertEqual(plan.artifacts, ())
            self.assertTrue({item.code for item in plan.diagnostics} & expected_codes)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
