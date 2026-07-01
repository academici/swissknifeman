"""Тесты scan (P2): реестр config.json, namespace-изоляция, кластеризация, ≥N-гейт, артефакты."""
import json
import tempfile
import unittest
from pathlib import Path

from analyst import lessons, scan
from analyst.common import Env


class TestScan(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.home = self.base / "home"
        self.home.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _project(self, pid, namespaces, trigger, action):
        """Создать каталог проекта с одним ephemeral-уроком; вернуть запись реестра."""
        ppath = self.base / pid
        L = lessons.new_lesson(trigger=trigger, action=action, scope=f"project:{pid}",
                               session_id=f"s-{pid}")
        lessons.save_lesson(str(ppath), L, "ephemeral")
        return {"id": pid, "local_path": str(ppath), "namespaces": namespaces, "enabled": True}

    def _write_config(self, projects):
        cfg = self.base / "config.json"
        cfg.write_text(json.dumps({"projects": projects}), encoding="utf-8")
        return cfg

    def test_load_and_enabled_filter(self):
        cfg = self._write_config([
            {"id": "a", "local_path": "/x", "namespaces": ["axioma"], "enabled": True},
            {"id": "b", "local_path": "/y", "namespaces": ["axioma"], "enabled": False},
            {"id": "c", "local_path": "", "namespaces": ["axioma"], "enabled": True},
        ])
        projs = scan.load_projects(cfg)
        self.assertEqual(len(projs), 3)
        en = scan.enabled_projects(projs)
        self.assertEqual([p["id"] for p in en], ["a"])   # b disabled, c без local_path

    def test_cross_project_pattern_detected(self):
        # три проекта одного namespace с ПОХОЖИМ уроком → паттерн
        trig, act = "laravel service placement in domain layer", "put service classes under Domain"
        projs = [self._project(pid, ["axioma"], trig, act) for pid in ("p1", "p2", "p3")]
        buckets = scan.gather_by_namespace(projs)
        self.assertIn("axioma", buckets)
        patterns = scan.detect_patterns(buckets, min_projects=3, threshold=0.5)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["weight"], 3)
        self.assertEqual(sorted(patterns[0]["projects"]), ["p1", "p2", "p3"])

    def test_below_threshold_projects_no_pattern(self):
        trig, act = "same trigger text here", "same action text here"
        projs = [self._project(pid, ["axioma"], trig, act) for pid in ("p1", "p2")]
        patterns = scan.detect_patterns(scan.gather_by_namespace(projs), min_projects=3)
        self.assertEqual(patterns, [])

    def test_namespace_isolation(self):
        # одинаковый урок, но проекты в РАЗНЫХ namespace → НЕ кластеризуются вместе
        trig, act = "identical lesson trigger", "identical lesson action"
        projs = [
            self._project("p1", ["axioma"], trig, act),
            self._project("p2", ["axioma"], trig, act),
            self._project("p3", ["other"], trig, act),
        ]
        patterns = scan.detect_patterns(scan.gather_by_namespace(projs), min_projects=3)
        # axioma имеет лишь 2 проекта, other — 1 → ни один namespace не даёт ≥3
        self.assertEqual(patterns, [])

    def test_dissimilar_lessons_no_cluster(self):
        projs = [
            self._project("p1", ["axioma"], "laravel service domain", "domain layer"),
            self._project("p2", ["axioma"], "vue reactive refs", "use ref not reactive"),
            self._project("p3", ["axioma"], "docker compose networks", "bridge mode"),
        ]
        patterns = scan.detect_patterns(scan.gather_by_namespace(projs), min_projects=3)
        self.assertEqual(patterns, [])

    def test_write_artifacts(self):
        trig, act = "shared pattern trigger words", "shared pattern action words"
        projs = [self._project(pid, ["axioma"], trig, act) for pid in ("p1", "p2", "p3")]
        patterns = scan.detect_patterns(scan.gather_by_namespace(projs), min_projects=3)
        env = Env(self.base, "scan", home=self.home)
        written = scan.write_artifacts(env, patterns)
        self.assertEqual(len(written), 1)
        pid = written[0]
        idx = env.state_dir / "index" / "by_pattern" / f"{pid}.json"
        sug = env.state_dir / "suggestions" / f"{pid}.md"
        self.assertTrue(idx.is_file() and sug.is_file())
        data = json.loads(idx.read_text(encoding="utf-8"))
        self.assertEqual(data["weight"], 3)
        self.assertIn("Не скилл", sug.read_text(encoding="utf-8"))

    def test_cmd_scan_json_and_isolation_endtoend(self):
        trig, act = "cross project shared lesson", "the shared resolution action"
        projs = [self._project(pid, ["axioma"], trig, act) for pid in ("p1", "p2", "p3")]
        projs.append(self._project("lonely", ["solo"], trig, act))
        cfg = self._write_config(projs)
        env = Env(self.base, "scan", home=self.home)
        # env.default_config должен указывать на наш config.json (monorepo_root fallback = root=base)
        self.assertEqual(Path(env.default_config), cfg)
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            scan.cmd_scan(env, ["--json"])
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["projects_scanned"], 4)
        self.assertEqual(len(payload["patterns"]), 1)   # только axioma (3), solo изолирован (1)
        self.assertEqual(payload["patterns"][0]["namespace"], "axioma")


if __name__ == "__main__":
    unittest.main()
