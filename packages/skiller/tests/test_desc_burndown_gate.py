"""P3.2: validate.sh description-gate — error>450/warn>300 +
burn-down-ratchet (scripts/desc-burndown.txt).

scripts/validate.sh — bash-wrap around python-heredoc'a (see test_validate_upstream_body_path.py
for justification: not lib/skiller-module, honestly tested only by real launch).
REPO_ROOT resolves from the script location → copy validate.sh + desc-burndown.txt next to
MINIMUM synthetic skills/. Checking for non-general exit-code (it is expectedly non-zero due to
missing registry environment - buckets.json/skills.json etc.), and SPECIFIC lines about
description-gate in stdout."""
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = PKG_ROOT / "scripts" / "validate.sh"

# Trigger prefix phrase (P3.5 description-trigger gate) — keeps these fixtures out
# scope new gate so that length remains the only axis checked here
# (see test_desc_trigger_gate.py — trigger gate is tested separately).
_TRIGGER_PREFIX = "Use when testing: "
# 451 character - the only character above DESC_ERROR_MAX.
DESC_451 = _TRIGGER_PREFIX + "x" * (451 - len(_TRIGGER_PREFIX))
# 320 char - between DESC_WARN_MAX(300) and DESC_ERROR_MAX(450).
DESC_320 = _TRIGGER_PREFIX + "y" * (320 - len(_TRIGGER_PREFIX))
# 250 symbol - legal norm (<= DESC_WARN_MAX).
DESC_250 = _TRIGGER_PREFIX + "z" * (250 - len(_TRIGGER_PREFIX))


class DescBurndownGateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "registry"
        self.skills_dir = self.root / "skills" / "testbucket"
        self.skills_dir.mkdir(parents=True)
        self.scripts_dir = self.root / "scripts"
        self.scripts_dir.mkdir()
        import shutil
        shutil.copy2(VALIDATE_SCRIPT, self.scripts_dir / "validate.sh")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_skill(self, name, description):
        d = self.skills_dir / name
        d.mkdir()
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\nbucket: testbucket\nversion: 1.0.0\n"
            f"description: {description}\n---\n\nBody.\n",
            encoding="utf-8")

    def _write_burndown(self, lines):
        (self.scripts_dir / "desc-burndown.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    def _run(self):
        return subprocess.run(
            ["bash", str(self.scripts_dir / "validate.sh")],
            capture_output=True, text=True, timeout=60)

    def test_over_450_is_hard_error_even_in_burndown(self):
        self._write_skill("over-450", DESC_451)
        self._write_burndown(["testbucket/over-450"])
        result = self._run()
        self.assertIn("hard-ceiling", result.stdout)
        self.assertNotEqual(result.returncode, 0)

    def test_between_300_and_450_in_burndown_is_warn_only(self):
        self._write_skill("legal-debt", DESC_320)
        self._write_burndown(["testbucket/legal-debt"])
        result = self._run()
        self.assertIn("WARN: skills/testbucket/legal-debt/SKILL.md", result.stdout)
        self.assertIn("inherited debt", result.stdout)
        self.assertNotIn("ERROR: skills/testbucket/legal-debt/SKILL.md", result.stdout)

    def test_between_300_and_450_not_in_burndown_is_error(self):
        self._write_skill("new-debt", DESC_320)
        self._write_burndown(["# empty — new debt is not legalized"])
        result = self._run()
        self.assertIn("ERROR: skills/testbucket/new-debt/SKILL.md", result.stdout)
        self.assertIn("new debt prohibited", result.stdout)

    def test_stale_entry_skill_missing_warns(self):
        self._write_skill("still-here", DESC_250)
        self._write_burndown(["testbucket/ghost-skill"])
        result = self._run()
        self.assertIn(
            "scripts/desc-burndown.txt: 'testbucket/ghost-skill' — rotten recording",
            result.stdout)

    def test_stale_entry_already_short_warns(self):
        self._write_skill("already-short", DESC_250)
        self._write_burndown(["testbucket/already-short"])
        result = self._run()
        self.assertIn(
            "scripts/desc-burndown.txt: 'testbucket/already-short' — rotten recording",
            result.stdout)

    def test_at_or_under_300_no_desc_warning(self):
        self._write_skill("clean", DESC_250)
        self._write_burndown(["# empty"])
        result = self._run()
        self.assertNotIn("skills/testbucket/clean/SKILL.md: description", result.stdout)


if __name__ == "__main__":
    unittest.main()
