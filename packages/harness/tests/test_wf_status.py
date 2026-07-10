"""wf_status.parse_run/parse_script_meta/summarize_result (P2.1).

Рукотворная мини-директория в tmp, повторяющая реальную раскладку (findings
`plans/SKM-ROADMAP-005/findings/P2-workflow-transcript-format.md`):

    <session>/workflows/scripts/<name>-wf_<id>.js
    <session>/subagents/workflows/wf_<id>/{journal.jsonl,agent-*.meta.json}

Никаких моков ФС — реальные файлы в tempdir (единый паттерн с test_settings_audit.py)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.wf_status import (
    discover_runs, parse_run, parse_script_meta, project_slug, summarize_result,
)


_SCRIPT_META = """
export const meta = {
  name: 'p2-1-demo',
  description: 'демо-прогон для юнит-теста wf_status',
  phases: [
    { title: 'Review', detail: 'первая фаза' },
    { title: 'Verify', detail: 'вторая фаза' },
  ],
}
"""


def _make_run(base, run_id="wf_demo123", journal_lines=None, script_text=_SCRIPT_META,
              agent_metas=None):
    """Собирает `<base>/session/subagents/workflows/<run_id>/` + sibling-скрипт
    (D19) под `<base>/session/workflows/scripts/`. Возвращает путь run_dir."""
    session = Path(base) / "session"
    run_dir = session / "subagents" / "workflows" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if journal_lines is not None:
        (run_dir / "journal.jsonl").write_text("\n".join(journal_lines) + "\n",
                                                 encoding="utf-8")
    if agent_metas:
        for agent_id, data in agent_metas.items():
            (run_dir / f"agent-{agent_id}.meta.json").write_text(
                json.dumps(data), encoding="utf-8")
    if script_text is not None:
        scripts_dir = session / "workflows" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / f"demo-{run_id}.js").write_text(script_text, encoding="utf-8")
    return run_dir


class ParseRunHappyPathCase(unittest.TestCase):
    """(а) Validation P2.1: мини-директория (journal: 2×started + 1×result, meta-скрипт
    с 2 фазами) → dict с agents_total=2, done=1, inflight=1, phases длины 2, 1 выжимка."""

    def test_two_started_one_result_two_phases(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = [
                json.dumps({"type": "started", "key": "v2:aaa", "agentId": "a1"}),
                json.dumps({"type": "started", "key": "v2:bbb", "agentId": "a2"}),
                json.dumps({"type": "result", "key": "v2:aaa", "agentId": "a1",
                            "result": {"summary": "готово"}}),
            ]
            run_dir = _make_run(tmp, journal_lines=lines,
                                 agent_metas={"a1": {"agentType": "workflow-subagent"},
                                              "a2": {"agentType": "workflow-subagent"}})

            status = parse_run(run_dir)

            self.assertFalse(status["degraded"], status["degraded_reasons"])
            self.assertEqual(status["agents_total"], 2)
            self.assertEqual(status["started"], 2)
            self.assertEqual(status["done"], 1)
            self.assertEqual(status["inflight"], 1)
            self.assertEqual(len(status["results"]), 1)
            self.assertEqual(status["results"][0]["summary"], "готово")
            self.assertEqual(len(status["meta"]["phases"]), 2)
            self.assertEqual(status["meta"]["phases"][0]["title"], "Review")
            self.assertEqual(status["meta"]["phases"][1]["detail"], "вторая фаза")
            self.assertTrue(status["meta"]["recognized"])
            self.assertEqual(status["run_id"], "wf_demo123")


class ParseRunDegradedCase(unittest.TestCase):
    """(б) Validation P2.1: битый journal (мусорная строка + отсутствующий файл) →
    degraded=True без исключения."""

    def test_missing_journal_is_degraded_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp, journal_lines=None)  # journal.jsonl вообще не создан

            status = parse_run(run_dir)

            self.assertTrue(status["degraded"])
            self.assertTrue(status["degraded_reasons"])
            self.assertIn("journal.jsonl", status["degraded_reasons"][0])
            self.assertEqual(status["agents_total"], 0)

    def test_garbage_only_journal_is_degraded_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = ["не json вообще", "{ битый json без закрытия"]
            run_dir = _make_run(tmp, journal_lines=lines)

            status = parse_run(run_dir)

            self.assertTrue(status["degraded"])
            self.assertTrue(status["degraded_reasons"])

    def test_mixed_garbage_and_valid_lines_not_degraded(self):
        """Одна мусорная строка среди валидных — `continue`, НЕ деградация (findings:
        «строки читать по одной; битую строку — continue, не падать»)."""
        with tempfile.TemporaryDirectory() as tmp:
            lines = [
                json.dumps({"type": "started", "key": "v2:aaa", "agentId": "a1"}),
                "мусорная строка ломает JSON {",
                json.dumps({"type": "result", "key": "v2:aaa", "agentId": "a1",
                            "result": "готово"}),
            ]
            run_dir = _make_run(tmp, journal_lines=lines, script_text=None)

            status = parse_run(run_dir)

            self.assertFalse(status["degraded"], status["degraded_reasons"])
            self.assertEqual(status["done"], 1)
            # скрипта нет вообще (D19 sibling не создан) — meta честно не распознана,
            # но это НЕ top-level degraded (Implementation Rules: отдельный флаг meta).
            self.assertFalse(status["meta"]["recognized"])
            self.assertEqual(status["meta"]["phases"], [])

    def test_missing_run_dir_itself_is_degraded_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = parse_run(Path(tmp) / "session" / "subagents" / "workflows" / "wf_ghost")
            self.assertTrue(status["degraded"])


class ParseScriptMetaCase(unittest.TestCase):
    def test_recognized_js_object_not_json(self):
        meta = parse_script_meta(_SCRIPT_META)
        self.assertTrue(meta["recognized"])
        self.assertEqual(meta["name"], "p2-1-demo")
        self.assertEqual(len(meta["phases"]), 2)

    def test_unrecognized_text_returns_empty_phases(self):
        meta = parse_script_meta("это не скрипт workflow вообще")
        self.assertFalse(meta["recognized"])
        self.assertEqual(meta["phases"], [])

    def test_none_text_does_not_raise(self):
        meta = parse_script_meta(None)
        self.assertFalse(meta["recognized"])
        self.assertEqual(meta["phases"], [])


class SummarizeResultCase(unittest.TestCase):
    def test_prefers_summary_over_title(self):
        self.assertEqual(
            summarize_result({"summary": "S", "title": "T"}), "S")

    def test_falls_back_to_title(self):
        self.assertEqual(summarize_result({"title": "T"}), "T")

    def test_falls_back_to_first_key(self):
        self.assertEqual(summarize_result({"findings": []}), "findings=[]")

    def test_plain_string(self):
        self.assertEqual(summarize_result("готово"), "готово")

    def test_never_raises_on_weird_input(self):
        class Weird(object):
            def __repr__(self):
                raise RuntimeError("boom")
        self.assertEqual(summarize_result(Weird()), "(результат не распознан)")


def _make_discoverable_run(config_dir, proj_slug, session, run_id, mtime=None):
    """Собирает `<config_dir>/projects/<proj_slug>/<session>/subagents/workflows/<run_id>/
    journal.jsonl` (P2.2 раскладка discovery) и, если задан, выставляет `mtime` через
    `os.utime` — детерминированный контроль порядка сортировки в тестах."""
    run_dir = Path(config_dir) / "projects" / proj_slug / session / "subagents" / "workflows" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    journal = run_dir / "journal.jsonl"
    journal.write_text(
        json.dumps({"type": "started", "key": "v2:x", "agentId": "a1"}) + "\n",
        encoding="utf-8",
    )
    if mtime is not None:
        os.utime(journal, (mtime, mtime))
    return run_dir


class DiscoverRunsCase(unittest.TestCase):
    """P2.2 Validation: tmp-дерево с 2 фейковыми прогонами (разный mtime) → свежайший
    первым; `--project` фильтрует по слагу; `--run` возвращает ровно его; пустая база →
    `[]` без падения."""

    def test_newest_by_mtime_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_discoverable_run(tmp, "-home-a-proj", "s1", "wf_old", mtime=1_000_000_000)
            _make_discoverable_run(tmp, "-home-a-proj", "s2", "wf_new", mtime=2_000_000_000)

            found = discover_runs(base_dir=tmp, limit=None)

            self.assertEqual([r["run_id"] for r in found], ["wf_new", "wf_old"])

    def test_project_filter_by_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_discoverable_run(tmp, "-home-a-proj-one", "s1", "wf_one", mtime=1_000)
            _make_discoverable_run(tmp, "-home-a-proj-two", "s1", "wf_two", mtime=2_000)

            found = discover_runs(base_dir=tmp, project="/home/a/proj-two", limit=None)

            self.assertEqual([r["run_id"] for r in found], ["wf_two"])

    def test_run_filter_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_discoverable_run(tmp, "-home-a-proj", "s1", "wf_aaa", mtime=1_000)
            _make_discoverable_run(tmp, "-home-a-proj", "s1", "wf_bbb", mtime=2_000)

            found = discover_runs(base_dir=tmp, run="wf_aaa", limit=None)

            self.assertEqual([r["run_id"] for r in found], ["wf_aaa"])

    def test_empty_base_returns_empty_list_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = discover_runs(base_dir=Path(tmp) / "does-not-exist")
            self.assertEqual(found, [])

    def test_default_limit_returns_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_discoverable_run(tmp, "-home-a-proj", "s1", "wf_old", mtime=1_000)
            _make_discoverable_run(tmp, "-home-a-proj", "s2", "wf_new", mtime=2_000)

            found = discover_runs(base_dir=tmp)

            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["run_id"], "wf_new")

    def test_sort_is_deterministic_tie_break_by_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_discoverable_run(tmp, "-home-a-proj", "s1", "wf_bbb", mtime=1_000)
            _make_discoverable_run(tmp, "-home-a-proj", "s2", "wf_aaa", mtime=1_000)

            found = discover_runs(base_dir=tmp, limit=None)

            self.assertEqual([r["run_id"] for r in found], ["wf_aaa", "wf_bbb"])


class ProjectSlugCase(unittest.TestCase):
    def test_matches_findings_example(self):
        self.assertEqual(
            project_slug("/home/vostrikov/projects/packages/loqum"),
            "-home-vostrikov-projects-packages-loqum",
        )


if __name__ == "__main__":
    unittest.main()
