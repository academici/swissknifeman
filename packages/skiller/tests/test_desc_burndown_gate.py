"""P3.2: validate.sh description-гейт — error>450/warn>300 +
burn-down-рэтчет (scripts/desc-burndown.txt).

scripts/validate.sh — bash-обёртка вокруг python-heredoc'а (см. test_validate_upstream_body_path.py
для обоснования: не lib/skiller-модуль, честно тестируется только реальным запуском).
REPO_ROOT резолвится от расположения скрипта → копируем validate.sh + desc-burndown.txt рядом с
МИНИМАЛЬНЫМ синтетическим skills/. Проверяем не общий exit-код (он ожидаемо ненулевой из-за
недостающего окружения реестра — buckets.json/skills.json и т.п.), а КОНКРЕТНЫЕ строки про
description-гейт в stdout."""
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = PKG_ROOT / "scripts" / "validate.sh"

# Триггерная фраза-префикс (P3.5 description-триггер-гейт) — держит эти фикстуры вне
# scope нового гейта, чтобы длина оставалась единственной проверяемой осью здесь
# (см. test_desc_trigger_gate.py — гейт триггера тестируется отдельно).
_TRIGGER_PREFIX = "Use when testing: "
# 451 симв — единственный симв сверх DESC_ERROR_MAX.
DESC_451 = _TRIGGER_PREFIX + "x" * (451 - len(_TRIGGER_PREFIX))
# 320 симв — между DESC_WARN_MAX(300) и DESC_ERROR_MAX(450).
DESC_320 = _TRIGGER_PREFIX + "y" * (320 - len(_TRIGGER_PREFIX))
# 250 симв — легальная норма (<= DESC_WARN_MAX).
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
        self.assertIn("hard-потолок", result.stdout)
        self.assertNotEqual(result.returncode, 0)

    def test_between_300_and_450_in_burndown_is_warn_only(self):
        self._write_skill("legal-debt", DESC_320)
        self._write_burndown(["testbucket/legal-debt"])
        result = self._run()
        self.assertIn("WARN: skills/testbucket/legal-debt/SKILL.md", result.stdout)
        self.assertIn("унаследованный долг", result.stdout)
        self.assertNotIn("ERROR: skills/testbucket/legal-debt/SKILL.md", result.stdout)

    def test_between_300_and_450_not_in_burndown_is_error(self):
        self._write_skill("new-debt", DESC_320)
        self._write_burndown(["# empty — новый долг не легализован"])
        result = self._run()
        self.assertIn("ERROR: skills/testbucket/new-debt/SKILL.md", result.stdout)
        self.assertIn("новый долг запрещён", result.stdout)

    def test_stale_entry_skill_missing_warns(self):
        self._write_skill("still-here", DESC_250)
        self._write_burndown(["testbucket/ghost-skill"])
        result = self._run()
        self.assertIn(
            "scripts/desc-burndown.txt: 'testbucket/ghost-skill' — протухшая запись",
            result.stdout)

    def test_stale_entry_already_short_warns(self):
        self._write_skill("already-short", DESC_250)
        self._write_burndown(["testbucket/already-short"])
        result = self._run()
        self.assertIn(
            "scripts/desc-burndown.txt: 'testbucket/already-short' — протухшая запись",
            result.stdout)

    def test_at_or_under_300_no_desc_warning(self):
        self._write_skill("clean", DESC_250)
        self._write_burndown(["# empty"])
        result = self._run()
        self.assertNotIn("skills/testbucket/clean/SKILL.md: description", result.stdout)


if __name__ == "__main__":
    unittest.main()
