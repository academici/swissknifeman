"""Internal documentation."""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.wf_status import (
    discover_runs, parse_run, parse_script_meta, project_slug, render_json,
    render_text, summarize_result, watch_loop,
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
    """Internal documentation."""
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
    """Internal documentation."""

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
    """Internal documentation."""

    def test_missing_journal_is_degraded_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp, journal_lines=None)

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
        """Internal documentation."""
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
    """Internal documentation."""
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
    """Internal documentation."""

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
            project_slug("/home/user/projects/packages/loqum"),
            "-home-user-projects-packages-loqum",
        )


class RenderTextCase(unittest.TestCase):
    """Internal documentation."""

    def _status(self, **overrides):
        status = {
            "run_id": "wf_demo123",
            "run_dir": "/tmp/wf_demo123",
            "degraded": False,
            "degraded_reasons": [],
            "agents_total": 2,
            "started": 2,
            "done": 1,
            "inflight": 1,
            "results": [{"agent_id": "a1", "summary": "готово"}],
            "meta": {
                "name": "p2-1-demo",
                "description": "демо",
                "phases": [
                    {"title": "Review", "detail": "первая фаза"},
                    {"title": "Verify", "detail": "вторая фаза"},
                ],
                "recognized": True,
                "script_path": "/tmp/script.js",
            },
        }
        status.update(overrides)
        return status

    def test_happy_path_contains_run_id_phases_and_percent(self):
        text = render_text(self._status())
        self.assertIn("wf_demo123", text)
        self.assertIn("Review", text)
        self.assertIn("Verify", text)
        self.assertIn("%", text)
        self.assertIn("статус: running", text)

    def test_deterministic_rendering_is_byte_for_byte(self):
        status = self._status()
        self.assertEqual(render_text(status), render_text(status))

    def test_done_state_when_no_inflight(self):
        text = render_text(self._status(inflight=0, done=2))
        self.assertIn("статус: done", text)

    def test_degraded_status_has_honest_reason_no_traceback(self):
        status = self._status(
            degraded=True,
            degraded_reasons=["journal.jsonl не найден: /tmp/wf_demo123/journal.jsonl"],
            started=0, done=0, inflight=0, agents_total=0, results=[],
            meta={"name": None, "description": None, "phases": [], "recognized": False,
                  "script_path": None},
        )
        text = render_text(status)
        self.assertIn("статус: degraded", text)
        self.assertIn("формат не распознан", text)
        self.assertIn("journal.jsonl не найден", text)
        self.assertNotIn("Traceback", text)


class RenderJsonCase(unittest.TestCase):
    """Internal documentation."""

    def test_round_trip_equals_original(self):
        status = parse_run(_make_run(tempfile.mkdtemp(), journal_lines=[
            json.dumps({"type": "started", "key": "v2:a", "agentId": "a1"}),
            json.dumps({"type": "result", "key": "v2:a", "agentId": "a1",
                        "result": {"summary": "готово"}}),
        ]))
        self.assertEqual(json.loads(render_json(status)), status)

    def test_json_is_valid_and_not_ascii_escaped(self):
        status = {"run_id": "wf_x", "degraded": False, "meta": {"name": "имя"}}
        dumped = render_json(status)
        self.assertEqual(json.loads(dumped), status)
        self.assertIn("имя", dumped)


class WatchLoopCase(unittest.TestCase):
    """Internal documentation."""

    def test_stops_when_inflight_reaches_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = [
                json.dumps({"type": "started", "key": "v2:a", "agentId": "a1"}),
                json.dumps({"type": "result", "key": "v2:a", "agentId": "a1",
                            "result": "готово"}),
            ]
            run_dir = _make_run(tmp, journal_lines=lines)
            sleeps = []
            buf = io.StringIO()

            exit_code = watch_loop(run_dir, out=buf, sleep_fn=sleeps.append,
                                    max_iterations=5)

            self.assertEqual(exit_code, 0)
            self.assertEqual(sleeps, [])
            self.assertIn("wf_demo123", buf.getvalue())

    def test_respects_max_iterations_when_still_inflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = [json.dumps({"type": "started", "key": "v2:a", "agentId": "a1"})]
            run_dir = _make_run(tmp, journal_lines=lines)
            sleeps = []
            buf = io.StringIO()

            exit_code = watch_loop(run_dir, out=buf, sleep_fn=sleeps.append,
                                    max_iterations=3)

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(sleeps), 2)
            self.assertEqual(buf.getvalue().count("run: wf_demo123"), 3)

    def test_keyboard_interrupt_gives_clean_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = [json.dumps({"type": "started", "key": "v2:a", "agentId": "a1"})]
            run_dir = _make_run(tmp, journal_lines=lines)
            buf = io.StringIO()

            def _raise(_interval):
                raise KeyboardInterrupt

            exit_code = watch_loop(run_dir, out=buf, sleep_fn=_raise, max_iterations=None)

            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
