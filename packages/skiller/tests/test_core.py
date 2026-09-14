"""CORE-политика раздачи: токен-скиллы по умолчанию + default-exclude дублей.

Реестр фикстуры по умолчанию НЕ содержит general/oss-dev/system (чтобы точные
ассерты других тестов держались, а CORE там был no-op). Здесь дополняем реестр
этими бакетами и проверяем инъекцию CORE (vendor=скиллы, connect=бакеты),
default-exclude дублирующих maind/ручных скиллов и отключение через --no-core."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.connect import do_connect
from skiller.vendor import do_vendor
from skiller.config import core_skill_tuples
import tests.fixtures as fx


class CoreCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        skills = self.root / "skills"
        for name in ("context-economy", "anti-drift", "compact-responses",
                     "session-handoff", "verify-claims"):
            fx.write_skill(skills / "general" / name, name)
        fx.write_skill(skills / "oss-dev" / "gh-review", "gh-review")
        fx.write_skill(skills / "system" / "shared-memory", "shared-memory")
        fx.write_skill(skills / "system" / "cross-project-coordinator",
                       "cross-project-coordinator")
        fx.write_skill(skills / "system" / "local-topology", "local-topology")
        # marketplace должен ОБЪЯВЛЯТЬ курируемый core-плагин, иначе connect-CORE его не пушит
        # (защита _marketplace_declares: на старом marketplace/в тестах плагина может не быть).
        (self.root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
            "name": "swissknifeman",
            "plugins": [{"name": "core", "source": "./",
                         "skills": ["./skills/general/context-economy"]}],
        }) + "\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_core_skill_tuples_resolves_and_respects_exclude(self):
        names = {t[3] for t in core_skill_tuples(self.env, set())}
        self.assertEqual(names, {"context-economy", "anti-drift",
                                 "session-handoff", "verify-claims"})
        # exclude (в форме bucket/rel) побеждает CORE
        excluded = {t[3] for t in core_skill_tuples(self.env, {"general/verify-claims"})}
        self.assertNotIn("verify-claims", excluded)

    def test_vendor_injects_core_even_outside_profile(self):
        # profile laravel-project -> [php, quality]; CORE-скиллы из general/oss-dev
        # должны лечь, хотя их бакеты не в профиле
        proj = fx.make_laravel_project(self.tmp)
        do_vendor(self.env, proj, {"agent": "generic"})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "general" / "context-economy" / "SKILL.md").exists())
        self.assertTrue((dest / "general" / "verify-claims" / "SKILL.md").exists())
        self.assertFalse((dest / "oss-dev" / "gh-review" / "SKILL.md").exists())
        self.assertFalse((dest / "general" / "compact-responses" / "SKILL.md").exists())

    def test_vendor_default_excludes_maind_dupes(self):
        # system выбран явно: shared-memory и cross-project-coordinator убираются
        # по умолчанию, local-topology остаётся
        proj = fx.make_laravel_project(self.tmp)
        do_vendor(self.env, proj, {"agent": "generic", "buckets": "system"})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "system" / "local-topology").exists())
        self.assertFalse((dest / "system" / "shared-memory").exists())
        self.assertFalse((dest / "system" / "cross-project-coordinator").exists())

    def test_no_core_disables_injection_and_default_exclude(self):
        proj = fx.make_laravel_project(self.tmp)
        do_vendor(self.env, proj,
                  {"agent": "generic", "buckets": "system", "no_core": True})
        dest = proj / ".ai" / "skills"
        self.assertFalse((dest / "general" / "context-economy").exists())
        # default-exclude снят -> дубли на месте
        self.assertTrue((dest / "system" / "shared-memory").exists())

    def test_connect_adds_core_plugin(self):
        # Умное подключение: CORE-политика пушит ЛЁГКИЙ курируемый плагин `core`,
        # а НЕ целые бакеты general+oss-dev (экономия резидентных токенов).
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {})
        settings = json.loads(
            (proj / ".claude" / "settings.local.json").read_text())
        enabled = {k.split("@")[0] for k, v in settings["enabledPlugins"].items() if v}
        self.assertIn("core", enabled)
        self.assertNotIn("general", enabled)   # целые бакеты больше не пушим
        self.assertNotIn("oss-dev", enabled)

    def test_connect_dry_run_redacts_existing_environment_secrets(self):
        proj = fx.make_laravel_project(self.tmp)
        settings_path = proj / ".claude" / "settings.local.json"
        settings_path.parent.mkdir()
        settings_path.write_text(json.dumps({
            "env": {"PERPLEXITY_API_KEY": "private-value"},
            "extraKnownMarketplaces": {},
        }), encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            do_connect(self.env, proj, {"dry_run": True, "no_core": True})

        self.assertNotIn("private-value", output.getvalue())
        self.assertIn("[REDACTED]", output.getvalue())
        self.assertIn("private-value", settings_path.read_text(encoding="utf-8"))

    def test_connect_no_core_omits_core_plugin(self):
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {"no_core": True})
        settings = json.loads(
            (proj / ".claude" / "settings.local.json").read_text())
        enabled = {k.split("@")[0] for k, v in settings["enabledPlugins"].items() if v}
        self.assertNotIn("core", enabled)

    def test_connect_core_skipped_when_marketplace_lacks_it(self):
        # Защита: marketplace не объявляет core (старый/пустой) → CORE не пушится,
        # но НЕ тихо (C-1) — явный warn на stderr, проверено отдельно ниже.
        (self.root / ".claude-plugin" / "marketplace.json").write_text("{}\n")
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {})
        settings = json.loads(
            (proj / ".claude" / "settings.local.json").read_text())
        enabled = {k.split("@")[0] for k, v in settings["enabledPlugins"].items() if v}
        self.assertNotIn("core", enabled)

    def test_connect_core_skipped_warns_not_silent(self):
        # C-1: раньше пропуск CORE (marketplace не объявляет плагин) был тихим —
        # обещание токен-экономии аннулировалось без сигнала. Теперь явный warn.
        (self.root / ".claude-plugin" / "marketplace.json").write_text("{}\n")
        proj = fx.make_laravel_project(self.tmp)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            do_connect(self.env, proj, {})
        self.assertIn("не объявляет плагин", buf.getvalue())
        self.assertIn("core", buf.getvalue())

    def test_connect_adds_default_command_plugins(self):
        # C-3: DEFAULT_COMMAND_PLUGINS (напр. `task`) — marketplace-guarded, как core,
        # но НЕ CORE-скилл: --no-core их не трогает (проверено ниже). Раньше эта ветка
        # (connect.py cmd_added) не была покрыта тестом — регресс раздачи команд
        # не поймали бы.
        (self.root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
            "name": "swissknifeman",
            "plugins": [
                {"name": "core", "source": "./",
                 "skills": ["./skills/general/context-economy"]},
                {"name": "task", "source": "./packages/task"},
            ],
        }) + "\n")
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {"no_core": True})
        settings = json.loads(
            (proj / ".claude" / "settings.local.json").read_text())
        enabled = {k.split("@")[0] for k, v in settings["enabledPlugins"].items() if v}
        # --no-core отключает CORE-скиллы, но НЕ командные плагины (не CORE)
        self.assertNotIn("core", enabled)
        self.assertIn("task", enabled)


if __name__ == "__main__":
    unittest.main()
