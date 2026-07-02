"""Тесты digest: чистые извлекатели (сигналы A/B) + защитная деградация + запись в ephemeral."""
import json
import tempfile
import unittest
from pathlib import Path

from analyst import digest, lessons


def _run_report(**over):
    rr = {
        "schema": 1,
        "session_id": "sid-123",
        "generated_at": "2026-07-01T10:00:00Z",
        "tools": {"total": 5, "by_name": {"Bash": 5}},
        "files_changed": ["/proj/src/Service.php", "/proj/tests/ServiceTest.php"],
        "tool_failures": [],
        "bash": {"tests": [], "lints": [], "failed": []},
        "workflows": [],
        "devloop": None,
        "maind": None,
    }
    rr.update(over)
    return rr


class TestExtractors(unittest.TestCase):
    def test_resolved_failure(self):
        rr = _run_report(bash={"tests": [
            {"command": "vendor/bin/pest tests/ServiceTest.php", "ok": False},
            {"command": "vendor/bin/pest tests/ServiceTest.php", "ok": True},
        ], "lints": [], "failed": []})
        cands = digest.extract_resolved_failures(rr, scope="project:proj", project="proj")
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertEqual(c["kind"], "gotcha")
        self.assertEqual(c["provenance"]["detector"], "resolved-failure")
        self.assertIn("test-pass", c["evidence"])
        self.assertIn("attempts:2", c["evidence"])
        # файлы/счётчики вынесены в meta (action — чистый семантический текст, S11)
        self.assertIn("ServiceTest.php", c["meta"]["files"])
        self.assertEqual(c["meta"]["attempts"], 2)
        self.assertNotIn("Уточни", c["action"])
        self.assertIn("Уточни", c["review_hint"])

    def test_failure_without_pass_is_ignored(self):
        rr = _run_report(bash={"tests": [
            {"command": "vendor/bin/pest tests/ServiceTest.php", "ok": False},
        ], "lints": [], "failed": []})
        self.assertEqual(digest.extract_resolved_failures(rr, scope="s", project="p"), [])

    def test_dissimilar_pass_not_matched(self):
        rr = _run_report(bash={"tests": [
            {"command": "vendor/bin/pest tests/ServiceTest.php", "ok": False},
            {"command": "npm run build --production", "ok": True},
        ], "lints": [], "failed": []})
        self.assertEqual(digest.extract_resolved_failures(rr, scope="s", project="p"), [])

    def test_workarounds(self):
        rr = _run_report(devloop={"workarounds": [
            "захардкодил лимит 100 пока нет конфига",
            "захардкодил лимит 100 пока нет конфига",  # дубль — схлопнуть
        ]})
        cands = digest.extract_workarounds(rr, scope="project:proj", project="proj")
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["provenance"]["detector"], "workaround")
        self.assertIn("workaround", cands[0]["evidence"])
        self.assertIn("захардкодил", cands[0]["action"])

    def test_extract_candidates_combines_and_degrades(self):
        self.assertEqual(digest.extract_candidates(None, scope="s", project="p"), [])
        self.assertEqual(digest.extract_candidates({}, scope="s", project="p"), [])
        rr = _run_report(
            bash={"tests": [
                {"command": "pytest test_x.py -k slow", "ok": False},
                {"command": "pytest test_x.py -k slow", "ok": True}],
                "lints": [], "failed": []},
            devloop={"workarounds": ["обходка X"]})
        cands = digest.extract_candidates(rr, scope="s", project="p")
        self.assertEqual(len(cands), 2)


class TestDigestCmd(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self._tmp.name)
        (self.proj / ".claude" / "runs").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_rr(self, rr):
        (self.proj / ".claude" / "runs" / f"{rr['session_id']}.json").write_text(
            json.dumps(rr), encoding="utf-8")

    def test_digest_writes_ephemeral_and_is_idempotent(self):
        import os
        rr = _run_report(bash={"tests": [
            {"command": "vendor/bin/pest", "ok": False},
            {"command": "vendor/bin/pest", "ok": True}], "lints": [], "failed": []})
        self._write_rr(rr)
        cwd = os.getcwd()
        try:
            os.chdir(self.proj)
            from analyst.cli import main
            main([str(self.proj), "digest"])
            eph = lessons.list_lessons(str(self.proj), "ephemeral")
            self.assertEqual(len(eph), 1)
            # аудит записан
            audit = lessons.read_audit(str(self.proj))
            self.assertTrue(any(r.get("action") == "digest" for r in audit))
            # повторный digest не создаёт дубль
            main([str(self.proj), "digest"])
            self.assertEqual(len(lessons.list_lessons(str(self.proj), "ephemeral")), 1)
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
