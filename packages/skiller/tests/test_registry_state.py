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

from skiller.common import MARKETPLACE
from skiller.registry import build_registry, write_plugin_manifests
from skiller.state import (db_records, load_db, save_db, upsert_project)
from skiller.doctor import cmd_doctor
from skiller.status import cmd_status
from skiller.connect import do_connect
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

    def test_marketplace_emits_curated_core_plugin(self):
        # Умное подключение: registry эмитит курируемый плагин `core` (source:"./" + skills[]
        # из существующих CORE_SKILLS), грузящий РОВНО эти скиллы вместо целых бакетов.
        from skiller.config import CORE_PLUGIN
        skills = self.root / "skills"
        fx.write_skill(skills / "general" / "context-economy", "context-economy")
        fx.write_skill(skills / "oss-dev" / "gh-review", "gh-review")
        bj = json.loads((self.root / "buckets.json").read_text())
        bj["general"] = {"description": "General", "category": "eng", "tags": []}
        bj["oss-dev"] = {"description": "OSS", "category": "eng", "tags": []}
        (self.root / "buckets.json").write_text(json.dumps(bj))
        _reg, meta, dirs = build_registry(self.env)
        write_plugin_manifests(self.env, meta, dirs)
        mp = json.loads(
            (self.root / ".claude-plugin" / "marketplace.json").read_text())
        core = next((p for p in mp["plugins"] if p["name"] == CORE_PLUGIN), None)
        self.assertIsNotNone(core, "marketplace должен содержать курируемый core-плагин")
        self.assertEqual(core["source"], "./")
        self.assertIn("./skills/general/context-economy", core["skills"])
        self.assertIn("./skills/oss-dev/gh-review", core["skills"])
        # курируемый core не имеет каталога-плагина на диске (ссылки, не копии)
        self.assertFalse((skills / CORE_PLUGIN).exists())

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

    def test_fork_skill_provenance_via_non_skill_path(self):
        # fork: files[].path указывает на зеркало (references/source.md), а не на
        # SKILL.md → registry должен взять provenance из files[0] (fallback).
        fx.write_upstream(self.root / "skills" / "devops" / "docker",
                          source="github", strategy="fork",
                          path="references/source.md",
                          url="https://raw.example/SKILL.md",
                          fetched_at="2026-03-03")
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        self.assertEqual(docker["source"], "github")
        self.assertEqual(docker["upstream"], "https://raw.example/SKILL.md")
        self.assertEqual(docker["fetched_at"], "2026-03-03")

    def test_requires_only_when_present(self):
        reg, *_ = build_registry(self.env)
        conv = next(s for s in reg["skills"] if s["name"] == "laravel-conventions")
        style = next(s for s in reg["skills"] if s["name"] == "code-style")
        self.assertEqual(conv["requires"], ["code-style"])
        # у скилла без requires поле отсутствует, а не пустой список
        self.assertNotIn("requires", style)

    def test_level_only_when_present(self):
        # опц. поле level: пишется в skills.json при наличии, иначе ключа нет
        (self.root / "skills" / "devops" / "docker" / "SKILL.md").write_text(
            "---\nname: docker\nversion: 0.1.0\ndescription: Docker\n"
            "level: foundation\n---\n\nBody.\n", encoding="utf-8")
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        style = next(s for s in reg["skills"] if s["name"] == "code-style")
        self.assertEqual(docker["level"], "foundation")
        self.assertNotIn("level", style)  # omit-when-empty

    def test_content_sha256_covers_whole_dir(self):
        # content_sha256 шире sha256 (по SKILL.md): ловит правки snippets/references
        docker = self.root / "skills" / "devops" / "docker"
        reg1, *_ = build_registry(self.env)
        e1 = next(s for s in reg1["skills"] if s["name"] == "docker")
        self.assertTrue(e1["content_sha256"])
        self.assertNotEqual(e1["content_sha256"], e1["sha256"])  # разный охват
        # правим ТОЛЬКО сниппет (SKILL.md не трогаем)
        (docker / "snippets").mkdir(exist_ok=True)
        (docker / "snippets" / "ex.md").write_text("v1", encoding="utf-8")
        reg2, *_ = build_registry(self.env)
        e2 = next(s for s in reg2["skills"] if s["name"] == "docker")
        self.assertEqual(e2["sha256"], e1["sha256"])  # SKILL.md не менялся
        self.assertNotEqual(e2["content_sha256"], e1["content_sha256"])  # дир иная

    def test_content_sha256_ignores_ru_alternate(self):
        # SKILL.ru.md (языковой альтернат) не входит в content_sha256
        docker = self.root / "skills" / "devops" / "docker"
        e1 = next(s for s in build_registry(self.env)[0]["skills"]
                  if s["name"] == "docker")
        (docker / "SKILL.ru.md").write_text("полный русский источник\n",
                                            encoding="utf-8")
        e2 = next(s for s in build_registry(self.env)[0]["skills"]
                  if s["name"] == "docker")
        self.assertEqual(e2["content_sha256"], e1["content_sha256"])

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

    def test_upsert_normalizes_path_dedupes(self):
        # разные repr одного пути (./, ..) → одна запись (нормализация resolve())
        upsert_project(self.env, {"path": "/p", "channel": "vendor"})
        upsert_project(self.env, {"path": "/p/.", "channel": "vendor"})
        db = load_db(self.env)
        self.assertEqual(len(db["projects"]), 1)
        self.assertEqual(db["projects"][0]["path"], "/p")
        # lookup тоже нормализует — находит запись по «грязному» repr
        self.assertEqual(len(db_records(self.env, "/p/.")), 1)

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
        self.assertIn("skiller doctor", out)
        self.assertIn("python3", out)
        self.assertIn("профили загружаются", out)

    def test_doctor_help(self):
        _, out = capture(cmd_doctor, self.env, ["--help"])
        self.assertIn("skiller doctor", out)


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
