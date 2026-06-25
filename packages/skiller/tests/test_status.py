"""Тесты status — read-only отчёт и гигиена каналов.

Ключевой кейс: один бакет не должен раздаваться ОДНОВРЕМЕННО плагином (connect) и
вендором (vendor) — иначе скиллы дублируются. Проверка живёт в skiller (владелец
скиллов) и доступна из зонтика через `swissknifeman skills status`."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.common import MANIFEST, MARKETPLACE
from skiller.status import channel_overlap, cmd_status
import tests.fixtures as fx


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


class TestChannelOverlapUnit(unittest.TestCase):
    def test_overlap_pure(self):
        self.assertEqual(
            channel_overlap(["php", "quality"], {"php", "devops"}), ["php"])
        self.assertEqual(channel_overlap(["php"], set()), [])
        self.assertEqual(channel_overlap([], {"php"}), [])


class TestStatusOverlapReport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.proj = fx.make_laravel_project(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _enable_plugins(self, buckets):
        """Записать connect-артефакт: marketplace + enabledPlugins для бакетов."""
        d = self.proj / ".claude"
        d.mkdir(parents=True, exist_ok=True)
        (d / "settings.local.json").write_text(json.dumps({
            "extraKnownMarketplaces": {
                MARKETPLACE: {"source": {"source": "directory",
                                         "path": str(self.root)}}},
            "enabledPlugins": {f"{b}@{MARKETPLACE}": True for b in buckets},
        }), encoding="utf-8")

    def _vendor_manifest(self, buckets):
        """Записать vendor-манифест с по одному скиллу на бакет."""
        d = self.proj / ".claude" / "skills"
        d.mkdir(parents=True, exist_ok=True)
        (d / MANIFEST).write_text(json.dumps({
            "version": 1, "layout": "flat", "agent": "claude", "profile": "",
            "installed_at": "2026-06-25T00:00:00Z",
            "skills": [{"flat_name": f"s-{b}",
                        "source_path": f"skills/{b}/s-{b}"} for b in buckets],
        }), encoding="utf-8")

    def test_warns_when_bucket_in_both_channels(self):
        self._enable_plugins(["php", "quality"])
        self._vendor_manifest(["php"])           # php в обоих каналах
        out = run(cmd_status, self.env, ["--target", str(self.proj)])
        self.assertIn("ДУБЛЬ КАНАЛОВ", out)
        self.assertIn("php", out.split("ДУБЛЬ КАНАЛОВ")[1].splitlines()[0])

    def test_no_warning_when_channels_disjoint(self):
        self._enable_plugins(["quality"])
        self._vendor_manifest(["php"])           # пересечения нет
        out = run(cmd_status, self.env, ["--target", str(self.proj)])
        self.assertNotIn("ДУБЛЬ КАНАЛОВ", out)

    def test_no_warning_single_channel(self):
        self._vendor_manifest(["php"])           # только vendor
        out = run(cmd_status, self.env, ["--target", str(self.proj)])
        self.assertNotIn("ДУБЛЬ КАНАЛОВ", out)


if __name__ == "__main__":
    unittest.main()
