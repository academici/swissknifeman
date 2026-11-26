"""The skills of the analyst plugin and its plugin manifests."""
import json
import unittest
from pathlib import Path

from aicore.content.skill import describe_skill

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EXPECTED = {"session-observer"}


def _skill_dirs():
    return sorted(p.parent for p in SKILLS.glob("*/SKILL.md"))


class TestSkills(unittest.TestCase):
    def test_expected_skills_present(self):
        self.assertEqual({d.name for d in _skill_dirs()}, EXPECTED)

    def test_describe_skill(self):
        for skill_dir in _skill_dirs():
            with self.subTest(skill=skill_dir.name):
                info = describe_skill(skill_dir, skill_id=skill_dir.name)
                self.assertEqual(info.name, skill_dir.name)


class TestManifests(unittest.TestCase):
    def setUp(self):
        self.claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))

    def test_claude_manifest_declares_skills(self):
        self.assertEqual(self.claude["name"], "analyst")
        self.assertIn("./skills", self.claude["skills"])

    def test_codex_manifest_matches_claude(self):
        for key in ("name", "version", "description"):
            self.assertEqual(self.codex[key], self.claude[key], key)
        self.assertEqual(self.codex["skills"], ["./skills"])


if __name__ == "__main__":
    unittest.main()
