"""Тесты update-реплея: подключаем проект, затем update восстанавливает выбор
из projects.json и повторно применяет его идемпотентно.

Диск — источник истины: update детектит маркеры (settings/манифест) и проигрывает
сохранённые опции. Сеть/composer не нужны — всё в tmpdir против фикстуры."""
import io
import contextlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from swissknifeman.common import MANIFEST, MARKETPLACE
from swissknifeman.connect import do_connect
from swissknifeman.vendor import do_vendor
from swissknifeman.update import cmd_update, replay_opts
import tests.fixtures as fx


def silently(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


class UpdateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_replay_opts_maps_sources(self):
        self.assertEqual(replay_opts({"profile_source": "flag",
                                      "profile": "laravel-project"}),
                         {"profile": "laravel-project"})
        self.assertEqual(replay_opts({"profile_source": "plugins",
                                      "plugins": ["php", "quality"]}),
                         {"plugins": "php,quality"})
        self.assertEqual(replay_opts({"profile_source": "buckets",
                                      "buckets": ["php"]}),
                         {"buckets": "php"})
        # autodetect/config переразрешаются с диска — флаги не навязываются
        self.assertEqual(replay_opts({"profile_source": "autodetect"}), {})

    def test_update_marketplace_idempotent(self):
        proj = fx.make_laravel_project(self.tmp)
        silently(do_connect, self.env, proj, {"profile": "laravel-project"})
        before = (proj / ".claude" / "settings.local.json").read_text()
        silently(cmd_update, self.env, ["--target", str(proj)])
        after = (proj / ".claude" / "settings.local.json").read_text()
        # повторный update не меняет включённые плагины
        b = {k for k, v in json.loads(before)["enabledPlugins"].items() if v}
        a = {k for k, v in json.loads(after)["enabledPlugins"].items() if v}
        self.assertEqual(a, b)
        self.assertEqual(a, {f"php@{MARKETPLACE}", f"quality@{MARKETPLACE}"})

    def test_update_vendor_replays_buckets(self):
        proj = fx.make_laravel_project(self.tmp)
        silently(do_vendor, self.env, proj,
                 {"agent": "generic", "buckets": "devops"})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "devops" / "docker").exists())
        # update должен переразложить тот же набор по записи projects.json
        silently(cmd_update, self.env, ["--target", str(proj)])
        self.assertTrue((dest / "devops" / "docker" / "SKILL.md").exists())
        manifest = json.loads((dest / MANIFEST).read_text())
        self.assertEqual(manifest["agent"], "generic")

    def test_update_unconnected_dies(self):
        proj = fx.make_laravel_project(self.tmp)
        with self.assertRaises(SystemExit):
            silently(cmd_update, self.env, ["--target", str(proj)])

    def test_update_help(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_update(self.env, ["--help"])
        self.assertIn("swissknifeman update", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
