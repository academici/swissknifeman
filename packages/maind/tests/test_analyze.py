"""Тесты analyze.py: поиск run-report, форензика bash-лога, вердикт GREEN/ATTENTION/RED,
сборка отчёта и --json. Без сети/демона — health-срез отключаем (with_health=False),
живой замер памяти не нужен для логики разбора."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from maind.analysis.analyze import (analyze_report, analytics_slice, bash_log_forensics, compute_verdict,
                           find_run_report, git_status, pending_lessons)
from maind.config import load_config
from tests.fixtures import make_repo, write_maind_config

GREEN_RR = {"schema": 1, "tools": {"total": 3, "by_name": {"Bash": 2, "Edit": 1}},
            "files_changed": ["/p/a.py"],
            "bash": {"tests": [{"command": "pytest", "ok": True}],
                     "lints": [{"command": "ruff", "ok": True}], "failed": []},
            "tool_failures": [], "workflows": [], "devloop": None,
            "session_id": "g1"}

ATTN_RR = {"schema": 1, "tools": {"total": 2, "by_name": {"Bash": 2}},
           "files_changed": [],
           "bash": {"tests": [{"command": "pytest", "ok": True}],
                    "lints": [{"command": "ruff", "ok": False}], "failed": ["ruff"]},
           "tool_failures": [{"tool": "Bash", "snippet": "boom"}],
           "workflows": [{"name": "dev-loop", "status": "completed", "summary": "ok"}],
           "devloop": {"deferred": ["e2e test"], "tool_failures": ["perplexity-web locked"]},
           "session_id": "a1"}

RED_RR = {"schema": 1, "tools": {"total": 1, "by_name": {"Bash": 1}}, "files_changed": [],
          "bash": {"tests": [{"command": "pytest", "ok": False}], "lints": [], "failed": ["pytest"]},
          "tool_failures": [], "workflows": [{"name": "dev-loop", "status": "failed"}],
          "devloop": None, "session_id": "r1"}

# тяжёлое сканирование (Read/Grep/Glob = 40) при нуле обращений к графу + пустой recall
MAIND_RR = {"schema": 1, "tools": {"total": 40, "by_name": {"Read": 25, "Grep": 10, "Glob": 5}},
            "files_changed": [], "bash": {"tests": [], "lints": [], "failed": []},
            "tool_failures": [], "workflows": [], "devloop": None,
            "maind": {"memory_recall": {"calls": 2, "results": 2, "found_total": 0, "found_max": 0}},
            "session_id": "m1"}


def _write_run(projdir, report):
    runs = Path(projdir) / ".claude" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{report['session_id']}.json").write_text(json.dumps(report), encoding="utf-8")


class VerdictCase(unittest.TestCase):
    def test_green(self):
        v, conf, red, reasons, repass = compute_verdict(GREEN_RR, {"dirty": False}, None)
        self.assertEqual((v, conf), ("GREEN", "high"))
        self.assertEqual((red, reasons, repass), ([], [], []))

    def test_attention_with_repass(self):
        v, conf, red, reasons, repass = compute_verdict(ATTN_RR, {"dirty": False}, None)
        self.assertEqual(v, "ATTENTION")
        self.assertFalse(red)
        self.assertTrue(any("линт" in r for r in reasons))
        self.assertTrue(any("deferred" in r for r in reasons))
        self.assertEqual(repass, ["perplexity-web locked"])   # dev-loop tool_failures → ПОВТОРНЫЙ ПРОХОД

    def test_red_on_failed_test_and_workflow(self):
        v, _c, red, _r, _rp = compute_verdict(RED_RR, {"dirty": False}, None)
        self.assertEqual(v, "RED")
        self.assertTrue(any("тест упал" in x for x in red))
        self.assertTrue(any("воркфлоу" in x for x in red))

    def test_dirty_tree_is_attention(self):
        v, _c, _red, reasons, _rp = compute_verdict(GREEN_RR,
                                                    {"dirty": True, "working_files": 4}, None)
        self.assertEqual(v, "ATTENTION")
        self.assertTrue(any("дерево не чисто" in r for r in reasons))

    def test_no_run_report_low_confidence(self):
        v, conf, _red, _r, _rp = compute_verdict(None, {"dirty": False}, None)
        self.assertEqual((v, conf), ("GREEN", "low"))


class FindRunReportCase(unittest.TestCase):
    def test_latest_and_by_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_run(tmp, GREEN_RR)
            _write_run(tmp, ATTN_RR)
            # свежий = тот, что записан последним (ATTN)
            by_session = find_run_report(tmp, session="g1")
            self.assertEqual(by_session["session_id"], "g1")
            self.assertIsNotNone(find_run_report(tmp))          # какой-то есть
            self.assertIsNone(find_run_report(tmp, session="nope"))

    def test_none_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(find_run_report(tmp))


class BashLogCase(unittest.TestCase):
    def test_filters_by_cwd_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            logdir = env.home / ".claude" / "logs"
            logdir.mkdir(parents=True)
            proj = os.path.join(tmp, "proj")
            recs = [
                {"cwd": proj, "session": "s1", "command": "python3 -m pytest tests/"},
                {"cwd": proj, "session": "s1", "command": "ruff check ."},
                {"cwd": "/other", "session": "s1", "command": "pytest"},   # чужой cwd — отсеять
                {"cwd": proj, "session": "s2", "command": "ls"},
            ]
            (logdir / "bash-commands.jsonl").write_text(
                "\n".join(json.dumps(r) for r in recs), encoding="utf-8")
            f = bash_log_forensics(env, proj)
            self.assertEqual(f["total"], 3)                     # три с нужным cwd
            self.assertEqual(len(f["tests"]), 1)
            self.assertEqual(len(f["lints"]), 1)
            f_s1 = bash_log_forensics(env, proj, session="s1")
            self.assertEqual(f_s1["total"], 2)                  # фильтр по сессии

    def test_none_without_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            _root, env = make_repo(tmp)
            self.assertIsNone(bash_log_forensics(env, tmp))


class GitCase(unittest.TestCase):
    def test_non_git_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(git_status(tmp))


class ReportAssemblyCase(unittest.TestCase):
    def test_full_report_json_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj_alpha"
            projdir.mkdir()
            _write_run(projdir, ATTN_RR)
            projects = [{"id": "alpha", "name": "Alpha", "type": "node-package",
                         "status": "active", "local_path": str(projdir)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            rep = analyze_report(env, config, config["projects"][0], with_health=False)
            self.assertEqual(rep["project"], "alpha")
            self.assertEqual(rep["verdict"], "ATTENTION")
            self.assertEqual(rep["confidence"], "high")
            self.assertEqual(rep["repass"], ["perplexity-web locked"])
            self.assertIsNone(rep["health"])                    # отключён
            # JSON-сериализуемо целиком
            self.assertIsInstance(json.dumps(rep, ensure_ascii=False), str)


class PendingLessonsCase(unittest.TestCase):
    """analyze напоминает о непросмотренных уроках analyst (ephemeral+candidate)."""
    def test_counts_ephemeral_and_candidate_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".claude" / "analyst" / "lessons"
            for state, n in (("ephemeral", 2), ("candidate", 1),
                             ("curated", 3), ("deprecated", 5)):
                d = base / state
                d.mkdir(parents=True)
                for i in range(n):
                    (d / f"l{i}.json").write_text("{}", encoding="utf-8")
            self.assertEqual(pending_lessons(tmp), 3)   # curated/deprecated не считаются

    def test_zero_when_no_analyst_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(pending_lessons(tmp), 0)

    def test_report_carries_pending_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj_beta"
            projdir.mkdir()
            _write_run(projdir, GREEN_RR)
            eph = projdir / ".claude" / "analyst" / "lessons" / "ephemeral"
            eph.mkdir(parents=True)
            (eph / "x.json").write_text("{}", encoding="utf-8")
            projects = [{"id": "beta", "name": "Beta", "type": "node-package",
                         "status": "active", "local_path": str(projdir)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            rep = analyze_report(env, config, config["projects"][0], with_health=False)
            self.assertEqual(rep["pending_lessons"], 1)


class AnalyticsConsumerCase(unittest.TestCase):
    def test_reads_only_normalized_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / ".swissknife" / "analytics"
            store.mkdir(parents=True)
            event = {"contract_version": "1.0.0", "provider_id": "codex", "session_id": "s",
                     "project_id": "p", "event_id": "e", "occurred_at": "2026-07-22T00:00:00Z",
                     "event_kind": "run_summary", "outcome": "ok", "metrics": {"usage": 1},
                     "provenance": {"raw_ref": "local:c", "sha256": "a" * 64,
                                    "reader_id": "codex-hook-context", "reader_version": "1.0.0"}}
            (store / "events.ndjson").write_text(json.dumps(event) + "\n", encoding="utf-8")
            slice_ = analytics_slice(tmp, "s")
            self.assertEqual((slice_["events"], slice_["providers"]), (1, ["codex"]))
            self.assertEqual(slice_["run_report"]["metrics"], {"usage": 1})
            self.assertEqual(slice_["run_report"]["provenance"][0]["sha256"], "a" * 64)


class MaindObservabilityCase(unittest.TestCase):
    def test_heavy_scan_no_graph_is_attention(self):
        v, _c, red, reasons, _rp = compute_verdict(MAIND_RR, {"dirty": False}, None)
        self.assertEqual(v, "ATTENTION")
        self.assertFalse(red)
        self.assertTrue(any("код-граф не использовался" in r for r in reasons))
        self.assertTrue(any("recall" in r for r in reasons))       # пустой recall тоже подсвечен

    def test_old_report_without_maind_key_ok(self):
        # старый run-report без ключа maind: эвристика не падает, вердикт прежний, без граф-шума
        v, _c, _red, reasons, _rp = compute_verdict(GREEN_RR, {"dirty": False}, None)
        self.assertEqual(v, "GREEN")
        self.assertFalse(any("граф" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
