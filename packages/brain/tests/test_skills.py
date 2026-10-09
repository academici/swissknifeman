"""The skill brain-locator and the plugin manifest of the brain module."""
import json
import re
import unittest
from pathlib import Path

from aicore.content.skill import describe_skill

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "brain-locator"


class TestSkill(unittest.TestCase):
    def test_describe_skill(self):
        info = describe_skill(SKILL, skill_id="brain-locator")
        self.assertEqual(info.name, SKILL.name)

    def test_ladder_starts_with_brain_vault(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        ladder = text[text.index("```bash"):]
        self.assertTrue(ladder.split("\n", 1)[1].startswith("# A."))
        self.assertLess(ladder.index("brain vault --json"), ladder.index("$MAIND_BRAIN_VAULT"))

    def test_plugin_manifest(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        unit = json.loads((ROOT / "unit.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["name"], "brain")
        self.assertEqual(plugin["version"], unit["version"])
        self.assertEqual(unit["provides"]["plugins"], [{"name": "brain", "manifest": ".claude-plugin/plugin.json"}])
        self.assertTrue((ROOT / plugin["skills"][0]).is_dir())


if __name__ == "__main__":
    unittest.main()
