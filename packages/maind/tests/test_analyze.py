"""Тесты analyze.py: поиск run-report, форензика bash-лога, вердикт GREEN/ATTENTION/RED,
сборка отчёта и --json. Без сети/демона — health-срез отключаем (with_health=False),
живой замер памяти не нужен для логики разбора."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from maind.analyze import (analyze_report, bash_log_forensics, compute_verdict,
                           find_run_report, git_status, pack_drift, pathology_slice,
                           tokens_slice)
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

# schema=2 с usage.totals (B-4: блок tokens) — in/out подобраны так, чтобы при медиане тренда
# 20k out=48k давал ровно ×2.4, как в примере из спеки.
TOKENS_RR = {"schema": 2, "tools": {"total": 1, "by_name": {"Bash": 1}}, "files_changed": [],
             "bash": {"tests": [], "lints": [], "failed": []},
             "tool_failures": [], "workflows": [], "devloop": None,
             "usage": {"totals": {"in": 120000, "out": 48000,
                                   "cache_read": 800000, "cache_creation": 5000},
                       "by_model": {"claude-sonnet-5": {"in": 120000, "out": 48000,
                                                        "cache_read": 800000,
                                                        "cache_creation": 5000, "msgs": 10}},
                       "cache_hit": 0.87, "agents": [], "subagents_parsed": 0,
                       "subagents_skipped": 0},
             "session_id": "t1"}


# C-2: patology-фикстуры для core.pathology.detect() поверх run-report.
# protected-write (attention, вне зависимости от schema) — правки managed-путей.
PATH_ATTN_RR = {"schema": 1, "tools": {"total": 2, "by_name": {"Edit": 2}},
                "files_changed": ["/p/a.py"],
                "bash": {"tests": [{"command": "pytest", "ok": True}], "lints": [], "failed": []},
                "tool_failures": [], "workflows": [], "devloop": None,
                "protected_writes": ["packages/skiller/skills/x/SKILL.md"],
                "session_id": "path-attn1"}

# no-op-run (info) — много тул-вызовов, ни файлов/тестов/retrieval; тест сам зелёный,
# так что этот отчёт НЕ должен менять вердикт, только попасть в efficiency.
PATH_INFO_RR = {"schema": 1, "tools": {"total": 25, "by_name": {"Read": 25}},
                "files_changed": [], "bash": {"tests": [], "lints": [], "failed": []},
                "tool_failures": [], "workflows": [], "devloop": None,
                "session_id": "path-info1"}


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


def _write_trend(projdir, rows):
    d = Path(projdir) / ".claude" / "analyze"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "usage-trend.ndjson", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _write_baseline(projdir, data):
    d = Path(projdir) / ".claude" / "analyze"
    d.mkdir(parents=True, exist_ok=True)
    (d / "baseline.json").write_text(json.dumps(data), encoding="utf-8")


class TokensCase(unittest.TestCase):
    def test_schema1_no_usage_block_and_no_error(self):
        # schema=1 (без usage) — блок МОЛЧА отсутствует, никаких падений/упоминаний
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(tokens_slice(GREEN_RR, tmp))
            v, _c, red, reasons, _rp = compute_verdict(GREEN_RR, {"dirty": False}, None,
                                                        tokens=None)
            self.assertEqual(v, "GREEN")
            self.assertFalse(red)
            self.assertFalse(any("токены" in r or "tokens" in r for r in reasons))

    def test_no_run_report_no_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(tokens_slice(None, tmp))

    def test_schema2_without_trend_shows_only_current_numbers(self):
        # <3 строк тренда (тут вообще их нет) — только текущие числа, без сравнения
        with tempfile.TemporaryDirectory() as tmp:
            blk = tokens_slice(TOKENS_RR, tmp)
            self.assertIsNotNone(blk)
            self.assertEqual(blk["in"], 120000)
            self.assertEqual(blk["out"], 48000)
            self.assertAlmostEqual(blk["cache_hit"], 0.87)
            self.assertIsNone(blk["trend"])
            self.assertIsNone(blk["baseline"])

    def test_schema2_with_trend_computes_median_and_ratio(self):
        # 20 исторических прогонов с out=20k (медиана=20k) + строка ТЕКУЩЕЙ сессии (t1),
        # которая должна быть исключена из тренда по полю session.
        with tempfile.TemporaryDirectory() as tmp:
            rows = [{"session": "t1", "in": 999, "out": 999}]     # текущая — исключить
            rows += [{"session": f"h{i}", "in": 10000, "out": 20000} for i in range(20)]
            _write_trend(tmp, rows)
            blk = tokens_slice(TOKENS_RR, tmp)
            tr = blk["trend"]
            self.assertEqual(tr["n"], 20)                          # текущая сессия не в счёте
            self.assertEqual(tr["median_out"], 20000)
            self.assertEqual(tr["median_in"], 10000)
            self.assertAlmostEqual(tr["ratio_out"], 2.4)           # 48000 / 20000

    def test_attention_reason_when_out_exceeds_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [{"session": f"h{i}", "in": 10000, "out": 20000} for i in range(20)]
            _write_trend(tmp, rows)
            tokens = tokens_slice(TOKENS_RR, tmp)
            v, _c, red, reasons, _rp = compute_verdict(TOKENS_RR, {"dirty": False}, None,
                                                        tokens=tokens)
            self.assertEqual(v, "ATTENTION")
            self.assertFalse(red)                                  # токены никогда не дают RED
            self.assertTrue(any("токены ×2.4" in r for r in reasons))

    def test_below_threshold_no_reason(self):
        # медиана высокая (out текущего прогона ниже 1.5×медианы и p90) — сравнение не триггерит
        with tempfile.TemporaryDirectory() as tmp:
            rows = [{"session": f"h{i}", "in": 10000, "out": 40000} for i in range(20)]
            _write_trend(tmp, rows)
            tokens = tokens_slice(TOKENS_RR, tmp)
            v, _c, _red, reasons, _rp = compute_verdict(TOKENS_RR, {"dirty": False}, None,
                                                         tokens=tokens)
            self.assertEqual(v, "GREEN")
            self.assertFalse(any("токены" in r for r in reasons))

    def test_pinned_baseline_totals_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_baseline(tmp, {"totals": {"median_out": 30000}})
            blk = tokens_slice(TOKENS_RR, tmp)
            self.assertEqual(blk["baseline"]["median_out"], 30000)
            self.assertAlmostEqual(blk["baseline"]["ratio_out"], 1.6)   # 48000 / 30000

    def test_pinned_baseline_by_model_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_baseline(tmp, {"by_model": {"claude-sonnet-5": {"median_out": 24000}}})
            blk = tokens_slice(TOKENS_RR, tmp)
            self.assertEqual(blk["baseline"]["median_out"], 24000)

    def test_baseline_missing_or_malformed_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(tokens_slice(TOKENS_RR, tmp)["baseline"])   # файла нет
            _write_baseline(tmp, {"unexpected": "shape"})                # неожиданный формат
            self.assertIsNone(tokens_slice(TOKENS_RR, tmp)["baseline"])
            _write_baseline(tmp, "not even a dict")                      # битый формат
            self.assertIsNone(tokens_slice(TOKENS_RR, tmp)["baseline"])

    def test_full_report_includes_tokens_block_json_serializable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj_tok"
            projdir.mkdir()
            _write_run(projdir, TOKENS_RR)
            rows = [{"session": f"h{i}", "in": 10000, "out": 20000} for i in range(20)]
            _write_trend(projdir, rows)
            projects = [{"id": "tok", "name": "Tok", "type": "node-package",
                         "status": "active", "local_path": str(projdir)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            rep = analyze_report(env, config, config["projects"][0], with_health=False)
            self.assertIsNotNone(rep["tokens"])
            self.assertEqual(rep["verdict"], "ATTENTION")
            self.assertTrue(any("токены ×2.4" in r for r in rep["reasons"]))
            self.assertIsInstance(json.dumps(rep, ensure_ascii=False), str)

    def test_full_report_schema1_tokens_key_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj_alpha2"
            projdir.mkdir()
            _write_run(projdir, GREEN_RR)
            projects = [{"id": "alpha2", "name": "Alpha2", "type": "node-package",
                         "status": "active", "local_path": str(projdir)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            rep = analyze_report(env, config, config["projects"][0], with_health=False)
            self.assertIsNone(rep["tokens"])
            self.assertEqual(rep["verdict"], "GREEN")


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_pack_lock(projdir, files):
    """Синтетический .claude/agent-pack.lock.json с одним паком `demo-pack`."""
    d = Path(projdir) / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    lock = {"schema": 1, "packs": {"demo-pack": {"version": "1.0.0", "files": files}}}
    (d / "agent-pack.lock.json").write_text(json.dumps(lock), encoding="utf-8")


class PackDriftCase(unittest.TestCase):
    def test_no_lock_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(pack_drift(tmp), [])

    def test_locally_modified_generated_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tgt = Path(tmp) / ".claude" / "agents" / "reviewer.md"
            tgt.parent.mkdir(parents=True)
            tgt.write_text("правлено руками, не как в паке", encoding="utf-8")
            _write_pack_lock(tmp, [
                {"src": "agents/reviewer.md", "target": ".claude/agents/reviewer.md",
                 "kind": "template", "base_sha256": _sha("оригинал из пака"),
                 "user_owned": False},
            ])
            reasons = pack_drift(tmp)
            self.assertEqual(len(reasons), 1)
            self.assertIn(".claude/agents/reviewer.md", reasons[0])
            self.assertIn("harness agent-packs render", reasons[0])

    def test_missing_generated_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_pack_lock(tmp, [
                {"src": "agents/reviewer.md", "target": ".claude/agents/reviewer.md",
                 "kind": "template", "base_sha256": _sha("оригинал из пака"),
                 "user_owned": False},
            ])
            reasons = pack_drift(tmp)
            self.assertEqual(len(reasons), 1)
            self.assertIn(".claude/agents/reviewer.md", reasons[0])

    def test_untouched_file_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tgt = Path(tmp) / ".claude" / "agents" / "reviewer.md"
            tgt.parent.mkdir(parents=True)
            tgt.write_text("оригинал из пака", encoding="utf-8")
            _write_pack_lock(tmp, [
                {"src": "agents/reviewer.md", "target": ".claude/agents/reviewer.md",
                 "kind": "template", "base_sha256": _sha("оригинал из пака"),
                 "user_owned": False},
            ])
            self.assertEqual(pack_drift(tmp), [])

    def test_user_owned_true_is_never_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tgt = Path(tmp) / ".claude" / "rules" / "override.md"
            tgt.parent.mkdir(parents=True)
            tgt.write_text("правка пользователя", encoding="utf-8")
            _write_pack_lock(tmp, [
                {"src": "rules/override.md", "target": ".claude/rules/override.md",
                 "kind": "template", "base_sha256": _sha("оригинал из пака"),
                 "user_owned": True},
            ])
            self.assertEqual(pack_drift(tmp), [])

    def test_merge_kind_is_never_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_pack_lock(tmp, [
                {"src": "hooks/settings-fragment.json", "target": ".claude/settings.json",
                 "kind": "merge", "base_sha256": _sha("фрагмент"), "user_owned": False},
            ])
            self.assertEqual(pack_drift(tmp), [])

    def test_review_gate_without_user_owned_field_is_temporarily_exempt(self):
        # старый лок (до появления поля user_owned): review-gate.env.ini — известное
        # исключение, чтобы первый же analyze после апгрейда схемы не кричал зря.
        with tempfile.TemporaryDirectory() as tmp:
            tgt = Path(tmp) / ".claude" / "review-gate.env.ini"
            tgt.parent.mkdir(parents=True)
            tgt.write_text("правка пользователя", encoding="utf-8")
            _write_pack_lock(tmp, [
                {"src": "hooks/review-gate.env.ini", "target": ".claude/review-gate.env.ini",
                 "kind": "template", "base_sha256": _sha("оригинал из пака")},
            ])
            self.assertEqual(pack_drift(tmp), [])

    def test_other_target_without_user_owned_field_is_flagged(self):
        # допуск точечный: любой ДРУГОЙ target без поля user_owned — трактуем как
        # НЕ user_owned (как в harness .get(..., False)) и проверяем как обычно.
        with tempfile.TemporaryDirectory() as tmp:
            tgt = Path(tmp) / ".claude" / "agents" / "reviewer.md"
            tgt.parent.mkdir(parents=True)
            tgt.write_text("правлено руками", encoding="utf-8")
            _write_pack_lock(tmp, [
                {"src": "agents/reviewer.md", "target": ".claude/agents/reviewer.md",
                 "kind": "template", "base_sha256": _sha("оригинал из пака")},
            ])
            reasons = pack_drift(tmp)
            self.assertEqual(len(reasons), 1)

    def test_compute_verdict_attention_not_red(self):
        drift = ["generated-файл пака правлен локально: .claude/agents/reviewer.md — "
                 "перенеси правку в override и восстанови (harness agent-packs render)"]
        v, _c, red, reasons, _rp = compute_verdict(GREEN_RR, {"dirty": False}, None,
                                                    pack_drift=drift)
        self.assertEqual(v, "ATTENTION")
        self.assertEqual(red, [])                              # RED от pack-drift не бывает
        self.assertEqual(reasons, drift)

    def test_full_report_includes_pack_drift_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj_pack"
            projdir.mkdir()
            _write_run(projdir, GREEN_RR)
            tgt = projdir / ".claude" / "agents" / "reviewer.md"
            tgt.parent.mkdir(parents=True)
            tgt.write_text("правлено руками", encoding="utf-8")
            _write_pack_lock(projdir, [
                {"src": "agents/reviewer.md", "target": ".claude/agents/reviewer.md",
                 "kind": "template", "base_sha256": _sha("оригинал из пака"),
                 "user_owned": False},
            ])
            projects = [{"id": "pack", "name": "Pack", "type": "node-package",
                         "status": "active", "local_path": str(projdir)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            rep = analyze_report(env, config, config["projects"][0], with_health=False)
            self.assertEqual(len(rep["pack_drift"]), 1)
            self.assertEqual(rep["verdict"], "ATTENTION")
            self.assertTrue(any("правлен локально" in r for r in rep["reasons"]))
            self.assertIsInstance(json.dumps(rep, ensure_ascii=False), str)


class PathologyCase(unittest.TestCase):
    """C-2: core.pathology.detect() поверх run-report — attention в reasons вердикта,
    info в rep['efficiency'], RED от патологий никогда не бывает, schema=1-«спокойный»
    отчёт не производит ни находок, ни секции."""

    def test_slice_splits_attention_and_info(self):
        attention, efficiency = pathology_slice(PATH_ATTN_RR)
        self.assertEqual(len(attention), 1)
        self.assertIn("managed-путей", attention[0])
        self.assertEqual(efficiency, [])

    def test_slice_info_goes_to_efficiency(self):
        attention, efficiency = pathology_slice(PATH_INFO_RR)
        self.assertEqual(attention, [])
        self.assertEqual(len(efficiency), 1)
        self.assertEqual(efficiency[0]["code"], "no-op-run")
        self.assertEqual(efficiency[0]["severity"], "info")

    def test_slice_defensive_on_none_run_report(self):
        # run-report может отсутствовать (форензика без источника) — detect() не падает
        self.assertEqual(pathology_slice(None), ([], []))

    def test_compute_verdict_attention_pathology_never_red(self):
        v, _c, red, reasons, _rp = compute_verdict(
            GREEN_RR, {"dirty": False}, None,
            pathology_attention=["любая патология-строка"])
        self.assertEqual(v, "ATTENTION")
        self.assertEqual(red, [])                              # ЖЁСТКО: патологии не дают RED
        self.assertEqual(reasons, ["любая патология-строка"])

    def test_full_report_attention_pathology_is_verdict_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj_path_attn"
            projdir.mkdir()
            _write_run(projdir, PATH_ATTN_RR)
            projects = [{"id": "path-attn", "name": "PathAttn", "type": "node-package",
                         "status": "active", "local_path": str(projdir)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            rep = analyze_report(env, config, config["projects"][0], with_health=False)
            self.assertEqual(rep["verdict"], "ATTENTION")
            self.assertEqual(rep["red"], [])                    # RED от патологий не бывает
            self.assertTrue(any("managed-путей" in r for r in rep["reasons"]))
            self.assertEqual(rep["efficiency"], [])              # это attention, не info
            self.assertIsInstance(json.dumps(rep, ensure_ascii=False), str)

    def test_full_report_info_pathology_in_efficiency_verdict_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj_path_info"
            projdir.mkdir()
            _write_run(projdir, PATH_INFO_RR)
            projects = [{"id": "path-info", "name": "PathInfo", "type": "node-package",
                         "status": "active", "local_path": str(projdir)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            rep = analyze_report(env, config, config["projects"][0], with_health=False)
            self.assertEqual(rep["verdict"], "GREEN")           # info не меняет вердикт
            self.assertEqual(rep["red"], [])
            self.assertEqual(len(rep["efficiency"]), 1)
            self.assertEqual(rep["efficiency"][0]["code"], "no-op-run")
            self.assertFalse(any("no-op-run" in r for r in rep["reasons"]))
            self.assertIsInstance(json.dumps(rep, ensure_ascii=False), str)

    def test_full_report_schema1_clean_report_no_pathology(self):
        # GREEN_RR — SCHEMA=1 с небольшими объёмами (tools.total=3, файлы с прогнанными
        # тестами) — detect() пуст: ни секции efficiency, ни лишних reasons.
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj_path_clean"
            projdir.mkdir()
            _write_run(projdir, GREEN_RR)
            projects = [{"id": "path-clean", "name": "PathClean", "type": "node-package",
                         "status": "active", "local_path": str(projdir)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            rep = analyze_report(env, config, config["projects"][0], with_health=False)
            self.assertEqual(rep["verdict"], "GREEN")
            self.assertEqual(rep["efficiency"], [])
            self.assertEqual(rep["reasons"], [])


if __name__ == "__main__":
    unittest.main()
