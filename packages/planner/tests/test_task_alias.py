"""Compatibility alias: remove in the next minor release.

The `task` compatibility plugin, the `task:<id>` command spelling and the legacy bridge environment."""
import contextlib
import io
import json
from pathlib import Path
import re
import unittest

import fixtures  # noqa: F401,E402 — restores the lib and aicore fallbacks
from planner import review_selection
from planner.command_catalog import build_command_catalog
from planner.command_render import parse_next_carrier, plan_claude_alias_render
from planner.commands_compat import normalize_command_id
from planner.plan import bridges


REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_ROOT = REPO_ROOT / "packages/planner/commands"
ROUTING_PATH = REPO_ROOT / "packages/planner/configs/command-routing.json"
PLUGIN_PATH = REPO_ROOT / "packages/planner/.claude-plugin/plugin.json"
ALIAS_ROOT = REPO_ROOT / "packages/planner/aliases/task"
ALIAS_GOLDEN = REPO_ROOT / "packages/planner/tests/fixtures_data/claude-command-golden/aliases/task"


def stderr_of(function, *args):
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        result = function(*args)
    return result, buffer.getvalue()


@fixtures.hub_only
class AliasPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build_command_catalog(COMMAND_ROOT, ROUTING_PATH)
        cls.plan = plan_claude_alias_render(cls.catalog, plugin_bytes=PLUGIN_PATH.read_bytes())

    def test_no_alias_command_links_outside_its_own_folder(self):
        for artifact in self.plan.artifacts:
            self.assertNotIn("](../", artifact.managed_bytes.decode("utf-8"), artifact.path)

    def test_ten_commands_and_the_plugin_are_generated(self):
        self.assertTrue(self.plan.ok)
        paths = {artifact.path for artifact in self.plan.artifacts}
        commands = {record.command_id.removeprefix("planner:") for record in self.catalog.records}
        self.assertEqual(len(commands), 10)
        self.assertEqual(paths, {"packages/planner/aliases/task/.claude-plugin/plugin.json",
                                 *(f"packages/planner/aliases/task/commands/{name}.md" for name in commands)})

    def test_committed_alias_and_golden_equal_the_render(self):
        for artifact in self.plan.artifacts:
            relative = artifact.path.removeprefix("packages/planner/aliases/task/")
            self.assertEqual((ALIAS_ROOT / relative).read_bytes(), artifact.managed_bytes, relative)
            self.assertEqual((ALIAS_GOLDEN / relative).read_bytes(), artifact.managed_bytes, relative)

    def test_plugin_is_commands_only_and_named_task(self):
        plugin = json.loads((ALIAS_ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        planner = json.loads(PLUGIN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(plugin["name"], "task")
        self.assertEqual(plugin["version"], planner["version"])
        self.assertEqual(plugin["commands"], ["./commands"])
        self.assertNotIn("skills", plugin)
        self.assertEqual(plugin["author"], planner["author"])

    def test_command_is_the_planner_command_plus_notice_and_description_prefix(self):
        for record in self.catalog.records:
            name = record.command_id.removeprefix("planner:")
            alias = (ALIAS_ROOT / "commands" / f"{name}.md").read_text(encoding="utf-8").split("\n")
            origin = (COMMAND_ROOT / f"{name}.md").read_text(encoding="utf-8").split("\n")
            close = origin.index("---", 1)
            self.assertEqual(alias[close], "---")
            for old, new in zip(origin[1:close], alias[1:close]):
                if old.startswith("description:"):
                    self.assertTrue(new.startswith(f'description: "Deprecated alias of /planner:{name}. '))
                else:
                    self.assertEqual(new, old)
            notice = alias[close + 1]
            self.assertTrue(notice.startswith(f"> `/task:{name}` is deprecated"), notice)
            self.assertIn(f"use `/planner:{name}`", notice)
            self.assertEqual(alias[close + 2], "")
            # a relative link into the package names the file of the planner plugin (the alias folder has no
            # references/, and no command names a package root)
            expected = [re.sub(r"\[([^\]]+)\]\(\.\./([^)]+)\)", r"\1 (`\2` of the enabled planner plugin)", line)
                        for line in origin[close + 1:]]
            self.assertEqual(alias[close + 3:], expected)
            self.assertNotIn("Skill(", "\n".join(alias))


class NormalizeCommandIdTests(unittest.TestCase):
    def test_legacy_spellings_map_to_planner(self):
        self.assertEqual(normalize_command_id("task:plan-run"), ("planner:plan-run", True))
        self.assertEqual(normalize_command_id("/task:review"), ("/planner:review", True))

    def test_other_text_is_unchanged(self):
        for text in ("planner:plan-run", "/planner:dev", "tasks:x", "task", "plan-run", ""):
            self.assertEqual(normalize_command_id(text), (text, False))

    def test_next_declaration_accepts_the_old_id_with_a_warning(self):
        old, warning = stderr_of(parse_next_carrier, "run-items: task:plan-run PLAN P4.5")
        new, silent = stderr_of(parse_next_carrier, "run-items: planner:plan-run PLAN P4.5")
        self.assertEqual(old, new)
        self.assertEqual(old.command_id, "planner:plan-run")
        self.assertIn("TASK_COMMAND_DEPRECATED: task:plan-run is deprecated; use planner:plan-run", warning)
        self.assertEqual(silent, "")

    def test_review_selection_accepts_the_old_id_with_a_warning(self):
        old, warning = stderr_of(review_selection.invocation_selection,
                                 "/task:plan-run PLAN P1.1 --reviewer codex/gpt-6")
        new, silent = stderr_of(review_selection.invocation_selection,
                                "/planner:plan-run PLAN P1.1 --reviewer codex/gpt-6")
        self.assertEqual(old, new)
        self.assertEqual(old, {"provider": "codex", "model": "gpt-6", "effort": "high"})
        self.assertIn("TASK_COMMAND_DEPRECATED", warning)
        self.assertEqual(silent, "")


class BridgeEnvironmentTests(unittest.TestCase):
    def test_dispatcher_no_longer_exports_the_legacy_names(self):
        env = bridges.environment()
        self.assertNotIn("TASK_ROOT", env)
        self.assertNotIn("TASK_PLAN_PY", env)
        self.assertIn("PLANNER_ROOT", env)


if __name__ == "__main__":
    unittest.main()
