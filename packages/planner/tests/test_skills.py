"""The skills of the planner plugin and the plugin manifests that declare them."""
import json
import unittest
from pathlib import Path

try:
    from aicore.content.skill import describe_skill
except ImportError:  # aicore is not on the path
    describe_skill = None

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


class TestSkills(unittest.TestCase):
    @unittest.skipIf(describe_skill is None, "aicore is not available")
    def test_describe_skill(self):
        dirs = sorted(path for path in SKILLS.iterdir() if (path / "SKILL.md").is_file())
        self.assertIn("workflow-craft", [path.name for path in dirs])
        for path in dirs:
            with self.subTest(skill=path.name):
                info = describe_skill(path, skill_id=path.name)
                self.assertEqual(info.name, path.name)

    def test_manifests_declare_skills(self):
        claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertIn("./skills", claude["skills"])
        self.assertIn("./skills", codex["skills"])


if __name__ == "__main__":
    unittest.main()
