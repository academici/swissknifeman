"""Интегрирующий тест settings-doctor: воспроизводит целиком field-case §Проблема
из `roadmap/settings-doctor.md` в tmpdir и требует, чтобы doctor ловил его СРАЗУ,
одним прогоном (критерий закрытия фазы P1, Implementation Rules P1.5).

Анти-самообман: не мокаем `run_checks`/эффективную конфигурацию — реальные файлы
`.claude/settings*.json`, реальный `build_context`/`run_checks`. Если тест красный —
чинится код doctor'а, а не ассерты."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.common import Env
from harness.settings_audit import build_context, exit_code, run_checks

from tests.test_settings_audit import _write


class SettingsDoctorFieldCase(unittest.TestCase):
    """Пункты §Проблема, воспроизведённые одновременно:

    1. `defaultMode` объявлен и в `user`, и в `local` (расхождение слоёв — id=3).
    2. Хук `PreToolUse`, объявленный в проекте, указывает на script, которого
       физически нет (владелец считал, что хук установлен — id=5).
    3. ~400 одноразовых точных `Bash(...)`-правил в `user` (id=6).
    4. Неканонический `permissions.autoApprove` в проекте (id=2).
    5. Плейнтекстовый API-ключ в `env` локальных настроек (id=9).
    6. `additionalDirectories`, объявленный вместо Bash-правил (ложное ожидание,
       что он решает матчинг Bash — не отдельный числовой id, но не должен
       уронить прогон; путь реальный, без лишнего шума).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.target = self.tmp / "proj"
        self.home.mkdir()
        self.target.mkdir()
        self.env = Env(self.tmp, "test", home=self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def test_full_field_case_caught_in_one_pass(self):
        # 1) defaultMode в user И local — расхождение слоёв (id=3).
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "default"}})

        # 2) PreToolUse-хук объявлен, но command-файл физически отсутствует (id=5).
        # 3) ~400 точных Bash(...)-правил в user (id=6) — дописываем в тот же слой.
        dead_allow = [f"Bash(echo {i})" for i in range(400)]
        _write(self.home / ".claude" / "settings.json", {
            "permissions": {"defaultMode": "default", "allow": dead_allow},
        })

        real_dir = self.tmp / "trusted"
        real_dir.mkdir()

        # 4) permissions.autoApprove — неканонический ключ (id=2).
        # 6) additionalDirectories вместо Bash-правил — путь реальный (не создаёт шум id=8).
        _write(self.target / ".claude" / "settings.json", {
            "permissions": {
                "defaultMode": "bypassPermissions",
                "autoApprove": True,
                "additionalDirectories": [str(real_dir)],
            },
            "hooks": {"PreToolUse": [
                {"matcher": "Bash",
                 "hooks": [{"type": "command",
                            "command": str(self.target / "hooks" / "safe-dirs.sh")}]},
            ]},
        })

        # 5) плейнтекстовый API-ключ в env локальных настроек (id=9).
        _write(self.target / ".claude" / "settings.local.json",
               {"env": {"ANTHROPIC_API_KEY": "sk-ant-0123456789abcdef"}})

        ctx = build_context(self.env, self.target)
        findings = run_checks(ctx)
        by_id = {}
        for f in findings:
            by_id.setdefault(f.id, []).append(f)

        for expected_id in (2, 3, 5, 6, 9):
            self.assertIn(expected_id, by_id,
                           f"ожидалась находка id={expected_id}, получены id: "
                           f"{sorted(by_id.keys())}")

        # id=8 (additionalDirectories) НЕ должна сработать — путь реальный.
        self.assertNotIn(8, by_id)

        self.assertGreater(exit_code(findings), 0)
        error_count = sum(1 for f in findings if f.level == "error")
        self.assertGreater(error_count, 0)


if __name__ == "__main__":
    unittest.main()
