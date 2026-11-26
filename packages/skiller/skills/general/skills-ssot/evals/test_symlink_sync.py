"""Behavioral checks for the optional source-owned symlink publisher.

Run: python3 skills/general/skills-ssot/evals/test_symlink_sync.py
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "snippets" / "symlink-sync.sh"


class SymlinkOwnershipTest(unittest.TestCase):
    def test_publish_preserves_foreign_assets_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for name in ("new", "foreign", "copy"):
                source = root / ".ai" / "skills" / name
                source.mkdir(parents=True)
                (source / "SKILL.md").write_text("source\n")
            target = root / ".claude" / "skills"
            target.mkdir(parents=True)
            (target / "foreign").symlink_to("../../other/foreign")
            (target / "unrelated-stale").symlink_to("../../other/removed")
            (target / "removed").symlink_to("../../.ai/skills/removed")
            (target / "copy").mkdir()
            (target / "copy" / "SKILL.md").write_text("local customization\n")
            subprocess.run(["bash", str(SCRIPT)], cwd=root, check=True,
                           capture_output=True, text=True)
            self.assertEqual((target / "new").readlink(), Path("../../.ai/skills/new"))
            self.assertEqual((target / "new" / "SKILL.md").read_text(), "source\n")
            self.assertEqual((target / "foreign").readlink(), Path("../../other/foreign"))
            self.assertTrue((target / "unrelated-stale").is_symlink())
            self.assertFalse((target / "removed").is_symlink())
            self.assertEqual((target / "copy" / "SKILL.md").read_text(), "local customization\n")
            second = subprocess.run(["bash", str(SCRIPT)], cwd=root, check=True,
                                    capture_output=True, text=True)
            self.assertEqual(second.stdout, "")
            self.assertTrue((root / ".cursor/skills/new/SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
