"""Tests settings: thresholds from aicore.config (defaults, project file, environment) and their wiring."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore.config import ConfigError

from analyst import digest, lessons, recompute, settings, status

SCHEMA = Path(settings.UNIT_ROOT) / "configs" / "config.schema.json"


def _mk(proj, state):
    L = lessons.new_lesson(trigger="t", action="a", scope="project:test", session_id="s1")
    lessons.save_lesson(proj, L, state)
    return L["id"]


class SettingsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.proj = self.root / "proj"
        self.proj.mkdir()
        self.env = {"SKM_HOME": str(self.root / "skm")}

    def project_config(self, body):
        path = self.proj / ".swissknifeman" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("schema_version = 1\n" + body, encoding="utf-8")
        return path

    def load(self, **kwargs):
        return settings.load_thresholds(self.proj, env=kwargs.pop("env", self.env), **kwargs)


class TestLoadThresholds(SettingsCase):
    def test_without_files_defaults(self):
        self.assertEqual(settings.DEFAULT_THRESHOLDS, self.load())
        self.assertEqual(settings.DEFAULT_THRESHOLDS, settings.load_thresholds(None, env=self.env))

    def test_project_file_changes_threshold_and_decision(self):
        self.project_config("[analyst.recompute]\ncandidate_min_n = 20\n")
        thresholds = self.load()
        self.assertEqual(20, thresholds.candidate_min_n)
        self.assertEqual(15, settings.DEFAULT_THRESHOLDS.candidate_min_n)
        self.assertEqual((20, 50), recompute.adaptive_thresholds(200, thresholds))
        agg = {"N": 18, "tests_total": 1, "tests_passed": 1}
        self.assertEqual("promote", recompute.decide_transition("ephemeral", agg, 0.9)[1])
        self.assertEqual("unchanged", recompute.decide_transition("ephemeral", agg, 0.9, 20, 50, thresholds)[1])
        self.assertEqual("unchanged", recompute.decide_transition("ephemeral", agg, 0.9,
                                                                  thresholds=thresholds.__class__(candidate_min_n=20))[1])

    def test_environment_beats_project(self):
        self.project_config("[analyst.recompute]\ncandidate_min_n = 20\n")
        env = dict(self.env, SKM_ANALYST_RECOMPUTE__CANDIDATE_MIN_N="7")
        self.assertEqual(7, self.load(env=env).candidate_min_n)

    def test_invalid_value_reports_file_and_line(self):
        path = self.project_config("[analyst.recompute]\ncandidate_min_n = 0\n")
        with self.assertRaises(ConfigError) as caught:
            self.load()
        self.assertIn(f"{path}:3", str(caught.exception))
        self.assertEqual("CONFIG_TYPE", caught.exception.code)

    def test_every_field_is_wired(self):
        body = ("[analyst.recompute]\ncandidate_min_n = 2\ncandidate_min_conf = 0.1\ncurated_min_n = 3\n"
                "curated_min_conf = 0.2\ncurated_min_passrate = 0.3\ndeprecate_conf = 0.4\n"
                "candidate_min_n_floor = 5\n[analyst.digest]\npathology_window = 6\npathology_min_hits = 4\n")
        self.project_config(body)
        self.assertEqual(settings.Thresholds(2, 0.1, 3, 0.2, 0.3, 0.4, 5, 6, 4), self.load())


class TestSchemaParity(unittest.TestCase):
    def test_schema_defaults_equal_code_defaults(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        defaults = {}
        for table, spec in schema["properties"].items():
            for key, leaf in spec["properties"].items():
                defaults[f"{table}.{key}"] = leaf["default"]
        self.assertEqual(set(settings._KEYS.values()), set(defaults))
        for field, key in settings._KEYS.items():
            self.assertEqual(defaults[key], getattr(settings.DEFAULT_THRESHOLDS, field), key)

    def test_module_constants_equal_defaults(self):
        t = settings.DEFAULT_THRESHOLDS
        self.assertEqual((15, 0.6, 50, 0.8, 0.95, 0.6, 3),
                         (recompute.CANDIDATE_MIN_N, recompute.CANDIDATE_MIN_CONF, recompute.CURATED_MIN_N,
                          recompute.CURATED_MIN_CONF, recompute.CURATED_MIN_PASSRATE, recompute.DEPRECATE_CONF,
                          recompute.CANDIDATE_MIN_N_FLOOR))
        self.assertEqual((5, 2), (digest.PATHOLOGY_WINDOW, digest.PATHOLOGY_MIN_HITS))
        self.assertEqual((t.pathology_window, t.pathology_min_hits), (5, 2))


class TestWiring(SettingsCase):
    def run_cmd(self, func, argv):
        out, err = io.StringIO(), io.StringIO()
        old = os.getcwd()
        os.chdir(self.proj)
        self.addCleanup(os.chdir, old)
        code = 0
        with mock.patch.dict(os.environ, self.env, clear=False), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            try:
                func(None, argv)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def _lesson_with_events(self):
        lid = _mk(str(self.proj), "ephemeral")
        lessons.event_append(str(self.proj), {"id": lid, "ts": "2026-06-01T00:00:00Z", "sessions_total": 60,
                                              "sessions_success": 60, "tests_total": 10, "tests_passed": 10})
        return lid

    def action_of(self, code_out):
        return json.loads(code_out)["results"][0]["action"]

    def test_cmd_recompute_dry_run_uses_project_threshold(self):
        self._lesson_with_events()
        argv = ["--dry-run", "--json", "--now", "2026-06-01T00:00:00Z"]
        code, out, _ = self.run_cmd(recompute.cmd_recompute, argv)
        self.assertEqual((0, "promote"), (code, self.action_of(out)))
        self.project_config("[analyst.recompute]\ncandidate_min_n = 100\n")
        code, out, _ = self.run_cmd(recompute.cmd_recompute, argv)
        self.assertEqual((0, "unchanged"), (code, self.action_of(out)))

    def test_cmd_recompute_config_error_has_no_traceback(self):
        path = self.project_config("[analyst.recompute]\ncandidate_min_n = 0\n")
        code, _, err = self.run_cmd(recompute.cmd_recompute, ["--dry-run"])
        self.assertEqual(1, code)
        self.assertIn(f"{path}:3", err)
        self.assertNotIn("Traceback", err)
        for func in (status.cmd_status, digest.cmd_digest):
            code, _, err = self.run_cmd(func, [])
            self.assertEqual(1, code)
            self.assertIn(f"{path}:3", err)

    def test_status_curated_ready_follows_thresholds(self):
        lid = _mk(str(self.proj), "candidate")
        lessons.event_append(str(self.proj), {"id": lid, "ts": "2026-06-01T00:00:00Z", "sessions_total": 60,
                                              "sessions_success": 60, "tests_total": 10, "tests_passed": 10})
        recompute.recompute_project(str(self.proj), "2026-06-01T00:00:00Z")
        self.assertEqual(1, status.build_status(str(self.proj))["curated_ready"])
        strict = settings.Thresholds(curated_min_n=500)
        self.assertEqual(0, status.build_status(str(self.proj), strict)["curated_ready"])

    def test_pathology_window_and_hits_follow_thresholds(self):
        runs = self.proj / ".claude" / "runs"
        runs.mkdir(parents=True)
        for index in range(4):
            (runs / f"r{index}.json").write_text(json.dumps({"session_id": f"s{index}"}), encoding="utf-8")
            os.utime(runs / f"r{index}.json", (1000 + index, 1000 + index))
        current = {"session_id": "now"}
        self.assertEqual(5, len(digest._recent_run_reports(str(self.proj), current)))
        self.assertEqual(2, len(digest._recent_run_reports(str(self.proj), current, 2)))
        with mock.patch.object(digest, "detect_pathologies", return_value=[{"code": "file-reread"}]):
            counts = digest._pathology_hit_counts(str(self.proj), current, settings.Thresholds(pathology_window=2))
            self.assertEqual({"file-reread": 2}, counts)
            lessons_one = digest.extract_pathologies(current, str(self.proj), settings.Thresholds(pathology_min_hits=2))
            lessons_three = digest.extract_pathologies(current, str(self.proj),
                                                      settings.Thresholds(pathology_window=5, pathology_min_hits=6))
        self.assertEqual(1, len(lessons_one))
        self.assertIn("5/5", lessons_one[0]["trigger"])
        self.assertEqual([], lessons_three)


if __name__ == "__main__":
    unittest.main()
