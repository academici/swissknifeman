"""P3.5 (2026.07.29-HARNESS-AGNOSTIC): validate.sh description-триггер-гейт — description
обязано отвечать «когда звать» + burn-down-рэтчет (scripts/desc-trigger-burndown.txt).

Зеркалит test_desc_burndown_gate.py (та же обёртка, тот же приём: реальный запуск
validate.sh против синтетического skills/, проверяем КОНКРЕТНЫЕ строки в stdout, не
общий exit-код — он ожидаемо ненулевой из-за недостающего окружения реестра)."""
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = PKG_ROOT / "scripts" / "validate.sh"

# Короткое описание без триггерной фразы — держим длину <= 300, чтобы не задевать
# независимый гейт длины (DESC_WARN_MAX/DESC_ERROR_MAX, test_desc_burndown_gate.py).
DESC_NO_TRIGGER = "A short description without the phrase this gate looks for at all"
DESC_WITH_TRIGGER = "Use when testing this gate: a short trigger-bearing description"


class DescTriggerGateCase(unittest.TestCase):
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

    def _write_skill(self, name, description, upstream=False):
        d = self.skills_dir / name
        d.mkdir()
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\nbucket: testbucket\nversion: 1.0.0\n"
            f"description: {description}\n---\n\nBody.\n",
            encoding="utf-8")
        if upstream:
            (d / "upstream.json").write_text(
                '{"schema_version": 1, "source": "github", "strategy": "notify"}\n',
                encoding="utf-8")

    def _write_trigger_burndown(self, lines):
        (self.scripts_dir / "desc-trigger-burndown.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    def _run(self):
        return subprocess.run(
            ["bash", str(self.scripts_dir / "validate.sh")],
            capture_output=True, text=True, timeout=60)

    def test_no_trigger_not_in_burndown_is_error(self):
        self._write_skill("no-trigger", DESC_NO_TRIGGER)
        self._write_trigger_burndown(["# empty — новый долг не легализован"])
        result = self._run()
        self.assertIn("ERROR: skills/testbucket/no-trigger/SKILL.md", result.stdout)
        self.assertIn("без триггерной фразы", result.stdout)
        self.assertIn("новый долг запрещён", result.stdout)

    def test_no_trigger_in_burndown_is_warn_only(self):
        self._write_skill("legal-debt", DESC_NO_TRIGGER)
        self._write_trigger_burndown(["testbucket/legal-debt"])
        result = self._run()
        self.assertIn("WARN: skills/testbucket/legal-debt/SKILL.md", result.stdout)
        self.assertIn("унаследованный долг", result.stdout)
        self.assertNotIn("ERROR: skills/testbucket/legal-debt/SKILL.md", result.stdout)

    def test_has_trigger_no_gate_line(self):
        self._write_skill("clean", DESC_WITH_TRIGGER)
        self._write_trigger_burndown(["# empty"])
        result = self._run()
        self.assertNotIn("skills/testbucket/clean/SKILL.md: description без триггерной",
                         result.stdout)

    def test_upstream_skill_exempt(self):
        self._write_skill("upstream-skill", DESC_NO_TRIGGER, upstream=True)
        self._write_trigger_burndown(["# empty"])
        result = self._run()
        self.assertNotIn(
            "skills/testbucket/upstream-skill/SKILL.md: description без триггерной",
            result.stdout)

    def test_stale_entry_skill_missing_warns(self):
        self._write_skill("still-here", DESC_WITH_TRIGGER)
        self._write_trigger_burndown(["testbucket/ghost-skill"])
        result = self._run()
        self.assertIn(
            "scripts/desc-trigger-burndown.txt: 'testbucket/ghost-skill' — протухшая запись",
            result.stdout)

    def test_stale_entry_already_has_trigger_warns(self):
        self._write_skill("already-fixed", DESC_WITH_TRIGGER)
        self._write_trigger_burndown(["testbucket/already-fixed"])
        result = self._run()
        self.assertIn(
            "scripts/desc-trigger-burndown.txt: 'testbucket/already-fixed' — протухшая запись",
            result.stdout)


if __name__ == "__main__":
    unittest.main()
