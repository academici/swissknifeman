"""Интеграционный тест: фейковый Laravel-проект, кейсы connect/vendor.

Каждый кейс гоняет реальный do_connect/do_vendor против синтетического
реестра (tests/fixtures) и проверяет артефакты на диске: .claude/settings,
манифест вендоринга, flat-layout для Boost, boost.json::skills, projects.json,
транзитивный requires. Сеть/composer/php не нужны — всё в tmpdir."""
import json
import unittest
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from swissknifeman.connect import do_connect
from swissknifeman.vendor import do_vendor
from swissknifeman.common import MANIFEST, MARKETPLACE
import tests.fixtures as fx


class LaravelCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    # --- connect (plugin marketplace) -------------------------------------------
    def test_connect_autodetect_writes_settings_and_db(self):
        proj = fx.make_laravel_project(self.tmp)
        rec = do_connect(self.env, proj, {})
        settings = json.loads(
            (proj / ".claude" / "settings.local.json").read_text())
        # marketplace объявлен с путём на наш реестр
        mk = settings["extraKnownMarketplaces"][MARKETPLACE]
        self.assertEqual(mk["source"]["path"], str(self.root))
        # профиль laravel-project -> php + quality плагины включены
        enabled = {k.split("@")[0] for k, v in settings["enabledPlugins"].items() if v}
        self.assertEqual(enabled, {"php", "quality"})
        self.assertEqual(rec["profile"], "laravel-project")
        # запись в projects.json
        db = json.loads(self.env.db_file.read_text())
        self.assertEqual(len(db["projects"]), 1)
        self.assertEqual(db["projects"][0]["channel"], "marketplace")

    def test_connect_explicit_plugins(self):
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {"plugins": "devops"})
        settings = json.loads(
            (proj / ".claude" / "settings.local.json").read_text())
        enabled = {k.split("@")[0] for k, v in settings["enabledPlugins"].items() if v}
        self.assertEqual(enabled, {"devops"})

    def test_connect_preserves_explicit_false(self):
        proj = fx.make_laravel_project(self.tmp)
        claude = proj / ".claude"
        claude.mkdir(parents=True)
        (claude / "settings.local.json").write_text(json.dumps({
            "enabledPlugins": {f"php@{MARKETPLACE}": False}}))
        do_connect(self.env, proj, {"profile": "laravel-project"})
        settings = json.loads((claude / "settings.local.json").read_text())
        # явный false для php не перетёрт
        self.assertIs(settings["enabledPlugins"][f"php@{MARKETPLACE}"], False)
        # бэкап создан
        self.assertTrue((claude / "settings.local.json.bak").exists())

    def test_connect_dry_run_writes_nothing(self):
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {"dry_run": True})
        self.assertFalse((proj / ".claude" / "settings.local.json").exists())
        self.assertFalse(self.env.db_file.exists())

    def test_connect_unknown_plugin_exits(self):
        proj = fx.make_laravel_project(self.tmp)
        with self.assertRaises(SystemExit):
            do_connect(self.env, proj, {"plugins": "does-not-exist"})

    # --- vendor -----------------------------------------------------------------
    def test_vendor_generic_bucket_layout(self):
        proj = fx.make_laravel_project(self.tmp)
        do_vendor(self.env, proj, {"agent": "generic", "buckets": "devops"})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "devops" / "docker" / "SKILL.md").exists())
        manifest = json.loads((dest / MANIFEST).read_text())
        self.assertEqual(manifest["layout"], "bucket")
        self.assertEqual(manifest["agent"], "generic")

    def test_vendor_pulls_requires(self):
        proj = fx.make_laravel_project(self.tmp)
        # выбираем только php (laravel-conventions требует code-style — обе должны лечь)
        do_vendor(self.env, proj, {"agent": "generic", "buckets": "php"})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "php" / "laravel-conventions" / "SKILL.md").exists())
        self.assertTrue((dest / "php" / "code-style" / "SKILL.md").exists())

    def test_vendor_exclude_skips_skill(self):
        proj = fx.make_laravel_project(self.tmp)
        do_vendor(self.env, proj,
                  {"agent": "generic", "buckets": "php", "exclude": "code-style"})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "php" / "laravel-conventions").exists())
        self.assertFalse((dest / "php" / "code-style").exists())

    def test_vendor_upstream_and_plugin_meta_not_copied(self):
        # upstream.json/.claude-plugin не должны попадать в вендоренную копию
        proj = fx.make_laravel_project(self.tmp)
        sd = self.root / "skills" / "devops" / "docker"
        (sd / "upstream.json").write_text("{}")
        (sd / ".claude-plugin").mkdir()
        (sd / ".claude-plugin" / "plugin.json").write_text("{}")
        do_vendor(self.env, proj, {"agent": "generic", "buckets": "devops"})
        dest = proj / ".ai" / "skills" / "devops" / "docker"
        self.assertTrue((dest / "SKILL.md").exists())
        self.assertFalse((dest / "upstream.json").exists())
        self.assertFalse((dest / ".claude-plugin").exists())

    # --- vendor into a Boost project (flat layout + boost.json sync) ------------
    def test_vendor_boost_uses_flat_layout_and_syncs_boost_json(self):
        proj = fx.make_laravel_project(self.tmp, boost=True)
        do_vendor(self.env, proj, {"agent": "generic", "buckets": "php"})
        dest = proj / ".ai" / "skills"
        # flat: .ai/skills/<name>/SKILL.md (без уровня бакета)
        self.assertTrue((dest / "laravel-conventions" / "SKILL.md").exists())
        self.assertTrue((dest / "code-style" / "SKILL.md").exists())
        self.assertFalse((dest / "php").exists())
        manifest = json.loads((dest / MANIFEST).read_text())
        self.assertEqual(manifest["layout"], "flat")
        # boost.json::skills дозаписан именами скиллов
        boost = json.loads((proj / "boost.json").read_text())
        self.assertIn("laravel-conventions", boost["skills"])
        self.assertIn("code-style", boost["skills"])

    def test_vendor_reinstall_is_clean(self):
        # повторный vendor с меньшим набором не оставляет осиротевшие каталоги
        proj = fx.make_laravel_project(self.tmp)
        do_vendor(self.env, proj, {"agent": "generic", "buckets": "php,devops"})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "devops" / "docker").exists())
        do_vendor(self.env, proj, {"agent": "generic", "buckets": "php"})
        # devops больше не выбран — должен быть вычищен по манифесту
        self.assertFalse((dest / "devops").exists())
        self.assertTrue((dest / "php" / "code-style").exists())


if __name__ == "__main__":
    unittest.main()
