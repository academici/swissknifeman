"""P3.5 (2026.07.31-SKM-LEAN): validate.sh description+when_to_use гейты (длина и
триггер) читают СОВОКУПНУЮ запись листинга, не голый `description` — та же формула, что
`budget.py::_listing_entry_tokens`/`_listing_entry_chars`
(`(description + " " + when_to_use).strip()`, upstream кап 1 536 симв). Дополняет
test_desc_burndown_gate.py (длина, description-only фикстуры) и test_desc_trigger_gate.py
(триггер, description-only фикстуры) сценариями, где `when_to_use` несёт часть записи.

Зеркалит те же две обёртки (реальный запуск validate.sh против синтетического skills/,
проверяем КОНКРЕТНЫЕ строки stdout, не общий exit-код)."""
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = PKG_ROOT / "scripts" / "validate.sh"


class DescListingCombinedGateCase(unittest.TestCase):
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

    def _write_skill(self, name, description, when_to_use=None):
        d = self.skills_dir / name
        d.mkdir()
        fm = (f"---\nname: {name}\nbucket: testbucket\nversion: 1.0.0\n"
              f"description: {description}\n")
        if when_to_use is not None:
            fm += f"when_to_use: {when_to_use}\n"
        fm += "---\n\nBody.\n"
        (d / "SKILL.md").write_text(fm, encoding="utf-8")

    def _write_trigger_burndown(self, lines):
        (self.scripts_dir / "desc-trigger-burndown.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    def _write_desc_burndown(self, lines):
        (self.scripts_dir / "desc-burndown.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    def _run(self):
        return subprocess.run(
            ["bash", str(self.scripts_dir / "validate.sh")],
            capture_output=True, text=True, timeout=60)

    def test_trigger_in_when_to_use_satisfies_gate(self):
        # description сама по себе триггера не несёт — он ТОЛЬКО в when_to_use.
        self._write_skill("moved-trigger", "A short description with no phrase at all",
                          when_to_use="Use when validating that when_to_use counts too")
        self._write_trigger_burndown(["# empty — новый долг не легализован"])
        result = self._run()
        self.assertNotIn(
            "skills/testbucket/moved-trigger/SKILL.md: description+when_to_use без "
            "триггерной", result.stdout)

    def test_length_is_sum_of_both_fields_over_warn_not_in_burndown_errors(self):
        # description сама по себе <= 300 (легальна одна), но сумма с when_to_use > 300.
        desc = "Use when summing: " + "d" * 180  # 199 симв
        when = "e" * 150  # сумма = 199 + 1 (пробел) + 150 = 349 > DESC_WARN_MAX(300)
        self._write_skill("summed-over", desc, when_to_use=when)
        self._write_trigger_burndown(["# empty"])
        self._write_desc_burndown(["# empty — новый долг не легализован"])
        result = self._run()
        self.assertIn("ERROR: skills/testbucket/summed-over/SKILL.md", result.stdout)
        self.assertIn("запись листинга (description+when_to_use)", result.stdout)
        self.assertIn("349 симв", result.stdout)
        self.assertIn("новый долг запрещён", result.stdout)

    def test_length_is_sum_of_both_fields_over_warn_in_burndown_warns_only(self):
        desc = "Use when summing: " + "d" * 180
        when = "e" * 150
        self._write_skill("summed-legal", desc, when_to_use=when)
        self._write_trigger_burndown(["# empty"])
        self._write_desc_burndown(["testbucket/summed-legal"])
        result = self._run()
        self.assertIn("WARN: skills/testbucket/summed-legal/SKILL.md", result.stdout)
        self.assertIn("унаследованный долг", result.stdout)
        self.assertNotIn("ERROR: skills/testbucket/summed-legal/SKILL.md", result.stdout)

    def test_stale_trigger_burndown_entry_via_when_to_use_warns(self):
        # description без триггера, но when_to_use его несёт — запись в trigger-burndown
        # протухла (совокупная запись УЖЕ несёт триггер).
        self._write_skill("already-fixed-via-wtu", "A plain description with no phrase",
                          when_to_use="Use when checking stale burndown entries")
        self._write_trigger_burndown(["testbucket/already-fixed-via-wtu"])
        result = self._run()
        self.assertIn(
            "scripts/desc-trigger-burndown.txt: 'testbucket/already-fixed-via-wtu' — "
            "протухшая запись", result.stdout)
        self.assertIn("уже несёт триггерную фразу", result.stdout)


if __name__ == "__main__":
    unittest.main()
