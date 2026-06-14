"""Тесты ядра CLI: registry-генерация, state (projects.json), doctor, status.

Гоняются против синтетического реестра (tests/fixtures) во временных каталогах,
без сети и subprocess. registry тестируется через build_registry/
write_plugin_manifests напрямую (cmd_registry зовёт generate-graph.sh)."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from swissknifeman.common import Env, MARKETPLACE
from swissknifeman.registry import build_registry, write_plugin_manifests
from swissknifeman.state import (db_records, load_db, save_db, upsert_project)
from swissknifeman.doctor import cmd_doctor
from swissknifeman.status import cmd_status
from swissknifeman.connect import do_connect
import tests.fixtures as fx


def capture(fn, *a, **kw):
    """Выполнить fn, вернуть (result, stdout-текст)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*a, **kw)
    return result, buf.getvalue()


class RegistryBuildCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_build_registry_shape(self):
        reg, bucket_meta, bucket_dirs = build_registry(self.env)
        self.assertEqual(reg["version"], 5)
        self.assertEqual(reg["name"], "swissknifeman")
        names = {s["name"] for s in reg["skills"]}
        # 4 скилла из фикстуры (generate-skill живёт вне skills/, в реестр не идёт)
        self.assertEqual(
            names, {"laravel-conventions", "code-style", "test-writer", "docker"})
        # счётчики бакетов
        self.assertEqual(reg["buckets"]["php"]["count"], 2)
        self.assertEqual(reg["buckets"]["devops"]["count"], 1)
        self.assertEqual(sorted(bucket_dirs), ["devops", "php", "quality"])

    def test_local_skill_has_source_local(self):
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        self.assertEqual(docker["source"], "local")
        self.assertNotIn("upstream", docker)

    def test_upstream_skill_carries_provenance(self):
        fx.write_upstream(self.root / "skills" / "devops" / "docker",
                          source="github",
                          url="https://raw.example/SKILL.md",
                          fetched_at="2026-02-02")
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        self.assertEqual(docker["source"], "github")
        self.assertEqual(docker["upstream"], "https://raw.example/SKILL.md")
        self.assertEqual(docker["fetched_at"], "2026-02-02")

    def test_requires_only_when_present(self):
        reg, *_ = build_registry(self.env)
        conv = next(s for s in reg["skills"] if s["name"] == "laravel-conventions")
        style = next(s for s in reg["skills"] if s["name"] == "code-style")
        self.assertEqual(conv["requires"], ["code-style"])
        # у скилла без requires поле отсутствует, а не пустой список
        self.assertNotIn("requires", style)

    def test_missing_buckets_json_dies(self):
        (self.root / "buckets.json").unlink()
        with self.assertRaises(SystemExit):
            build_registry(self.env)

    def test_write_plugin_manifests(self):
        _, bucket_meta, bucket_dirs = build_registry(self.env)
        n = write_plugin_manifests(self.env, bucket_meta, bucket_dirs)
        # 3 бакета + generate-skill
        self.assertEqual(n, 4)
        # per-bucket манифест
        php_plugin = json.loads(
            (self.root / "skills" / "php" / ".claude-plugin" / "plugin.json")
            .read_text())
        self.assertEqual(php_plugin["name"], "php")
        # корневой marketplace
        mk = json.loads(
            (self.root / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(mk["name"], MARKETPLACE)
        plugin_names = {p["name"] for p in mk["plugins"]}
        self.assertIn("generate-skill", plugin_names)
        self.assertIn("php", plugin_names)


class StateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_db_default_when_absent(self):
        self.assertFalse(self.env.db_file.exists())
        db = load_db(self.env)
        self.assertEqual(db["projects"], [])
        self.assertIn("version", db)

    def test_upsert_insert_then_update_preserves_first_connected(self):
        upsert_project(self.env, {"path": "/p", "channel": "vendor",
                                  "buckets": ["php"]})
        rec1 = load_db(self.env)["projects"][0]
        first = rec1["first_connected_at"]
        self.assertEqual(rec1["buckets"], ["php"])
        # обновляем тот же (path, channel) — first_connected_at сохраняется
        upsert_project(self.env, {"path": "/p", "channel": "vendor",
                                  "buckets": ["php", "devops"]})
        db = load_db(self.env)
        self.assertEqual(len(db["projects"]), 1)
        rec2 = db["projects"][0]
        self.assertEqual(rec2["buckets"], ["php", "devops"])
        self.assertEqual(rec2["first_connected_at"], first)

    def test_upsert_distinct_channels_coexist(self):
        upsert_project(self.env, {"path": "/p", "channel": "vendor"})
        upsert_project(self.env, {"path": "/p", "channel": "marketplace"})
        recs = db_records(self.env, "/p")
        self.assertEqual({r["channel"] for r in recs}, {"vendor", "marketplace"})

    def test_save_load_round_trip_no_tmp_left(self):
        save_db(self.env, {"version": 1, "projects": [{"path": "/x",
                                                       "channel": "vendor"}]})
        self.assertEqual(load_db(self.env)["projects"][0]["path"], "/x")
        # атомарная запись не оставляет временного файла
        leftovers = list(self.env.state_dir.glob("*.tmp"))
        self.assertEqual(leftovers, [])


class DoctorCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_doctor_runs_and_reports(self):
        # doctor может вернуть код 1 (нет симлинка/не git-репо в tmp) — это норма;
        # важно, что он не падает с исключением и печатает диагностику.
        try:
            _, out = capture(cmd_doctor, self.env, [])
        except SystemExit:
            # issues>0 -> sys.exit(1); перехватываем вывод повторно без exit-чувствительности
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with contextlib.suppress(SystemExit):
                    cmd_doctor(self.env, [])
            out = buf.getvalue()
        self.assertIn("swissknifeman doctor", out)
        self.assertIn("python3", out)
        self.assertIn("профили загружаются", out)

    def test_doctor_help(self):
        _, out = capture(cmd_doctor, self.env, ["--help"])
        self.assertIn("swissknifeman doctor", out)


class StatusCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_status_on_connected_project(self):
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {})
        _, out = capture(cmd_status, self.env, ["--target", str(proj)])
        self.assertIn(str(proj), out)
        self.assertIn("marketplace", out)
        self.assertIn("Профиль", out)

    def test_status_on_unconnected_project(self):
        proj = fx.make_laravel_project(self.tmp)
        _, out = capture(cmd_status, self.env, ["--target", str(proj)])
        self.assertIn("не подключён", out)


if __name__ == "__main__":
    unittest.main()
