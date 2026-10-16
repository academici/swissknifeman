"""The Codex migrated-command skill: rendered only for its exact path and a well-formed source command."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from aicore.provider.runtime import codex_migrated_command_skill

PATH = ".codex-plugin/migrated-command-skills/source-command-plan/SKILL.md"


class MigratedCommandSkillTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.source = Path(tmp.name)
        (self.source / "commands").mkdir()

    def command(self, text: str) -> None:
        (self.source / "commands" / "plan.md").write_text(text, encoding="utf-8")

    def test_a_well_formed_command_is_rendered(self):
        self.command("---\ndescription: Make a plan\n---\n\nDo $ARGUMENTS.\n")
        rendered = codex_migrated_command_skill(self.source, PATH).decode("utf-8")
        self.assertTrue(rendered.startswith('---\nname: "source-command-plan"\ndescription: Make a plan\n---\n'))
        self.assertIn("command `plan`", rendered)
        self.assertTrue(rendered.endswith("## Command Template\n\nDo $ARGUMENTS.\n"))

    def test_other_paths_are_not_owned(self):
        self.command("---\ndescription: Make a plan\n---\nbody\n")
        for path in (".codex-plugin/other/source-command-plan/SKILL.md",
                     ".codex-plugin/migrated-command-skills/plan/SKILL.md",
                     ".codex-plugin/migrated-command-skills/source-command-plan/README.md",
                     "migrated-command-skills/source-command-plan/SKILL.md"):
            self.assertIsNone(codex_migrated_command_skill(self.source, path), path)

    def test_a_missing_or_malformed_command_gives_nothing(self):
        self.assertIsNone(codex_migrated_command_skill(self.source, PATH))  # no commands/plan.md
        for text in ("", "no front matter\n", "---\ndescription: open\n", "---\nname: plan\n---\nbody\n",
                     "---\ndescription:\n---\nbody\n"):
            self.command(text)
            self.assertIsNone(codex_migrated_command_skill(self.source, PATH), repr(text))


if __name__ == "__main__":
    unittest.main()
