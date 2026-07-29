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
from skiller.status import (channel_overlap, cmd_status, dead_local_entries,
                            detect_raw_vendor_path, local_channel_entries,
                            name_duplicates, registry_skill_names)
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


class TestDetectRawVendorPath(unittest.TestCase):
    """P3.5 дельта а: канал без манифеста (репо-факт flexcrm — симлинки из
    стороннего .ai/skills, без skills-lock.json)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_none_when_no_skills_dir(self):
        self.assertIsNone(detect_raw_vendor_path(self.tmp, {}))

    def test_none_when_skills_dir_empty(self):
        (self.tmp / ".claude" / "skills").mkdir(parents=True)
        self.assertIsNone(detect_raw_vendor_path(self.tmp, {}))

    def test_found_without_manifest(self):
        d = self.tmp / ".claude" / "skills" / "foo"
        d.mkdir(parents=True)
        self.assertEqual(detect_raw_vendor_path(self.tmp, {}), ".claude/skills")

    def test_respects_configured_skills_path(self):
        d = self.tmp / "custom" / "skills" / "foo"
        d.mkdir(parents=True)
        self.assertEqual(
            detect_raw_vendor_path(self.tmp, {"skills_path": "custom/skills"}),
            "custom/skills")


class TestLocalChannelEntries(unittest.TestCase):
    """P3.5 дельта в: мёртвые записи — битые симлинки И каталоги без SKILL.md."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.skills_dir = self.tmp / "skills"
        self.skills_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_live_dead_and_empty_dir_classified(self):
        live = self.skills_dir / "live-skill"
        fx.write_skill(live, "live-skill", description="A live one")
        (self.skills_dir / "no-skill-md").mkdir()
        (self.skills_dir / "broken-link").symlink_to(
            self.skills_dir / "nonexistent-target")
        entries = local_channel_entries(self.skills_dir)
        by_dir = {e["dir"]: e for e in entries}
        self.assertEqual(by_dir["live-skill"],
                         {"dir": "live-skill", "dead": False, "name": "live-skill"})
        self.assertTrue(by_dir["no-skill-md"]["dead"])
        self.assertTrue(by_dir["broken-link"]["dead"])

    def test_empty_dir_returns_no_entries(self):
        self.assertEqual(local_channel_entries(self.skills_dir), [])

    def test_missing_dir_returns_no_entries(self):
        self.assertEqual(local_channel_entries(self.skills_dir / "gone"), [])


class TestNameDuplicatesAgainstRegistry(unittest.TestCase):
    """P3.5 дельта б: дубль считается по frontmatter `name`, по ВСЕМУ реестру
    (не только включённым бакетам) — вторая физическая копия скилла реестра."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_duplicate_and_unique_names(self):
        names = registry_skill_names(self.env)
        self.assertIn("code-style", names)
        self.assertEqual(names["code-style"], ["php"])
        local = [
            {"dir": "code-style", "dead": False, "name": "code-style"},
            {"dir": "my-own-thing", "dead": False, "name": "my-own-thing"},
            {"dir": "broken", "dead": True, "name": None},
        ]
        dup = name_duplicates(local, names)
        self.assertEqual(dup, [("code-style", "code-style", ("php",))])

    def test_dead_entries_ignored_by_dup_detector(self):
        names = registry_skill_names(self.env)
        local = [{"dir": "code-style", "dead": True, "name": None}]
        self.assertEqual(name_duplicates(local, names), [])


class TestStatusRawVendorReport(unittest.TestCase):
    """Интеграционный прогон cmd_status на канале без манифеста — тот же класс,
    что flexcrm (Code Guidance item'а требует прогона на живом дереве; здесь —
    воспроизводимый эквивалент в tmpdir)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.proj = fx.make_laravel_project(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_reports_duplicates_and_dead_entries(self):
        skills_dir = self.proj / ".claude" / "skills"
        # дубль имени с реестровым php/code-style
        fx.write_skill(skills_dir / "code-style", "code-style")
        # уникальный локальный скилл — не дубль
        fx.write_skill(skills_dir / "my-own-thing", "my-own-thing")
        # битый симлинк
        (skills_dir / "broken").symlink_to(skills_dir / "nowhere")
        out = run(cmd_status, self.env, ["--target", str(self.proj)])
        self.assertIn("БЕЗ манифеста", out)
        self.assertIn("ДУБЛИ ИМЁН", out)
        self.assertIn("code-style", out)
        self.assertIn("МЁРТВЫЕ ЗАПИСИ", out)
        self.assertIn("broken", out)
        js = json.loads(run(cmd_status, self.env,
                            ["--target", str(self.proj), "--json"]))
        self.assertEqual(js["dead_entries"], ["broken"])
        self.assertEqual([d["dir"] for d in js["name_duplicates"]], ["code-style"])

    def test_silent_when_no_local_skills_dir(self):
        out = run(cmd_status, self.env, ["--target", str(self.proj)])
        self.assertNotIn("ДУБЛИ ИМЁН", out)
        self.assertNotIn("МЁРТВЫЕ ЗАПИСИ", out)
        self.assertNotIn("Канал vendor", out)


if __name__ == "__main__":
    unittest.main()
